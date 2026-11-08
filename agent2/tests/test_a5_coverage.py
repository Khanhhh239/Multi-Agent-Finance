"""Coverage denominators, causal readiness and review visibility independent of hits."""
import copy
from datetime import timedelta
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from sme_fraud.a5_coverage import transaction_record, coverage, write_coverage
from sme_fraud.dynamic_thresholds import DynamicThresholds
from sme_fraud.rule_audit_cases import Case
from sme_fraud.review_store import ReviewStore, csv_rows, source_fingerprint
from sme_fraud.review_server import make_server
from sme_fraud.run_a5_coverage import guard
from test_dynamic_thresholds import NOW, sample, policy
from test_review import make_fixture


def tx(identity='CURRENT', **values):
    return dict(dict(company_id='C001', transaction_id=identity, posted_at=NOW.isoformat(),
                     is_financial_entry=1, amount_vnd=5_000_000), **values)


def evaluate(rows, row=None):
    p = policy()
    engine = DynamicThresholds(rows, p)
    diagnostics = {}
    row = row or tx()
    signal, evidence = engine.evaluate_transaction(row, diagnostics=diagnostics)
    return transaction_record(row, signal, evidence, diagnostics, p), evidence


class A5CoverageTest(unittest.TestCase):
    def history(self):
        return [sample('H1', NOW-timedelta(days=2), 1_000_000),
                sample('H2', NOW-timedelta(days=1), 1_000_000)]

    def test_diagnostics_do_not_change_selection_or_evidence(self):
        rows = self.history()+[sample('CURRENT', NOW, 5_000_000)]
        plain = DynamicThresholds(rows, policy()).evaluate_transaction(tx())
        record, evidence = evaluate(rows)
        self.assertEqual(plain, (record['amount_signal'], evidence))
        self.assertTrue(record['ready'])
        self.assertEqual(record['selected']['sample_count'], 2)

    def test_current_and_simultaneous_observations_are_not_history(self):
        rows = [sample('SAME', NOW, 1_000_000), sample('CURRENT', NOW, 5_000_000)]
        record, _ = evaluate(rows)
        self.assertEqual(record['status'], 'insufficient_history')
        self.assertEqual(record['selected']['sample_count'], 0)
        self.assertIsNone(record['selected']['threshold_vnd'])
        self.assertFalse(record['amount_signal'])

    def test_partial_history_counts_once_per_transaction(self):
        rows = self.history()+[sample('A', NOW, 5_000_000, source_transaction_id='CURRENT'),
            sample('B', NOW, 8_000_000, source_transaction_id='CURRENT', account_code='6422')]
        record, _ = evaluate(rows)
        self.assertEqual(record['status'], 'partial_history')
        total = coverage([record])['totals']
        self.assertEqual((total['ready_transactions'], total['fully_ready_transactions']), (1, 0))
        self.assertEqual((total['observations'], total['ready_observations']), (2, 1))
        self.assertEqual(total['ready_over_eligible'], 1)

    def test_expense_preference_does_not_count_ready_cash_as_ready_expense(self):
        rows = [sample('H1', NOW-timedelta(days=2), 1, measurement='cash_outflow'),
                sample('H2', NOW-timedelta(days=1), 1, measurement='cash_outflow'),
                sample('CASH', NOW, 5_000_000, measurement='cash_outflow', source_transaction_id='CURRENT'),
                sample('EXPENSE', NOW, 5_000_000, source_transaction_id='CURRENT')]
        record, _ = evaluate(rows)
        self.assertEqual(record['candidate_count'], 1)
        self.assertEqual(record['status'], 'insufficient_history')
        self.assertEqual(record['selected']['measurement'], 'expense_debit')

    def test_late_source_and_absent_source_are_distinct_and_excluded_from_eligible(self):
        late, _ = evaluate([sample('CURRENT', NOW, 5_000_000, observed_at=(NOW+timedelta(days=1)).isoformat())])
        absent, _ = evaluate([])
        self.assertEqual(late['status'], 'not_observed_at_cutoff')
        self.assertEqual(absent['status'], 'not_applicable')
        total = coverage([late, absent])['totals']
        self.assertEqual(total['eligible_transactions'], 0)
        self.assertIsNone(total['ready_over_eligible'])

    def test_nonround_ready_transaction_is_outside_a5_gate(self):
        record, _ = evaluate(self.history()+[sample('CURRENT', NOW, 5_000_001)], tx(amount_vnd=5_000_001))
        self.assertTrue(record['ready'])
        self.assertTrue(record['amount_signal'])
        self.assertFalse(record['a5_predicate'])
        self.assertEqual(coverage([record])['totals']['a5_gate_eligible_transactions'], 0)

    def test_rule_engine_exports_cold_and_nohit_rows_as_well_as_hits(self):
        case = Case()
        for i in range(3):
            case.pay(case.at-timedelta(days=4-i), 1_000_000, kind='cash_expense')
        case.pay(amount=1_000_000, kind='cash_expense')
        case.config = dict(noise_policy='phase2', amount_baseline='rolling_account',
                           dynamic_min_samples=2, dynamic_cycle_enabled=False)
        result = case.score()
        rows = result['a5_evaluations']
        self.assertEqual(len(rows), 4)
        self.assertEqual([r['status'] for r in rows], ['insufficient_history']*2+['ready']*2)
        self.assertFalse(any(r['hit_emitted'] for r in rows))
        with tempfile.TemporaryDirectory() as folder:
            write_coverage(Path(folder), result)
            self.assertEqual(json.loads((Path(folder)/'a5_coverage.json').read_text(encoding='utf-8'))['totals']['ready_over_eligible'], .5)
            self.assertEqual(len(list(csv_rows(Path(folder)/'a5_evaluations.csv'))), 4)

    def test_frozen_roots_rejected_before_reading(self):
        with self.assertRaises(ValueError):
            guard(Path(__file__).resolve().parents[1]/'data/synthetic_sources_20261017_v2/sme_fraud_005/new')


class A5ReviewTest(unittest.TestCase):
    def test_api_visibility_cache_invalidation_and_old_snapshot_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data, report = make_fixture(root)
            store = ReviewStore(root/'data', root/'reports', root/'cache.sqlite3')
            store.prepare()
            self.assertFalse(store.a5_coverage('003')['available'])
            self.assertIsNone(store.transaction('003', 'T1')['a5_evaluation'])
            before = source_fingerprint(data, report)
            records = []
            for row in csv_rows(data/'transactions.csv'):
                record, _ = evaluate([], row)
                records.append(record)
            write_coverage(report, dict(a5_evaluations=records))
            self.assertNotEqual(before, source_fingerprint(data, report))
            store.prepare()
            self.assertEqual(store.detail('003', 'RC_1')['a5_evaluations'][0]['status'], 'not_applicable')
            self.assertEqual(store.transaction('003', 'T1')['a5_evaluation']['status'], 'not_applicable')
            server = make_server(store, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
                connection.request('GET', '/api/a5-coverage?scenario=003')
                response = connection.getresponse()
                payload = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual(payload['totals']['transactions'], 8)
                self.assertEqual(payload['totals']['eligible_transactions'], 0)
                connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
