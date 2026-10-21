"""Financial/cutoff invariants and independent checks of the T0 evaluator."""

import copy
import hashlib
import itertools
from pathlib import Path
import random
import tempfile
import unittest

from t0.data import allocation_errors, save_receipt_dataset, snapshot
from t0.evaluation import evaluate, metrics
from scripts.archive.t0.benchmark_t0_receipts_v01 import benchmark
from t0.matching import Config, METHODS, maximum_weight_assignment, reconcile, references
from scripts.archive.t0.generate_t0_receipts_v01 import generate
from t0.__main__ import main


def invoice(**overrides):
    return {"tenant_id": "A", "invoice_id": "INV-1", "version": 1,
            "customer_id": "C1", "customer_name": "Cong ty An Phat", "currency": "VND",
            "amount_minor": 100, "issued_on": "2025-01-01", "due_on": "2025-01-31",
            "effective_on": "2025-01-01", "available_on": "2025-01-01", **overrides}


def receipt(**overrides):
    return {"tenant_id": "A", "transaction_id": "B1", "version": 1,
            "customer_id": "C1", "counterparty": "Cong ty An Phat", "currency": "VND",
            "amount_minor": 100, "booked_on": "2025-01-31", "effective_on": "2025-01-31",
            "available_on": "2025-01-31", "reference": "TT INV-1", **overrides}


class SnapshotTests(unittest.TestCase):
    def test_future_revision_is_not_visible_at_cutoff(self):
        old = invoice()
        revised = invoice(version=2, amount_minor=150, available_on="2025-03-01")
        rows, quality = snapshot([old, revised], "invoices", "2025-02-01")
        self.assertEqual(rows, [old])
        self.assertEqual(quality["future_rows"], 1)
        self.assertEqual(snapshot([old, revised], "invoices", "2025-03-01")[0], [revised])

    def test_invalid_future_payload_does_not_affect_past(self):
        future = invoice(version=2, amount_minor="BAD", available_on="2025-03-01")
        rows, q = snapshot([invoice(), future], "invoices", "2025-02-01")
        self.assertEqual(len(rows), 1)
        self.assertFalse(q["quarantined"])

    def test_late_arrival_and_future_effective_revision(self):
        late = invoice(available_on="2025-04-01")
        self.assertEqual(snapshot([late], "invoices", "2025-03-01")[0], [])
        future = invoice(version=2, amount_minor=200, effective_on="2025-05-01",
                         available_on="2025-02-01")
        self.assertEqual(snapshot([invoice(), future], "invoices", "2025-04-01")[0], [invoice()])
        self.assertEqual(snapshot([invoice(), future], "invoices", "2025-05-01")[0], [future])

    def test_duplicate_idempotency_and_conflict_fail_closed(self):
        rows, q = snapshot([invoice(), invoice()], "invoices", "2025-02-01")
        self.assertEqual(len(rows), 1)
        self.assertEqual(q["duplicate_deliveries"], 1)
        rows, q = snapshot([invoice(), invoice(amount_minor=200)], "invoices", "2025-02-01")
        self.assertFalse(rows)
        self.assertEqual(len(q["quarantined"]), 1)

    def test_bad_newest_version_does_not_resurrect_old(self):
        rows, q = snapshot([invoice(), invoice(version=2, amount_minor=-1)], "invoices", "2025-02-01")
        self.assertFalse(rows)
        self.assertTrue(q["quarantined"])
        rows, q = snapshot([invoice(), invoice(version="2")], "invoices", "2025-02-01")
        self.assertFalse(rows)

    def test_quality_dates_money_and_versions(self):
        for changes in ({"amount_minor": 1.5}, {"amount_minor": True}, {"amount_minor": 0},
                        {"issued_on": "20250101"}, {"due_on": "2024-01-01"},
                        {"currency": "vnd"}, {"currency": "123"}, {"version": 0}):
            with self.subTest(changes=changes):
                rows, quality = snapshot([invoice(**changes)], "invoices", "2025-02-01")
                self.assertFalse(rows)
                self.assertTrue(quality["quarantined"])

    def test_negative_bank_transaction_quarantined(self):
        rows, q = snapshot([receipt(amount_minor=-100)], "bank", "2025-02-01")
        self.assertFalse(rows)
        self.assertTrue(q["quarantined"])

    def test_business_date_and_availability_both_bound(self):
        rows, _ = snapshot([receipt(booked_on="2025-03-01")], "bank", "2025-02-01")
        self.assertFalse(rows)


class MatchingTests(unittest.TestCase):
    def test_reference_token_boundaries_and_vietnamese_normalization(self):
        self.assertFalse(references(receipt(reference="INV-10"), invoice()))
        self.assertTrue(references(receipt(reference="TT: inv/1."), invoice()))

    def test_partial_then_final_payment(self):
        result = reconcile([invoice()], [receipt(amount_minor=40), receipt(
            transaction_id="B2", amount_minor=60, booked_on="2025-02-01")])
        self.assertEqual([r["amount_minor"] for r in result["allocations"]], [40, 60])
        self.assertFalse(result["invariant_errors"])
        self.assertEqual(reconcile([invoice()], [receipt(amount_minor=40)], "exact_reference")["allocations"], [])

    def test_grouped_payment(self):
        other = invoice(invoice_id="INV-2", amount_minor=200)
        result = reconcile([invoice(), other], [receipt(amount_minor=300, reference="INV-1 INV-2")])
        self.assertEqual([r["amount_minor"] for r in result["allocations"]], [100, 200])

    def test_overpayment_and_group_ambiguity_abstain(self):
        self.assertFalse(reconcile([invoice()], [receipt(amount_minor=101)])["allocations"])
        other = invoice(invoice_id="INV-2", customer_id="C2")
        self.assertFalse(reconcile([invoice(), other], [receipt(
            amount_minor=200, customer_id="", reference="INV-1 INV-2")])["allocations"])

    def test_ambiguous_amount_and_identity_abstain(self):
        for method in METHODS:
            result = reconcile([invoice(), invoice(invoice_id="INV-2")],
                               [receipt(reference="cong no")], method)
            self.assertEqual(result["allocations"], [], method)

    def test_same_invoice_cannot_receive_more_than_face_value(self):
        result = reconcile([invoice()], [receipt(), receipt(transaction_id="B2")])
        self.assertEqual(sum(a["amount_minor"] for a in result["allocations"]), 100)

    def test_tenant_currency_customer_and_date_guards(self):
        for changes in ({"tenant_id": "B"}, {"currency": "USD"}, {"customer_id": "C2"},
                        {"booked_on": "2024-12-31"}, {"booked_on": "2025-12-31"}):
            for method in METHODS:
                with self.subTest(changes=changes, method=method):
                    self.assertFalse(reconcile([invoice()], [receipt(**changes)], method)["allocations"])

    def test_input_is_not_mutated(self):
        inv, bank = [invoice()], [receipt()]
        before = copy.deepcopy((inv, bank))
        reconcile(inv, bank)
        self.assertEqual((inv, bank), before)

    def test_missing_names_do_not_count_as_identity_evidence(self):
        inv = invoice(customer_name="")
        bank = receipt(customer_id="", counterparty="", reference="cong no")
        self.assertFalse(reconcile([inv], [bank], "scored_global")["allocations"])

    def test_explicit_reference_does_not_fall_back_to_unreferenced_invoice(self):
        inv = [invoice(amount_minor=200), invoice(invoice_id="INV-2")]
        for method in ("scored_global", "reference_then_global"):
            # 100 against a referenced invoice of 200 can be a partial receipt;
            # the hybrid may allocate it to INV-1, never the unrelated INV-2.
            result = reconcile(inv, [receipt()], method)
            self.assertTrue(all(r["invoice_id"] == "INV-1" for r in result["allocations"]))

    def test_global_assignment_beats_local_greedy(self):
        weights = [[0.9, 0.8], [0.85, -1]]
        result = maximum_weight_assignment(weights)
        self.assertEqual(set(result), {(0, 1), (1, 0)})
        self.assertEqual(maximum_weight_assignment([[-1], [-1]]), [])

    def test_global_assignment_matches_independent_brute_force(self):
        rng = random.Random(9)
        for n in range(1, 5):
            for m in range(1, 4):
                for _ in range(10):
                    weights = [[rng.choice([-1, 0.1, 0.4, 0.9]) for _ in range(m)] for _ in range(n)]
                    actual = sum(weights[i][j] for i, j in maximum_weight_assignment(weights))
                    best = 0
                    for choices in itertools.product(range(-1, m), repeat=n):
                        real = [j for j in choices if j >= 0]
                        if len(real) == len(set(real)):
                            value = sum(weights[i][j] for i, j in enumerate(choices) if j >= 0)
                            best = max(best, value)
                    self.assertAlmostEqual(actual, best)

    def test_invariants_catch_overallocation_and_wrong_scope(self):
        a = reconcile([invoice()], [receipt()])["allocations"][0]
        self.assertIn("invoice over-allocated", allocation_errors([invoice()], [receipt()], [dict(a, amount_minor=101)]))
        self.assertIn("cross-currency allocation", allocation_errors([invoice()], [receipt()], [dict(a, currency="USD")]))
        self.assertIn("unknown or cross-tenant endpoint", allocation_errors([invoice()], [receipt()], [dict(a, tenant_id="B")]))


class EvaluationTests(unittest.TestCase):
    def test_wrong_amount_is_not_counted_as_correct_link(self):
        pred = reconcile([invoice()], [receipt()])
        truth = [dict(pred["allocations"][0], amount_minor=80)]
        result = metrics([invoice()], [receipt()], truth, pred)
        self.assertEqual(result["precision"], 0)
        self.assertEqual(result["recall"], 0)
        self.assertEqual(result["money_by_currency"]["VND"]["wrongly_allocated_minor"], 20)

    def test_empty_precision_is_null_and_no_truth_is_not_perfect_recall(self):
        result = reconcile([invoice()], [receipt(amount_minor=101)])
        measured = metrics([invoice()], [receipt(amount_minor=101)], [], result)
        self.assertIsNone(measured["precision"])
        self.assertIsNone(measured["recall"])

    def test_missing_and_false_links_money_are_measured_separately(self):
        inv = [invoice(), invoice(invoice_id="INV-2")]
        predicted = reconcile(inv, [receipt()])
        truth = [dict(predicted["allocations"][0], invoice_id="INV-2")]
        measured = metrics(inv, [receipt()], truth, predicted)
        self.assertEqual(measured["money_by_currency"]["VND"]["wrongly_allocated_minor"], 100)
        self.assertEqual(measured["money_by_currency"]["VND"]["missing_truth_minor"], 100)

    def test_bad_truth_rejected(self):
        result = reconcile([invoice()], [receipt()])
        truth = [dict(result["allocations"][0], amount_minor=200)]
        with self.assertRaisesRegex(ValueError, "invalid truth"):
            metrics([invoice()], [receipt()], truth, result)

    def test_invalid_predictions_are_rejected_before_edge_deduplication(self):
        result = reconcile([invoice()], [receipt()])
        truth = list(result["allocations"])
        result["allocations"] *= 2
        with self.assertRaisesRegex(ValueError, "invalid predictions"):
            metrics([invoice()], [receipt()], truth, result)

    def test_synthetic_deterministic_independent_seed_and_replay(self):
        self.assertEqual(generate(11, 1), generate(11, 1))
        self.assertNotEqual(generate(11, 1), generate(12, 1))
        for profile in ("clean", "noisy", "stress"):
            inv, bank, truth, manifest = generate(101, 2, profile)
            for method in METHODS:
                measured = evaluate(inv, bank, truth, manifest["cutoff"], method)
                self.assertTrue(measured["order_and_replay_stable"])
                self.assertFalse(measured["invariant_errors"])
                self.assertEqual(set(measured["money_by_currency"]), {"VND", "USD"})

    def test_existing_synthetic_instance_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            save_receipt_dataset(root, generate(101, 1))
            original = (root / "invoices.jsonl").read_bytes()
            save_receipt_dataset(root, generate(101, 1))
            with self.assertRaisesRegex(ValueError, "choose a new --output"):
                save_receipt_dataset(root, generate(102, 1))
            self.assertEqual((root / "invoices.jsonl").read_bytes(), original)

    def test_future_endpoints_excluded_from_scoring(self):
        inv, bank, truth, manifest = generate(101, 1)
        measured = evaluate(inv, bank, truth, manifest["cutoff"], "exact_reference")
        self.assertNotIn("late_arrival", measured["by_scenario"])
        self.assertEqual(measured["excluded_truth_edges"], 1)

    def test_truth_unknown_raw_endpoint_is_rejected(self):
        truth = [{"tenant_id": "A", "transaction_id": "TYPO", "invoice_id": "INV-1"}]
        with self.assertRaisesRegex(ValueError, "absent from raw"):
            evaluate([invoice()], [receipt()], truth, "2025-06-30", "exact_reference")

    def test_small_benchmark_and_split_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            report = benchmark(folder, blocks=1, validation_seeds=(1,), test_seeds=(2,), profiles=("noisy",))
            self.assertEqual(len(report["runs"]), 8)
            self.assertTrue((Path(folder) / "benchmark.json").is_file())
            self.assertTrue(all(r["all_invariants_pass"] for r in report["summary"]))
            root = Path(__file__).resolve().parents[1]
            for name in ("benchmark_t0_receipts_v01.py", "generate_t0_receipts_v01.py"):
                relative = "scripts/archive/t0/" + name
                self.assertEqual(report["source_sha256"][relative],
                                 hashlib.sha256((root / relative).read_bytes()).hexdigest())
            saved = (Path(folder) / "benchmark.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "new --output"):
                benchmark(folder, blocks=1, validation_seeds=(1,), test_seeds=(2,), profiles=("noisy",))
            self.assertEqual((Path(folder) / "benchmark.json").read_bytes(), saved)
            with self.assertRaisesRegex(ValueError, "disjoint"):
                benchmark(folder, validation_seeds=(1,), test_seeds=(1,))

    def test_cli_reconcile_does_not_read_truth(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            save_receipt_dataset(root, generate(101, 1))
            (root / "truth.jsonl").unlink()
            result = main(["reconcile", "--input", str(root), "--cutoff", "2025-06-30",
                           "--output", str(root / "output")])
            self.assertEqual(result, 0)
            self.assertTrue((root / "output/allocations.jsonl").is_file())

    def test_config_threshold_validation(self):
        with self.assertRaises(ValueError):
            Config(score_threshold=1.1)


if __name__ == "__main__":
    unittest.main()
