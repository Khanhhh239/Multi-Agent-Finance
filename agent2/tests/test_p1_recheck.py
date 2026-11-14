"""P1 acceptance assertions retain legacy limits and verify the temporal fix."""
import unittest
from p1_recheck_support import run_case


class P1EngineRecheckTests(unittest.TestCase):
    def test_below_cap_matches_native(self):run_case('below')
    def test_exceeded_matches_points_evidence_and_prior_native(self):run_case('exceeded')
    def test_missing_history_is_null_and_native_cannot_express_readiness(self):run_case('missing_history')
    def test_late_invoice_native_is_information_gap_and_canonical_is_null(self):
        summary,_=run_case('late_invoice')
        self.assertFalse(summary['findings'])
        self.assertEqual(summary['resolved_findings'][0]['status'],'FIXED_IN_TESTED_SCOPE')
        self.assertEqual(summary['classification'],'native_temporal_fix_verified')
    def test_late_allocation_is_not_retroactively_used(self):run_case('late_allocation')
    def test_late_unrequired_attachment_does_not_change_P1(self):run_case('late_attachment')
    def test_simultaneous_members_totals_and_unique_group_match(self):run_case('simultaneous')


if __name__=='__main__':unittest.main()
