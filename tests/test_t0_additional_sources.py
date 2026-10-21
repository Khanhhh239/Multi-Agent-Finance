"""Source feasibility checks must not turn documentation into business evidence."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from scripts.archive.t0.research_t0_additional_sources import (
    ERP_FIELDS, check_source, inspect_documents, text_content)


class AdditionalSourceResearchTests(unittest.TestCase):
    def test_erp_schema_coverage_is_explicit_and_missing_field_fails_coverage(self):
        docs = {name + ".json": json.dumps({"fields": [{"fieldname": key} for key in keys]}).encode()
                for name, keys in ERP_FIELDS.items()}
        result = inspect_documents("erpnext", docs)
        self.assertTrue(result["all_proposed_fields_present"])
        del_field = json.loads(docs["bank_transaction_payments.json"])
        del_field["fields"] = [f for f in del_field["fields"] if f["fieldname"] != "allocated_amount"]
        docs["bank_transaction_payments.json"] = json.dumps(del_field).encode()
        result = inspect_documents("erpnext", docs)
        self.assertFalse(result["all_proposed_fields_present"])
        self.assertEqual(result["schemas"]["bank_transaction_payments"]["required_missing"], ["allocated_amount"])

    def test_docile_document_labels_and_synthetic_subset_do_not_imply_matching_truth(self):
        result = inspect_documents("docile", {
            "readme.md": b"First obtain a secret token",
            "dataset_page.html": b"<p>Access request; annotated and synthetic subsets</p>"})
        self.assertTrue(result["readme_requires_token"])
        self.assertTrue(result["page_separates_synthetic"])
        self.assertIn("no bank allocation", result["interpretation"])

    def test_synthetic_provenance_overrides_real_world_marketing(self):
        result = inspect_documents("bankstatemently", {"readme.md": b"Real-world challenges, synthetic statements"})
        self.assertTrue(result["declares_synthetic"])
        with self.assertRaises(ValueError):
            inspect_documents("bankstatemently", {"readme.md": b"Unverified provenance"})

    def test_html_checks_ignore_scripts_and_styles(self):
        self.assertEqual(text_content(b"<script>open api</script><style>foo</style><p>Visible</p>"), "Visible")
        result = inspect_documents("misa", {"portal.html": b"<script>open api sandbox</script>",
                                              "invoice_receipts.html": b"<p>Unknown</p>"})
        self.assertFalse(result["portal_mentions_open_api"])
        self.assertFalse(result["portal_mentions_sandbox"])

    def test_ukraine_response_shape_does_not_copy_records_to_report(self):
        result = inspect_documents("ukraine-spending", {
            "acts.json": b'[{"id":1,"supplier":"SYNTH-SECRET"}]',
            "transactions.json": b'[]'})
        self.assertEqual(result["responses"]["acts.json"]["rows"], 1)
        self.assertNotIn("SYNTH-SECRET", json.dumps(result))

    def test_failed_access_preserved_cached_and_never_accepted_for_matching(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("https://example.test", 403, "Forbidden", {}, None)):
                report = check_source(Path(tmp), "bankstatemently")
            self.assertEqual(report["status"], "access_incomplete")
            self.assertFalse(report["matching_accepted"])
            self.assertEqual(report["business_dataset_audits"], 0)
            self.assertEqual(report["matcher_runs"], 0)
            with patch("urllib.request.urlopen") as network:
                check_source(Path(tmp), "bankstatemently")
                network.assert_not_called()
            self.assertFalse((Path(tmp) / "bankstatemently/bank.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
