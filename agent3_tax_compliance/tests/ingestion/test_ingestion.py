import concurrent.futures
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from src.app import create_app
from src.config import PROJECT, Settings
from src.domain.taxpayer import AccessContext, TaxpayerMaster
from src.ingestion.detector import detect
from src.ingestion.models import AuthGrant, IngestionError, RoutePolicy
from src.ingestion.preprocess import apply, bbox, compose, crop_transform, deskew_transform, exif_transform, inverse
from src.ingestion.sandbox import run_bounded
from src.ingestion.service import IngestionService
from src.ingestion.upload import StagedUpload, cleanup_staging
from fixtures import image_bytes, pdf_bytes

TOKEN='test-only-credential-not-for-deployment'
CTX=AccessContext(actor_id='fixture-admin',tenant_id='tenant-a',taxpayer_ids=frozenset({'payer-a','payer-b'}),permissions=frozenset({'ADMIN'}))


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.directory=Path(self.temp.name)
        grant=AuthGrant(token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),actor_id=CTX.actor_id,
                        tenant_id=CTX.tenant_id,taxpayer_ids=CTX.taxpayer_ids,permissions=CTX.permissions)
        self.settings=Settings(database_path=self.directory/'capture.sqlite3',staging_directory=self.directory/'staging',
                               render_dpi=72,auth_grants=(grant,))
        self.service=IngestionService(self.settings); self.repo=self.service.repository
        self.repo.base.initialize()
        for payer in CTX.taxpayer_ids:
            self.repo.base.add_taxpayer(CTX,TaxpayerMaster(config_version='fixture-v1',creator='fixture',stage='test',
                tenant_id=CTX.tenant_id,taxpayer_id=payer,revision=1,tax_code='1234567890',
                effective_from=date(2026,1,1),provenance_reference='synthetic-only'))

    def tearDown(self): self.temp.cleanup()

    def submit(self,raw=None,key='key-1',service=None,enqueue=True,mime='application/pdf',filename='invoice.pdf'):
        service=service or self.service
        with StagedUpload(service.settings) as staged:
            raw=pdf_bytes() if raw is None else raw
            for start in range(0,len(raw),127): staged.write(raw[start:start+127])
            return service.accept_staged(CTX,'payer-a',1,key,staged,mime,filename,enqueue=enqueue)

    def processed(self,kind='native',**kwargs):
        view=self.submit(pdf_bytes(kind,**kwargs))
        outcome=self.service.work_one(CTX,'payer-a',view.ingestion_id)
        self.assertEqual(outcome.status,'SUCCEEDED',str(outcome.issue))
        return self.repo.document(CTX,'payer-a',view.ingestion_id)

    def test_native_scan_mixed_and_hybrid_routes(self):
        for kind,expected in [('native',['NATIVE_TEXT']),('scan',['OCR']),('mixed',['NATIVE_TEXT','OCR']),('hybrid',['HYBRID'])]:
            view=self.submit(pdf_bytes(kind),key=kind)
            outcome=self.service.work_one(CTX,'payer-a',view.ingestion_id)
            self.assertEqual(outcome.status,'SUCCEEDED',str(outcome.issue))
            document=self.repo.document(CTX,'payer-a',view.ingestion_id)
            self.assertEqual([p.route for p in document.pages],expected)
            self.assertTrue(all(p.route_reasons for p in document.pages))
            self.assertEqual(outcome.extraction_status,'QUEUED')
            self.assertEqual(document.pages[0].deduplication_required,kind=='hybrid')

    def test_invisible_layer_and_garbage_do_not_skip_ocr(self):
        for kind in ('invisible','garbage'):
            view=self.submit(pdf_bytes(kind),key=kind)
            self.service.work_one(CTX,'payer-a',view.ingestion_id)
            page=self.repo.document(CTX,'payer-a',view.ingestion_id).pages[0]
            self.assertEqual(page.route,'OCR')
            if kind=='invisible':
                self.assertGreater(page.invisible_text_spans,0); self.assertFalse(page.native_blocks)

    def test_vietnamese_font_nbsp_is_valid_native_text(self):
        raw=(PROJECT/'tests/fixtures/ocr/functional_set_v1/syn-00-pdf_text.pdf').read_bytes()
        view=self.submit(raw)
        outcome=self.service.work_one(CTX,'payer-a',view.ingestion_id)
        self.assertEqual(outcome.status,'SUCCEEDED',str(outcome.issue))
        page=self.repo.document(CTX,'payer-a',view.ingestion_id).pages[0]
        self.assertEqual(page.route,'NATIVE_TEXT')
        self.assertGreaterEqual(page.valid_glyph_ratio,0.98)

    def test_pdf_rotations_and_crop_inverse_evidence(self):
        for rotation in (0,90,180,270):
            view=self.submit(pdf_bytes(rotation=rotation,crop=True),key='rotation-'+str(rotation))
            self.service.work_one(CTX,'payer-a',view.ingestion_id)
            page=self.repo.document(CTX,'payer-a',view.ingestion_id).pages[0]
            self.assertEqual(page.rotation,rotation)
            self.assertEqual(page.geometry.crop_origin,(10,20))
            for block in page.native_blocks:
                region=block.evidence.bbox
                rendered=(region[0]*page.render_width,region[1]*page.render_height,region[2]*page.render_width,region[3]*page.render_height)
                restored=bbox(page.geometry.render_to_original,rendered)
                for original,actual in zip(block.original_bbox,restored): self.assertAlmostEqual(original,actual,places=4)

    def test_exif_rotation_preserves_raw_and_processed_orientation(self):
        raw=image_bytes(exif=6,format='JPEG')
        view=self.submit(raw,mime='image/jpeg',filename='invoice.jpg')
        outcome=self.service.work_one(CTX,'payer-a',view.ingestion_id)
        self.assertEqual(outcome.status,'SUCCEEDED',str(outcome.issue))
        page=self.repo.document(CTX,'payer-a',view.ingestion_id).pages[0]
        self.assertEqual((page.render_width,page.render_height),(80,120))
        self.assertEqual(page.exif_orientation,6)
        self.assertEqual(self.repo.base.source(CTX,'payer-a',view.source_id)[1],raw)
        self.assertTrue(self.repo.render(CTX,'payer-a',view.ingestion_id,0).startswith(b'\x89PNG'))

    def test_png_source_pixels_and_document_pixel_budget(self):
        limited=IngestionService(self.settings.model_copy(update={'max_source_pixels':1000}))
        view=self.submit(image_bytes(),service=limited,mime='image/png',filename='invoice.png')
        self.assertEqual(limited.work_one(CTX,'payer-a',view.ingestion_id).issue.code,'LIMIT_EXCEEDED')
        limited=IngestionService(self.settings.model_copy(update={'max_document_pixels':150000}))
        view=self.submit(pdf_bytes('mixed'),key='total-pixels',service=limited)
        self.assertEqual(limited.work_one(CTX,'payer-a',view.ingestion_id).issue.code,'LIMIT_EXCEEDED')

    def test_encrypted_corrupt_page_and_pixel_limits_are_typed(self):
        for name,raw,code in [('encrypted',pdf_bytes('encrypted'),'ENCRYPTED_PDF'),
                              ('corrupt',b'%PDF-1.4\nnot-a-document','CORRUPT_DOCUMENT'),
                              ('pixels',pdf_bytes('oversized'),'LIMIT_EXCEEDED')]:
            view=self.submit(raw,key=name)
            outcome=self.service.work_one(CTX,'payer-a',view.ingestion_id)
            self.assertEqual(outcome.status,'FAILED'); self.assertEqual(outcome.issue.code,code)
            self.assertFalse(outcome.issue.retryable)
            self.assertEqual(outcome.extraction_status,'NOT_QUEUED')
        limited=IngestionService(self.settings.model_copy(update={'max_pages':1}))
        view=self.submit(pdf_bytes('mixed'),key='page-limit',service=limited)
        self.assertEqual(limited.work_one(CTX,'payer-a',view.ingestion_id).issue.code,'LIMIT_EXCEEDED')

    def test_byte_limit_stops_before_writing_overflow_chunk(self):
        small=self.settings.model_copy(update={'max_upload_bytes':4})
        with StagedUpload(small) as staged:
            staged.write(b'1234')
            with self.assertRaises(IngestionError) as error: staged.write(b'5')
            self.assertEqual(error.exception.status,413); self.assertEqual(staged.size,4)
            path=staged.path
        self.assertFalse(path.exists())

    def test_idempotency_same_content_configuration_and_conflicts(self):
        raw=pdf_bytes(); first=self.submit(raw)
        again=self.submit(raw)
        self.assertEqual(first.ingestion_id,again.ingestion_id)
        with self.assertRaises(IngestionError) as error: self.submit(pdf_bytes('scan'))
        self.assertEqual(error.exception.issue.code,'IDEMPOTENCY_CONFLICT')
        modified=IngestionService(self.settings.model_copy(update={'route_policy':RoutePolicy(version='route-v2')}))
        with self.assertRaises(IngestionError): self.submit(raw,service=modified)
        with self.repo.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sources').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)

    def test_concurrent_same_key_creates_one_ingestion(self):
        raw=pdf_bytes()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            views=list(pool.map(lambda _:self.submit(raw),range(2)))
        self.assertEqual(views[0].ingestion_id,views[1].ingestion_id)
        with self.repo.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sources').fetchone()[0],1)

    def test_no_runnable_job_when_raw_audit_rolls_back(self):
        with self.repo.db() as db:
            db.execute("CREATE TRIGGER fail_source BEFORE INSERT ON events WHEN json_extract(NEW.payload,'$.event_type')='SOURCE_STORED' BEGIN SELECT RAISE(ABORT,'failure'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.submit()
        with self.repo.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sources').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)

    def test_actual_process_death_after_raw_commit_and_recovery(self):
        raw=pdf_bytes(); raw_path=self.directory/'input.pdf'; raw_path.write_bytes(raw)
        code="""
import json,os,sys
from pathlib import Path
from src.config import Settings
from src.domain.taxpayer import AccessContext
from src.ingestion.service import IngestionService
from src.ingestion.upload import StagedUpload
s=Settings(**json.loads(sys.argv[1])); c=AccessContext(**json.loads(sys.argv[2])); service=IngestionService(s)
staged=StagedUpload(s); staged.write(Path(sys.argv[3]).read_bytes())
service.accept_staged(c,'payer-a',1,'crash-key',staged,'application/pdf','invoice.pdf',enqueue=False)
os._exit(73)
"""
        result=subprocess.run([sys.executable,'-c',code,self.settings.model_dump_json(exclude={'auth_grants'}),CTX.model_dump_json(),str(raw_path)],
                              cwd=PROJECT,timeout=20,capture_output=True)
        self.assertEqual(result.returncode,73,result.stderr.decode(errors='replace'))
        with self.repo.db() as db:
            row=db.execute('SELECT ingestion_id,status FROM ingestions').fetchone()
            self.assertEqual(row['status'],'STORED'); self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
        self.assertEqual(self.repo.recover_stored(CTX,'payer-a'),1)
        outcome=self.service.work_one(CTX,'payer-a',row['ingestion_id'])
        self.assertEqual(outcome.status,'SUCCEEDED',str(outcome.issue))
        self.assertEqual(self.repo.base.source(CTX,'payer-a',outcome.source_id)[1],raw)

    def test_expired_worker_lease_recovers_and_stale_token_cannot_complete(self):
        view=self.submit(); old=self.repo.claim(CTX,'payer-a',view.ingestion_id)
        self.assertIsNone(self.repo.claim(CTX,'payer-a',view.ingestion_id))
        with self.repo.db() as db:
            db.execute('UPDATE ingestions SET lease_until=?',(time.time()-1,))
        result=self.service.work_one(CTX,'payer-a',view.ingestion_id)
        self.assertEqual(result.status,'SUCCEEDED',str(result.issue)); self.assertEqual(result.attempts,2)
        from src.ingestion.models import IngestionIssue
        self.assertFalse(self.repo.fail(CTX,'payer-a',view.ingestion_id,old,
            IngestionIssue(code='PROCESSING_ERROR',message='stale',next_action='none')))
        document=self.repo.document(CTX,'payer-a',view.ingestion_id)
        self.assertEqual(document.pages[0].page_id,self.repo.document(CTX,'payer-a',view.ingestion_id).pages[0].page_id)
        with self.repo.db() as db: self.assertEqual(db.execute('SELECT count(*) FROM extraction_outbox').fetchone()[0],1)

    def test_artifact_and_extraction_audit_failure_rolls_back_then_retry(self):
        view=self.submit()
        with self.repo.db() as db:
            db.execute("CREATE TRIGGER fail_complete BEFORE INSERT ON ingestion_events WHEN json_extract(NEW.payload,'$.event_type')='DOCUMENT_AND_EXTRACTION_COMMITTED' BEGIN SELECT RAISE(ABORT,'failure'); END")
        result=self.service.work_one(CTX,'payer-a',view.ingestion_id)
        self.assertEqual(result.status,'FAILED'); self.assertTrue(result.issue.retryable)
        with self.repo.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM documents').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM extraction_outbox').fetchone()[0],0)
            db.execute('DROP TRIGGER fail_complete')
        self.repo.retry(CTX,'payer-a',view.ingestion_id)
        self.assertEqual(self.service.work_one(CTX,'payer-a',view.ingestion_id).status,'SUCCEEDED')

    def test_timeout_retry_budget_is_finite(self):
        service=IngestionService(self.settings.model_copy(update={'worker_timeout_seconds':0.001,'max_attempts':2}))
        view=self.submit(service=service)
        outcome=service.work_one(CTX,'payer-a',view.ingestion_id)
        self.assertEqual(outcome.issue.code,'WORKER_TIMEOUT'); self.assertTrue(outcome.issue.retryable)
        service.repository.retry(CTX,'payer-a',view.ingestion_id)
        outcome=service.work_one(CTX,'payer-a',view.ingestion_id)
        self.assertEqual(outcome.attempts,2); self.assertFalse(outcome.issue.retryable)
        with self.assertRaises(IngestionError): service.repository.retry(CTX,'payer-a',view.ingestion_id)

    def test_authenticated_upload_status_document_render_and_raw(self):
        headers={'Authorization':'Bearer '+TOKEN,'Idempotency-Key':'http-1','Content-Type':'application/pdf','X-Filename':'invoice.pdf'}
        with TestClient(create_app(self.settings)) as client:
            response=client.post('/v1/ingestions?taxpayer_id=payer-a&master_revision=1',headers=headers,content=pdf_bytes())
            self.assertEqual(response.status_code,202,response.text); view=response.json(); identifier=view['ingestion_id']
            self.service.work_one(CTX,'payer-a',identifier)
            base=f'/v1/ingestions/{identifier}'
            self.assertEqual(client.get(base+'?taxpayer_id=payer-a',headers=headers).json()['status'],'SUCCEEDED')
            self.assertEqual(client.get(base+'/document?taxpayer_id=payer-a',headers=headers).status_code,200)
            self.assertEqual(client.get(base+'/pages/0/image?taxpayer_id=payer-a',headers=headers).headers['content-type'],'image/png')
            raw=client.get('/v1/sources/'+view['source_id']+'/raw?taxpayer_id=payer-a',headers=headers)
            self.assertEqual(raw.headers['x-content-type-options'],'nosniff')

    def test_auth_scope_mime_path_and_unsupported_format_rejection(self):
        base='/v1/ingestions?taxpayer_id=payer-a&master_revision=1'
        headers={'Authorization':'Bearer '+TOKEN,'Idempotency-Key':'http-1','Content-Type':'application/pdf'}
        with TestClient(create_app(self.settings)) as client:
            self.assertEqual(client.post(base,headers={'Idempotency-Key':'x'},content=pdf_bytes()).status_code,401)
            self.assertEqual(client.post(base.replace('payer-a','ungranted'),headers=headers,content=pdf_bytes()).status_code,403)
            self.assertEqual(client.post(base,headers={**headers,'X-Filename':'../invoice.pdf'},content=pdf_bytes()).status_code,400)
            self.assertEqual(client.post(base,headers=headers,content=image_bytes()).status_code,415)
            for prefix in (b'PK\x03\x04',b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1',b'<?xml version="1.0"?><invoice/>'):
                self.assertEqual(client.post(base,headers=headers,content=prefix).status_code,415)
        with self.repo.db() as db: self.assertEqual(db.execute('SELECT count(*) FROM ingestions').fetchone()[0],0)

    def test_slow_upload_times_out_and_cleans_staging(self):
        import asyncio
        import httpx
        async def exercise():
            async def slow_body():
                yield b'%PDF-'
                await asyncio.sleep(0.1)
                yield b'remainder'
            app=create_app(self.settings.model_copy(update={'max_upload_seconds':0.02}))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                response=await client.post('/v1/ingestions?taxpayer_id=payer-a&master_revision=1',
                    headers={'Authorization':'Bearer '+TOKEN,'Idempotency-Key':'slow','Content-Type':'application/pdf'},content=slow_body())
                self.assertEqual(response.status_code,408,response.text)
                self.assertEqual(response.json()['error']['code'],'UPLOAD_TIMEOUT')
        asyncio.run(exercise())
        self.assertFalse(list(self.settings.staging_directory.glob('capture-*.part')))
        with self.repo.db() as db: self.assertEqual(db.execute('SELECT count(*) FROM sources').fetchone()[0],0)

    def test_staging_cleanup_only_old_system_files(self):
        directory=self.settings.staging_directory; directory.mkdir(exist_ok=True)
        old=directory/'capture-orphan.part'; old.write_bytes(b'orphan'); os.utime(old,(0,0))
        other=directory/'user.pdf'; other.write_bytes(b'keep')
        fresh=directory/'capture-active.part'; fresh.write_bytes(b'active')
        self.assertEqual(cleanup_staging(self.settings),1)
        self.assertTrue(other.exists()); self.assertTrue(fresh.exists())

    def test_cross_tenant_http_reads_and_viewer_upload_are_denied(self):
        view=self.submit()
        other='other-test-token'; viewer='viewer-test-token'
        grants=(AuthGrant(token_sha256=hashlib.sha256(other.encode()).hexdigest(),actor_id='other',tenant_id='tenant-b',
                         taxpayer_ids=frozenset({'payer-a'}),permissions=frozenset({'READ'})),
                AuthGrant(token_sha256=hashlib.sha256(viewer.encode()).hexdigest(),actor_id='viewer',tenant_id='tenant-a',
                          taxpayer_ids=frozenset({'payer-a'}),permissions=frozenset({'READ'})))
        with TestClient(create_app(self.settings.model_copy(update={'auth_grants':grants}))) as client:
            self.assertEqual(client.get(f'/v1/ingestions/{view.ingestion_id}?taxpayer_id=payer-a',
                             headers={'Authorization':'Bearer '+other}).status_code,404)
            self.assertEqual(client.get(f'/v1/sources/{view.source_id}/raw?taxpayer_id=payer-a',
                             headers={'Authorization':'Bearer '+other}).status_code,404)
            self.assertEqual(client.post('/v1/ingestions?taxpayer_id=payer-a&master_revision=1',
                             headers={'Authorization':'Bearer '+viewer,'Idempotency-Key':'viewer'},content=pdf_bytes()).status_code,403)

    def test_pending_capacity_and_old_foundation_migration(self):
        limited=IngestionService(self.settings.model_copy(update={'max_pending_ingestions':1}))
        self.submit(service=limited)
        with self.assertRaises(IngestionError) as error: self.submit(key='next',service=limited)
        self.assertEqual(error.exception.status,429)
        path=self.directory/'foundation-v1.sqlite3'
        with sqlite3.connect(path) as db:
            db.executescript((PROJECT/'migrations/001_foundation.sql').read_text())
            db.execute("INSERT INTO taxpayer_masters VALUES('t','p',1,'preserved')")
        from src.persistence.repository import Repository
        repository=Repository(Settings(database_path=path))
        repository.initialize(); repository.initialize()
        with repository.connection() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],6)
            self.assertEqual(db.execute('SELECT payload FROM taxpayer_masters').fetchone()[0],'preserved')


class GeometryAndSandboxTests(unittest.TestCase):
    def test_transform_roundtrips_exif_crop_and_deskew(self):
        for orientation in range(1,9):
            matrix=compose(exif_transform(orientation,120,80),crop_transform(3,4))
            matrix=compose(matrix,deskew_transform(2.5,(40,60)))
            point=(25,35); restored=apply(inverse(matrix),apply(matrix,point))
            self.assertAlmostEqual(restored[0],point[0],places=8); self.assertAlmostEqual(restored[1],point[1],places=8)

    def test_os_memory_cap_is_enforced(self):
        code='import sys; sys.stdin.buffer.readline(); data=bytearray(300*1024*1024)'
        with self.assertRaises(IngestionError) as error:
            run_bounded([sys.executable,'-c',code],b'GO\n',10,64,PROJECT)
        self.assertEqual(error.exception.issue.code,'WORKER_RESOURCE_ERROR')


if __name__=='__main__': unittest.main()
