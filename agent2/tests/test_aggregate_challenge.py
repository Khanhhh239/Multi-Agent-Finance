import sys
import unittest
from pathlib import Path

packages = Path(__file__).resolve().parents[1]/'.runtime/site-packages'
if packages.exists():
    sys.path.insert(0, str(packages))
from sme_fraud.aggregate_challenge import window_case
from sme_fraud.benford import monthly_diagnostics


class AggregateChallengeTest(unittest.TestCase):
    def target(self, results, code):
        scope = 'creator:E_CONTROL' if code in {'D3','D6'} else 'company'
        return next(r for r in results if r['rule_id']==code and r['scope']==scope and r['cutoff_at']=='2025-10-01T00:00:00+07:00')

    def test_dense_windows_enable_all_six_rules_and_departments_projects(self):
        tables, _ = window_case(801, 'natural')
        result = monthly_diagnostics(tables, 'phase4')
        for code in ('D1','D2','D3','D4','D5','D6'):
            self.assertEqual(self.target(result, code)['status'], 'evaluated', code)
        self.assertTrue(any(r['rule_id']=='D6' and r['scope'].startswith('department:') and r['status']=='evaluated' for r in result))
        self.assertTrue(any(r['rule_id']=='D6' and r['scope'].startswith('project_id:') and r['status']=='evaluated' for r in result))
        self.assertTrue(all(not r['adds_transaction_score'] for r in result))

    def test_d3_far_below_threshold_is_counterpart_for_actual_near_amounts(self):
        tables, _ = window_case(802, 'far_below_limit_pairs')
        self.assertFalse(self.target(monthly_diagnostics(tables, 'phase4'), 'D3')['signal'])
        near, _ = window_case(802, 'near_limit_shift')
        self.assertTrue(self.target(monthly_diagnostics(near, 'phase4'), 'D3')['signal'])

    def test_suffix_intervention_has_prior_baseline(self):
        tables, _ = window_case(803, 'suffix_shift')
        target = self.target(monthly_diagnostics(tables, 'phase4'), 'D4')
        self.assertTrue(target['signal'])
        self.assertGreater(target['baseline_rows'], 300)

    def test_small_or_fixed_population_is_unknown_not_a_negative(self):
        for pattern in ('small_sample','fixed_legitimate'):
            tables, truth = window_case(804, pattern)
            results = monthly_diagnostics(tables, 'phase4')
            self.assertTrue(all(r['expected_signal'] is None for r in truth))
            self.assertEqual(self.target(results, 'D3')['status'], 'not_evaluable')


if __name__ == '__main__':
    unittest.main()
