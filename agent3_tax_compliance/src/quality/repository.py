import json
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
from ..extraction.repository import ExtractionRepository
from ..canonicalization.derive import sha,rederive
from ..persistence.repository import digest
from .contracts import QualityAssessment,QualityPolicy,CalibrationScope,CalibrationArtifact
from .policy import load_policy
from .assessor import assess

def implementation_sha():
    root=Path(__file__).resolve().parent
    return sha({p.name:digest(p.read_bytes()) for p in sorted(root.glob('*.py'))})

def verified_events(db,record):
    """Proof requires an immutable, scoped event whose after-field matches the current value."""
    from .completeness import flatten
    proofs=set();groups={}
    for path,field in flatten(record).items():
        event_id=field.provenance.review_event_id
        if field.confidence_basis!='HUMAN_CONFIRMED' or not event_id: continue
        groups.setdefault(event_id,[]).append((path,field))
    for event_id,fields in groups.items():
        row=db.execute('SELECT payload,sha256 FROM review_events WHERE tenant_id=? AND taxpayer_id=? AND record_id=? AND event_id=?',
            (record.tenant_id,record.taxpayer_id,record.record_id,event_id)).fetchone()
        if not row: continue
        if digest(row['payload'].encode())!=row['sha256']: raise ValueError('review proof integrity failure')
        event=json.loads(row['payload'])
        def matches(path,field):
            for c in event['changes']:
                if c['field_path']==path and c['after']==field.model_dump(mode='json'):return True
                if c['field_path']=='items' and path.startswith('items.'):
                    _,iid,name=path.split('.')
                    if any(i['item_id']==iid and i.get(name)==field.model_dump(mode='json') for i in c['after']['rows']):return True
            return False
        if all(matches(path,field) for path,field in fields):
            proofs.add(event_id)
    return tuple(sorted(proofs))

def replay(inputs,assessment):
    from ..extraction.contracts import ExtractionArtifact
    from ..domain.cfr import CanonicalFinancialRecord
    if inputs['implementation_sha256']!=implementation_sha() or inputs['implementation_sha256']!=assessment.implementation_sha256:
        raise ValueError('replay requires the pinned implementation')
    if sha(inputs['policy'])!=assessment.policy_sha256 or sha(inputs['artifact'])!=assessment.extraction_sha256:
        raise ValueError('replay snapshot/assessment binding mismatch')
    if sha(inputs['record'] if inputs['record'] else inputs['artifact'])!=assessment.input_sha256 or sha(inputs['calibrations'])!=assessment.calibration_sha256:
        raise ValueError('replay record/calibration mismatch')
    return assess(ExtractionArtifact.model_validate(inputs['artifact']),
        CanonicalFinancialRecord.model_validate(inputs['record']) if inputs['record'] else None,
        QualityPolicy.model_validate(inputs['policy']),CalibrationScope.model_validate(inputs['scope']),
        assessment_id=assessment.assessment_id,created_at=assessment.created_at,implementation_sha256=inputs['implementation_sha256'],
        calibrations=tuple(CalibrationArtifact.model_validate(c) for c in inputs['calibrations']),
        verified_review_events=tuple(inputs.get('verified_review_events',())))

class QualityRepository:
    def __init__(self,settings):
        self.extraction=ExtractionRepository(settings);self.ingestion=self.extraction.ingestion;self.base=self.extraction.base

    def get(self,ctx,payer,assessment_id):
        ctx.require(ctx.tenant_id,payer)
        with self.ingestion.db() as db:
            row=db.execute('SELECT payload,sha256 FROM quality_assessments WHERE tenant_id=? AND taxpayer_id=? AND assessment_id=?',
                (ctx.tenant_id,payer,assessment_id)).fetchone()
        if not row: raise KeyError('quality assessment not found')
        if digest(row['payload'].encode())!=row['sha256']: raise ValueError('quality integrity failure')
        return QualityAssessment.model_validate_json(row['payload'])

    def inputs(self,ctx,payer,assessment_id):
        ctx.require(ctx.tenant_id,payer)
        with self.ingestion.db() as db:
            row=db.execute('SELECT inputs,inputs_sha256 FROM quality_assessments WHERE tenant_id=? AND taxpayer_id=? AND assessment_id=?',
                (ctx.tenant_id,payer,assessment_id)).fetchone()
        if not row: raise KeyError('quality assessment not found')
        if digest(row['inputs'].encode())!=row['inputs_sha256']: raise ValueError('quality replay input integrity failure')
        return json.loads(row['inputs'])

    def work(self,ctx,payer,artifact_id,policy=None,revision=None):
        ctx.require(ctx.tenant_id,payer,'WRITE');policy=policy or load_policy()
        artifact=self.extraction.get(ctx,payer,artifact_id)
        record=self.base.record(ctx,payer,artifact.record.record_id,revision) if artifact.record else None
        if record:
            source,_=self.base.source(ctx,payer,record.source_id)
            if source.sha256!=artifact.input_sha256: raise ValueError('artifact/source mismatch')
            master=self.base.taxpayer(ctx,payer,record.taxpayer_master_revision)
            recomputed,_,_=rederive(record,master,artifact.profile)
            if recomputed.derived!=record.derived: raise ValueError('stale derived fields; rederive before quality')
        with self.ingestion.db() as db:
            row=db.execute('SELECT ocr_config_key FROM cfr_extractions WHERE tenant_id=? AND taxpayer_id=? AND artifact_id=?',
                (ctx.tenant_id,payer,artifact_id)).fetchone()
        normalized=self.extraction.ocr.get(ctx,payer,artifact.ingestion_id,row['ocr_config_key'])['result']
        if sha(normalized.model_dump(mode='json'))!=artifact.normalized_input_sha256: raise ValueError('normalized input hash mismatch')
        scope=CalibrationScope(field_family='*',document_family=artifact.profile.version,engine_id=normalized.ocr_config.model_id,
            engine_config_version=normalized.ocr_config.version,engine_runtime_sha256=normalized.runtime_sha256,
            preprocess_version=normalized.ocr_config.preprocess_version,extractor_sha256=artifact.extractor_sha256,
            score_kind='DETECTION' if normalized.ocr_config.model_id=='ppocrv6_vietocr' else 'UNAVAILABLE')
        inputs={'artifact':artifact.model_dump(mode='json'),'record':record.model_dump(mode='json') if record else None,
            'policy':policy.model_dump(mode='json'),'scope':scope.model_dump(mode='json'),'calibrations':[],
            'implementation_sha256':implementation_sha()}
        if record:
            with self.ingestion.db() as db:
                # Read-only v5 historical databases have no review table.
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='review_events'").fetchone():
                    proofs=verified_events(db,record)
                    if proofs: inputs['verified_review_events']=list(proofs)
        key=sha(inputs)
        with self.ingestion.db() as db:
            db.execute('BEGIN IMMEDIATE')
            # Default-head reads must not become silently stale while waiting for lock.
            if record and revision is None:
                head=db.execute('SELECT head FROM records WHERE tenant_id=? AND taxpayer_id=? AND record_id=?',
                    (ctx.tenant_id,payer,record.record_id)).fetchone()[0]
                if head!=record.revision: raise ValueError('revision changed; retry quality assessment')
            previous=db.execute('SELECT assessment_id FROM quality_assessments WHERE tenant_id=? AND taxpayer_id=? AND replay_key=?',
                (ctx.tenant_id,payer,key)).fetchone()
            if previous: return self.get(ctx,payer,previous['assessment_id'])
            assessment=assess(artifact,record,policy,scope,assessment_id='quality-'+uuid4().hex,created_at=datetime.now(timezone.utc),
                implementation_sha256=inputs['implementation_sha256'],verified_review_events=tuple(inputs.get('verified_review_events',())))
            raw=assessment.model_dump_json();input_raw=json.dumps(inputs,sort_keys=True,ensure_ascii=False,separators=(',',':'))
            db.execute('INSERT INTO quality_assessments VALUES(?,?,?,?,?,?,?,?,?)',
                (ctx.tenant_id,payer,artifact_id,key,assessment.assessment_id,raw,digest(raw.encode()),input_raw,digest(input_raw.encode())))
            self.ingestion._event(db,ctx,payer,artifact.ingestion_id,'QUALITY_ASSESSED',assessment.input_sha256,
                {'assessment_id':assessment.assessment_id,'record_revision':assessment.record_revision,'policy_version':policy.version,'review_required':True})
            return assessment
