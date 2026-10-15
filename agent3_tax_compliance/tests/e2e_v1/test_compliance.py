"""Synthetic raw capture/review -> planning -> real ZEN -> template/API acceptance."""
import sys,json,sqlite3,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from pydantic import ValidationError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'rules_v1'))
import test_rules as rf
from src.orchestration.workflow import Workflow
from src.orchestration.contracts import EvaluationCommand,EvaluationReport
from src.planning.contracts import RuleSet,RuleFamily,Predicate,FieldRequirement
from src.legal_registry.registry import LegalRegistry
from src.taxonomy.service import Taxonomy
from src.rules.contracts import ModelPackage,Binding
from src.rules.zen_adapter import EngineFailure
from src.review.correction_service import CorrectionService
from src.review.contracts import ReviewError,CorrectionCommand,Change
from src.explanation.service import render,load_templates
from src.app import create_app


class ComplianceTests(unittest.TestCase):
    def setUp(self):
        self.fixture=rf.PersistenceTests('test_capture_review_plan_real_worker_store_replay_end_to_end')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.settings=self.fixture.fixture.fixture.settings
        self.workflow=Workflow(self.settings);self.ctx=self.fixture.ctx;self.payer=self.fixture.payer
        self.record_id=self.fixture.fixture.record.record_id
        self.client=TestClient(create_app(self.settings))
        self.headers={'Authorization':'Bearer '+self.fixture.fixture.fixture.token,'Idempotency-Key':'evaluation-one'}
        self.revision=1;self.catalog=None;self.package=None

    def approved(self):
        plan,self.package=self.fixture.approved_capture_plan()
        inputs=self.workflow.planning.snapshot(self.ctx,self.payer,plan.evaluation_id)
        self.catalog=(RuleSet.model_validate(inputs['ruleset']),LegalRegistry.model_validate(inputs['legal']),Taxonomy.model_validate(inputs['taxonomy']))
        self.revision=2
        return plan

    def patches(self):
        from contextlib import ExitStack
        stack=ExitStack()
        if self.catalog:
            stack.enter_context(patch('src.planning.repository.load_catalog',return_value=self.catalog))
            stack.enter_context(patch('src.orchestration.workflow.load_package',return_value=self.package))
        return stack

    def run_evaluation(self,key='evaluation-one',runner=None):
        with self.patches():return self.workflow.work(self.ctx,self.payer,self.record_id,EvaluationCommand(expected_record_revision=self.revision),key,runner=runner)

    def test_default_catalog_no_false_tax_pass_and_capture_export_works(self):
        result=self.run_evaluation()
        self.assertEqual(result.status,'COMPLETED')
        self.assertIn(result.report.aggregate.verdict,('REVIEW','NO_VERDICT'))
        self.assertEqual(result.report.aggregate.counts.evaluated,0)
        self.assertTrue(result.report.technical_only)
        self.assertTrue(self.workflow.replay(self.ctx,self.payer,result.evaluation_id)['verified'])
        response=self.client.get('/v1/records/'+self.record_id+'/export?taxpayer_id='+self.payer,headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['record']['revision'],1)

    def test_reviewed_capture_real_zen_template_snapshot_replay(self):
        self.approved();result=self.run_evaluation()
        self.assertEqual(result.report.aggregate.verdict,'PASS')
        self.assertIn('bản dữ liệu 2',result.report.explanation.scope)
        self.assertEqual(result.report.explanation.verdict,result.report.aggregate.verdict)
        self.assertEqual(result.report.attempts_total,1)
        rows=self.workflow.artifact(self.ctx,self.payer,result.evaluation_id).rule_results
        self.assertEqual(rows[0].result,'PASS')
        self.assertTrue(rows[0].trace.raw_response_json)
        self.assertTrue(rows[0].sources)
        self.assertTrue(rows[0].citations[0].locator_reviewed)
        self.assertTrue(self.workflow.replay(self.ctx,self.payer,result.evaluation_id)['verified'])

    def test_idempotency_same_key_no_repeat_work_and_changed_request_conflicts(self):
        result=self.run_evaluation()
        with patch.object(self.workflow,'prepare',side_effect=AssertionError('must not prepare again')):
            self.assertEqual(self.run_evaluation(),result)
        with self.assertRaises(ReviewError) as caught:
            self.workflow.work(self.ctx,self.payer,self.record_id,EvaluationCommand(expected_record_revision=1,reason='different'),'evaluation-one')
        self.assertEqual(caught.exception.code,'IDEMPOTENCY_CONFLICT')

    def test_new_request_new_public_evaluation_reuses_pinned_engine_safely(self):
        self.approved();first=self.run_evaluation();second=self.run_evaluation('evaluation-two')
        self.assertNotEqual(first.evaluation_id,second.evaluation_id)
        self.assertEqual(first.report.execution_id,second.report.execution_id)
        self.assertEqual(first.report.record_sha256,second.report.record_sha256)

    def test_changed_ruleset_new_plan_and_evaluation(self):
        self.approved();first=self.run_evaluation()
        self.catalog=(self.catalog[0].model_copy(update={'version':'synthetic-next'}),*self.catalog[1:])
        second=self.run_evaluation('evaluation-two')
        self.assertNotEqual(first.report.planning_evaluation_id,second.report.planning_evaluation_id)
        self.assertNotEqual(first.report.execution_id,second.report.execution_id)

    def test_stale_revision_rejected(self):
        self.approved()
        with self.assertRaises(ReviewError) as caught:
            self.workflow.work(self.ctx,self.payer,self.record_id,EvaluationCommand(expected_record_revision=1),'stale')
        self.assertEqual(caught.exception.code,'REVISION_CONFLICT')

    def correct_direction(self):
        service=CorrectionService(self.settings)
        task=service.page(self.ctx,self.payer,'tasks',record_id=self.record_id,revision=self.revision)['items'][0]
        command=CorrectionCommand(record_id=self.record_id,expected_revision=self.revision,task_id=task['task_id'],reason='Synthetic direction comparison',
            changes=(Change(field_path='parties.seller.tax_id',new_value='1111111111'),Change(field_path='parties.buyer.tax_id',new_value='1234567890')))
        service.correct(self.ctx,self.payer,command,'direction-review')
        self.revision+=1

    def test_correction_new_direction_and_historical_evaluation_not_reused(self):
        self.approved();old=self.run_evaluation();self.correct_direction()
        rule=self.catalog[0].families[0].versions[0]
        rule=rule.model_copy(update={'predicates':(Predicate(requirement=FieldRequirement(path='derived.invoice_direction'),value='INPUT'),)})
        self.catalog=(RuleSet(version='direction-synthetic',families=(RuleFamily(rule_id=rule.rule_id,supported_from=rule.effective_from,supported_to=rule.effective_to,versions=(rule,)),)),*self.catalog[1:])
        result=self.run_evaluation('new-revision')
        self.assertEqual(result.record_revision,3)
        self.assertNotEqual(old.report.record_sha256,result.report.record_sha256)
        plan=self.workflow.planning.get(self.ctx,self.payer,result.report.planning_evaluation_id)
        self.assertEqual(plan.entries[0].traces[0].state,'MATCH')
        previous=self.workflow.get(self.ctx,self.payer,old.evaluation_id)
        self.assertFalse(previous.is_current_revision)
        self.assertEqual(previous.report,old.report)

    def test_failure_resume_uses_pinned_snapshot_not_new_catalog(self):
        with patch.object(self.workflow.execution,'work',side_effect=RuntimeError('simulated outage')):
            with self.assertRaises(RuntimeError):self.run_evaluation()
        row=self.workflow.latest(self.ctx,self.payer,self.record_id,1)[0]
        self.assertEqual(row.status,'FAILED');self.assertIsNone(row.report)
        with patch('src.orchestration.workflow.load_package',side_effect=AssertionError('must use pinned package')):
            result=self.workflow.resume(self.ctx,self.payer,row.evaluation_id)
        self.assertEqual(result.status,'COMPLETED')
        self.assertEqual(result.evaluation_id,row.evaluation_id)

    def test_report_audit_failure_rolls_back_then_resume(self):
        audit=self.workflow.base._audit
        def fail(db,ctx,tenant,payer,event,hash,record=None,reason=''):
            if reason=='Compliance evaluation/template stored':raise RuntimeError('audit failed')
            return audit(db,ctx,tenant,payer,event,hash,record,reason)
        with patch.object(self.workflow.base,'_audit',side_effect=fail):
            with self.assertRaises(RuntimeError):self.run_evaluation()
        with self.workflow.ingestion.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM evaluation_reports').fetchone()[0],0)
        row=self.workflow.latest(self.ctx,self.payer,self.record_id,1)[0]
        self.assertEqual(self.workflow.resume(self.ctx,self.payer,row.evaluation_id).status,'COMPLETED')

    def test_api_auth_scope_summary_pages_detail_export_and_replay(self):
        self.approved();url='/v1/records/'+self.record_id+'/evaluations?taxpayer_id='+self.payer
        body={'expected_record_revision':2}
        self.assertEqual(self.client.post(url,json=body,headers={'Idempotency-Key':'no-auth'}).status_code,401)
        with self.patches():response=self.client.post(url,json=body,headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        identifier=response.json()['evaluation_id'];base='/v1/evaluations/'+identifier
        for suffix in ('','/rule-results?limit=1','/attempts?limit=1','/export'):
            target=base+suffix+('&' if '?' in suffix else '?')+'taxpayer_id='+self.payer
            response=self.client.get(target,headers=self.headers)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.headers['cache-control'],'private, no-store')
        self.assertEqual(self.client.post(base+'/replay?taxpayer_id='+self.payer,headers=self.headers).json()['verified'],True)
        rows=self.workflow.page(self.ctx,self.payer,identifier,'rules')
        detail=self.client.get(base+'/rule-results/'+rows['items'][0]['result_id']+'?taxpayer_id='+self.payer,headers=self.headers)
        self.assertTrue(detail.json()['trace'])
        self.assertEqual(self.client.get(base+'?taxpayer_id=payer-b',headers=self.headers).status_code,403)
        other=self.ctx.model_copy(update={'tenant_id':'other'})
        with self.assertRaises(KeyError):self.workflow.get(other,self.payer,identifier)

    def test_signed_pagination_stable_scoped_and_kind_bound(self):
        result=self.run_evaluation();identifier=result.evaluation_id
        first=self.workflow.page(self.ctx,self.payer,identifier,'rules',limit=1)
        self.assertTrue(first['next_cursor'])
        second=self.workflow.page(self.ctx,self.payer,identifier,'rules',first['next_cursor'],1)
        self.assertNotEqual(first['items'][0]['result_id'],second['items'][0]['result_id'])
        self.assertEqual(first['snapshot_sha256'],second['snapshot_sha256'])
        for kind,limit in (('attempts',1),('rules',2)):
            with self.assertRaises(ReviewError):self.workflow.page(self.ctx,self.payer,identifier,kind,first['next_cursor'],limit)
        other=self.run_evaluation('other-evaluation')
        with self.assertRaises(ReviewError):self.workflow.page(self.ctx,self.payer,other.evaluation_id,'rules',first['next_cursor'],1)
        with self.assertRaises(ReviewError):self.workflow.page(self.ctx,self.payer,identifier,'rules','tampered',1)

    def test_mixed_fail_review_timeout_retained_in_template(self):
        self.approved();base=self.catalog[0].families[0].versions[0];seller='1234567890'
        rules=[];models=[]
        for kind in ('PASS','FAIL','REVIEW','ERROR'):
            rule=base.model_copy(update={'rule_id':kind});rules.append(rule)
            binding=Binding(condition_id='ok',operation='EQUALS',path='parties.seller.tax_id',expected='other' if kind=='FAIL' else seller)
            models.append(rf.model_for(rule,(binding,),review='ok' if kind=='REVIEW' else None))
        self.catalog=(RuleSet(version='mixed',families=tuple(RuleFamily(rule_id=r.rule_id,supported_from=r.effective_from,supported_to=r.effective_to,versions=(r,)) for r in rules)),*self.catalog[1:])
        self.package=ModelPackage(package_id='mixed-synthetic',version='1',models=tuple(models))
        def runner(model,context,policy):
            if model.rule_id=='ERROR':raise EngineFailure('ENGINE_TIMEOUT',True)
            return rf.native(model,context,policy)
        result=self.run_evaluation(runner=runner)
        self.assertEqual(result.report.aggregate.verdict,'FAIL')
        self.assertTrue(result.report.aggregate.review_required)
        self.assertEqual(result.report.aggregate.counts.errors,1)
        self.assertEqual(result.report.aggregate.coverage,'PARTIAL')
        self.assertTrue(any('lỗi xử lý' in t for t in result.report.explanation.notices))
        self.assertEqual(self.workflow.page(self.ctx,self.payer,result.evaluation_id,'attempts')['total'],5)

    def test_source_limitation_scoped_pass_explained(self):
        self.approved();base=self.catalog[0].families[0].versions[0]
        outside=base.model_copy(update={'rule_id':'NON_CASH','family':'PAYMENT_EVIDENCE'})
        self.catalog=(RuleSet(version='scoped',families=tuple(RuleFamily(rule_id=r.rule_id,supported_from=r.effective_from,supported_to=r.effective_to,versions=(r,)) for r in (base,outside))),*self.catalog[1:])
        self.package=self.package.model_copy(update={'models':(*self.package.models,rf.model_for(outside))})
        result=self.run_evaluation(runner=rf.native)
        self.assertEqual(result.report.aggregate.verdict,'PASS_WITHIN_SCOPE')
        self.assertEqual(result.report.aggregate.counts.out_of_scope,1)
        self.assertTrue(any('nguồn độc lập' in a for a in result.report.explanation.next_actions))

    def test_reports_immutable_and_schema_version_nine(self):
        result=self.run_evaluation()
        with self.workflow.ingestion.db() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],9)
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM evaluation_reports')
        payload=result.report.model_dump(mode='json');payload['explanation']['verdict']='FAIL'
        with self.assertRaises(ValidationError):EvaluationReport.model_validate(payload)

    def test_frontend_assets_and_new_api_openapi_available(self):
        for name in ('app.js','style.css','compliance.js','compliance.css'):
            self.assertEqual(self.client.get('/review-assets/'+name).status_code,200)
        paths=self.client.get('/openapi.json').json()['paths']
        self.assertIn('/v1/evaluations/{evaluation_id}/rule-results',paths)

    def test_contract_error_template_has_no_tax_conclusion_even_for_partial_rows(self):
        plan,inputs,package=rf.setup()
        result=rf.execute(plan,inputs,package,runner=rf.native)
        broken=rf.aggregate(plan,result.outcomes+result.outcomes,package)
        result=result.model_copy(update={'aggregate':broken})
        explanation,rows=render('evaluation-synthetic',plan,result,inputs,load_templates())
        self.assertIsNone(explanation.verdict)
        self.assertTrue(all(row.result is None and row.trace is None for row in rows))

    def test_missing_date_and_low_confidence_do_not_become_violations(self):
        result=self.run_evaluation()
        rows=self.workflow.artifact(self.ctx,self.payer,result.evaluation_id).rule_results
        self.assertTrue(any(row.rule_version is None or row.eligibility!='ELIGIBLE' for row in rows))
        self.assertFalse(any(row.result=='FAIL' for row in rows))
        self.assertTrue(any('Chưa' in row.explanation or 'Cần' in row.explanation for row in rows))


if __name__=='__main__':unittest.main()
