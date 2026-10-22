"""Generator shortcut audit V13: does the PRESENCE of a field separate fraud within a transaction type?

For every transaction type and every column, compare the fraud rate of rows where the field is filled with
rows where it is empty. A field that is filled almost only on fraud rows (or only on legitimate rows) of a
type is a generator artefact unless real books behave the same way. Output is a ranked table for human
review; all data are dữ liệu tổng hợp.
  python scripts/audit_field_presence.py work/data/v5dev_s1001 --out results/v5/field_presence_1001.json
"""
import argparse
import json
from pathlib import Path

import pandas as pd


def audit(world: Path, min_rows=5):
    tx = pd.read_csv(world / "transactions.csv", dtype=str, keep_default_na=False)
    lab = pd.read_csv(world / "labels.csv", dtype=str, keep_default_na=False, usecols=["transaction_id", "is_fraud"])
    d = tx.merge(lab, on="transaction_id")
    y = d.is_fraud == "1"
    findings = []
    for kind, g in d.groupby("txn_type"):
        gy = y[g.index]
        if gy.sum() == 0:
            continue
        for col in tx.columns:
            if col in ("transaction_id",):
                continue
            filled = g[col].astype(str).str.len() > 0
            n_f, n_e = int(filled.sum()), int((~filled).sum())
            if n_f < min_rows and n_e < min_rows:
                continue
            if n_f == 0 or n_e == 0:
                continue
            rate_f, rate_e = float(gy[filled].mean()), float(gy[~filled].mean())
            # extreme separation: one side almost pure fraud or containing almost all the type's fraud
            share_of_fraud_in_filled = float(gy[filled].sum() / gy.sum())
            if (rate_f >= .5 and n_f >= 2) or (rate_e >= .5 and n_e >= 2):
                findings.append(dict(txn_type=kind, column=col, filled_rows=n_f, empty_rows=n_e,
                                     fraud_rate_filled=round(rate_f, 3), fraud_rate_empty=round(rate_e, 3),
                                     fraud_share_filled=round(share_of_fraud_in_filled, 3)))
    return sorted(findings, key=lambda f: -max(f["fraud_rate_filled"], f["fraud_rate_empty"]))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("world", type=Path)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    f = audit(a.world)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"data_origin": "dữ liệu tổng hợp", "world": a.world.name, "findings": f},
                                ensure_ascii=False, indent=1), encoding="utf-8")
    for x in f:
        print(x)


if __name__ == "__main__":
    main()
