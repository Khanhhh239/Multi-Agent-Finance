"""Reliability bins for the locked v5/v4 validation and test comparisons."""
from __future__ import annotations

import json

import lightgbm as lgb
import numpy as np
import pandas as pd

from agent1.data.world_manifest import sha256_file
from agent1.models import t1
from agent1.paths import ROOT
from analysis.analyze_t1_v4_payment_survival import predicted_cdf as v4_paid_cdf
from experiments.t1_competing_v5.core import PAID, WRITEOFF, cumulative_incidence, observed_state, predict_hazards
from experiments.t1_competing_v5.run import (
    MODEL_PATH, OUTPUT, PROTOCOL_PATH, TRAIN_META, read_inputs,
    source_hashes, v5_state_at_day, world_snapshots,
)


def reliability_bins(probability: np.ndarray, outcome: np.ndarray, n_bins=10) -> list[dict]:
    probability = np.asarray(probability, dtype=float)
    outcome = np.asarray(outcome, dtype=int)
    if len(probability) != len(outcome) or not np.isfinite(probability).all():
        raise ValueError("Calibration inputs differ or contain nonfinite probabilities")
    # Equal-count bins retain resolution where predictions are concentrated.
    bin_id = pd.qcut(probability, q=n_bins, labels=False, duplicates="drop")
    if np.isscalar(bin_id):
        bin_id = np.zeros(len(probability), dtype=int)
    bins = np.asarray(bin_id)
    if np.isnan(bins).all():
        bins = np.zeros(len(probability), dtype=int)
    return [{"bin": int(i), "n": int(mask.sum()),
             "mean_predicted": float(probability[mask].mean()),
             "observed_rate": float(outcome[mask].mean())}
            for i in np.unique(bins) if (mask := (bins == i)).any()]


def main() -> None:
    protocol, cohort, old_meta, _ = read_inputs()
    metadata = json.loads(TRAIN_META.read_text(encoding="utf-8"))
    if metadata["source_hashes"] != source_hashes() or \
            metadata["protocol_sha256"] != sha256_file(PROTOCOL_PATH) or \
            metadata["model_sha256"] != sha256_file(MODEL_PATH):
        raise ValueError("v5 source/model differs from locked training")
    booster = lgb.Booster(model_file=str(MODEL_PATH))
    old_model = t1.HazardGBM(feats=old_meta["features"])
    old_model.booster = lgb.Booster(model_file=str(ROOT / protocol["source_model_v4"]))
    cutoffs = pd.date_range(protocol["eval_first_cutoff"], protocol["eval_last_cutoff"],
                            freq=f'{protocol["eval_stride_days"]}D')
    cutoffs = cutoffs[(pd.Timestamp(protocol["eval_label_end"]) - cutoffs).days >= 371]
    rows, summaries = [], []
    for entry in cohort["worlds"]:
        if entry["role"] == "train":
            continue
        world, role = entry["name"], entry["role"]
        frame = world_snapshots(world, cutoffs, protocol["eval_label_end"])
        frame = frame.sort_values(["cutoff", "invoice_id"]).drop_duplicates("invoice_id").reset_index(drop=True)
        hz = predict_hazards(booster, frame, metadata["features"])
        fp, fw, so = cumulative_incidence(hz)
        old_hz = old_model.hazards(frame)
        for day in (28, 91, 98, 365):
            actual = observed_state(frame, day)
            p5, w5, _ = v5_state_at_day(fp, fw, so, hz, day)
            p4 = v4_paid_cdf(old_hz, day)
            for name, p, w in (("v5_competing", p5, w5),
                               ("v4_paid_only", p4, np.zeros(len(p4)))):
                for cause, probability, target in (("paid", p, actual == PAID),
                                                   ("writeoff", w, actual == WRITEOFF)):
                    bins = reliability_bins(probability, target)
                    for row in bins:
                        rows.append({"world": world, "role": role, "model": name,
                                     "day": day, "cause": cause, **row})
                    ece = sum(row["n"] * abs(row["mean_predicted"] - row["observed_rate"])
                              for row in bins) / len(frame)
                    summaries.append({"world": world, "role": role, "model": name,
                                      "day": day, "cause": cause, "n": len(frame),
                                      "n_bins": len(bins), "ece": ece})
        print(f"calibration {world}: {len(frame):,}", flush=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUTPUT / "calibration_bins.csv", index=False)
    pd.DataFrame(summaries).to_csv(OUTPUT / "calibration_ece.csv", index=False)
    (OUTPUT / "calibration_summary.json").write_text(json.dumps({
        "analysis_code_sha256": sha256_file(__file__),
        "model_sha256": metadata["model_sha256"],
        "calibration_bins_sha256": sha256_file(OUTPUT / "calibration_bins.csv"),
        "calibration_ece_sha256": sha256_file(OUTPUT / "calibration_ece.csv"),
        "method": "Equal-count reliability bins on fully observed validation/test anchors",
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
