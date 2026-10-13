import time
import json
from uuid import uuid4
from ...ingestion.repository import IngestionRepository
from ...persistence.repository import digest
from .protocol import NormalizedPageExtraction, NormalizedDocumentExtraction, OCRError


class OCRRepository:
    def __init__(self, settings):
        self.ingestion=IngestionRepository(settings)

    def claim(self,ctx,payer,identifier,key,lease_seconds,max_attempts):
        ctx.require(ctx.tenant_id,payer)
        ctx.require(ctx.tenant_id,payer,'WRITE')
        with self.ingestion.db() as db:
            db.execute('BEGIN IMMEDIATE')
            outbox=db.execute('SELECT * FROM extraction_outbox WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=?',
                             (ctx.tenant_id,payer,identifier)).fetchone()
            if outbox is None: raise OCRError('BAD_INPUT','Document is not ready for extraction')
            db.execute("INSERT OR IGNORE INTO ocr_jobs(tenant_id,taxpayer_id,ingestion_id,config_key,status) VALUES(?,?,?,?,'QUEUED')",
                       (ctx.tenant_id,payer,identifier,key))
            row=db.execute('SELECT * FROM ocr_jobs WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=? AND config_key=?',
                           (ctx.tenant_id,payer,identifier,key)).fetchone()
            if row['payload']: return None
            if row['status']=='FAILED' or row['attempts']>=max_attempts:
                if row['status']!='FAILED':
                    db.execute("UPDATE ocr_jobs SET status='FAILED',lease_token=NULL,lease_until=NULL,issue='ATTEMPT_LIMIT' WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=? AND config_key=?",
                               (ctx.tenant_id,payer,identifier,key))
                return None
            if row['lease_until'] and row['lease_until']>time.time(): return None
            # Cross-process concurrency is enforced in the same write transaction
            # as claim, including separate CLI processes and tenant scopes.
            active=db.execute("SELECT COUNT(*) FROM ocr_jobs WHERE status='PROCESSING' AND lease_until>?",(time.time(),)).fetchone()[0]
            if active: return None
            token=uuid4().hex
            db.execute("UPDATE ocr_jobs SET status='PROCESSING',attempts=attempts+1,lease_token=?,lease_until=? WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=? AND config_key=?",
                       (token,time.time()+lease_seconds,ctx.tenant_id,payer,identifier,key))
            self.ingestion._event(db,ctx,payer,identifier,'OCR_CLAIMED',outbox['document_sha256'],{'config_key':key})
            return token

    def cached(self,ctx,payer,key):
        ctx.require(ctx.tenant_id,payer)
        with self.ingestion.db() as db:
            row=db.execute('SELECT payload,sha256 FROM ocr_page_cache WHERE tenant_id=? AND taxpayer_id=? AND cache_key=?',
                           (ctx.tenant_id,payer,key)).fetchone()
        if not row: return None
        if digest(row['payload'].encode())!=row['sha256']: raise OCRError('BAD_INPUT','OCR cache integrity failure')
        return NormalizedPageExtraction.model_validate_json(row['payload'])

    def cache(self,ctx,payer,key,page):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        if page.status!='COMPLETE': return
        raw=page.model_dump_json()
        with self.ingestion.db() as db:
            db.execute('INSERT OR IGNORE INTO ocr_page_cache VALUES(?,?,?,?,?)',
                       (ctx.tenant_id,payer,key,raw,digest(raw.encode())))

    def finish(self,ctx,payer,identifier,key,token,result=None,issue=None):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        raw=result.model_dump_json() if result else None
        if result and (result.tenant_id,result.taxpayer_id,result.ingestion_id)!=(ctx.tenant_id,payer,identifier):
            raise PermissionError('result ownership mismatch')
        if result:
            from .bridge import config_key
            result=NormalizedDocumentExtraction.model_validate_json(raw)
            doc=self.ingestion.document(ctx,payer,identifier)
            if (result.source_id,result.document_id,result.input_sha256,result.taxpayer_master_revision)!=(
                    doc.source_id,doc.document_id,doc.input_sha256,doc.taxpayer_master_revision):
                raise ValueError('result source/master identity mismatch')
            if key!=config_key(result.ocr_config,result.runtime_sha256): raise ValueError('result configuration mismatch')
            if len(result.pages)!=len(doc.pages): raise ValueError('missing document pages')
            for page,original in zip(result.pages,doc.pages):
                if (page.page_id,page.image_hash,page.geometry,page.route)!=(original.page_id,original.render_sha256,original.geometry,original.route):
                    raise ValueError('result page identity mismatch')
        with self.ingestion.db() as db:
            db.execute('BEGIN IMMEDIATE')
            outbox=db.execute('SELECT document_sha256 FROM extraction_outbox WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=?',
                             (ctx.tenant_id,payer,identifier)).fetchone()
            if result and result.document_artifact_sha256!=outbox[0]: raise ValueError('document hash mismatch')
            cursor=db.execute('UPDATE ocr_jobs SET status=?,payload=?,sha256=?,issue=?,lease_token=NULL,lease_until=NULL '
                'WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=? AND config_key=? AND lease_token=? AND payload IS NULL',
                (result.status if result else 'FAILED',raw,digest(raw.encode()) if raw else None,
                 issue.model_dump_json() if issue else None,ctx.tenant_id,payer,identifier,key,token))
            if cursor.rowcount!=1: raise OCRError('PROTOCOL_ERROR','OCR lease was superseded')
            self.ingestion._event(db,ctx,payer,identifier,'OCR_FINISHED',outbox[0],
                                 {'config_key':key,'status':result.status if result else 'FAILED',
                                  'result_sha256':digest(raw.encode()) if raw else None})

    def get(self,ctx,payer,identifier,key):
        ctx.require(ctx.tenant_id,payer)
        with self.ingestion.db() as db:
            row=db.execute('SELECT * FROM ocr_jobs WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=? AND config_key=?',
                           (ctx.tenant_id,payer,identifier,key)).fetchone()
        if not row: return None
        result=None
        if row['payload']:
            if digest(row['payload'].encode())!=row['sha256']: raise OCRError('BAD_INPUT','OCR result integrity failure')
            result=NormalizedDocumentExtraction.model_validate_json(row['payload'])
        issue=json.loads(row['issue']) if row['issue'] and row['issue']!='ATTEMPT_LIMIT' else (
            OCRError('OCR_FAILED','Worker recovery attempt limit reached').issue.model_dump(mode='json') if row['issue'] else None)
        return dict(schema_version='1.0.0',config_version='ocr-layout-v1',creator='ocr-repository',stage='ocr-layout',
                    ingestion_id=identifier,config_key=key,status=row['status'],attempts=row['attempts'],issue=issue,result=result)
