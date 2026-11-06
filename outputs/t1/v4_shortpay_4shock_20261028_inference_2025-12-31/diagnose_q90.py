"""Read-only Q90 audit for the locked v4 T1 inference batch.

Run with project dependencies available: python <this file>
This file lives outside agent1/ and scripts/ to preserve the train code hash.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from agent1.data.world_manifest import sha256_file  # noqa: E402
from agent1.models import t1  # noqa: E402
from agent1.models.features import SnapshotBuilder  # noqa: E402


def grouped(frame: pd.DataFrame, column: str) -> list[dict]:
    result = []
    for value, group in frame.groupby(column, observed=True, dropna=False):
        capped = group.q90_capped
        result.append({
            column: str(value), "n": int(len(group)),
            "q90_capped": int(capped.sum()),
            "q90_cap_rate": float(capped.mean()),
            "share_of_all_caps": float(capped.sum() / frame.q90_capped.sum()),
            "open_amount": float(group.amount_open.sum()),
            "capped_open_amount": float(group.loc[capped, "amount_open"].sum()),
            "p13_median": float(group.p_paid_13w.median()),
        })
    return result


def main() -> None:
    directory = Path(__file__).resolve().parent
    out_data = ROOT / "outputs/data/v4_shortpay_4shock_20261028"
    synthetic = ROOT / "data/synthetic"
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    train = json.loads((out_data / "train.json").read_text(encoding="utf-8"))
    if sha256_file(directory / "predictions.csv") != summary["predictions_sha256"]:
        raise ValueError("Predictions changed since inference")
    if sha256_file(out_data / "model.txt") != train["model_sha256"]:
        raise ValueError("Model changed since training")

    predictions = pd.read_csv(directory / "predictions.csv")
    model = t1.HazardGBM(feats=train["features"])
    model.booster = lgb.Booster(model_file=str(out_data / "model.txt"))
    chunks = []
    cutoff = pd.Timestamp(summary["as_of"])
    for world, group in predictions.groupby("world", sort=False):
        source = synthetic / world
        frame = SnapshotBuilder(
            pd.read_parquet(source / "invoices.parquet"),
            pd.read_parquet(source / "payments.parquet"),
            pd.read_parquet(source / "promises.parquet"),
        ).model_snapshot(cutoff)
        group = group.reset_index(drop=True).copy()
        if not frame.invoice_id.reset_index(drop=True).equals(group.invoice_id):
            raise ValueError(f"Snapshot order mismatch: {world}")
        H = model.hazards(frame)
        _, S = t1.pmf_from_hazard(H)
        tail_raw = H[:, -4:].mean(axis=1)
        tail = np.clip(tail_raw, .02, .6)
        s91 = S[:, -1]
        f120 = 1 - s91 * np.power(1 - tail, (120 - 91) / 7)
        q90_uncapped = t1.quantiles_from_hazard(H, cap=100000)[:, 2]
        group["age_days"] = frame.age_days.to_numpy()
        group["days_past_due"] = frame.days_past_due.to_numpy()
        group["paid_frac"] = frame.paid_frac_so_far.to_numpy()
        group["s91"] = s91
        group["f120"] = f120
        group["tail_h_raw"] = tail_raw
        group["tail_h"] = tail
        group["q90_uncapped"] = q90_uncapped
        chunks.append(group)
        print(f"{world}: {len(group)}", flush=True)
    d = pd.concat(chunks, ignore_index=True)
    if len(d) != summary["n_open"] or int(d.q90_capped.sum()) != summary["n_q90_capped"]:
        raise ValueError("Counts differ from inference summary")
    if not np.allclose(d.p_paid_13w, 1 - d.s91, atol=1e-9):
        raise ValueError("13-week CDF differs from inference")
    if not (d.q90_capped.to_numpy() == (d.q90_uncapped.to_numpy() >= 120)).all():
        raise ValueError("Uncapped Q90 does not explain cap flag")
    if not (d.q90_capped.to_numpy() == (d.f120.to_numpy() <= .9 + 1e-10)).all():
        raise ValueError("CDF at 120 days does not explain cap flag")

    d["age_group"] = pd.cut(d.age_days, [-1, 30, 90, 180, 365, 730, 100000],
                             labels=["0-30", "31-90", "91-180", "181-365", "366-730", ">730"])
    d["dpd_group"] = pd.cut(d.days_past_due, [-100000, 0, 30, 90, 180, 365, 100000],
                             labels=["not_overdue", "1-30", "31-90", "91-180", "181-365", ">365"])
    d["paid_group"] = pd.cut(d.paid_frac, [-.001, 0, .25, .5, .75, 1],
                              labels=["none", "0-25%", "25-50%", "50-75%", ">75%"])
    d["p13_group"] = pd.cut(d.p_paid_13w, [-.001, .1, .5, .8, .9, 1],
                             labels=["0-10%", "10-50%", "50-80%", "80-90%", "90-100%"])
    d["q90_unbounded_group"] = pd.cut(d.q90_uncapped, [0, 91, 120, 180, 365, 1000000],
                                       labels=["<=91", "91-120", "120-180", "180-365", ">365"])
    capped = d[d.q90_capped]
    stats = {
        "source_predictions_sha256": summary["predictions_sha256"],
        "source_model_sha256": train["model_sha256"],
        "n": int(len(d)), "q90_capped": int(len(capped)),
        "q90_cap_rate": float(len(capped) / len(d)),
        "q90_capped_amount_share": float(capped.amount_open.sum() / d.amount_open.sum()),
        "p13_below_90_count": int((d.p_paid_13w < .9).sum()),
        "p13_below_90_among_capped": int((capped.p_paid_13w < .9).sum()),
        "p13_below_50_among_capped": int((capped.p_paid_13w < .5).sum()),
        "p13_capped_median": float(capped.p_paid_13w.median()),
        "f120_capped_median": float(capped.f120.median()),
        "tail_floor_binding_count": int((d.tail_h_raw < .02).sum()),
        "tail_floor_binding_among_capped": int((capped.tail_h_raw < .02).sum()),
        "tail_h_capped_median": float(capped.tail_h.median()),
        "q90_uncapped_capped_median_days": float(capped.q90_uncapped.median()),
        "q90_uncapped_capped_p90_days": float(capped.q90_uncapped.quantile(.9)),
        "q90_above_180_count": int((d.q90_uncapped > 180).sum()),
        "q90_above_365_count": int((d.q90_uncapped > 365).sum()),
        "cap_if_180": int((d.q90_uncapped >= 180).sum()),
        "cap_if_365": int((d.q90_uncapped >= 365).sum()),
        "groupings": {key: grouped(d, key) for key in
                      ("role", "world", "age_group", "dpd_group", "paid_group", "p13_group", "q90_unbounded_group")},
    }
    (directory / "q90_diagnostic.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in stats.items() if k != "groupings"}, indent=2))


if __name__ == "__main__":
    main()
