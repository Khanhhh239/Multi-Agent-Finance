import copy
import hashlib
import json
from pathlib import Path
import unittest

from finance_input import AccessScope, check_core, schema
from finance_input.validation import StrictValidator
from sme_fraud.imports import parse_vnd, records_as_of, validate_input

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures/input_contract_v1.json"


class InputContractTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(FIXTURE.read_text("utf-8"))
        self.scope = AccessScope("demo", frozenset({"C001", "C002"}), "test-importer", frozenset({"data.import"}))

    def report(self):
        return validate_input(self.data, self.scope)

    def codes(self):
        return {e["code"] for e in self.report()["errors"]}

    def test_schema_is_valid(self):
        StrictValidator.check_schema(schema())

    def test_fixture_retains_every_row_and_negative_amount(self):
        before = copy.deepcopy(self.data)
        report = self.report()
        self.assertEqual(report["status"], "accepted_with_warnings")
        self.assertEqual(report["counts"]["transactions"], 6)
        self.assertEqual(self.data, before)
        self.assertEqual(self.data["transactions"][2]["amount_vnd"], -2000000)

    def test_same_ids_in_two_companies_are_separate(self):
        visible = records_as_of(self.data, self.scope, "2026-10-10T11:00:00+07:00")
        self.assertEqual(len(visible["transactions"]), 6)
        self.assertEqual({r["company_id"] for r in visible["transactions"] if r["record_id"] == "T001"}, {"C001", "C002"})

    def test_identical_id_same_company_revision_rejected(self):
        self.data["transactions"].append(copy.deepcopy(self.data["transactions"][0]))
        self.assertIn("DUPLICATE_REVISION", self.codes())

    def test_late_document_not_visible_in_old_knowledge(self):
        doc = self.data["supporting_documents"][0]
        doc["observed_at"] = "2026-10-12T10:00:00+07:00"
        old = records_as_of(self.data, self.scope, "2026-10-11T10:00:00+07:00")
        new = records_as_of(self.data, self.scope, "2026-10-13T10:00:00+07:00")
        self.assertFalse(any(r["company_id"] == "C001" for r in old["supporting_documents"]))
        self.assertTrue(any(r["company_id"] == "C001" for r in new["supporting_documents"]))

    def test_late_revision_cannot_replace_past_value(self):
        revision = copy.deepcopy(self.data["transactions"][0])
        revision.update(revision=2, amount_vnd=7000000, observed_at="2026-10-12T10:00:00+07:00")
        self.data["transactions"].append(revision)
        for cutoff, amount in [("2026-10-11T10:00:00+07:00", 12000000), ("2026-10-13T10:00:00+07:00", 7000000)]:
            visible = records_as_of(self.data, self.scope, cutoff)
            selected = next(r for r in visible["transactions"] if r["company_id"] == "C001" and r["record_id"] == "T001")
            self.assertEqual(selected["amount_vnd"], amount)

    def test_as_of_is_order_independent_and_copied(self):
        first = records_as_of(self.data, self.scope, "2026-10-11T10:00:00+07:00")
        for rows in self.data.values():
            if isinstance(rows, list): rows.reverse()
        self.assertEqual(first, records_as_of(self.data, self.scope, "2026-10-11T03:00:00Z"))
        first["transactions"][0]["amount_vnd"] = 1
        self.assertNotEqual(first, records_as_of(self.data, self.scope, "2026-10-11T03:00:00Z"))

    def test_future_effective_record_not_visible_yet(self):
        self.data["supporting_documents"][0]["effective_at"] = "2026-10-12T10:00:00+07:00"
        visible = records_as_of(self.data, self.scope, "2026-10-11T10:00:00+07:00")
        self.assertFalse(any(r["company_id"] == "C001" for r in visible["supporting_documents"]))

    def test_revision_time_cannot_move_back(self):
        revision = copy.deepcopy(self.data["vendors"][0])
        revision.update(revision=2, observed_at="2026-10-09T10:00:00+07:00")
        self.data["vendors"].append(revision)
        self.assertIn("REVISION_TIME", self.codes())

    def test_timestamps_missing_naive_ambiguous_invalid_rejected(self):
        for stamp in [None, "2026-10-10", "10/11/2026", "2026-10-10T10:00:00", "2026-13-10T10:00:00+07:00", "2026-10-10T10:00:00-00:00", "2026-10-10T10:00:00+07:99"]:
            with self.subTest(stamp=stamp):
                self.data["transactions"][0]["observed_at"] = stamp
                self.assertIn("SCHEMA", self.codes())

    def test_money_exact_and_signed_without_rounding(self):
        for source, expected in [("-12000000", -12000000), ("100.00", 100), (999999999999999999, 999999999999999999)]:
            self.assertEqual(parse_vnd(source), expected)
        for source in [1.0, True, "1.1", "12,000", "1e3", "NaN", "Infinity", 1000000000000000000]:
            with self.subTest(source=source), self.assertRaises(ValueError): parse_vnd(source)

    def test_canonical_money_rejects_float_string_bool_fraction_and_overflow(self):
        for value in [1.0, True, "12000000", 1.5, 1000000000000000000]:
            with self.subTest(value=value):
                self.data["transactions"][0]["amount_vnd"] = value
                self.assertIn("SCHEMA", self.codes())

    def test_negative_requires_adjustment_kind_reason_original(self):
        original = copy.deepcopy(self.data["transactions"][2])
        for field in ["kind", "adjustment_reason", "adjusts_ref"]:
            with self.subTest(field=field):
                changed = copy.deepcopy(original)
                if field == "kind": changed["kind"] = "payment"
                else: changed.pop(field)
                self.data["transactions"][2] = changed
                self.assertIn("ADJUSTMENT_CONTEXT", self.codes())

    def test_negative_invoice_and_allocation_adjustments_are_accepted(self):
        for table, original_id in [("invoices", "I001"), ("payment_allocations", "A001")]:
            adjustment = copy.deepcopy(self.data[table][0])
            adjustment.update(record_id="NEG001",amount_vnd=-1000,kind="adjustment",adjustment_reason="Sửa sai",adjusts_ref=dict(record_id=original_id,revision=1))
            self.data[table].append(adjustment)
        self.assertNotEqual(self.report()["status"], "rejected")

    def test_overpayment_and_distinct_payments_same_invoice_not_import_errors(self):
        # C001: two 12M allocations against a 20M invoice. Both remain analyzable.
        report = self.report()
        self.assertFalse(report["errors"])
        self.assertEqual(report["counts"]["payment_allocations"], 4)

    def test_many_to_many_allocation_is_supported(self):
        invoice = copy.deepcopy(self.data["invoices"][0]); invoice["record_id"] = "I002"
        self.data["invoices"].append(invoice)
        allocation = copy.deepcopy(self.data["payment_allocations"][0]); allocation.update(record_id="A003",invoice_ref=dict(record_id="I002",revision=1))
        self.data["payment_allocations"].append(allocation)
        self.assertFalse(self.report()["errors"])

    def test_other_company_does_not_satisfy_missing_reference(self):
        self.data["vendors"] = [r for r in self.data["vendors"] if r["company_id"] != "C001"]
        self.assertIn("REFERENCE_MISSING", self.codes())

    def test_self_adjustment_rejected(self):
        self.data["transactions"][2]["adjusts_ref"]["record_id"] = "ADJ001"
        self.assertIn("SELF_REFERENCE", self.codes())

    def test_cyclic_adjustments_rejected(self):
        first = self.data["transactions"][2]
        second = copy.deepcopy(first)
        second.update(record_id="ADJ002",adjusts_ref=dict(record_id="ADJ001",revision=1))
        first["adjusts_ref"] = dict(record_id="ADJ002",revision=1)
        self.data["transactions"].append(second)
        self.assertIn("ADJUSTMENT_CYCLE", self.codes())

    def test_foreign_currency_requires_separate_contract(self):
        self.data["transactions"][0]["currency"] = "USD"
        self.assertIn("SCHEMA", self.codes())

    def test_missing_known_time_never_defaults_to_event_time(self):
        self.data["transactions"][0].pop("observed_at")
        self.assertIn("REQUIRED_FIELD", self.codes())
        self.assertNotIn("observed_at", self.data["transactions"][0])

    def test_company_master_required(self):
        self.data["companies"] = self.data["companies"][:1]
        self.assertIn("COMPANY_MISSING", self.codes())

    def test_partial_auxiliary_sources_warn_without_dropping_rows(self):
        self.data["supporting_documents"] = []
        report = self.report()
        self.assertEqual(report["status"], "accepted_with_warnings")
        self.assertFalse(report["capabilities"]["C001"]["bank_change_input"]["available"])
        self.assertTrue(report["capabilities"]["C001"]["transaction_input"]["available"])
        self.assertEqual(report["counts"]["transactions"], 6)

    def test_scope_denial_does_not_expose_foreign_rows(self):
        for scope in [None, AccessScope("foreign",frozenset({"C001"}),"test",frozenset({"data.import"})),
                      AccessScope("demo",frozenset({"C001"}),"test",frozenset({"data.import"})),
                      AccessScope("demo",frozenset({"C001","C002"}),"test",frozenset())]:
            with self.subTest(scope=scope):
                report = validate_input(self.data,scope)
                self.assertEqual(report["errors"][0]["code"],"ACCESS_DENIED")
                self.assertFalse(report["counts"])
                self.assertFalse(report["capabilities"])

    def test_malformed_company_id_does_not_crash(self):
        self.data["transactions"][0]["company_id"] = ["C001"]
        self.assertIn("SCHEMA", self.codes())

    def test_leading_zero_identifiers_preserved(self):
        self.assertEqual(self.data["employees"][0]["bank_account"], "00123456")
        self.assertFalse(self.report()["errors"])

    def test_unknown_columns_and_label_truth_not_accepted(self):
        for field in ["fraud_label", "paid_date_true", "unknown_column"]:
            with self.subTest(field=field):
                changed = copy.deepcopy(self.data)
                changed["transactions"][0][field] = 1
                self.assertEqual(validate_input(changed,self.scope)["status"], "rejected")

    def test_missing_vs_unknown_explicit_without_inventing_value(self):
        self.data["vendors"][0]["missing_fields"] = dict(tax_id="not_provided_by_source",address="unknown")
        self.assertFalse(self.report()["errors"])
        self.data["vendors"][0]["tax_id"] = "0123456789"
        self.assertIn("MISSING_CONFLICT", self.codes())

    def test_source_and_original_document_not_automatically_verified(self):
        doc = self.data["supporting_documents"][0]
        doc.update(source_kind="original"); doc["source"]["is_simulated"] = False
        self.assertFalse(self.report()["errors"])
        self.assertEqual(doc["verification_status"], "unverified")
        doc["verification_status"] = "verified"
        self.assertIn("VERIFICATION_MISSING", self.codes())
        self.assertIn("VERIFICATION_PERMISSION", self.codes())

    def test_verification_cannot_use_future_knowledge(self):
        self.scope = AccessScope("demo",frozenset({"C001","C002"}),"verifier",frozenset({"data.import","evidence.verify"}))
        doc = self.data["supporting_documents"][0]
        doc.update(verification_status="verified",verification=dict(verified_by="verifier",verified_at="2026-10-12T10:00:00+07:00",basis="Đối chiếu fixture mô phỏng"))
        self.assertIn("VERIFICATION_TIME", self.codes())
        doc["observed_at"] = "2026-10-12T10:00:00+07:00"
        self.assertFalse(self.report()["errors"])
        self.assertEqual(doc["source_kind"], "simulated")  # verification never turns simulation into an original

    def test_pinned_money_reuse_exact_bytes(self):
        upstream = json.loads((ROOT/"shared/finance_input/UPSTREAM.json").read_text("utf-8"))
        copied = upstream["copied"][0]
        actual = hashlib.sha256((ROOT/"shared/finance_input"/copied["target"]).read_bytes()).hexdigest()
        self.assertEqual(actual, copied["sha256"])

    def test_errors_have_row_field_and_next_action(self):
        self.data["transactions"][0]["amount_vnd"] = 1.1
        err = self.report()["errors"][0]
        self.assertEqual(err["row"], 1)
        self.assertEqual(err["field"], "amount_vnd")
        self.assertTrue(err["action"])


if __name__ == "__main__": unittest.main()
