"""Guard meaningful ranking/error metrics, especially zero scores and ties."""
import unittest

from experiments.he_inference.comparison_metrics import compare_rows,timing_summary,recovery_summary


def rows(scores):
    return [dict(record_id='T'+str(i),revision=1,score=s,available=True) for i,s in enumerate(scores)]


class ComparisonMetricsTests(unittest.TestCase):
    def test_joins_by_identity_not_response_order(self):
        a=rows([3.,2.,1.]);b=list(reversed(rows([3.+1e-8,2.,1.])))
        m=compare_rows(a,b)
        self.assertTrue(m['all_scores_within_tolerance']);self.assertTrue(m['exact_order_equal'])
        self.assertAlmostEqual(m['spearman'],1.);self.assertEqual(m['material_pair_inversions'],0)
        self.assertTrue(m['top_k_covers_entire_dataset'])

    def test_material_inversion_is_not_hidden_by_top_k_covering_every_row(self):
        m=compare_rows(rows([3.,2.,1.]),rows([1.,2.,3.]))
        self.assertEqual(m['top_k_overlap_fraction'],1.)
        self.assertFalse(m['exact_order_equal']);self.assertEqual(m['material_pair_inversions'],3)
        self.assertAlmostEqual(m['spearman'],-1.)

    def test_near_tie_may_change_exact_order_within_tolerance(self):
        m=compare_rows(rows([1.,1.+1e-6]),rows([1.+1e-6,1.]))
        self.assertTrue(m['all_scores_within_tolerance']);self.assertFalse(m['exact_order_equal'])
        self.assertEqual(m['material_pair_inversions'],0);self.assertEqual(m['comparable_pairs'],0)

    def test_zero_reference_does_not_invent_relative_accuracy(self):
        m=compare_rows(rows([0.,0.]),rows([1e-7,1e-7]))
        self.assertIsNone(m['maximum_relative_error']);self.assertEqual(m['relative_error_undefined_rows'],2)
        self.assertIsNone(m['spearman']);self.assertTrue(m['all_scores_within_tolerance'])

    def test_missing_unavailable_nonfinite_duplicate_and_empty_rejected(self):
        for a,b in [(rows([1]),[]),([],[]),(rows([1]),rows([float('nan')])),
                    (rows([1]),rows([1])+rows([1])),(rows([1]),[dict(rows([1])[0],available=False)])]:
            with self.subTest(a=a,b=b),self.assertRaises(ValueError):compare_rows(a,b)

    def test_combined_tolerance_and_review_budget(self):
        m=compare_rows(rows([1000.,2.,1.]),rows([1000.005,2.,1.]),2)
        self.assertTrue(m['all_scores_within_tolerance']);self.assertFalse(m['top_k_covers_entire_dataset'])
        self.assertEqual(m['top_k_overlap'],2)
        with self.assertRaises(ValueError):compare_rows(rows([1]),rows([1]),0)

    def test_timing_preserves_samples_and_rejects_invalid(self):
        m=timing_summary([1.,2.,3.]);self.assertEqual(m['median_ms'],2.);self.assertEqual(m['count'],3)
        for samples in ([],[-1.],[float('inf')]):
            with self.assertRaises(ValueError):timing_summary(samples)

    def test_inconclusive_fault_not_counted_as_success_or_in_denominator(self):
        m=recovery_summary([dict(mode='crash',injection_confirmed=True,recovered=False,recovery_ms=None),
            dict(mode='crash',injection_confirmed=False,recovered=True,recovery_ms=1.),
            dict(mode='network',injection_confirmed=True,recovered=True,recovery_ms=3.)])
        self.assertEqual(m[0]['confirmed'],1);self.assertEqual(m[0]['inconclusive'],1)
        self.assertEqual(m[0]['success_fraction'],0.);self.assertEqual(m[1]['success_fraction'],1.)

    def test_all_inconclusive_faults_produce_no_success_percentage(self):
        group=recovery_summary([dict(mode='crash',injection_confirmed=False,recovered=True,recovery_ms=2.)])[0]
        self.assertEqual(group['confirmed'],0);self.assertIsNone(group['success_fraction'])
        self.assertIsNone(group['successful_recovery_time'])


if __name__=='__main__':unittest.main()
