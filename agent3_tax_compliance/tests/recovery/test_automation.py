import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).parent))
import test_regions as region_fixtures
from src.recovery.automation import AutomationReview,AutoCommand
from src.recovery.policy import deduplicated_tail,diagnose,select_candidate,text_key
from src.review.contracts import ReviewError
from src.domain.field import FieldObject


class AutoRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.case=region_fixtures.RegionTests('test_reread_is_cached_candidate_with_original_and_transform');self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.f=self.case.f;self.calls=[];self.hook=None;self.fail=False
        self.record=self.f.record
        item=self.record.items[0];self.path='items.'+item.item_id+'.description'
        field=item.description.model_copy(update={'value':'Dịch vụ tháng) tháng)'})
        self.record=self.record.model_copy(update={'items':(item.model_copy(update={'description':field}),)})
        test=self
        class Region:
            client=test.case.reader
            def read(self,ctx,payer,rid,command):
                test.calls.append(command.field_path)
                if test.hook:test.hook()
                if test.fail:raise ReviewError('WORKER_TIMEOUT','test',503)
                return {'status':'CANDIDATE','suggested_value':'Dịch vụ tháng)','original_value':'Dịch vụ tháng) tháng)','recovery_id':'observed-one','observations':[]}
        self.service=AutomationReview(self.f.fixture.settings,Region())
        self.patch=patch.object(self.service,'inputs',side_effect=lambda *_:(self.record,self.f.artifact,self.case.normalized));self.patch.start();self.addCleanup(self.patch.stop)
    def run_auto(self,retry=False):return self.service.run(self.f.ctx,self.f.payer,self.f.record.record_id,AutoCommand(expected_record_revision=1,retry_failed=retry))

    def test_exact_suffix_repair_selected_but_record_not_changed(self):
        old=self.f.repo.base.record(self.f.ctx,self.f.payer,self.f.record.record_id)
        result=self.run_auto();entry=next(e for e in result['entries'] if e['field_path']==self.path)
        self.assertEqual(entry['selection']['decision'],'RECOMMENDED');self.assertTrue(result['review_required']);self.assertFalse(result['auto_confirmed'])
        self.assertEqual(self.f.repo.base.record(self.f.ctx,self.f.payer,self.f.record.record_id),old)
        again=self.run_auto();self.assertTrue(again['cache_hit']);self.assertEqual(again['run_id'],result['run_id']);self.assertEqual(len(self.calls),1)

    def test_changed_numbers_names_or_conflicts_never_auto_selected(self):
        field=self.record.items[0].description
        for value,codes in (('Dịch vụ 999 tháng)',['REPEATED_SUFFIX']),('Hàng khác',['REPEATED_SUFFIX']),('Dịch vụ tháng)',['REPEATED_SUFFIX','SOURCE_CONFLICT'])):
            result=select_candidate(field,{'issue_codes':codes},{'status':'CANDIDATE','suggested_value':value})
            self.assertEqual(result['decision'],'REVIEW');self.assertIsNone(result['selected_value'])
        self.assertIsNone(deduplicated_tail('100 100'));self.assertIsNone(deduplicated_tail('A A'))
        self.assertEqual(text_key('a\u0301  B'),'á b')

    def test_human_confirmed_values_are_never_scheduled_or_selected(self):
        item=self.record.items[0];field=item.description.model_copy(update={'confidence_basis':'HUMAN_CONFIRMED'})
        record=self.record.model_copy(update={'items':(item.model_copy(update={'description':field}),)})
        plan=diagnose(record,self.f.artifact,self.case.normalized)
        self.assertFalse(any(e['field_path']==self.path for e in plan['entries']))
        self.assertEqual(select_candidate(field,{'issue_codes':['REPEATED_SUFFIX']},{'status':'CANDIDATE','suggested_value':'Dịch vụ tháng)'})['reason'],'HUMAN_VALUE_PROTECTED')

    def test_failures_cached_explicit_retry_bounded_to_two_attempts(self):
        self.fail=True
        a=self.run_auto();self.assertTrue(a['errors']);self.assertFalse(a['recommended'])
        self.assertEqual(self.run_auto()['attempt'],1);self.assertEqual(len(self.calls),1)
        self.assertEqual(self.run_auto(True)['attempt'],2);self.assertEqual(len(self.calls),2)
        with self.assertRaises(ReviewError) as err:self.run_auto(True)
        self.assertEqual(err.exception.code,'AUTOMATION_BUDGET')

    def test_scope_and_stale_revision_rejected(self):
        for ctx in (self.f.ctx.model_copy(update={'permissions':frozenset({'READ'})}),self.f.ctx.model_copy(update={'tenant_id':'other'})):
            # Scope binding is enforced before an injected fixture input can bypass it.
            with self.assertRaises(PermissionError):self.service.run(ctx,'outside',self.f.record.record_id,AutoCommand(expected_record_revision=1))
        with self.assertRaises(ReviewError):self.service.run(self.f.ctx,self.f.payer,self.f.record.record_id,AutoCommand(expected_record_revision=2))
        self.assertFalse(self.calls)

    def test_active_durable_lease_prevents_duplicate_work(self):
        def hook():
            with self.assertRaises(ReviewError) as err:self.run_auto()
            self.assertEqual(err.exception.code,'AUTOMATION_BUSY')
        self.hook=hook;self.run_auto();self.assertEqual(len(self.calls),1)

    def test_expanded_recovery_uses_spare_crop_budget_and_preserves_primary(self):
        calls=[]
        def read(ctx,payer,rid,command):
            calls.append(command.reader)
            return {'status':'NEEDS_REVIEW' if command.reader=='primary' else 'CANDIDATE',
                'suggested_value':None if command.reader=='primary' else 'Dịch vụ tháng)',
                'original_value':'Dịch vụ tháng) tháng)','recovery_id':'comparison-test','observations':[]}
        self.service.region.comparison_runtime=lambda:'c'*64
        with patch.object(self.service.region,'read',side_effect=read):result=self.run_auto()
        entry=next(e for e in result['entries'] if e['field_path']==self.path)
        self.assertEqual(calls,['primary','expanded'])
        self.assertEqual(entry['primary_recovery']['status'],'NEEDS_REVIEW')
        self.assertEqual(entry['expanded']['status'],'CANDIDATE');self.assertFalse(result['auto_confirmed'])

    def test_stale_results_persist_but_are_not_returned_as_current(self):
        self.hook=self.f.correct
        with self.assertRaises(ReviewError) as err:self.run_auto()
        self.assertEqual(err.exception.code,'REVISION_CONFLICT')
        with closing(self.service.db()) as db:self.assertEqual(db.execute("SELECT status FROM recovery_runs").fetchone()[0],'STALE')

    def test_http_strict_contract_auth_and_read_only_inspection(self):
        path=f'/v1/records/{self.f.record.record_id}/automation-review?taxpayer_id={self.f.payer}'
        self.assertEqual(self.f.client.post(path,json={'expected_record_revision':1}).status_code,401)
        self.assertEqual(self.f.client.post(path,headers=self.f.headers,json={'expected_record_revision':True}).status_code,422)
        response=self.f.client.get(path,headers=self.f.headers);self.assertEqual(response.status_code,200)
        self.assertIn('user_guide',response.json());self.assertFalse(self.calls)

    def test_total_field_and_crop_budgets_include_deferred_items(self):
        # Each existing eligible field gets the same valid two-line source.
        field=self.record.items[0].description
        seller=self.record.parties.seller.model_copy(update={'name':field,'address':field})
        record=self.record.model_copy(update={'parties':self.record.parties.model_copy(update={'seller':seller})})
        plan=diagnose(record,self.f.artifact,self.case.normalized)
        self.assertLessEqual(plan['scheduled_fields'],2);self.assertLessEqual(plan['scheduled_crops'],4)
        self.assertTrue(any(e['state']=='DEFERRED' for e in plan['entries']))


if __name__=='__main__':unittest.main()
