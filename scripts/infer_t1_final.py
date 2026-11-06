"""Batch T1 inference on open invoices in the locked final synthetic cohort."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.data.world_manifest import code_provenance, load_cohort, sha256_file
from agent1.models.features import SnapshotBuilder
from agent1.models import t1
from agent1.paths import OUT, SYNTH


DEFAULT_COHORT = SYNTH / "v3_final_20261027_cohort.json"
DEFAULT_MODEL_DIR = OUT / "data" / "v3_final_20261027"


def infer(cohort_path: Path, model_dir: Path, output_dir: Path, as_of: str) -> dict:
    cohort_path, model_dir, output_dir = map(Path, (cohort_path, model_dir, output_dir))
    cutoff = pd.Timestamp(as_of)
    if pd.isna(cutoff) or cutoff != cutoff.normalize():
        raise ValueError("as_of must be a calendar date")

    cohort = load_cohort(cohort_path)
    metadata = json.loads((model_dir / "train.json").read_text(encoding="utf-8"))
    model_path = model_dir / "model.txt"
    cohort_hash, model_hash = sha256_file(cohort_path), sha256_file(model_path)
    if metadata["cohort_sha256"] != cohort_hash or metadata["model_sha256"] != model_hash:
        raise ValueError("T1 model does not match the locked cohort or recorded artifact hash")
    train_worlds = [entry["name"] for entry in cohort["worlds"] if entry["role"] == "train"]
    if metadata["train_worlds"] != train_worlds:
        raise ValueError("T1 model metadata has a different training split")

    model = t1.HazardGBM(feats=metadata["features"])
    model.booster = lgb.Booster(model_file=str(model_path))
    if model.booster.feature_name() != model.feats + t1.WEEK_FEATS:
        raise ValueError("T1 model feature order differs from current inference code")

    prediction_parts = []
    world_rows = []
    for entry in cohort["worlds"]:
        world = entry["name"]
        directory = SYNTH / world
        config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
        if not pd.Timestamp(config["start"]) <= cutoff <= pd.Timestamp(config["end"]):
            raise ValueError(f"{world}: as_of outside data window")
        builder = SnapshotBuilder(
            pd.read_parquet(directory / "invoices.parquet"),
            pd.read_parquet(directory / "payments.parquet"),
            pd.read_parquet(directory / "promises.parquet"),
        )
        frame = builder.model_snapshot(cutoff)
        if frame.empty:
            world_rows.append({"world": world, "role": entry["role"], "n_open": 0,
                               "amount_open": 0.0})
            continue
        if frame["invoice_id"].duplicated().any():
            raise ValueError(f"{world}: duplicate invoice_id in open snapshot")

        hazards = model.hazards(frame)
        quantiles = t1.quantiles_from_hazard(hazards)
        _, survival = t1.pmf_from_hazard(hazards)
        predicted = frame[["invoice_id", "firm_id", "customer_id", "issue_date",
                           "due_date", "amount_gross", "amount_open"]].copy()
        predicted.insert(0, "role", entry["role"])
        predicted.insert(0, "world", world)
        predicted.insert(2, "as_of", cutoff)
        predicted["q10_days"] = quantiles[:, 0]
        predicted["q50_days"] = quantiles[:, 1]
        predicted["q90_days"] = quantiles[:, 2]
        for name in ("q10", "q50", "q90"):
            predicted[f"{name}_capped"] = predicted[f"{name}_days"].ge(t1.CAP)
        predicted["p_paid_4w"] = 1 - survival[:, 3]
        predicted["p_paid_13w"] = 1 - survival[:, -1]
        predicted["q50_date"] = cutoff + pd.to_timedelta(np.ceil(quantiles[:, 1]), unit="D")
        predicted.loc[predicted["q50_capped"], "q50_date"] = pd.NaT
        numeric = predicted[["q10_days", "q50_days", "q90_days", "p_paid_4w", "p_paid_13w"]]
        if not np.isfinite(numeric.to_numpy()).all() or not (
            (predicted["q10_days"] <= predicted["q50_days"]) &
            (predicted["q50_days"] <= predicted["q90_days"]) &
            predicted["p_paid_4w"].between(0, 1) & predicted["p_paid_13w"].between(0, 1) &
            (predicted["p_paid_4w"] <= predicted["p_paid_13w"])
        ).all():
            raise ValueError(f"{world}: invalid inference output")
        prediction_parts.append(predicted)
        world_rows.append({"world": world, "role": entry["role"],
                           "n_open": int(len(predicted)),
                           "amount_open": float(predicted["amount_open"].sum()),
                           "q50_days_median": float(predicted["q50_days"].median()),
                           "p_paid_4w_mean": float(predicted["p_paid_4w"].mean()),
                           "p_paid_13w_mean": float(predicted["p_paid_13w"].mean())})
        print(f"{world}: {len(predicted):,} open invoices", flush=True)

    if not prediction_parts:
        raise ValueError("No open invoices to infer")
    predictions = pd.concat(prediction_parts, ignore_index=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = output_dir / "predictions.csv"
    worlds_path = output_dir / "world_summary.csv"
    predictions.to_csv(predictions_path, index=False, date_format="%Y-%m-%d")
    pd.DataFrame(world_rows).to_csv(worlds_path, index=False)
    current = code_provenance()
    summary = {
        "as_of": str(cutoff.date()), "cohort": str(cohort_path),
        "cohort_sha256": cohort_hash, "model": str(model_path),
        "model_sha256": model_hash, "model_name": "DH-GBM",
        "prediction_horizon_weeks": t1.K, "quantile_cap_days": t1.CAP,
        "worlds": len(world_rows), "n_open": int(len(predictions)),
        "amount_open": float(predictions["amount_open"].sum()),
        "n_q50_capped": int(predictions["q50_capped"].sum()),
        "n_q90_capped": int(predictions["q90_capped"].sum()),
        "p_paid_4w_mean": float(predictions["p_paid_4w"].mean()),
        "p_paid_13w_mean": float(predictions["p_paid_13w"].mean()),
        "predictions_sha256": sha256_file(predictions_path),
        "world_summary_sha256": sha256_file(worlds_path),
        "current_code_provenance": current,
        "code_matches_training": current["source_code_sha256"] == metadata["source_code_sha256"],
        "git_commit_matches_training": current["commit"] == metadata["commit"],
        "scope": "Synthetic open invoices only; no real-business performance claim",
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--as-of", default="2025-12-31")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    destination = args.output_dir or OUT / "t1" / f"v3_final_20261027_inference_{args.as_of}"
    print(json.dumps(infer(args.cohort, args.model_dir, destination, args.as_of),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
