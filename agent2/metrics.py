"""Metrics that match how a small business actually uses alerts.

* ranking quality: average precision (AP), R-precision (precision at K = number of positives)
* operating points: a fixed alert budget per company-week (B = 1 and 3), which is what an accountant can read
* case view: a fraud case (several rows) counts as found when any of its rows is alerted
* earliness: days from the first row of a case to the first alerted row
* honesty: hard-negative (legitimate look-alike) false-alert rate at the same operating point
* uncertainty: case-clustered bootstrap for AP
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score


def tie_break(n, seed=0):
    return np.random.default_rng(seed).random(n) * 1e-9


def average_precision(y, s):
    return float(average_precision_score(y, s)) if y.sum() else float("nan")


def r_precision(y, s):
    k = int(y.sum())
    if k == 0:
        return float("nan")
    order = np.argsort(-s, kind="stable")[:k]
    return float(y[order].mean())


def weekly_alerts(df: pd.DataFrame, s: np.ndarray, per_week: int, min_score=-np.inf) -> np.ndarray:
    """Top `per_week` rows per (company, week) by score; rows below `min_score` are never alerted."""
    tmp = pd.DataFrame({"g": df["company_id"].values + "_" + df["week"].astype(str).values, "s": s})
    rank = tmp.groupby("g")["s"].rank(method="first", ascending=False).values
    return (rank <= per_week) & (s >= min_score)


def case_stats(df: pd.DataFrame, alerts: np.ndarray):
    pos = df["is_fraud"].values == 1
    cases = df.loc[pos, ["case_id", "t"]].assign(alert=alerts[pos])
    if cases.empty:
        return dict(cases=0, case_recall=float("nan"), median_delay_days=float("nan"))
    g = cases.groupby("case_id")
    found = g["alert"].any()
    first = g["t"].min()
    first_alert = cases[cases["alert"]].groupby("case_id")["t"].min()
    delay = (first_alert - first.loc[first_alert.index]).dt.total_seconds() / 86400
    return dict(cases=int(len(found)), case_recall=float(found.mean()),
                median_delay_days=float(delay.median()) if len(delay) else float("nan"))


def entity_key(df: pd.DataFrame) -> pd.Series:
    """Case entity: the vendor when there is one, else the employee, else the creating user."""
    vendor = df["vendor_id"].astype(str).replace({"": np.nan})
    employee = df["employee_id"].astype(str).replace({"": np.nan})
    return df["company_id"] + ":" + vendor.fillna(employee).fillna(df["creator_id"].astype(str))


def entity_level(df: pd.DataFrame, alerts: np.ndarray):
    """Collapse alerted rows into one alert per (entity, ISO week): what the accountant actually opens."""
    key = (entity_key(df) + "|" + df["week"].astype(str)).values
    y = df["is_fraud"].values
    frame = pd.DataFrame({"k": key[alerts], "y": y[alerts]})
    if frame.empty:
        return dict(entity_alerts=0, entity_precision=float("nan"))
    g = frame.groupby("k")["y"].max()
    return dict(entity_alerts=int(len(g)), entity_precision=float(g.mean()))


def operating_point(df: pd.DataFrame, alerts: np.ndarray):
    y = df["is_fraud"].values
    n = int(alerts.sum())
    tp = int((alerts & (y == 1)).sum())
    hard = df["hard_negative_type"].values != ""
    out = dict(alerts=n, alerts_per_1000=1000 * n / len(df), tp=tp, precision=tp / n if n else float("nan"),
               recall=tp / max(1, int(y.sum())),
               hard_neg_alert_rate=float(alerts[hard & (y == 0)].mean()) if (hard & (y == 0)).any() else float("nan"))
    out.update(case_stats(df, alerts))
    out.update(entity_level(df, alerts))
    return out


def evaluate_scores(df: pd.DataFrame, score: np.ndarray, budgets=(1, 3), seed=0) -> dict:
    """df must be the evaluation slice (e.g. the test split). `score`: higher = more suspicious."""
    y = df["is_fraud"].values.astype(int)
    s = np.asarray(score, dtype=float) + tie_break(len(df), seed)
    out = dict(rows=len(df), positives=int(y.sum()), ap=average_precision(y, s), r_precision=r_precision(y, s),
               roc_auc=float(roc_auc_score(y, s)) if 0 < y.sum() < len(y) else float("nan"),
               ap_baseline=float(y.mean()))
    for b in budgets:
        out[f"B{b}"] = operating_point(df, weekly_alerts(df, s, b))
    return out


def per_group_recall(df: pd.DataFrame, score: np.ndarray, column: str, per_week=3, seed=0) -> dict:
    s = np.asarray(score, dtype=float) + tie_break(len(df), seed)
    alerts = weekly_alerts(df, s, per_week)
    pos = df["is_fraud"].values == 1
    res = {}
    for key, idx in df[pos].groupby(column).groups.items():
        rows = df.index.get_indexer(idx)
        res[str(key)] = dict(n=int(len(rows)), recall=float(alerts[rows].mean()))
    return res


def bootstrap_ap(df: pd.DataFrame, score: np.ndarray, reps=200, seed=0):
    """Case-clustered bootstrap: resample fraud cases and legitimate rows with replacement."""
    rng = np.random.default_rng(seed)
    y = df["is_fraud"].values.astype(int)
    s = np.asarray(score, dtype=float) + tie_break(len(df), seed)
    pos_cases = df.loc[y == 1, "case_id"].values
    cases = np.unique(pos_cases)
    by_case = {c: np.where((y == 1) & (df["case_id"].values == c))[0] for c in cases}
    neg_idx = np.where(y == 0)[0]
    aps = []
    for _ in range(reps):
        pick = rng.choice(cases, len(cases))
        pos = np.concatenate([by_case[c] for c in pick])
        neg = rng.choice(neg_idx, len(neg_idx))
        idx = np.concatenate([pos, neg])
        aps.append(average_precision_score(y[idx], s[idx]))
    return [float(np.percentile(aps, 2.5)), float(np.percentile(aps, 97.5))]
