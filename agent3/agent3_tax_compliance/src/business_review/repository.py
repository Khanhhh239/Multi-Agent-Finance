"""Local operator imports and read-only HTTP readiness; separate immutable sidecar."""
import json
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from ..persistence.repository import Repository,digest
from ..quality.contracts import QualityAssessment
from ..planning.catalog import load_catalog,load_capability
from ..planning.contracts import PlanningContext,CapabilityProfile
from ..planning.service import plan
from .service import observed
from ..canonicalization.derive import sha
from ..review.contracts import ReviewError
from .contracts import ReviewDossier
from .evidence import verify_files,store_files,verify_stored
from .service import bind_scope,prepare

APP_ID=1110659670


class BusinessReviewRepository:
    def __init__(self,settings):
        self.base=Repository(settings)
        self.path=settings.database_path.with_name(settings.database_path.stem+'.business.sqlite3')

    @contextmanager
    def db(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.path,timeout=10) as db:
            db.row_factory=sqlite3.Row
            tables=db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            ident=db.execute('PRAGMA application_id').fetchone()[0]
            if tables and ident!=APP_ID:raise ValueError('unknown business database')
            db.execute('PRAGMA application_id='+str(APP_ID))
            db.execute('''CREATE TABLE IF NOT EXISTS business_reviews(
                tenant_id TEXT NOT NULL,taxpayer_id TEXT NOT NULL,record_id TEXT NOT NULL,
                revision INTEGER NOT NULL,review_id TEXT NOT NULL,actor_id TEXT NOT NULL,
                payload TEXT NOT NULL,sha256 TEXT NOT NULL,
                PRIMARY KEY(tenant_id,taxpayer_id,review_id))''')
            yield db

    def import_local(self,ctx,payer,record_id,dossier,evidence_root):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        dossier=ReviewDossier.model_validate_json(dossier.model_dump_json())
        record=self.base.record(ctx,payer,record_id)
        bind_scope(record,dossier)
        if dossier.reviewer_id!=ctx.actor_id:raise ValueError('reviewer must be authenticated operator')
        verify_files(dossier,evidence_root)
        source,_=self.base.source(ctx,payer,record.source_id)
        if any(d.kind=='INVOICE' and d.sha256!=source.sha256 for d in dossier.documents):
            raise ValueError('invoice evidence is not the captured source')
        self.verify_daily(ctx,payer,dossier)
        store_files(dossier,evidence_root,self.evidence_directory(ctx,payer))
        raw=dossier.model_dump_json();pin=digest(raw.encode())
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT sha256 FROM business_reviews WHERE tenant_id=? AND taxpayer_id=? AND review_id=?',
                (ctx.tenant_id,payer,dossier.review_id)).fetchone()
            if row and row['sha256']!=pin:raise ReviewError('REVIEW_ID_CONFLICT','Use a new review ID for changed evidence.',409)
            if not row:db.execute('INSERT INTO business_reviews VALUES(?,?,?,?,?,?,?,?)',
                (ctx.tenant_id,payer,record_id,record.revision,dossier.review_id,ctx.actor_id,raw,pin))
        return dict(review_id=dossier.review_id,record_revision=record.revision,dossier_sha256=sha(dossier.model_dump(mode='json')),
            imported=True,technical_only=True,legal_approval=False)

    def evidence_directory(self,ctx,payer):
        return self.path.with_suffix('.evidence')/sha([ctx.tenant_id,payer])

    def verify_daily(self,ctx,payer,dossier):
        if dossier.daily:
            for row in dossier.daily.ledger.purchases:
                # Never read another tenant/payer by accepting caller-controlled ledger scope.
                if (row.tenant_id,row.taxpayer_id)!=(ctx.tenant_id,payer):raise ValueError('cross-scope daily ledger')
                other=self.base.record(ctx,payer,row.record_id)
                if (row.revision,row.input_sha256,row.issue_date,row.seller_tax_id,row.gross,row.currency)!=(
                    other.revision,sha(other.model_dump(mode='json')),
                    observed(other.invoice.issue_date) if other.invoice else None,
                    str(observed(other.parties.seller.tax_id)).replace('-','') if other.parties.seller else None,
                    observed(other.totals.gross),observed(other.currency)):
                    raise ValueError('daily ledger differs from saved current records')

    def latest(self,ctx,payer,record):
        ctx.require(ctx.tenant_id,payer)
        if not self.path.exists():return None
        with self.db() as db:
            row=db.execute('SELECT * FROM business_reviews WHERE tenant_id=? AND taxpayer_id=? AND record_id=? AND revision=? ORDER BY rowid DESC LIMIT 1',
                (ctx.tenant_id,payer,record.record_id,record.revision)).fetchone()
        if row is None:return None
        if digest(row['payload'].encode())!=row['sha256']:raise ValueError('review integrity failure')
        dossier=ReviewDossier.model_validate_json(row['payload']);bind_scope(record,dossier)
        verify_stored(dossier,self.evidence_directory(ctx,payer))
        return dossier

    def assess(self,ctx,payer,record_id):
        ctx.require(ctx.tenant_id,payer)
        record=self.base.record(ctx,payer,record_id)
        with self.base.connection() as db:
            rows=db.execute("SELECT payload,sha256 FROM quality_assessments WHERE tenant_id=? AND taxpayer_id=? AND json_extract(payload,'$.record_id')=? AND json_extract(payload,'$.record_revision')=?",
                (ctx.tenant_id,payer,record_id,record.revision)).fetchall()
        qualities=[]
        for raw,pin in rows:
            if digest(raw.encode())!=pin:raise ValueError('quality integrity failure')
            q=QualityAssessment.model_validate_json(raw)
            if q.input_sha256==sha(record.model_dump(mode='json')):qualities.append(q)
        if not qualities:raise ReviewError('QUALITY_REQUIRED','Assess quality for the saved revision first.',409)
        q=max(qualities,key=lambda v:(v.created_at,v.assessment_id))
        rules,legal,taxonomy=load_catalog()
        name='pdf_ocr_v1' if record.source_format in ('PDF','IMAGE') else 'invoice_xml_v1' if record.source_format=='INVOICE_XML' else None
        profile=load_capability(name) if name else None
        dossier=self.latest(ctx,payer,record)
        if dossier:self.verify_daily(ctx,payer,dossier)
        if dossier and record.source_format in ('PDF','IMAGE','INVOICE_XML'):
            profile=CapabilityProfile.model_validate_json((Path(__file__).resolve().parents[2]/
                'configs/business_review/capability_reviewed_capture_v1.json').read_text(encoding='utf-8'))
        result=prepare(record,dossier,rules,legal,profile,q)
        master=self.base.taxpayer(ctx,payer,record.taxpayer_master_revision)
        result['draft_plan']=plan(record,q,master,rules,legal,profile,taxonomy,
            PlanningContext.model_validate(result['planning_context']),created_at=q.created_at).model_dump(mode='json')
        result['is_current_revision']=self.base.record(ctx,payer,record_id).revision==record.revision
        return result
