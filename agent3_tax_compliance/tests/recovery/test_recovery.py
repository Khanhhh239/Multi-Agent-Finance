import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'review'))
import test_review as fixtures
from src.recovery.api import ReextractCommand,reextract
from src.review.contracts import ReviewError


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ReviewTests('test_record_summary_and_job_link_survive_new_browser_session')
        self.f.setUp();self.addCleanup(self.f.doCleanups)

    def run_recovery(self,revision=1,ctx=None):
        return reextract(self.f.fixture.settings,ctx or self.f.ctx,self.f.payer,self.f.record.record_id,
                         ReextractCommand(expected_record_revision=revision,reason='Compared retained source'))

    def test_same_implementation_no_change_no_new_record(self):
        before=self.f.count('records');result=self.run_recovery()
        self.assertEqual(result['status'],'NO_CHANGE')
        self.assertEqual(self.f.count('records'),before)

    def test_new_extractor_preserves_review_and_reuses_recovery_record(self):
        self.f.correct();old=self.f.repo.base.record(self.f.ctx,self.f.payer,self.f.record.record_id)
        before=self.f.count('records')
        with patch('src.extraction.repository.implementation_sha',return_value='f'*64):
            first=self.run_recovery(2);second=self.run_recovery(2)
        self.assertEqual(first['record_id'],second['record_id'])
        self.assertNotEqual(first['record_id'],old.record_id)
        self.assertEqual(self.f.count('records'),before+1)
        self.assertEqual(self.f.repo.base.record(self.f.ctx,self.f.payer,old.record_id),old)
        new=self.f.repo.view(self.f.ctx,self.f.payer,first['record_id'])
        self.assertEqual(new['record']['revision'],1)
        self.assertNotEqual(new['record']['parties']['seller']['tax_id']['confidence_basis'],'HUMAN_CONFIRMED')
        self.assertTrue(self.f.repo.page(self.f.ctx,self.f.payer,'tasks',record_id=first['record_id'])['items'])

    def test_stale_revision_rejected_before_allocating(self):
        self.f.correct();before=self.f.count('records')
        with self.assertRaises(ReviewError) as caught:self.run_recovery()
        self.assertEqual(caught.exception.code,'REVISION_CONFLICT')
        self.assertEqual(self.f.count('records'),before)

    def test_scope_and_write_permission_enforced(self):
        for ctx in (self.f.ctx.model_copy(update={'tenant_id':'another'}),
                    self.f.ctx.model_copy(update={'permissions':frozenset({'READ'})})):
            with self.assertRaises((KeyError,PermissionError)):self.run_recovery(ctx=ctx)

    def test_concurrent_recovery_allocates_once(self):
        before=self.f.count('records')
        with patch('src.extraction.repository.implementation_sha',return_value='e'*64),ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.run_recovery(),range(2)))
        self.assertEqual(results[0]['record_id'],results[1]['record_id'])
        self.assertEqual(self.f.count('records'),before+1)

    def test_http_auth_scope_validation_and_recovery(self):
        path=f'/v1/records/{self.f.record.record_id}/reextract?taxpayer_id={self.f.payer}'
        command={'expected_record_revision':1,'reason':'Recover retained OCR'}
        self.assertEqual(self.f.client.post(path,json=command).status_code,401)
        self.assertEqual(self.f.client.post(path.replace(self.f.payer,'other'),headers=self.f.headers,json=command).status_code,403)
        self.assertEqual(self.f.client.post(path,headers=self.f.headers,json={**command,'expected_record_revision':True}).status_code,422)
        self.assertEqual(self.f.client.post(path,headers=self.f.headers,json=command).json()['status'],'NO_CHANGE')

