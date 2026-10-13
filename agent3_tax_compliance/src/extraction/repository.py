from ..adapters.ocr.repository import OCRRepository
from ..canonicalization.derive import sha
from ..persistence.repository import digest
from ..domain.envelope import SourceEnvelope
from .contracts import ExtractionArtifact,ExtractionProfile
from .service import extract,implementation_sha

class ExtractionRepository:
    def __init__(self,settings):
        self.ocr=OCRRepository(settings)
        self.ingestion=self.ocr.ingestion
        self.base=self.ingestion.base

    def get(self,ctx,payer,artifact_id):
        ctx.require(ctx.tenant_id,payer)
        with self.ingestion.db() as db:
            row=db.execute('SELECT payload,sha256 FROM cfr_extractions WHERE tenant_id=? AND taxpayer_id=? AND artifact_id=?',
                (ctx.tenant_id,payer,artifact_id)).fetchone()
        if not row: raise KeyError('extraction not found')
        if digest(row['payload'].encode())!=row['sha256']: raise ValueError('extraction integrity failure')
        return ExtractionArtifact.model_validate_json(row['payload'])

    def work(self,ctx,payer,ingestion_id,ocr_config_key,profile=None):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        profile=profile or ExtractionProfile()
        job=self.ocr.get(ctx,payer,ingestion_id,ocr_config_key)
        if not job or job['result'] is None: raise ValueError('committed OCR result required')
        document=job['result']
        source,_=self.base.source(ctx,payer,document.source_id)
        if source.sha256!=document.input_sha256: raise ValueError('OCR/source hash mismatch')
        master=self.base.taxpayer(ctx,payer,document.taxpayer_master_revision)
        key=sha({'document':sha(document.model_dump(mode='json')),'profile':profile.model_dump(mode='json'),
                 'master':sha(master.model_dump(mode='json')),'extractor':implementation_sha()})
        scope=(ctx.tenant_id,payer,ingestion_id,ocr_config_key,key)
        # Lock covers allocation, CFR, artifact and audit; duplicate calls reuse IDs.
        with self.ingestion.db() as db:
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute('SELECT artifact_id FROM cfr_extractions WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=? AND ocr_config_key=? AND extraction_key=?',scope).fetchone()
            if previous: return self.get(ctx,payer,previous['artifact_id'])
            artifact=extract(document,source.detected_format,master,profile)
            artifact=ExtractionArtifact.model_validate_json(artifact.model_dump_json())
            record=artifact.record
            if record:
                if source.taxpayer_master_revision!=record.taxpayer_master_revision or source.detected_format!=record.source_format:
                    raise ValueError('record source/master mismatch')
                db.execute('INSERT INTO records VALUES(?,?,?,?,?)',(ctx.tenant_id,payer,record.record_id,record.source_id,1))
                self.base._insert_revision(db,record)
                self.base._audit(db,ctx,ctx.tenant_id,payer,'RECORD_CREATED',digest(record.model_dump_json().encode()),record)
            raw=artifact.model_dump_json()
            db.execute('INSERT INTO cfr_extractions VALUES(?,?,?,?,?,?,?,?)',(*scope,artifact.artifact_id,raw,digest(raw.encode())))
            self.ingestion._event(db,ctx,payer,ingestion_id,'CFR_EXTRACTED',document.input_sha256,
                {'artifact_id':artifact.artifact_id,'extraction_key':key,'review_required':True})
            return artifact
