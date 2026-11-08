"""Regression tests for evidence timing and lawful lookalikes, not mock scores."""
import copy
import unittest

from sme_fraud.features import build_features
from sme_fraud.generate import Generator
from sme_fraud.rules import normalize, score_rules
from sme_fraud.benford import bh_adjust, digits_test


class RulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = Generator(10_000, .005, 20261012, 2).finalize()
        cls.features = build_features(cls.tables)
        cls.result = score_rules(cls.tables, features=cls.features)
        cls.truth = {r['transaction_id']: r for r in cls.tables['labels']}

    def test_no_truth_or_partition_input(self):
        changed = dict(self.tables, labels=[], splits=[])
        self.assertEqual(score_rules(changed, features=self.features), self.result)

    def test_future_transactions_and_masters_cannot_change_past_alerts(self):
        cutoff = self.tables['transactions'][1800]['posted_at']
        short = copy.deepcopy(self.tables)
        short['transactions'] = [r for r in short['transactions'] if r['posted_at'] <= cutoff]
        for name, column in (('employees', 'recorded_at'), ('vendors', 'recorded_at'),
                             ('advances', 'recorded_at'), ('entity_links', 'observed_at'),
                             ('attendance', 'observed_at'), ('vendor_status_history', 'observed_at'),
                             ('bank_account_changes', 'observed_at'), ('advance_events', 'observed_at')):
            short[name] = [r for r in short[name] if r[column] <= cutoff]
        result = score_rules(short)
        self.assertEqual(result['scores'], [r for r in self.result['scores'] if r['posted_at'] <= cutoff])
        self.assertEqual(result['hits'], [r for r in self.result['hits'] if r['detected_at'] <= cutoff])

    def test_equal_timestamp_payment_does_not_retroactively_trigger_duplicate(self):
        row = next(r for r in self.tables['transactions'] if r['txn_type'] == 'vendor_payment')
        clone = dict(row, transaction_id='T_same_time')
        changed = dict(self.tables)
        changed['transactions'] = [r for r in self.tables['transactions'] if r['posted_at'] <= row['posted_at']] + [clone]
        short_features = [r for r in self.features if r['transaction_id'] in {t['transaction_id'] for t in changed['transactions']}]
        feature = next(r for r in self.features if r['transaction_id'] == row['transaction_id'])
        short_features.append(dict(feature, transaction_id=clone['transaction_id']))
        result = score_rules(changed, features=short_features)
        scores = {r['transaction_id']: r for r in result['scores']}
        expected = next(r for r in self.result['scores'] if r['transaction_id'] == row['transaction_id'])
        self.assertEqual(scores[row['transaction_id']], expected)
        self.assertNotIn('P1', scores[clone['transaction_id']]['rule_ids'])

    def test_lawful_self_approval_and_remote_payroll_are_exempt(self):
        for hit in self.result['hits']:
            hard = self.truth[hit['transaction_id']]['hard_negative_type']
            if hard in {'legitimate_self_approval', 'legitimate_period_close'} and hit['rule_id'] == 'C2':
                self.assertTrue(hit['suppressed_reason'])
                self.assertEqual(hit['hard_trigger'], 0)
            if hard == 'remote_employee_payroll':
                self.assertNotEqual(hit['rule_id'], 'E1')

    def test_verified_bank_change_and_installments_are_not_hard_triggers(self):
        for hit in self.result['hits']:
            hard = self.truth[hit['transaction_id']]['hard_negative_type']
            if hard == 'verified_bank_change' and hit['rule_id'] == 'B7':
                self.assertTrue(hit['suppressed_reason'])
                self.assertEqual(hit['hard_trigger'], 0)
            if hard == 'legitimate_installments':
                self.assertNotEqual(hit['rule_id'], 'P1')

    def test_risky_status_cannot_be_read_before_publication(self):
        late = {i for i, r in self.truth.items() if r['observability'] == 'registry_reported_later'}
        self.assertTrue(late)
        self.assertFalse(any(h['rule_id'] == 'B4' and h['transaction_id'] in late for h in self.result['hits']))

    def test_graph_ablation_removes_network_only_signals(self):
        direct = score_rules(self.tables, features=self.features, config={'enable_graph': False})
        self.assertFalse(any(h['rule_id'] == 'A3' for h in direct['hits']))
        self.assertFalse(any(h['graph_path'] for h in direct['hits']))
        graph_only = [h for h in self.result['hits'] if h['rule_id'] == 'B2' and not h['evidence']['direct_matches']]
        self.assertTrue(graph_only)

    def test_evidence_graph_never_uses_future_links(self):
        for hit in self.result['hits']:
            self.assertTrue(all(e['observed_at'] <= hit['detected_at'] for e in hit['graph_path']))

    def test_actual_duplicate_and_missing_writeoff_have_evidence(self):
        for kind, rule in [('duplicate_payment', 'P1'), ('long_outstanding_advance', 'T2')]:
            hits = [h for h in self.result['hits'] if h['rule_id'] == rule
                    and self.truth[h['transaction_id']]['fraud_type'] == kind]
            self.assertTrue(hits)
            self.assertTrue(all(h['evidence'] and h['hard_trigger'] for h in hits))

    def test_normalisation_preserves_ids_and_does_not_match_blanks(self):
        self.assertEqual(normalize('+84 912 345 678', 'phone'), '0912345678')
        self.assertEqual(normalize('0912.345.678', 'phone'), '0912345678')
        self.assertEqual(normalize('0012345', 'bank_account'), '0012345')
        self.assertEqual(normalize(''), '')

    def test_benford_inapplicable_population_is_explicit_not_zero(self):
        self.assertEqual(digits_test([10_000_000] * 1000, 'first')['status'], 'not_evaluable')
        self.assertEqual(digits_test(list(range(100, 110)), 'second')['status'], 'not_evaluable')
        self.assertEqual(bh_adjust([.01, .04, .03]), [.03, .04, .04])

    def test_missing_operational_sources_are_reported(self):
        coverage = {r['rule_id']: r for r in self.result['coverage']}
        self.assertEqual(len([c for c in coverage if c[0] in 'ABCDEF']), 31)
        self.assertTrue(all(coverage[c]['status'] == 'not_evaluable' for c in ['C4', 'E2', 'F2', 'F3', 'F4']))


if __name__ == '__main__':
    unittest.main()
