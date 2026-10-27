import copy,csv,http.client,json,tempfile,threading,unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from sme_fraud.feedback import read_audit,record_feedback
from sme_fraud.generate import write_csv
from sme_fraud.review_store import ReviewStore
from sme_fraud.review_server import make_server
from sme_fraud.review_roles import ReviewPrincipal
from sme_fraud.review_workflow import TwoStageReview
from test_review import make_fixture


class TwoStageReviewTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.data,self.report=make_fixture(self.root)
        self.now=datetime.fromisoformat('2026-10-24T09:00:00+07:00')
        self.store=ReviewStore(self.root/'data',self.root/'reports',self.root/'review.sqlite3',clock=lambda:self.now)
        self.store.prepare();self.workflow=TwoStageReview(self.store)
        self.accountant=ReviewPrincipal('ACC01','P01','Kế toán A','accountant',('C001',))
        self.chief=ReviewPrincipal('CHIEF01','P02','Kế toán trưởng B','chief_accountant',('C001',))
        self.director=ReviewPrincipal('DIR01','P03','Giám đốc C','director',('C001',))

    def body(self,case_id='RC_1',**values):
        current=self.workflow.state('003',case_id)
        result=dict(decision='false_positive',reason='Đã đối chiếu chứng từ trong fixture.',missing_evidence='',
            active_minutes=3.5,timing_method='measured_stopwatch',expected_event_hash=current['latest_event_hash'],
            expected_scope_hash=current['case_scope_hash'])
        result.update(values);return result

    def primary(self,case_id='RC_1'):
        return self.workflow.submit('003',case_id,self.accountant,self.body(case_id))

    def audit(self):return read_audit(self.report/'feedback_audit.jsonl')

    def test_primary_waits_for_final_review_and_does_not_close_case(self):
        state=self.primary()
        self.assertEqual(state['stage'],'pending_final');self.assertEqual(self.audit(),[])
        self.assertNotEqual(self.store.detail('003','RC_1')['case']['status'],'closed')
        self.assertEqual(state['primary']['data']['active_minutes'],3.5)

    def test_chief_and_director_can_each_finalize_another_persons_review(self):
        for case_id,person in [('RC_1',self.chief),('RC_2',self.director)]:
            self.primary(case_id)
            state=self.workflow.final_action('003',case_id,person,self.body(case_id))
            self.assertEqual(state['stage'],'finalized')
            self.assertEqual(self.store.detail('003',case_id)['case']['status'],'closed')
        self.assertEqual([r['reviewer'] for r in self.audit()],[self.chief.display_name,self.director.display_name])
        self.assertTrue(all(r.get('workflow_approval_id') for r in self.audit()))

    def test_accountant_cannot_finalize_and_supervisors_cannot_submit_primary(self):
        self.primary()
        with self.assertRaises(PermissionError):self.workflow.final_action('003','RC_1',self.accountant,self.body())
        for actor in (self.chief,self.director):
            with self.assertRaises(PermissionError):self.workflow.submit('003','RC_2',actor,self.body('RC_2'))
        self.assertEqual(self.audit(),[])

    def test_different_account_for_same_person_cannot_self_approve(self):
        self.primary();same=replace(self.chief,person_id=' p01 ')
        with self.assertRaisesRegex(PermissionError,'khác người'):self.workflow.final_action('003','RC_1',same,self.body())
        self.assertEqual(self.audit(),[])

    def test_scope_and_unauthenticated_requests_are_rejected(self):
        with self.assertRaises(PermissionError):self.workflow.submit('003','RC_1',None,self.body())
        with self.assertRaises(PermissionError):self.workflow.submit('003','RC_7',self.accountant,self.body('RC_7'))
        self.assertEqual(self.audit(),[])

    def test_identity_and_role_from_request_cannot_be_forged(self):
        for field,value in [('role','director'),('reviewer','Fake'),('person_id','P02')]:
            with self.assertRaises(ValueError):self.workflow.submit('003','RC_1',self.accountant,self.body(**{field:value}))

    def test_no_finalization_without_a_pending_primary(self):
        with self.assertRaises(RuntimeError):self.workflow.final_action('003','RC_1',self.chief,self.body())
        self.assertEqual(self.audit(),[])

    def test_return_requires_resubmission_and_keeps_the_case_open(self):
        self.primary();state=self.workflow.final_action('003','RC_1',self.chief,self.body(reason='Cần kiểm tra thêm hóa đơn.'),action='return')
        self.assertEqual(state['stage'],'returned');self.assertEqual(self.audit(),[])
        with self.assertRaises(RuntimeError):self.workflow.final_action('003','RC_1',self.director,self.body())
        self.primary();self.workflow.final_action('003','RC_1',self.director,self.body())
        self.assertEqual(len(self.audit()),1)

    def test_stale_primary_and_finalization_requests_fail(self):
        stale=self.body();self.primary()
        with self.assertRaises(RuntimeError):self.workflow.submit('003','RC_1',self.accountant,stale)
        with self.assertRaises(RuntimeError):self.workflow.final_action('003','RC_1',self.chief,stale)
        wrong=self.body(expected_scope_hash='wrong')
        with self.assertRaisesRegex(RuntimeError,'bằng chứng'):self.workflow.final_action('003','RC_1',self.chief,wrong)

    def test_changed_case_evidence_does_not_inherit_the_primary_review(self):
        self.primary();old=self.body()
        with (self.report/'case_queue.csv').open(encoding='utf-8-sig',newline='') as s:rows=list(csv.DictReader(s))
        next(r for r in rows if r['case_id']=='RC_1')['max_score']='99'
        write_csv(self.report/'case_queue.csv',rows);self.store.prepare()
        self.assertEqual(self.workflow.state('003','RC_1')['stage'],'pending_review')
        with self.assertRaises(RuntimeError):self.workflow.final_action('003','RC_1',self.chief,old)

    def test_direct_feedback_and_cli_api_cannot_skip_the_two_levels(self):
        self.primary()
        with self.assertRaises(PermissionError):record_feedback(self.report,'RC_1','false_positive','Fake chief','Fake decision',self.now.isoformat())
        with self.assertRaises(PermissionError):self.store.save_feedback('003','RC_1','false_positive','Fake chief','Fake decision','')
        self.assertEqual(self.audit(),[])

    def test_real_minutes_are_required_and_not_inferred_from_estimates(self):
        for update in ({'active_minutes':0},{'active_minutes':True},{'active_minutes':float('inf')},{'timing_method':'estimated'}):
            with self.assertRaises(ValueError):self.workflow.submit('003','RC_1',self.accountant,self.body(**update))
        with self.assertRaises(ValueError):self.workflow.submit('003','RC_1',self.accountant,self.body(decision='information_gap'))

    def test_information_request_gate_is_preserved_at_final_approval(self):
        detail=self.store.detail('003','RC_1')
        self.store.update_information_request('003','RC_1',dict(action='create',expected_hash='',case_scope_hash=detail['case']['review_scope_hash'],
            owner='Kế toán A',actor='Kế toán A',reason='Cần hóa đơn.',requested_documents='Hóa đơn',due_at='2026-10-25T09:00:00+07:00'))
        self.primary()
        with self.assertRaisesRegex(RuntimeError,'Còn yêu cầu tài liệu'):self.workflow.final_action('003','RC_1',self.chief,self.body())
        self.assertEqual(self.audit(),[]);self.assertEqual(self.workflow.state('003','RC_1')['stage'],'pending_final')

    def test_audit_integrity_restart_and_no_duplicate_finalization(self):
        self.primary();self.workflow=TwoStageReview(self.store)
        self.workflow.final_action('003','RC_1',self.chief,self.body())
        with self.assertRaises(RuntimeError):self.workflow.final_action('003','RC_1',self.director,self.body())
        self.assertEqual(len(self.audit()),1)
        with self.store.connection() as db:db.execute("UPDATE review_workflow_events SET data=replace(data,'Kế toán A','Tampered') WHERE sequence=1")
        with self.assertRaises(ValueError):self.workflow.state('003','RC_1')

    def test_derived_csv_failure_after_append_does_not_duplicate_a_conclusion(self):
        self.primary()
        with patch('sme_fraud.feedback.write_review_states',side_effect=OSError('disk transient')):
            state=self.workflow.final_action('003','RC_1',self.chief,self.body())
        self.assertEqual(state['stage'],'finalized');self.assertEqual(len(self.audit()),1)

    def test_backup_restore_preserves_pending_review_and_the_permission_gate(self):
        from sme_fraud.review_backup import create_backup,restore_backup,restored_store
        self.primary()
        manifest=create_backup(self.store.database,self.root/'data',self.root/'reports',self.root/'backup')
        self.assertEqual(manifest['review_state']['workflow_events'],1)
        restore_backup(self.root/'backup',self.root/'restored')
        store=restored_store(self.root/'restored');store.clock=lambda:self.now
        workflow=TwoStageReview(store);state=workflow.state('003','RC_1')
        self.assertEqual(state['stage'],'pending_final')
        with self.assertRaises(PermissionError):store.save_feedback('003','RC_1','false_positive','Fake','Fake reason','')
        body=self.body();body['expected_scope_hash']=state['case_scope_hash'];body['expected_event_hash']=state['latest_event_hash']
        self.assertEqual(workflow.final_action('003','RC_1',self.chief,body)['stage'],'finalized')

    def test_backup_detects_a_tampered_workflow_log(self):
        from sme_fraud.review_backup import create_backup
        self.primary()
        with self.store.connection() as db:db.execute("UPDATE review_workflow_events SET data=replace(data,'Kế toán A','Other')")
        with self.assertRaises(ValueError):create_backup(self.store.database,self.root/'data',self.root/'reports',self.root/'backup')

    def test_http_uses_trusted_provider_and_anonymous_can_read_without_writing(self):
        actors={'A':self.accountant,'B':self.chief}
        server=make_server(self.store,port=0,review_workflow=self.workflow,
            identity_provider=lambda request:actors.get(request.headers.get('X-Fixture-User')))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def call(method,path,body=None,actor='',token=''):
            c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
            c.request(method,path,json.dumps(body) if body is not None else None,{'Content-Type':'application/json','X-CSRF-Token':token,'X-Fixture-User':actor})
            r=c.getresponse();result=r.status,json.loads(r.read());c.close();return result
        try:
            code,meta=call('GET','/api/meta');token=meta['csrf_token']
            self.assertEqual(code,200);self.assertIsNone(meta['review_workflow']['principal'])
            code,detail=call('GET','/api/case?scenario=003&id=RC_1');self.assertEqual(code,200)
            body=dict(scenario='003',case_id='RC_1',**self.body())
            self.assertEqual(call('POST','/api/review-workflow/primary',body,token=token)[0],403)
            self.assertEqual(call('POST','/api/review-workflow/primary',body,actor='A',token=token)[0],200)
            self.assertEqual(call('POST','/api/feedback',dict(scenario='003',case_id='RC_1',decision='false_positive',reviewer='Fake',reason='Fake',expected_hash=''),actor='B',token=token)[0],403)
            body=dict(scenario='003',case_id='RC_1',**self.body())
            self.assertEqual(call('POST','/api/review-workflow/finalize',body,actor='A',token=token)[0],403)
            self.assertEqual(call('POST','/api/review-workflow/finalize',body,actor='B',token=token)[0],200)
        finally:server.shutdown();server.server_close();thread.join(5)


if __name__=='__main__':unittest.main()
