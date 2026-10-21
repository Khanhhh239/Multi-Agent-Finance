"""Regression and independent exhaustive checks for the T0 review fixes."""

from copy import deepcopy
from itertools import product
import json
from pathlib import Path
import tempfile
import unittest

from t0 import constrained, gates, journal, offline, robustness, settlement
from t0.__main__ import load_allocation_input, main
from t0.data import write_json, write_jsonl
from t0.ledger import EventStore, replay


def invoice(identifier="I1", amount=100, **fields):
    return {"tenant_id": "A", "id": identifier, "invoice_number": "INV-" + identifier,
            "side": "AR", "party_id": "C", "currency": "VND", "amount_minor": amount,
            "issued_on": "2025-01-01", "available_on": "2025-01-01", **fields}


def payment(identifier="P1", amount=100, **fields):
    return {"tenant_id": "A", "id": identifier, "side": "AR", "party_id": "C", "currency": "VND",
            "amount_minor": amount, "payment_on": "2025-01-31", "available_on": "2025-01-31",
            "reference": "INV-I1", **fields}


class SnapshotHardeningTests(unittest.TestCase):
    def test_invalid_availability_and_business_dates_rejected_before_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_json(folder / "manifest.json", {"schema": "t0-invoice-payment-v2", "availability": "simulated", "cutoff": "2025-02-01"})
            for kind, field in (("invoice", "available_on"), ("payment", "available_on"),
                                ("invoice", "issued_on"), ("payment", "payment_on")):
                for invalid in ("", "2025-01-00", "2025-1-1", "2025-99-99", None):
                    with self.subTest(kind=kind, field=field, invalid=invalid):
                        i, p = invoice(), payment()
                        (i if kind == "invoice" else p)[field] = invalid
                        write_jsonl(folder / "invoices.jsonl", [i])
                        write_jsonl(folder / "payments.jsonl", [p])
                        with self.assertRaises(ValueError):
                            load_allocation_input(folder)

    def test_valid_late_arrival_and_future_business_date_stay_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_json(folder / "manifest.json", {"schema": "t0-invoice-payment-v2", "availability": "simulated", "cutoff": "2025-02-01"})
            write_jsonl(folder / "invoices.jsonl", [invoice(), invoice("I2", available_on="2025-03-01"),
                                                       invoice("I3", issued_on="2025-03-01")])
            write_jsonl(folder / "payments.jsonl", [payment()])
            self.assertEqual([i["id"] for i in load_allocation_input(folder)[0]], ["I1"])


class TransportTests(unittest.TestCase):
    def test_solver_against_independent_exhaustive_integer_oracle(self):
        edges_all = [(0, 0), (0, 1), (1, 0), (1, 1)]
        for supplies in product(range(3), repeat=2):
            for caps in product(range(3), repeat=2):
                for mask in product((False, True), repeat=4):
                    edges = [e for e, selected in zip(edges_all, mask) if selected]
                    target, solutions = min(sum(supplies), sum(caps)), []
                    for amounts in product(range(3), repeat=len(edges)):
                        if sum(amounts) != target:
                            continue
                        if (any(sum(a for (p, _), a in zip(edges, amounts) if p == k) > supplies[k] for k in range(2))
                                or any(sum(a for (_, i), a in zip(edges, amounts) if i == k) > caps[k] for k in range(2))):
                            continue
                        solutions.append({e: a for e, a in zip(edges, amounts) if a})
                    expected = "infeasible" if not solutions else "unique" if len(solutions) == 1 else "nonunique"
                    status, flow = constrained.unique_transport(supplies, caps, edges)
                    self.assertEqual(status, expected, (supplies, caps, edges))
                    if status == "unique":
                        self.assertEqual(flow, solutions[0])

    def test_reference_constrained_many_to_many_has_unique_amounts(self):
        inv = [invoice("I1", 40), invoice("I2", 60)]
        ps = [payment("P1", 70, reference="INV-I1 + INV-I2"), payment("P2", 30, reference="INV-I2")]
        result = constrained.allocate(inv, ps)
        self.assertEqual({(a["payment_id"], a["invoice_id"]): a["amount_minor"] for a in result["allocations"]},
                         {("P1", "I1"): 40, ("P1", "I2"): 30, ("P2", "I2"): 30})
        self.assertEqual(result["allocation_hash"], constrained.allocate(inv[::-1], ps[::-1])["allocation_hash"])

    def test_nonunique_partial_group_and_competing_overpayments_abstain(self):
        for inv, ps in (([invoice("I1", 40), invoice("I2", 60)], [payment(amount=70, reference="INV-I1 INV-I2")]),
                        ([invoice()], [payment("P1"), payment("P2")])):
            result = constrained.allocate(inv, ps)
            self.assertFalse(result["allocations"])
            self.assertTrue(all(d["reason"] == "flow_nonunique" for d in result["decisions"]))

    def test_wrong_valid_reference_is_review_even_for_unknown_party(self):
        for party in ("C", ""):
            result = constrained.allocate([invoice(), invoice("I2")], [payment(reference="INV-I2", party_id=party)])
            self.assertFalse(result["allocations"])
            self.assertEqual(result["decisions"][0]["status"], "review")

    def test_observed_breakdown_resolves_partial_group_and_preserves_surplus(self):
        inv = [invoice("I1", 40), invoice("I2", 60)]
        p = payment(amount=80, reference="INV-I1 INV-I2", remittance=[
            {"invoice_number": "INV-I1", "amount_minor": 25}, {"invoice_number": "INV-I2", "amount_minor": 30}])
        before = deepcopy([inv, p])
        result = constrained.allocate(inv, [p])
        self.assertEqual([a["amount_minor"] for a in result["allocations"]], [25, 30])
        self.assertEqual(result["decisions"][0]["unallocated_minor"], 25)
        self.assertEqual([inv, p], before)

    def test_breakdown_conflict_overflow_and_duplicate_never_commit(self):
        for breakdown in ([{"invoice_number": "UNKNOWN", "amount_minor": 20}],
                          [{"invoice_number": "INV-I1", "amount_minor": 120}],
                          [{"invoice_number": "INV-I1", "amount_minor": 20}] * 2):
            r = constrained.allocate([invoice()], [payment(remittance=breakdown)])
            self.assertFalse(r["allocations"])
            self.assertEqual(r["decisions"][0]["status"], "review")
        with self.assertRaises(ValueError):
            constrained.allocate([invoice()], [payment(remittance=[{"invoice_number": "INV-I1", "amount_minor": True}])])

    def test_scope_date_and_component_budget(self):
        for field, value in (("side", "AP"), ("currency", "USD"), ("party_id", "OTHER"),
                             ("payment_on", "2024-12-31"), ("tenant_id", "B")):
            self.assertFalse(constrained.allocate([invoice()], [payment(**{field: value})])["allocations"])
        inv = [invoice(str(n), amount=n + 1) for n in range(13)]
        p = payment(amount=91, reference=" ".join(i["invoice_number"] for i in inv))
        self.assertEqual(constrained.allocate(inv, [p])["decisions"][0]["reason"], "flow_component_overflow")


class LedgerHardeningTests(unittest.TestCase):
    def test_adjustment_and_link_cannot_predate_endpoint_atomic(self):
        for kind, endpoint, field in (("credit_note", "invoice", "invoice_id"), ("refund", "payment", "payment_id")):
            with tempfile.TemporaryDirectory() as tmp, EventStore(Path(tmp) / "store.sqlite") as store:
                base = offline.record(endpoint, "E1", 100, day="2025-01-20", side="AR", party_id="C",
                                      **({"invoice_number": "INV-1"} if endpoint == "invoice" else {}))
                store.submit("base", base)
                adj = offline.record(kind, "ADJ1", 10, day="2025-01-21", **{field: "E1"})
                adj["effective_on"] = "2025-01-01"
                with self.assertRaisesRegex(ValueError, "predates"):
                    store.submit("bad", adj)
                self.assertEqual(len(store.events()), 1)
        events = [offline.record("payment", "P1", 100, day="2025-01-20", side="AR", party_id="C"),
                  offline.record("bank", "B1", 100, day="2025-01-20", direction="credit")]
        link = offline.record("bank_link", "L1", 0, day="2025-01-21", payment_id="P1", bank_id="B1", fee_minor=0)
        link["effective_on"] = "2025-01-01"
        with self.assertRaisesRegex(ValueError, "predates"):
            replay(events + [link], "2025-02-01")

    def test_split_bank_and_payment_links_conserve_both_sides(self):
        for side, direction, b1, b2 in (("AR", "credit", 35, 55), ("AP", "debit", 45, 65)):
            events = [offline.record("payment", "P1", 100, side=side, party_id="C"),
                      offline.record("bank", "B1", b1, direction=direction),
                      offline.record("bank", "B2", b2, direction=direction),
                      offline.record("bank_link", "L1", 0, payment_id="P1", bank_id="B1", fee_minor=5,
                                     payment_amount_minor=40, bank_amount_minor=b1),
                      offline.record("bank_link", "L2", 0, payment_id="P1", bank_id="B2", fee_minor=5,
                                     payment_amount_minor=60, bank_amount_minor=b2)]
            self.assertEqual(len(replay(events, "2025-02-01")["bank_links"]), 2)
            extra = deepcopy(events[-1]); extra["data"]["id"] = "L3"
            with self.assertRaisesRegex(ValueError, "remaining"):
                replay(events + [extra], "2025-02-01")
        events = [offline.record("payment", "P1", 40, side="AR", party_id="C"),
                  offline.record("payment", "P2", 60, side="AR", party_id="C"),
                  offline.record("bank", "B", 100, direction="credit"),
                  offline.record("bank_link", "L1", 0, payment_id="P1", bank_id="B", fee_minor=0,
                                 payment_amount_minor=40, bank_amount_minor=40),
                  offline.record("bank_link", "L2", 0, payment_id="P2", bank_id="B", fee_minor=0,
                                 payment_amount_minor=60, bank_amount_minor=60)]
        self.assertEqual(len(replay(events, "2025-02-01")["bank_links"]), 2)


class StatementTests(unittest.TestCase):
    def statement(self, identifier="S1", start="2025-01-01", end="2025-01-31", **fields):
        return offline.record("bank_statement", identifier, 0, day=end, account_id="ACC",
                              start_on=start, end_on=end, opening_minor=fields.pop("opening_minor", 100),
                              closing_minor=fields.pop("closing_minor", 140), credits_minor=fields.pop("credits_minor", 50),
                              debits_minor=fields.pop("debits_minor", 10), transactions_complete=fields.pop("transactions_complete", True), **fields)

    def bank_rows(self):
        return [offline.record("bank", "B1", 50, day="2025-01-10", direction="credit", account_id="ACC"),
                offline.record("bank", "B2", 10, day="2025-01-20", direction="debit", account_id="ACC")]

    def test_statement_totals_continuity_scope_and_completeness(self):
        events = self.bank_rows() + [self.statement()]
        row = replay(events, "2025-01-31")["bank_reconciliation"][0]
        self.assertEqual(row["status"], "matched_declared_complete")
        self.assertEqual(row["closing_difference_minor"], 0)
        unknown = deepcopy(events); unknown[-1]["data"]["transactions_complete"] = False
        self.assertEqual(replay(unknown, "2025-01-31")["bank_reconciliation"][0]["status"], "unknown_completeness")
        bad = deepcopy(events); bad[0]["data"]["account_id"] = "OTHER"
        self.assertEqual(replay(bad, "2025-01-31")["bank_reconciliation"][0]["status"], "mismatch")
        next_statement = self.statement("S2", "2025-02-01", "2025-02-28", opening_minor=150,
                                        closing_minor=150, credits_minor=0, debits_minor=0)
        row = replay(events + [next_statement], "2025-02-28")["bank_reconciliation"][1]
        self.assertFalse(row["continuity_pass"])
        self.assertEqual(row["status"], "mismatch")

    def test_late_bank_row_cannot_change_older_statement_snapshot(self):
        events = self.bank_rows() + [self.statement(credits_minor=60, closing_minor=150)]
        old = replay(events, "2025-01-31")
        late = offline.record("bank", "LATE", 10, day="2025-02-02", direction="credit", account_id="ACC")
        late["effective_on"] = "2025-01-15"
        self.assertEqual(old, replay(events + [late], "2025-01-31"))
        self.assertEqual(replay(events + [late], "2025-02-02")["bank_reconciliation"][0]["status"], "matched_declared_complete")

    def test_overlap_invalid_scale_and_future_period_are_rejected(self):
        for field, value in (("opening_minor", 1.5), ("credits_minor", -1), ("transactions_complete", "true"),
                             ("end_on", "2025-02-01")):
            s = self.statement(); s["data"][field] = value
            with self.assertRaises(ValueError):
                replay([s], "2025-03-01")
        with self.assertRaisesRegex(ValueError, "overlapping"):
            replay([self.statement(), self.statement("S2")], "2025-02-01")


class InconsistencyTests(unittest.TestCase):
    def document(self, total="100.00", **fields):
        return {"doc_id": "D1", "doc_type": "customer_invoice", "role": "posting_doc", "date": "2025-01-01",
                "metadata": {"currency_code": "USD"},
                "ocr_text": f"Invoice Number: INV-1\nTotal: ${total}\n  - Description Service | Amount $100.00\n", **fields}

    def test_arithmetic_identity_and_unknown_policies(self):
        self.assertFalse(journal.detect_inconsistency([self.document()])["inconsistent"])
        self.assertTrue(journal.detect_inconsistency([self.document("110.00")])["inconsistent"])
        self.assertTrue(journal.detect_inconsistency([self.document(), self.document("110.00")])["inconsistent"])
        self.assertIsNone(journal.detect_inconsistency([self.document(doc_type="lease_agreement")])["inconsistent"])
        self.assertIsNone(journal.detect_inconsistency([self.document(role="context_only")])["inconsistent"])

    def test_declared_tax_and_bank_arithmetic_do_not_infer_tax_policy(self):
        doc = self.document(ocr_text="Invoice Number: INV-1\nSubtotal: $100.00\nTax Amount: $10.00\nTotal: $111.00\n  - Description Service | Amount $100.00\n")
        self.assertEqual(journal.detect_inconsistency([doc])["findings"][0]["code"], "subtotal_tax_total_mismatch")
        bank = self.document(doc_type="bank_statement", role="support_doc",
                             ocr_text="Opening Balance: $100.00\nClosing Balance: $120.00\n - Date 2025-01-01 | Amount $-10.00 | Running Balance $90.00\n")
        self.assertTrue(journal.detect_inconsistency([bank])["inconsistent"])

    def test_expected_fields_and_validation_metadata_cannot_change_detector(self):
        r = {"record_id": "R1", "industry": "professional_services", "allowed_accounts": [], "documents": [self.document()]}
        prediction = journal.predict(r)
        r.update(expected_inconsistency=True, expected_inconsistency_codes=["SECRET"],
                 metadata={"validation": "SECRET", "underlying_expected_entry_count": 999})
        r["documents"][0]["metadata"]["expected_inconsistency"] = True
        self.assertEqual(prediction, journal.predict(r))

    def test_abstained_positive_stays_in_recall_denominator(self):
        records = [{"record_id": str(n), "expected_inconsistency": expected} for n, expected in enumerate((True, False, True, False))]
        predictions = [{"record_id": str(n), "inconsistency": {"inconsistent": observed}} for n, observed in enumerate((True, True, None, False))]
        measured = journal.inconsistency_metrics(records, predictions)
        self.assertEqual(measured["precision"], 0.5)
        self.assertEqual(measured["recall_full_pool"], 0.5)
        self.assertEqual(measured["decision_coverage"], 0.75)


class GateTests(unittest.TestCase):
    def test_missing_cache_is_incomplete_in_a_real_local_runner(self):
        plan = json.loads(offline.PLAN.read_text(encoding="utf-8"))
        plan.update(blocks=1, seeds={"validation": [13], "test": [14]})
        with tempfile.TemporaryDirectory() as tmp:
            r = offline.run_all(Path(tmp) / "output", Path(tmp) / "missing", plan)
            self.assertEqual(len(r["assessment"]["unavailable_tasks"]), 4)
            self.assertEqual(gates.exit_code(r["assessment"]), 3)
            self.assertIsNone(r["finrca"]["quality"])
            self.assertFalse(r["assessment"]["production_ready"])

    def test_missing_tasks_technical_failure_and_quality_have_distinct_exits(self):
        a = {"execution_complete": False, "technical_pass": True, "quality_complete": False}
        self.assertEqual(gates.exit_code(a), 3)
        a.update(execution_complete=True, technical_pass=False)
        self.assertEqual(gates.exit_code(a), 1)
        a.update(technical_pass=True)
        self.assertEqual(gates.exit_code(a), 0)
        self.assertEqual(gates.exit_code(a, "quality"), 4)

    def test_null_quality_and_nan_policy_never_pass(self):
        results = {"ar": {"summary": []}, "finrca": {}, "recbench": {}, "finbalance": {}, "fiscus": {}}
        a = gates.assess(results, {"check": True})
        self.assertFalse(a["quality_complete"])
        self.assertFalse(a["production_ready"])
        with self.assertRaises(ValueError):
            gates.assess(results, {}, {**gates.DEFAULT_POLICY, "ar_min_precision": float("nan")})


class RobustnessTests(unittest.TestCase):
    def test_noise_preserves_truth_and_split_worlds(self):
        plan = json.loads(robustness.PLAN.read_text(encoding="utf-8"))
        first = robustness.generate(17, 1, "clean", plan["noise"])
        for profile in plan["profiles"]:
            self.assertEqual(first[2], robustness.generate(17, 1, profile, plan["noise"])[2])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bad"
            with self.assertRaises(ValueError):
                robustness.benchmark(out, {**plan, "seeds": {"validation": [1], "test": [1]}})
            self.assertFalse(out.exists())

    def test_small_benchmark_and_cli_need_no_labels_for_prediction(self):
        plan = json.loads(robustness.PLAN.read_text(encoding="utf-8"))
        plan.update(blocks=1, seeds={"validation": [1], "test": [2]})
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            report = robustness.benchmark(folder / "bench", plan)
            self.assertTrue(report["all_pass"])
            self.assertEqual(len(report["runs"]), 16)
            source = folder / "source"
            source.mkdir()
            write_json(source / "manifest.json", {"schema": "t0-invoice-payment-v2", "availability": "simulated", "cutoff": "2025-02-01"})
            write_jsonl(source / "invoices.jsonl", [invoice()])
            write_jsonl(source / "payments.jsonl", [payment()])
            self.assertEqual(main(["allocate", "--input", str(source), "--output", str(folder / "pred")]), 0)
            result = json.loads((folder / "pred/predictions.json").read_text(encoding="utf-8"))
            self.assertEqual(result["method"], "constrained_flow")


class SettlementHardeningTests(unittest.TestCase):
    def test_integer_parser_never_truncates_or_accepts_bool(self):
        for value in (1.5, True, "1.0", "NaN", 0):
            with self.assertRaises(ValueError):
                settlement.signed_minor(value)
        self.assertEqual(settlement.signed_minor("-120"), -120)
        with self.assertRaisesRegex(ValueError, "labels"):
            settlement.score([], [{"stmt_line_id": "B", "currency": "USD"}], [],
                             [{"stmt_line_id": "B", "is_matchable": "unknown"}], {})


if __name__ == "__main__":
    unittest.main()
