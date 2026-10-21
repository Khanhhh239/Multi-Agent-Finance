"""Research audits preserve missing endpoints, currencies and raw provenance."""

import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.data_audit.research_t0_fixture_sources import (
    SOURCES, audit_allocations, audit_payout_bank, inspect, snapshot)


class FixtureResearchTests(unittest.TestCase):
    def test_partial_allocation_not_mistaken_for_full_settlement(self):
        invoices = [{"invoice_id": "i", "currency": "USD", "vendor_id": "v", "invoice_total": "200"}]
        payments = [{"payment_id": p, "payment_currency": "USD", "vendor_id": "v", "payment_amount": a}
                    for p, a in [("p1", "55"), ("p2", "35")]]
        allocations = [{"invoice_id": "i", "payment_id": p, "allocated_amount": a}
                       for p, a in [("p1", "55"), ("p2", "35")]]
        result = audit_allocations(invoices, payments, allocations)
        self.assertEqual(result["invoices_partly_allocated"], 1)
        self.assertEqual(result["invoices_with_multiple_payments"], 1)
        self.assertEqual(result["invoices_overallocated"], 0)
        broken = allocations + [{"invoice_id": "missing", "payment_id": "p1", "allocated_amount": "1"}]
        self.assertEqual(audit_allocations(invoices, payments, broken)["orphan_allocation_rows"], 1)

    def test_cross_currency_amounts_not_compared_as_same_currency(self):
        result = audit_allocations(
            [{"invoice_id": "i", "currency": "USD", "vendor_id": "v", "invoice_total": "10"}],
            [{"payment_id": "p", "payment_currency": "VND", "vendor_id": "v", "payment_amount": "250000"}],
            [{"invoice_id": "i", "payment_id": "p", "allocated_amount": "250000"}])
        self.assertEqual(result["cross_currency_edges"], 1)
        self.assertEqual(result.get("invoices_overallocated", 0), 0)

    def test_missing_observed_payout_is_retained_and_not_counted_as_zero(self):
        payouts = [{"payout_id": "p", "settle_currency": "USD", "amount_minor": "100", "expected_arrival_date": "2026-01-01"}]
        bank = [{"stmt_line_id": "b", "currency": "USD", "amount_minor": "150", "value_date": "2026-01-01"}]
        truth = [{"payout_id": p, "stmt_line_id": "b"} for p in ("p", "missing")]
        result = audit_payout_bank(payouts, bank, truth)
        self.assertEqual(result["truth_rows_with_payout_absent_from_observed_table"], 1)
        self.assertEqual(result["bank_ids_with_multiple_truth_payouts"], 1)
        self.assertEqual(result["groups_skipped_incomplete_observed_endpoints"], 1)
        self.assertEqual(result.get("complete_same_currency_groups", 0), 0)

    def test_upstream_python_is_parsed_without_execution_and_raw_tamper_fails(self):
        code = b'raise RuntimeError("must never execute")\ndef test_example(): pass\n'
        response = io.BytesIO(code)
        response.status = 200
        spec = {"revision": "fixed", "requests": {"test_fixture.py": "https://example.test/fixed/test_fixture.py"}}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(SOURCES, {"fixture_test": spec}):
            with patch("urllib.request.urlopen", return_value=response):
                folder, _ = snapshot(Path(tmp), "fixture_test")
            result = inspect("fixture_test", folder)
            self.assertEqual(result["file_profiles"]["test_fixture.py"]["test_functions"], ["test_example"])
            with patch("urllib.request.urlopen") as network:
                snapshot(Path(tmp), "fixture_test", offline=True)
                network.assert_not_called()
            (folder / "test_fixture.py").write_bytes(code + b"# changed")
            with self.assertRaisesRegex(ValueError, "bytes or provenance"):
                snapshot(Path(tmp), "fixture_test", offline=True)


if __name__ == "__main__":
    unittest.main()
