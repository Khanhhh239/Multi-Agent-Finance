"""Audit arithmetic and counterfactual alert accounting at low prevalence."""
import unittest

from sme_fraud.rule_audit import MAIN_RULES, EXTRA_RULES, confusion, period_for_window, replay_scores, scenario_coverage, eligible


class RuleAuditTest(unittest.TestCase):
    def test_f1_eligibility_respects_saved_snapshot_policy(self):
        row = dict(txn_type='stock_purchase', is_financial_entry=1)
        self.assertFalse(eligible('F1', row))
        self.assertFalse(eligible('F1', row, {'spec_policy': 'legacy'}))
        self.assertTrue(eligible('F1', row, {'spec_policy': 'phase3'}))
        self.assertTrue(eligible('F1', {**row, 'txn_type': 'adjustment'}))

    def test_b1_master_and_outflow_audit_populations_are_distinct(self):
        row = dict(vendor_id='V', txn_type='stock_purchase', is_financial_entry=1, payment_channel='journal', credit_account='331')
        self.assertTrue(eligible('B1', row))
        self.assertFalse(eligible('B1', row, {'spec_policy': 'phase3'}))
        self.assertTrue(eligible('B1', {**row, 'txn_type': 'rent', 'payment_channel': 'bank', 'credit_account': '1121'}, {'spec_policy': 'phase3'}))

    def test_undefined_precision_is_not_zero_or_perfect(self):
        labels = {'fraud': {'is_fraud': 1}, 'normal': {'is_fraud': 0}}
        result = confusion(labels, set(), labels)
        self.assertIsNone(result['fraud_precision'])
        self.assertEqual(result['fraud_recall_all'], 0)
        self.assertEqual(result['fpr'], 0)
        self.assertIsNone(result['fraud_precision_wilson_row95'])
        self.assertIsNone(confusion([], set(), labels)['accuracy'])

    def test_fpr_uses_normal_rows_and_precision_uses_selected_rows(self):
        labels = {str(i): {'is_fraud': int(i == 0)} for i in range(1001)}
        result = confusion(labels, {'0', '1'}, labels)
        self.assertEqual((result['tp'], result['fp'], result['fn'], result['tn']), (1, 1, 0, 999))
        self.assertEqual(result['fraud_precision'], .5)
        self.assertEqual(result['fpr'], .001)
        self.assertEqual(result['false_alerts_per_1000_normal'], 1)
        # A rule that alerts nobody still has deceptively high raw accuracy.
        self.assertGreater(confusion(labels, set(), labels)['accuracy'], .999)

    def test_unrelated_fraud_is_not_target_scenario_denominator(self):
        labels = {
            'a': dict(is_fraud=1, fraud_type='split_payments', variant='x', case_id='case', observability='available'),
            'b': dict(is_fraud=1, fraud_type='duplicate_payment', variant='x', case_id='other', observability='available'),
            'c': dict(is_fraud=0, fraud_type='', variant='', case_id='case', observability=''),
        }
        result = scenario_coverage('A1', labels, {'a', 'c'}, labels)
        self.assertEqual((result['rows'], result['hits'], result['coverage']), (1, 1, 1))
        self.assertEqual((result['cases'], result['detected_cases']), (1, 1))
        self.assertIsNone(scenario_coverage('B7', labels, {'a'}, labels)['coverage'])

    def test_closed_window_belongs_to_period_ending_before_cutoff(self):
        self.assertEqual(period_for_window('2025-01-01T00:00:00+07:00'), 'train')
        self.assertEqual(period_for_window('2025-07-01T00:00:00+07:00'), 'validation')
        self.assertEqual(period_for_window('2026-01-01T00:00:00+07:00'), 'test')
        self.assertIsNone(period_for_window('2026-02-01T00:00:00+07:00'))

    def test_removing_rule_recomputes_later_recurrence_without_simultaneous_peeking(self):
        rows = [dict(transaction_id=str(i), company_id='C', vendor_id='V', employee_id='', creator_id='E', posted_at=t)
                for i, t in enumerate(['2025-08-01T10:00:00+07:00']*2 +
                                      ['2025-08-02T10:00:00+07:00', '2025-09-10T10:00:00+07:00'])]
        points = {'0': {'A1': 8}, '1': {'A1': 8}, '2': {'B4': 10}, '3': {'B4': 10}}
        config = {'recurrence_cap': 3, 'operational_score': 7}
        base = replay_scores(rows, points, config)
        removed = replay_scores(rows, points, config, {'A1'})
        self.assertEqual([base[str(i)]['recurrence_points'] for i in range(4)], [0, 0, 2, 0])
        self.assertEqual(removed['2']['rule_score'], 10)
        self.assertEqual(base['2']['rule_score'], 12)
        self.assertFalse(removed['0']['alert'])

    def test_overlapping_rules_do_not_have_additive_alert_effects(self):
        rows = [dict(transaction_id='T', company_id='C', vendor_id='V', employee_id='', creator_id='E',
                     posted_at='2025-08-01T10:00:00+07:00')]
        points = {'T': {'A1': 8, 'A2': 4, 'B5': 3, 'E4': 3, 'E3': 3}}
        config = {'recurrence_cap': 3, 'operational_score': 7}
        base = replay_scores(rows, points, config)
        self.assertEqual(base['T']['base_score'], 11)
        self.assertEqual(replay_scores(rows, points, config, {'B5'})['T'], base['T'])
        self.assertTrue(replay_scores(rows, points, config, {'A1'})['T']['alert'])
        self.assertFalse(replay_scores(rows, points, config, {'A1', 'A2'})['T']['alert'])

    def test_appendix_rules_are_not_counted_in_main_31(self):
        self.assertEqual(len(MAIN_RULES), 31)
        self.assertEqual(len(set(MAIN_RULES)), 31)
        self.assertFalse(set(MAIN_RULES) & set(EXTRA_RULES))


if __name__ == '__main__':
    unittest.main()
