"""HTTP human review with server-owned identity/revision/evidence metadata."""
import sys
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi.testclient import TestClient

APP=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(APP));sys.path.insert(0,str(APP/'tests/e2e_v1'))
import test_compliance as cf
from src.app import create_app
from src.ingestion.models import AuthGrant
from src.persistence.repository import digest
from src.business_review.web import WebReviews


class WebBusinessTests(unittest.TestCase):
    def setUp(self):
        self.f=cf.ComplianceTests('test_default_catalog_no_false_tax_pass_and_capture_export_works')
        self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.client=self.f.client;self.headers=self.f.headers
        self.url='/v1/records/'+self.f.record_id
        self.params={'taxpayer_id':self.f.payer}
        self.repo=WebReviews(self.f.settings)

    def command(self,**changes):
        return dict(expected_record_revision=1,expected_review_id=None,confirmed=True,review_reference='Human reviewed original source',
            invoice=None,products=[],payment=None,daily=None,**changes)

    def save(self,data=None,key='business-save-1'):
        return self.client.post(self.url+'/business-reviews',params=self.params,json=data or self.command(),
            headers={**self.headers,'Idempotency-Key':key})

    def upload(self,kind='BANK_STATEMENT',body=None,revision=1,name='bank.pdf'):
        if body is None:
            rec=self.repo.base.record(self.f.ctx,self.f.payer,self.f.record_id)
            body=self.repo.base.source(self.f.ctx,self.f.payer,rec.source_id)[1]
        return self.client.post(self.url+'/business-documents',params={**self.params,'expected_record_revision':revision,'kind':kind},
            content=body,headers={**self.headers,'X-File-Name':name,'Content-Type':'application/octet-stream'})

    def test_editor_and_save_server_binds_metadata_and_idempotency(self):
        editor=self.client.get(self.url+'/business-review',params=self.params,headers=self.headers)
        self.assertEqual(editor.status_code,200);self.assertIsNone(editor.json()['review_id'])
        self.assertEqual(editor.json()['documents'][0]['evidence_id'],'source-invoice')
        first=self.save();self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(self.save().json(),first.json())
        rec=self.repo.base.record(self.f.ctx,self.f.payer,self.f.record_id)
        dossier=self.repo.latest(self.f.ctx,self.f.payer,rec)
        self.assertEqual(dossier.reviewer_id,self.f.ctx.actor_id)
        self.assertEqual(dossier.record_revision,1);self.assertEqual(rec.revision,1)
        self.assertFalse(first.json()['legal_approval'])

    def test_optimistic_review_conflict_and_idempotency_changed_body(self):
        self.assertEqual(self.save().status_code,200)
        self.assertEqual(self.save(key='business-save-2').status_code,409)
        data=self.command();data['review_reference']='Changed contents'
        self.assertEqual(self.save(data).status_code,409)
        editor=self.client.get(self.url+'/business-review',params=self.params,headers=self.headers).json()
        data['expected_review_id']=editor['review_id']
        self.assertEqual(self.save(data,key='business-save-3').status_code,200)

    def test_confirmation_and_server_owned_fields_cannot_be_forged(self):
        data=self.command();data['confirmed']=False
        self.assertEqual(self.save(data).status_code,422)
        for key,value in [('reviewer_id','forged'),('record_sha256','a'*64),('legal_approval',True),('payment_proof',{'field':True})]:
            data=self.command();data[key]=value
            self.assertEqual(self.save(data).status_code,422,key)

    def test_stale_record_revision_rejected_on_upload_and_save(self):
        data=self.command();data['expected_record_revision']=999
        self.assertEqual(self.save(data).status_code,409)
        self.assertEqual(self.upload(revision=999).status_code,409)

    def test_document_upload_download_and_readiness_draft(self):
        response=self.upload();self.assertEqual(response.status_code,200,response.text)
        doc=response.json();self.assertTrue(doc['evidence_id'].startswith('bd-'))
        downloaded=self.client.get(self.url+'/business-documents/'+doc['evidence_id'],params=self.params,headers=self.headers)
        self.assertEqual(downloaded.status_code,200);self.assertEqual(digest(downloaded.content),doc['sha256'])
        self.assertEqual(downloaded.headers['x-content-type-options'],'nosniff')
        self.assertIn('attachment',downloaded.headers['content-disposition'])
        self.f.run_evaluation()
        self.assertEqual(self.save().status_code,200)
        readiness=self.client.get(self.url+'/business-readiness',params=self.params,headers=self.headers)
        self.assertEqual(readiness.status_code,200,readiness.text)
        self.assertIsNone(readiness.json()['tax_verdict'])
        self.assertTrue(all(e['eligibility']!='ELIGIBLE' for e in readiness.json()['draft_plan']['entries']))

    def test_file_magic_empty_oversize_and_original_source_kind_rejected(self):
        for body in (b'',b'<script>attack</script>'):
            self.assertEqual(self.upload(body=body).status_code,422)
        self.assertEqual(self.upload(kind='INVOICE').status_code,422)
        settings=self.f.settings.model_copy(update={'max_upload_bytes':10})
        client=TestClient(create_app(settings))
        response=client.post(self.url+'/business-documents',params={**self.params,'expected_record_revision':1,'kind':'OTHER'},
            content=b'%PDF-'+b'a'*100,headers=self.headers)
        self.assertEqual(response.status_code,413)

    def test_auth_readonly_cross_payer_and_unknown_document(self):
        self.assertEqual(self.client.get(self.url+'/business-review',params=self.params).status_code,401)
        self.assertEqual(self.client.get(self.url+'/business-review',params={'taxpayer_id':'other'},headers=self.headers).status_code,403)
        self.assertEqual(self.client.get(self.url+'/business-documents/unknown',params=self.params,headers=self.headers).status_code,404)
        grant=AuthGrant(token_sha256=digest(b'readonly'),actor_id='reader',tenant_id=self.f.ctx.tenant_id,
            taxpayer_ids=frozenset({self.f.payer}),permissions=frozenset({'READ'}))
        client=TestClient(create_app(self.f.settings.model_copy(update={'auth_grants':(grant,)})))
        headers={'Authorization':'Bearer readonly','Idempotency-Key':'readonly'}
        self.assertFalse(client.get(self.url+'/business-review',params=self.params,headers=headers).json()['can_write'])
        self.assertEqual(client.post(self.url+'/business-reviews',params=self.params,json=self.command(),headers=headers).status_code,403)
        self.assertEqual(client.post(self.url+'/business-documents',params={**self.params,'expected_record_revision':1,'kind':'OTHER'},content=b'%PDF-test',headers=headers).status_code,403)

    def test_uploaded_doc_scope_and_pending_upload_never_becomes_proof(self):
        self.assertEqual(self.upload().status_code,200)
        record=self.repo.base.record(self.f.ctx,self.f.payer,self.f.record_id)
        self.assertIsNone(self.repo.latest(self.f.ctx,self.f.payer,record))
        data=self.command();data['invoice']=dict(invoice_kind='VAT',form='ORDINARY',evidence_ids=['bd-forged'])
        self.assertEqual(self.save(data).status_code,422)

    def test_same_day_candidates_are_not_automatic_completeness(self):
        result=self.client.get(self.url+'/business-daily-candidates',params=self.params,headers=self.headers)
        self.assertEqual(result.status_code,200);self.assertFalse(result.json()['completeness_verified'])

    def test_parallel_saves_have_single_winner(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda key:self.save(key=key),['parallel-1','parallel-2']))
        self.assertEqual(sorted(r.status_code for r in results),[200,409])
        with self.repo.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM business_reviews').fetchone()[0],1)

    def test_documents_cannot_be_referenced_from_another_record(self):
        doc=self.upload().json()
        record=self.repo.base.record(self.f.ctx,self.f.payer,self.f.record_id)
        other=record.model_copy(update={'record_id':'other-record','revision':1})
        self.repo.base.create_record(self.f.ctx,other)
        url='/v1/records/other-record'
        self.assertEqual(self.client.get(url+'/business-documents/'+doc['evidence_id'],params=self.params,headers=self.headers).status_code,404)
        command=self.command();command['invoice']=dict(invoice_kind='VAT',form='ORDINARY',evidence_ids=[doc['evidence_id']])
        response=self.client.post(url+'/business-reviews',params=self.params,json=command,headers={**self.headers,'Idempotency-Key':'other-record'})
        self.assertEqual(response.status_code,422)

    def test_chunked_upload_size_checked_during_stream(self):
        client=TestClient(create_app(self.f.settings.model_copy(update={'max_upload_bytes':10})))
        def chunks():
            yield b'%PDF-'
            yield b'a'*20
        response=client.post(self.url+'/business-documents',params={**self.params,'expected_record_revision':1,'kind':'OTHER'},
            content=chunks(),headers=self.headers)
        self.assertEqual(response.status_code,413)


if __name__=='__main__':unittest.main()
