import json
import time
from uuid import uuid4
from datetime import datetime
from ..canonicalization.derive import sha
from ..persistence.repository import digest, RevisionConflict
from ..planning.repository import PlanningRepository
from .contracts import ExecutionPolicy, RuleOutcome, ComplianceResult, ModelPackage
from .models import load_package
from .executor import execute, run_id
from .replay import verify


class ExecutionRepository:
    def __init__(self, settings):
        self.planning = PlanningRepository(settings)
        self.base = self.planning.base
        self.ingestion = self.planning.ingestion

    def get(self, ctx, payer, execution_id):
        ctx.require(ctx.tenant_id, payer)
        with self.ingestion.db() as db:
            row = db.execute('SELECT payload,sha256 FROM compliance_results WHERE tenant_id=? AND taxpayer_id=? AND execution_id=?',
                (ctx.tenant_id,payer,execution_id)).fetchone()
        if row is None: raise KeyError('Execution result not found')
        if digest(row['payload'].encode()) != row['sha256']: raise ValueError('Execution result integrity failure')
        return ComplianceResult.model_validate_json(row['payload'])

    def attempts(self, ctx, payer, execution_id):
        ctx.require(ctx.tenant_id, payer)
        with self.ingestion.db() as db:
            exists = db.execute('SELECT 1 FROM rule_execution_runs WHERE tenant_id=? AND taxpayer_id=? AND execution_id=?',
                (ctx.tenant_id,payer,execution_id)).fetchone()
            if not exists: raise KeyError('Execution run not found')
            rows = db.execute('SELECT payload,sha256 FROM rule_execution_attempts WHERE tenant_id=? AND taxpayer_id=? AND execution_id=? ORDER BY attempt_id',
                (ctx.tenant_id,payer,execution_id)).fetchall()
        results=[]
        for row in rows:
            if digest(row['payload'].encode()) != row['sha256']: raise ValueError('Attempt integrity failure')
            results.append(RuleOutcome.model_validate_json(row['payload']))
        return tuple(sorted(results,key=lambda a:(a.key.rule_id,a.key.rule_version,a.key.unit_type,a.key.unit_id,a.attempt_number)))

    def work(self, ctx, payer, evaluation_id, *, package=None, policy=None, runner=None):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        self.base.initialize()
        plan=self.planning.get(ctx,payer,evaluation_id)
        inputs=self.planning.snapshot(ctx,payer,evaluation_id)
        record=self.base.record(ctx,payer,plan.record_id,plan.record_revision)
        master=self.base.taxpayer(ctx,payer,record.taxpayer_master_revision)
        if sha(record.model_dump(mode='json'))!=plan.record_sha256 or master.model_dump(mode='json')!=inputs['master']:
            raise ValueError('Stored source revision/master differs from planning snapshot')
        package=package or load_package()
        policy=policy or ExecutionPolicy()
        identifier=run_id(plan,package,policy,None)
        snapshot=json.dumps(dict(planning=inputs,package=package.model_dump(mode='json'),policy=policy.model_dump(mode='json')),
            sort_keys=True,ensure_ascii=False,separators=(',',':'))
        lease_token=uuid4().hex
        with self.ingestion.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM rule_execution_runs WHERE tenant_id=? AND taxpayer_id=? AND execution_id=?',
                (ctx.tenant_id,payer,identifier)).fetchone()
            if row:
                if row['inputs']!=snapshot or row['inputs_sha256']!=digest(snapshot.encode()): raise ValueError('Run snapshot integrity mismatch')
                if row['status']=='COMPLETE': return self.get(ctx,payer,identifier)
                if row['lease_until']>time.time(): raise RevisionConflict('Execution already running')
                stamp=datetime.fromisoformat(row['created_at'])
                db.execute('UPDATE rule_execution_runs SET lease_token=?,lease_until=? WHERE tenant_id=? AND taxpayer_id=? AND execution_id=?',
                    (lease_token,time.time()+120,ctx.tenant_id,payer,identifier))
            else:
                from ..domain.base import utcnow
                stamp=utcnow()
                db.execute('INSERT INTO rule_execution_runs VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (ctx.tenant_id,payer,identifier,evaluation_id,'RUNNING',lease_token,time.time()+120,stamp.isoformat(),snapshot,digest(snapshot.encode())))
        def fence(db):
            row=db.execute('SELECT lease_token,status FROM rule_execution_runs WHERE tenant_id=? AND taxpayer_id=? AND execution_id=?',
                (ctx.tenant_id,payer,identifier)).fetchone()
            if row['lease_token']!=lease_token or row['status']!='RUNNING': raise RevisionConflict('Execution lease superseded')
        def store(attempt):
            raw=attempt.model_dump_json()
            with self.ingestion.db() as db:
                db.execute('BEGIN IMMEDIATE');fence(db)
                db.execute('INSERT INTO rule_execution_attempts VALUES(?,?,?,?,?,?)',
                    (ctx.tenant_id,payer,identifier,attempt.attempt_id,raw,digest(raw.encode())))
                self.base._audit(db,ctx,ctx.tenant_id,payer,'ARTIFACT_STORED',digest(raw.encode()),record,reason='Rule execution attempt stored')
                db.execute('UPDATE rule_execution_runs SET lease_until=? WHERE tenant_id=? AND taxpayer_id=? AND execution_id=?',
                    (time.time()+120,ctx.tenant_id,payer,identifier))
        initial=self.attempts(ctx,payer,identifier)
        # Integrity and bound facts of existing attempts are checked before resume.
        from .outcomes import validate
        for attempt in initial: validate(plan,(attempt,),package)
        result=execute(plan,inputs,package,policy,runner=runner,created_at=stamp,on_attempt=store,initial_attempts=initial)
        verify(result,plan,inputs,package,policy)
        raw=result.model_dump_json()
        with self.ingestion.db() as db:
            db.execute('BEGIN IMMEDIATE');fence(db)
            db.execute('INSERT INTO compliance_results VALUES(?,?,?,?,?)',(ctx.tenant_id,payer,identifier,raw,digest(raw.encode())))
            self.base._audit(db,ctx,ctx.tenant_id,payer,'ARTIFACT_STORED',digest(raw.encode()),record,reason='Compliance result stored')
            db.execute("UPDATE rule_execution_runs SET status='COMPLETE',lease_until=0 WHERE tenant_id=? AND taxpayer_id=? AND execution_id=?",
                (ctx.tenant_id,payer,identifier))
        return result

    def replay(self,ctx,payer,execution_id):
        result=self.get(ctx,payer,execution_id)
        with self.ingestion.db() as db:
            row=db.execute('SELECT inputs,inputs_sha256 FROM rule_execution_runs WHERE tenant_id=? AND taxpayer_id=? AND execution_id=?',
                (ctx.tenant_id,payer,execution_id)).fetchone()
        if digest(row['inputs'].encode())!=row['inputs_sha256']: raise ValueError('Replay snapshot integrity failure')
        snapshot=json.loads(row['inputs'])
        plan=self.planning.get(ctx,payer,result.evaluation_id)
        return verify(result,plan,snapshot['planning'],ModelPackage.model_validate(snapshot['package']),ExecutionPolicy.model_validate(snapshot['policy']))
