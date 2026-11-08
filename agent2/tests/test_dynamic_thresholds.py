"""Rolling-window arithmetic, seasonal context, isolation and causal replay."""
from datetime import datetime, timedelta
import calendar
import math
import unittest

from sme_fraud.dynamic_thresholds import DynamicThresholds, ThresholdPolicy, key_of, observation
from sme_fraud.generate import TZ


NOW = datetime(2025, 7, 25, 12, tzinfo=TZ)


def sample(identity, at, amount, **values):
    result = dict(observation_id=identity, company_id='C001', account_code='6421', measurement='expense_debit',
                  family='general_expense', event_at=at.isoformat(), amount_vnd=amount, source_transaction_id=identity,
                  source_ref='fixture:'+identity, currency='VND')
    result.update(values)
    return result


def policy(**values):
    return ThresholdPolicy(**{'minimum_samples': 2, 'cycle_enabled': False, **values})


class DynamicThresholdsTest(unittest.TestCase):
    def test_linear_p95_p99_and_strict_upper_tail(self):
        rows = [sample(str(i), NOW-timedelta(days=4-i), amount*1_000_000) for i, amount in enumerate((1, 2, 3, 4))]
        for method, threshold in (('p95', 3_850_000), ('p99', 3_970_000)):
            engine = DynamicThresholds(rows, policy(method=method))
            hit, evidence = engine.evaluate(sample('CURRENT', NOW, 3_900_000))
            self.assertAlmostEqual(evidence['threshold_vnd'], threshold)
            self.assertEqual(hit, method == 'p95')
            self.assertEqual(evidence['selected_parameter']['sample_count'], 4)
        equal = DynamicThresholds(rows, policy()).evaluate(sample('CURRENT', NOW, 3_970_000))
        self.assertFalse(equal[0])

    def test_mean_plus_k_sample_standard_deviation(self):
        rows = [sample('A', NOW-timedelta(days=2), 1_000_000), sample('B', NOW-timedelta(days=1), 3_000_000)]
        hit, evidence = DynamicThresholds(rows, policy(method='mean_std', sigma_k=2)).evaluate(sample('C', NOW, 5_000_000))
        self.assertAlmostEqual(evidence['threshold_vnd'], 2_000_000+2*math.sqrt(2)*1_000_000)
        self.assertTrue(hit)

    def test_zero_variance_and_lower_tail_are_not_undefined_or_two_sided(self):
        rows = [sample(str(i), NOW-timedelta(days=i+1), 1_000_000) for i in range(4)]
        for amount, expected in ((100_000, False), (1_000_000, False), (1_000_001, True)):
            result = DynamicThresholds(rows, policy(method='mean_std')).evaluate(sample('NEW', NOW, amount))
            self.assertEqual(result[0], expected)
            self.assertEqual(result[1]['threshold_vnd'], 1_000_000)

    def test_30_60_90_day_boundaries_and_expiry_are_exact(self):
        rows = [sample(str(days), NOW-timedelta(days=days), days*1000) for days in (1, 30, 31, 60, 61, 90, 91)]
        engine = DynamicThresholds(rows, policy())
        engine.advance(NOW.isoformat())
        key = key_of(observation(rows[0]))
        for days, expected in ((30, 2), (60, 4), (90, 6)):
            self.assertEqual(engine.parameters_for(key, NOW.isoformat(), days)[0]['sample_count'], expected)
        later = NOW+timedelta(days=91)
        engine.advance(later.isoformat())
        self.assertEqual(engine.parameters_for(key, later.isoformat(), 90)[0]['sample_count'], 0)

    def test_company_exact_subaccount_measurement_and_family_never_pool(self):
        ordinary = [sample(str(i), NOW-timedelta(days=i+1), 1_000_000) for i in range(3)]
        alternatives = [dict(company_id='C002'), dict(account_code='6422'), dict(account_code='641'),
                        dict(measurement='cash_outflow'), dict(family='payroll')]
        rows = ordinary+[sample('OTHER'+str(i), NOW-timedelta(days=1), 100_000_000, **change)
                         for i, change in enumerate(alternatives)]
        hit, evidence = DynamicThresholds(rows, policy()).evaluate(sample('NEW', NOW, 2_000_000))
        self.assertTrue(hit)
        self.assertEqual(evidence['selected_parameter']['sample_count'], 3)
        self.assertEqual(evidence['threshold_vnd'], 1_000_000)

    def test_current_and_simultaneous_transactions_never_enter_their_own_baseline(self):
        earlier = [sample(str(i), NOW-timedelta(days=i+1), 1_000_000) for i in range(3)]
        batch = [sample('BATCH1', NOW, 100_000_000), sample('BATCH2', NOW, 200_000_000)]
        engine = DynamicThresholds(earlier+batch, policy())
        for row in batch:
            hit, evidence = engine.evaluate(row)
            self.assertTrue(hit)
            self.assertEqual(evidence['selected_parameter']['sample_count'], 3)
        table = engine.parameter_table(NOW.isoformat())
        self.assertEqual(next(r for r in table if r['window_days'] == 90)['sample_count'], 5)

    def test_future_values_and_late_observations_cannot_change_past_evidence(self):
        earlier = [sample(str(i), NOW-timedelta(days=i+1), 1_000_000) for i in range(3)]
        current = sample('NEW', NOW, 2_000_000)
        expected = DynamicThresholds(earlier, policy()).evaluate(current)
        future = sample('FUTURE', NOW+timedelta(days=1), 999_000_000)
        late = sample('LATE', NOW-timedelta(days=1), 999_000_000, observed_at=(NOW+timedelta(days=1)).isoformat())
        self.assertEqual(DynamicThresholds(earlier+[future, late], policy()).evaluate(current), expected)

    def test_parameter_selection_never_uses_current_amount_or_truth(self):
        earlier = [sample(str(i), NOW-timedelta(days=i+1), 1_000_000, is_fraud=i % 2) for i in range(3)]
        first = DynamicThresholds(earlier, policy()).evaluate(sample('NEW', NOW, 2_000_000))
        second = DynamicThresholds(list(reversed(earlier)), policy()).evaluate(sample('NEW', NOW, 20_000_000, is_fraud=1))
        self.assertEqual(first[1]['selected_parameter'], second[1]['selected_parameter'])

    def monthly_rows(self, end=False):
        rows = []
        for month in range(1, 7):
            for day in range(1, 21):
                at = datetime(2025, month, day, 9, tzinfo=TZ)
                rows.append(sample(f'DAILY_{month}_{day}', at, 1_000_000, family='payroll',
                                   measurement='cash_outflow', account_code='334'))
            day = calendar.monthrange(2025, month)[1] if end else 25
            for index in range(5):
                at = datetime(2025, month, day, 10, index, tzinfo=TZ)
                rows.append(sample(f'PAY_{month}_{index}', at, 20_000_000, family='payroll',
                                   measurement='cash_outflow', account_code='334'))
        return rows

    def test_monthly_payday_lifts_threshold_and_off_cycle_keeps_a_lower_threshold(self):
        rows = self.monthly_rows()
        settings = policy(cycle_enabled=True, minimum_samples=5)
        for at, expected in ((datetime(2025, 7, 25, 12, tzinfo=TZ), False),
                             (datetime(2025, 7, 10, 12, tzinfo=TZ), True)):
            current = sample('CURRENT', at, 20_000_000, family='payroll', measurement='cash_outflow', account_code='334')
            hit, evidence = DynamicThresholds(rows, settings).evaluate(current)
            self.assertEqual(hit, expected)
            self.assertTrue(evidence['calendar_conditioned'])
            self.assertEqual(evidence['selected_parameter']['phase'], 'day_of_month')
            self.assertEqual(evidence['threshold_vnd'], 1_000_000 if expected else 20_000_000)

    def test_month_end_context_handles_short_months_and_leap_february(self):
        rows = self.monthly_rows(end=True)
        current = sample('CURRENT', datetime(2025, 7, 31, 12, tzinfo=TZ), 20_000_000,
                         family='payroll', measurement='cash_outflow', account_code='334')
        hit, evidence = DynamicThresholds(rows, policy(cycle_enabled=True, minimum_samples=5)).evaluate(current)
        self.assertFalse(hit)
        self.assertTrue(evidence['calendar_conditioned'])
        self.assertEqual(evidence['selected_parameter']['phase'], 'month_end_offset')
        # A leap-day is a genuine month-end sample, not a fabricated day 31.
        feb = observation(sample('LEAP', datetime(2024, 2, 29, 12, tzinfo=TZ), 1_000_000))
        self.assertEqual(feb['_end_offset'], 0)

    def test_insufficient_phase_history_falls_back_without_inventing_a_cycle(self):
        rows = [sample(str(i), NOW-timedelta(days=i+1), 1_000_000) for i in range(20)]
        hit, evidence = DynamicThresholds(rows, policy(cycle_enabled=True)).evaluate(sample('NEW', NOW, 2_000_000))
        self.assertTrue(hit)
        self.assertFalse(evidence['calendar_conditioned'])
        self.assertEqual(evidence['selected_parameter']['phase'], 'all_days')

    def test_cold_start_exports_null_effective_thresholds_not_global_defaults(self):
        row = sample('OLD', NOW-timedelta(days=1), 1_000_000)
        engine = DynamicThresholds([row], policy())
        hit, evidence = engine.evaluate(sample('NEW', NOW, 999_000_000))
        self.assertFalse(hit)
        self.assertEqual(evidence['status'], 'insufficient_history')
        self.assertIsNone(evidence['threshold_vnd'])
        self.assertTrue(all(r['effective_threshold_vnd'] is None for r in engine.parameter_table(NOW.isoformat())))

    def test_bad_configuration_and_conflicting_source_ids_are_rejected(self):
        for values in ({'window_days': 120}, {'minimum_samples': True}, {'sigma_k': float('nan')},
                       {'cycle_radius_days': -1}, {'method': 'choose_using_labels'}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                ThresholdPolicy(**values)
        row = sample('DUPLICATE', NOW, 1_000_000)
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            DynamicThresholds([row, dict(row, amount_vnd=2_000_000)])
