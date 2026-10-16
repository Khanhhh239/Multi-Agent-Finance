"""Paired case-clustered uncertainty for fixed development alert decisions.

The bootstrap resamples whole fraud cases and legitimate rows, using the same
draws for both policies. It does not reselect a weekly budget in each draw.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def paired_bootstrap(te, alerts_a, alerts_b, reps=2000, seed=0):
    if reps < 1:
        raise ValueError("reps must be positive")
    a, b = np.asarray(alerts_a), np.asarray(alerts_b)
    if a.shape != (len(te),) or b.shape != a.shape:
        raise ValueError("alert vectors must align with evaluation rows")
    if not np.isin(a, [False, True]).all() or not np.isin(b, [False, True]).all():
        raise ValueError("alerts must be binary")
    a, b = a.astype(bool), b.astype(bool)
    pos = te.is_fraud.to_numpy() == 1
    if not pos.any():
        raise ValueError("at least one fraud case is required")
    cases = te.loc[pos, ["company_id", "case_id"]].copy()
    if cases.case_id.isna().any() or (cases.case_id == "").any():
        raise ValueError("positive rows require case_id")
    cases["rows"] = 1
    cases["a"] = a[pos].astype(int)
    cases["b"] = b[pos].astype(int)
    g = cases.groupby(["company_id", "case_id"], sort=True)
    totals = g[["rows", "a", "b"]].sum().to_numpy()
    found = g[["a", "b"]].max().to_numpy()
    rng = np.random.default_rng(seed)
    deltas = np.empty((reps, 2))
    negatives = int((~pos).sum())
    # Legitimate-row resampling cannot change either recall statistic, so it is
    # integrated out exactly rather than allocating draws that have no effect.
    for i in range(reps):
        idx = rng.integers(len(totals), size=len(totals))
        sample = totals[idx].sum(axis=0)
        deltas[i, 0] = (sample[1] - sample[2]) / sample[0]
        deltas[i, 1] = (found[idx, 0] - found[idx, 1]).mean()
    point = [float(a[pos].mean() - b[pos].mean()),
             float((found[:, 0] - found[:, 1]).mean())]
    return {"recall_delta": {"estimate": point[0], "ci95": np.quantile(deltas[:, 0], [.025, .975]).tolist()},
            "case_recall_delta": {"estimate": point[1], "ci95": np.quantile(deltas[:, 1], [.025, .975]).tolist()},
            "found_cases_delta": {"estimate": point[1] * len(totals),
                                  "ci95": (np.quantile(deltas[:, 1], [.025, .975]) * len(totals)).tolist()},
            "cases": len(totals), "legitimate_rows": negatives, "reps": reps, "seed": seed}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--alerts", type=Path, nargs="+", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--reps", type=int, default=2000)
    args = p.parse_args()
    result = {}
    for path in args.alerts:
        with np.load(path, allow_pickle=False) as saved:
            frame = pd.DataFrame({k: saved[k] for k in ("company_id", "case_id", "is_fraud")})
            names = saved["names"].tolist()
            alerts = dict(zip(names, saved["alerts"]))
            result[path.stem] = {name: paired_bootstrap(frame, alerts[name], alerts["L3"], args.reps)
                                 for name in ("L4", "L4-FB", "L3-FB", "C-L4")}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
