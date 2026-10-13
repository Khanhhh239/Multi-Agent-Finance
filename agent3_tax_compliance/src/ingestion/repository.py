from contextlib import contextmanager
import hashlib
import json
import sqlite3
import time
from uuid import uuid4

from ..domain.base import utcnow
from ..domain.envelope import SourceEnvelope
from ..domain.storage import Job
from ..persistence.repository import Repository, digest
from .models import DocumentArtifact, IngestionError, IngestionIssue, IngestionView

STAMP=dict(config_version='ingestion-v1',creator='ingestion-repository',stage='ingestion')


class IngestionRepository:
    def __init__(self,settings):
        self.settings=settings; self.base=Repository(settings)

    @contextmanager
    def db(self):
        with self.base.connection() as db:
            db.row_factory=sqlite3.Row
            yield db

    def _event(self,db,ctx,payer,ingestion_id,kind,sha,details=None):
        event_id='event-'+uuid4().hex
        payload=dict(schema_version='1.0.0',**STAMP,created_at=utcnow().isoformat(),
                     event_id=event_id,tenant_id=ctx.tenant_id,taxpayer_id=payer,actor_id=ctx.actor_id,
                     ingestion_id=ingestion_id,event_type=kind,input_sha256=sha,details=details or {})
        db.execute('INSERT INTO ingestion_events VALUES(?,?,?,?,?)',
                   (ctx.tenant_id,payer,event_id,ingestion_id,json.dumps(payload)))

    @staticmethod
    def _row(db,ctx,payer,identifier):
        row=db.execute('SELECT i.*,s.sha256 FROM ingestions i JOIN sources s '
                       'ON i.tenant_id=s.tenant_id AND i.taxpayer_id=s.taxpayer_id AND i.source_id=s.source_id '
                       'WHERE i.tenant_id=? AND i.taxpayer_id=? AND i.ingestion_id=?',
                       (ctx.tenant_id,payer,identifier)).fetchone()
        if row is None:
            raise IngestionError('NOT_FOUND','Ingestion not found.',status=404,next_action='Check the ingestion ID and taxpayer scope.')
        return row

    def get(self,ctx,payer,identifier):
        ctx.require(ctx.tenant_id,payer)
        with self.db() as db:
            row=self._row(db,ctx,payer,identifier)
            outbox=db.execute('SELECT status FROM extraction_outbox WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=?',
                              (ctx.tenant_id,payer,identifier)).fetchone()
        return IngestionView(**STAMP,created_at=row['created_at'],ingestion_id=identifier,source_id=row['source_id'],
            document_id=row['document_id'],input_sha256=row['sha256'],status=row['status'],attempts=row['attempts'],
            issue=IngestionIssue.model_validate_json(row['issue']) if row['issue'] else None,
            extraction_status='QUEUED' if outbox else 'NOT_QUEUED')

    def accept(self,ctx,payer,key,fingerprint,envelope,raw,ingestion_id,document_id):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        envelope=SourceEnvelope.model_validate_json(envelope.model_dump_json())
        if (envelope.tenant_id,envelope.taxpayer_id)!=(ctx.tenant_id,payer):
            raise PermissionError('access denied')
        if len(raw)!=envelope.size_bytes or len(raw)>self.settings.max_upload_bytes or digest(raw)!=envelope.sha256:
            raise IngestionError('PROCESSING_ERROR','Staged raw size/hash mismatch.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT ingestion_id,fingerprint FROM ingestions WHERE tenant_id=? AND taxpayer_id=? AND idempotency_key=?',
                                (ctx.tenant_id,payer,key)).fetchone()
            if existing:
                if existing['fingerprint']!=fingerprint:
                    raise IngestionError('IDEMPOTENCY_CONFLICT','Key was already used for different content, master revision or processing configuration.',status=409)
                ingestion_id=existing['ingestion_id']
            else:
                count=db.execute("SELECT COUNT(*) FROM ingestions WHERE status IN ('STORED','QUEUED','PROCESSING')").fetchone()[0]
                if count>=self.settings.max_pending_ingestions:
                    raise IngestionError('LIMIT_EXCEEDED','Pending ingestion capacity reached.',retryable=True,status=429,
                                         next_action='Drain the worker queue before retrying the upload.')
                db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?)',
                           (ctx.tenant_id,payer,envelope.source_id,envelope.taxpayer_master_revision,envelope.sha256,raw,envelope.model_dump_json()))
                self.base._audit(db,ctx,ctx.tenant_id,payer,'SOURCE_STORED',envelope.sha256)
                db.execute('INSERT INTO ingestions(tenant_id,taxpayer_id,ingestion_id,idempotency_key,fingerprint,source_id,document_id,status,created_at) '
                           "VALUES(?,?,?,?,?,?,?,'STORED',?)",(ctx.tenant_id,payer,ingestion_id,key,fingerprint,envelope.source_id,document_id,utcnow().isoformat()))
                self._event(db,ctx,payer,ingestion_id,'RAW_STORED',envelope.sha256)
        return self.get(ctx,payer,ingestion_id)

    def enqueue(self,ctx,payer,identifier):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE'); row=self._row(db,ctx,payer,identifier)
            if row['status']=='STORED':
                job=Job(**STAMP,job_id='job-'+identifier,tenant_id=ctx.tenant_id,taxpayer_id=payer,
                        source_id=row['source_id'],input_sha256=row['sha256'])
                db.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',(ctx.tenant_id,payer,job.job_id,row['source_id'],job.model_dump_json()))
                self.base._audit(db,ctx,ctx.tenant_id,payer,'JOB_CREATED',row['sha256'])
                db.execute("UPDATE ingestions SET status='QUEUED' WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=?",(ctx.tenant_id,payer,identifier))
                self._event(db,ctx,payer,identifier,'ENQUEUED',row['sha256'])
        return self.get(ctx,payer,identifier)

    def recover_stored(self,ctx,payer):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        with self.db() as db:
            rows=db.execute("SELECT ingestion_id FROM ingestions WHERE tenant_id=? AND taxpayer_id=? AND status='STORED'",
                            (ctx.tenant_id,payer)).fetchall()
        for row in rows: self.enqueue(ctx,payer,row[0])
        return len(rows)

    def pending(self,ctx,payer):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        with self.db() as db:
            rows=db.execute("SELECT ingestion_id FROM ingestions WHERE tenant_id=? AND taxpayer_id=? AND "
                            "(status='QUEUED' OR (status='PROCESSING' AND lease_until<?)) ORDER BY created_at",
                            (ctx.tenant_id,payer,time.time())).fetchall()
        return [r[0] for r in rows]

    def claim(self,ctx,payer,identifier):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        token=uuid4().hex
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE'); row=self._row(db,ctx,payer,identifier)
            expired=row['status']=='PROCESSING' and row['lease_until']<time.time()
            if row['status']!='QUEUED' and not expired:
                return None
            if row['attempts']>=self.settings.max_attempts:
                issue=IngestionIssue(code='RETRY_NOT_ALLOWED',retryable=False,message='Attempt limit exhausted.',next_action='Inspect the document or environment before a new submission.')
                db.execute("UPDATE ingestions SET status='FAILED',issue=?,lease_until=NULL,lease_token=NULL WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=?",
                           (issue.model_dump_json(),ctx.tenant_id,payer,identifier))
                self._event(db,ctx,payer,identifier,'ATTEMPTS_EXHAUSTED',row['sha256'])
                return None
            db.execute("UPDATE ingestions SET status='PROCESSING',attempts=attempts+1,lease_token=?,lease_until=?,issue=NULL WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=?",
                       (token,time.time()+self.settings.worker_timeout_seconds+15,ctx.tenant_id,payer,identifier))
            self._event(db,ctx,payer,identifier,'CLAIMED',row['sha256'],{'lease_token':token,'recovered_expired_lease':expired})
        return token

    def retry(self,ctx,payer,identifier):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE'); row=self._row(db,ctx,payer,identifier)
            issue=IngestionIssue.model_validate_json(row['issue']) if row['issue'] else None
            if row['status']!='FAILED' or not issue or not issue.retryable or row['attempts']>=self.settings.max_attempts:
                raise IngestionError('RETRY_NOT_ALLOWED','Ingestion is not eligible for another attempt.',status=409,
                                     next_action='Inspect the saved issue; submit corrected content with a new key if necessary.')
            db.execute("UPDATE ingestions SET status='QUEUED',lease_token=NULL,lease_until=NULL WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=?",(ctx.tenant_id,payer,identifier))
            self._event(db,ctx,payer,identifier,'RETRY_QUEUED',row['sha256'])
        return self.get(ctx,payer,identifier)

    def fail(self,ctx,payer,identifier,token,issue):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE'); row=self._row(db,ctx,payer,identifier)
            if row['status']!='PROCESSING' or row['lease_token']!=token:
                return False
            if row['attempts']>=self.settings.max_attempts and issue.retryable:
                issue=issue.model_copy(update={'retryable':False,'next_action':'Attempt limit exhausted; inspect before a new submission.'})
            db.execute("UPDATE ingestions SET status='FAILED',issue=?,lease_token=NULL,lease_until=NULL WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=?",
                       (issue.model_dump_json(),ctx.tenant_id,payer,identifier))
            self._event(db,ctx,payer,identifier,'READ_FAILED',row['sha256'],issue.model_dump(mode='json'))
        return True

    def complete(self,ctx,payer,identifier,token,document,renders):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        document=DocumentArtifact.model_validate_json(document.model_dump_json())
        if (document.tenant_id,document.taxpayer_id,document.ingestion_id)!=(ctx.tenant_id,payer,identifier):
            raise ValueError('document ownership mismatch')
        if len(renders)!=len(document.pages) or sum(map(len,renders))>self.settings.max_artifact_bytes:
            raise ValueError('render count/byte budget mismatch')
        for page,png in zip(document.pages,renders):
            if digest(png)!=page.render_sha256: raise ValueError('render hash mismatch')
        payload=document.model_dump_json(); sha=digest(payload.encode())
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE'); row=self._row(db,ctx,payer,identifier)
            if row['status']!='PROCESSING' or row['lease_token']!=token:
                return False
            envelope=db.execute('SELECT envelope FROM sources WHERE tenant_id=? AND taxpayer_id=? AND source_id=?',
                                (ctx.tenant_id,payer,row['source_id'])).fetchone()[0]
            master=SourceEnvelope.model_validate_json(envelope)
            if (document.source_id,document.document_id,document.input_sha256,document.taxpayer_master_revision)!=(
                    row['source_id'],row['document_id'],row['sha256'],master.taxpayer_master_revision):
                raise ValueError('document/source binding mismatch')
            db.execute('INSERT INTO documents VALUES(?,?,?,?,?)',(ctx.tenant_id,payer,identifier,payload,sha))
            for page,png in zip(document.pages,renders):
                db.execute('INSERT INTO page_renders VALUES(?,?,?,?,?,?)',
                           (ctx.tenant_id,payer,identifier,page.page_index,png,page.render_sha256))
            db.execute('INSERT INTO extraction_outbox VALUES(?,?,?,?,?)',(ctx.tenant_id,payer,identifier,sha,'QUEUED'))
            db.execute("UPDATE ingestions SET status='SUCCEEDED',lease_token=NULL,lease_until=NULL,issue=NULL WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=?",
                       (ctx.tenant_id,payer,identifier))
            self._event(db,ctx,payer,identifier,'DOCUMENT_AND_EXTRACTION_COMMITTED',row['sha256'],{'document_sha256':sha})
        return True

    def document(self,ctx,payer,identifier):
        ctx.require(ctx.tenant_id,payer)
        with self.db() as db:
            row=db.execute('SELECT payload,sha256 FROM documents WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=?',
                           (ctx.tenant_id,payer,identifier)).fetchone()
        if not row: raise IngestionError('NOT_FOUND','Document artifact is not available.',status=404)
        if digest(row[0].encode())!=row[1]: raise ValueError('document integrity failure')
        return DocumentArtifact.model_validate_json(row[0])

    def render(self,ctx,payer,identifier,index):
        ctx.require(ctx.tenant_id,payer)
        with self.db() as db:
            row=db.execute('SELECT png,sha256 FROM page_renders WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=? AND page_index=?',
                           (ctx.tenant_id,payer,identifier,index)).fetchone()
        if not row: raise IngestionError('NOT_FOUND','Page render is not available.',status=404)
        if digest(row[0])!=row[1]: raise ValueError('render integrity failure')
        return row[0]
