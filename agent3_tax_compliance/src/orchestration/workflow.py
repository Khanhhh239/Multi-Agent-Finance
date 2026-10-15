"""Revision-pinned orchestration. Existing stage repositories own their artifacts."""
import json
import time
from pathlib import Path
from uuid import uuid4
from datetime import datetime
from ..domain.base import utcnow
from ..canonicalization.derive import sha
from ..persistence.repository import digest,RevisionConflict
from ..review.repository import ReviewRepository
from ..review.contracts import ReviewError
from ..rules.repository import ExecutionRepository
from ..rules.models import load_package
from ..rules.contracts import ModelPackage,ExecutionPolicy,ExecutionError
from ..rules.zen_adapter import evaluate as evaluate_zen
from ..explanation.service import load_templates,render
from .contracts import EvaluationCommand,EvaluationArtifact,EvaluationReport,EvaluationState


def implementation_sha():
    root=Path(__file__).resolve().parents[1]
    return sha({p.relative_to(root).as_posix():digest(p.read_bytes()) for folder in ('orchestration','explanation')
        for p in sorted((root/folder).rglob('*')) if p.is_file() and p.suffix in ('.py','.json')})


class Workflow:
    def __init__(self,settings):
        self.execution=ExecutionRepository(settings)
        self.planning=self.execution.planning
        self.quality=self.planning.quality
        self.review=ReviewRepository(settings)
        self.base=self.execution.base
        self.ingestion=self.execution.ingestion

    def row(self,ctx,payer,identifier):
        ctx.require(ctx.tenant_id,payer)
        with self.ingestion.db() as db:
            row=db.execute('SELECT * FROM evaluations WHERE tenant_id=? AND taxpayer_id=? AND evaluation_id=?',
                (ctx.tenant_id,payer,identifier)).fetchone()
        if row is None:raise KeyError('Evaluation not found')
        if digest(row['snapshot'].encode())!=row['snapshot_sha256']:raise ValueError('Evaluation snapshot integrity failure')
        return row

    def artifact(self,ctx,payer,identifier):
        self.row(ctx,payer,identifier)
        with self.ingestion.db() as db:
            row=db.execute('SELECT payload,sha256 FROM evaluation_reports WHERE tenant_id=? AND taxpayer_id=? AND evaluation_id=?',
                (ctx.tenant_id,payer,identifier)).fetchone()
        if row is None:raise ReviewError('EVALUATION_NOT_COMPLETE','Evaluation has no final report yet.',409)
        if digest(row['payload'].encode())!=row['sha256']:raise ValueError('Evaluation report integrity failure')
        artifact=EvaluationArtifact.model_validate_json(row['payload'])
        if (artifact.report.tenant_id,artifact.report.taxpayer_id,artifact.report.evaluation_id)!=(ctx.tenant_id,payer,identifier):
            raise ValueError('Evaluation artifact scope mismatch')
        return artifact

    def get(self,ctx,payer,identifier):
        row=self.row(ctx,payer,identifier)
        head=self.base.record(ctx,payer,row['record_id'])
        report=self.artifact(ctx,payer,identifier).report if row['status']=='COMPLETED' else None
        return EvaluationState(evaluation_id=identifier,record_id=row['record_id'],record_revision=row['revision'],status=row['status'],
            stage=row['stage'],latest_record_revision=head.revision,is_current_revision=head.revision==row['revision'],report=report,
            error=ExecutionError.model_validate_json(row['error']) if row['error'] else None)

    def latest(self,ctx,payer,record_id,revision):
        self.base.record(ctx,payer,record_id,revision)
        with self.ingestion.db() as db:
            rows=db.execute('SELECT evaluation_id FROM evaluations WHERE tenant_id=? AND taxpayer_id=? AND record_id=? AND revision=? ORDER BY rowid DESC LIMIT 20',
                (ctx.tenant_id,payer,record_id,revision)).fetchall()
        return [self.get(ctx,payer,r['evaluation_id']) for r in rows]

    def prepare(self,ctx,payer,record_id,command):
        head=self.base.record(ctx,payer,record_id)
        if head.revision!=command.expected_record_revision:
            raise ReviewError('REVISION_CONFLICT','Reload the latest record before evaluating.',409,head.revision)
        record,artifact,_=self.review.head_context(ctx,payer,record_id)
        if record.revision!=command.expected_record_revision:
            raise ReviewError('REVISION_CONFLICT','Record changed while preparing evaluation.',409,record.revision)
        started=time.perf_counter()
        quality=self.quality.work(ctx,payer,artifact.artifact_id,revision=record.revision)
        quality_seconds=time.perf_counter()-started
        started=time.perf_counter()
        plan=self.planning.work(ctx,payer,record_id,record.revision)
        planning_seconds=time.perf_counter()-started
        inputs=self.planning.snapshot(ctx,payer,plan.evaluation_id)
        # The planner may select an equivalent assessment that was committed concurrently.
        from ..quality.contracts import QualityAssessment
        pinned_quality=QualityAssessment.model_validate(inputs['quality'])
        if pinned_quality.input_sha256!=quality.input_sha256:raise ValueError('Quality/plan revision mismatch')
        source,_=self.base.source(ctx,payer,record.source_id)
        return dict(plan_id=plan.evaluation_id,record_id=record_id,revision=record.revision,record_sha256=plan.record_sha256,
            assessment_id=pinned_quality.assessment_id,extraction_artifact_id=artifact.artifact_id,source_sha256=source.sha256,
            package=load_package().model_dump(mode='json'),policy=ExecutionPolicy().model_dump(mode='json'),templates=load_templates(),
            implementation_sha256=implementation_sha(),stage_seconds={'quality':quality_seconds,'planning':planning_seconds})

    def work(self,ctx,payer,record_id,command,idempotency_key,*,runner=None):
        ctx.require(ctx.tenant_id,payer,'WRITE');self.base.initialize()
        command=EvaluationCommand.model_validate_json(command.model_dump_json())
        from pydantic import TypeAdapter
        from ..domain.base import Identifier
        TypeAdapter(Identifier).validate_python(idempotency_key)
        request_hash=sha([record_id,command.model_dump(mode='json')])
        def existing():
            with self.ingestion.db() as db:
                return db.execute('SELECT * FROM evaluations WHERE tenant_id=? AND taxpayer_id=? AND idempotency_key=?',
                    (ctx.tenant_id,payer,idempotency_key)).fetchone()
        old=existing()
        if old and old['command_sha256']!=request_hash:raise ReviewError('IDEMPOTENCY_CONFLICT','Key belongs to a different evaluation request.',409)
        if old and old['status']=='COMPLETED':return self.get(ctx,payer,old['evaluation_id'])
        snapshot=json.loads(old['snapshot']) if old else self.prepare(ctx,payer,record_id,command)
        if not old:snapshot['command']=command.model_dump(mode='json')
        if old and digest(old['snapshot'].encode())!=old['snapshot_sha256']:raise ValueError('Snapshot integrity failure')
        if snapshot['implementation_sha256']!=implementation_sha():raise ValueError('Resume requires pinned workflow implementation')
        identifier=old['evaluation_id'] if old else 'evaluation-'+uuid4().hex
        token=uuid4().hex
        raw_snapshot=json.dumps(snapshot,sort_keys=True,ensure_ascii=False,separators=(',',':'))
        with self.ingestion.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM evaluations WHERE tenant_id=? AND taxpayer_id=? AND idempotency_key=?',
                (ctx.tenant_id,payer,idempotency_key)).fetchone()
            if row:
                if row['command_sha256']!=request_hash:raise ReviewError('IDEMPOTENCY_CONFLICT','Key belongs to another request.',409)
                if row['status']=='COMPLETED':return self.get(ctx,payer,row['evaluation_id'])
                if row['status']=='RUNNING' and row['lease_until']>time.time():raise RevisionConflict('Evaluation already running')
                identifier=row['evaluation_id'];snapshot=json.loads(row['snapshot'])
                if digest(row['snapshot'].encode())!=row['snapshot_sha256'] or snapshot['implementation_sha256']!=implementation_sha():
                    raise ValueError('Stored evaluation snapshot/version differs')
                stamp=datetime.fromisoformat(row['created_at'])
                db.execute("UPDATE evaluations SET status='RUNNING',lease_token=?,lease_until=?,error=NULL WHERE tenant_id=? AND taxpayer_id=? AND evaluation_id=?",
                    (token,time.time()+120,ctx.tenant_id,payer,identifier))
            else:
                # A correction during preparation must not silently run against the previous head.
                head=db.execute('SELECT head FROM records WHERE tenant_id=? AND taxpayer_id=? AND record_id=?',(ctx.tenant_id,payer,record_id)).fetchone()[0]
                if head!=command.expected_record_revision:raise ReviewError('REVISION_CONFLICT','Record changed before evaluation was pinned.',409,head)
                stamp=utcnow()
                db.execute('INSERT INTO evaluations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (ctx.tenant_id,payer,identifier,record_id,command.expected_record_revision,idempotency_key,request_hash,'RUNNING','PLANNED',token,
                     time.time()+120,stamp.isoformat(),raw_snapshot,digest(raw_snapshot.encode()),None))
        record=self.base.record(ctx,payer,record_id,snapshot['revision'])
        def advance(stage):
            with self.ingestion.db() as db:
                db.execute('BEGIN IMMEDIATE')
                changed=db.execute('UPDATE evaluations SET stage=?,lease_until=? WHERE tenant_id=? AND taxpayer_id=? AND evaluation_id=? AND lease_token=? AND status=\'RUNNING\'',
                    (stage,time.time()+120,ctx.tenant_id,payer,identifier,token)).rowcount
                if not changed:raise RevisionConflict('Evaluation lease superseded')
        try:
            advance('EXECUTING')
            def heartbeat(model,context,policy):
                advance('EXECUTING')
                return (runner or evaluate_zen)(model,context,policy)
            started=time.perf_counter()
            result=self.execution.work(ctx,payer,snapshot['plan_id'],package=ModelPackage.model_validate(snapshot['package']),
                policy=ExecutionPolicy.model_validate(snapshot['policy']),runner=heartbeat)
            execution_seconds=time.perf_counter()-started
            self.execution.replay(ctx,payer,result.execution_id)
            advance('EXPLAINING')
            plan=self.planning.get(ctx,payer,snapshot['plan_id']);inputs=self.planning.snapshot(ctx,payer,plan.evaluation_id)
            started=time.perf_counter()
            explanation,rows=render(identifier,plan,result,inputs,snapshot['templates'])
            report=EvaluationReport(config_version='compliance-mvp-v1',creator='compliance-workflow',stage='evaluation',created_at=stamp,
                evaluation_id=identifier,tenant_id=ctx.tenant_id,taxpayer_id=payer,record_id=record_id,record_revision=record.revision,
                planning_evaluation_id=plan.evaluation_id,execution_id=result.execution_id,extraction_artifact_id=snapshot['extraction_artifact_id'],
                assessment_id=snapshot['assessment_id'],record_sha256=plan.record_sha256,source_sha256=snapshot['source_sha256'],
                package_sha256=result.package_sha256,template_sha256=sha(snapshot['templates']),implementation_sha256=implementation_sha(),pins=plan.pins,
                aggregate=result.aggregate,explanation=explanation,rule_results_total=len(rows),attempts_total=len(result.attempts),
                stage_seconds={**snapshot['stage_seconds'],'execution':execution_seconds,'template':time.perf_counter()-started})
            artifact=EvaluationArtifact(report=report,rule_results=rows);raw=artifact.model_dump_json()
            with self.ingestion.db() as db:
                db.execute('BEGIN IMMEDIATE')
                current=db.execute('SELECT lease_token,status FROM evaluations WHERE tenant_id=? AND taxpayer_id=? AND evaluation_id=?',(ctx.tenant_id,payer,identifier)).fetchone()
                if current['lease_token']!=token or current['status']!='RUNNING':raise RevisionConflict('Evaluation lease superseded')
                db.execute('INSERT INTO evaluation_reports VALUES(?,?,?,?,?)',(ctx.tenant_id,payer,identifier,raw,digest(raw.encode())))
                self.base._audit(db,ctx,ctx.tenant_id,payer,'ARTIFACT_STORED',digest(raw.encode()),record,reason='Compliance evaluation/template stored')
                db.execute("UPDATE evaluations SET status='COMPLETED',stage='COMPLETE',lease_until=0 WHERE tenant_id=? AND taxpayer_id=? AND evaluation_id=?",
                    (ctx.tenant_id,payer,identifier))
        except BaseException as exc:
            error=ExecutionError(code='EVALUATION_INTERRUPTED' if isinstance(exc,KeyboardInterrupt) else 'EVALUATION_STAGE_ERROR',
                message='Evaluation did not complete; preserved stage artifacts may be resumed.',retryable=True,next_action='RETRY')
            with self.ingestion.db() as db:
                db.execute("UPDATE evaluations SET status='FAILED',error=?,lease_until=0 WHERE tenant_id=? AND taxpayer_id=? AND evaluation_id=? AND lease_token=? AND status='RUNNING'",
                    (error.model_dump_json(),ctx.tenant_id,payer,identifier,token))
            raise
        return self.get(ctx,payer,identifier)

    def resume(self,ctx,payer,identifier,*,runner=None):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        row=self.row(ctx,payer,identifier)
        snapshot=json.loads(row['snapshot'])
        return self.work(ctx,payer,row['record_id'],EvaluationCommand.model_validate(snapshot['command']),row['idempotency_key'],runner=runner)

    def page(self,ctx,payer,identifier,kind,cursor=None,limit=25):
        if not 1<=limit<=100:raise ReviewError('PAGE_LIMIT','Page size must be 1 to 100.')
        artifact=self.artifact(ctx,payer,identifier)
        if kind=='rules':items=[r.model_dump(mode='json',exclude={'trace'}) for r in artifact.rule_results]
        elif kind=='attempts':
            result=self.execution.get(ctx,payer,artifact.report.execution_id)
            items=[dict(evaluation_id=identifier,planning_evaluation_id=a.key.evaluation_id,attempt_id=a.attempt_id,
                rule_id=a.key.rule_id,rule_version=a.key.rule_version,unit_type=a.key.unit_type,unit_id=a.key.unit_id,
                attempt_number=a.attempt_number,execution_status=a.execution_status,result=a.result,error=a.error.model_dump(mode='json') if a.error else None) for a in result.attempts]
            items.sort(key=lambda a:(a['rule_id'],a['rule_version'],a['unit_type'],a['unit_id'],a['attempt_number']))
        else:raise ValueError('Unknown evaluation page')
        snapshot_hash=sha(items);offset=0
        binding=dict(tenant=ctx.tenant_id,payer=payer,evaluation=identifier,kind=kind,limit=limit,snapshot=snapshot_hash)
        if cursor:
            body=self.review.unsign(cursor)
            if not isinstance(body,dict) or {k:v for k,v in body.items() if k!='offset'}!=binding or type(body.get('offset')) is not int:
                raise ReviewError('INVALID_CURSOR','Cursor does not belong to this immutable page.',400)
            offset=body['offset']
            if not 0<=offset<=len(items):raise ReviewError('INVALID_CURSOR','Invalid page position.',400)
        next_offset=offset+limit
        token=self.review.sign({**binding,'offset':next_offset}) if next_offset<len(items) else None
        return dict(evaluation_id=identifier,record_revision=artifact.report.record_revision,total=len(items),items=items[offset:next_offset],
            next_cursor=token,snapshot_sha256=snapshot_hash)

    def replay(self,ctx,payer,identifier):
        artifact=self.artifact(ctx,payer,identifier)
        snapshot=json.loads(self.row(ctx,payer,identifier)['snapshot'])
        if artifact.report.implementation_sha256!=implementation_sha() or artifact.report.template_sha256!=sha(snapshot['templates']):
            raise ValueError('Replay requires pinned workflow/template implementation')
        result=self.execution.replay(ctx,payer,artifact.report.execution_id)
        plan=self.planning.get(ctx,payer,artifact.report.planning_evaluation_id)
        explanation,rows=render(identifier,plan,result,self.planning.snapshot(ctx,payer,plan.evaluation_id),snapshot['templates'])
        if explanation!=artifact.report.explanation or rows!=artifact.rule_results or result.aggregate!=artifact.report.aggregate:
            raise ValueError('Evaluation/template replay differs')
        return dict(evaluation_id=identifier,verified=True,record_revision=artifact.report.record_revision,engine_reexecuted=False)
