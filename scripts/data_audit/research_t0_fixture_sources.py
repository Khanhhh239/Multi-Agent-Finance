"""Download pinned public fixtures and inspect records without executing upstream code.

This is source research, not a matcher benchmark. Raw snapshots stay outside Git.
Only development/coverage labels are inspected; no external ERP is installed.
"""

import argparse
import ast
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from t0.data import read_json, read_jsonl
DAY = "2026-10-20"
MAX_BYTES = 16_000_000


def github(repo, revision, paths):
    return {p: f"https://raw.githubusercontent.com/{repo}/{revision}/{p}" for p in paths}


def huggingface(repo, revision, paths):
    return {p: f"https://huggingface.co/datasets/{repo}/resolve/{revision}/{p}" for p in paths}


SOURCES = {
    "erpnext": {
        "kind": "software_test_fixtures", "revision": "064e673b84ff119ed995f261a5e47446d8259b19",
        "page": "https://github.com/frappe/erpnext", "license_scope": "GPL-3.0 software; inspect license.txt; not private company data",
        "requests": github("frappe/erpnext", "064e673b84ff119ed995f261a5e47446d8259b19", [
            "license.txt", "erpnext/accounts/doctype/payment_reconciliation/test_payment_reconciliation.py",
            "erpnext/accounts/doctype/bank_transaction/test_bank_transaction.py",
            "erpnext/setup/demo_data/payment_entry.json"]),
    },
    "oca": {
        "kind": "software_test_fixtures", "revision": "2da3bc0d9d2e6e3c34af25326d1d6130b4ac59e3",
        "page": "https://github.com/OCA/account-reconcile/tree/18.0", "license_scope": "Repository license plus module manifest; verify per-module terms before copying",
        "requests": github("OCA/account-reconcile", "2da3bc0d9d2e6e3c34af25326d1d6130b4ac59e3", [
            "LICENSE", "account_mass_reconcile/__manifest__.py", "account_mass_reconcile/tests/test_reconcile.py",
            "account_move_base_import/tests/data/statement.csv"]),
    },
    "recbench": {
        "kind": "synthetic_settlement_benchmark", "revision": "8cf65de21434a480cb3a499e3c39246c9e8b744a",
        "page": "https://huggingface.co/datasets/end-close/recbench", "license_scope": "Dataset card declares CC BY 4.0; code availability not verified",
        "requests": huggingface("end-close/recbench", "8cf65de21434a480cb3a499e3c39246c9e8b744a", [
            "README.md", "small/manifest.json", "small/csv/payouts.csv", "small/csv/bank_statements.csv",
            "small/csv/truth_payout_bank.csv", "small/csv/labels_payout.csv", "small/csv/labels_bank.csv"]),
    },
    "finrca": {
        "kind": "synthetic_accounts_payable_benchmark", "revision": "76c93ec32536e29826e2ab9e68b58e0351410bc7",
        "page": "https://github.com/PratikGhawate/FinRCA-AI-Bench", "license_scope": "Repository MIT license; no separate dataset license established by this inspection",
        "requests": github("PratikGhawate/FinRCA-AI-Bench", "76c93ec32536e29826e2ab9e68b58e0351410bc7", [
            "README.md", "LICENSE", "docs/data_dictionary.md", "docs/failure_taxonomy.md",
            "data/benchmark/train/rca_ground_truth.jsonl"] + [
                f"data/{stage}/{name}.csv" for stage in ("raw_clean", "benchmark/full")
                for name in ("invoices", "payments", "payment_allocations", "bank_transactions", "bank_statements")]),
    },
    "finbalance": {
        "kind": "synthetic_document_accounting_benchmark", "revision": "a1062b7b392eaf53311308c2f63cf748b68bb8cf",
        "page": "https://github.com/Devansh1105/finbalance", "license_scope": "DATA_LICENSE.md explicitly covers generated data under CC BY 4.0; software license separate",
        "requests": github("Devansh1105/finbalance", "a1062b7b392eaf53311308c2f63cf748b68bb8cf", [
            "README.md", "LICENSE", "DATA_LICENSE.md", "data/README.md", "data/coverage/records.jsonl"]),
    },
    "fiscus": {
        "kind": "synthetic_workflow_state_fixtures", "revision": "86178237e0c5d75f4ff08b6452cbd9b2d25cb061",
        "page": "https://data.mendeley.com/datasets/w7tk797ngc/1", "license_scope": "Mendeley v1 and HF card declare CC BY 4.0",
        "requests": huggingface("keaxe21/fiscus-financial-workflow-state-fixtures", "86178237e0c5d75f4ff08b6452cbd9b2d25cb061", [
            "README.md", "data/financial_workflow_state_fixtures.jsonl"]),
    },
    "invoice_sample": {
        "kind": "constructed_invoice_payment_sample", "revision": "ed946c293697575a7ed1bf9bc27488bea2052ea0",
        "page": "https://github.com/RichieGarafola/invoice-reconciliation-tool", "license_scope": "Repository LICENSE; constructed sample, not verified company records",
        "requests": github("RichieGarafola/invoice-reconciliation-tool", "ed946c293697575a7ed1bf9bc27488bea2052ea0", [
            "README.md", "LICENSE", "data/sample_invoices.csv", "data/sample_payments.csv", "scripts/generate_sample_data.py"]),
    },
    "invoice_matcher": {
        "kind": "software_demo_fixtures", "revision": "1b1e4a4e14acb22503ca7d8dae821115aee3cb12",
        "page": "https://github.com/realtonkaa/invoice-payment-matcher", "license_scope": "Repository LICENSE; demo provenance only, no independent SME truth established",
        "requests": github("realtonkaa/invoice-payment-matcher", "1b1e4a4e14acb22503ca7d8dae821115aee3cb12", [
            "README.md", "LICENSE", "tests/fixtures/sample_bank.csv"] + [
                f"tests/fixtures/sample_invoices/invoice_{i:03d}.txt" for i in (1, 2, 3)]),
    },
}


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def snapshot(base, source_id, offline=False):
    spec = SOURCES[source_id]
    folder = base / source_id
    manifest_path = folder / "source_manifest.json"
    spec_hash = digest(json.dumps(spec, sort_keys=True).encode())
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        if manifest["spec_hash"] != spec_hash or manifest["use_policy"] != "inspection_only_excluded_from_matching":
            raise ValueError("Snapshot specification/policy differs")
        names = [v["file"] for v in manifest["files"]]
        errors = [v["file"] for v in manifest["errors"]]
        if len(set(names + errors)) != len(names + errors) or set(names + errors) != set(spec["requests"]):
            raise ValueError("Snapshot request coverage differs")
        for item in manifest["files"]:
            payload = (folder / item["file"]).read_bytes()
            if item["url"] != spec["requests"][item["file"]] or digest(payload) != item["sha256"] or len(payload) != item["bytes"]:
                raise ValueError("Snapshot bytes or provenance changed")
        return folder, manifest
    if offline:
        raise ValueError("Offline mode requires an existing snapshot")
    if folder.exists() and any(folder.iterdir()):
        raise ValueError("Incomplete snapshot; choose a new --input")
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"source_id": source_id, "spec_hash": spec_hash, "source": spec,
                "use_policy": "inspection_only_excluded_from_matching", "files": [], "errors": []}
    for name, url in spec["requests"].items():
        stamp = datetime.now(timezone.utc).isoformat()
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "FinanceProject-T0-FixtureResearch/1.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read(MAX_BYTES + 1)
                if len(payload) > MAX_BYTES:
                    raise ValueError("Response exceeds 16 MB bound")
                target = folder / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                manifest["files"].append({"file": name, "url": url, "status": response.status,
                    "checked_at_utc": stamp, "bytes": len(payload), "sha256": digest(payload)})
        except (OSError, ValueError) as exc:
            manifest["errors"].append({"file": name, "url": url, "checked_at_utc": stamp,
                "error_type": type(exc).__name__, "http_status": getattr(exc, "code", None), "reason": str(exc)[:200]})
    write_json(manifest_path, manifest)
    return folder, manifest


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("Missing/duplicate header")
        rows = list(reader)
        if any(None in row or any(v is None for v in row.values()) for row in rows):
            raise ValueError("Malformed CSV")
        return rows, reader.fieldnames


def jsonl_rows(path):
    return read_jsonl(path, parse_float=Decimal)


def index(rows, key):
    result = {r[key]: r for r in rows}
    if "" in result or len(result) != len(rows):
        raise ValueError("Blank or duplicate ID")
    return result


def audit_allocations(invoices, payments, allocations):
    inv = index(invoices, "invoice_id")
    pay = index(payments, "payment_id")
    inv_sums, pay_sums = defaultdict(Decimal), defaultdict(Decimal)
    by_inv, by_pay = defaultdict(set), defaultdict(set)
    counts = Counter()
    seen = set()
    for row in allocations:
        i, p = row["invoice_id"], row["payment_id"]
        counts["duplicate_allocation_pairs"] += (i, p) in seen
        seen.add((i, p))
        if i not in inv or p not in pay:
            counts["orphan_allocation_rows"] += 1
            continue
        amount = Decimal(row["allocated_amount"])
        if not amount.is_finite() or amount <= 0:
            raise ValueError("Invalid allocation amount")
        counts["cross_currency_edges"] += inv[i]["currency"] != pay[p]["payment_currency"]
        counts["cross_vendor_edges"] += inv[i]["vendor_id"] != pay[p]["vendor_id"]
        inv_sums[i] += amount
        pay_sums[p] += amount
        by_inv[i].add(p)
        by_pay[p].add(i)
    counts["invoices_with_multiple_payments"] = sum(len(v) > 1 for v in by_inv.values())
    counts["payments_with_multiple_invoices"] = sum(len(v) > 1 for v in by_pay.values())
    # Same-currency comparison only. No silent FX or inference from status.
    cross_i = {r["invoice_id"] for r in allocations if r["invoice_id"] in inv and r["payment_id"] in pay
               and inv[r["invoice_id"]]["currency"] != pay[r["payment_id"]]["payment_currency"]}
    for i, row in inv.items():
        if i in cross_i:
            continue
        amount, total = inv_sums[i], Decimal(row["invoice_total"])
        counts["invoices_no_allocation"] += amount == 0
        counts["invoices_partly_allocated"] += 0 < amount < total
        counts["invoices_overallocated"] += amount > total
    cross_p = {r["payment_id"] for r in allocations if r["invoice_id"] in cross_i}
    counts["payments_overallocated_same_currency"] = sum(
        pay_sums[p] > Decimal(row["payment_amount"]) for p, row in pay.items() if p not in cross_p)
    return dict(counts)


def audit_payout_bank(payout_rows, bank_rows, truth):
    payout = index(payout_rows, "payout_id")
    bank = index(bank_rows, "stmt_line_id")
    for row in payout_rows:
        int(row["amount_minor"])
        date.fromisoformat(row["expected_arrival_date"])
    for row in bank_rows:
        int(row["amount_minor"])
        date.fromisoformat(row["value_date"])
    grouped = defaultdict(list)
    for row in truth:
        grouped[row["stmt_line_id"]].append(row["payout_id"])
    counters = Counter()
    for bank_id, ids in grouped.items():
        if bank_id not in bank or any(p not in payout for p in ids):
            counters["groups_skipped_incomplete_observed_endpoints"] += 1
            continue
        b = bank[bank_id]
        if any(payout[p]["settle_currency"] != b["currency"] for p in ids):
            counters["groups_with_currency_mismatch"] += 1
            continue
        counters["complete_same_currency_groups"] += 1
        counters["complete_groups_equal_amount"] += sum(int(payout[p]["amount_minor"]) for p in ids) == int(b["amount_minor"])
    return {**dict(counters),
        "truth_rows_with_payout_absent_from_observed_table": sum(r["payout_id"] not in payout for r in truth),
        "truth_rows_with_bank_absent": sum(r["stmt_line_id"] not in bank for r in truth),
        "duplicate_truth_edges": len(truth) - len({(r["payout_id"], r["stmt_line_id"]) for r in truth}),
        "bank_ids_with_multiple_truth_payouts": sum(len(v) > 1 for v in grouped.values()),
        "payout_ids_with_multiple_bank_links": sum(v > 1 for v in Counter(r["payout_id"] for r in truth).values())}


def inspect(source_id, folder):
    profiles = {}
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.name == "source_manifest.json":
            continue
        name = path.relative_to(folder).as_posix()
        if path.suffix == ".csv":
            rows, fields = csv_rows(path)
            profiles[name] = {"rows": len(rows), "fields": fields}
        elif path.suffix == ".jsonl":
            rows = jsonl_rows(path)
            profiles[name] = {"rows": len(rows), "fields": sorted(set().union(*(r.keys() for r in rows)))}
        elif path.suffix == ".py":
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            profiles[name] = {"test_functions": [n.name for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")],
                "external_code_executed": False}
    result = {"file_profiles": profiles, "record_audits": {}}
    if source_id == "finrca":
        for stage in ("raw_clean", "benchmark/full"):
            tables = {n: csv_rows(folder / f"data/{stage}/{n}.csv")[0]
                      for n in ("invoices", "payments", "payment_allocations", "bank_transactions")}
            checks = audit_allocations(tables["invoices"], tables["payments"], tables["payment_allocations"])
            refs = Counter(r["reference_number"] for r in tables["payments"])
            checks["bank_rows_with_unique_payment_reference"] = sum(refs[r["payment_reference"]] == 1 for r in tables["bank_transactions"])
            checks["bank_reference_is_confirmed_truth"] = False
            statements = csv_rows(folder / f"data/{stage}/bank_statements.csv")[0]
            checks["statement_equation_failures"] = sum(
                Decimal(r["opening_balance"]) + Decimal(r["total_credits"]) - Decimal(r["total_debits"]) != Decimal(r["closing_balance"])
                for r in statements)
            checks["statement_totals_checked_against_transactions"] = False
            result["record_audits"][stage] = checks
        labels = jsonl_rows(folder / "data/benchmark/train/rca_ground_truth.jsonl")
        result["record_audits"]["train_label_fields"] = sorted(set().union(*(r.keys() for r in labels)))
    elif source_id == "recbench":
        tables = {n: csv_rows(folder / f"small/csv/{n}.csv")[0]
                  for n in ("payouts", "bank_statements", "truth_payout_bank")}
        result["record_audits"] = {
            **audit_payout_bank(tables["payouts"], tables["bank_statements"], tables["truth_payout_bank"]),
            "bank_currencies": dict(Counter(r["currency"] for r in tables["bank_statements"])),
            "bank_labels": dict(Counter(r["match_type"] for r in csv_rows(folder / "small/csv/labels_bank.csv")[0])),
            "payout_labels": dict(Counter(r["level"] for r in csv_rows(folder / "small/csv/labels_payout.csv")[0])),
            "ledger_settlement_tables_audited": False,
            "manifest_parquet_hashes_verified": False,
        }
    elif source_id == "finbalance":
        rows = jsonl_rows(folder / "data/coverage/records.jsonl")
        docs = [d for r in rows for d in r.get("documents", [])]
        result["record_audits"] = {"coverage_records": len(rows), "documents": len(docs),
            "document_types": dict(Counter(d.get("doc_type") for d in docs)),
            "record_fields": sorted(rows[0]), "pdfs_downloaded": False, "ledger_replayed": False}
    elif source_id == "fiscus":
        rows = jsonl_rows(folder / "data/financial_workflow_state_fixtures.jsonl")
        result["record_audits"] = {"domains": dict(Counter(r["domain"] for r in rows)),
            "expected_statuses": dict(Counter(r["expected_status"] for r in rows)),
            "published_jsonl_hash_matches": digest((folder / "data/financial_workflow_state_fixtures.jsonl").read_bytes()) ==
                "a4f618e6c8a01f93a78383142200ba89d1afca81bdba9f280f9053cb12ab1666"}
    elif source_id == "invoice_sample":
        invoices = csv_rows(folder / "data/sample_invoices.csv")[0]
        payments = csv_rows(folder / "data/sample_payments.csv")[0]
        inv = index(invoices, "invoice_id")
        totals = defaultdict(Decimal)
        counts = Counter()
        for p in payments:
            counts["orphan_payment_rows"] += p["invoice_id"] not in inv
            totals[p["invoice_id"]] += Decimal(p["amount_paid"])
        for i, r in inv.items():
            paid, due = totals[i], Decimal(r["amount"])
            status = "unpaid" if paid == 0 else "partial" if paid < due else "paid" if paid == due else "overpaid"
            counts[status] += 1
        result["record_audits"] = {"invoice_payment_status_counts": dict(counts),
            "explicit_invoice_id_already_in_payment": True,
            "independent_bank_observation_present": False}
    return result


def research(base, source_id, offline):
    folder, manifest = snapshot(base, source_id, offline)
    report = {"source_id": source_id, "manifest": manifest, "real_business_datasets_added": 0,
              "matcher_runs": 0, "matching_accepted": False}
    try:
        report["inspection"] = inspect(source_id, folder)
        report["status"] = "inspected_with_access_gaps" if manifest["errors"] else "inspected"
    except (ValueError, KeyError, OSError, SyntaxError, TypeError) as exc:
        report["status"] = "inspection_incomplete"
        report["inspection_error"] = str(exc)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / f"data/T0/raw/fixture_research/{DAY}")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; choose a new --output")
    with ThreadPoolExecutor(max_workers=4) as pool:
        reports = list(pool.map(lambda key: research(args.input, key, args.offline), SOURCES))
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "client_research_date": DAY, "script_sha256": digest(Path(__file__).read_bytes()), "sources": reports,
        "scope": "Pinned public fixture downloads, static source inspection and bounded tabular/JSONL audits; no upstream code, matcher or training run",
        "real_business_datasets_added": 0, "matcher_runs": 0,
        "limits": "Synthetic/demo fixtures are not SME validation. CSV hashes are local provenance, not verification of RecBench parquet release hashes. Historical labels and workflow expectations are not interchangeable with exhaustive invoice-bank amount truth."}
    write_json(args.output, report)
    for item in reports:
        print(f"{item['source_id']}: {item['status']}; files={len(item['manifest']['files'])}; access_errors={len(item['manifest']['errors'])}")
    return int(any(r["status"] == "inspection_incomplete" for r in reports))


if __name__ == "__main__":
    raise SystemExit(main())
