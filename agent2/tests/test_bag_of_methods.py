"""Bag of methods chosen by injection (synthetic test doubles only)."""
import io
import unittest

import joblib
import numpy as np

from sme_fraud import bag_of_methods as B
from sme_fraud.ml_estimators import CompanyEstimator, catalog

NAMES = (['log_amount', 'amount_limit_ratio', 'near_limit', 'hour_sin', 'hour_cos', 'weekday_sin', 'weekday_cos', 'created_weekend',
          'created_off_hours', 'approval_log_hours', 'self_approved', 'self_approval_permitted', 'support_doc_count',
          'goods_receipt_verified', 'support_docs_known', 'has_vendor', 'invoice_known', 'vendor_age_log_days',
          'vendor_tenure_log_days', 'employee_bank_overlap', 'employee_phone_overlap_current',
          'employee_address_overlap_current', 'related_party_disclosed', 'graph_employee_count_current',
          'linked_vendor_count_current', 'prior_same_amount_30d', 'prior_invoice_payment_count',
          'cumulative_invoice_payment_ratio', 'recipient_count_3d', 'recipient_sum_limit_3d', 'creator_count_7d',
          'creator_near_limit_30d', 'prior_type_history_log_count', 'log_amount_vs_history', 'amount_history_z',
          'advance_overdue_days', 'advance_open_fraction', 'advance_writeoff_evidence_missing', 'attendance_known',
          'attendance_days', 'alternative_work_evidence', 'employee_contract_on_file', 'type_payroll',
          'type_advance_issue'] + [f'noise_{i}' for i in range(8)])


def ledger(n=400, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, len(NAMES)))
    for name in NAMES:
        j = NAMES.index(name)
        if name.startswith(('near_', 'created_', 'self_', 'goods_', 'support_docs', 'has_', 'invoice_known', 'related_', 'employee_',
                            'alternative', 'attendance_known', 'advance_open', 'advance_writeoff', 'type_')):
            x[:, j] = (rng.random(n) < .25).astype(float)
    x[:, NAMES.index('amount_limit_ratio')] = rng.uniform(0, .6, n)
    x[:, NAMES.index('has_vendor')] = (rng.random(n) < .5).astype(float)
    x[:, NAMES.index('type_payroll')] = (rng.random(n) < .2).astype(float)
    for name in ('advance_overdue_days', 'prior_same_amount_30d', 'recipient_count_3d', 'creator_count_7d', 'creator_near_limit_30d'):
        x[:, NAMES.index(name)] = np.abs(rng.normal(0, 1, n)).round()
    return x


class BagTest(unittest.TestCase):
    def test_fit_selects_reports_and_scores_deterministically(self):
        x = ledger()
        first = B.BagOfMethods().fit(x, NAMES)
        second = B.BagOfMethods().fit(x, NAMES)
        dg = first.diagnostics_
        self.assertEqual(dg['chosen'], second.diagnostics_['chosen'])
        self.assertIn(dg['chosen'], dg['candidate_objectives'])
        self.assertGreaterEqual(dg['chosen_objective'] + 1e-12, dg['baseline_objective'] - B.MARGIN)
        self.assertEqual(len(dg['families_used']), 10)
        self.assertEqual(set(dg['recall_by_level']), {0, 1, 2})
        self.assertTrue(0 <= dg['held_out_family_recall_estimate'] <= 1)
        self.assertEqual(dg['reliability'], 'trung bình')
        self.assertEqual(B.BagOfMethods().fit(ledger(250), NAMES).diagnostics_['reliability'], 'thấp')
        scores = first.score(x[:50])
        np.testing.assert_allclose(scores, second.score(x[:50]), rtol=1e-10)
        self.assertEqual(scores.shape, (50,)); self.assertTrue(np.isfinite(scores).all())

    def test_through_company_estimator_and_joblib(self):
        x = ledger(seed=1)
        model = CompanyEstimator('bag_injection').fit(x, columns=NAMES)
        before = model.score(x[:30])
        restored = joblib.load(io.BytesIO(self._dump(model)))
        np.testing.assert_allclose(before, restored.score(x[:30]), rtol=1e-10)
        self.assertEqual(model.diagnostics_['kind'], 'bag_of_methods_injection')
        info = next(a for a in catalog() if a['id'] == 'bag_injection')
        self.assertFalse(info['requires_labels']); self.assertTrue(info['installed'])

    @staticmethod
    def _dump(model):
        buffer = io.BytesIO(); joblib.dump(model, buffer); return buffer.getvalue()

    def test_refuses_too_few_rows_and_mismatched_columns(self):
        with self.assertRaisesRegex(ValueError, 'ít nhất'):
            B.BagOfMethods().fit(ledger(40), NAMES)
        with self.assertRaisesRegex(ValueError, 'tên cột'):
            B.BagOfMethods().fit(ledger(), NAMES[:-1])
        with self.assertRaisesRegex(ValueError, 'tên cột'):
            CompanyEstimator('bag_injection').fit(ledger())

    def test_families_missing_their_columns_are_skipped_not_fatal(self):
        keep = [i for i, n in enumerate(NAMES) if n not in ('attendance_days', 'type_payroll')]
        names = [NAMES[i] for i in keep]
        dg = B.BagOfMethods().fit(ledger()[:, keep], names).diagnostics_
        skipped = dict(dg['families_skipped'])
        self.assertIn('payroll_without_attendance', skipped)
        self.assertEqual(len(dg['families_used']), 9)

    def test_injected_clones_are_more_unusual_than_real_rows(self):
        x = ledger(seed=2)
        rng = np.random.default_rng(0)
        clones, fam, lev, _, used = B.make_injections(x[280:], x[:280], NAMES, rng)
        model = B.ShrunkMahalanobis().fit(x[:280])
        real, inj = model.score(x[280:]), model.score(clones)
        for level in (0, 1):                   # obvious and moderate concealment shift the joint distribution
            self.assertGreater(np.median(inj[lev == level]), np.median(real))
        self.assertTrue(np.array_equal(np.unique(fam), np.asarray(used)))

    def test_surprise_scale_is_monotone_and_extends_beyond_the_reference_maximum(self):
        ref = B.Reference(np.arange(1, 101, dtype=float))
        s = ref.surprise(np.array([1., 50., 100., 150., 300.]))
        self.assertTrue((np.diff(s) > 0).all())

    def test_default_comparison_list_excludes_the_slow_bag(self):
        import inspect
        from sme_fraud import company_ml_comparison as comparison
        self.assertIn("a!='bag_injection'", inspect.getsource(comparison.compare).replace(' ', ''))


if __name__ == '__main__':
    unittest.main()
