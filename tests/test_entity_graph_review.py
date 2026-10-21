"""Graph JSON through the real SQLite review cache and local HTTP API."""
import csv
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from sme_fraud.generate import write_csv
from sme_fraud.review_server import make_server
from sme_fraud.review_store import ReviewStore
from test_review import make_fixture


class EntityGraphReviewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data, self.report = make_fixture(self.root)
        for name in ('employees', 'vendors'):
            with (self.data/f'{name}.csv').open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            for row in rows:
                row.update(bank_account='00123456789', bank_code='BANK_A', phone='0912345678',
                           address='Số 1 Đường A', tax_code='0100000001' if name == 'vendors' else '0123456789')
            write_csv(self.data/f'{name}.csv', rows)
        self.store = ReviewStore(self.root/'data', self.root/'reports', self.root/'review.sqlite3')
        self.store.prepare()

    def tearDown(self):
        self.temp.cleanup()

    def test_case_detail_adds_typed_context_without_replacing_rule_proofs(self):
        detail = self.store.detail('003', 'RC_1')
        network = detail['entity_network']
        self.assertEqual(network['scope']['as_of'], detail['case']['last_seen_at'])
        self.assertEqual({n['type'] for n in network['nodes']},
                         {'employee', 'vendor', 'bank_account', 'phone', 'address', 'tax_code'})
        self.assertTrue(any(f['type'] == 'vendor_employee_shared_phone' for f in network['findings']))
        self.assertEqual([h['rule_id'] for h in detail['hits']], ['P1'])
        self.assertEqual(detail['graph_edges'], [])

    def test_future_master_label_and_identity_are_excluded_from_old_case(self):
        path = self.data/'vendors.csv'
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        rows.append(dict(rows[0], name='FUTURE_NAME', phone='0988888888', recorded_at='2025-08-30T00:00:00+07:00'))
        write_csv(path, rows)
        self.store.prepare()
        detail = self.store.detail('003', 'RC_1')
        text = json.dumps(detail['entity_network'], ensure_ascii=False)
        self.assertNotIn('FUTURE_NAME', text)
        self.assertNotIn('0988888888', text)
        self.assertIn('<script>Đối tác</script>', text)

    def test_graph_cache_refresh_preserves_review_conclusion_and_case_identity(self):
        self.store.save_feedback('003', 'RC_1', 'false_positive', 'Reviewer', 'Đã đối chiếu chứng từ', expected_hash='')
        previous = self.store.detail('003', 'RC_1')['case']['feedback']['event_hash']
        write_csv(self.data/'entity_links.csv', [dict(company_id='C001', source_id='V01', target_id='0988888888',
            link_type='phone', observed_at='2025-08-01T00:00:00+07:00')])
        self.store.prepare()
        detail = self.store.detail('003', 'RC_1')
        self.assertEqual(detail['case']['feedback']['event_hash'], previous)
        self.assertEqual(detail['case']['case_id'], 'RC_1')
        self.assertFalse(any(f['type'] == 'vendor_employee_shared_phone' for f in detail['entity_network']['findings']))

    def test_cross_company_case_reference_is_reported_missing_not_linked(self):
        graph = self.store.detail('003', 'RC_7')['entity_network']
        self.assertFalse(graph['nodes'])
        self.assertTrue(graph['missing_seed_entities'])
        self.assertEqual(graph['scope']['company_id'], 'C002')

    def test_http_network_and_filtered_path_queries_and_invalid_scope(self):
        server = make_server(self.store, port=0, qa=True)
        thread = Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}/api/entity-graph?'
        query = dict(scenario='003', company='C001', as_of='2025-08-02T12:00:00+07:00',
                     entity_type='vendor', entity_id='V01')
        try:
            with urlopen(base+urlencode(query)) as response:
                network = json.load(response)
            self.assertTrue(network['nodes'])
            self.assertTrue(network['links'])
            with urlopen(base+urlencode(dict(query, target_type='employee', target_id='E01',
                                            relations='bank_account', depth=2))) as response:
                path = json.load(response)
            self.assertEqual(path['hops'], 2)
            self.assertTrue(path['found'])
            for changes in ({'company': 'NO_SUCH_COMPANY'}, {'as_of': 'invalid'}, {'max_nodes': 0},
                            {'scenario': '../../outside'}):
                with self.subTest(changes=changes), self.assertRaises(HTTPError) as error:
                    urlopen(base+urlencode(dict(query, **changes)))
                self.assertIn(error.exception.code, (400, 404))
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()
