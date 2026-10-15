import sys,json,unittest,sqlite3,math
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from pydantic import ValidationError
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'extraction_v1'))
import test_extraction as fixtures
from src.quality.contracts import *
from src.quality.policy import load_policy,confidence_reason
from src.quality.assessor import assess,family
from src.quality.completeness import flatten,coverage,completeness
from src.quality.calibration import fit,predict,metrics,precision_interval,threshold_report
from src.quality.validators import validate_raw,consistency
from src.quality.repository import QualityRepository,replay,implementation_sha
from src.canonicalization.derive import rederive,sha
from src.domain.field import FieldObject,FieldStatus,ConfidenceBasis
from src.domain.evidence import Provenance
from src.app import create_app

NOW=datetime(2026,10,13,tzinfo=timezone.utc)
SCOPE=CalibrationScope(field_family='*',document_family='invoice-vi-v1',engine_id='test-engine',
    engine_config_version='engine-config-v1',engine_runtime_sha256='c'*64,
    preprocess_version='preprocess-v1',extractor_sha256='a'*64,score_kind='RECOGNITION')

def evaluate(artifact=None,policy=None,**kwargs):
    artifact=artifact or fixtures.run()
    scope=SCOPE.model_copy(update={'extractor_sha256':artifact.extractor_sha256})
    return assess(artifact,artifact.record,policy or load_policy(),scope,assessment_id='assessment-test',created_at=NOW,
        implementation_sha256='a'*64,**kwargs)

def samples(scope=SCOPE,synthetic=True):
    return tuple(ScoreSample(sample_id=f'sample-{split}-{n}',logical_document_id=f'doc-{split}-{n}',group_id=f'group-{split}-{n}',
        source_sha256=sha([split,n]),split=split,scope=scope,raw_score=.8,correct=n%5!=0,
        use_permitted=True,independently_reviewed=True,split_frozen=True,synthetic=synthetic,evidence_reference='synthetic-test')
        for split in ('FIT','HOLDOUT') for n in range(30))

def update_field(artifact,path,field):
    data=artifact.record.model_dump(mode='json');parts=path.split('.');target=data
    for part in parts[:-1]: target=target[part]
    target[parts[-1]]=field.model_dump(mode='json')
    record=fixtures.CanonicalFinancialRecord.model_validate(data)
    return artifact.model_copy(update={'record':record})

class QualityTests(unittest.TestCase):
    def test_current_policy_cannot_enable_auto_accept(self):
        policy=load_policy();self.assertFalse(policy.auto_accept_enabled);self.assertTrue(all(v is None for v in policy.thresholds.values()))
        with self.assertRaises(ValidationError): QualityPolicy.model_validate({**policy.model_dump(),'auto_accept_enabled':True})
        with self.assertRaises(ValidationError): QualityPolicy.model_validate({**policy.model_dump(),'thresholds':{'money':.99}})

    def test_complete_format_does_not_imply_reliability(self):
        result=evaluate();self.assertEqual(result.completeness.ratio,1)
        self.assertEqual(result.critical_completeness.ratio,1)
        self.assertEqual(result.confidence.calibrated_count,0);self.assertIsNone(result.confidence.mean)
        self.assertTrue(result.review_required);self.assertTrue(all(not f.auto_accepted for f in result.fields))

    def test_critical_missing_not_hidden_by_overall(self):
        artifact=fixtures.run();missing=artifact.record.parties.seller.tax_id.model_copy(update={'value':None,'status':FieldStatus.MISSING})
        artifact=update_field(artifact,'parties.seller.tax_id',missing);result=evaluate(artifact)
        self.assertGreater(result.completeness.ratio,result.critical_completeness.ratio)
        self.assertIn('MISSING_FIELD',[i.code for i in result.issues]);self.assertEqual(result.disposition,'REQUEST_DATA')

    def test_receipt_has_separate_denominator(self):
        artifact=fixtures.run();artifact=artifact.model_copy(update={'record':artifact.record.model_copy(update={'record_type':'RECEIPT'})})
        result=evaluate(artifact)
        self.assertEqual(result.completeness.expected,6);self.assertEqual(result.critical_completeness.expected,3)
        self.assertEqual(result.profile_version,'receipt-quality-v1')

    def test_exclusions_not_counted_as_missing(self):
        missing=FieldObject(status='MISSING',source='test',provenance=Provenance(method='test',adapter_version='test'))
        fields={'a':missing.model_copy(update={'status':FieldStatus.NOT_APPLICABLE}),'b':missing.model_copy(update={'status':FieldStatus.NOT_PROVIDED_BY_SOURCE}),'c':missing}
        c=coverage(('a','b','c'),fields);self.assertEqual(c.denominator,1);self.assertEqual(c.excluded_not_applicable,1);self.assertEqual(c.excluded_not_provided,1)
        c=coverage(('a','b'),fields);self.assertIsNone(c.ratio)

    def test_source_invalid_differs_from_extraction_failure(self):
        status,issues=validate_raw('parties.seller.tax_id','123',source_confirmed=False)
        self.assertEqual(status,'UNKNOWN');self.assertEqual(issues[0].classification,'INVALID_EXTRACTION')
        status,issues=validate_raw('parties.seller.tax_id','123',source_confirmed=True)
        self.assertEqual(status,'INVALID_SOURCE_CONTENT');self.assertEqual(issues[0].classification,'INVALID_SOURCE_CONTENT')

    def test_source_check_requires_fidelity_and_scoped_evidence(self):
        artifact=fixtures.run();field=artifact.record.parties.seller.tax_id
        check=SourceCheck(field_path='parties.seller.tax_id',raw_value='123',fidelity_policy_version='xml-fidelity-v1',
            verification_reference='confirmed-xml-snapshot',evidence=field.provenance.evidence)
        with self.assertRaises(ValueError): evaluate(artifact,source_checks=(check,))
        policy=load_policy().model_copy(update={'fidelity_policies':('xml-fidelity-v1',)})
        result=evaluate(artifact,policy,source_checks=(check,),verified_fidelity_policies=('xml-fidelity-v1',))
        self.assertEqual(next(f for f in result.fields if f.field_path=='parties.seller.tax_id').validation,'INVALID_SOURCE_CONTENT')
        wrong=check.model_copy(update={'evidence':(check.evidence[0].model_copy(update={'source_id':'other'}),)})
        with self.assertRaises(ValueError): evaluate(artifact,policy,source_checks=(wrong,),verified_fidelity_policies=('xml-fidelity-v1',))

    def test_xml_deterministic_fidelity_without_probability(self):
        artifact=fixtures.run();field=artifact.record.invoice.number
        field=field.model_copy(update={'confidence_basis':ConfidenceBasis.DETERMINISTIC,'provenance':field.provenance.model_copy(update={'deterministic_policy_version':'xml-fidelity-v1'})})
        artifact=update_field(artifact,'invoice.number',field)
        policy=load_policy().model_copy(update={'fidelity_policies':('xml-fidelity-v1',)})
        a=evaluate(artifact,policy,verified_fidelity_policies=('xml-fidelity-v1',))
        q=next(f for f in a.fields if f.field_path=='invoice.number')
        self.assertEqual(q.reliability,'DETERMINISTIC_VERIFIED');self.assertTrue(q.eligible_within_policy)
        self.assertIsNone(q.probability);self.assertFalse(q.auto_accepted)
        b=evaluate(artifact,policy);self.assertIn('FIDELITY_UNVERIFIED',[i.code for i in b.issues])

    def test_human_confirmation_requires_verified_event(self):
        artifact=fixtures.run();field=artifact.record.invoice.number
        field=field.model_copy(update={'confidence_basis':ConfidenceBasis.HUMAN_CONFIRMED,'provenance':field.provenance.model_copy(update={'review_event_id':'event-1'})})
        artifact=update_field(artifact,'invoice.number',field)
        q=next(f for f in evaluate(artifact).fields if f.field_path=='invoice.number');self.assertEqual(q.reliability,'UNAVAILABLE')
        q=next(f for f in evaluate(artifact,verified_review_events=('event-1',)).fields if f.field_path=='invoice.number')
        self.assertEqual(q.reliability,'HUMAN_CONFIRMED')

    def test_ambiguous_has_select_action(self):
        a=fixtures.run(fixtures.document(['MST người bán: 1234567890','MST người bán: 9876543210']))
        result=evaluate(a);self.assertIn('SELECT_CANDIDATE',[r.action for r in result.recommendations])

    def test_incomplete_items_requests_data(self):
        result=evaluate(fixtures.run(fixtures.document(['Số hóa đơn: A'])))
        self.assertIn('INCOMPLETE_ITEMS',[i.code for i in result.issues]);self.assertEqual(result.disposition,'REQUEST_DATA')

    def test_multi_invoice_review_split(self):
        result=evaluate(fixtures.run(fixtures.document(['Số hóa đơn: A'],second=['Số hóa đơn: B'])))
        self.assertIsNone(result.record_id);self.assertEqual(result.disposition,'REVIEW_SPLIT')

    def test_amount_mismatch_not_legal_fail_or_source_invalid(self):
        result=evaluate(fixtures.run(fixtures.document(['Cộng trước thuế: 1000000','Tiền thuế: 8000','Tổng thanh toán: 108000'])))
        issue=next(i for i in result.issues if i.code=='HEADER_TOTAL_MISMATCH')
        self.assertEqual(issue.classification,'UNKNOWN');self.assertEqual(issue.severity,'ERROR')
        self.assertNotIn('FAIL',result.model_dump_json())

    def test_unparseable_extraction_issue_has_reextract_action(self):
        result=evaluate(fixtures.run(fixtures.document(['Tổng thanh toán: 1e9'])))
        q=next(i for i in result.issues if i.code=='INVALID_EXTRACTION');self.assertEqual(q.action,'REEXTRACT')

    def test_unparseable_party_keeps_canonical_path_and_block_refs(self):
        artifact=fixtures.run(fixtures.document(['MST người bán: 123']))
        result=evaluate(artifact);q=next(i for i in result.issues if i.code=='INVALID_EXTRACTION')
        self.assertEqual(q.field_path,'parties.seller.tax_id');self.assertEqual(q.source_block_refs,('block-0-0',))

    def test_pure_replay_schema_and_immutable_versions(self):
        artifact=fixtures.run();a=evaluate(artifact);b=evaluate(artifact)
        self.assertEqual(a,b);self.assertEqual(QualityAssessment.model_validate_json(a.model_dump_json()),a)
        policy=load_policy().model_copy(update={'version':'quality-manual-v2'})
        self.assertNotEqual(a.policy_sha256,evaluate(artifact,policy).policy_sha256)

class CalibrationTests(unittest.TestCase):
    def test_known_metrics_and_threshold_counts(self):
        m=metrics((.8,.2),(True,False));self.assertAlmostEqual(m['brier'],.04);self.assertAlmostEqual(m['ece'],.2)
        report=threshold_report((.9,.8,.1),(True,False,True),.8)
        self.assertEqual(report['accepted'],2);self.assertEqual(report['false_acceptances'],1);self.assertEqual(report['precision'],.5)
        self.assertIsNone(threshold_report((),(),.9)['precision'])
        low,high=precision_interval(10,10);self.assertLess(low,1);self.assertAlmostEqual(high,1)

    def test_functional_fit_never_production(self):
        model=fit(samples(),SCOPE,version='functional-v1',created_at=NOW)
        self.assertEqual(model.status,'FUNCTIONAL_ONLY');self.assertIsNone(predict(model,SCOPE,.8))
        self.assertAlmostEqual(predict(model,SCOPE,.8,allow_functional=True),25/32)
        self.assertIsNone(predict(model,SCOPE,.1,allow_functional=True))

    def test_insufficient_samples_and_detection_scores_unavailable(self):
        self.assertEqual(fit((),SCOPE,version='empty',created_at=NOW).status,'UNAVAILABLE')
        detection=SCOPE.model_copy(update={'score_kind':'DETECTION'})
        m=fit(samples(detection),detection,version='detection',created_at=NOW)
        self.assertIn('SCORE_NOT_TEXT_OR_FIELD_CONFIDENCE',m.reasons)

    def test_no_test_or_development_fit(self):
        for split in ('TEST','DEVELOPMENT'):
            ss=list(samples());ss[0]=ss[0].model_copy(update={'split':split})
            with self.assertRaises(ValueError): fit(ss,SCOPE,version='bad',created_at=NOW)

    def test_logical_source_and_template_group_leakage(self):
        for name in ('logical_document_id','source_sha256','group_id'):
            ss=list(samples());ss[-1]=ss[-1].model_copy(update={name:getattr(ss[0],name)})
            with self.assertRaises(ValueError): fit(ss,SCOPE,version='leak',created_at=NOW)

    def test_data_permission_review_and_freeze_gate(self):
        for name in ('use_permitted','independently_reviewed','split_frozen'):
            ss=list(samples());ss[0]=ss[0].model_copy(update={name:False})
            m=fit(ss,SCOPE,version='denied',created_at=NOW);self.assertEqual(m.status,'UNAVAILABLE');self.assertIn('DATASET_GATE_NOT_MET',m.reasons)

    def test_engine_preprocess_field_changes_invalidate(self):
        m=fit(samples(synthetic=False),SCOPE,version='unit-only',created_at=NOW)
        self.assertEqual(m.status,'VALIDATED')
        for name,value in (('engine_id','other'),('engine_config_version','v2'),('engine_runtime_sha256','d'*64),('preprocess_version','v2'),('extractor_sha256','b'*64),('field_family','different')):
            self.assertIsNone(predict(m,SCOPE.model_copy(update={name:value}),.8))

    def test_no_mapping_for_unsupported_holdout_bin(self):
        ss=list(samples());ss[-1]=ss[-1].model_copy(update={'raw_score':.1})
        self.assertIn('UNSUPPORTED_HOLDOUT_BIN',fit(ss,SCOPE,version='bin',created_at=NOW).reasons)

    def test_duplicate_and_mixed_scope_rejected(self):
        ss=samples()
        with self.assertRaises(ValueError): fit(ss+(ss[0],),SCOPE,version='duplicate',created_at=NOW)
        with self.assertRaises(ValueError): fit(ss,SCOPE.model_copy(update={'engine_id':'other'}),version='mixed',created_at=NOW)

    def test_high_mean_cannot_accept_low_date(self):
        artifact=fixtures.run();models=[];scores={}
        for path,field in flatten(artifact.record).items():
            if field.status!='PRESENT': continue
            low=path=='invoice.issue_date';count,correct,bucket=(8,0,0) if low else (100,99,4)
            probability=(correct+1)/(count+2);version='cal-'+str(len(models))
            model=CalibrationArtifact(config_version=version,creator='unit-fixture',stage='test',created_at=NOW,version=version,
                scope=SCOPE.model_copy(update={'field_family':family(path),'extractor_sha256':artifact.extractor_sha256}),status='VALIDATED',dataset_sha256='a'*64,
                fit_count=count,holdout_count=30,bins=(CalibrationBin(index=bucket,count=count,correct=correct,probability=probability),),brier=.01,ece=.01)
            models.append(model);scores[path]=.1 if low else .9
            field=field.model_copy(update={'confidence_basis':ConfidenceBasis.CALIBRATED,'confidence':probability,
                'provenance':field.provenance.model_copy(update={'calibration_version':version})})
            if path.startswith('items.'): continue # tested header fields suffice; no list-index mutation
            artifact=update_field(artifact,path,field)
        result=evaluate(artifact,calibrations=models,raw_scores=scores)
        self.assertGreater(result.confidence.mean,.85)
        date=next(f for f in result.fields if f.field_path=='invoice.issue_date');self.assertEqual(date.probability,.1)
        self.assertFalse(date.auto_accepted);self.assertFalse(date.eligible_within_policy);self.assertTrue(result.review_required)
        self.assertEqual(confidence_reason(date.probability,.95),'LOW_CONFIDENCE')
        self.assertEqual(confidence_reason(date.probability,None),'ACCEPTANCE_THRESHOLD_UNAVAILABLE')

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.PersistenceTests(methodName='test_atomic_idempotent_roundtrip');self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.repo=QualityRepository(self.fixture.settings);self.ctx=fixtures.CTX
        self.artifact=self.fixture.repo.work(self.ctx,'payer-a',self.fixture.identifier,self.fixture.key)

    def test_roundtrip_idempotence_and_snapshot_replay(self):
        a=self.repo.work(self.ctx,'payer-a',self.artifact.artifact_id);b=self.repo.work(self.ctx,'payer-a',self.artifact.artifact_id)
        self.assertEqual(a,b);self.assertEqual(a,replay(self.repo.inputs(self.ctx,'payer-a',a.assessment_id),a))
        self.assertEqual(self.repo.get(self.ctx,'payer-a',a.assessment_id),a)
        with self.repo.ingestion.db() as db: self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],9)

    def test_policy_change_appends_assessment(self):
        a=self.repo.work(self.ctx,'payer-a',self.artifact.artifact_id)
        policy=load_policy().model_copy(update={'version':'quality-manual-v2'})
        b=self.repo.work(self.ctx,'payer-a',self.artifact.artifact_id,policy)
        self.assertNotEqual(a.assessment_id,b.assessment_id);self.assertEqual(self.repo.get(self.ctx,'payer-a',a.assessment_id),a)

    def test_atomic_audit_failure_and_immutable_payload(self):
        with patch.object(self.repo.ingestion,'_event',side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError): self.repo.work(self.ctx,'payer-a',self.artifact.artifact_id)
        with self.repo.ingestion.db() as db: self.assertEqual(db.execute('SELECT count(*) FROM quality_assessments').fetchone()[0],0)
        self.repo.work(self.ctx,'payer-a',self.artifact.artifact_id)
        with self.repo.ingestion.db() as db:
            with self.assertRaises(sqlite3.IntegrityError): db.execute("DELETE FROM quality_assessments")

    def test_auth_tenant_scope_and_not_found(self):
        a=self.repo.work(self.ctx,'payer-a',self.artifact.artifact_id)
        client=TestClient(create_app(self.fixture.settings));url='/v1/quality-assessments/'+a.assessment_id
        self.assertEqual(client.get(url,params={'taxpayer_id':'payer-a'}).status_code,401)
        headers={'Authorization':'Bearer '+self.fixture.token}
        self.assertEqual(client.get(url,params={'taxpayer_id':'other'},headers=headers).status_code,403)
        self.assertEqual(client.get(url,params={'taxpayer_id':'payer-a'},headers=headers).status_code,200)
        self.assertEqual(client.get('/v1/quality-assessments/missing',params={'taxpayer_id':'payer-a'},headers=headers).status_code,404)
        with self.assertRaises(KeyError): self.repo.get(self.ctx.model_copy(update={'tenant_id':'other'}),'payer-a',a.assessment_id)

    def test_corrected_revision_requires_rederive(self):
        a=self.artifact.record;changed=a.parties.buyer.tax_id.model_copy(update={'value':'1234567890'})
        b=a.model_copy(update={'revision':2,'parties':a.parties.model_copy(update={'buyer':a.parties.buyer.model_copy(update={'tax_id':changed})})})
        self.repo.base.append_revision(self.ctx,b,1,'test stale derived')
        with self.assertRaisesRegex(ValueError,'rederive'): self.repo.work(self.ctx,'payer-a',self.artifact.artifact_id)
        master=self.repo.base.taxpayer(self.ctx,'payer-a',1)
        c,_,_=rederive(b.model_copy(update={'revision':3}),master,self.artifact.profile)
        self.repo.base.append_revision(self.ctx,c,2,'test rederived')
        result=self.repo.work(self.ctx,'payer-a',self.artifact.artifact_id);self.assertEqual(result.record_revision,3)
        original=self.repo.work(self.ctx,'payer-a',self.artifact.artifact_id,revision=1);self.assertEqual(original.record_revision,1)

    def test_concurrent_calls_share_assessment(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:self.repo.work(self.ctx,'payer-a',self.artifact.artifact_id),range(2)))
        self.assertEqual(results[0].assessment_id,results[1].assessment_id)

    def test_replay_rejects_changed_policy_or_implementation(self):
        a=self.repo.work(self.ctx,'payer-a',self.artifact.artifact_id)
        inputs=self.repo.inputs(self.ctx,'payer-a',a.assessment_id)
        with self.assertRaises(ValueError): replay({**inputs,'implementation_sha256':'f'*64},a)
        changed={**inputs,'policy':{**inputs['policy'],'version':'changed'}}
        with self.assertRaises(ValueError): replay(changed,a)

    def test_cached_result_does_not_bypass_head_race_check(self):
        self.repo.work(self.ctx,'payer-a',self.artifact.artifact_id)
        old=self.artifact.record;new=old.model_copy(update={'revision':2})
        self.repo.base.append_revision(self.ctx,new,1,'new revision before quality lock')
        with patch.object(self.repo.base,'record',return_value=old):
            with self.assertRaisesRegex(ValueError,'revision changed'): self.repo.work(self.ctx,'payer-a',self.artifact.artifact_id)

if __name__=='__main__': unittest.main()
