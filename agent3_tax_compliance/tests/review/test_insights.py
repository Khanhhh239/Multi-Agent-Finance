import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import test_review as fixtures
from src.review.insights import record_timing,timings,percentile

class InsightTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ReviewTests('test_idempotent_double_submit_and_key_conflict');self.f.setUp();self.addCleanup(self.f.doCleanups)
    def test_counts_bound_to_revision_are_not_accuracy(self):
        f=self.f;url=f'/v1/records/{f.record.record_id}/capture-insights?taxpayer_id={f.payer}'
        self.assertEqual(f.client.get(url).status_code,401)
        before=f.client.get(url,headers=f.headers);self.assertEqual(before.status_code,200,before.text)
        self.assertIsNone(before.json()['accuracy']);self.assertEqual(before.json()['record_revision'],1)
        f.correct();after=f.client.get(url,headers=f.headers).json()
        self.assertEqual(after['record_revision'],2);self.assertEqual(after['review_saves'],1);self.assertGreater(after['human_confirmed'],0)
        self.assertNotIn('1234567890',str(after))
        denied=f.client.get(url.replace('payer-a','outside'),headers=f.headers);self.assertEqual(denied.status_code,403)
    def test_percentiles_and_scope_and_bounded_storage(self):
        f=self.f
        for seconds in (1,2,3,4):record_timing(f.fixture.settings,f.ctx.tenant_id,f.payer,'region_ocr',seconds,seconds==1)
        record_timing(f.fixture.settings,'other',f.payer,'region_ocr',999,True)
        row=timings(f.fixture.settings,f.ctx,f.payer)[0]
        self.assertEqual(row['count'],4);self.assertEqual(row['p50_seconds'],2);self.assertEqual(row['p95_seconds'],4)
        self.assertEqual(row['first_request_count'],1);self.assertEqual(row['subsequent_count'],3)
        self.assertIsNone(percentile([],0.5))
        with self.assertRaises(ValueError):record_timing(f.fixture.settings,f.ctx.tenant_id,f.payer,'region_ocr',float('nan'),False)
    def test_http_save_records_stage_without_values_or_urls(self):
        f=self.f;command=f.command().model_dump(mode='json')
        result=f.client.post('/v1/corrections?taxpayer_id='+f.payer,json=command,headers={**f.headers,'Idempotency-Key':'measure-save'})
        self.assertEqual(result.status_code,200,result.text)
        rows=timings(f.fixture.settings,f.ctx,f.payer)
        self.assertTrue(any(r['stage']=='review_save' and r['count']==1 for r in rows))
