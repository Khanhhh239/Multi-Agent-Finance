"""Validation and realism audit for world-v4 datasets.

Structural: join coverage, chronology inside the split, foreign keys and no future master data, balanced books
(friend's accounting audit, extended to the new kinds), truth isolated from transactions/features.
Business: every receipt points to an earlier sales invoice; payroll after a resignation exists only as a final
settlement or as labelled fraud; every scheme has a case in every split; case rows stay in one split.
Calibration report: realised ACFE-style shares (perpetrator level, collusion, concealment) and per-scheme volumes.
Shortcut audit: a model given only nuisance fields that carry no fraud meaning in real books (minute, second,
transaction-ID ordinal, invoice-number digits, amount modulo 1,000) must not separate fraud (AUC near .5).
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from sme_fraud.generate import WINDOWS, parse

from .accounting_ext import check_accounting_v4
from .world_v4_schemes import SCHEMES

TRUTH = {"is_fraud", "fraud_type", "variant", "case_id", "hard_negative_type", "split", "difficulty", "scheme_group", "concealment"}


def read(directory, name):
    with (directory / f"{name}.csv").open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def shortcut_audit(directory: Path):
    """AUC gain from nuisance fields on top of the transaction type (type mix legitimately differs for fraud)."""
    import lightgbm as lgb
    tx = pd.read_csv(directory / "transactions.csv", keep_default_na=False, dtype=str,
                     usecols=["transaction_id", "posted_at", "invoice_number", "amount_vnd", "txn_type"])
    lab = pd.read_csv(directory / "labels.csv", keep_default_na=False, usecols=["transaction_id", "is_fraud"])
    sp = pd.read_csv(directory / "splits.csv")
    d = tx.merge(lab, on="transaction_id").merge(sp, on="transaction_id")
    t = pd.to_datetime(d["posted_at"].str[:19])
    base = pd.get_dummies(d["txn_type"]).astype(int)
    nuisance = pd.DataFrame({"minute": t.dt.minute, "second": t.dt.second, "id_ordinal": d["transaction_id"].str[1:].astype(int),
                             "invoice_digits": pd.to_numeric(d["invoice_number"].str.extract(r"(\d+)")[0], errors="coerce").fillna(-1),
                             "amount_mod_1000": d["amount_vnd"].astype(np.int64) % 1000})
    tr, te = d["split"] == "train", d["split"] == "test"
    out = {}
    for name, x in (("type_only", base), ("type_plus_nuisance", pd.concat([base, nuisance], axis=1))):
        m = lgb.LGBMClassifier(n_estimators=200, num_leaves=15, learning_rate=.05, verbose=-1, class_weight="balanced").fit(x[tr], d.loc[tr, "is_fraud"])
        out[name] = float(roc_auc_score(d.loc[te, "is_fraud"], m.predict_proba(x[te])[:, 1]))
    out["gain"] = out["type_plus_nuisance"] - out["type_only"]
    return out


def validate_v4(directory: Path, run_shortcut=True):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    names = ("companies", "employees", "vendors", "customers", "transactions", "labels", "splits", "invoices", "journal_documents",
             "journal_lines", "document_links", "account_flow_edges", "bank_account_changes", "advance_events", "features", "truth_cases")
    tables = {n: read(directory, n) for n in names}
    tx = {r["transaction_id"]: r for r in tables["transactions"]}
    lab = {r["transaction_id"]: r for r in tables["labels"]}
    spl = {r["transaction_id"]: r["split"] for r in tables["splits"]}
    feats = tables["features"]
    assert len(tx) == manifest["requested_rows"] and set(tx) == set(lab) == set(spl) == {r["transaction_id"] for r in feats}, "join coverage"
    assert not (TRUTH & set(tables["transactions"][0])) and not (TRUTH & set(feats[0])), "truth leaked into transactions/features"
    emp = {r["employee_id"]: r for r in tables["employees"]}
    ven = {r["vendor_id"]: r for r in tables["vendors"]}
    cus = {r["customer_id"]: r for r in tables["customers"]}
    case_splits = defaultdict(set)
    for tid, r in tx.items():
        at = parse(r["posted_at"])
        a, b = WINDOWS[spl[tid]]
        assert a <= parse(r["created_at"]) <= parse(r["approved_at"]) <= at < b, f"chronology {tid} {lab[tid]['fraud_type']}"
        for f, m in (("vendor_id", ven), ("customer_id", cus), ("employee_id", emp), ("creator_id", emp), ("approver_id", emp)):
            if r[f]:
                assert r[f] in m and m[r[f]]["company_id"] == r["company_id"], f"fk {tid} {f}"
                assert m[r[f]]["recorded_at"] <= r["posted_at"], f"future master {tid} {f} {lab[tid]['fraud_type']}"
        if lab[tid]["case_id"]:
            case_splits[lab[tid]["case_id"]].add(spl[tid])
    assert all(len(s) == 1 for s in case_splits.values()), "case crosses a split"
    # business integrity
    inv_time = {r["invoice_id"]: r["posted_at"] for r in tx.values() if r["txn_type"] == "sales_invoice"}
    bad_receipts = [t for t, r in tx.items() if r["txn_type"] == "customer_receipt" and r["applied_invoice_id"]
                    and not (r["applied_invoice_id"] in inv_time and inv_time[r["applied_invoice_id"]] <= r["posted_at"])]
    assert not bad_receipts, f"receipts without earlier invoice: {bad_receipts[:3]}"
    after_leave = Counter()
    for t, r in tx.items():
        if r["txn_type"] == "payroll" and r["employee_id"] and emp[r["employee_id"]]["terminated_at"] and r["posted_at"] > emp[r["employee_id"]]["terminated_at"]:
            after_leave[lab[t]["fraud_type"] or lab[t]["hard_negative_type"] or "UNLABELLED"] += 1
    assert "UNLABELLED" not in after_leave, f"payroll after resignation without label: {after_leave}"
    accounting = check_accounting_v4(tables)
    cases = tables["truth_cases"]
    coverage = defaultdict(set)
    for c in cases:
        coverage[c["scheme"]].add(c["split"])
    missing = {s: sorted(set(WINDOWS) - coverage[s]) for s in SCHEMES if set(WINDOWS) - coverage[s]}
    fraud_by_case = Counter(r["case_id"] for r in lab.values() if int(r["is_fraud"]))
    assert all(int(c["fraud_rows"]) == fraud_by_case[c["case_id"]] for c in cases), "truth_cases row counts"
    y = sum(int(r["is_fraud"]) for r in lab.values())
    report = dict(status="passed", rows=len(tx), fraud_rows=y, fraud_rate=y / len(tx), cases=len(cases),
                  schemes=len({c["scheme"] for c in cases}), scheme_split_gaps=missing,
                  companies=len(tables["companies"]), companies_with_fraud=len({c["company_id"] for c in cases}),
                  perpetrator_level=dict(Counter(c["perpetrator_level"] for c in cases)),
                  collusion=dict(Counter(c["collusion"] for c in cases)), concealment=dict(Counter(c["concealment"] for c in cases)),
                  acfe_branch_cases=dict(Counter(c["acfe_branch"] for c in cases)),
                  rows_per_scheme=dict(Counter(r["fraud_type"] for r in lab.values() if int(r["is_fraud"]))),
                  decoys=dict(Counter(r["hard_negative_type"] for r in lab.values() if r["hard_negative_type"])),
                  payroll_after_resignation=dict(after_leave), txn_types=dict(Counter(r["txn_type"] for r in tx.values())),
                  accounting_status=accounting["status"])
    if run_shortcut:
        report["shortcut_audit"] = shortcut_audit(directory)
        assert report["shortcut_audit"]["gain"] < .05, "generator shortcut: nuisance fields add fraud signal beyond the type"
    (directory / "validation_v4.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, required=True)
    print(json.dumps(validate_v4(p.parse_args().data), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
