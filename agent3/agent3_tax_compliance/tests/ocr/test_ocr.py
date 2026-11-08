import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from datetime import date

import pymupdf
from pydantic import ValidationError
from fastapi.testclient import TestClient
from src.app import create_app
from src.config import Settings
from src.domain.taxpayer import AccessContext,TaxpayerMaster
from src.ingestion.models import AuthGrant,DocumentArtifact
from src.ingestion.service import IngestionService
from src.ingestion.upload import StagedUpload
from src.ingestion.sandbox import run_bounded
from src.ingestion.models import IngestionError
from src.adapters.ocr.protocol import *
from src.adapters.ocr.bridge import OCRBridge,request_for,config_key,STAMP
from src.adapters.ocr.normalizer import normalize
from src.adapters.ocr.layout_merge import merge
from src.adapters.ocr.worker_client import WorkerClient

ROOT=Path(__file__).resolve().parents[2]
CTX=AccessContext(actor_id='ocr-test',tenant_id='tenant-ocr',taxpayer_ids=frozenset({'payer-ocr'}),permissions=frozenset({'ADMIN'}))
TOKEN='ocr-test-only-not-production'


def response(req,text='TOTAL: 8.000.000',polygon=((5,5),(90,5),(90,20),(5,20))):
    return OCRBridgeResponse(**STAMP,**{name:getattr(req,name) for name in
        ('request_id','source_id','document_id','page_id','page_index','image_hash','model_config_version','runtime_sha256')},
        engine_versions={'tesseract':'test'},result=BenchmarkResult(schema_version='1.1',run_id=req.request_id,
            model_id=req.model_id,output_mode='boxes_and_text',image_id=Path(req.image_path).name,
            image_width=req.image_width,image_height=req.image_height,load_time_ms=0,inference_time_ms=1,
            document_text_raw=text,detections=(Detection(polygon=polygon,text_raw=text,confidence=.81),)))


class FakeClient:
    def __init__(self,fail_page=None): self.calls=0;self.fail_page=fail_page
    def inventory(self): return {'runtime_sha256':'a'*64}
    def run_batch(self,requests,config):
        self.calls+=1
        if requests[0].page_index==self.fail_page: raise OCRError('WORKER_TIMEOUT','test timeout',True)
        return [response(req) for req in requests]


class OCRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.ingestion.pdf_reader import read_image
        cls.directory=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.directory.cleanup)
        image=ROOT/'tests/fixtures/ocr/functional_set_v1/syn-00-image.png'
        cls.page=read_image(image,Path(cls.directory.name),{'source_id':'source-smoke','document_id':'doc-smoke',
                           'input_sha256':hashlib.sha256(image.read_bytes()).hexdigest()},Settings())[0]

    def setUp(self):
        self.config=OCRConfig()
        self.req=request_for(self.page,Path('irrelevant.png'),self.config,'a'*64)
        self.res=response(self.req)

    def test_wrong_page_hash_and_version_rejected(self):
        for name,value in [('page_id','wrong'),('image_hash','b'*64),('runtime_sha256','b'*64),('request_id','wrong')]:
            with self.subTest(name=name),self.assertRaises(OCRError): correlate(self.req,self.res.model_copy(update={name:value}))
        payload=json.loads(self.res.model_dump_json());payload['protocol_version']='2'
        with self.assertRaises(ValidationError): OCRBridgeResponse.model_validate(payload)

    def test_benchmark_version_and_nan_score_rejected(self):
        for score in (float('nan'),float('inf'),-.1,1.01):
            with self.assertRaises(ValidationError): Detection(polygon=((0,0),(1,0),(1,1)),text_raw='x',confidence=score)
        with self.assertRaises(ValidationError): Detection(polygon=((0,0),(float('nan'),0),(1,1)),text_raw='x')
        raw=json.loads(self.res.model_dump_json());raw['result']['schema_version']='1.0'
        with self.assertRaises(ValidationError): OCRBridgeResponse.model_validate(raw)

    def test_outside_zero_area_polygon_rejected(self):
        for polygon in (((-1,0),(2,0),(2,2)),((1,1),(1,2),(1,3)),((1,1),(2,2),(3,3))):
            with self.assertRaises(OCRError): normalize(self.page,response(self.req,polygon=polygon))

    def test_full_page_text_has_no_invented_geometry(self):
        res=self.res.model_copy(update={'result':self.res.result.model_copy(update={'detections':()})})
        blocks=normalize(self.page,res)
        self.assertEqual(blocks[0].geometry_status,'UNAVAILABLE');self.assertIsNone(blocks[0].evidence)

    def test_scores_not_calibrated_ids_stable_and_reverse_transform_kept(self):
        first=normalize(self.page,self.res)[0]
        req=self.req.model_copy(update={'request_id':'another-request'})
        second=normalize(self.page,response(req))[0]
        self.assertEqual(first.block_id,second.block_id)
        self.assertEqual(first.origins[0].score_semantics,'ENGINE_HEURISTIC_NOT_CALIBRATED')
        self.assertEqual(first.evidence.transform_id,self.page.geometry.transform_id)

    def test_overlay_money_dedup_and_conflicting_values_survive(self):
        from src.ingestion.models import TextBlock
        first=normalize(self.page,self.res)[0]
        native=TextBlock(block_id='native',text=first.text_raw,source_order=0,reading_order=0,
                         original_bbox=(0,0,1,1),evidence=first.evidence.model_copy(update={'block_id':'native'}))
        page=self.page.model_copy(update={'native_blocks':(native,)})
        merged=merge(page,[first]);self.assertEqual(len(merged),1);self.assertEqual(len(merged[0].origins),2)
        different=normalize(self.page,response(self.req,'TOTAL: 3.000.000'))[0]
        merged=merge(page,[different]);self.assertEqual(len(merged),2)
        self.assertTrue(all(b.conflict_with for b in merged))

    def test_disjoint_equal_money_kept(self):
        first=normalize(self.page,self.res)[0]
        second=normalize(self.page,response(self.req,polygon=((100,50),(200,50),(200,70),(100,70))))[0]
        self.assertEqual(len(merge(self.page,[first,second])),2)

    def test_native_split_spans_match_one_ocr_row(self):
        from src.ingestion.models import TextBlock
        block=normalize(self.page,self.res)[0];x0,y0,x1,y1=block.evidence.bbox
        mid=(x0+x1)/2
        native=[]
        for index,(text,box) in enumerate([('TOTAL:',(x0,y0,mid,y1)),('8.000.000',(mid,y0,x1,y1))]):
            native.append(TextBlock(block_id=f'native-{index}',text=text,source_order=index,reading_order=index,
                original_bbox=(0,0,1,1),evidence=block.evidence.model_copy(update={'bbox':box,'block_id':f'native-{index}'})))
        blocks=merge(self.page.model_copy(update={'native_blocks':tuple(native)}),[block])
        self.assertEqual(len(blocks),1);self.assertEqual(len(blocks[0].origins),3)

    def test_two_column_and_table_reading_order(self):
        entries=[]
        for text,box in [('right-top',(.6,.1,.8,.12)),('left-bottom',(.1,.5,.3,.52)),
                         ('left-top',(.1,.1,.3,.12)),('right-bottom',(.6,.5,.8,.52))]:
            w,h=self.page.render_width,self.page.render_height
            x0,y0,x1,y1=box
            entries.extend(normalize(self.page,response(self.req,text,((x0*w,y0*h),(x1*w,y0*h),(x1*w,y1*h),(x0*w,y1*h)))))
        columns=merge(self.page.model_copy(update={'table_structure_present':False}),entries)
        self.assertEqual([b.text_raw for b in columns],['left-top','left-bottom','right-top','right-bottom'])
        table=merge(self.page.model_copy(update={'table_structure_present':True}),entries)
        self.assertEqual([b.text_raw for b in table],['left-top','right-top','left-bottom','right-bottom'])

    def test_timeout_retry_is_bounded_and_crash_not_retried(self):
        client=WorkerClient();client._runtime={'runtime_sha256':'a'*64,'engine_versions':{}}
        for code,calls in [('WORKER_TIMEOUT',2),('WORKER_RESOURCE_ERROR',1)]:
            error=IngestionError(code,'injected failure')
            with patch.object(client,'verify_runtime'),patch('src.adapters.ocr.worker_client.run_bounded',side_effect=error) as invoke:
                with self.assertRaises(OCRError): client.run_batch([self.req],self.config)
                self.assertEqual(invoke.call_count,calls)

    def test_timeout_retains_stage_progress_without_returning_partial_text(self):
        client=WorkerClient();client._runtime={'runtime_sha256':'a'*64,'engine_versions':{}}
        def timeout(command,wire,*args,**kwargs):
            payload=json.loads(wire)
            Path(payload['progress_path']).write_text(json.dumps({
                'stage':'RECOGNITION_CROP','completed_regions':3,'total_regions':74,
                'elapsed_ms':120000,'detection_ms':60000}),encoding='utf-8')
            raise IngestionError('WORKER_TIMEOUT','Synthetic deadline',retryable=True)
        with patch.object(client,'verify_runtime'),patch('src.adapters.ocr.worker_client.run_bounded',side_effect=timeout):
            with self.assertRaises(OCRError) as caught:client.run_batch([self.req],self.config)
        self.assertEqual(caught.exception.issue.code,'WORKER_TIMEOUT')
        self.assertEqual(len(client.metrics_history),self.config.max_attempts)
        self.assertEqual(client.metrics_history[-1]['progress']['completed_regions'],3)

    def test_retry_does_not_reuse_previous_attempt_progress(self):
        client=WorkerClient();client._runtime={'runtime_sha256':'a'*64,'engine_versions':{}}
        calls=[]
        def timeout(command,wire,*args,**kwargs):
            path=Path(json.loads(wire)['progress_path']);calls.append(1)
            self.assertFalse(path.exists())
            if len(calls)==1:path.write_text('{"stage":"DETECTION"}',encoding='utf-8')
            raise IngestionError('WORKER_TIMEOUT','Synthetic deadline',retryable=True)
        with patch.object(client,'verify_runtime'),patch('src.adapters.ocr.worker_client.run_bounded',side_effect=timeout):
            with self.assertRaises(OCRError):client.run_batch([self.req],self.config)
        self.assertNotIn('progress',client.metrics_history[-1])

    def test_malformed_diagnostics_do_not_hide_worker_failure(self):
        client=WorkerClient();client._runtime={'runtime_sha256':'a'*64,'engine_versions':{}}
        def crash(command,wire,*args,**kwargs):
            Path(json.loads(wire)['progress_path']).write_text('not-json',encoding='utf-8')
            raise IngestionError('WORKER_RESOURCE_ERROR','Synthetic crash')
        with patch.object(client,'verify_runtime'),patch('src.adapters.ocr.worker_client.run_bounded',side_effect=crash):
            with self.assertRaises(OCRError) as caught:client.run_batch([self.req],self.config)
        self.assertEqual(caught.exception.issue.code,'WORKER_CRASH')
        self.assertNotIn('progress',client.metrics_history[-1])

    def test_output_limit_and_wrong_page_rejected_without_retry(self):
        client=WorkerClient();client._runtime={'runtime_sha256':'a'*64,'engine_versions':{}}
        for mode in ('too-large','wrong-page'):
            def emit(command,wire,*args,**kwargs):
                payload=json.loads(wire);path=Path(payload['output'])
                if mode=='too-large': path.write_bytes(b'x'*(self.config.max_output_bytes+1))
                else: path.write_text(self.res.model_copy(update={'page_id':'wrong'}).model_dump_json()+'\n',encoding='utf-8')
                return {}
            with patch.object(client,'verify_runtime'),patch('src.adapters.ocr.worker_client.run_bounded',side_effect=emit) as invoke:
                with self.assertRaises(OCRError) as caught: client.run_batch([self.req],self.config)
                self.assertEqual(caught.exception.issue.code,'OUTPUT_LIMIT' if mode=='too-large' else 'PROTOCOL_ERROR')
                self.assertEqual(invoke.call_count,1)

    def test_changed_runtime_files_are_not_used(self):
        with tempfile.TemporaryDirectory() as directory:
            client=WorkerClient(directory);path=Path(directory)/'pinned.txt';path.write_bytes(b'changed')
            client._runtime={'files':{'pinned.txt':'a'*64}}
            with self.assertRaises(OCRError) as caught: client.verify_runtime()
            self.assertEqual(caught.exception.issue.code,'MODEL_UNAVAILABLE')

    def test_config_and_runtime_cache_invalidation(self):
        key=config_key(self.config,'a'*64)
        for config,runtime in [(OCRConfig(psm=6),'a'*64),(OCRConfig(version='v2'),'a'*64),(self.config,'b'*64)]:
            self.assertNotEqual(key,config_key(config,runtime))

    def test_missing_runtime_explicitly_unavailable(self):
        with tempfile.TemporaryDirectory() as directory,self.assertRaises(OCRError) as caught:
            WorkerClient(directory).inventory()
        self.assertEqual(caught.exception.issue.code,'MODEL_UNAVAILABLE')

    def test_real_worker_smoke_and_no_package_collision(self):
        client=WorkerClient();runtime=client.inventory()
        image=Path(self.directory.name)/'page-0.png'
        # Fixture PNG is exactly the canonical ingestion image bytes.
        self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(),self.page.render_sha256)
        req=request_for(self.page,image,self.config,runtime['runtime_sha256'])
        res=client.run_batch([req],self.config)[0]
        self.assertGreater(len(normalize(self.page,res)),5)
        self.assertEqual(res.engine_versions['pytesseract'],'0.3.13')
        self.assertNotIn('src.adapters.tesseract_adapter',sys.modules)

    def test_real_worker_timeout_kills_tree(self):
        client=WorkerClient();client.inventory()
        with self.assertRaises(IngestionError) as caught:
            run_bounded([str(client.python),'-c','import sys,time;sys.stdin.read();time.sleep(10)'],b'{}',.2,128,client.root,max_processes=3)
        self.assertEqual(caught.exception.issue.code,'WORKER_TIMEOUT')


class OCRIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.directory=Path(self.temp.name)
        grant=AuthGrant(token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),actor_id=CTX.actor_id,
                       tenant_id=CTX.tenant_id,taxpayer_ids=CTX.taxpayer_ids,permissions=CTX.permissions)
        self.settings=Settings(database_path=self.directory/'capture.sqlite3',staging_directory=self.directory/'staging',auth_grants=(grant,))
        self.service=IngestionService(self.settings);repo=self.service.repository
        repo.base.initialize()
        repo.base.add_taxpayer(CTX,TaxpayerMaster(config_version='test',creator='test',stage='test',tenant_id=CTX.tenant_id,
            taxpayer_id='payer-ocr',revision=1,tax_code='0000000000',effective_from=date(2026,1,1),provenance_reference='synthetic'))
        with pymupdf.open() as pdf:
            for _ in range(3): pdf.new_page(width=300,height=400)
            raw=pdf.tobytes()
        with StagedUpload(self.settings) as staged:
            staged.write(raw)
            view=self.service.accept_staged(CTX,'payer-ocr',1,'ocr-test',staged,'application/pdf','test.pdf')
        self.identifier=view.ingestion_id
        self.assertEqual(self.service.work_one(CTX,'payer-ocr',self.identifier).status,'SUCCEEDED')

    def tearDown(self): self.temp.cleanup()

    def test_three_page_timeout_is_partial_and_evidence_retained(self):
        client=FakeClient(fail_page=1);bridge=OCRBridge(self.settings,client=client)
        job=bridge.work_one(CTX,'payer-ocr',self.identifier)
        self.assertEqual(job['status'],'PARTIAL')
        self.assertEqual([p.status for p in job['result'].pages],['COMPLETE','FAILED','COMPLETE'])
        self.assertEqual(job['result'].pages[1].issue.code,'WORKER_TIMEOUT')
        self.assertTrue(job['result'].pages[2].blocks[0].evidence)

    def test_restart_idempotent_result_and_scoped_api(self):
        client=FakeClient();bridge=OCRBridge(self.settings,client=client)
        first=bridge.work_one(CTX,'payer-ocr',self.identifier)
        second=OCRBridge(self.settings,client=client).work_one(CTX,'payer-ocr',self.identifier)
        self.assertEqual(client.calls,3);self.assertEqual(first['result'],second['result'])
        key=config_key(bridge.config,'a'*64)
        app=TestClient(create_app(self.settings));url=f'/v1/ingestions/{self.identifier}/extractions/{key}?taxpayer_id=payer-ocr'
        self.assertEqual(app.get(url).status_code,401)
        self.assertEqual(app.get(url,headers={'Authorization':'Bearer '+TOKEN}).status_code,200)
        denied=CTX.model_copy(update={'tenant_id':'another'})
        self.assertIsNone(bridge.repository.get(denied,'payer-ocr',self.identifier,key))
        self.assertIsNone(bridge.repository.cached(denied,'payer-ocr','a'*64))

    def test_stale_lease_fencing_and_recovery_budget(self):
        repo=OCRBridge(self.settings,client=FakeClient()).repository
        first=repo.claim(CTX,'payer-ocr',self.identifier,'key',-1,2)
        second=repo.claim(CTX,'payer-ocr',self.identifier,'key',-1,2)
        self.assertNotEqual(first,second)
        with self.assertRaises(OCRError):
            repo.finish(CTX,'payer-ocr',self.identifier,'key',first,issue=OCRError('OCR_FAILED','test').issue)
        self.assertIsNone(repo.claim(CTX,'payer-ocr',self.identifier,'key',30,2))
        self.assertEqual(repo.get(CTX,'payer-ocr',self.identifier,'key')['status'],'FAILED')

    def test_audit_failure_rolls_back_result(self):
        client=FakeClient();bridge=OCRBridge(self.settings,client=client)
        original=bridge.repository.ingestion._event
        def fail(db,ctx,payer,identifier,kind,sha,details=None):
            if kind=='OCR_FINISHED': raise RuntimeError('audit storage failed')
            return original(db,ctx,payer,identifier,kind,sha,details)
        with patch.object(bridge.repository.ingestion,'_event',side_effect=fail),self.assertRaises(RuntimeError):
            bridge.work_one(CTX,'payer-ocr',self.identifier)
        job=bridge.repository.get(CTX,'payer-ocr',self.identifier,config_key(bridge.config,'a'*64))
        self.assertIsNone(job['result']);self.assertEqual(job['status'],'PROCESSING')

    def test_cross_process_claim_is_serialized(self):
        repo=OCRBridge(self.settings,client=FakeClient()).repository
        first=repo.claim(CTX,'payer-ocr',self.identifier,'config-one',30,2)
        self.assertIsNotNone(first)
        # A separate repository/connection cannot start a concurrent config.
        other=OCRBridge(self.settings,client=FakeClient()).repository
        self.assertIsNone(other.claim(CTX,'payer-ocr',self.identifier,'config-two',30,2))
        self.assertEqual(other.get(CTX,'payer-ocr',self.identifier,'config-two')['status'],'QUEUED')

    def test_committed_ocr_result_and_cache_are_immutable(self):
        import sqlite3
        bridge=OCRBridge(self.settings,client=FakeClient());bridge.work_one(CTX,'payer-ocr',self.identifier)
        with self.assertRaises(sqlite3.IntegrityError),bridge.repository.ingestion.db() as db:
            db.execute("UPDATE ocr_jobs SET payload='{}'")
        with self.assertRaises(sqlite3.IntegrityError),bridge.repository.ingestion.db() as db:
            db.execute("DELETE FROM ocr_page_cache")


if __name__=='__main__': unittest.main()
