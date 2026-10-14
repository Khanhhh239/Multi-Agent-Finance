import json
from ..quality.repository import QualityRepository
from ..quality.contracts import QualityAssessment
from ..canonicalization.derive import sha
from ..persistence.repository import digest
from .contracts import PlanningContext,RulePlan,RuleSet,CapabilityProfile
from ..legal_registry.registry import LegalRegistry
from ..taxonomy.service import Taxonomy
from ..domain.cfr import CanonicalFinancialRecord
from ..domain.taxpayer import TaxpayerMaster
from .catalog import load_catalog,load_capability
from .service import plan,implementation_sha


def replay(inputs,expected):
    if implementation_sha()!=expected.implementation_sha256:raise ValueError('pinned implementation required')
    result=plan(CanonicalFinancialRecord.model_validate(inputs['record']),QualityAssessment.model_validate(inputs['quality']),
        TaxpayerMaster.model_validate(inputs['master']),RuleSet.model_validate(inputs['ruleset']),
        LegalRegistry.model_validate(inputs['legal']),CapabilityProfile.model_validate(inputs['profile']) if inputs['profile'] else None,
        Taxonomy.model_validate(inputs['taxonomy']),PlanningContext.model_validate(inputs['context']),created_at=expected.created_at)
    if result!=expected:raise ValueError('plan replay differs from immutable artifact')
    return result


class PlanningRepository:
    def __init__(self,settings):
        self.quality=QualityRepository(settings);self.base=self.quality.base;self.ingestion=self.quality.ingestion

    def get(self,ctx,payer,evaluation_id):
        ctx.require(ctx.tenant_id,payer)
        with self.ingestion.db() as db:
            row=db.execute('SELECT payload,sha256 FROM rule_plans WHERE tenant_id=? AND taxpayer_id=? AND evaluation_id=?',
                           (ctx.tenant_id,payer,evaluation_id)).fetchone()
        if row is None:raise KeyError('rule plan not found')
        if digest(row['payload'].encode())!=row['sha256']:raise ValueError('plan integrity failure')
        return RulePlan.model_validate_json(row['payload'])

    def work(self,ctx,payer,record_id,revision):
        ctx.require(ctx.tenant_id,payer,'WRITE');self.base.initialize()
        record=self.base.record(ctx,payer,record_id,revision)
        with self.ingestion.db() as db:
            rows=db.execute('SELECT payload,sha256 FROM quality_assessments WHERE tenant_id=? AND taxpayer_id=? AND json_extract(payload,\'$.record_id\')=? AND json_extract(payload,\'$.record_revision\')=?',
                            (ctx.tenant_id,payer,record_id,revision)).fetchall()
        assessments=[]
        for row in rows:
            if digest(row['payload'].encode())!=row['sha256']:raise ValueError('quality integrity failure')
            assessment=QualityAssessment.model_validate_json(row['payload'])
            if assessment.input_sha256==sha(record.model_dump(mode='json')):assessments.append(assessment)
        if not assessments:raise ValueError('current revision needs a quality assessment first')
        quality=max(assessments,key=lambda a:(a.created_at,a.assessment_id))
        master=self.base.taxpayer(ctx,payer,record.taxpayer_master_revision)
        ruleset,legal,taxonomy=load_catalog()
        profile_name='pdf_ocr_v1' if record.source_format in ('PDF','IMAGE') else 'invoice_xml_v1' if record.source_format=='INVOICE_XML' else 'bank_v1' if record.source_format=='BANK_STATEMENT' else None
        profile=load_capability(profile_name) if profile_name else None
        # Public endpoint accepts no user-asserted legal/absence/ledger proofs.
        context=PlanningContext(tenant_id=ctx.tenant_id,taxpayer_id=payer,record_id=record_id,record_revision=revision)
        inputs={name:obj.model_dump(mode='json') if obj is not None else None for name,obj in (
            ('record',record),('quality',quality),('master',master),('ruleset',ruleset),('legal',legal),
            ('profile',profile),('taxonomy',taxonomy),('context',context))}
        key=sha([inputs,implementation_sha()])
        with self.ingestion.db() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT evaluation_id FROM rule_plans WHERE tenant_id=? AND taxpayer_id=? AND record_id=? AND revision=? AND replay_key=?',
                           (ctx.tenant_id,payer,record_id,revision,key)).fetchone()
            if old:return self.get(ctx,payer,old['evaluation_id'])
            result=plan(record,quality,master,ruleset,legal,profile,taxonomy,context)
            raw=result.model_dump_json();snap=json.dumps(inputs,sort_keys=True,ensure_ascii=False,separators=(',',':'))
            db.execute('INSERT INTO rule_plans VALUES(?,?,?,?,?,?,?,?,?,?)',(ctx.tenant_id,payer,result.evaluation_id,
                record_id,revision,key,raw,digest(raw.encode()),snap,digest(snap.encode())))
            self.base._audit(db,ctx,ctx.tenant_id,payer,'ARTIFACT_STORED',digest(raw.encode()),record,reason='RulePlan artifact created')
            return result

    def snapshot(self,ctx,payer,evaluation_id):
        self.get(ctx,payer,evaluation_id)
        with self.ingestion.db() as db:
            row=db.execute('SELECT inputs,inputs_sha256 FROM rule_plans WHERE tenant_id=? AND taxpayer_id=? AND evaluation_id=?',
                           (ctx.tenant_id,payer,evaluation_id)).fetchone()
        if digest(row['inputs'].encode())!=row['inputs_sha256']:raise ValueError('snapshot integrity failure')
        return json.loads(row['inputs'])
