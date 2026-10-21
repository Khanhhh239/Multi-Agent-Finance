"""Financial edge cases and evaluator independence, not performance expectations."""

from copy import deepcopy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
import hashlib
import io

from t0 import benchrec, scenarios
from t0.data import allocation_errors, snapshot
from t0.evaluation import evaluate
from scripts.data_download import download_t0_benchrec as downloader
from scripts.data_audit import benchmark_t0_reconciliation as runner
from scripts.data_audit.research_t0_reconciliation import capture
from scripts.data_audit import research_t0_reconciliation as research


def row(identifier, amount, allocation=None, day="2025-01-01", reference="ref ABC"):
    result = {"id": identifier, "amount": Decimal(amount), "date": date.fromisoformat(day),
              "reference": reference, "currency": "USD", "account": "account1"}
    if allocation is not None:
        result["allocation"] = allocation
    return result


class BenchRecTests(unittest.TestCase):
    def test_signed_money_and_scope(self):
        a = [row("a1", "-10.10", "key1"), row("a2", "10.10", "key2")]
        b = [row("b1", "-10.10")]
        result = benchrec.match(a, b, "exact_amount_date")
        self.assertEqual(result["predictions"]["b1"]["a_ids"], ["a1"])
        b[0]["account"] = "other"
        self.assertFalse(benchrec.match(a, b, "bounded_group_sum")["predictions"])

    def test_groups_and_ambiguity(self):
        a = [row("a1", "4", "key1"), row("a2", "6", "key2")]
        b = [row("b1", "10")]
        result = benchrec.match(a, b, "bounded_group_sum")
        self.assertEqual(result["predictions"]["b1"]["allocations"], ["key1", "key2"])
        a.append(row("a3", "6", "key3"))
        self.assertFalse(benchrec.match(a, b, "bounded_group_sum")["predictions"])

    def test_global_conflicts_abstain_and_order_is_stable(self):
        a = [row("a1", "10", "key1")]
        b = [row("b1", "10"), row("b2", "10")]
        for method in benchrec.METHODS:
            result = benchrec.match(a, b, method)
            self.assertFalse(result["predictions"])
            self.assertEqual(result["prediction_hash"], benchrec.match(a, b[::-1], method)["prediction_hash"])

    def test_group_overflow_does_not_truncate(self):
        a = [row(f"a{i}", str(i + 1), f"key{i}") for i in range(13)]
        result = benchrec.match(a, [row("b", "100")], "bounded_group_sum")
        self.assertFalse(result["predictions"])
        self.assertEqual(result["diagnostics"]["group_pool_overflow_B"], 1)

    def test_subset_is_nonempty_and_null_is_not_positive(self):
        b = [row("b1", "10"), row("b2", "10"), row("b3", "10")]
        truth = {"b1": frozenset(("k1", "k2")), "b2": frozenset(), "b3": frozenset(("k3",))}
        predictions = {"b1": {"allocations": ["k1"]}, "b2": {"allocations": ["k2"]}}
        metrics = benchrec.score(b, truth, predictions)
        self.assertEqual(metrics["precision"], 0.5)
        self.assertEqual(metrics["match_rate"], 0.5)
        self.assertEqual(metrics["exact_set_precision"], 0)
        self.assertIsNone(benchrec.score(b, truth, {})["precision"])
        self.assertEqual(benchrec.score(b, truth, {})["match_rate"], 0)

    def test_allocation_whitespace_and_malformed_sets(self):
        self.assertEqual(benchrec.parse_allocations("[USD_ a  b,USD_c]"), frozenset(("USD_ a  b", "USD_c")))
        for value in ("[", "[]", "[a,a]", "[a,]", "a,b", "[a,[b]]", "a]", " ", None):
            with self.assertRaises(ValueError):
                benchrec.parse_allocations(value)

    def test_scorer_rejects_empty_duplicate_and_malformed_predictions(self):
        bank = [row("b", "10")]
        truth = {"b": frozenset({"key"})}
        for keys in ([], ["key", "key"], "key", [""], [None]):
            with self.subTest(keys=keys), self.assertRaises(ValueError):
                benchrec.score(bank, truth, {"b": {"allocations": keys}})
        with self.assertRaisesRegex(ValueError, "Duplicate bank"):
            benchrec.score(bank + bank, truth, {})
        with self.assertRaisesRegex(ValueError, "allocation sets"):
            benchrec.score(bank, {"b": "key"}, {})

    def test_invalid_numeric_config_and_truth_split(self):
        for kwargs in ({"date_window_days": True}, {"date_window_days": 0.5},
                       {"text_threshold": float("nan")}, {"group_candidate_cap": 12.5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                benchrec.Config(**kwargs)
        with self.assertRaisesRegex(ValueError, "Unknown truth split"):
            benchrec.load_truth(Path("no-input-should-be-read"), "typo", set(), set())

    def test_noise_never_changes_amount_or_output_keys(self):
        b = [row("b", "-100")]
        original = deepcopy(b)
        noisy, _ = benchrec.perturb(b, {"mask_reference": 1, "date_error_days": 3}, 11)
        self.assertEqual(b, original)
        self.assertEqual(noisy[0]["amount"], b[0]["amount"])
        self.assertEqual(noisy[0]["reference"], "")

    def test_invariant_detects_reuse_and_fake_allocation(self):
        a = [row("a", "10", "key")]
        b = [row("b1", "10"), row("b2", "10")]
        preds = {i: {"a_ids": ["a"], "allocations": ["fake"]} for i in ("b1", "b2")}
        errors = benchrec.invariant_errors(a, b, preds)
        self.assertEqual(errors["A_reused"], 1)
        self.assertEqual(errors["allocation_output_mismatch"], 2)

    def test_adapter_allowlist_ignores_labels_and_history(self):
        import csv
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            raw = {"A_id": "a", "B_id": "", "A_amount": "-10", "A_valueDate": "2025-01-01",
                   "A_currencyCode": "USD", "A_account": "account", "A_transactionReferences": "ref",
                   "A_transactionAttributes": "attr", "A_allocation": "USD_2025-01-01_account_attr",
                   "targetAllocation": "secret", "matchId": "secret", "wasPreviouslyMismatched": "secret"}

            def write():
                file = path / "BenchRec_cash_v1.0_train.csv"
                with file.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(raw))
                    writer.writeheader()
                    writer.writerow(raw)
                payload = file.read_bytes()
                (path / "source_manifest.json").write_text(json.dumps({"source_id": "benchrec-kaggle-v3",
                    "download_status": "downloaded", "files": [{"file": file.name, "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest()}]}), encoding="utf-8")
            write()
            before = benchrec.load_features(path, "train")
            raw["targetAllocation"] = raw["matchId"] = "different label"
            write()
            after = benchrec.load_features(path, "train")
            self.assertEqual(before, after)
            self.assertFalse({"targetAllocation", "matchId", "wasPreviouslyMismatched"} & before[0][0].keys())
            (path / "BenchRec_cash_v1.0_train.csv").write_text("tampered")
            with self.assertRaises(ValueError):
                benchrec.load_features(path, "train")


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(Path("research/references/data-checks/t0/reconciliation-benchmark-plan-v1.json").read_text())

    def test_truth_intent_stays_identical_across_noise(self):
        generated = [scenarios.generate(101, 2, name, spec)
                     for name, spec in self.plan["invoice_suite"]["profiles"].items()]
        self.assertEqual(len({g[3]["latent_world_hash"] for g in generated}), 1)
        projection = lambda g: {(r["transaction_id"], r["invoice_id"], r["amount_minor"]) for r in g[2]}
        self.assertTrue(all(projection(g) == projection(generated[0]) for g in generated))
        for invoices, bank, truth, manifest in generated:
            ii, _ = snapshot(invoices, "invoices", manifest["cutoff"])
            bb, quality = snapshot(bank, "bank", manifest["cutoff"])
            visible = {i["invoice_id"] for i in ii}
            self.assertEqual(allocation_errors(ii, bb, [r for r in truth if r["invoice_id"] in visible]), [])
            self.assertEqual(len(quality["quarantined"]), 2)
            result = evaluate(invoices, bank, truth, manifest["cutoff"], "reference_then_global")
            self.assertTrue(result["order_and_replay_stable"])
            self.assertFalse(result["invariant_errors"])

    def test_split_is_disjoint_and_ground_truth_not_a_matcher(self):
        spec = self.plan["invoice_suite"]
        self.assertFalse(set(spec["validation_seeds"]) & set(spec["test_seeds"]))
        self.assertNotIn("reconcile(", Path(scenarios.__file__).read_text())


class DownloadTests(unittest.TestCase):
    def archive(self, names):
        buffer = io.BytesIO()
        with ZipFile(buffer, "w") as archive:
            for name, value in names.items():
                archive.writestr(name, value)
        return buffer.getvalue()

    def test_archive_pinning_and_safe_members(self):
        payload = self.archive({"file.csv": b"header\nvalue\n"})
        expected = {"file.csv": hashlib.sha256(b"header\nvalue\n").hexdigest()}
        digest = hashlib.sha256(payload).hexdigest()
        self.assertEqual(downloader.checked_members(payload, digest, expected)["file.csv"], b"header\nvalue\n")
        with self.assertRaises(ValueError):
            downloader.checked_members(payload, "wrong", expected)
        with self.assertRaises(ValueError):
            downloader.checked_members(payload, digest, {"file.csv": "wrong"})
        unsafe = self.archive({"../escape.csv": b"data"})
        with self.assertRaises(ValueError):
            downloader.checked_members(unsafe, hashlib.sha256(unsafe).hexdigest(),
                                       {"../escape.csv": hashlib.sha256(b"data").hexdigest()})

    def test_download_is_immutable_and_cached_without_network(self):
        value = b"header\nvalue\n"
        payload = self.archive({"file.csv": value})
        digest = hashlib.sha256(payload).hexdigest()
        expected = {"file.csv": hashlib.sha256(value).hexdigest()}
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = payload
        with tempfile.TemporaryDirectory() as directory, patch.object(downloader, "ARCHIVE_HASH", digest), \
                patch.object(downloader, "EXPECTED", expected), patch.object(downloader, "urlopen", return_value=response) as network, \
                patch.object(downloader, "checked_members", wraps=lambda data: {"file.csv": value}):
            self.assertEqual(downloader.download(directory), "downloaded_verified")
            self.assertEqual(downloader.download(directory), "verified_cached")
            self.assertEqual(network.call_count, 1)
            (Path(directory) / "file.csv").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                downloader.download(directory)


class ExperimentProtectionTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(runner.PLAN.read_text(encoding="utf-8"))

    def test_plan_rejects_leaking_splits_and_invalid_noise(self):
        runner.validate_plan(self.plan)
        for mutation in ("overlap", "duplicate", "empty", "nonfinite", "negative_days", "invalid_blocks"):
            plan = deepcopy(self.plan)
            if mutation == "overlap":
                plan["invoice_suite"]["test_seeds"] = plan["invoice_suite"]["validation_seeds"]
            elif mutation == "duplicate":
                plan["benchrec"]["seeds"] = [1, 1]
            elif mutation == "empty":
                plan["benchrec"]["seeds"] = []
            elif mutation == "nonfinite":
                plan["benchrec"]["profiles"]["noisy"]["mask_reference"] = float("nan")
            elif mutation == "negative_days":
                plan["invoice_suite"]["profiles"]["noisy"]["date_error_days"] = -1
            else:
                plan["invoice_suite"]["blocks"] = 0
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                runner.validate_plan(plan)

    def test_partial_experiment_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            sentinel = path / "saved-predictions.json"
            sentinel.write_text('"preserve"', encoding="utf-8")
            with patch("sys.argv", ["benchmark", "--output", directory]), \
                    patch.object(runner, "run_invoice") as work, self.assertRaisesRegex(ValueError, "not empty"):
                runner.main()
            self.assertEqual(sentinel.read_text(), '"preserve"')
            work.assert_not_called()

    def test_unstable_experiment_fails_and_keeps_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "new"
            bad = {"summary": [{"all_invariants_pass": True, "all_order_and_replay_stable": False}]}
            with patch("sys.argv", ["benchmark", "--only", "invoice", "--output", str(output)]), \
                    patch.object(runner, "run_invoice", return_value=bad), self.assertRaisesRegex(ValueError, "stability failed"):
                runner.main()
            self.assertTrue((output / "experiment.json").exists())
            self.assertTrue((output / "report.json").exists())

    def test_source_cache_is_immutable_and_bound_to_source(self):
        source = {"id": "test", "kind": "academic", "url": "https://example.invalid/paper", "supports": "fixture"}
        with tempfile.TemporaryDirectory() as directory, patch("scripts.data_audit.research_t0_reconciliation.urlopen") as network:
            path = Path(directory)
            raw = path / "test.raw"
            raw.write_bytes(b"preserve")
            with self.assertRaisesRegex(ValueError, "Incomplete source cache"):
                capture(source, path)
            metadata = {**source, "sha256": hashlib.sha256(b"preserve").hexdigest(), "bytes": 8, "status": 200}
            (path / "test.json").write_text(json.dumps(metadata), encoding="utf-8")
            self.assertEqual(capture(source, path), metadata)
            with self.assertRaisesRegex(ValueError, "Cached source"):
                capture(dict(source, url="https://example.invalid/other"), path)
            self.assertEqual(raw.read_bytes(), b"preserve")
            network.assert_not_called()

    def test_research_report_is_not_overwritten_or_fetched_again(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            source = Path(directory) / "unread-snapshot"
            output.write_text("previous evidence", encoding="utf-8")
            with patch("sys.argv", ["research", "--input", str(source), "--output", str(output)]), \
                    patch.object(research, "capture") as fetch, self.assertRaisesRegex(ValueError, "Research report exists"):
                research.main()
            self.assertFalse(source.exists())
            self.assertEqual(output.read_text(), "previous evidence")
            fetch.assert_not_called()

    def test_verify_existing_rechecks_metrics_and_detects_changed_truth(self):
        plan = deepcopy(self.plan)
        plan["invoice_suite"].update(blocks=1, validation_seeds=[7], test_seeds=[8])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            payload = {"plan": plan, "invoice": runner.run_invoice(plan, path)}
            historical = path / "report.json"
            historical.write_text(json.dumps(payload), encoding="utf-8")
            original = historical.read_bytes()
            verification = runner.verify_existing(path, Path("unused-source"))
            self.assertEqual(verification["invoice_runs_verified"], 24)
            self.assertEqual(historical.read_bytes(), original)
            manifest_path = path / "invoice-datasets/validation/clean-7/manifest.json"
            manifest_bytes = manifest_path.read_bytes()
            changed_manifest = json.loads(manifest_bytes)
            changed_manifest["blocks"] += 1
            manifest_path.write_text(json.dumps(changed_manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "manifest changed"):
                runner.verify_existing(path, Path("unused-source"))
            manifest_path.write_bytes(manifest_bytes)
            truth = path / "invoice-datasets/validation/clean-7/truth.jsonl"
            truth.write_bytes(truth.read_bytes() + b'{}\n')
            with self.assertRaisesRegex(ValueError, "input/truth changed"):
                runner.verify_existing(path, Path("unused-source"))
            payload["invoice"]["runs"].pop()
            historical.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Historical runs"):
                runner.verify_existing(path, Path("unused-source"))


if __name__ == "__main__":
    unittest.main()
