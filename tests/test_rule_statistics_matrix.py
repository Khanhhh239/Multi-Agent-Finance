"""Six aggregate rules have source/window controls, never transaction routing."""
import copy
import unittest
from datetime import timedelta

from sme_fraud.aggregate_challenge import window_case
from sme_fraud.benford import digits_test, monthly_diagnostics
from sme_fraud.generate import parse, stamp


PATTERNS = dict(D1='first_digit_shift', D2='second_digit_shift', D3='near_limit_shift',
                D4='suffix_shift', D5='first_digit_shift', D6='first_digit_shift')


class RuleStatisticsMatrixTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables, cls.results = {}, {}
        for pattern in set(PATTERNS.values()) | {'natural', 'small_sample', 'fixed_legitimate'}:
            tables, _ = window_case(20261027, pattern)
            cls.tables[pattern] = tables
            cls.results[pattern] = monthly_diagnostics(tables, 'phase4')

    def selected(self, pattern, code):
        scope = 'creator:E_CONTROL' if code in {'D3', 'D6'} else 'company'
        return next(r for r in self.results[pattern] if r['rule_id'] == code and r['scope'] == scope
                    and r['cutoff_at'] == '2025-10-01T00:00:00+07:00')

    def test_all_six_positive_signals_keep_aggregate_scope(self):
        for code, pattern in PATTERNS.items():
            with self.subTest(rule=code):
                row = self.selected(pattern, code)
                self.assertEqual(row['status'], 'evaluated')
                self.assertIs(row['signal'], True)
                self.assertFalse(row['adds_transaction_score'])
                self.assertEqual(row['action'], 'aggregate_review_only')

    def test_all_six_natural_counterparts_are_evaluated_negatives(self):
        for code in PATTERNS:
            with self.subTest(rule=code):
                row = self.selected('natural', code)
                self.assertEqual(row['status'], 'evaluated')
                self.assertIs(row['signal'], False)

    def test_missing_sample_is_unknown_instead_of_a_negative(self):
        for code in PATTERNS:
            row = self.selected('small_sample', code)
            self.assertEqual(row['status'], 'not_evaluable', code)
            self.assertNotEqual(row.get('signal'), True)
            self.assertTrue(row['skip_reasons'])

    def test_fixed_legitimate_population_is_not_forced_into_benford(self):
        for code in ('D1', 'D2', 'D3', 'D5', 'D6'):
            self.assertEqual(self.selected('fixed_legitimate', code)['status'], 'not_evaluable', code)

    def test_minimum_population_and_expected_cell_count_boundaries(self):
        for kind, minimum, sizes in (('first', 300, ((299, False), (300, True))),
                                    ('second', 1000, ((999, False), (1000, True))),
                                    ('first_two', 1000, ((1145, False), (1146, True)))):
            for count, evaluable in sizes:
                amounts = [int(10 ** (3 + 4 * i / count)) for i in range(count)]
                self.assertEqual(digits_test(amounts, kind, minimum)['status'] == 'evaluated', evaluable,
                                 (kind, count))

    def test_d4_needs_three_hundred_rows_in_both_time_windows(self):
        for count, expected in ((299, 'not_evaluable'), (300, 'evaluated')):
            tables, _ = window_case(20261027, 'suffix_shift', size=count)
            row = next(r for r in monthly_diagnostics(tables, 'phase4') if r['rule_id'] == 'D4'
                       and r['scope'] == 'company' and r['cutoff_at'] == '2025-10-01T00:00:00+07:00')
            self.assertEqual(row['status'], expected)

    def test_later_records_do_not_rewrite_any_closed_diagnostic_window(self):
        tables = copy.deepcopy(self.tables['natural'])
        old = self.results['natural']
        future = [{**r, 'transaction_id': 'FUTURE_' + r['transaction_id'],
                   'posted_at': stamp(parse(r['posted_at']) + timedelta(days=400))} for r in tables['transactions']]
        tables['transactions'].extend(future)
        after = monthly_diagnostics(tables, 'phase4')
        cutoffs = {r['cutoff_at'] for r in old}
        self.assertEqual(old, [r for r in after if r['cutoff_at'] in cutoffs])


if __name__ == '__main__':
    unittest.main()
