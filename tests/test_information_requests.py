"""Operational document workflow: scope, audit, concurrency and immutable risk."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import csv
import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from sme_fraud.generate import write_csv
from sme_fraud.review_store import ReviewStore
from sme_fraud.review_server import make_server
from sme_fraud.review_support import linked_returns
from test_review import make_fixture


class InformationRequestTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.data,self.report=make_fixture(self.root)
        self.now=datetime.fromisoformat('2026-10-19T09:00:00+07:00')
        self.store=self.restart()
        self.store.prepare()

    def tearDown(self):
        self.temp.cleanup()

    def restart(self):
        return ReviewStore(self.root/'data',self.root/'reports',self.root/'review.sqlite3',clock=lambda:self.now)

    def create(self,case='RC_1',**values):
        body=dict(action='create',case_scope_hash=self.store.detail('003',case)['case']['review_scope_hash'],
            expected_hash='',actor='SIM_TEST',reason='Đối chiếu tài liệu mô phỏng',owner='SIM_OWNER',
            due_at=(self.now+timedelta(days=2)).isoformat(),requested_documents='Hóa đơn gốc và phiếu chi')
        body.update(values)
        return self.store.update_information_request('003',case,body)

    def update(self,old,action,case='RC_1',**values):
        body=dict(action=action,request_id=old['request_id'],expected_hash=old['event_hash'],
            case_scope_hash=self.store.detail('003',case)['case']['review_scope_hash'],
            actor='SIM_TEST',reason='Nội dung đã đối chiếu theo chứng từ mô phỏng')
        body.update(values)
        return self.store.update_information_request('003',case,body)

    def test_end_to_end_requires_review_then_reasoned_conclusion(self):
        risk=self.store.detail('003','RC_1')
        files=['case_queue.csv','rule_hits.jsonl','case_events.csv']
        before={f:hashlib.sha256((self.report/f).read_bytes()).hexdigest() for f in files}
        opened=self.create()
        detail=self.store.detail('003','RC_1')
        self.assertEqual(detail['case']['status'],'awaiting_information')
        self.assertEqual(detail['information_requests']['active_count'],1)
        self.assertEqual(detail['information_requests']['requests'][0]['age_hours'],0)
        self.assertEqual(detail['information_requests']['requests'][0]['created_at'],'2026-10-19T09:00:00+07:00')
        self.assertEqual(detail['case']['max_score'],risk['case']['max_score'])
        self.assertEqual(detail['hits'],risk['hits'])
        with self.assertRaises(RuntimeError):
            self.store.save_feedback('003','RC_1','false_positive','SIM_TEST','Chưa rà tài liệu','')
        gap=self.store.save_feedback('003','RC_1','information_gap','SIM_TEST','Còn thiếu hóa đơn gốc','')
        received=self.update(opened,'receive',evidence_refs=['DOC_SIM_1','DOC_SIM_1'])
        self.assertEqual(received['evidence_refs'],['DOC_SIM_1'])
        self.store=self.restart()
        self.store.prepare()
        self.assertTrue(self.store.detail('003','RC_1')['information_requests']['ready_for_rereview'])
        with self.assertRaises(RuntimeError):
            self.store.save_feedback('003','RC_1','false_positive','SIM_TEST','Nhận chưa đủ để kết luận',gap['event_hash'])
        self.update(received,'review')
        with self.assertRaises(ValueError):
            self.store.save_feedback('003','RC_1','false_positive','SIM_TEST','',gap['event_hash'])
        final=self.store.save_feedback('003','RC_1','false_positive','SIM_TEST','Đã đối chiếu DOC_SIM_1, nghĩa vụ chi khớp',gap['event_hash'])
        self.assertEqual(self.store.detail('003','RC_1')['case']['status'],'closed')
        self.assertEqual(len(self.store.detail('003','RC_1')['information_requests']['history']),3)
        with self.assertRaises(RuntimeError):
            self.create()
        self.store.save_feedback('003','RC_1','information_gap','SIM_TEST','Tài liệu mới cần bổ sung',final['event_hash'])
        self.create()
        self.assertEqual(before,{f:hashlib.sha256((self.report/f).read_bytes()).hexdigest() for f in files})

    def test_operational_deadlines_do_not_follow_historical_transaction_or_score(self):
        event=self.create()
        self.now+=timedelta(days=3)
        detail=self.store.detail('003','RC_1')
        info=detail['information_requests']
        self.assertEqual((info['overdue_count'],info['requests'][0]['age_hours']),(1,72))
        queued=next(r for r in self.store.list_cases('003')['items'] if r['case_id']=='RC_1')
        self.assertEqual(queued['collection_summary']['overdue_count'],1)
        self.assertEqual(queued['max_score'],detail['case']['max_score'])
        self.update(event,'cancel')
        self.assertEqual(self.store.detail('003','RC_1')['information_requests']['active_count'],0)

    def test_validation_does_not_create_partial_events(self):
        bad=[dict(owner=''),dict(requested_documents=''),dict(actor=''),dict(reason=''),
             dict(due_at='2026-10-20T12:00:00'),dict(due_at=self.now.isoformat()),
             dict(due_at='2025-01-01T00:00:00+07:00'),dict(owner='x'*101),dict(action='approve')]
        for values in bad:
            with self.subTest(values=values),self.assertRaises(ValueError):
                self.create(**values)
        self.assertEqual(self.store.detail('003','RC_1')['information_requests']['history'],[])
        opened=self.create()
        with self.assertRaises(RuntimeError):self.update(opened,'review')
        for refs in ([],[''],['x']*21,'DOC'):
            with self.subTest(refs=refs),self.assertRaises(ValueError):
                self.update(opened,'receive',evidence_refs=refs)

    def test_assign_reopen_and_terminal_state_preserve_history(self):
        opened=self.create()
        assigned=self.update(opened,'assign',owner='SIM_OWNER_2',due_at=(self.now+timedelta(days=4)).isoformat())
        received=self.update(assigned,'receive',evidence_refs=['DOC_A'])
        reopened=self.update(received,'reopen')
        self.assertEqual(reopened['evidence_refs'],['DOC_A'])
        cancelled=self.update(reopened,'cancel')
        with self.assertRaises(RuntimeError):self.update(cancelled,'assign',owner='SIM_OTHER',due_at=(self.now+timedelta(days=5)).isoformat())
        info=self.store.detail('003','RC_1')['information_requests']
        self.assertEqual(len(info['history']),5)
        self.assertEqual(info['requests'][0]['owner'],'SIM_OWNER_2')
        self.assertEqual(info['active_count'],0)

    def test_concurrent_stale_updates_have_one_winner(self):
        opened=self.create()
        def attempt(_):
            try:self.update(opened,'receive',evidence_refs=['DOC_A']);return 'saved'
            except RuntimeError:return 'stale'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(attempt,range(2))),['saved','stale'])
        self.assertEqual(len(self.store.detail('003','RC_1')['information_requests']['history']),2)

    def test_final_conclusion_racing_new_request_cannot_leave_closed_with_open_task(self):
        def attempt(action):
            try:
                if action=='request':self.create()
                else:self.store.save_feedback('003','RC_1','false_positive','SIM_TEST','Đã đối chiếu độc lập','')
                return 'saved'
            except RuntimeError:return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(attempt,['request','close'])),['conflict','saved'])
        detail=self.store.detail('003','RC_1')
        self.assertFalse(detail['case']['status']=='closed' and detail['information_requests']['active_count'])

    def test_return_chain_traverses_reversal_and_rejects_cross_company_links(self):
        rows=[dict(transaction_id=k,company_id=c,journal_document_id='J_'+k,original_transaction_id=o)
              for k,c,o in [('ORIGINAL','C001',''),('RETURN','C001','ORIGINAL'),('REVERSAL','C001','RETURN'),('OTHER','C002','ORIGINAL')]]
        related=linked_returns(rows,[],{'ORIGINAL'})
        self.assertEqual({r['transaction_id'] for r in related},{'RETURN','REVERSAL'})
        links=[dict(company_id='C002',source_document_id='J_ORIGINAL',target_document_id='J_REVERSAL',link_type='reversal_of')]
        for r in rows:r['original_transaction_id']=''
        self.assertEqual(linked_returns(rows,links,{'ORIGINAL'}),[])

    def test_other_company_case_and_changed_scope_do_not_inherit(self):
        opened=self.create()
        for case in ('RC_2','RC_7'):
            with self.assertRaises(RuntimeError):self.update(opened,'cancel',case=case)
        self.assertEqual(self.store.detail('003','RC_7')['information_requests']['history'],[])
        with self.assertRaises(RuntimeError):self.create(case_scope_hash='stale')
        with (self.report/'case_queue.csv').open(encoding='utf-8-sig',newline='') as stream:
            cases=list(csv.DictReader(stream))
        cases[0]['max_score']='99'
        write_csv(self.report/'case_queue.csv',cases)
        self.store.prepare()
        info=self.store.detail('003','RC_1')['information_requests']
        self.assertEqual(info['active_count'],0)
        self.assertFalse(info['requests'][0]['applies_to_current_scope'])
        with self.assertRaises(RuntimeError):self.update(opened,'cancel')
        self.create()
        self.assertEqual(len(self.store.detail('003','RC_1')['information_requests']['requests']),2)

    def test_tampered_audit_fails_closed(self):
        self.create()
        with self.store.connection() as db:
            db.execute("UPDATE information_request_events SET data=replace(data,'SIM_OWNER','TAMPERED')")
        with self.assertRaises(ValueError):self.store.detail('003','RC_1')
        with self.assertRaises(ValueError):self.store.list_cases('003')
        with self.assertRaises(ValueError):self.create()

    def test_optional_support_and_related_return_are_company_scoped(self):
        self.assertEqual(self.store.detail('003','RC_1')['review_support']['invoices'],[])
        with (self.data/'transactions.csv').open(encoding='utf-8-sig',newline='') as stream:
            rows=list(csv.DictReader(stream))
        rows[1]['invoice_id']='INV_TEST'
        original=rows[1]
        returned=dict(original,transaction_id='RETURN_SIM',journal_document_id='J_RETURN',
            original_transaction_id='T1',posted_at='2025-09-01T12:00:00+07:00',debit_account='111',credit_account='642',payment_channel='journal')
        rows=[dict(r,original_transaction_id=r.get('original_transaction_id',''),invoice_id=r.get('invoice_id','')) for r in rows]+[returned]
        write_csv(self.data/'transactions.csv',rows)
        write_csv(self.data/'invoices.csv',[dict(company_id=c,invoice_id='INV_TEST',issued_at=original['posted_at'],recorded_at=original['posted_at']) for c in ('C001','C002')])
        write_csv(self.data/'invoice_versions.csv',[dict(company_id=c,invoice_id='INV_TEST',revision_id='REV_'+c,observed_at=original['posted_at'],evidence_id='SRC_'+c) for c in ('C001','C002')])
        write_csv(self.data/'document_links.csv',[dict(source_document_id='J1',target_document_id='J_RETURN',link_type='reversal_of')])
        self.store.prepare()
        detail=self.store.detail('003','RC_1')
        self.assertEqual([r['transaction_id'] for r in detail['transactions']],['T1'])
        self.assertEqual({r['transaction_id'] for r in detail['review_support']['transactions']},{'T1','RETURN_SIM'})
        self.assertEqual([r['company_id'] for r in detail['review_support']['invoices']],['C001'])
        self.assertEqual([r['revision_id'] for r in detail['review_support']['invoice_versions']],['REV_C001'])
        self.assertEqual(self.store.transaction('003','RETURN_SIM')['original_transaction_id'],'T1')
        self.assertEqual(detail['hits'][0]['points'],20)

    def test_http_requires_csrf_and_returns_request_history(self):
        server=make_server(self.store,port=0,qa=True)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(method,path,body=None,headers=None):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
            connection.request(method,path,json.dumps(body) if body else None,headers or {})
            response=connection.getresponse();data=response.read();connection.close()
            return response.status,data
        try:
            status,raw=request('GET','/api/meta');self.assertEqual(status,200)
            token=json.loads(raw)['csrf_token']
            detail=self.store.detail('003','RC_1')
            body=dict(scenario='003',case_id='RC_1',action='create',expected_hash='',case_scope_hash=detail['case']['review_scope_hash'],
                actor='SIM_API',reason='Kiểm thử luồng API',owner='SIM_OWNER',requested_documents='Hóa đơn gốc',due_at=(self.now+timedelta(days=1)).isoformat())
            self.assertEqual(request('POST','/api/information-requests',body,{'Content-Type':'application/json'})[0],403)
            headers={'Content-Type':'application/json','X-CSRF-Token':token}
            self.assertEqual(request('POST','/api/information-requests',body,dict(headers,Origin='http://other.invalid'))[0],403)
            status,raw=request('POST','/api/information-requests',body,headers);self.assertEqual(status,200,raw)
            self.assertEqual(json.loads(raw)['status'],'open')
            status,raw=request('GET','/api/case?scenario=003&id=RC_1');self.assertEqual(json.loads(raw)['information_requests']['active_count'],1)
            self.assertEqual(request('GET','/review_explanations.js')[0],200)
        finally:
            server.shutdown();server.server_close();thread.join(5)
