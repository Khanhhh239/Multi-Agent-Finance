"""Historical access, provenance and ERP-schema checks from the T0 source search.

This is feasibility research, not an invoice-bank dataset audit or a benchmark.
Only public read requests are used; downloaded code is never executed.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from t0.data import fingerprint, write_json


UKRAINE = "https://api.spending.gov.ua/api/v2/"
ERP = "https://raw.githubusercontent.com/frappe/erpnext/develop/erpnext/accounts/doctype/"
SOURCES = {
    "ukraine-spending": {
        "kind": "public_funds_candidate", "source_page": "https://spending.gov.ua/",
        "requests": {
            "acts.json": UKRAINE + "disposers/acts?disposerId=42001897",
            "transactions.json": UKRAINE + "api/transactions/?startdate=2025-12-01&enddate=2025-12-01&payers_edrpous=42001897",
        },
        "limits": "Treasury transactions and acts/invoices may be different grains. Query parameter/filter semantics and independent allocation truth not verified.",
    },
    "rmit-xero-study": {
        "kind": "research_code_availability", "source_page": "https://ssrn.com/abstract=5019966",
        "requests": {"repository.json": "https://api.github.com/repos/justinadrmun/stellargraph",
                     "readme.md": "https://raw.githubusercontent.com/justinadrmun/stellargraph/master/README.md"},
        "limits": "Paper describes business data verified by bookkeepers, but a public model-code repository is not a released business dataset.",
    },
    "docile": {
        "kind": "document_extraction_benchmark", "source_page": "https://docile.rossum.ai/",
        "requests": {"readme.md": "https://raw.githubusercontent.com/rossumai/docile/main/README.md",
                     "dataset_page.html": "https://docile.rossum.ai/"},
        "limits": "Invoice/document field extraction labels are not invoice-bank allocations. Annotated and synthetic subsets must be separated. No access form submitted.",
    },
    "bankstatemently": {
        "kind": "synthetic_parser_benchmark", "source_page": "https://github.com/bankstatemently/bank-statement-parsing-benchmark",
        "requests": {"readme.md": "https://raw.githubusercontent.com/bankstatemently/bank-statement-parsing-benchmark/main/README.md"},
        "limits": "Synthetic statements despite real-world formatting claims; excluded as evidence on real business data. No PDFs or evaluation service used.",
    },
    "erpnext": {
        "kind": "erp_export_schema", "source_page": "https://docs.frappe.io/erpnext/bank-reconciliation",
        "requests": {name + ".json": ERP + name + "/" + name + ".json" for name in (
            "sales_invoice", "payment_entry_reference", "bank_transaction", "bank_transaction_payments")},
        "limits": "Official develop-branch schemas describe an export route, not actual company records. Exact bytes/hashes preserved; production version and permissions still need checking.",
    },
    "misa": {
        "kind": "local_erp_export_route", "source_page": "https://developer.misa.vn/?lang=vi",
        "requests": {"portal.html": "https://developer.misa.vn/?lang=vi",
                     "invoice_receipts.html": "https://helpact.misa.vn/kb/lam-the-nao-khi-khong-thay-chuc-nang-thu-tien-theo-hoa-don/"},
        "limits": "Product supports invoice-level receipt workflows, but export/API field coverage and historical bank links not established. No account registered or private records accessed.",
    },
}

ERP_FIELDS = {
    "sales_invoice": {"customer", "currency", "grand_total", "outstanding_amount", "due_date"},
    "payment_entry_reference": {"reference_doctype", "reference_name", "allocated_amount"},
    "bank_transaction": {"bank_account", "date", "deposit", "withdrawal", "currency", "payment_entries"},
    "bank_transaction_payments": {"payment_document", "payment_entry", "allocated_amount", "clearance_date"},
}


def digest(value):
    return hashlib.sha256(value).hexdigest()


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def text_content(payload):
    parser = PageText()
    parser.feed(payload.decode("utf-8-sig"))
    return " ".join(" ".join(parser.parts).split())


def inspect_documents(source_id, documents):
    """Facts from public files only. Never infer released data from code or docs."""
    if source_id == "erpnext":
        inspected = {}
        for name, required in ERP_FIELDS.items():
            schema = json.loads(documents[name + ".json"])
            fields = {row["fieldname"]: row for row in schema["fields"]}
            inspected[name] = {"schema_field_count": len(fields),
                "required_present": sorted(required & fields.keys()), "required_missing": sorted(required - fields.keys())}
        return {"kind": "official_schema_inspection", "schemas": inspected,
                "all_proposed_fields_present": all(not v["required_missing"] for v in inspected.values()),
                "interpretation": "Schema can guide a pilot export; no instance export, business data or mapping accuracy checked"}
    if source_id == "docile":
        readme = documents["readme.md"].decode().lower()
        page = text_content(documents["dataset_page.html"]).lower()
        return {"kind": "access_and_task_inspection", "readme_requires_token": "secret token" in readme,
                "page_mentions_access_request": "access request" in page,
                "page_separates_synthetic": "synthetic" in page,
                "interpretation": "Research access process; document extraction benchmark, no bank allocation labels established"}
    if source_id == "bankstatemently":
        readme = documents["readme.md"].decode().lower()
        if "synthetic" not in readme:
            raise ValueError("Expected synthetic provenance statement missing; re-review source")
        return {"kind": "provenance_inspection", "declares_synthetic": True,
                "interpretation": "Excluded from real-data validation; no synthetic statement counted as a real account"}
    if source_id == "rmit-xero-study":
        metadata = json.loads(documents["repository.json"])
        return {"kind": "code_availability_inspection", "default_branch": metadata["default_branch"],
                "repository_is_public": metadata["private"] is False,
                "interpretation": "Public graph library code exists; no public link to the paper's business corpus verified"}
    if source_id == "misa":
        portal = text_content(documents["portal.html"]).lower()
        help_page = text_content(documents["invoice_receipts.html"]).lower()
        return {"kind": "product_workflow_inspection", "portal_mentions_open_api": "open api" in portal,
                "portal_mentions_sandbox": "sandbox" in portal,
                "help_mentions_invoice_level_receivables": "theo dõi công nợ theo từng hóa đơn" in help_page,
                "interpretation": "Static HTML keyword checks only; absence is inconclusive for JS pages. Actual export columns, API entitlement and independent bank mappings still untested"}
    if source_id == "ukraine-spending":
        result = {}
        for name, payload in documents.items():
            data = json.loads(payload)
            if isinstance(data, list):
                result[name] = {"type": "list", "rows": len(data),
                                "columns": sorted(data[0]) if data and isinstance(data[0], dict) else []}
            elif isinstance(data, dict):
                result[name] = {"type": "object", "envelope_keys": sorted(data)}
            else:
                raise ValueError("Unexpected API JSON type")
        return {"kind": "bounded_response_shape_inspection", "responses": result,
                "interpretation": "Response shape only, not a full dataset audit or verified invoice-transaction linkage"}
    raise ValueError("Unknown source")


def check_source(base, source_id):
    spec = SOURCES[source_id]
    folder = Path(base) / source_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "source_manifest.json"
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("spec_hash") != fingerprint(spec) or manifest.get("source_id") != source_id:
            raise ValueError("Existing research snapshot has a different specification")
        if manifest.get("use_policy") != "inspection_only_excluded_from_matching":
            raise ValueError("Research source is inspection-only")
        names = [item["file"] for item in manifest["files"]]
        if len(names) != len(set(names)) or not set(names) <= spec["requests"].keys():
            raise ValueError("Unexpected research raw file entries")
        for item in manifest["files"]:
            if item["url"] != spec["requests"][item["file"]]:
                raise ValueError("Research raw URL differs from specification")
            payload = (folder / item["file"]).read_bytes()
            if digest(payload) != item["sha256"] or len(payload) != item["bytes"]:
                raise ValueError("Research raw hash/size mismatch")
    else:
        if any(folder.iterdir()):
            raise ValueError("Incomplete research snapshot; use a new --input directory")
        manifest = {"source_id": source_id, "spec_hash": fingerprint(spec), "source": spec,
                    "use_policy": "inspection_only_excluded_from_matching", "files": [], "errors": []}
        # Continue independent requests even if one API/file fails; retain each result.
        for name, url in spec["requests"].items():
            stamp = datetime.now(timezone.utc).isoformat()
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "FinanceProject-T0-Research/1.0"})
                with urllib.request.urlopen(request, timeout=20) as response:
                    payload = response.read(4_000_001)
                    if len(payload) > 4_000_000:
                        raise ValueError("Response exceeds 4 MB research limit")
                    with (folder / name).open("xb") as handle:
                        handle.write(payload)
                    manifest["files"].append({"file": name, "url": url, "final_url": response.url,
                        "status": response.status, "checked_at_utc": stamp,
                        "bytes": len(payload), "sha256": digest(payload)})
            except (OSError, ValueError) as exc:
                manifest["errors"].append({"file": name, "url": url, "checked_at_utc": stamp,
                    "error_type": type(exc).__name__, "http_status": getattr(exc, "code", None), "reason": str(exc)})
        write_json(path, manifest)
    report = {"source_id": source_id, "manifest": manifest, "business_dataset_audits": 0,
              "matching_accepted": False, "matcher_runs": 0, "inspection": None}
    if manifest["errors"]:
        report["status"] = "access_incomplete"
    else:
        try:
            documents = {item["file"]: (folder / item["file"]).read_bytes() for item in manifest["files"]}
            if set(documents) != set(spec["requests"]):
                raise ValueError("Incomplete source documents")
            report["inspection"] = inspect_documents(source_id, documents)
            report["status"] = "schema_inspected" if source_id == "erpnext" else "provenance_or_access_inspected"
        except (KeyError, ValueError, TypeError) as exc:
            report["status"] = "inspection_failed"
            report["inspection_error"] = str(exc)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/T0/raw/additional_research/2026-10-19")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; choose a new --output")
    with ThreadPoolExecutor(max_workers=3) as pool:
        reports = list(pool.map(lambda key: check_source(args.input, key), SOURCES))
    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "script_sha256": digest(Path(__file__).read_bytes()), "sources": reports,
              "business_dataset_audits": 0, "matcher_runs": 0,
              "scope": "Executed access/provenance/schema checks. No business dataset or model benchmark run.",
              "limits": "No credential, account registration, form submission or execution of downloaded code. Cached snapshots, including failures, are reused; choose a new input folder to retry."}
    write_json(args.output, result)
    for report in reports:
        print(f"{report['source_id']}: {report['status']}; business_dataset_audits=0; matcher_runs=0")
    return int(any(r["status"] == "inspection_failed" for r in reports))


if __name__ == "__main__":
    raise SystemExit(main())
