"""T0 v2 financial invariants, causal cutoff and independent evaluator checks."""

from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from t0 import allocation, journal, offline, settlement
from t0.__main__ import load_allocation_input, main
from t0.adapters import component_splits, minor, normalize_finrca, statement_checks, verified_source
from t0.data import write_json
from t0.ledger import EventStore, replay


def invoice(identifier="I1", amount=100, **kwargs):
    return {"tenant_id": "A", "id": identifier, "invoice_number": "INV-" + identifier,
            "side": "AR", "party_id": "C", "currency": "VND", "amount_minor": amount,
            "issued_on": "2025-01-01", "due_on": "2025-01-31", **kwargs}


def payment(identifier="P1", amount=100, **kwargs):
    return {"tenant_id": "A", "id": identifier, "side": "AR", "party_id": "C", "currency": "VND",
            "amount_minor": amount, "payment_on": "2025-01-31", "reference": "INV-I1", **kwargs}


def commands():
    return [offline.record("invoice", "I1", 100, side="AR", party_id="C", invoice_number="INV-I1"),
            offline.record("payment", "P1", 120, side="AR", party_id="C"),
            offline.decision("suggest", allocations=[{"invoice_id": "I1", "payment_id": "P1", "amount_minor": 100}]),
            offline.decision("approve"), offline.decision("commit", external_result="verified")]


class AllocationTests(unittest.TestCase):
    def test_overpayment_allocates_only_debt_and_keeps_credit(self):
        result = allocation.allocate([invoice()], [payment(amount=120)])
        self.assertEqual(result["allocations"][0]["amount_minor"], 100)
        self.assertEqual(result["decisions"][0]["unallocated_minor"], 20)
        self.assertFalse(allocation.allocate([invoice()], [payment(amount=120)], overpayment=False)["allocations"])

    def test_same_day_partial_payments_do_not_depend_on_order(self):
        ps = [payment("P1", 40), payment("P2", 60)]
        result = allocation.allocate([invoice()], ps)
        self.assertEqual(sum(a["amount_minor"] for a in result["allocations"]), 100)
        self.assertEqual(result["allocation_hash"], allocation.allocate([invoice()], ps[::-1])["allocation_hash"])
        conflict = allocation.allocate([invoice()], [payment("P1", 60), payment("P2", 60)])
        self.assertFalse(conflict["allocations"])
        self.assertTrue(all(d["reason"] == "competing_references" for d in conflict["decisions"]))

    def test_invoice_number_is_distinct_from_internal_id_and_scope_blocks(self):
        i = invoice("internal-uuid", invoice_number="BILL-100")
        p = payment(reference="paid BILL-100")
        self.assertEqual(allocation.allocate([i], [p])["allocations"][0]["invoice_id"], "internal-uuid")
        for field, value in (("currency", "USD"), ("side", "AP"), ("party_id", "OTHER"), ("payment_on", "2024-12-01")):
            with self.subTest(field=field):
                self.assertFalse(allocation.allocate([i], [{**p, field: value}])["allocations"])
        self.assertFalse(allocation.allocate([i], [payment(reference="BILL-1000", party_id="")])["allocations"])

    def test_cross_currency_reference_never_falls_back_to_other_invoice(self):
        inv = [invoice(currency="USD"), invoice("I2")]
        self.assertFalse(allocation.allocate(inv, [payment()])["allocations"])
        duplicate_number = [invoice(amount=40), invoice("I2", 60, invoice_number="INV-I1")]
        self.assertFalse(allocation.allocate(duplicate_number, [payment()])["allocations"])

    def test_group_uniqueness_and_budget_are_not_truncated(self):
        inv = [invoice("I1", 40), invoice("I2", 60)]
        p = payment(reference="no invoice")
        result = allocation.allocate(inv, [p])
        self.assertEqual(len(result["allocations"]), 2)
        self.assertFalse(allocation.allocate(inv + [invoice("I3", 60)], [p])["allocations"])
        pool = [invoice(str(n), 1) for n in range(13)]
        result = allocation.allocate(pool, [payment(amount=5, reference="")])
        self.assertEqual(result["decisions"][0]["reason"], "group_pool_overflow")
        self.assertFalse(result["allocations"])

    def test_underdetermined_partial_group_and_shared_groups_are_reviewed(self):
        inv = [invoice("I1", 40), invoice("I2", 60)]
        p = payment(amount=70, reference="INV-I1 + INV-I2")
        self.assertEqual(allocation.allocate(inv, [p])["decisions"][0]["status"], "review")
        ps = [payment("P1", reference=""), payment("P2", reference="")]
        self.assertFalse(allocation.allocate(inv, ps)["allocations"])

    def test_unknown_party_amount_only_cannot_auto_match(self):
        self.assertFalse(allocation.allocate([invoice()], [payment(party_id="", reference="")])["allocations"])
        self.assertFalse(allocation.allocate([invoice(invoice_number="发票")],
                                            [payment(amount=50, party_id="", reference="nothing")])["allocations"])

    def test_money_types_and_duplicate_id_fail(self):
        for value in (True, 1.5, -1, 0):
            with self.assertRaises(ValueError):
                allocation.allocate([invoice(amount=value)], [payment()])
        with self.assertRaises(ValueError):
            allocation.allocate([invoice(), invoice()], [payment()])


class LedgerTests(unittest.TestCase):
    def test_approval_is_not_commit_and_reversal_once(self):
        events = commands()
        self.assertEqual(replay(events[:4], "2025-02-01")["invoices"][0]["outstanding_minor"], 100)
        self.assertEqual(replay(events, "2025-02-01")["invoices"][0]["outstanding_minor"], 0)
        events.append(offline.decision("reverse", day="2025-02-02"))
        self.assertEqual(replay(events, "2025-02-02")["invoices"][0]["outstanding_minor"], 100)
        with self.assertRaises(ValueError):
            replay(events + [events[-1]], "2025-02-03")

    def test_unknown_result_requires_verification_before_retry(self):
        events = commands()
        events[-1]["external_result"] = "unknown"
        self.assertEqual(replay(events, "2025-02-01")["invoices"][0]["outstanding_minor"], 100)
        with self.assertRaises(ValueError):
            replay(events + [offline.decision("commit", external_result="verified")], "2025-02-01")
        events.append(offline.decision("verify", external_result="not_committed"))
        events.append(offline.decision("commit", external_result="verified"))
        self.assertEqual(replay(events, "2025-02-01")["invoices"][0]["outstanding_minor"], 0)

    def test_unknown_result_also_blocks_a_new_decision_on_same_payment(self):
        events = commands()
        events[-1]["external_result"] = "unknown"
        events += [offline.decision("suggest", identifier="D2", allocations=[{"invoice_id": "I1", "payment_id": "P1", "amount_minor": 100}]),
                   offline.decision("approve", identifier="D2"),
                   offline.decision("commit", identifier="D2", external_result="verified")]
        with self.assertRaisesRegex(ValueError, "unknown"):
            replay(events, "2025-02-01")

    def test_unknown_result_blocks_refund_of_uncertain_unapplied_credit(self):
        events = commands()
        events[-1]["external_result"] = "unknown"
        with self.assertRaisesRegex(ValueError, "unknown"):
            replay(events + [offline.record("refund", "R1", 100, day="2025-02-02", payment_id="P1")], "2025-02-02")

    def test_late_arrival_and_backdated_reversal_cannot_change_old_gold(self):
        events = commands()
        old = replay(events, "2025-01-31")
        reverse = offline.decision("reverse", day="2025-02-02")
        reverse["effective_on"] = "2025-01-31"
        self.assertEqual(old, replay(events + [reverse], "2025-01-31"))
        self.assertEqual(replay(events + [reverse], "2025-02-02")["invoices"][0]["outstanding_minor"], 100)
        late = offline.record("bank", "B1", 120, day="2025-02-03", direction="credit")
        late["effective_on"] = "2025-01-20"
        self.assertFalse(replay(events + [reverse, late], "2025-02-02")["bank_movements"])

    def test_durable_exact_retry_mismatch_and_atomic_invalid_insert(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "ledger.sqlite"
            with EventStore(db) as store:
                for n, e in enumerate(commands()):
                    store.submit(str(n), e)
                expected = store.gold("2025-02-01")
            with EventStore(db) as store:
                self.assertTrue(store.submit("4", commands()[4])["replayed"])
                self.assertEqual(store.gold("2025-02-01"), expected)
                with self.assertRaises(ValueError):
                    store.submit("4", offline.decision("reverse"))
                with self.assertRaises(ValueError):
                    store.submit("new", offline.record("refund", "R1", 30, day="2025-02-02", payment_id="P1"))
                self.assertEqual(len(store.events()), 5)

    def test_credit_note_refund_and_fee_are_not_cash_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = offline.ledger_demo(Path(tmp) / "demo")
        snapshots = report["snapshots"]
        self.assertEqual(snapshots["2025-01-31"]["outstanding_minor"], 900)
        self.assertEqual(snapshots["2025-02-01"]["outstanding_minor"], 0)
        self.assertEqual(snapshots["2025-02-01"]["unallocated_minor"], 200)
        self.assertEqual(snapshots["2025-02-03"]["cash_movements"][0]["net_minor"], 880)

    def test_unsupported_fx_and_duplicate_bank_link_fail(self):
        events = [offline.record("payment", "P1", 100, side="AR", party_id="C"),
                  offline.record("bank", "B1", 90, direction="credit"),
                  offline.record("bank_link", "L1", 0, payment_id="P1", bank_id="B1", fee_minor=10)]
        self.assertEqual(len(replay(events, "2025-02-01")["bank_links"]), 1)
        bad = deepcopy(events[-1]); bad["data"]["id"] = "L2"
        with self.assertRaises(ValueError):
            replay(events + [bad], "2025-02-01")
        events[1]["data"]["currency"] = "USD"
        with self.assertRaises(ValueError):
            replay(events, "2025-02-01")

    def test_ap_direction_and_scope_are_preserved(self):
        events = commands()
        events[0]["data"]["side"] = events[1]["data"]["side"] = "AP"
        self.assertEqual(replay(events, "2025-02-01")["invoices"][0]["side"], "AP")
        events[1]["data"]["party_id"] = "WRONG"
        with self.assertRaises(ValueError):
            replay(events, "2025-02-01")


class AdapterAndEvaluationTests(unittest.TestCase):
    def test_currency_scale_is_exact_never_rounds_or_takes_abs(self):
        self.assertEqual(minor("12.30", "USD"), 1230)
        self.assertEqual(minor("-12", "JPY"), -12)
        for value, currency in (("1.01", "JPY"), (1.1, "USD"), ("NaN", "USD"), ("1", "XXX")):
            with self.assertRaises(ValueError):
                minor(value, currency)

    def test_split_unions_clean_corrupted_relationships(self):
        stages = {"clean": {"invoices": [{"id": "i1"}, {"id": "i2"}], "payments": [{"id": "p1"}, {"id": "p2"}],
                            "allocations": [{"invoice_id": "i1", "payment_id": "p1"}]},
                  "corrupted": {"invoices": [], "payments": [], "allocations": [
                      {"invoice_id": "i2", "payment_id": "p1"}, {"invoice_id": "i2", "payment_id": "p2"}]}}
        self.assertEqual(len({v["world_id"] for v in component_splits(stages).values()}), 1)

    def test_finrca_corrupted_allocation_preserved_with_diagnostics(self):
        tables = {"invoices": [{"invoice_id": "i", "vendor_id": "v", "currency": "USD", "invoice_number": "BILL-1",
                                  "invoice_total": "1.00", "invoice_date": "2025-01-01", "due_date": "2025-01-31"}],
                  "payments": [{"payment_id": "p", "vendor_id": "v", "payment_currency": "USD", "payment_amount": "2.00",
                                "payment_date": "2025-01-31", "reference_number": "PMT-1"}],
                  "bank_transactions": [], "bank_statements": [],
                  "payment_allocations": [{"invoice_id": "i", "payment_id": "p", "allocated_amount": "1.20", "allocation_date": "2025-01-31"}]}
        hashes = {f"data/benchmark/full/{n}.csv": "fixture-hash" for n in tables}
        result = normalize_finrca(tables, "benchmark/full", hashes)
        self.assertEqual(result["allocations"][0]["amount_minor"], 120)
        self.assertIn("invoice_overallocated", result["allocations"][0]["reasons"])
        self.assertIsNone(result["audit"]["matching_quality"])
        self.assertEqual(result["invoices"][0]["side"], "AP")

    def test_statements_equation_is_not_transaction_reconciliation(self):
        statements = [{"bank_statement_id": "s", "bank_account_id": "a", "statement_date": "2025-01-31",
                       "opening_balance": "100", "closing_balance": "90", "total_credits": "0", "total_debits": "10"}]
        result = statement_checks(statements, [])
        self.assertEqual(result["equation_failures"], 0)
        self.assertEqual(result["posted_date_total_failures"], 1)

    def test_evaluator_counts_wrong_amount_not_just_edge(self):
        i, p = invoice(), payment(amount=120)
        truth = [{"tenant_id": "A", "invoice_id": "I1", "payment_id": "P1", "side": "AR", "currency": "VND", "amount_minor": 90, "scenario": "partial"}]
        result = allocation.allocate([i], [p])
        measured = offline.metrics([i], [p], truth, result)
        self.assertEqual(measured["precision"], 0)
        self.assertEqual(measured["money_by_currency"]["VND"]["wrong_minor"], 10)
        with self.assertRaisesRegex(ValueError, "raw universe"):
            offline.metrics([i], [p], [{**truth[0], "invoice_id": "ABSENT"}], result)

    def test_settlement_unknown_endpoint_never_becomes_negative(self):
        p = [{"payout_id": "p1", "payout_ref": "P-1", "amount_minor": "100", "settle_currency": "USD", "expected_arrival_date": "2025-01-01"}]
        b = [{"stmt_line_id": "b1", "currency": "USD", "amount_minor": "100", "direction": "credit", "value_date": "2025-01-01", "reference": "P-1"}]
        truth = [{"payout_id": "MISSING", "stmt_line_id": "b1"}]
        labels = [{"stmt_line_id": "b1", "is_matchable": "true"}]
        measured = settlement.score(p, b, truth, labels, {"b1": "p1"})
        self.assertEqual(measured["predictions_on_unknown_bank_rows"], 1)
        self.assertIsNone(measured["exact_link_precision"])

    def test_settlement_competing_bank_claims_are_review(self):
        p = [{"payout_id": "p", "payout_ref": "PAY-1", "amount_minor": "100", "settle_currency": "USD", "expected_arrival_date": "2025-01-01"}]
        b = {"currency": "USD", "amount_minor": "100", "direction": "credit", "value_date": "2025-01-01", "reference": "PAY-1"}
        self.assertFalse(settlement.match(p, [{**b, "stmt_line_id": "b1"}, {**b, "stmt_line_id": "b2"}])["predictions"])

    def test_settlement_negative_payout_preserves_sign_and_direction(self):
        p = [{"payout_id": "p", "payout_ref": "PAY-1", "amount_minor": "-100", "settle_currency": "USD", "expected_arrival_date": "2025-01-01"}]
        b = {"stmt_line_id": "b", "currency": "USD", "amount_minor": "-100", "direction": "debit", "value_date": "2025-01-01", "reference": "PAY-1"}
        self.assertEqual(settlement.match(p, [b])["predictions"], {"b": "p"})
        with self.assertRaisesRegex(ValueError, "sign"):
            settlement.match(p, [{**b, "direction": "credit"}])

    def test_raw_hash_tamper_fails_before_normalization(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            data = b"original"
            (folder / "raw.csv").write_bytes(data)
            write_json(folder / "source_manifest.json", {"source_id": "test", "source": {}, "files": [
                {"file": "raw.csv", "status": 200, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}]})
            verified_source(folder, ["raw.csv"])
            (folder / "raw.csv").write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "hash"):
                verified_source(folder, ["raw.csv"])

    def test_journal_extractor_never_reads_expected_output(self):
        doc = {"doc_id": "D1", "doc_type": "customer_invoice", "role": "posting_doc", "date": "2025-01-01",
               "ocr_text": "CUSTOMER INVOICE\nTotal: $100.00\n", "metadata": {"currency_code": "USD"}}
        r = {"record_id": "r", "industry": "professional_services",
             "allowed_accounts": ["Accounts Receivable", "Service Revenue"], "documents": [doc]}
        prediction = journal.predict(r)
        self.assertEqual(prediction, journal.predict({**r, "expected_entries": [{"amount": "garbage"}]}))
        self.assertEqual(prediction["entries"][0]["amount_minor"], 10000)
        balance = journal.replay_simple({"assets": {"Cash": Decimal("100")}, "equity": {"Owner's Equity": Decimal("100")}}, prediction["entries"])
        self.assertTrue(balance["balanced"])
        self.assertEqual(balance["equity"]["Retained Earnings"], 10000)


class OfflineCliTests(unittest.TestCase):
    def test_generate_allocate_never_needs_truth_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, out = Path(tmp) / "input", Path(tmp) / "output"
            self.assertEqual(main(["generate", "--seed", "7", "--blocks", "1", "--output", str(raw)]), 0)
            (raw / "truth.jsonl").unlink()
            self.assertEqual(main(["allocate", "--input", str(raw), "--output", str(out)]), 0)
            with patch("sys.stderr"):
                self.assertEqual(main(["allocate", "--input", str(raw), "--output", str(out)]), 2)

    def test_static_pool_rejects_fictitious_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / "manifest.json", {"schema": "t0-invoice-payment-v2", "availability": "static_retrospective"})
            (root / "invoices.jsonl").write_text("", encoding="utf-8")
            (root / "payments.jsonl").write_text("", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_allocation_input(root, "2025-01-01")

    def test_plan_overlap_rejected_before_output_and_small_benchmark(self):
        plan = json.loads(offline.PLAN.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            bad = {**plan, "seeds": {"validation": [1], "test": [1]}}
            with self.assertRaises(ValueError):
                offline.benchmark(out, bad)
            self.assertFalse(out.exists())
            plan.update(blocks=1, seeds={"validation": [1], "test": [2]})
            report = offline.benchmark(out, plan)
            self.assertTrue(all(s["all_invariants_pass"] and s["all_order_stable"] for s in report["summary"]))


if __name__ == "__main__":
    unittest.main()
