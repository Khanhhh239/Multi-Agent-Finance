"""P2 evidence requests remain visible, persistent and outside urgent delivery."""
import csv
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from datetime import datetime

from test_review import make_fixture
from sme_fraud.generate import write_csv
from sme_fraud.review_store import ReviewStore
from sme_fraud.review_server import make_server
from sme_fraud.notifications import Notifications


class CashReviewFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data, self.report = make_fixture(self.root)
        with (self.report/'case_queue.csv').open(encoding='utf-8-sig', newline='') as stream:
            template = next(csv.DictReader(stream))
        case = dict(template, case_id='IR_CASH', transaction_ids='["T0"]', rule_ids='P2',
                    opened_at='2025-08-01T12:00:00+07:00', last_seen_at='2025-08-01T12:00:00+07:00',
                    case_type='information_request', source_status='information_gap', max_score=0,
                    priority='thap', status='awaiting_information', requires_rereview=1,
                    explanation_vi='Cần bổ sung bằng chứng cho khoản chi tiền mặt')
        write_csv(self.report/'case_queue.csv', [case])
        write_csv(self.report/'case_events.csv', [dict(case_id='IR_CASH', event='opened',
            event_at=case['opened_at'], transaction_id='T0', priority='thap', rule_score=0)])
        hit = dict(transaction_id='T0', company_id='C001', detected_at=case['opened_at'], rule_id='P2',
            rule_name='Chi tiền mặt cần rà soát', points=0, hard_trigger=0, suppressed_reason='',
            scoring_role='information_request', status='information_gap', signal=None,
            evidence=dict(review_category='information_request', missing_fields=['invoice_identity']),
            related_transaction_ids=[], graph_path=[])
        (self.report/'rule_hits.jsonl').write_text(json.dumps(hit)+'\n', encoding='utf-8')
        self.clock = lambda: datetime.fromisoformat('2026-10-18T09:00:00+07:00')
        self.restart()

    def restart(self):
        self.store = ReviewStore(self.root/'data', self.root/'reports', self.root/'review.sqlite3', clock=self.clock)
        self.store.prepare()
        self.notifications = Notifications(self.store, dict(dry_run=True, replay_existing=True))

    def tearDown(self):
        self.temp.cleanup()

    def test_zero_point_request_is_filterable_and_has_real_evidence_without_fake_feedback(self):
        page = self.store.list_cases('003', category='information_request', status='awaiting_information')
        self.assertEqual(page['total'], 1)
        self.assertEqual((page['items'][0]['max_score'], page['items'][0]['priority']), (0, 'thap'))
        self.assertEqual(self.store.list_cases('003', category='operational_review')['total'], 0)
        detail = self.store.detail('003', 'IR_CASH')
        self.assertEqual(detail['case']['status'], 'awaiting_information')
        self.assertFalse(detail['feedback_history'])
        self.assertEqual(len(detail['hits']), 1)
        self.assertEqual(len(detail['documents']), 1)
        self.assertEqual(detail['hits'][0]['points'], 0)
        with self.assertRaises(ValueError):
            self.store.list_cases('003', category='made_up')

    def test_request_never_generates_high_priority_job_and_shares_daily_cap(self):
        self.notifications.plan('003')
        jobs = self.notifications.status('003')['items']
        self.assertFalse(any(job['kind'] == 'high_priority' for job in jobs))
        weekly = [job for job in jobs if job['kind'] == 'weekly']
        self.assertTrue(weekly)
        self.assertEqual({ref['case_id'] for job in weekly for ref in job['case_refs']}, {'IR_CASH'})
        self.assertEqual(self.store.list_cases('003', daily=True)['total'], 1)
        admission = self.store.admit('003', 'IR_CASH')
        self.assertEqual(admission['used'], 1)

    def test_review_reason_and_request_status_persist_on_restart(self):
        self.store.save_feedback('003', 'IR_CASH', 'information_gap', 'TEST_REVIEWER', 'Cần bổ sung hóa đơn gốc.', '')
        self.restart()
        detail = self.store.detail('003', 'IR_CASH')
        self.assertEqual(detail['case']['status'], 'awaiting_information')
        self.assertEqual(detail['case']['feedback']['reason'], 'Cần bổ sung hóa đơn gốc.')
        self.assertEqual(detail['audit_integrity'], 'passed')

    def test_http_filter_and_csv_export_match_the_category(self):
        server = make_server(self.store, port=0, qa=True, notifications=self.notifications)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for path in ('/api/cases?scenario=003&category=information_request',
                         '/api/export?scenario=003&category=information_request'):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
                try:
                    connection.request('GET', path)
                    response = connection.getresponse()
                    body = response.read().decode('utf-8-sig')
                    self.assertEqual(response.status, 200)
                    if path.startswith('/api/cases'):
                        self.assertEqual(json.loads(body)['items'][0]['status'], 'awaiting_information')
                    else:
                        self.assertEqual([r['case_id'] for r in csv.DictReader(io.StringIO(body))], ['IR_CASH'])
                finally:
                    connection.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)

