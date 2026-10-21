"""Regression fixtures for the archived multi-source audit and active source gate."""

import csv
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from t0.data import fingerprint, guard_matching_source, write_json
from scripts.archive.t0.audit_t0_moneyvis import sha256
from scripts.archive.t0.audit_t0_source_survey import (SOURCES, audit_cityvizor, audit_dc, audit_source,
                                             audit_tna, download_source, main as audit_main,
                                             uk_amount, verify_source)


def city_row(**overrides):
    return {"profileId": 3, "year": 2025, "date": "2025-01-02T00:00:00.000Z",
            "incomeAmount": 0, "expenditureAmount": 10, "counterpartyId": "SYNTH-C",
            "counterpartyName": "SYNTH-NAME", "description": "SYNTH-DESC",
            "paragraph": 1, "item": 2, "event": "", **overrides}


def dc_row(**overrides):
    return {"OBJECTID": 1, "AGENCYCODE": "SYNTH-A", "SUPPLIERNAME": "SYNTH-C",
            "INVOICENUMBER": "SYNTH-I", "PAYMENTNUMBER": "SYNTH-P", "FISCALYEAR": "2025",
            "INVOICEDATE": 1735689600000, "PAYMENTDATE": 1735862400000,
            "ESTPAYMENTDATE": 1735776000000, "PAYMENTAMOUNT": 10, "VOUCHERAMOUNT": 10, **overrides}


def raw_fixture(base, source_id, files=None, failed=False):
    folder = base / source_id
    folder.mkdir(parents=True)
    manifest = {"source_id": source_id, "spec_hash": fingerprint(SOURCES[source_id]),
                "use_policy": "inspection_only_excluded_from_matching", "files": [], "errors": [],
                "download_status": "failed" if failed else "downloaded", "fixture": "synthetic"}
    for filename in SOURCES[source_id]["files"] if not failed else []:
        payload = (files or {}).get(filename, b"[]")
        (folder / filename).write_bytes(payload)
        manifest["files"].append({"file": filename, "url": SOURCES[source_id]["files"][filename],
                                  "sha256": sha256(payload), "bytes": len(payload)})
    write_json(folder / "source_manifest.json", manifest)
    return folder


class SourceSurveyTests(unittest.TestCase):
    def test_archived_cli_handles_cached_failures_and_hashes_relocated_code_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for source_id in SOURCES:
                raw_fixture(base, source_id, failed=True)
            output = base / "audit.json"
            args = ["--input", str(base), "--output", str(output)]
            with patch("urllib.request.urlopen") as network, redirect_stdout(io.StringIO()):
                self.assertEqual(audit_main(args), 0)
                original = output.read_bytes()
                report = json.loads(original)
                self.assertTrue(all(r["status"] == "access_failed" for r in report["sources"]))
                self.assertEqual(report["summary"]["accepted_for_matching"], 0)
                root = Path(__file__).resolve().parents[1]
                for name, digest in report["code_hashes"].items():
                    self.assertEqual(sha256((root / name).read_bytes()), digest)
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as rejected:
                    audit_main([*args, "--download"])
                self.assertEqual(rejected.exception.code, 2)
                network.assert_not_called()
            self.assertEqual(output.read_bytes(), original)

    def test_city_budget_lines_duplicates_missing_party_and_negative_amount_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            rows = [city_row(), city_row(), city_row(expenditureAmount=-2, counterpartyId="", counterpartyName="")]
            write_json(folder / "payments.json", rows)
            write_json(folder / "years.json", [{"year": 2025, "validity": None}])
            p = audit_cityvizor(folder, 3)
            self.assertEqual(p["valid_rows"], 3)
            self.assertEqual(p["identical_row_occurrences_beyond_first"], 1)
            self.assertEqual(p["amount_signs"]["negative_rows"], 1)
            self.assertEqual(p["expenditure_total_source_decimal_units"], "18")
            self.assertEqual(p["missing_counterparty_id_rows"], 1)
            self.assertIsNone(p["currency"])
            self.assertNotIn("SYNTH-NAME", json.dumps(p))
            self.assertEqual(json.loads((folder / "payments.json").read_text()), rows)

    def test_city_schema_change_and_invalid_rows_are_not_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_json(folder / "payments.json", [{"new_schema": 1}])
            with self.assertRaises(ValueError):
                audit_cityvizor(folder, 3)
            write_json(folder / "payments.json", [city_row(date="bad"), city_row(profileId=4)])
            write_json(folder / "years.json", [])
            p = audit_cityvizor(folder, 3)
            self.assertEqual(len(p["errors"]), 1)
            self.assertEqual(p["wrong_profile_or_year_rows"], 1)
            self.assertFalse(p["year_metadata_present"])

    def test_tna_does_not_double_count_repeated_invoice_totals(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            buffer = io.StringIO(newline="")
            writer = csv.writer(buffer)
            writer.writerow(["Operational Transaction Number", "Last Invoice Payment Date", "Supplier",
                             "Supplier's Invoice Number", "Line Amount Spend", "Invoice Amount Spend"])
            for line in ("60.00", "40.00"):
                writer.writerow(["SYNTH-T", "02/01/2025", "SYNTH-C", "SYNTH-I", line, "100.00"])
            writer.writerow(["SYNTH-X", "02/01/2025", "SYNTH-C", "SYNTH-J", "2.00", "2.00"])
            writer.writerow(["SYNTH-X", "02/01/2025", "SYNTH-C", "SYNTH-J", "3.00", "3.00"])
            (folder / "payments.csv").write_text(buffer.getvalue(), encoding="utf-8")
            p = audit_tna(folder)
            self.assertEqual(p["line_total_source_decimal_units"], "105.00")
            self.assertEqual(p["max_lines_per_candidate_group"], 2)
            self.assertEqual(p["groups_with_conflicting_repeated_invoice_amounts"], 1)
            self.assertEqual(p["groups_where_sum_lines_equals_invoice_amount"], 1)

    def test_uk_money_is_exact_and_does_not_guess_decimal_comma(self):
        self.assertEqual(uk_amount("1,234.50"), Decimal("1234.50"))
        self.assertEqual(uk_amount("-0.01"), Decimal("-0.01"))
        for value in ("1,23", "NaN", "1.001", "(20.00)", "1,234,56"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                uk_amount(value)

    def test_dc_actual_date_is_separate_from_estimate_and_row_grain_not_assumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_json(folder / "payments.json", {"features": [{"attributes": row} for row in [dc_row(), dc_row(OBJECTID=2, PAYMENTAMOUNT=0)]], "exceededTransferLimit": True})
            write_json(folder / "count.json", {"count": 100})
            write_json(folder / "schema.json", {"fields": [{"name": "PAYMENTDATE"}, {"name": "ESTPAYMENTDATE"}]})
            p = audit_dc(folder)
            self.assertEqual(p["actual_differs_from_estimate_rows"], 2)
            self.assertEqual(p["zero_payment_rows"], 1)
            self.assertEqual(p["candidate_invoice_groups_with_multiple_rows"], 1)
            self.assertEqual(p["candidate_payment_groups_with_multiple_rows"], 1)
            self.assertTrue(p["schema_has_actual_and_estimated_payment_date"])
            self.assertFalse(p["sample_is_full_query"])
            self.assertIsNone(p["currency"])

    def test_download_snapshot_hash_idempotency_and_all_inspection_policies(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for source_id in SOURCES:
                folder = raw_fixture(base, source_id)
                with self.assertRaisesRegex(ValueError, "Source excluded"):
                    guard_matching_source(folder)
                with patch("urllib.request.urlopen") as network:
                    download_source(base, source_id)
                    network.assert_not_called()
            folder = base / "cityvizor-cernosice-2025"
            (folder / "payments.json").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "hash/size"):
                verify_source(folder, "cityvizor-cernosice-2025")

    def test_http403_retained_without_normalized_data_and_audit_distinguishes_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("https://example.test", 403, "Forbidden", {}, None)):
                manifest = download_source(base, "opencollective-webpack")
            self.assertEqual(manifest["errors"][0]["http_status"], 403)
            self.assertEqual(manifest["files"], [])
            report = audit_source(base, "opencollective-webpack")
            self.assertEqual(report["status"], "access_failed")
            self.assertIsNone(report["profile"])
            self.assertFalse(report["matching_gate"]["accepted"])
            self.assertFalse((base / "opencollective-webpack/bank.jsonl").exists())

    def test_participation_page_is_not_a_dataset_and_schema_error_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_fixture(base, "benchrec", {"participation.html": b"SYNTHETIC fixture"})
            report = audit_source(base, "benchrec")
            self.assertEqual(report["status"], "access_gated")
            self.assertIsNone(report["profile"])
            raw_fixture(base, "cityvizor-cernosice-2025", {"payments.json": b'[{"bad":1}]'})
            report = audit_source(base, "cityvizor-cernosice-2025")
            self.assertEqual(report["status"], "audit_failed")
            self.assertFalse(report["matching_gate"]["accepted"])


if __name__ == "__main__":
    unittest.main()
