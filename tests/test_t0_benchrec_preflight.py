"""Synthetic fixtures for the structural BenchRec preflight, never model labels."""

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.data_audit.audit_t0_benchrec import FILES, audit, audit_train_semantics, profile_csv


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class BenchRecPreflightTests(unittest.TestCase):
    def test_train_group_discrepancies_are_reported_not_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            fields = ["matchId", "A_id", "B_id", "A_debitOrCredit", "B_debitOrCredit",
                      "A_amount", "B_amount", "A_currencyCode", "B_currencyCode",
                      "A_account", "B_account", "A_allocation", "targetAllocation"]
            path = folder / FILES["train"]
            write_csv(path, fields, [
                {"matchId": "group", "A_id": "SYNTH-A", "A_debitOrCredit": "CR", "A_amount": "10.25",
                 "A_currencyCode": "USD", "A_account": "SYNTH-account", "A_allocation": "SYNTH-key"},
                {"matchId": "group", "B_id": "SYNTH-B", "B_debitOrCredit": "DR", "B_amount": "10.00",
                 "B_currencyCode": "USD", "B_account": "SYNTH-account", "targetAllocation": "SYNTH-key"}])
            payload = path.read_bytes()
            (folder / "source_manifest.json").write_text(json.dumps({"source_id": "benchrec-kaggle-v3",
                "download_status": "downloaded", "files": [{"file": path.name, "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest()}]}), encoding="utf-8")
            result = audit_train_semantics(folder)
            self.assertEqual(result["counts"]["different_signed_sum_groups"], 1)
            self.assertEqual(result["counts"]["groups_with_any_B_target_outside_A_group_keys"], 0)
            self.assertEqual(result["absolute_group_sum_discrepancy_by_currency"], {"USD": "0.25"})
            self.assertEqual(path.read_bytes(), payload)
            self.assertNotIn("SYNTH-", json.dumps(result))

    def test_signed_amounts_and_side_grain_are_reported_without_exposing_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.csv"
            write_csv(path, ["A_id", "B_id", "A_transactionType", "B_transactionType", "A_amount", "B_amount", "targetAllocation"], [
                {"A_id": "SYNTH-PRIVATE-A", "A_transactionType": "A", "A_amount": "-1.25"},
                {"B_id": "SYNTH-PRIVATE-B", "B_transactionType": "B", "B_amount": "1.25", "targetAllocation": "SYNTH-PRIVATE-LABEL"},
                {"B_id": "SYNTH-PRIVATE-B", "B_transactionType": "B", "B_amount": "NaN"}])
            report, _ = profile_csv(path)
            self.assertEqual(report["row_shapes_by_present_id"], {"A": 1, "B": 2})
            self.assertEqual(report["A_amount_negative"], 1)
            self.assertEqual(report["B_id_duplicate_occurrences"], 1)
            self.assertEqual(report["issues"], {"B_amount_parse_errors": 1})
            self.assertNotIn("SYNTH-PRIVATE", json.dumps(report))

    def test_malformed_rows_and_repeated_header_are_not_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.csv"
            path.write_text("A_id,B_id\nSYNTH-A\n", encoding="utf-8")
            report, _ = profile_csv(path)
            self.assertEqual(report["issues"]["malformed_csv_rows"], 1)
            path.write_text("A_id,A_id\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                profile_csv(path)

    def test_solution_coverage_and_raw_hash_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            fields = ["A_id", "B_id", "A_transactionType", "B_transactionType", "A_allocation", "targetAllocation", "matchId"]
            write_csv(folder / FILES["train"], fields, [{"A_id": "SYNTH-TRAIN-A"}])
            write_csv(folder / FILES["eval"], fields, [{"B_id": "SYNTH-EVAL-B"}])
            write_csv(folder / FILES["solution"], ["B_id", "targetAllocation", "Usage"], [{"B_id": "SYNTH-OTHER-B"}])
            write_csv(folder / FILES["submission_example"], ["B_id"], [{"B_id": "SYNTH-EVAL-B"}])
            manifest = {"source_id": "benchrec-kaggle-v3", "download_status": "downloaded",
                        "use_policy": "inspection_only_excluded_from_matching", "files": []}
            for name in FILES.values():
                payload = (folder / name).read_bytes()
                manifest["files"].append({"file": name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
            (folder / "source_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            report = audit(folder)
            self.assertEqual(report["identity_checks"]["eval_B_ids_missing_solution"], 1)
            self.assertEqual(report["identity_checks"]["solution_B_ids_absent_from_eval"], 1)
            self.assertEqual(report["matcher_runs"], 0)
            self.assertFalse(report["accepted_for_current_invoice_matcher"])
            (folder / FILES["eval"]).write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "hash/size"):
                audit(folder)


if __name__ == "__main__":
    unittest.main()
