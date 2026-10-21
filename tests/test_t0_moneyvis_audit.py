"""Archived MoneyVis audit and active source-policy guard; fixtures are synthetic."""

from contextlib import redirect_stderr, redirect_stdout
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from t0.__main__ import main
from scripts.archive.t0.audit_t0_moneyvis import (CSV_URL, HEADERS, audit_moneyvis, decimal_money,
                                         download_moneyvis, main as audit_main, sha256)


def fixture(directory, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(HEADERS)
    writer.writerows(rows)
    payload = stream.getvalue().encode()
    (directory / "moneyvis.csv").write_bytes(payload)
    (directory / "source_manifest.json").write_text(json.dumps({
        "source_id": "moneyvis-author-csv", "csv_url": CSV_URL,
        "sha256": sha256(payload), "bytes": len(payload),
        "use_policy": "inspection_only_excluded_from_matching",
        "fixture": "synthetic test rows, not real data",
    }), encoding="utf-8")


def row(day, debit="", credit="", balance="100.00"):
    return [day, "TEST", "SYNTH-SORT", "SYNTH-ACCOUNT", "SYNTH-DESC", debit, credit, balance]


class RealSourceAuditTests(unittest.TestCase):
    def test_archived_cli_is_offline_by_default_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            fixture(path, [row("01/01/2025", credit="1.00")])
            raw = (path / "moneyvis.csv").read_bytes()
            output = path / "audit.json"
            args = ["--input", str(path), "--output", str(output)]
            with patch("urllib.request.urlopen") as network, redirect_stdout(io.StringIO()):
                self.assertEqual(audit_main(args), 0)
                original = output.read_bytes()
                self.assertFalse(json.loads(original)["matching_gate"]["accepted"])
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as rejected:
                    audit_main([*args, "--download"])
                self.assertEqual(rejected.exception.code, 2)
                network.assert_not_called()
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual((path / "moneyvis.csv").read_bytes(), raw)

    def test_reverse_order_balance_exact_without_inventing_currency_or_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            fixture(path, [row("03/01/2025", debit="0.10", balance="100.20"),
                           row("02/01/2025", credit="0.30", balance="100.30"),
                           row("01/01/2025", credit="100.00")])
            report = audit_moneyvis(path)
            self.assertEqual(report["profile"]["balance_transitions"]["reverse_storage_balance_equation_pass"], 2)
            self.assertFalse(report["matching_gate"]["accepted"])
            self.assertEqual(report["matcher_runs"], 0)
            self.assertIsNone(report["precision"])
            self.assertIsNone(report["profile"]["currency"])
            self.assertNotIn("SYNTH-ACCOUNT", json.dumps(report))
            self.assertNotIn("SYNTH-DESC", json.dumps(report))
            self.assertFalse((path / "bank.jsonl").exists())

    def test_invalid_rows_are_reported_without_bridging_balance_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            fixture(path, [row("03/01/2025", credit="1.00"),
                           row("02/01/2025", debit="bad"),
                           row("01/01/2025", credit="1.00")])
            p = audit_moneyvis(path)["profile"]
            self.assertEqual(p["valid_rows"], 2)
            self.assertEqual(p["errors"][0]["csv_line"], 3)
            self.assertEqual(p["balance_transitions"]["checked"], 0)

    def test_balance_mismatch_is_preserved_and_duplicates_not_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            same = row("01/01/2025", credit="1.00")
            fixture(path, [same, same])
            p = audit_moneyvis(path)["profile"]
            self.assertEqual(p["rows"], 2)
            self.assertEqual(p["identical_row_occurrences_beyond_first"], 1)
            self.assertEqual(p["balance_transitions"]["reverse_mismatch_csv_lines"], [[2, 3]])

    def test_invalid_amounts_and_cash_direction(self):
        for value in ("NaN", "Infinity", "0.001", "bad"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                decimal_money(value)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            fixture(path, [row("01/01/2025", debit="-1.00"),
                           row("02/01/2025", debit="1.00", credit="1.00"),
                           row("03/01/2025")])
            self.assertEqual(len(audit_moneyvis(path)["profile"]["errors"]), 3)

    def test_hash_tampering_stops_audit_and_immutable_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            fixture(path, [row("01/01/2025", credit="1.00")])
            self.assertEqual(download_moneyvis(path)["source_id"], "moneyvis-author-csv")
            raw = path / "moneyvis.csv"
            raw.write_bytes(raw.read_bytes() + b"tampered")
            with self.assertRaises(ValueError):
                audit_moneyvis(path)
            with self.assertRaises(ValueError):
                download_moneyvis(path)

    def test_reconcile_and_evaluate_reject_before_loading_or_writing_matcher_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            fixture(path, [row("01/01/2025", credit="1.00")])
            for command in ("reconcile", "evaluate"):
                output = path / command
                args = [command, "--input", str(path), "--cutoff", "2025-01-01", "--output", str(output)]
                if command == "evaluate":
                    args.append("--truth-exhaustive")
                captured = io.StringIO()
                with redirect_stderr(captured):
                    self.assertEqual(main(args), 2)
                self.assertIn("Source excluded from matching", captured.getvalue())
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
