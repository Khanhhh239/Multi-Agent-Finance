"""Structural, chronology, accounting and artefact checks for world-v3 datasets.

Generalises the friend's validate.py (which hard-codes the six original families) and adds checks
for the artefacts v3 was built to remove.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from sme_fraud.features import FEATURE_DESCRIPTIONS
from sme_fraud.generate import WINDOWS, parse
from sme_fraud.validate import read_dataset

from .world_v3 import DECOYS_V3, FAMILIES_V3

TRUTH_COLUMNS = {"is_fraud", "fraud_type", "variant", "case_id", "hard_negative_type", "split", "difficulty"}


def validate_v3(directory: Path, strict_artifacts=True, expected_families=None, extra_decoys=()):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    tables = read_dataset(directory)
    tx = {r["transaction_id"]: r for r in tables["transactions"]}
    labels = {r["transaction_id"]: r for r in tables["labels"]}
    splits = {r["transaction_id"]: r["split"] for r in tables["splits"]}
    features = {r["transaction_id"]: r for r in tables["features"]}
    assert len(tx) == len(tables["transactions"]) == manifest["requested_rows"], "row count / duplicate ids"
    assert set(tx) == set(labels) == set(splits) == set(features), "join coverage"
    fraud = [r for r in labels.values() if int(r["is_fraud"])]
    assert len(fraud) == round(len(tx) * manifest["requested_fraud_rate"]), "exact fraud budget"
    assert set(r["fraud_type"] for r in fraud) == set(expected_families or FAMILIES_V3), "expected families present"
    assert not ({r["hard_negative_type"] for r in labels.values() if r["hard_negative_type"]} - set(DECOYS_V3) - set(extra_decoys) -
                set(manifest.get("hard_negative_types", [])) - _friend_hard_types()), "unknown hard negative type"
    assert all(not int(r["is_fraud"]) for r in labels.values() if r["hard_negative_type"]), "hard negatives labelled normal"
    assert list(next(iter(features.values()))) == ["transaction_id", *FEATURE_DESCRIPTIONS], "feature allowlist"
    assert not (TRUTH_COLUMNS & set(next(iter(tx.values())))), "truth leaked into raw transactions"
    employees = {r["employee_id"]: r for r in tables["employees"]}
    vendors = {r["vendor_id"]: r for r in tables["vendors"]}
    customers = {r["customer_id"]: r for r in tables["customers"]}
    cases = defaultdict(set)
    for tid, r in tx.items():
        at = parse(r["posted_at"])
        start, end = WINDOWS[splits[tid]]
        assert start <= parse(r["created_at"]) <= parse(r["approved_at"]) <= at < end, f"time consistency {tid}"
        assert int(r["amount_vnd"]) > 0 and r["currency"] == "VND", f"amount {tid}"
        for field, master in (("vendor_id", vendors), ("customer_id", customers), ("employee_id", employees),
                              ("creator_id", employees), ("approver_id", employees)):
            if r[field]:
                assert r[field] in master and master[r[field]]["company_id"] == r["company_id"], f"fk {tid} {field}"
                assert master[r[field]]["recorded_at"] <= r["posted_at"], f"future dimension {tid} {field}"
        if r["invoice_id"]:
            assert r["invoice_issued_at"] <= r["posted_at"], f"future invoice {tid}"
        if labels[tid]["case_id"]:
            cases[labels[tid]["case_id"]].add(splits[tid])
        assert all(math.isfinite(float(x)) for k, x in features[tid].items() if k != "transaction_id"), "nonfinite feature"
    assert all(len(s) == 1 for s in cases.values()), "case crosses a chronological split"
    balance = defaultdict(int)
    for line in tables["journal_lines"]:
        if line["transaction_id"]:
            balance[line["transaction_id"]] += int(line["debit_vnd"]) - int(line["credit_vnd"])
    assert all(v == 0 for v in balance.values()), "debits != credits"
    from sme_fraud.audit_accounting import check_accounting
    accounting = check_accounting(tables)

    # ---- artefact checks: nothing in master data should trivially separate fraud ----
    y = np.array([int(labels[t]["is_fraud"]) for t in features])
    report = dict(status="passed", observations=len(tx), fraud_rows=int(y.sum()), cases=len(cases),
                  families=dict(Counter(r["fraud_type"] for r in fraud)),
                  difficulty=dict(Counter(r["difficulty"] for r in fraud)),
                  decoys=dict(Counter(r["hard_negative_type"] for r in labels.values() if r["hard_negative_type"])))
    ten = np.array([float(features[t]["vendor_tenure_log_days"]) for t in features])
    vend = np.array([int(features[t]["has_vendor"]) for t in features])
    mask = vend == 1
    auc = roc_auc_score(y[mask], ten[mask])
    report["vendor_tenure_auc_among_vendor_rows"] = float(auc)
    onboard = Counter(v["onboarded_at"][:10] for v in vendors.values())
    report["max_share_vendors_same_onboard_day"] = max(onboard.values()) / len(vendors)
    names = [v["name"] for v in vendors.values()]
    distinctive = Counter(" ".join(n.split(" - ")[0].split()[-2:]) for n in names)
    report["max_share_same_distinctive_name"] = max(distinctive.values()) / len(names)
    if strict_artifacts:
        assert 0.10 <= auc <= 0.90, f"vendor tenure still separates fraud (AUC {auc:.3f})"
        assert report["max_share_vendors_same_onboard_day"] < .02, "onboarding dates collapsed"
        assert report["max_share_same_distinctive_name"] < .1, "vendor names not diverse"
    report["accounting_check"] = accounting if isinstance(accounting, dict) and len(json.dumps(accounting)) < 2000 else "ok"
    (directory / "validation_v3.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _friend_hard_types():
    from sme_fraud.generate import HARD_NEGATIVES
    return set(HARD_NEGATIVES)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate_v3(args.data), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
