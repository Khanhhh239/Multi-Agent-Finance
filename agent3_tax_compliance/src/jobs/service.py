import json
import time
from uuid import uuid4
from ..canonicalization.derive import sha
from ..ingestion.service import IngestionService
from ..adapters.ocr.bridge import OCRBridge,config_key
from ..review.repository import ReviewRepository,envelope,raw_json
from ..review.contracts import ReviewError
from .state import validate_transition

class CaptureJobs(ReviewRepository):
    def get(self,ctx,payer,job_id):
        ctx.require(ctx.tenant_id,payer)
        with self.ingestion.db() as db: row=self.row(db,ctx,payer,job_id)
        return envelope(job_id=job_id,ingestion_id=row['ingestion_id'],state=row['state'],attempts=row['attempts'],
            max_attempts=self.settings.max_attempts,**json.loads(row['payload']))

    @staticmethod
    def row(db,ctx,payer,job_id):
        row=db.execute('SELECT * FROM capture_jobs WHERE tenant_id=? AND taxpayer_id=? AND job_id=?',(ctx.tenant_id,payer,job_id)).fetchone()
        if not row: raise KeyError('capture job not found')
        return row

    def enqueue(self,ctx,payer,ingestion_id):
        ctx.require(ctx.tenant_id,payer,'WRITE');source=self.ingestion.get(ctx,payer,ingestion_id)
        job_id='capture-'+uuid4().hex
        with self.ingestion.db() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT job_id FROM capture_jobs WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=?',
                (ctx.tenant_id,payer,ingestion_id)).fetchone()
            if old: job_id=old['job_id']
            else:
                db.execute('INSERT INTO capture_jobs VALUES(?,?,?,?,?,?,?,?,?)',
                    (ctx.tenant_id,payer,job_id,ingestion_id,'QUEUED',0,None,None,raw_json({'schema_version':'1.0.0','config_version':'capture-job-v1',
                     'creator':'capture-job-service','stage':'capture','created_at':source.created_at.isoformat(),'input_sha256':source.input_sha256})))
                self.ingestion._event(db,ctx,payer,ingestion_id,'CAPTURE_QUEUED',sha([job_id,ingestion_id]),{'job_id':job_id})
        return self.get(ctx,payer,job_id)

    def transition(self,ctx,payer,job_id,state,*,token=None,updates=None):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        with self.ingestion.db() as db:
            db.execute('BEGIN IMMEDIATE');row=self.row(db,ctx,payer,job_id)
            if token and (row['lease_token']!=token or row['lease_until']<time.time()):
                raise ReviewError('STALE_WORKER','Worker lease is no longer valid.',409)
            if not token and row['lease_token']: raise ReviewError('JOB_BUSY','Capture job has an active worker.',409)
            validate_transition(row['state'],state);payload=json.loads(row['payload']);payload.update(updates or {})
            terminal=state in ('REVIEW','COMPLETED','PROCESSING_ERROR','WAITING_DATA','OPERATOR')
            db.execute('UPDATE capture_jobs SET state=?,payload=?,lease_token=?,lease_until=? WHERE tenant_id=? AND taxpayer_id=? AND job_id=?',
                (state,raw_json(payload),None if terminal else token,None if terminal else row['lease_until'],ctx.tenant_id,payer,job_id))
            self.ingestion._event(db,ctx,payer,row['ingestion_id'],'CAPTURE_STATE_CHANGED',sha([job_id,state,row['attempts']]),
                {'job_id':job_id,'before':row['state'],'after':state,'attempt':row['attempts']})
        return self.get(ctx,payer,job_id)

    def recover(self,ctx,payer,job_id,action,reason):
        if not reason.strip(): raise ReviewError('REASON_REQUIRED','Recovery requires a reason.')
        job=self.get(ctx,payer,job_id)
        if job['state'] not in ('PROCESSING_ERROR','REVIEW'): raise ReviewError('INVALID_RECOVERY','This job cannot be recovered.',409)
        if action=='RETRY':
            if job['state']!='PROCESSING_ERROR': raise ReviewError('INVALID_RECOVERY','Only processing errors can be retried.',409)
            if job['attempts']>=self.settings.max_attempts:
                return self.transition(ctx,payer,job_id,'OPERATOR',updates={'recovery_reason':reason})
            if not job.get('retryable',True): raise ReviewError('NOT_RETRYABLE','Request new source data or operator assistance.',409)
            return self.transition(ctx,payer,job_id,'QUEUED',updates={'recovery_reason':reason})
        if action not in ('REQUEST_DATA','OPERATOR'): raise ReviewError('INVALID_RECOVERY','Invalid recovery action.')
        return self.transition(ctx,payer,job_id,{'REQUEST_DATA':'WAITING_DATA','OPERATOR':'OPERATOR'}[action],updates={'recovery_reason':reason})

    def claim(self,ctx,payer,job_id,lease_seconds):
        ctx.require(ctx.tenant_id,payer,'WRITE');token=uuid4().hex
        with self.ingestion.db() as db:
            db.execute('BEGIN IMMEDIATE');row=self.row(db,ctx,payer,job_id)
            if row['lease_token'] and row['lease_until']<time.time():
                # Fenced recovery, no silent success after worker death.
                db.execute("UPDATE capture_jobs SET state='PROCESSING_ERROR',lease_token=NULL,lease_until=NULL WHERE tenant_id=? AND taxpayer_id=? AND job_id=?",(ctx.tenant_id,payer,job_id))
                self.ingestion._event(db,ctx,payer,row['ingestion_id'],'CAPTURE_LEASE_EXPIRED',sha([job_id,row['attempts']]),{'job_id':job_id,'attempt':row['attempts']})
                return None
            if row['state']!='QUEUED' or row['lease_token']: return None
            if row['attempts']>=self.settings.max_attempts:
                db.execute("UPDATE capture_jobs SET state='OPERATOR' WHERE tenant_id=? AND taxpayer_id=? AND job_id=?",(ctx.tenant_id,payer,job_id));return None
            validate_transition(row['state'],'PREPARING')
            db.execute("UPDATE capture_jobs SET state='PREPARING',attempts=attempts+1,lease_token=?,lease_until=? WHERE tenant_id=? AND taxpayer_id=? AND job_id=?",
                (token,time.time()+lease_seconds,ctx.tenant_id,payer,job_id))
            self.ingestion._event(db,ctx,payer,row['ingestion_id'],'CAPTURE_CLAIMED',sha([job_id,row['attempts']+1]),{'job_id':job_id,'attempt':row['attempts']+1})
        return token

    def work_one(self,ctx,payer,job_id,bridge=None,profile=None):
        bridge=bridge or OCRBridge(self.settings)
        lease=self.settings.worker_timeout_seconds+self.settings.max_pages*bridge.config.timeout_seconds*bridge.config.max_attempts+120
        token=self.claim(ctx,payer,job_id,lease)
        if token is None: return self.get(ctx,payer,job_id)
        job=self.get(ctx,payer,job_id);identifier=job['ingestion_id']
        try:
            reader=IngestionService(self.settings);ing=self.ingestion.get(ctx,payer,identifier)
            if ing.status=='FAILED': self.ingestion.retry(ctx,payer,identifier)
            ing=reader.work_one(ctx,payer,identifier)
            if ing.status!='SUCCEEDED':
                error=ReviewError(ing.issue.code if ing.issue else 'SOURCE_PROCESSING_FAILED','Source processing did not succeed.',409)
                error.retryable=bool(ing.issue and ing.issue.retryable)
                raise error
            self.transition(ctx,payer,job_id,'EXTRACTING',token=token)
            # Failed OCR attempts are immutable; retry uses a new version/key, retaining history.
            if job['attempts']>1:
                bridge=OCRBridge(self.settings,bridge.config.model_copy(update={'version':bridge.config.version+'-retry-'+job_id[-8:]+'-'+str(job['attempts'])}),bridge.client)
            result=bridge.work_one(ctx,payer,identifier)
            if not result.get('result') or result['result'].status=='FAILED': raise ReviewError('OCR_FAILED','OCR failed; inspect worker/model or request a clearer source.',409)
            key=config_key(bridge.config,bridge.client.inventory()['runtime_sha256'])
            artifact=self.extraction.work(ctx,payer,identifier,key,profile)
            self.transition(ctx,payer,job_id,'ASSESSING',token=token,updates={'extraction_artifact_id':artifact.artifact_id})
            quality=self.quality.work(ctx,payer,artifact.artifact_id)
            if artifact.record: self.ensure_tasks(ctx,payer,artifact.record.record_id)
            return self.transition(ctx,payer,job_id,'REVIEW',token=token,updates={
                'record_id':artifact.record.record_id if artifact.record else None,'assessment_id':quality.assessment_id,
                'review_split':artifact.record is None,'retryable':False,'error_code':None})
        except KeyboardInterrupt:
            self.transition(ctx,payer,job_id,'PROCESSING_ERROR',token=token,updates={
                'error_code':'WORKER_INTERRUPTED','retryable':True,'recovery_actions':['RETRY','REQUEST_DATA','OPERATOR']})
            raise
        except Exception as error:
            # No exception text/full tax IDs/model payloads are persisted in operational logs.
            code=error.code if isinstance(error,ReviewError) else 'PROCESSING_ERROR'
            retryable=getattr(error,'retryable',not isinstance(error,(ValueError,PermissionError)))
            try:
                failed=self.transition(ctx,payer,job_id,'PROCESSING_ERROR',token=token,updates={
                    'error_code':code,'retryable':retryable,'recovery_actions':(['RETRY'] if retryable else [])+['REQUEST_DATA','OPERATOR']})
                if failed['attempts']>=self.settings.max_attempts:
                    return self.transition(ctx,payer,job_id,'OPERATOR',updates={'retryable':False,'recovery_actions':['OPERATOR']})
                return failed
            except ReviewError as stale:
                if stale.code=='STALE_WORKER': return self.get(ctx,payer,job_id)
                raise

