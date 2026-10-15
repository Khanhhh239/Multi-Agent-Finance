"""Structural, prevalence, accounting, label-isolation and scenario checks."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from .features import FEATURE_DESCRIPTIONS
from .generate import FAMILIES, HARD_NEGATIVES, WINDOWS, parse


def read_dataset(directory):
    names = ("companies", "employees", "vendors", "customers", "transactions", "labels", "splits", "invoices",
             "journal_documents", "journal_lines", "document_links", "account_flow_edges",
             "bank_account_changes", "vendor_status_history", "advances", "advance_events", "features")
    tables = {}
    for name in names:
        with (directory/f"{name}.csv").open(encoding="utf-8-sig",newline="") as stream:
            tables[name] = list(csv.DictReader(stream))
    return tables


def validate(directory: Path):
    manifest = json.loads((directory/"manifest.json").read_text(encoding="utf-8"))
    tables = read_dataset(directory)
    tx = {r["transaction_id"]:r for r in tables["transactions"]}
    labels = {r["transaction_id"]:r for r in tables["labels"]}
    splits = {r["transaction_id"]:r["split"] for r in tables["splits"]}
    features = {r["transaction_id"]:r for r in tables["features"]}
    assert len(tx)==len(tables["transactions"])==manifest["requested_rows"], "Row count/IDs"
    assert set(tx)==set(labels)==set(splits)==set(features), "Join coverage"
    assert len(labels)==len(tables["labels"]) and len(features)==len(tables["features"]), "Duplicate truth/features"
    fraud = [r for r in labels.values() if int(r["is_fraud"])]
    assert len(fraud)==round(len(tx)*manifest["requested_fraud_rate"]), "Exact fraud budget"
    assert set(r["fraud_type"] for r in fraud)==set(FAMILIES), "Six families"
    assert set(r["hard_negative_type"] for r in labels.values() if r["hard_negative_type"])==set(HARD_NEGATIVES), "Hard-negative coverage"
    assert all(not int(r["is_fraud"]) for r in labels.values() if r["hard_negative_type"]), "Hard negatives labelled normal"
    assert list(next(iter(features.values())))==["transaction_id",*FEATURE_DESCRIPTIONS], "Feature allowlist"
    assert not ({"is_fraud","fraud_type","variant","case_id","hard_negative_type","split","difficulty"}&set(next(iter(tx.values())))), "Truth in raw transactions"
    cases = defaultdict(set)
    employee_map = {r["employee_id"]:r for r in tables["employees"]}
    vendor_map = {r["vendor_id"]:r for r in tables["vendors"]}
    customer_map = {r["customer_id"]:r for r in tables["customers"]}
    for tid,r in tx.items():
        at = parse(r["posted_at"])
        start,end = WINDOWS[splits[tid]]
        assert start<=parse(r["created_at"])<=parse(r["approved_at"])<=at<end, f"Time consistency {tid}"
        assert int(r["amount_vnd"])>0 and r["currency"]=="VND", f"Amount/currency {tid}"
        for field,master in (("vendor_id",vendor_map),("customer_id",customer_map),("employee_id",employee_map),
                             ("creator_id",employee_map),("approver_id",employee_map)):
            if r[field]:
                assert r[field] in master and master[r[field]]["company_id"]==r["company_id"], f"FK/company {tid} {field}"
                assert master[r[field]]["recorded_at"]<=r["posted_at"], f"Future dimension {tid}"
        assert not (r["txn_type"]=="payroll" and r["vendor_id"]), "Payroll must not use vendor"
        if r["invoice_id"]:
            assert r["invoice_issued_at"]<=r["posted_at"], f"Future invoice {tid}"
        if labels[tid]["case_id"]:
            cases[labels[tid]["case_id"]].add(splits[tid])
        assert all(math.isfinite(float(x)) for k,x in features[tid].items() if k!="transaction_id"), "Feature nonfinite"
    assert all(len(s)==1 for s in cases.values()), "Case crosses chronological split"
    balance, ledger_counts = defaultdict(int), Counter()
    for line in tables["journal_lines"]:
        tid = line["transaction_id"]
        if not tid:
            continue
        assert tid in tx and int(tx[tid]["is_financial_entry"]), "Journal FK/financial rows"
        balance[tid] += int(line["debit_vnd"])-int(line["credit_vnd"])
        ledger_counts[tid] += 1
    assert all(value==0 for value in balance.values()), "Debits != credits"
    assert all(ledger_counts[tid]>=2 if int(r["is_financial_entry"]) else ledger_counts[tid]==0 for tid,r in tx.items()), "Missing financial lines/review booked as cash"
    from .audit_accounting import check_accounting
    accounting = check_accounting(tables)
    for tid,l in labels.items():
        f = features[tid]
        if l["hard_negative_type"]=="verified_bank_change":
            assert int(f["bank_changed_recently"]) and int(f["bank_change_verified"]), "Verified bank negative"
        if l["hard_negative_type"]=="legitimate_self_approval":
            assert int(f["self_approved"]) and int(f["self_approval_permitted"]), "Permitted self approval"
        if l["hard_negative_type"]=="legitimate_installments":
            assert float(f["cumulative_invoice_payment_ratio"])<=1.00001, "Installment exceeds invoice"
        if l["variant"]=="repeated_full_invoice":
            assert float(f["cumulative_invoice_payment_ratio"])>1 and int(f["prior_invoice_payment_count"])>=1, "Duplicate evidence"
        if l["variant"]=="new_shell_two_hop":
            assert int(f["graph_employee_count"])>=1, "Hidden two-hop link absent"
        if l["variant"]=="ghost_employee_payroll":
            assert int(f["recipient_employee_bank_count"])>=2 and int(f["attendance_known"]) and not int(f["attendance_days"]), "Ghost employee evidence"
        if l["variant"]=="overdue_unsettled":
            assert float(f["advance_overdue_days"])>0 and float(f["advance_open_fraction"])>0, "Advance overdue evidence"
        if l["hard_negative_type"]=="approved_advance_extension":
            assert int(f["advance_extension_known"]) and not float(f["advance_overdue_days"]), "Extension as-of state"
        if l["observability"]=="registry_reported_later":
            assert not int(f["registry_risky_now"]), "Registry future leakage"
        if l["hard_negative_type"]=="historical_valid_invoice":
            assert int(f["registry_risky_now"]) and not int(f["registry_risky_at_invoice"]), "Historical invoice chronology"
        if int(tx[tid]['is_financial_entry']):
            assert int(f['pair_supported_for_scenario']) and not int(f['account_outside_framework']), 'Accounting feature audit'
        if tx[tid]['txn_type']=='advance_writeoff':
            assert int(f['advance_writeoff_evidence_missing'])==int(not int(tx[tid]['evidence_on_file'])), 'Writeoff evidence feature'
    for name,info in manifest["files"].items():
        assert hashlib.sha256((directory/name).read_bytes()).hexdigest()==info["sha256"], f"Checksum {name}"
    result = dict(status="passed",observations=len(tx),fraud_rows=len(fraud),hard_negatives=manifest["hard_negative_rows"],
                  balanced_financial_documents=len(balance),case_count=len(cases),
                  checks=["exact_prevalence","foreign_keys","chronology","case_split_isolation","balanced_journal",
                          "no_payroll_vendor","numeric_features","label_isolation","scenario_evidence","file_checksums",
                          "accounting_framework","compound_vat_entries","production_flow","writeoff_reclassification",
                          "auxiliary_document_chronology"])
    (directory/"validation.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    (directory/'accounting_validation.json').write_text(json.dumps(accounting,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data",type=Path,default=Path("data/sme_fraud_003"))
    args=parser.parse_args()
    print(json.dumps(validate(args.data),indent=2))


if __name__=="__main__":
    main()
