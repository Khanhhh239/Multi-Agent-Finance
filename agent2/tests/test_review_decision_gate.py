"""Web, public feedback API and actual CLI share one bound request-store gate."""
import contextlib
import csv
from datetime import datetime,timedelta
import io
import http.client
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from sme_fraud.feedback import DECISIONS,record_feedback,read_audit,main
from sme_fraud.generate import write_csv
from sme_fraud.review_decision_gate import BINDING_FILE
from sme_fraud.review_store import ReviewStore
from sme_fraud.review_server import make_server
from test_review import make_fixture


class ReviewDecisionGateTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.data,self.report=make_fixture(self.root)
        self.now=datetime.fromisoformat('2026-10-19T09:00:00+07:00')
        self.store=ReviewStore(self.root/'data',self.root/'reports',self.root/'review.sqlite3',clock=lambda:self.now)
        self.store.prepare()

    def tearDown(self):self.temp.cleanup()

    def request(self,case='RC_1'):
        detail=self.store.detail('003',case)
        return self.store.update_information_request('003',case,dict(action='create',expected_hash='',
            case_scope_hash=detail['case']['review_scope_hash'],actor='SIM_ACTOR',owner='SIM_OWNER',
            requested_documents='SIM hóa đơn gốc',reason='SIM cần đối chiếu',due_at=(self.now+timedelta(days=2)).isoformat()))

    def update(self,event,action,**values):
        return self.store.update_information_request('003','RC_1',dict(action=action,request_id=event['request_id'],
            expected_hash=event['event_hash'],case_scope_hash=self.store.detail('003','RC_1')['case']['review_scope_hash'],
            actor='SIM_ACTOR',reason='SIM đã đối chiếu',**values))

    def cli_api(self,decision,**values):
        return record_feedback(self.report,'RC_1',decision,'SIM_CLI','SIM đối chiếu có lý do',self.now.isoformat(),**values)

    def test_every_final_decision_is_blocked_in_both_paths_while_open(self):
        self.request()
        before=read_audit(self.report/'feedback_audit.jsonl')
        for decision in DECISIONS-{'information_gap'}:
            with self.subTest(decision=decision):
                with self.assertRaisesRegex(RuntimeError,'Còn yêu cầu tài liệu'):self.cli_api(decision)
                with self.assertRaisesRegex(RuntimeError,'Còn yêu cầu tài liệu'):
                    self.store.save_feedback('003','RC_1',decision,'SIM_WEB','SIM lý do','')
        self.assertEqual(read_audit(self.report/'feedback_audit.jsonl'),before)
        self.assertEqual(self.store.detail('003','RC_1')['case']['status'],'awaiting_information')

    def test_received_is_not_reviewed_and_information_gap_stays_allowed(self):
        opened=self.request();received=self.update(opened,'receive',evidence_refs=['SIM_DOC'])
        gap=self.cli_api('information_gap')
        with self.assertRaises(RuntimeError):self.cli_api('false_positive')
        self.update(received,'review')
        saved=self.cli_api('false_positive',expected_hash=gap['event_hash'])
        self.assertEqual(self.store.detail('003','RC_1')['case']['feedback']['event_hash'],saved['event_hash'])

    def test_reasoned_cancellation_allows_explicit_final_conclusion(self):
        opened=self.request();self.update(opened,'cancel')
        saved=self.cli_api('non_compliance')
        self.assertEqual(saved['decision'],'non_compliance')
        self.assertEqual(len(self.store.detail('003','RC_1')['information_requests']['history']),2)

    def test_missing_binding_or_database_is_never_treated_as_no_requests(self):
        self.request();path=self.report/BINDING_FILE;content=path.read_bytes();path.unlink()
        with self.assertRaises(RuntimeError):self.cli_api('false_positive')
        with self.assertRaises(RuntimeError):self.store.save_feedback('003','RC_1','false_positive','SIM','SIM reason','')
        with self.assertRaises(RuntimeError):self.store.prepare()
        path.write_bytes(content)
        with patch.object(Path,'is_file',lambda p:False if p.resolve()==self.store.database.resolve() else original(p)):
            with self.assertRaisesRegex(RuntimeError,'Không tìm thấy SQLite'):self.cli_api('false_positive')

    def test_wrong_database_cannot_bypass_the_registered_store(self):
        self.request()
        other=self.root/'other.sqlite3'
        connection=sqlite3.connect(other);connection.close()
        with self.assertRaisesRegex(RuntimeError,'SQLite khác'):self.cli_api('false_positive',database=other)
        duplicate=ReviewStore(self.root/'data',self.root/'reports',other,clock=lambda:self.now)
        with self.assertRaises(RuntimeError):duplicate.prepare()
        self.assertEqual(self.store.detail('003','RC_1')['information_requests']['active_count'],1)

    def test_tampered_binding_or_request_history_fails_closed(self):
        self.request();path=self.report/BINDING_FILE
        content=path.read_text(encoding='utf-8');path.write_text(content.replace('003','001'),encoding='utf-8')
        with self.assertRaises(ValueError):self.cli_api('false_positive')
        path.write_text(content,encoding='utf-8')
        with self.store.connection() as db:
            db.execute("UPDATE information_request_events SET data=replace(data,'SIM_OWNER','TAMPERED')")
        for decision in ('false_positive','information_gap'):
            with self.assertRaises(ValueError):self.cli_api(decision)

    def test_optimistic_hash_and_required_reason_are_shared(self):
        first=self.cli_api('information_gap',expected_hash='')
        with self.assertRaises(RuntimeError):self.cli_api('false_positive',expected_hash='')
        with self.assertRaises(ValueError):
            record_feedback(self.report,'RC_1','false_positive','SIM','',self.now.isoformat())
        saved=self.cli_api('false_positive',expected_hash=first['event_hash'])
        self.assertEqual(saved['previous_hash'],first['event_hash'])

    def test_actual_cli_process_rejects_pending_request_without_appending_audit(self):
        self.request()
        args=[sys.executable,'-X','utf8','-B','-m','sme_fraud.feedback','--report',str(self.report),'--case-id','RC_1',
              '--decision','false_positive','--reviewer','SIM_CLI','--reason','SIM kiểm thử chứng từ',
              '--reviewed-at',self.now.isoformat()]
        blocked=subprocess.run(args,cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,encoding='utf-8')
        self.assertNotEqual(blocked.returncode,0)
        self.assertIn('RuntimeError',blocked.stderr)
        self.assertEqual(read_audit(self.report/'feedback_audit.jsonl'),[])
        args[args.index('false_positive')]='information_gap'
        allowed=subprocess.run(args,cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(allowed.returncode,0,allowed.stderr)
        self.assertEqual(json.loads(allowed.stdout)['decision'],'information_gap')
        self.assertTrue(allowed.stdout.isascii())
        self.assertEqual(json.loads(allowed.stdout)['reason'],'SIM kiểm thử chứng từ')

    def test_http_uses_the_same_gate_and_allows_missing_information_notes(self):
        self.request();server=make_server(self.store,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def call(method,path,body=None,token=''):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            connection.request(method,path,json.dumps(body) if body is not None else None,
                {'Content-Type':'application/json','X-CSRF-Token':token})
            response=connection.getresponse();result=(response.status,json.loads(response.read()));connection.close();return result
        try:
            _,meta=call('GET','/api/meta')
            body=dict(scenario='003',case_id='RC_1',decision='false_positive',reviewer='SIM_WEB',reason='SIM đã đối chiếu',expected_hash='')
            code,result=call('POST','/api/feedback',body,meta['csrf_token'])
            self.assertEqual(code,409);self.assertIn('Còn yêu cầu tài liệu',result['error'])
            self.assertEqual(read_audit(self.report/'feedback_audit.jsonl'),[])
            body['decision']='information_gap'
            code,result=call('POST','/api/feedback',body,meta['csrf_token'])
            self.assertEqual(code,200);self.assertEqual(result['decision'],'information_gap')
        finally:server.shutdown();server.server_close();thread.join(5)

    def test_old_alias_does_not_escape_a_pending_scope(self):
        self.request()
        with (self.report/'case_queue.csv').open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
        rows[0]['case_id']='RC_RENAMED';write_csv(self.report/'case_queue.csv',rows)
        self.store.prepare()
        with self.assertRaisesRegex(RuntimeError,'Còn yêu cầu tài liệu'):self.cli_api('false_positive')

    def test_no_store_legacy_report_can_only_collect_missing_information(self):
        legacy=self.root/'legacy';legacy.mkdir()
        write_csv(legacy/'case_queue.csv',[dict(case_id='OLD',last_seen_at='2025-01-01T00:00:00+07:00')])
        record_feedback(legacy,'OLD','information_gap','SIM','SIM missing proof',self.now.isoformat())
        with self.assertRaisesRegex(RuntimeError,'SQLite có thẩm quyền'):
            record_feedback(legacy,'OLD','false_positive','SIM','SIM final reason',self.now.isoformat())

    def test_cli_main_supports_explicit_database_and_expected_hash(self):
        args=['feedback','--report',str(self.report),'--case-id','RC_1','--decision','information_gap',
              '--reviewer','SIM_CLI','--reason','SIM missing proof','--database',str(self.store.database),'--expected-hash','']
        with patch('sys.argv',args),contextlib.redirect_stdout(io.StringIO()) as captured:main()
        self.assertEqual(json.loads(captured.getvalue())['decision'],'information_gap')


original=Path.is_file
