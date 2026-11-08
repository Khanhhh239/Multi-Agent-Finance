"""Does injection-based selection find REAL labelled fraud in the held-out period of a generated world?

Labels are read only to MEASURE recall at 3 alerts per company-week; nothing is trained or selected on them.
  python -m sme_fraud.generate --output .runtime/exp/world_a --rows 30000 --fraud-rate 0.005 --seed 20261108 --companies 3
  python -B scripts/validate_bag_injection.py .runtime/exp/world_a 0     # world folder, company index
The generated world comes from this repository generator, so the result is optimistic relative to real data.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from sme_fraud.ml_estimators import CompanyEstimator  # noqa: E402

world = Path(sys.argv[1])
company_index = int(sys.argv[2]) if len(sys.argv) > 2 else 0
features = pd.read_csv(world / "features.csv")
cols = [c for c in features.columns if c != "transaction_id"]
tx = pd.read_csv(world / "transactions.csv", usecols=["transaction_id", "company_id", "posted_at"], dtype=str)
lab = pd.read_csv(world / "labels.csv", usecols=["transaction_id", "is_fraud", "fraud_type"], dtype=str, keep_default_na=False)
df = features.merge(tx, on="transaction_id").merge(lab, on="transaction_id")
df["t"] = pd.to_datetime(df.posted_at, utc=True, format="mixed")
company = sorted(df.company_id.unique())[company_index]
d = df[df.company_id == company].sort_values(["t", "transaction_id"]).reset_index(drop=True)
cut = int(len(d) * .6)
train, test = d.iloc[:cut], d.iloc[cut:].reset_index(drop=True)
x_tr, x_te = train[cols].to_numpy(np.float32), test[cols].to_numpy(np.float32)
fraud = (test.is_fraud == "1").to_numpy()
week = test.t.dt.strftime("%G-W%V").to_numpy()
print(f"company {company}: train {len(train)}, test {len(test)}, fraud rows in test {fraud.sum()} "
      f"({test[fraud].fraud_type.nunique()} types), fraud rows in train {(train.is_fraud == '1').sum()} (NOT used)")


def weekly_top(scores, k=3):
    flags = np.zeros(len(scores), bool)
    for w in np.unique(week):
        idx = np.flatnonzero(week == w)
        flags[idx[np.argsort(-scores[idx], kind="stable")[:k]]] = True
    return flags


def report(name, scores, seconds):
    flags = weekly_top(scores)
    hit = (flags & fraud).sum()
    top5 = scores >= np.quantile(scores, .95)
    types = {t: float(flags[(test.fraud_type == t).to_numpy()].mean()) for t in sorted(set(test.fraud_type[fraud]))}
    return dict(name=name, recall_w3=hit / max(1, fraud.sum()), precision_w3=hit / max(1, flags.sum()),
                recall_top5pct=(top5 & fraud).sum() / max(1, fraud.sum()), alerts=int(flags.sum()), seconds=round(seconds, 1)), types


rows, per_type = [], {}
for algorithm in ("isolation_forest", "ecod", "lof", "autoencoder", "bag_injection"):
    t = time.perf_counter()
    est = CompanyEstimator(algorithm).fit(x_tr, columns=cols)
    s = est.score(x_te)
    row, types = report(algorithm, s, time.perf_counter() - t)
    rows.append(row)
    per_type[algorithm] = types
    if algorithm == "bag_injection":
        dg = est.diagnostics_
        print("\nBAG chosen:", dg["chosen"], "members", dg["chosen_members"], dg["chosen_kind"], "| reliability", dg["reliability"])
        print("objective chosen %.3f vs baseline %.3f | injected recall mean chosen %.3f baseline %.3f | held-out-family estimate %.3f (min %.3f)" % (
            dg["chosen_objective"], dg["baseline_objective"], dg["recall_chosen_mean"], dg["recall_baseline_mean"],
            dg["held_out_family_recall_estimate"], dg["held_out_family_recall_min"]))
        print("families used", len(dg["families_used"]), "skipped", dg["families_skipped"], "methods failed", dg["methods_failed"])
        print("top candidates", dict(list(dg["candidate_objectives"].items())[:6]))
print()
print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f"{v:.3f}"))
print("\nrecall at 3 alerts per week, by REAL fraud type")
print(pd.DataFrame(per_type).round(2).to_string())
