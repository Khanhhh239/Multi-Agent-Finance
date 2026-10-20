import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'review'))
import test_review as fixtures
from src.recovery.regions import RegionRecovery,RegionCommand,crop_box,plan_regions,_SLOT
from src.adapters.ocr.protocol import OCRBridgeResponse,BenchmarkResult,OCRError
from src.review.contracts import ReviewError


class Reader:
    def __init__(self,text='New observed text'):
        self.text=text;self.calls=0;self.requests=[];self.hook=None
    def inventory(self):return {'runtime_sha256':'e'*64}
    def run_batch(self,requests,config,**kwargs):
        self.calls+=1;self.requests=requests
        if self.hook:self.hook()
        return [OCRBridgeResponse(config_version=config.version,creator='test',stage='ocr',
            **{k:getattr(r,k) for k in ('request_id','source_id','document_id','page_id','page_index','image_hash','model_config_version','runtime_sha256')},
            engine_versions={'test':'1'},result=BenchmarkResult(schema_version='1.1',run_id=r.request_id,model_id=r.model_id,
                output_mode='full_page_text',image_id=Path(r.image_path).name,image_width=r.image_width,image_height=r.image_height,
                load_time_ms=0,inference_time_ms=1,document_text_raw=self.text(r) if callable(self.text) else self.text)) for r in requests]


class RegionTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ReviewTests('test_record_summary_and_job_link_survive_new_browser_session');self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.reader=Reader();self.service=RegionRecovery(self.f.fixture.settings,self.reader)
        # Fixture normalized OCR uses a placeholder image hash. Replace only the
        # mock boundary with the actual retained render hash, never runtime data.
        self.artifact=self.f.artifact
        normalized=self.f.repo.extraction.ocr.get(self.f.ctx,self.f.payer,self.artifact.ingestion_id,self.f.fixture.key)['result']
        from src.persistence.repository import digest
        raw=self.f.repo.ingestion.render(self.f.ctx,self.f.payer,self.artifact.ingestion_id,0)
        normalized=normalized.model_copy(update={'pages':tuple(p.model_copy(update={'image_hash':digest(raw)}) for p in normalized.pages)})
        self.normalized=normalized
        self.patch=patch.object(self.service.repo.extraction.ocr,'get',return_value={'result':normalized});self.patch.start();self.addCleanup(self.patch.stop)
        self.command=RegionCommand(expected_record_revision=1,field_path='items.'+self.f.record.items[0].item_id+'.description')

    def read(self,command=None,ctx=None):return self.service.read(ctx or self.f.ctx,self.f.payer,self.f.record.record_id,command or self.command)

    def test_reread_is_cached_candidate_with_original_and_transform(self):
        before=self.f.repo.base.record(self.f.ctx,self.f.payer,self.f.record.record_id)
        result=self.read();again=self.read()
        self.assertEqual(result['status'],'CANDIDATE');self.assertTrue(result['review_required'])
        self.assertEqual(result['suggested_value'],' '.join(['New observed text']*len(result['observations'])));self.assertEqual(result['original_value'],before.items[0].description.value)
        self.assertEqual(self.reader.calls,1);self.assertTrue(again['cache_hit'])
        self.assertEqual(result['recovery_id'],again['recovery_id'])
        self.assertTrue(result['observations'][0]['evidence']['transform_id'])
        self.assertEqual(self.f.repo.base.record(self.f.ctx,self.f.payer,self.f.record.record_id),before)
        self.assertEqual(self.f.repo.extraction.get(self.f.ctx,self.f.payer,self.artifact.artifact_id),self.artifact)

    def test_expanded_crop_has_distinct_cache_scale_and_original_evidence(self):
        primary=self.read();expanded=self.read(self.command.model_copy(update={'reader':'expanded'}))
        self.assertEqual(expanded['reader'],'expanded');self.assertNotEqual(primary['recovery_id'],expanded['recovery_id'])
        self.assertEqual(primary['observations'][0]['evidence'],expanded['observations'][0]['evidence'])
        self.assertEqual(expanded['observations'][0]['resize_scale'],2)
        self.assertTrue(all(r.image_width>0 and r.image_height>0 for r in self.reader.requests))
        self.assertTrue(self.read(self.command.model_copy(update={'reader':'expanded'}))['cache_hit'])
        self.assertEqual(self.reader.calls,2)

    def test_scope_readonly_stale_and_unsupported_do_not_call_model(self):
        for context in (self.f.ctx.model_copy(update={'tenant_id':'other'}),self.f.ctx.model_copy(update={'permissions':frozenset({'READ'})})):
            with self.assertRaises((KeyError,PermissionError)):self.read(ctx=context)
        for command,code in ((self.command.model_copy(update={'expected_record_revision':2}),'REVISION_CONFLICT'),
                             (self.command.model_copy(update={'field_path':'derived.counterparty'}),'REGION_UNSUPPORTED'),
                             (self.command.model_copy(update={'field_path':'items.nonexistent.description'}),'INVALID_FIELD')):
            with self.assertRaises(ReviewError) as err:self.read(command)
            self.assertEqual(err.exception.code,code)
        self.assertEqual(self.reader.calls,0)

    def test_blank_and_partial_recognition_abstain(self):
        self.reader.text=' '
        result=self.read();self.assertEqual(result['status'],'NEEDS_REVIEW');self.assertIsNone(result['suggested_value'])

    def test_typed_rereads_parse_canonical_values_and_never_mutate_cfr(self):
        original=self.f.repo.base.record(self.f.ctx,self.f.payer,self.f.record.record_id)
        for path,label,value,want in [('invoice.issue_date','Ngày lập:','30/06/2025','2025-06-30'),
            ('totals.gross','Tổng thanh toán:','9007199254740993','9007199254740993'),
            ('parties.seller.tax_id','MST người bán:','0312662961-002','0312662961002')]:
            self.reader.text=lambda request,lab=label,val=value: lab if Path(request.image_path).name=='line-0.png' else val
            result=self.read(RegionCommand(expected_record_revision=1,field_path=path))
            self.assertEqual(result['status'],'CANDIDATE');self.assertEqual(result['parse_status'],'VALID')
            self.assertEqual(result['suggested_value'],want);self.assertEqual(result['value_format'],'CANONICAL')
            self.assertEqual(self.f.repo.base.record(self.f.ctx,self.f.payer,self.f.record.record_id),original)

    def test_bad_typed_reread_keeps_observation_but_offers_no_value(self):
        self.reader.text=lambda request: 'Ngày lập:' if Path(request.image_path).name=='line-0.png' else '31/02/2025'
        result=self.read(RegionCommand(expected_record_revision=1,field_path='invoice.issue_date'))
        self.assertEqual(result['status'],'NEEDS_REVIEW');self.assertEqual(result['parse_status'],'REJECTED')
        self.assertIsNone(result['suggested_value']);self.assertIn('31/02/2025',[o['text'] for o in result['observations']])

    def test_comparison_is_separately_pinned_and_cannot_choose_arbitrary_model(self):
        primary=self.read()
        with patch('src.recovery.regions.WorkerClient',return_value=self.reader):
            result=self.read(self.command.model_copy(update={'reader':'comparison'}))
            again=self.read(self.command.model_copy(update={'reader':'comparison'}))
        self.assertEqual(result['model_id'],'vietocr_region_wide');self.assertEqual(result['reader'],'comparison')
        self.assertNotEqual(result['recovery_id'],primary['recovery_id']);self.assertTrue(again['cache_hit'])
        self.assertTrue(all(r.model_id=='vietocr_region_wide' for r in self.reader.requests))
        with self.assertRaises(ValidationError):RegionCommand(expected_record_revision=1,field_path=self.command.field_path,reader='arbitrary')

    def test_cache_commit_race_returns_persisted_winner_not_unstored_id(self):
        winner=self.read();self.reader.text='Losing concurrent observation'
        # Simulate a cache miss racing another app process's completed INSERT.
        with patch.object(self.service,'cached',return_value=None):loser=self.read()
        self.assertEqual(loser['recovery_id'],winner['recovery_id'])
        self.assertEqual(loser['suggested_value'],winner['suggested_value'])
        self.assertTrue(loser['cache_hit'])

    def test_failures_do_not_cache_or_modify_record(self):
        with patch.object(self.reader,'run_batch',side_effect=OCRError('WORKER_TIMEOUT','test',True)):
            with self.assertRaises(ReviewError) as err:self.read()
            self.assertEqual(err.exception.status,503)
        self.assertEqual(self.read()['status'],'CANDIDATE')
        self.assertEqual(self.f.repo.base.record(self.f.ctx,self.f.payer,self.f.record.record_id).revision,1)

    def test_revision_change_while_model_runs_rejects_output(self):
        self.reader.hook=self.f.correct
        with self.assertRaises(ReviewError) as err:self.read()
        self.assertEqual(err.exception.code,'REVISION_CONFLICT')
        with self.service.db() as db:self.assertEqual(db.execute('select count(*) from region_reads').fetchone()[0],0)

    def test_busy_rejects_without_queueing(self):
        _SLOT.acquire()
        try:
            with self.assertRaises(ReviewError) as err:self.read()
            self.assertEqual(err.exception.status,429);self.assertEqual(self.reader.calls,0)
        finally:_SLOT.release()

    def test_crop_clips_edges_and_covers_fractional_pixels(self):
        self.assertEqual(crop_box((0,0,1,1),100,200),(0,0,100,200))
        self.assertEqual(crop_box((.101,.201,.299,.309),100,100),(9,19,31,32))

    def test_missing_evidence_and_large_blocks_abstain(self):
        record=self.f.record
        with self.assertRaises(ReviewError) as err:plan_regions(record,self.artifact,self.normalized,'parties.seller.address')
        self.assertEqual(err.exception.code,'REGION_NO_EVIDENCE')
        refs=record.items[0].description.provenance.evidence
        p=self.normalized.pages[0];b=next(b for b in p.blocks if b.block_id==refs[0].block_id)
        big=b.model_copy(update={'evidence':b.evidence.model_copy(update={'bbox':(0,0,1,1)})})
        norm=self.normalized.model_copy(update={'pages':(p.model_copy(update={'blocks':tuple(big if v.block_id==b.block_id else v for v in p.blocks)}),)})
        with self.assertRaises(ReviewError) as err:plan_regions(record,self.artifact,norm,self.command.field_path)
        self.assertEqual(err.exception.code,'REGION_NOT_LINE')

    def test_http_validates_auth_strict_revision_and_profile_cannot_be_injected(self):
        path=f'/v1/records/{self.f.record.record_id}/reread-region?taxpayer_id={self.f.payer}'
        body=self.command.model_dump()
        self.assertEqual(self.f.client.post(path,json=body).status_code,401)
        for extra in ({'expected_record_revision':True},{'model_id':'evil'},{'bbox':[0,0,1,1]}):
            self.assertEqual(self.f.client.post(path,json={**body,**extra},headers=self.f.headers).status_code,422)

    def test_response_mismatch_and_page_integrity_reject(self):
        with patch.object(self.reader,'run_batch',return_value=[]):
            with self.assertRaises(ValueError):self.read()
        p=self.normalized.pages[0]
        with patch.object(self.service.repo.extraction.ocr,'get',return_value={'result':self.normalized.model_copy(update={'pages':(p.model_copy(update={'image_hash':'f'*64}),)})}):
            with self.assertRaises(ValueError):self.read()
        self.assertEqual(self.reader.calls,0)


if __name__=='__main__':unittest.main()
