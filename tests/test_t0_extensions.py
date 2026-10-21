"""Cross-date, observed FX, revision, refund and explicit-journal contracts."""

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_EVEN
import json
from pathlib import Path
import tempfile
import unittest

from t0 import constrained, fx, journal, offline
from t0.__main__ import main
from t0.data import write_json, write_jsonl
from t0.ledger import EventStore, replay


def inv(identifier="I1", amount=40, **extra):
    return {"tenant_id": "A", "id": identifier, "invoice_number": "INV-" + identifier,
            "side": "AR", "party_id": "C", "currency": "USD", "amount_minor": amount,
            "issued_on": "2025-01-01", "available_on": "2025-01-01", **extra}


def pay(identifier="P1", amount=70, **extra):
    return {"tenant_id": "A", "id": identifier, "side": "AR", "party_id": "C", "currency": "USD",
            "amount_minor": amount, "reference": "INV-I1 INV-I2", "payment_on": "2025-01-02",
            "available_on": "2025-01-02", **extra}


def quote(source="USD", target="VND", n=250, d=1, **extra):
    return {"source_currency": source, "target_currency": target, "rate_num": n, "rate_den": d,
            "rounding": "half_even", "quoted_on": "2025-01-01", "available_on": "2025-01-01",
            "source_ref": "fixture-independent-quote", **extra}


def rec(kind, identifier, amount, day="2025-01-01", **extra):
    return offline.record(kind, identifier, amount, day=day, **extra)


def dec(action, day="2025-01-03", **extra):
    return offline.decision(action, day=day, **extra)


def policy():
    return {"policy_id": "development-explicit-v1", "functional_currency": "USD",
            "effective_on": "2025-01-01", "available_on": "2025-01-01",
            "accounts": {"receivable": "Accounts Receivable", "payable": "Accounts Payable", "cash": "Cash",
                         "revenue": "Service Revenue", "expense": "Travel Expense", "input_tax": "Tax Receivable",
                         "output_tax": "Tax Payable", "fx_gain": "FX Gain", "fx_loss": "FX Loss"}}


def doc(identifier="D1", kind="customer_invoice", **facts):
    return {"doc_id": identifier, "doc_type": kind, "role": "posting_doc", "date": "2025-01-02",
            "available_on": "2025-01-02", "ocr_text": "Observed structured export", "metadata": {"currency_code": facts.get("currency", "USD")},
            "accounting_facts": {"schema": "t0-journal-facts-v1", "party_id": "C", "currency": "USD",
                                 "subtotal_minor": 10000, "discount_minor": 1000, "tax_minor": 900,
                                 "total_minor": 9900, "revenue_recognition": "immediate", **facts}}


def packet(documents, **extra):
    return {"record_id": "R1", "industry": "professional_services", "allowed_accounts": [],
            "cutoff": "2025-01-31", "accounting_policy": policy(), "documents": documents, **extra}


class CrossDateTests(unittest.TestCase):
    def test_joint_cross_date_unique_flow_and_order(self):
        invoices = [inv(), inv("I2", 60)]
        payments = [pay(), pay("P2", 30, payment_on="2025-01-03", reference="INV-I2")]
        expected = {("P1", "I1", 40), ("P1", "I2", 30), ("P2", "I2", 30)}
        result = constrained.allocate(invoices, payments)
        self.assertEqual({(a["payment_id"], a["invoice_id"], a["amount_minor"]) for a in result["allocations"]}, expected)
        self.assertEqual(result, constrained.allocate(invoices[::-1], payments[::-1]))
        self.assertFalse(result["invariant_errors"])

    def test_partial_snapshot_cannot_use_later_constraint(self):
        invoices = [inv(), inv("I2", 60)]
        self.assertFalse(constrained.allocate(invoices, [pay()])["allocations"])
        payments = [pay(), pay("P2", 30, payment_on="2025-01-03", reference="INV-I1 INV-I2")]
        self.assertFalse(constrained.allocate(invoices, payments)["allocations"])

    def test_each_payment_still_cannot_use_future_invoice(self):
        result = constrained.allocate([inv(issued_on="2025-01-03")], [pay(amount=40, reference="INV-I1")])
        self.assertFalse(result["allocations"])


class FXTests(unittest.TestCase):
    def test_rational_conversion_matches_independent_decimal_rounding(self):
        for amount in range(1, 35):
            for n, d in ((1, 2), (3, 2), (11, 7), (250, 1)):
                wanted = int((Decimal(amount) * n / d).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
                if wanted == 0:
                    with self.assertRaises(ValueError):
                        fx.convert(amount, quote(n=n, d=d), "USD", "VND", "2025-01-02", "2025-01-03")
                else:
                    self.assertEqual(fx.convert(amount, quote(n=n, d=d), "USD", "VND", "2025-01-02", "2025-01-03"), wanted)

    def test_future_pair_rounding_and_numeric_guards(self):
        for fields in ({"rate_num": True}, {"rate_den": 0}, {"rate_num": 1.2}, {"rounding": "floor"},
                       {"source_ref": ""}, {"available_on": "2025-02-01"}, {"target_currency": "EUR"},
                       {"quoted_on": "2025-01-04"}):
            with self.assertRaises(ValueError):
                fx.convert(100, quote(**fields), "USD", "VND", "2025-01-03", "2025-01-03")

    def test_observed_fx_proposal_and_ledger_consumption_in_both_currencies(self):
        invoices = [inv(amount=100, tenant_id="DEMO")]
        payments = [pay(amount=25000, currency="VND", tenant_id="DEMO", reference="INV-I1", fx_remittance=[
            {"invoice_number": "INV-I1", "invoice_amount_minor": 100, "payment_amount_minor": 25000, "fx": quote()}])]
        result = fx.allocate(invoices, payments, "2025-01-03")
        self.assertEqual(len(result["allocations"]), 1)
        events = [rec("invoice", "I1", 100, currency="USD", side="AR", party_id="C", invoice_number="INV-I1"),
                  rec("payment", "P1", 25000, currency="VND", side="AR", party_id="C"),
                  dec("suggest", allocations=result["allocations"]), dec("approve"), dec("commit", external_result="verified")]
        result = replay(events, "2025-01-03")
        self.assertEqual(result["invoices"][0]["outstanding_minor"], 0)
        self.assertEqual(result["payments"][0]["unallocated_minor"], 0)
        with self.assertRaises(ValueError):
            replay(events + [dec("suggest", decision_id="D2", allocations=[{
                "invoice_id": "I1", "payment_id": "P1", "amount_minor": 1, "payment_amount_minor": 250,
                "fx": quote()}]), dec("approve", decision_id="D2"), dec("commit", decision_id="D2", external_result="verified")], "2025-01-03")
        reversed_gold = replay(events + [dec("reverse")], "2025-01-03")
        self.assertEqual(reversed_gold["payments"][0]["unallocated_minor"], 25000)

    def test_competing_fx_proposals_abstain_and_no_quote_is_inferred(self):
        p = pay(amount=25000, currency="VND", fx_remittance=[
            {"invoice_number": "INV-I1", "invoice_amount_minor": 100, "payment_amount_minor": 25000, "fx": quote()}])
        self.assertFalse(fx.allocate([inv(amount=100)], [p, {**p, "id": "P2"}], "2025-01-03")["allocations"])
        self.assertFalse(fx.allocate([inv(amount=100)], [pay(currency="VND")], "2025-01-03")["allocations"])

    def test_fx_remittance_cannot_override_conflicting_known_reference(self):
        p = pay(amount=25000, currency="VND", reference="INV-I2", fx_remittance=[
            {"invoice_number": "INV-I1", "invoice_amount_minor": 100, "payment_amount_minor": 25000, "fx": quote()}])
        self.assertFalse(fx.allocate([inv(amount=100), inv("I2", 200)], [p], "2025-01-03")["allocations"])


class VersionAndRefundTests(unittest.TestCase):
    def setup_events(self, side="AR"):
        return [rec("invoice", "I1", 100, side=side, party_id="C", invoice_number="INV1"),
                rec("payment", "P1", 150, side=side, party_id="C")]

    def revision(self, original, amount=120):
        e = deepcopy(original)
        e.update(action="revise", available_on="2025-02-01", expected_version=1)
        e["data"]["amount_minor"] = amount
        return e

    def test_late_revision_immutable_history_optimistic_lock_and_retry(self):
        events = self.setup_events()
        revision = self.revision(events[0])
        before = replay(events, "2025-01-31")
        self.assertEqual(before, replay(events + [revision], "2025-01-31"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store.sqlite"
            with EventStore(path) as store:
                for n, e in enumerate(events):
                    store.submit(str(n), e)
                store.submit("revision", revision)
                self.assertTrue(store.submit("revision", revision)["replayed"])
                gold = store.gold("2025-02-01")
                self.assertEqual(gold["invoices"][0]["outstanding_minor"], 120)
                self.assertEqual([v["version"] for v in gold["document_versions"] if v["kind"] == "invoice"], [1, 2])
                with self.assertRaisesRegex(ValueError, "stale"):
                    store.submit("revision-again", revision)
                self.assertEqual(gold, store.gold("2025-02-01"))
            with EventStore(path) as store:
                self.assertEqual(store.events()[0], events[0])
                self.assertEqual(store.gold("2025-02-01"), gold)

    def test_stale_approval_requires_cancel_and_new_suggestion(self):
        events = self.setup_events() + [dec("suggest", allocations=[{"invoice_id": "I1", "payment_id": "P1", "amount_minor": 100}])]
        revision = self.revision(events[0])
        with self.assertRaisesRegex(ValueError, "stale decision"):
            replay(events + [revision, dec("approve", day="2025-02-01")], "2025-02-01")
        gold = replay(events + [revision, dec("cancel", day="2025-02-01")], "2025-02-01")
        self.assertEqual(gold["decisions"][0]["status"], "cancelled")

    def test_revisions_cannot_erase_posted_money_scope_or_unknown_outcome(self):
        events = self.setup_events() + [dec("suggest", allocations=[{"invoice_id": "I1", "payment_id": "P1", "amount_minor": 100}]),
                                       dec("approve"), dec("commit", external_result="verified")]
        with self.assertRaises(ValueError):
            replay(events + [self.revision(events[0], 90)], "2025-02-01")
        changed = self.revision(events[0]); changed["data"]["currency"] = "USD"
        with self.assertRaisesRegex(ValueError, "scope"):
            replay(events + [changed], "2025-02-01")
        unknown = deepcopy(events); unknown[-1]["external_result"] = "unknown"
        with self.assertRaisesRegex(ValueError, "unknown"):
            replay(unknown + [self.revision(events[0])], "2025-02-01")

    def test_refund_bank_split_and_shared_bank_budget_ar_ap(self):
        for side, direction in (("AR", "debit"), ("AP", "credit")):
            events = self.setup_events(side) + [rec("refund", "R1", 50, payment_id="P1"),
                rec("bank", "B1", 31 if side == "AR" else 29, direction=direction),
                rec("bank", "B2", 20, direction=direction),
                rec("refund_bank_link", "RL1", 0, refund_id="R1", bank_id="B1", refund_amount_minor=30,
                    bank_amount_minor=31 if side == "AR" else 29, fee_minor=1),
                rec("refund_bank_link", "RL2", 0, refund_id="R1", bank_id="B2", refund_amount_minor=20, fee_minor=0)]
            gold = replay(events, "2025-01-31")
            self.assertEqual(gold["refunds"][0]["bank_unlinked_minor"], 0)
            self.assertTrue(all(b["unlinked_minor"] == 0 for b in gold["bank_unlinked"]))
            with self.assertRaises(ValueError):
                replay(events + [rec("refund_bank_link", "RL3", 0, refund_id="R1", bank_id="B2", refund_amount_minor=1,
                                     bank_amount_minor=1, fee_minor=0)], "2025-01-31")

    def test_fx_bank_and_refund_gain_loss_are_separate_from_cash(self):
        events = [rec("payment", "P1", 100, currency="USD", side="AR", party_id="C"),
                  rec("bank", "B1", 24995, currency="VND", direction="credit"),
                  rec("bank_link", "L1", 0, currency="USD", payment_id="P1", bank_id="B1", fee_minor=5,
                      fx=quote(), carrying_bank_minor=24000)]
        gold = replay(events, "2025-01-31")
        self.assertEqual(gold["bank_links"][0]["realized_fx_minor"], 1000)
        self.assertEqual(gold["bank_movements"][0]["net_minor"], 24995)
        self.assertEqual(gold["payments"][0]["unallocated_minor"], 100)
        events += [rec("refund", "R1", 20, currency="USD", payment_id="P1"),
                   rec("bank", "BR", 5002, currency="VND", direction="debit"),
                   rec("refund_bank_link", "LR", 0, currency="USD", refund_id="R1", bank_id="BR", fee_minor=2,
                       fx=quote(), carrying_bank_minor=4900)]
        gold = replay(events, "2025-01-31")
        self.assertEqual(gold["refund_bank_links"][0]["realized_fx_minor"], -100)
        self.assertEqual(gold["payments"][0]["unallocated_minor"], 80)

    def test_payment_revision_cannot_shrink_below_bank_link(self):
        events = self.setup_events() + [rec("bank", "B", 150, direction="credit"),
            rec("bank_link", "L", 0, payment_id="P1", bank_id="B", fee_minor=0)]
        with self.assertRaisesRegex(ValueError, "bank-linked"):
            replay(events + [self.revision(events[1], 140)], "2025-02-01")

    def test_bank_amount_cannot_be_reused_across_payment_and_refund_links(self):
        events = [rec("payment", "AP", 100, side="AP", party_id="V"),
                  rec("payment", "AR", 100, side="AR", party_id="C"),
                  rec("refund", "R", 100, payment_id="AR"),
                  rec("bank", "B", 100, direction="debit"),
                  rec("bank_link", "L", 0, payment_id="AP", bank_id="B", fee_minor=0)]
        with self.assertRaisesRegex(ValueError, "remaining"):
            replay(events + [rec("refund_bank_link", "RL", 0, refund_id="R", bank_id="B", fee_minor=0)], "2025-01-31")

    def test_ap_fx_bank_loss_and_same_currency_bool_are_rejected_or_signed(self):
        events = [rec("payment", "P1", 100, currency="USD", side="AP", party_id="C"),
                  rec("bank", "B", 25005, direction="debit"),
                  rec("bank_link", "L", 0, currency="USD", payment_id="P1", bank_id="B", fee_minor=5,
                      fx=quote(), carrying_bank_minor=24000)]
        self.assertEqual(replay(events, "2025-01-31")["bank_links"][0]["realized_fx_minor"], -1000)
        same_currency = self.setup_events() + [dec("suggest", allocations=[{
            "invoice_id": "I1", "payment_id": "P1", "amount_minor": 1, "payment_amount_minor": True}])]
        with self.assertRaises(ValueError):
            replay(same_currency, "2025-01-31")


class JournalPolicyTests(unittest.TestCase):
    def test_tax_discount_sale_and_purchase_are_balanced_multiline(self):
        sale = journal.predict(packet([doc()]))
        lines = sale["postings"][0]["lines"]
        self.assertEqual([(r["account"], r["debit_minor"], r["credit_minor"]) for r in lines],
                         [("Accounts Receivable", 9900, 0), ("Service Revenue", 0, 9000), ("Tax Payable", 0, 900)])
        self.assertFalse(sale["inconsistency"]["inconsistent"])
        purchase = doc(kind="vendor_invoice", tax_treatment="recoverable", expense_account="Travel Expense")
        result = journal.predict(packet([purchase]))
        self.assertEqual(result["postings"][0]["lines"][1]["account"], "Tax Receivable")
        purchase["accounting_facts"]["tax_treatment"] = "expensed"
        lines = journal.predict(packet([purchase]))["postings"][0]["lines"]
        self.assertEqual(lines[0]["debit_minor"], 9900)
        self.assertEqual(sum(r["debit_minor"] - r["credit_minor"] for r in lines), 0)

    def test_credit_note_refund_and_payment_dependencies(self):
        invoice = doc()
        credit = doc("CN1", "customer_credit_note", subtotal_minor=1000, discount_minor=0, tax_minor=0,
                     total_minor=1000, reference_doc_id="D1")
        refund = doc("R1", "customer_refund", amount_minor=1000, carrying_functional_minor=1000, reference_doc_id="CN1")
        result = journal.predict(packet([refund, invoice, credit]))
        self.assertEqual(len(result["postings"]), 3)
        refund_lines = next(p["lines"] for p in result["postings"] if p["doc_id"] == "R1")
        self.assertEqual(refund_lines[0]["credit_minor"], 1000)
        broken = deepcopy(refund); broken["accounting_facts"]["party_id"] = "OTHER"
        self.assertTrue(journal.predict(packet([invoice, credit, broken]))["inconsistency"]["inconsistent"])

    def test_fx_settlement_books_balanced_explicit_gain(self):
        invoice = doc(currency="EUR", subtotal_minor=10000, discount_minor=0, tax_minor=0, total_minor=10000,
                      fx=quote("EUR", "USD", 108, 100))
        payment = doc("P1", "customer_payment", currency="EUR", amount_minor=10000, carrying_functional_minor=10800,
                      reference_doc_id="D1", fx=quote("EUR", "USD", 11, 10))
        result = journal.predict(packet([invoice, payment]))
        self.assertEqual(result["postings"][1]["lines"][-1], {"account": "FX Gain", "debit_minor": 0, "credit_minor": 200})
        self.assertTrue(all(sum(r["debit_minor"] - r["credit_minor"] for r in p["lines"]) == 0 for p in result["postings"]))

    def test_detector_blocks_bad_arithmetic_and_dependent_payment(self):
        invoice = doc(total_minor=9999)
        payment = doc("P1", "customer_payment", amount_minor=100, carrying_functional_minor=100, reference_doc_id="D1")
        result = journal.predict(packet([invoice, payment]))
        self.assertTrue(result["inconsistency"]["inconsistent"])
        self.assertFalse(result["entries"])

    def test_cumulative_payment_overflow_abstains_whole_competing_group(self):
        documents = [doc()] + [doc(p, "customer_payment", amount_minor=6000, carrying_functional_minor=6000,
                                   reference_doc_id="D1") for p in ("P1", "P2")]
        result = journal.predict(packet(documents))
        self.assertEqual(len(result["postings"]), 1)
        self.assertTrue(result["inconsistency"]["inconsistent"])
        self.assertEqual(result["entries"], journal.predict(packet(documents[::-1]))["entries"])

    def test_duplicate_and_conflicting_documents_cannot_double_post(self):
        d = doc()
        self.assertEqual(len(journal.predict(packet([d, deepcopy(d)]))["postings"]), 1)
        changed = deepcopy(d); changed["accounting_facts"]["total_minor"] = 10
        result = journal.predict(packet([d, changed]))
        self.assertFalse(result["entries"])
        self.assertTrue(result["inconsistency"]["inconsistent"])

    def test_cutoff_policy_and_labels_cannot_supply_future_features(self):
        original = packet([doc()])
        predicted = journal.predict(original)
        poisoned = deepcopy(original)
        poisoned.update(expected_entries=[{"amount": "secret"}], expected_inconsistency=True)
        poisoned["documents"][0]["metadata"]["expected_inconsistency"] = True
        self.assertEqual(predicted, journal.predict(poisoned))
        future = deepcopy(original["documents"][0]); future["doc_id"] = "FUTURE"; future["available_on"] = "2025-02-01"
        self.assertEqual(predicted["entries"], journal.predict(packet([doc(), future]))["entries"])
        missing_policy = packet([doc()]); missing_policy.pop("accounting_policy")
        self.assertFalse(journal.predict(missing_policy)["entries"])
        self.assertIsNone(journal.predict(missing_policy)["inconsistency"]["inconsistent"])

    def test_unsupported_recognition_rounding_and_account_policy_abstain(self):
        for fields in ({"revenue_recognition": "deferred"}, {"tax_minor": True},
                       {"currency": "EUR", "fx": quote("EUR", "USD", 1, 7)}):
            self.assertFalse(journal.predict(packet([doc(**fields)]))["entries"])
        d = doc(kind="vendor_invoice", expense_account="Invented Expense", tax_treatment="recoverable")
        self.assertFalse(journal.predict(packet([d]))["entries"])

    def test_bank_running_balance_not_only_final_equation(self):
        d = doc(kind="bank_statement"); d.pop("accounting_facts")
        d["ocr_text"] = "Opening Balance: $100.00\nClosing Balance: $100.00\n - Date 2025-01-01 | Amount $-10.00 | Running Balance $91.00\n - Date 2025-01-02 | Amount $10.00 | Running Balance $100.00\n"
        result = journal.detect_inconsistency([d])
        self.assertIn("bank_running_balance_mismatch", [f["code"] for f in result["findings"]])

    def test_trial_balance_replays_tax_and_reports_incomplete_predictions(self):
        p = packet([doc()])
        p["accounting_policy"]["accounts"]["equity"] = "Owner's Equity"
        p["opening_balances"] = {"currency": "USD", "as_of": "2025-01-01", "available_on": "2025-01-01",
                                  "balances": {"Cash": 10000, "Owner's Equity": -10000}}
        trial = journal.predict(p)["trial_balance"]
        self.assertTrue(trial["balanced"])
        self.assertTrue(trial["prediction_complete"])
        self.assertEqual(trial["balances"]["Tax Payable"], -900)
        p["documents"].append(doc("BAD", total_minor=10))
        self.assertFalse(journal.predict(p)["trial_balance"]["prediction_complete"])
        p["opening_balances"]["available_on"] = "2025-02-01"
        self.assertEqual(journal.predict(p)["trial_balance"]["status"], "unsupported")

    def test_unknown_policy_is_not_classified_as_inconsistent(self):
        result = journal.predict(packet([doc(revenue_recognition="deferred")]))
        self.assertIsNone(result["inconsistency"]["inconsistent"])
        self.assertFalse(result["entries"])
        payment = doc("PAY", "customer_payment", amount_minor=100, carrying_functional_minor=100, reference_doc_id="MISSING")
        self.assertIsNone(journal.predict(packet([payment]))["inconsistency"]["inconsistent"])

    def test_settlement_carrying_cannot_be_fabricated(self):
        payment = doc("P1", "customer_payment", amount_minor=1000, carrying_functional_minor=999999, reference_doc_id="D1")
        result = journal.predict(packet([doc(), payment]))
        self.assertTrue(result["inconsistency"]["inconsistent"])
        self.assertEqual(len(result["postings"]), 1)

    def text_document(self, kind, content):
        d = doc(kind=kind); d.pop("accounting_facts"); d["ocr_text"] = content
        return d

    def test_declared_loan_activity_creates_separate_principal_interest_entries(self):
        d = self.text_document("loan_statement", "Opening Principal: $100.00\nDraw Amount: $50.00\nPrincipal Paid: $20.00\nInterest Paid: $3.00\nEnding Principal: $130.00\n")
        r = packet([d], allowed_accounts=["Cash", "Loans Payable", "Interest Expense"])
        entries = journal.predict(r)["entries"]
        self.assertEqual([(e["debit_account"], e["credit_account"], e["amount_minor"]) for e in entries],
                         [("Cash", "Loans Payable", 5000), ("Loans Payable", "Cash", 2000), ("Interest Expense", "Cash", 300)])
        d["ocr_text"] = d["ocr_text"].replace("$130.00", "$120.00")
        self.assertFalse(journal.predict(r)["entries"])
        self.assertTrue(journal.predict(r)["inconsistency"]["inconsistent"])

    def test_declared_payroll_preserves_gross_and_employer_tax(self):
        d = self.text_document("payroll_summary", "Gross Pay: $100.00\nEmployer Tax: 10.00\nCash Outflow: $110.00\n")
        r = packet([d], allowed_accounts=["Cash", "Salaries Expense", "Payroll Tax Expense"])
        entries = journal.predict(r)["entries"]
        self.assertEqual([e["amount_minor"] for e in entries], [10000, 1000])
        d["ocr_text"] = d["ocr_text"].replace("$110.00", "$109.00")
        self.assertFalse(journal.predict(r)["entries"])
        self.assertTrue(journal.predict(r)["inconsistency"]["inconsistent"])

    def test_supplier_expense_category_requires_allowed_exact_account(self):
        d = self.text_document("supplier_invoice", "Expense Category: Repairs Expense\nTotal: $100.00\n")
        r = packet([d], allowed_accounts=["Repairs Expense", "Accounts Payable"])
        self.assertEqual(journal.predict(r)["entries"][0]["debit_account"], "Repairs Expense")
        r["allowed_accounts"] = ["Other Expense"]
        self.assertFalse(journal.predict(r)["entries"])

    def test_credit_notes_cannot_overreverse_tax_or_change_purchase_policy(self):
        invoice = doc()
        credits = [doc(n, "customer_credit_note", subtotal_minor=400, discount_minor=0, tax_minor=500,
                       total_minor=900, reference_doc_id="D1") for n in ("C1", "C2")]
        result = journal.predict(packet([invoice, *credits]))
        self.assertTrue(result["inconsistency"]["inconsistent"])
        self.assertEqual(len(result["postings"]), 1)
        purchase = doc(kind="vendor_invoice", tax_treatment="recoverable", expense_account="Travel Expense")
        credit = doc("C1", "vendor_credit_note", subtotal_minor=100, discount_minor=0, tax_minor=0,
                     total_minor=100, reference_doc_id="D1", tax_treatment="expensed", expense_account="Travel Expense")
        self.assertTrue(journal.predict(packet([purchase, credit]))["inconsistency"]["inconsistent"])


class ExtensionCliTests(unittest.TestCase):
    def test_fx_and_journal_cli_are_prediction_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "source"; source.mkdir()
            write_json(source / "manifest.json", {"schema": "t0-invoice-payment-v2", "availability": "simulated", "cutoff": "2025-01-31"})
            write_jsonl(source / "invoices.jsonl", [inv(amount=100)])
            write_jsonl(source / "payments.jsonl", [pay(amount=25000, currency="VND", fx_remittance=[{
                "invoice_number": "INV-I1", "invoice_amount_minor": 100, "payment_amount_minor": 25000, "fx": quote()}])])
            self.assertEqual(main(["allocate-fx", "--input", str(source), "--cutoff", "2025-01-31", "--output", str(folder / "fx")]), 0)
            write_jsonl(folder / "journal.jsonl", [packet([doc()])])
            self.assertEqual(main(["journal-predict", "--input", str(folder / "journal.jsonl"), "--output", str(folder / "journal")]), 0)
            self.assertEqual(len(json.loads((folder / "journal/predictions.json").read_text(encoding="utf-8"))[0]["postings"]), 1)


if __name__ == "__main__":
    unittest.main()
