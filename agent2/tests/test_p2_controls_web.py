"""Actual frozen fixtures, UAT persistence, scope isolation and HTTP boundaries."""
from concurrent.futures import ThreadPoolExecutor
import csv
import http.client
import io
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest

from sme_fraud.feature_contract import sha
from sme_fraud.p2_controls_web import P2Controls
from sme_fraud.p2_controls_server import make_server
from p2_test_fixture import SOURCE, REPORT


class P2Fixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = P2Controls(SOURCE, REPORT, self.root/'reviews.sqlite3')

    def tearDown(self):
        self.temp.cleanup()

    def body(self, identity='FULL_ABOVE', **values):
        return dict(dict(snapshot_id=self.store.snapshot_id, control_id=identity, verdict='passed',
                         reviewer='SIM_UAT_TEST', reason='Kiểm thử tự động, không phải nghiệm thu độc lập.', expected_hash=''), **values)


class P2ControlsWebTest(P2Fixture, unittest.TestCase):
    def test_complete_population_includes_no_p2_transactions(self):
        meta = self.store.metadata()
        self.assertEqual((meta['controls'], meta['transactions'], meta['matched_transactions']), (32, 73, 73))
        self.assertEqual(meta['category_counts'], dict(no_p2=43, information_request=14, vat_document_review=15, verified_internal_breach=1))
        self.assertEqual(meta['reviewed_controls'], 0)
        no_p2 = {r['control_id'] for r in self.store.list_controls(category='no_p2')['items']}
        self.assertIn('FULL_BELOW', no_p2)
        self.assertNotIn('FULL_ABOVE', no_p2)
        self.assertEqual(self.store.list_controls(group='full_invoice')['total'], 6)

    def test_reused_transaction_ids_never_mix_controls(self):
        below, above = (self.store.detail(key) for key in ('FULL_BELOW', 'FULL_ABOVE'))
        self.assertEqual(below['transactions'][0]['transaction_id'], above['transactions'][0]['transaction_id'])
        self.assertFalse(below['comparisons'][0]['actual']['p2_present'])
        self.assertEqual(above['comparisons'][0]['actual']['points'], 8)
        self.assertNotEqual(below['transactions'][0]['amount_vnd'], above['transactions'][0]['amount_vnd'])
        below['transactions'][0]['amount_vnd'] = 0
        self.assertNotEqual(self.store.detail('FULL_BELOW')['transactions'][0]['amount_vnd'], 0)
        with self.assertRaises(KeyError):
            self.store.detail('../sme_fraud_005')

    def test_review_sources_explain_exceptions_and_recurrence_without_rescoring(self):
        mixed=self.store.detail('INSTALL_MIXED')
        self.assertEqual(mixed['supplier_payment_agreements'][0]['agreement_id'],'AGR_CONTROL')
        recurring=self.store.detail('RECUR_A5')
        self.assertEqual(recurring['recurring_payments'][0]['pattern_id'],'PAT_CONTROL')
        self.assertEqual(next(h['points'] for h in recurring['hits'] if h['rule_id']=='A5'),0)
        cash=self.store.detail('INSTALL_CASH')
        self.assertEqual([int(r['recurrence_points']) for r in cash['rule_scores']],[0,1])
        self.assertEqual([int(r['rule_score']) for r in cash['rule_scores']],[8,9])
        self.assertEqual(cash['invoice_versions'],[])
        self.assertTrue(all(p['purpose']=='display_policy_reference_only_no_rescoring' for p in cash['policy_context'].values()))
        self.assertEqual(sum(int(h['points']) for h in cash['hits'] if h['rule_id']=='P2'),16)

    def test_refund_preserves_original_p2_and_balanced_evidence(self):
        detail = self.store.detail('REFUND_FULL')
        outcomes = detail['comparisons']
        self.assertEqual([r['actual']['points'] for r in outcomes], [8, 0])
        self.assertTrue(detail['document_links'])
        for doc in detail['documents']:
            lines = [r for r in detail['lines'] if r['document_id'] == doc['document_id']]
            self.assertEqual(sum(r['debit_vnd'] for r in lines), sum(r['credit_vnd'] for r in lines))

    def test_reviews_survive_restart_and_do_not_modify_detector_artifacts(self):
        files = [SOURCE/'manifest.json', SOURCE/'expected_outcomes.json', REPORT/'predictions_frozen.json', REPORT/'FULL_ABOVE/case_queue.json']
        before = {str(p): sha(p) for p in files}
        first = self.store.save_review(self.body())
        restart = P2Controls(SOURCE, REPORT, self.root/'reviews.sqlite3')
        self.assertEqual(restart.detail('FULL_ABOVE')['review'], first)
        second = restart.save_review(self.body(verdict='needs_fix', expected_hash=first['event_hash'], reason='Kiểm thử chỉnh kết quả.'))
        self.assertEqual(len(restart.detail('FULL_ABOVE')['history']), 2)
        self.assertEqual(restart.list_controls(verdict='needs_fix')['items'][0]['review']['event_hash'], second['event_hash'])
        self.assertEqual(before, {str(p): sha(p) for p in files})
        with self.assertRaises(RuntimeError):
            restart.save_review(self.body())

    def test_required_reason_snapshot_binding_and_version_isolation(self):
        for values in ({'reason':''}, {'reviewer':''}, {'verdict':'confirmed_fraud'}, {'reason':'x'*2001}):
            with self.assertRaises(ValueError):
                self.store.save_review(self.body(**values))
        with self.assertRaises(RuntimeError):
            self.store.save_review(self.body(snapshot_id='stale'))
        self.store.save_review(self.body())
        original = self.store.snapshot_id
        self.store.snapshot_id='different-frozen-snapshot'
        self.assertEqual(self.store.metadata()['reviewed_controls'], 0)
        self.assertIsNone(self.store.detail('FULL_ABOVE')['review'])
        self.store.snapshot_id=original

    def test_parallel_stale_writes_accept_exactly_one(self):
        def save(_):
            try:
                self.store.save_review(self.body())
                return 'saved'
            except RuntimeError:
                return 'stale'
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(save, range(2)))
        self.assertEqual(sorted(results), ['saved', 'stale'])
        self.assertEqual(len(self.store.history()), 1)

    def test_audit_tamper_and_input_tamper_fail_closed(self):
        self.store.save_review(self.body())
        with self.store.connect() as db:
            db.execute("UPDATE reviews SET reason='tampered'")
        with self.assertRaises(ValueError):
            self.store.metadata()
        copied = self.root/'report'
        shutil.copytree(REPORT, copied)
        (copied/'FULL_ABOVE/rule_hits.json').write_text('[]', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            P2Controls(SOURCE, copied, self.root/'other.sqlite3')

    def test_database_cannot_be_inside_frozen_inputs(self):
        with self.assertRaises(ValueError):
            P2Controls(SOURCE, REPORT, SOURCE/'reviews.sqlite3')
        with self.assertRaises(ValueError):
            P2Controls(SOURCE, REPORT, REPORT/'reviews.sqlite3')


class P2ControlsHTTPTest(P2Fixture, unittest.TestCase):
    # HTTP tests reuse the actual immutable fixtures, with their own empty journal.
    def setUp(self):
        super().setUp()
        self.server = make_server(self.store, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=20)
        payload = json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None
        connection.request(method, path, body=payload, headers=headers or {})
        response = connection.getresponse()
        raw = response.read()
        content_type = response.getheader('Content-Type')
        status, policy = response.status, response.getheader('Content-Security-Policy')
        connection.close()
        return status, json.loads(raw) if 'application/json' in content_type else raw.decode('utf-8-sig'), policy

    def test_http_assets_detail_filters_and_csv(self):
        for path in ('/p2-controls', '/p2_controls.js', '/p2_controls.css', '/styles.css'):
            status, text, policy = self.request('GET', path)
            self.assertEqual(status, 200)
            self.assertTrue(text)
            self.assertIn("script-src 'self'", policy)
        status, page, _ = self.request('GET', '/api/p2-controls?group=refund_reversal')
        self.assertEqual(page['total'], 6)
        _, detail, _ = self.request('GET', '/api/p2-controls/detail?id=RECUR_A5')
        self.assertEqual(len(detail['transactions']), 23)
        self.assertTrue(detail['comparisons'][-1]['actual']['a5_suppressed'])
        _, csv_text, _ = self.request('GET', '/api/p2-controls/export?group=refund_reversal')
        self.assertEqual({r['control_id'] for r in csv.DictReader(io.StringIO(csv_text))}, {r['control_id'] for r in page['items']})
        self.assertEqual(self.request('GET', '/api/p2-controls/detail?id=../sme_fraud_005')[0], 404)

    def test_http_csrf_origin_stale_input_and_formula_safe_export(self):
        _, meta, _ = self.request('GET', '/api/p2-controls/meta')
        path = '/api/p2-controls/review'
        headers = {'Content-Type':'application/json', 'X-CSRF-Token':meta['csrf_token']}
        self.assertEqual(self.request('POST', path, self.body(), {'Content-Type':'application/json'})[0], 403)
        self.assertEqual(self.request('POST', path, self.body(), {**headers, 'Origin':'https://untrusted.example'})[0], 403)
        self.assertEqual(self.request('POST', path, [], headers)[0], 400)
        self.assertEqual(self.request('POST', path, self.body(reason=''), headers)[0], 400)
        self.assertEqual(self.request('POST', path, self.body(reason='=SUM(1,2)'), headers)[0], 200)
        self.assertEqual(self.request('POST', path, self.body(), headers)[0], 409)
        _, exported, _ = self.request('GET', '/api/p2-controls/export?verdict=passed')
        self.assertEqual(list(csv.DictReader(io.StringIO(exported)))[0]['reason'], "'=SUM(1,2)")

    def test_optional_mount_in_existing_case_management_server(self):
        from test_review import make_fixture
        from sme_fraud.review_store import ReviewStore
        from sme_fraud.review_server import make_server as case_server
        make_fixture(self.root)
        queue = ReviewStore(self.root/'data', self.root/'reports', self.root/'queue.sqlite3')
        queue.prepare()
        server = case_server(queue, 0, p2_controls=self.store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
            conn.request('GET', '/api/meta')
            meta = json.loads(conn.getresponse().read())
            self.assertTrue(meta['p2_controls_available'])
            conn.request('GET', '/p2-controls')
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIn('Đối chứng chi tiền mặt', response.read().decode('utf-8'))
            conn.request('POST', '/api/p2-controls/review', json.dumps(self.body()).encode('utf-8'),
                         {'Content-Type':'application/json','X-CSRF-Token':meta['csrf_token']})
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
