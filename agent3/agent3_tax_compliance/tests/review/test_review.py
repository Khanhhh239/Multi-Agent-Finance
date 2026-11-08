import sys,unittest,sqlite3,time,json
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from pydantic import ValidationError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'extraction_v1'))
import test_extraction as fixtures
from src.review.correction_service import CorrectionService
from src.review.contracts import Change,CorrectionCommand,TaskAction,ReviewError
from src.review.revision_reprocessor import apply
from src.quality.repository import replay
from src.quality.completeness import flatten
from src.jobs.service import CaptureJobs
from src.jobs.state import validate_transition
from src.app import create_app

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.PersistenceTests(methodName='test_atomic_idempotent_roundtrip');self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.ctx=fixtures.CTX;self.payer='payer-a';self.repo=CorrectionService(self.fixture.settings)
        self.artifact=self.repo.extraction.work(self.ctx,self.payer,self.fixture.identifier,self.fixture.key)
        self.record=self.artifact.record;self.q=self.repo.quality.work(self.ctx,self.payer,self.artifact.artifact_id)
        self.repo.ensure_tasks(self.ctx,self.payer,self.record.record_id)
        self.task=self.repo.page(self.ctx,self.payer,'tasks',record_id=self.record.record_id)['items'][0]
        self.client=TestClient(create_app(self.fixture.settings));self.headers={'Authorization':'Bearer '+self.fixture.token}

    def command(self,changes=None,**extra):
        return CorrectionCommand(record_id=self.record.record_id,expected_revision=1,task_id=self.task['task_id'],reason='Compared against source',
            changes=tuple(changes if changes is not None else [Change(field_path='parties.seller.tax_id',new_value='1234567890')]),**extra)
    def correct(self,command=None,key='correction-one'):
        return self.repo.correct(self.ctx,self.payer,command or self.command(),key)
    def count(self,table):
        with self.repo.ingestion.db() as db:return db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]

    def test_record_summary_and_job_link_survive_new_browser_session(self):
        jobs=CaptureJobs(self.fixture.settings);job=jobs.enqueue(self.ctx,self.payer,self.fixture.identifier)
        view=self.repo.view(self.ctx,self.payer,self.record.record_id)
        self.assertEqual(view['capture_job']['job_id'],job['job_id'])
        page=self.repo.page(self.ctx,self.payer,'records')
        self.assertEqual(page['items'][0]['summary']['invoice_number'],self.record.invoice.number.value)
        other=self.ctx.model_copy(update={'tenant_id':'another-tenant'})
        self.assertEqual(self.repo.page(other,self.payer,'records')['items'],[])
        with self.assertRaises(KeyError):self.repo.view(other,self.payer,self.record.record_id)

    def test_worker_interrupt_releases_lease_for_explicit_retry(self):
        from src.adapters.ocr.bridge import OCRBridge
        jobs=CaptureJobs(self.fixture.settings);job=jobs.enqueue(self.ctx,self.payer,self.fixture.identifier)
        class Native:
            def inventory(self):return {'runtime_sha256':'a'*64}
        bridge=OCRBridge(self.fixture.settings,fixtures.OCRConfig(),Native())
        with patch.object(bridge,'work_one',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):jobs.work_one(self.ctx,self.payer,job['job_id'],bridge)
        result=jobs.get(self.ctx,self.payer,job['job_id'])
        self.assertEqual(result['state'],'PROCESSING_ERROR');self.assertEqual(result['error_code'],'WORKER_INTERRUPTED')
        self.assertTrue(result['retryable'])
        retried=jobs.recover(self.ctx,self.payer,job['job_id'],'RETRY','Resume after closing local launcher')
        self.assertEqual(retried['state'],'QUEUED')

    def test_atomic_correction_direction_reassessment_replay_export(self):
        result=self.correct();r=self.repo.base.record(self.ctx,self.payer,self.record.record_id)
        self.assertEqual(r.revision,2);self.assertEqual(r.derived.invoice_direction.value,'OUTPUT')
        self.assertEqual(r.derived.counterparty,r.parties.buyer)
        q=self.repo.quality.get(self.ctx,self.payer,result['assessment_id'])
        f=next(f for f in q.fields if f.field_path=='parties.seller.tax_id');self.assertEqual(f.reliability,'HUMAN_CONFIRMED')
        self.assertEqual(replay(self.repo.quality.inputs(self.ctx,self.payer,q.assessment_id),q),q)
        self.assertTrue(self.repo.rebuild(self.ctx,self.payer,r.record_id)['verified'])
        export=self.repo.export(self.ctx,self.payer,r.record_id);self.assertEqual(export['record']['revision'],2)
        self.assertTrue(export['review_required']);self.assertNotIn('verdict',export)

    def test_idempotent_double_submit_and_key_conflict(self):
        a=self.correct();b=self.correct();self.assertEqual(a['event_id'],b['event_id']);self.assertTrue(b['replayed']);self.assertEqual(self.count('review_events'),1)
        c=self.command([Change(field_path='parties.seller.tax_id',new_value='1111111111')])
        with self.assertRaises(ReviewError) as error:self.correct(c)
        self.assertEqual(error.exception.code,'IDEMPOTENCY_CONFLICT')

    def test_concurrent_reviewers_cas(self):
        other=self.ctx.model_copy(update={'actor_id':'second-reviewer'})
        def submit(pair):
            ctx,key=pair
            try:return self.repo.correct(ctx,self.payer,self.command(),key)
            except ReviewError as error:return error
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,[(self.ctx,'one'),(other,'two')]))
        self.assertEqual(sum(isinstance(r,dict) for r in results),1)
        error=next(r for r in results if isinstance(r,ReviewError));self.assertEqual(error.status,409);self.assertEqual(error.latest_revision,2)
        self.assertEqual(self.count('review_events'),1)

    def test_audit_failure_rolls_back_every_write(self):
        counts={t:self.count(t) for t in ('revisions','review_events','quality_assessments','review_tasks')}
        with patch.object(self.repo.ingestion,'_event',side_effect=RuntimeError('audit failure')):
            with self.assertRaises(RuntimeError):self.correct()
        self.assertEqual({t:self.count(t) for t in counts},counts)
        self.assertEqual(self.repo.base.record(self.ctx,self.payer,self.record.record_id).revision,1)

    def test_candidate_field_and_record_ownership(self):
        candidate=next(c for c in self.artifact.candidates if c.semantic_field=='totals.gross')
        for cid in (candidate.candidate_id,'candidate-from-another-record'):
            with self.assertRaises(ReviewError):self.correct(self.command([Change(field_path='parties.seller.tax_id',selected_candidate_id=cid)]))
        self.assertEqual(self.count('review_events'),0)
        self.correct(self.command([Change(field_path='totals.gross',selected_candidate_id=candidate.candidate_id)]))

    def test_real_candidate_from_second_record_rejected(self):
        from src.ingestion.service import IngestionService
        from src.ingestion.upload import StagedUpload
        from src.adapters.ocr.bridge import OCRBridge
        raw=(Path(__file__).resolve().parents[1]/'fixtures/ocr/functional_set_v1/syn-01-pdf_text.pdf').read_bytes()
        service=IngestionService(self.fixture.settings)
        with StagedUpload(self.fixture.settings) as staged:
            staged.write(raw);view=service.accept_staged(self.ctx,self.payer,1,'second-source',staged,'application/pdf')
        service.work_one(self.ctx,self.payer,view.ingestion_id)
        class Native:
            def inventory(self):return {'runtime_sha256':'a'*64}
            def run_batch(self,*args):raise AssertionError('native')
        OCRBridge(self.fixture.settings,fixtures.OCRConfig(),Native()).work_one(self.ctx,self.payer,view.ingestion_id)
        other=self.repo.extraction.work(self.ctx,self.payer,view.ingestion_id,self.fixture.key)
        c=next(c for c in other.candidates if c.semantic_field=='totals.gross')
        with self.assertRaises(ReviewError):self.correct(self.command([Change(field_path='totals.gross',selected_candidate_id=c.candidate_id)]))

    def test_item_correction_recomputes_exact_totals(self):
        item=self.record.items[0];prefix='items.'+item.item_id+'.'
        command=self.command([Change(field_path=prefix+'net',new_value='200000.01'),Change(field_path=prefix+'vat_treatment',new_value='TAXABLE_RATE'),Change(field_path=prefix+'vat_rate',new_value='0.08')],
            confirm_items_complete=True,expected_item_count=len(self.record.items),verified_pages=(0,))
        self.correct(command);export=self.repo.export(self.ctx,self.payer,self.record.record_id)
        self.assertEqual(export['summary']['derived_totals']['net']['value'],'200000.01')
        self.assertEqual(export['summary']['derived_totals']['vat']['value'],'16000.0008')
        self.assertEqual(export['summary']['derived_totals']['gross']['value'],'216000.0108')
        self.assertEqual(export['record']['totals'],self.record.model_dump(mode='json')['totals'])
        self.assertTrue(self.repo.rebuild(self.ctx,self.payer,self.record.record_id)['verified'])

    def test_exempt_treatment_is_not_zero_rate(self):
        prefix='items.'+self.record.items[0].item_id+'.'
        self.correct(self.command([Change(field_path=prefix+'vat_treatment',new_value='KCT')]))
        r=self.repo.base.record(self.ctx,self.payer,self.record.record_id)
        self.assertIsNone(r.items[0].vat_rate.value);self.assertEqual(r.items[0].vat_rate.status,'NOT_APPLICABLE')

    def test_bad_formats_derived_identity_and_completeness_are_rejected(self):
        for path,value in [('totals.gross','1e9'),('invoice.issue_date','31/02/2026'),('parties.seller.tax_id','123'),('derived.invoice_direction','INPUT'),('items.not-owned.net','100')]:
            with self.assertRaises((ReviewError,ValidationError)):self.correct(self.command([Change(field_path=path,new_value=value)]))
        with self.assertRaises(ReviewError):self.correct(self.command(confirm_items_complete=True,expected_item_count=999,verified_pages=(0,)))
        self.assertEqual(self.count('review_events'),0)

    def test_task_dedupe_and_lineage(self):
        before=self.count('review_tasks');self.repo.ensure_tasks(self.ctx,self.payer,self.record.record_id);self.assertEqual(before,self.count('review_tasks'))
        self.correct();tasks=self.repo.page(self.ctx,self.payer,'tasks',record_id=self.record.record_id,limit=100)['items']
        self.assertTrue(all(t['status'] in ('SUPERSEDED','RESOLVED') for t in tasks if t['revision']==1))
        self.assertTrue(any(t['previous_ids'] for t in tasks if t['revision']==2))

    def test_task_actions_are_scoped_audited_and_old_revision_rejected(self):
        result=self.repo.task_action(self.ctx,self.payer,self.task['task_id'],TaskAction(action='REQUEST_DATA',reason='Need original'))
        self.assertEqual(result['status'],'WAITING_DATA');self.correct()
        with self.assertRaises(ReviewError):self.repo.task_action(self.ctx,self.payer,self.task['task_id'],TaskAction(action='REOPEN',reason='Retry'))

    def test_scoped_snapshot_pagination(self):
        page=self.repo.page(self.ctx,self.payer,'tasks',record_id=self.record.record_id,limit=1);cursor=page['next_cursor'];self.assertTrue(cursor)
        self.correct();next_page=self.repo.page(self.ctx,self.payer,'tasks',record_id=self.record.record_id,limit=100,cursor=cursor)
        self.assertTrue(all(t['revision']==1 for t in next_page['items']))
        with self.assertRaises(ReviewError):self.repo.page(self.ctx,self.payer,'tasks',status='OPEN',cursor=cursor)
        other=self.ctx.model_copy(update={'tenant_id':'tenant-other'})
        self.assertEqual(self.repo.page(other,self.payer,'tasks')['items'],[])
        with self.assertRaises(ReviewError):self.repo.page(other,self.payer,'tasks',cursor=cursor)
        with self.assertRaises(ReviewError):self.repo.page(self.ctx,self.payer,'tasks',limit=101)

    def test_signed_evidence_expiry_tamper_actor_and_auth(self):
        grant=self.repo.grant(self.ctx,self.payer,self.artifact.artifact_id,0,10)
        self.assertTrue(self.repo.redeem(self.ctx,self.payer,grant['token']).startswith(b'\x89PNG'))
        with patch('src.review.repository.time.time',return_value=time.time()+11):
            with self.assertRaises(ReviewError):self.repo.redeem(self.ctx,self.payer,grant['token'])
        with self.assertRaises(ReviewError):self.repo.redeem(self.ctx.model_copy(update={'actor_id':'different'}),self.payer,grant['token'])
        with self.assertRaises(ReviewError):self.repo.redeem(self.ctx,self.payer,grant['token']+'a')
        self.assertEqual(self.client.post('/v1/evidence-image',params={'taxpayer_id':self.payer},json={'token':grant['token']}).status_code,401)

    def test_human_proof_survives_second_revision_and_regular_quality(self):
        self.correct();current=self.repo.base.record(self.ctx,self.payer,self.record.record_id)
        task=self.repo.page(self.ctx,self.payer,'tasks',record_id=current.record_id,status='OPEN',limit=100)['items'][0]
        cmd=CorrectionCommand(record_id=current.record_id,expected_revision=2,task_id=task['task_id'],reason='Source checked',changes=(Change(field_path='parties.buyer.tax_id',new_value='9876543210'),))
        self.correct(cmd,'two');q=self.repo.quality.work(self.ctx,self.payer,self.artifact.artifact_id)
        self.assertTrue(all(next(f for f in q.fields if f.field_path==p).reliability=='HUMAN_CONFIRMED' for p in ('parties.seller.tax_id','parties.buyer.tax_id')))
        self.assertTrue(self.repo.rebuild(self.ctx,self.payer,current.record_id)['verified'])

    def test_events_immutable_and_audit_redacts_fields(self):
        self.correct()
        with self.repo.ingestion.db() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM review_events')
        audit=self.repo.page(self.ctx,self.payer,'audit',record_id=self.record.record_id)
        self.assertNotIn('1234567890',json.dumps(audit));self.assertNotIn('after',audit['items'][0])

    def test_api_errors_permissions_export_and_ui(self):
        params={'taxpayer_id':self.payer};url='/v1/records/'+self.record.record_id
        self.assertEqual(self.client.get(url,params=params).status_code,401)
        self.assertEqual(self.client.get(url,params={'taxpayer_id':'other'},headers=self.headers).status_code,403)
        self.assertEqual(self.client.get(url,params=params,headers=self.headers).status_code,200)
        body=self.command().model_dump(mode='json');headers={**self.headers,'Idempotency-Key':'api-one'}
        self.assertEqual(self.client.post('/v1/corrections',params=params,headers=headers,json=body).status_code,200)
        conflict=self.client.post('/v1/corrections',params=params,headers={**self.headers,'Idempotency-Key':'api-two'},json=body)
        self.assertEqual(conflict.status_code,409);self.assertEqual(conflict.json()['error']['latest_revision'],2)
        self.assertEqual(self.client.get(url+'/export',params=params,headers=self.headers).json()['record']['revision'],2)
        self.assertEqual(self.client.get('/review').status_code,200);self.assertEqual(self.client.get('/review-assets/app.js').status_code,200)
        self.assertEqual(self.client.get('/review-assets/secrets').status_code,404)

    def test_job_native_flow_and_dedupe(self):
        from src.adapters.ocr.bridge import OCRBridge
        jobs=CaptureJobs(self.fixture.settings);job=jobs.enqueue(self.ctx,self.payer,self.fixture.identifier)
        self.assertEqual(job['job_id'],jobs.enqueue(self.ctx,self.payer,self.fixture.identifier)['job_id'])
        class Native:
            def inventory(self):return {'runtime_sha256':'a'*64}
            def run_batch(self,*args):raise AssertionError('Native flow must not invoke OCR')
        result=jobs.work_one(self.ctx,self.payer,job['job_id'],OCRBridge(self.fixture.settings,fixtures.OCRConfig(),Native()))
        self.assertEqual(result['state'],'REVIEW',result);self.assertEqual(result['record_id'],self.record.record_id)
        response=self.client.post('/v1/jobs/'+job['job_id']+'/complete',params={'taxpayer_id':self.payer},headers=self.headers)
        self.assertEqual(response.status_code,409)

    def test_processing_error_retry_bound_and_operator_path(self):
        from src.adapters.ocr.bridge import OCRBridge
        jobs=CaptureJobs(self.fixture.settings);job=jobs.enqueue(self.ctx,self.payer,self.fixture.identifier)
        class Broken:
            def inventory(self):raise RuntimeError('Do not leak tax code 1234567890')
        bridge=OCRBridge(self.fixture.settings,fixtures.OCRConfig(),Broken())
        for attempt in range(1,4):
            result=jobs.work_one(self.ctx,self.payer,job['job_id'],bridge)
            self.assertEqual(result['attempts'],attempt)
            if attempt<3:
                self.assertEqual(result['state'],'PROCESSING_ERROR');jobs.recover(self.ctx,self.payer,job['job_id'],'RETRY','Fix runtime')
        self.assertEqual(result['state'],'OPERATOR');self.assertNotIn('1234567890',json.dumps(result))
        with self.assertRaises(ReviewError):validate_transition('OPERATOR','COMPLETED')

    def test_expired_lease_recovery_and_stale_worker_fence(self):
        jobs=CaptureJobs(self.fixture.settings);job=jobs.enqueue(self.ctx,self.payer,self.fixture.identifier)
        token=jobs.claim(self.ctx,self.payer,job['job_id'],1)
        with patch('src.jobs.service.time.time',return_value=time.time()+2):
            self.assertIsNone(jobs.claim(self.ctx,self.payer,job['job_id'],10))
        self.assertEqual(jobs.get(self.ctx,self.payer,job['job_id'])['state'],'PROCESSING_ERROR')
        jobs.recover(self.ctx,self.payer,job['job_id'],'RETRY','Worker died')
        with self.assertRaises(ReviewError):jobs.transition(self.ctx,self.payer,job['job_id'],'EXTRACTING',token=token)

    def test_buyer_identity_change_and_ambiguous_direction(self):
        self.correct(self.command([Change(field_path='parties.buyer.tax_id',new_value='1234567890')]))
        r=self.repo.base.record(self.ctx,self.payer,self.record.record_id);self.assertEqual(r.derived.invoice_direction.value,'INPUT')
        task=self.repo.page(self.ctx,self.payer,'tasks',record_id=r.record_id,status='OPEN',limit=100)['items'][0]
        cmd=CorrectionCommand(record_id=r.record_id,expected_revision=2,task_id=task['task_id'],reason='Seller also matches',changes=(Change(field_path='parties.seller.tax_id',new_value='1234567890'),))
        self.correct(cmd,'ambiguous');r=self.repo.base.record(self.ctx,self.payer,r.record_id)
        self.assertEqual(r.derived.invoice_direction.status,'AMBIGUOUS');self.assertIsNone(r.derived.invoice_direction.value)

    def test_review_event_id_cannot_be_reused_for_a_different_value(self):
        self.correct(self.command([Change(field_path='parties.seller.tax_id',new_value='1234567890'),Change(field_path='parties.buyer.tax_id',new_value='9876543210')]))
        r=self.repo.base.record(self.ctx,self.payer,self.record.record_id)
        seller=r.parties.seller.model_copy(update={'tax_id':r.parties.seller.tax_id.model_copy(update={'value':'1111111111'})})
        forged=r.model_copy(update={'revision':3,'parties':r.parties.model_copy(update={'seller':seller})})
        from src.canonicalization.derive import rederive
        forged,_,_=rederive(forged,fixtures.MASTER,self.artifact.profile)
        self.repo.base.append_revision(self.ctx,forged,2,'Fixture simulating a forged proof')
        q=self.repo.quality.work(self.ctx,self.payer,self.artifact.artifact_id)
        self.assertEqual(next(f for f in q.fields if f.field_path=='parties.seller.tax_id').reliability,'UNAVAILABLE')

    def test_upload_api_to_worker_to_review_to_export(self):
        from src.adapters.ocr.bridge import OCRBridge
        raw=(Path(__file__).resolve().parents[1]/'fixtures/ocr/functional_set_v1/syn-02-pdf_text.pdf').read_bytes()
        uploaded=self.client.post('/v1/ingestions',params={'taxpayer_id':self.payer,'master_revision':1},headers={**self.headers,'Content-Type':'application/pdf','Idempotency-Key':'e2e-upload'},content=raw)
        self.assertEqual(uploaded.status_code,202,uploaded.text)
        job=self.client.post('/v1/capture-jobs',params={'taxpayer_id':self.payer,'ingestion_id':uploaded.json()['ingestion_id']},headers=self.headers).json()
        class Native:
            def inventory(self):return {'runtime_sha256':'a'*64}
            def run_batch(self,*args):raise AssertionError('native')
        result=CaptureJobs(self.fixture.settings).work_one(self.ctx,self.payer,job['job_id'],OCRBridge(self.fixture.settings,fixtures.OCRConfig(),Native()))
        self.assertEqual(result['state'],'REVIEW',result)
        task=self.repo.page(self.ctx,self.payer,'tasks',record_id=result['record_id'])['items'][0]
        command=CorrectionCommand(record_id=result['record_id'],expected_revision=1,task_id=task['task_id'],reason='Functional simulated review',changes=(Change(field_path='parties.seller.tax_id',new_value='1234567890'),))
        self.correct(command,'e2e-correct');export=self.client.get('/v1/records/'+result['record_id']+'/export',params={'taxpayer_id':self.payer},headers=self.headers)
        self.assertEqual(export.json()['record']['revision'],2)

    def test_exempt_with_explicit_clear_replays_once(self):
        prefix='items.'+self.record.items[0].item_id+'.'
        self.correct(self.command([Change(field_path=prefix+'vat_treatment',new_value='KKKNT'),Change(field_path=prefix+'vat_rate',operation='CLEAR')]))
        self.assertTrue(self.repo.rebuild(self.ctx,self.payer,self.record.record_id)['verified'])

    def test_no_write_permission_even_with_visible_record(self):
        reader=self.ctx.model_copy(update={'permissions':frozenset({'READ'})})
        with self.assertRaises(PermissionError):self.repo.correct(reader,self.payer,self.command(),'reader')
        with self.assertRaises(PermissionError):self.repo.task_action(reader,self.payer,self.task['task_id'],TaskAction(action='REQUEST_DATA',reason='read only'))

    def test_task_missing_reason_and_float_payload_rejected(self):
        with self.assertRaises(ValidationError):self.command().model_copy(update={'reason':' '}).__class__.model_validate({**self.command().model_dump(),'reason':' '})
        with self.assertRaises(ValidationError):Change(field_path='totals.gross',new_value=100.5)

    def test_request_data_recovery_path(self):
        jobs=CaptureJobs(self.fixture.settings);job=jobs.enqueue(self.ctx,self.payer,self.fixture.identifier)
        token=jobs.claim(self.ctx,self.payer,job['job_id'],60)
        jobs.transition(self.ctx,self.payer,job['job_id'],'PROCESSING_ERROR',token=token)
        result=jobs.recover(self.ctx,self.payer,job['job_id'],'REQUEST_DATA','Unreadable source; request replacement')
        self.assertEqual(result['state'],'WAITING_DATA')
        with self.assertRaises(ReviewError):jobs.recover(self.ctx,self.payer,job['job_id'],'RETRY','Cannot retry old source')

    def test_manual_completion_requires_current_verified_fields(self):
        from src.adapters.ocr.bridge import OCRBridge
        jobs=CaptureJobs(self.fixture.settings);job=jobs.enqueue(self.ctx,self.payer,self.fixture.identifier)
        class Native:
            def inventory(self):return {'runtime_sha256':'a'*64}
            def run_batch(self,*args):raise AssertionError('native')
        jobs.work_one(self.ctx,self.payer,job['job_id'],OCRBridge(self.fixture.settings,fixtures.OCRConfig(),Native()))
        changes=[Change(field_path=path,operation='CONFIRM') for path,field in flatten(self.record).items() if field.status=='PRESENT' and path not in ('parties.seller.tax_id','parties.buyer.tax_id')]
        changes.extend([Change(field_path='parties.seller.tax_id',new_value='1234567890'),Change(field_path='parties.buyer.tax_id',new_value='9876543210')])
        self.correct(self.command(changes,confirm_items_complete=True,expected_item_count=len(self.record.items),verified_pages=(0,)))
        q=self.repo.head_context(self.ctx,self.payer,self.record.record_id)[2]
        self.assertTrue(all(i.code=='AUTO_ACCEPT_DISABLED' for i in q.issues),[i.code for i in q.issues])
        response=self.client.post('/v1/jobs/'+job['job_id']+'/complete',params={'taxpayer_id':self.payer},headers=self.headers)
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['state'],'COMPLETED')

if __name__=='__main__':unittest.main()
