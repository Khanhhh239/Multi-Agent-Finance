"""Regression cases found by the Python/JSON maintenance review."""

from copy import deepcopy
from decimal import localcontext
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts.data_audit import audit_t1_source_samples as samples
from scripts.data_download import download_czech_t1_datasets as download
from scripts.checks import check_code
from t0 import adapters, benchrec, journal, journal_policy, offline
from t0.data import canonical, read_jsonl, write_json, write_jsonl
from t0.ledger import replay
from t0.matching import maximum_weight_assignment


def structured(identifier, kind="customer_invoice", **facts):
    return {"doc_id": identifier, "doc_type": kind, "role": "posting_doc",
            "date": "2025-01-02", "available_on": "2025-01-02", "ocr_text": "Observed",
            "accounting_facts": {"schema": "t0-journal-facts-v1", "party_id": "C", "currency": "USD",
                                 "subtotal_minor": 100, "tax_minor": 0, "total_minor": 100,
                                 "revenue_recognition": "immediate", **facts}}


def packet(documents):
    return {"record_id": "R", "industry": "professional_services", "allowed_accounts": [],
            "cutoff": "2025-01-31", "documents": documents,
            "accounting_policy": {"policy_id": "P", "functional_currency": "USD",
                                  "effective_on": "2025-01-01", "available_on": "2025-01-01",
                                  "accounts": {"receivable": "AR", "cash": "Cash", "revenue": "Revenue"}}}


class InputContracts(unittest.TestCase):
    def test_jsonl_rejects_duplicate_keys_and_nonfinite_values_with_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.jsonl"
            for line in ('{"amount":1,"amount":2}', '{"value":NaN}', '{"value":Infinity}', '{"value":1e999}', '{bad}'):
                with self.subTest(line=line):
                    path.write_text('\n' + line + '\n', encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, r"input.jsonl:2:"):
                        read_jsonl(path)

    def test_json_writers_reject_nonfinite_without_truncating_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kept.json"
            path.write_bytes(b"original")
            for writer in (write_json, write_jsonl):
                with self.assertRaises(ValueError):
                    writer(path, [{"value": float("nan")}])
                self.assertEqual(path.read_bytes(), b"original")
            with self.assertRaises(ValueError):
                canonical({"value": float("inf")})

    def test_csv_adapters_reject_lossy_headers_and_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.csv"
            for content in ('id,id\n1,2\n', 'id,value\n1\n', 'id,value\n1,2,3\n', ',value\n1,2\n', 'id,value\nid,value\n'):
                for reader in (adapters.csv_rows, benchrec.csv_rows):
                    with self.subTest(content=content, reader=reader.__module__):
                        path.write_text(content, encoding="utf-8")
                        with self.assertRaises(ValueError):
                            list(reader(path))

    def test_decimal_minor_conversion_is_independent_of_decimal_context(self):
        amount = "123456789012345678901234567890.12"
        expected = 12345678901234567890123456789012
        with localcontext() as context:
            context.prec = 6
            self.assertEqual(adapters.minor(amount, "USD"), expected)
            with self.assertRaises(ValueError):
                adapters.minor(amount + "3", "USD")

    def test_source_manifest_cannot_silently_override_duplicate_file_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = b"observed"
            (root / "raw.csv").write_bytes(payload)
            entry = {"file": "raw.csv", "status": 200, "bytes": len(payload),
                     "sha256": hashlib.sha256(payload).hexdigest()}
            write_json(root / "source_manifest.json", {"source_id": "test", "source": {}, "files": [entry, entry]})
            with self.assertRaisesRegex(ValueError, "duplicate"):
                adapters.verified_source(root, ["raw.csv"])

    def test_assignment_rejects_nonfinite_and_non_numeric_weights(self):
        # NaN cannot improve an assignment; reject before entering the solver.
        with self.assertRaises(ValueError):
            maximum_weight_assignment([[float("nan")]])
        for value in (float("inf"), float("-inf"), True, "1"):
            with self.assertRaises(ValueError):
                maximum_weight_assignment([[value]])


class JournalContracts(unittest.TestCase):
    def test_duplicate_source_delivery_does_not_disable_settlement(self):
        invoice = structured("I")
        payment = structured("P", "customer_payment", reference_doc_id="I", amount_minor=100,
                             carrying_functional_minor=100)
        original = journal.predict(packet([invoice, payment]))
        replayed = journal.predict(packet([invoice, deepcopy(invoice), payment]))
        self.assertEqual(replayed["entries"], original["entries"])
        self.assertEqual(replayed["inconsistency"]["inconsistent"], False)

    def test_conflicting_invoice_totals_block_both_candidates(self):
        base = {"doc_id": "A", "doc_type": "customer_invoice", "role": "posting_doc", "date": "2025-01-02",
                "metadata": {"currency_code": "USD", "issuer_name": "X", "counterparty_name": "Y"},
                "ocr_text": "Invoice Number: INV-1\nTotal: $1.00\n- Item | Amount $1.00\n"}
        other = {**deepcopy(base), "doc_id": "B", "ocr_text": base["ocr_text"].replace("1.00", "2.00")}
        result = journal.predict({"record_id": "R", "industry": "professional_services",
                                  "allowed_accounts": ["Accounts Receivable", "Service Revenue"], "documents": [base, other]})
        self.assertTrue(result["inconsistency"]["inconsistent"])
        self.assertEqual(result["entries"], [])
        self.assertEqual(result["entries"], journal.predict({"record_id": "R", "industry": "professional_services",
                         "allowed_accounts": ["Accounts Receivable", "Service Revenue"], "documents": [other, base]})["entries"])

    def test_text_posting_requires_distinct_allowed_accounts(self):
        base = {"doc_id": "I", "doc_type": "customer_invoice", "role": "posting_doc", "date": "2025-01-02",
                "metadata": {"currency_code": "USD"}, "ocr_text": "Total: $1.00\n"}
        self.assertIsNone(journal.document_entry(base, "professional_services", ["Cash"])[0])
        base.update(doc_type="supplier_invoice", ocr_text="Total: $1.00\nExpense Category: Accounts Payable\n")
        self.assertIsNone(journal.document_entry(base, "professional_services", ["Accounts Payable"])[0])

    def test_pairing_cannot_silently_discard_unbalanced_or_invalid_lines(self):
        posting = {"doc_id": "I", "posting_date": "2025-01-02", "lines": [
            {"account": "AR", "debit_minor": 100, "credit_minor": 0},
            {"account": "Revenue", "debit_minor": 0, "credit_minor": 90}]}
        with self.assertRaises(ValueError):
            journal_policy.pair_entries(posting)
        posting["lines"][1]["credit_minor"] = True
        with self.assertRaises(ValueError):
            journal_policy.pair_entries(posting)


class LedgerContracts(unittest.TestCase):
    def test_allocation_metadata_must_agree_with_endpoints(self):
        events = [offline.record("invoice", "I", 100, side="AR", party_id="C", invoice_number="I"),
                  offline.record("payment", "P", 100, side="AR", party_id="C")]
        for field, value in (("currency", "USD"), ("payment_currency", "USD"), ("side", "AP"), ("tenant_id", "OTHER")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replay(events + [offline.decision("suggest", allocations=[{
                    "invoice_id": "I", "payment_id": "P", "amount_minor": 100, field: value}])], "2025-01-31")

    def test_invoice_due_date_cannot_precede_issue(self):
        with self.assertRaises(ValueError):
            replay([offline.record("invoice", "I", 100, side="AR", party_id="C", invoice_number="I",
                                   due_on="2024-12-31")], "2025-01-31")


class SourceContracts(unittest.TestCase):
    def test_resume_cache_checks_hash_even_when_size_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cached.json"
            path.write_bytes(b"original")
            meta = {"bytes": 8, "sha256": hashlib.sha256(b"original").hexdigest()}
            self.assertTrue(download.verified_cache(path, meta))
            path.write_bytes(b"modified")
            with self.assertRaises(ValueError):
                download.verified_cache(path, meta)

    def test_sample_numbers_and_dates_tolerate_invalid_input(self):
        for value in ("NaN", "Infinity", "-Infinity", "sNaN"):
            self.assertIsNone(samples.number(value))
        for value in (True, float("inf"), float("nan"), 10**100):
            self.assertIsNone(samples.date(value))

    def test_health_profile_preserves_missing_buyer_without_crashing(self):
        row = {"id_invoice": 1, "import_id": 2, "odberatel": None, "dodavatel": None,
               "datum_vystaveni": "2025-01-01", "datum_prijeti": "2025-01-01",
               "datum_splatnosti": "2025-01-02", "datum_uhrady": "2025-01-02",
               "castka_s_dph": "100", "castka_uhrazena": "NaN", "identifikator_dodavatele": "I"}
        profile = samples.health_profile([row])
        self.assertEqual(profile["distinct_buyer_ids"], 0)
        self.assertEqual(profile["complete_rows_by_buyer_code"], {"None": 1})
        self.assertEqual(profile["paid_amount_below_gross_same_currency"], 0)

    def test_download_never_replaces_existing_raw_with_changed_response(self):
        class Response(io.BytesIO):
            headers = {}
            url = "https://fixture.invalid/source"
            status = 200
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "raw.csv"
            path.write_bytes(b"original")
            with patch.object(download.urllib.request, "urlopen", side_effect=lambda *a, **k: Response(b"changed")), patch.object(download.time, "sleep"):
                with self.assertRaises(ValueError):
                    download.get("https://fixture.invalid/source", path, 100)
            self.assertEqual(path.read_bytes(), b"original")

    def test_identical_download_replay_preserves_raw_bytes(self):
        class Response(io.BytesIO):
            headers = {}
            url = "https://fixture.invalid/source"
            status = 200
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "raw.csv"
            path.write_bytes(b"original")
            with patch.object(download.urllib.request, "urlopen", return_value=Response(b"original")):
                result = download.get("https://fixture.invalid/source", path, 100)
            self.assertEqual(result["sha256"], hashlib.sha256(b"original").hexdigest())
            self.assertEqual(path.read_bytes(), b"original")


class RepositoryChecks(unittest.TestCase):
    def test_checker_reports_python_json_and_jsonl_errors_without_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "valid.py").write_text("raise RuntimeError('must not execute')", encoding="utf-8")
            (root / "broken.py").write_text("return 1", encoding="utf-8")
            (root / "broken.json").write_text('{"a":1,"a":2}', encoding="utf-8")
            (root / "broken.jsonl").write_text('[]\n', encoding="utf-8")
            errors, counts = check_code.check_repository(root)
            self.assertEqual(len(errors), 3)
            self.assertEqual(counts, {".py": 2, ".json": 1, ".jsonl": 1})
            self.assertTrue(any("broken.py" in error for error in errors))
            self.assertTrue(any("broken.json" in error for error in errors))
            self.assertTrue(any("broken.jsonl" in error for error in errors))

    def test_checker_skips_data_outputs_and_dependencies_but_checks_examples(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder in ("data/T0/raw", "data/T1/interim", "data/T0/processed", "node_modules", ".venv", "research/references/code"):
                directory = root / folder
                directory.mkdir(parents=True)
                (directory / "ignored.json").write_text("invalid", encoding="utf-8")
            examples = root / "data/T0/examples"
            examples.mkdir(parents=True)
            (examples / "checked.json").write_text('{"a":true}', encoding="utf-8")
            self.assertEqual(check_code.check_repository(root), ([], {".json": 1}))


class ReferenceHelperContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from reference_notebooks import survival_utils
        except ImportError as exc:
            raise unittest.SkipTest("Optional numpy/pandas unavailable: " + str(exc)) from exc
        cls.helper = survival_utils

    def frame(self, duration, event):
        helper = self.helper
        return helper.pd.DataFrame({"duration_days": duration, "event": event,
                                   "days_past_due_at_T": [0] * len(duration),
                                   "observed_age_days": [1] * len(duration),
                                   "days_until_due_at_T": [0] * len(duration)})

    def test_person_period_censors_event_outside_requested_horizon(self):
        result = self.helper.expand_person_period(self.frame([15, 14, 7], [1, 1, 0]), max_bins=2)
        self.assertEqual(result["hazard_event"].tolist(), [0, 0, 0, 1, 0])
        self.assertTrue(self.helper.expand_person_period(self.frame([], [])).empty)

    def test_hazard_inference_uses_same_bin_width_as_expansion(self):
        helper = self.helper
        frame = self.frame([10], [1])
        for field in helper.HAZARD_FEATURES:
            if field not in frame:
                frame[field] = 0
        class Model:
            def __init__(self):
                self.ages = []
            def predict_proba(self, features):
                self.ages.append(features[0, helper.HAZARD_FEATURES.index("age_at_bin")])
                return [[0.75, 0.25]]
        model = Model()
        actual = helper.survival_matrix(frame, model, max_bins=2, bin_days=5)
        self.assertEqual(model.ages, [1, 6])
        helper.np.testing.assert_allclose(actual, [[0.75, 0.5625]])

    def test_invalid_hazard_probabilities_cannot_become_survival_features(self):
        helper = self.helper
        frame = self.frame([7], [1])
        for field in helper.HAZARD_FEATURES:
            if field not in frame:
                frame[field] = 0
        for values in ([[0, float("nan")]], [[-0.2, 1.2]], [[0.8, 0.8]], [[0.5]]):
            model = Mock()
            model.predict_proba.return_value = values
            with self.assertRaises(ValueError):
                helper.survival_matrix(frame, model, max_bins=1)

    def test_median_is_first_half_probability_crossing_including_plateau(self):
        helper = self.helper
        values = helper.survival_features(helper.np.array([[0.5, 0.5, 0.25]]))
        self.assertEqual(values["median_remaining_days"].tolist(), [7])


if __name__ == "__main__":
    unittest.main()
