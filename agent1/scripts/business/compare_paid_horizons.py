"""Paired offline comparison of cumulative full-settlement probabilities on open AR."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.t1_compact.historical_workspace import Method

ORIGIN = pd.Timestamp("2020-01-15")
FIRM = "HR-CA02"
HORIZONS = (28, 91)
KEY = ["firm_id", "invoice_id", "cutoff"]
PROBS = ["paid_28", "paid_91"]


def align(frame, predictions):
    """Reject missing/extra anchors rather than silently comparing intersections."""
    if predictions.duplicated(KEY).any():
        raise ValueError("Duplicate forecast keys")
    rows = frame[KEY].merge(
        predictions[KEY + PROBS],
        on=KEY,
        how="outer",
        indicator=True,
        validate="one_to_one",
    )
    if not rows["_merge"].eq("both").all():
        raise ValueError("Forecast keys must match the frozen cohort exactly")
    p = (
        rows.set_index(KEY)
        .loc[pd.MultiIndex.from_frame(frame[KEY]), PROBS]
        .to_numpy(float)
    )
    if (
        not np.isfinite(p).all()
        or (p < 0).any()
        or (p > 1).any()
        or (np.diff(p, axis=1) < -1e-9).any()
    ):
        raise ValueError(
            "Expected finite, monotone cumulative Paid probabilities in [0,1]"
        )
    return p


def ece(p, y):
    bins = np.minimum((p * 10).astype(int), 9)
    return np.abs(np.bincount(bins, weights=p - y, minlength=10)).sum() / len(p)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def paired_ci(delta_loss, customers):
    unique, idx = np.unique(customers, return_inverse=True)
    if len(unique) < 2:
        return None, None
    draw = np.random.default_rng(7).integers(len(unique), size=(1000, len(unique)))
    samples = np.bincount(idx, weights=delta_loss)[draw].sum(1) / np.bincount(idx)[
        draw
    ].sum(1)
    return tuple(np.quantile(samples, [0.025, 0.975]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate-csv",
        type=Path,
        help="Predictions generated at the origin for the exact real cohort",
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    source = ROOT / "data/interim/real_customer_invoices.parquet"
    data = pd.read_parquet(source, filters=[("firm_id", "==", FIRM)]).rename(
        columns={"paid_date_true": "settled", "amount_gross": "amount"}
    )
    data = data[
        (data.amount > 0)
        & (data.due_date >= data.issue_date)
        & (data.settled.isna() | (data.settled >= data.issue_date))
    ].sort_values(["issue_date", "invoice_id"])
    observed_end = data.settled.max()
    if ORIGIN + pd.Timedelta(days=max(HORIZONS)) > observed_end:
        raise ValueError("Insufficient follow-up")
    past = data[data.issue_date <= ORIGIN].copy()
    past.loc[past.settled > ORIGIN, "settled"] = pd.NaT
    past["known_at"] = past.issue_date
    past["settled_known_at"] = past.settled
    opened = past[past.settled.isna()].copy()
    opened["cutoff"] = str(ORIGIN.date())
    ages = (ORIGIN - opened.issue_date).dt.days

    def predict(name):
        model = Method(name).fit(past, ORIGIN)
        p = model.distribution(opened, ages)
        return np.column_stack([p[:, : days // 7].sum(1) for days in HORIZONS])

    with threadpool_limits(1), warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        anchor = predict("customer")
        candidate = (
            align(opened, pd.read_csv(args.candidate_csv, dtype={k: str for k in KEY}))
            if args.candidate_csv
            else predict("neural")
        )
    name = "external_candidate" if args.candidate_csv else "neural"
    days = (
        (data.loc[opened.index, "settled"] - ORIGIN).dt.days.fillna(np.inf).to_numpy()
    )
    truth = days[:, None] <= np.array(HORIZONS)
    overdue = (ORIGIN - opened.due_date).dt.days.to_numpy()
    groups = opened.customer_id.to_numpy()
    slices = {
        "all": np.ones(len(opened), bool),
        "not_overdue": overdue <= 0,
        "1_30": (overdue > 0) & (overdue <= 30),
        "31_90": (overdue > 30) & (overdue <= 90),
        "91_180": (overdue > 90) & (overdue <= 180),
        "over_180": overdue > 180,
    }
    rows = []
    for bucket, mask in slices.items():
        n = int(mask.sum())
        for j, h in enumerate(HORIZONS):
            row = dict(
                bucket=bucket,
                horizon_days=h,
                n=n,
                customers=len(np.unique(groups[mask])),
            )
            if n:
                a, b, y = anchor[mask, j], candidate[mask, j], truth[mask, j]
                la, lb = (a - y) ** 2, (b - y) ** 2
                row.update(
                    observed_rate=y.mean(),
                    anchor_mean=a.mean(),
                    candidate_mean=b.mean(),
                    anchor_brier=la.mean(),
                    candidate_brier=lb.mean(),
                    delta_brier=(lb - la).mean(),
                    anchor_ece10=ece(a, y),
                    candidate_ece10=ece(b, y),
                )
                row["ci_low"], row["ci_high"] = paired_ci(lb - la, groups[mask])
            rows.append(row)
    out = args.out or ROOT / "outputs/business" / (
        "paid_external_audit" if args.candidate_csv else "paid_horizon_audit"
    )
    out.mkdir(parents=True, exist_ok=True)
    results = pd.DataFrame(rows)
    results.to_csv(out / "scores.csv", index=False)
    meta = dict(
        origin=str(ORIGIN.date()),
        firm=FIRM,
        observed_end_proxy=str(observed_end.date()),
        anchor="customer",
        candidate=name,
        train_n=len(past),
        open_n=len(opened),
        primary_delta_ci95=paired_ci(
            ((candidate - truth) ** 2 - (anchor - truth) ** 2).mean(axis=1), groups
        ),
        primary_delta_brier_28_91=results.loc[
            results.bucket == "all", "delta_brier"
        ].mean(),
        data_sha256=sha(source),
        implementation_sha256=sha(ROOT / "agent1/adaptive/methods.py"),
        scorer_sha256=sha(Path(__file__)),
        candidate_csv_sha256=sha(args.candidate_csv) if args.candidate_csv else None,
        target="ERP clear_date proxy for full settlement; no verified bank cash or write-off labels",
        comparison="retrospective research on a previously inspected cohort; no production selection",
    )
    (out / "protocol.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(results.loc[results.bucket == "all"].to_string(index=False))


if __name__ == "__main__":
    main()
