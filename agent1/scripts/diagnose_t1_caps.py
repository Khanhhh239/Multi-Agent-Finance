"""Measure why final-cohort T1 inference quantiles hit the 120-day display cap."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.models.features import SnapshotBuilder
from agent1.models import t1
from agent1.paths import OUT, SYNTH
from scripts.train_manifest import _rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-only", action="store_true")
    args = parser.parse_args()
    source = OUT / "t1" / "v3_final_20261027_inference_2025-12-31"
    output = OUT / "t1" / "v3_final_20261027_cap_diagnostic_2025-12-31"
    output.mkdir(parents=True, exist_ok=True)
    if args.training_only:
        protocol = {"label_horizon_days": 120, "train_stride_days": 28,
                    "eval_stride_days": 28}
        rows = []
        for i in range(4):
            world = f"v3_final_20261027_train_{i:03d}"
            frame = _rows(SYNTH / world, "2024-07-01", role="train", protocol=protocol)
            high = frame.paid_frac_so_far.gt(.75)
            rows.append({"world": world, "snapshots": len(frame),
                         "events": int(frame.event.sum()),
                         "high_paid_fraction_snapshots": int(high.sum()),
                         "high_paid_fraction_events": int(frame.loc[high, "event"].sum())})
            print(rows[-1], flush=True)
        pd.DataFrame(rows).to_csv(output / "train_high_paid_fraction.csv", index=False)
        return
    predictions = pd.read_csv(source / "predictions.csv")
    meta = json.loads((OUT / "data" / "v3_final_20261027" / "train.json").read_text())
    model = t1.HazardGBM(feats=meta["features"])
    model.booster = lgb.Booster(model_file=str(OUT / "data" / "v3_final_20261027" / "model.txt"))
    cutoff = pd.Timestamp("2025-12-31")
    parts = []
    for world in predictions.world.unique():
        directory = SYNTH / world
        invoices = pd.read_parquet(directory / "invoices.parquet")
        builder = SnapshotBuilder(invoices,
                                  pd.read_parquet(directory / "payments.parquet"),
                                  pd.read_parquet(directory / "promises.parquet"))
        frame = builder.model_snapshot(cutoff)
        hazards = model.hazards(frame)
        unbounded = t1.quantiles_from_hazard(hazards, cap=10000)
        htail = np.clip(hazards[:, -4:].mean(1), .02, .6)
        p = predictions.loc[predictions.world.eq(world)].reset_index(drop=True).copy()
        if not p.invoice_id.equals(frame.invoice_id.reset_index(drop=True)):
            raise ValueError(f"{world}: prediction order differs from snapshot")
        truth = invoices.set_index("invoice_id").loc[p.invoice_id,
            ["closure_type", "ultra_late", "is_bad_debt", "paid_amount", "remaining_amount",
             "partial", "n_payments", "first_payment_date", "credit_note", "writeoff_date"]]
        for col in truth:
            p[col] = truth[col].to_numpy()
        p["age_days"] = frame.age_days.to_numpy()
        p["days_past_due"] = frame.days_past_due.to_numpy()
        p["paid_frac_so_far"] = frame.paid_frac_so_far.to_numpy()
        p["c_n_hist"] = frame.c_n_hist.to_numpy()
        p["htail"] = htail
        p["q50_unbounded"] = unbounded[:, 1]
        p["q90_unbounded"] = unbounded[:, 2]
        p["open_frac"] = p.amount_open / p.amount_gross
        parts.append(p)
        print(f"{world}: done", flush=True)
    d = pd.concat(parts, ignore_index=True)
    d["age_group"] = pd.cut(d.age_days, [-1, 30, 90, 180, 365, 730, 10000],
                            labels=["0-30", "31-90", "91-180", "181-365", "366-730", ">730"])
    d["overdue_group"] = pd.cut(d.days_past_due, [-1, 0, 30, 90, 180, 365, 730, 10000],
                                labels=["not overdue", "1-30", "31-90", "91-180", "181-365", "366-730", ">730"])
    d["paid_group"] = pd.cut(d.paid_frac_so_far, [-.01, 0, .25, .5, .75, .9999, 1.01],
                             labels=["none", "(0,.25]", "(.25,.5]", "(.5,.75]", "(.75,1)", "full"])
    d["customer_history_group"] = pd.cut(d.c_n_hist.fillna(0), [-1, 0, 2, 9, 1000000],
                                          labels=["0", "1-2", "3-9", "10+"])
    d["issue_year"] = pd.to_datetime(d.issue_date).dt.year
    d["paid_age_days"] = (cutoff - pd.to_datetime(d.first_payment_date)).dt.days
    d["paid_age_group"] = pd.cut(d.paid_age_days, [-1, 30, 90, 180, 365, 730, 10000],
                                 labels=["0-30", "31-90", "91-180", "181-365", "366-730", ">730"])

    groupings = ("world", "role", "age_group", "overdue_group", "paid_group",
                 "customer_history_group", "issue_year", "closure_type", "ultra_late",
                 "partial", "n_payments", "paid_age_group")
    for name in groupings:
        table = d.groupby(name, observed=True).agg(
            n=("invoice_id", "size"), q50_capped=("q50_capped", "sum"),
            q90_capped=("q90_capped", "sum"), amount_open=("amount_open", "sum"),
            p_paid_13w_mean=("p_paid_13w", "mean"), htail_median=("htail", "median"),
        ).reset_index()
        table["q50_cap_rate"] = table.q50_capped / table.n
        table["q90_cap_rate"] = table.q90_capped / table.n
        table.to_csv(output / f"by_{name}.csv", index=False)

    cross = d.groupby(["paid_group", "age_group"], observed=True).agg(
        n=("invoice_id", "size"), q50_capped=("q50_capped", "sum"),
        q90_capped=("q90_capped", "sum"), amount_open=("amount_open", "sum"),
    ).reset_index()
    cross.to_csv(output / "by_paid_and_age.csv", index=False)

    gains = pd.DataFrame({"feature": model.booster.feature_name(),
                          "gain": model.booster.feature_importance("gain"),
                          "splits": model.booster.feature_importance("split")})
    gains.sort_values("gain", ascending=False).to_csv(output / "feature_importance.csv", index=False)
    capped50 = d[d.q50_capped]
    capped90 = d[d.q90_capped]
    summary = {
        "n": int(len(d)), "q50_capped": int(len(capped50)), "q90_capped": int(len(capped90)),
        "q50_capped_amount_share": float(capped50.amount_open.sum() / d.amount_open.sum()),
        "q90_capped_amount_share": float(capped90.amount_open.sum() / d.amount_open.sum()),
        "q50_capped_overdue_gt_365": int((capped50.days_past_due > 365).sum()),
        "q90_capped_overdue_gt_365": int((capped90.days_past_due > 365).sum()),
        "q50_capped_age_gt_365": int((capped50.age_days > 365).sum()),
        "q90_capped_age_gt_365": int((capped90.age_days > 365).sum()),
        "q50_capped_p13_median": float(capped50.p_paid_13w.median()),
        "q90_capped_p13_median": float(capped90.p_paid_13w.median()),
        "q50_unbounded_capped_median": float(capped50.q50_unbounded.median()),
        "q90_unbounded_capped_median": float(capped90.q90_unbounded.median()),
        "q50_unbounded_capped_p90": float(capped50.q50_unbounded.quantile(.9)),
        "q90_unbounded_capped_p90": float(capped90.q90_unbounded.quantile(.9)),
        "q50_capped_htail_median": float(capped50.htail.median()),
        "q90_capped_htail_median": float(capped90.htail.median()),
        "n_invoices_issued_before_2025": int((d.issue_year < 2025).sum()),
        "q50_capped_issued_before_2025": int((capped50.issue_year < 2025).sum()),
        "q90_capped_issued_before_2025": int((capped90.issue_year < 2025).sum()),
        "n_closure_open": int(d.closure_type.eq("open").sum()),
        "q50_cap_due_to_p13_below_half": int((capped50.p_paid_13w < .5).sum()),
        "q90_cap_due_to_p13_below_nine_tenths": int((capped90.p_paid_13w < .9).sum()),
        "near_full_count": int(d.paid_frac_so_far.gt(.75).sum()),
        "near_full_two_payments": int((d.paid_frac_so_far.gt(.75) & d.n_payments.eq(2)).sum()),
        "near_full_partial_flag": int((d.paid_frac_so_far.gt(.75) & d.partial).sum()),
        "near_full_no_writeoff": int((d.paid_frac_so_far.gt(.75) & d.writeoff_date.isna()).sum()),
        "near_full_open_frac_median": float(d.loc[d.paid_frac_so_far.gt(.75), "open_frac"].median()),
        "near_full_paid_age_gt_90": int((d.loc[d.paid_frac_so_far.gt(.75), "paid_age_days"] > 90).sum()),
        "near_full_q50_capped": int(d.loc[d.paid_frac_so_far.gt(.75), "q50_capped"].sum()),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
