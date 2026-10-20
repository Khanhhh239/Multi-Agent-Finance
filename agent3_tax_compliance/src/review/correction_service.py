from datetime import datetime,timezone
from uuid import uuid4
from ..canonicalization.derive import sha
from ..domain.cfr import CanonicalFinancialRecord
from ..persistence.repository import digest
from ..quality.assessor import assess
from ..quality.contracts import CalibrationScope
from ..quality.repository import implementation_sha,verified_events
from ..quality.policy import load_policy
from ..quality.completeness import flatten
from .repository import ReviewRepository,envelope,raw_json
from .revision_reprocessor import apply
from .contracts import ReviewError,CorrectionCommand,CorrectionEvent

class CorrectionService(ReviewRepository):
    def correct(self,ctx,payer,command,key):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        command=CorrectionCommand.model_validate_json(command.model_dump_json())
        command_sha=sha([ctx.actor_id,command.model_dump(mode='json')]);scope=(ctx.tenant_id,payer,command.record_id)
        # Read pinned immutable inputs before acquiring the write lock; head is checked again inside it.
        record,artifact,previous_q=self.head_context(ctx,payer,command.record_id)
        master=self.base.taxpayer(ctx,payer,record.taxpayer_master_revision)
        doc=self.ingestion.document(ctx,payer,artifact.ingestion_id)
        previous_inputs=self.quality.inputs(ctx,payer,previous_q.assessment_id)
        now=datetime.now(timezone.utc);event_id='review-'+uuid4().hex
        with self.ingestion.db() as db:
            db.execute('BEGIN IMMEDIATE')
            prior=db.execute('SELECT * FROM review_events WHERE tenant_id=? AND taxpayer_id=? AND record_id=? AND idempotency_key=?',(*scope,key)).fetchone()
            if prior:
                if prior['command_sha256']!=command_sha: raise ReviewError('IDEMPOTENCY_CONFLICT','Key already used for a different correction.',409)
                event=self.checked_event(prior)
                return envelope(event_id=event['event_id'],record_revision=event['after_revision'],assessment_id=event['assessment_id'],replayed=True)
            head=db.execute('SELECT head FROM records WHERE tenant_id=? AND taxpayer_id=? AND record_id=?',scope).fetchone()[0]
            if head!=command.expected_revision or record.revision!=head:
                raise ReviewError('REVISION_CONFLICT','Another reviewer changed this record. Reload before editing.',409,head)
            task=db.execute('SELECT * FROM review_tasks WHERE tenant_id=? AND taxpayer_id=? AND task_id=?',(ctx.tenant_id,payer,command.task_id)).fetchone()
            if not task or task['record_id']!=command.record_id: raise ReviewError('TASK_OWNERSHIP','Task does not belong to this record.',404)
            if task['revision']!=head or task['status'] not in ('OPEN','WAITING_DATA','OPERATOR'):
                raise ReviewError('STALE_TASK','Task belongs to an older revision or is already resolved.',409,head)
            for op in command.item_operations:
                if op.operation!='ADD':continue
                history=db.execute('SELECT payload,sha256 FROM review_events WHERE tenant_id=? AND taxpayer_id=? AND record_id=?',scope).fetchall()
                if any(any(c['field_path']=='items' and any(i['item_id']==op.item_id for side in ('before','after') for i in (c[side] or {}).get('rows',[]))
                           for c in self.checked_event(row)['changes']) for row in history):
                    raise ReviewError('ITEM_ID_CONFLICT','Mã dòng đã dùng trong lịch sử; hãy tạo dòng mới.')
            updated,changes,manifest,affected=apply(record,artifact,master,command,event_id,[p.page_index for p in doc.pages],now)
            # Store fully validated canonical field payloads, including Decimal/date normalization.
            fields=flatten(updated)
            for change in changes:
                if change['field_path'] not in ('item_discovery_status','items'): change['after']=fields[change['field_path']].model_dump(mode='json')
            proofs=verified_events(db,updated)+(event_id,)
            policy=load_policy();scope_model=CalibrationScope.model_validate(previous_inputs['scope'])
            q=assess(artifact,updated,policy,scope_model,assessment_id='quality-'+uuid4().hex,created_at=now,
                implementation_sha256=implementation_sha(),verified_review_events=proofs)
            inputs={'artifact':artifact.model_dump(mode='json'),'record':updated.model_dump(mode='json'),
                'policy':policy.model_dump(mode='json'),'scope':scope_model.model_dump(mode='json'),'calibrations':[],
                'implementation_sha256':implementation_sha(),'verified_review_events':list(proofs)}
            event=dict(schema_version='1.0.0',config_version='review-v1',creator='correction-service',stage='review',created_at=now.isoformat(),
                event_id=event_id,tenant_id=ctx.tenant_id,taxpayer_id=payer,record_id=command.record_id,actor_id=ctx.actor_id,
                task_id=command.task_id,reason=command.reason,before_revision=record.revision,after_revision=updated.revision,
                before_sha256=sha(record.model_dump(mode='json')),after_sha256=sha(updated.model_dump(mode='json')),
                changes=changes,record_stamp={k:updated.model_dump(mode='json')[k] for k in ('revision','creator','stage','config_version','created_at')},
                derivation=manifest.model_dump(mode='json'),affected_nodes=list(affected),assessment_id=q.assessment_id,
                completeness_proof={'page_indices':list(command.verified_pages),'item_count':command.expected_item_count} if command.confirm_items_complete else None)
            self.base._insert_revision(db,updated)
            db.execute('UPDATE records SET head=? WHERE tenant_id=? AND taxpayer_id=? AND record_id=? AND head=?',
                (updated.revision,*scope,head))
            event=CorrectionEvent.model_validate(event).model_dump(mode='json')
            payload=raw_json(event)
            db.execute('INSERT INTO review_events VALUES(?,?,?,?,?,?,?,?)',(*scope,event_id,key,command_sha,payload,digest(payload.encode())))
            self.base._audit(db,ctx,ctx.tenant_id,payer,'RECORD_REVISED',event['after_sha256'],updated,command.reason)
            qraw=q.model_dump_json();iraw=raw_json(inputs)
            db.execute('INSERT INTO quality_assessments VALUES(?,?,?,?,?,?,?,?,?)',
                (ctx.tenant_id,payer,artifact.artifact_id,sha(inputs),q.assessment_id,qraw,digest(qraw.encode()),iraw,digest(iraw.encode())))
            old=db.execute('SELECT * FROM review_tasks WHERE tenant_id=? AND taxpayer_id=? AND record_id=? AND revision=?',(*scope,head)).fetchall()
            db.execute("UPDATE review_tasks SET status='SUPERSEDED' WHERE tenant_id=? AND taxpayer_id=? AND record_id=? AND revision=? AND status IN ('OPEN','WAITING_DATA','OPERATOR')",(*scope,head))
            # Resolution reflects the new assessment, rather than assuming that any edit fixes the submitted issue.
            remains=any(r.reason==task['reason'] and (r.field_path or '')==task['field_path'] for r in q.recommendations)
            if not remains: db.execute("UPDATE review_tasks SET status='RESOLVED' WHERE tenant_id=? AND taxpayer_id=? AND task_id=?",(ctx.tenant_id,payer,command.task_id))
            self.build_tasks(db,ctx,payer,q,old)
            self.ingestion._event(db,ctx,payer,artifact.ingestion_id,'REVIEW_CORRECTED',q.input_sha256,
                {'event_id':event_id,'record_revision':updated.revision,'assessment_id':q.assessment_id,'field_paths':[c['field_path'] for c in changes]})
        return envelope(event_id=event_id,record_revision=updated.revision,assessment_id=q.assessment_id,replayed=False)
