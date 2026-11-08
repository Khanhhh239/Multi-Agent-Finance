"""Evaluate a locked T1 cohort without turning censored outcomes into payments.

The evaluator is outside agent1/ and scripts/ so an existing training source hash
remains reproducible. It only reads validation/test Worlds and the saved model.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent1.data.world_manifest import code_provenance, load_cohort, sha256_file  # noqa: E402
from agent1.models import t1  # noqa: E402
from agent1.paths import OUT, SYNTH  # noqa: E402
from scripts.train_manifest import _rows  # noqa: E402


DEFAULT_COHORT = SYNTH / "v4_shortpay_4shock_20261028_cohort.json"
DEFAULT_MODEL_DIR = OUT / "data/v4_shortpay_4shock_20261028"


def probability_metrics(remaining: np.ndarray, probability: np.ndarray,
                        horizon: int) -> tuple[dict, list[dict]]:
    """Full-follow-up binary outcome at horizon; inf means no payment by then."""
    rem = np.asarray(remaining, dtype=float)
    p = np.asarray(probability, dtype=float)
    if len(rem) != len(p) or not len(p) or not np.isfinite(p).all() or \
            ((p < 0) | (p > 1)).any() or np.isnan(rem).any():
        raise ValueError("Invalid probability evaluation inputs")
    y = (rem <= horizon).astype(float)
    clip = np.clip(p, 1e-12, 1 - 1e-12)
    bins = np.minimum((p * 10).astype(int), 9)
    table = []
    for idx in range(10):
        mask = bins == idx
        if mask.any():
            table.append({"bin": idx, "n": int(mask.sum()),
                          "predicted_mean": float(p[mask].mean()),
                          "observed_rate": float(y[mask].mean())})
    ece = sum(row["n"] / len(p) * abs(row["predicted_mean"] - row["observed_rate"])
              for row in table)
    event_rate = float(y.mean())
    metrics = {"horizon_days": horizon, "n": len(p),
               "n_paid_by_horizon": int(y.sum()), "observed_rate": event_rate,
               "predicted_mean": float(p.mean()),
               "calibration_gap": float(p.mean() - event_rate),
               "brier": float(np.mean((p - y) ** 2)),
               "brier_climatology_reference": float(event_rate * (1 - event_rate)),
               "log_loss": float(np.mean(-(y * np.log(clip) + (1 - y) * np.log(1 - clip)))),
               "ece10": float(ece),
               "auc": float(roc_auc_score(y, p)) if 0 < y.sum() < len(y) else None}
    return metrics, table


def quantile_metrics(remaining: np.ndarray, quantiles: np.ndarray,
                     horizon: int) -> dict:
    """CDF crossing for finite quantiles; exact-time loss only for resolved rows."""
    rem = np.asarray(remaining, dtype=float)
    q = np.asarray(quantiles, dtype=float)
    if q.shape != (len(rem), 3) or not np.isfinite(q).all() or \
            (q[:, 0] > q[:, 1]).any() or (q[:, 1] > q[:, 2]).any() or \
            np.isnan(rem).any():
        raise ValueError("Invalid quantile evaluation inputs")
    if (q > horizon).any():
        raise ValueError("Quantile exceeds the available follow-up")
    resolved = rem <= horizon
    answer = {"n": int(len(rem)), "n_resolved_by_horizon": int(resolved.sum()),
              "resolved_share": float(resolved.mean()),
              "selection_warning": "Exact-time losses condition on payment by horizon"}
    for idx, level in enumerate(t1.QS):
        finite = q[:, idx] < horizon
        crossing = rem[finite] <= q[finite, idx]
        error = rem[resolved] - q[resolved, idx]
        answer[f"q{int(level * 100)}"] = {
            "n_finite": int(finite.sum()), "n_capped": int((~finite).sum()),
            "finite_fraction": float(finite.mean()),
            "observed_cdf_at_finite_quantile": float(crossing.mean()) if finite.any() else None,
            "target_cdf": float(level),
            "cdf_gap": float(crossing.mean() - level) if finite.any() else None,
            "resolved_only_pinball": float(np.maximum(level * error, (level - 1) * error).mean())
            if resolved.any() else None,
        }
    finite_interval = q[:, 2] < horizon
    covered = (rem >= q[:, 0]) & (rem <= q[:, 2])
    legacy_covered = (np.minimum(rem, horizon) >= q[:, 0]) & \
        (np.minimum(rem, horizon) <= q[:, 2])
    false_censor_hits = legacy_covered & ~covered
    answer["finite_q10_q90_interval"] = {
        "n": int(finite_interval.sum()),
        "observed_coverage": float(covered[finite_interval].mean())
        if finite_interval.any() else None,
        "nominal_coverage": .8,
        "scope": "Only rows with Q90 below horizon; not full-cohort coverage",
    }
    answer["capped_q90_paid_by_horizon_rate"] = float(resolved[~finite_interval].mean()) \
        if (~finite_interval).any() else None
    answer["numeric_interval_hit_by_horizon"] = float(covered.mean())
    answer["legacy_clipped_label_coverage"] = float(legacy_covered.mean())
    answer["legacy_false_hits_from_censoring"] = int(false_censor_hits.sum())
    return answer


def evaluate(cohort_path: Path, model_dir: Path, output_dir: Path) -> dict:
    cohort_path, model_dir, output_dir = map(Path, (cohort_path, model_dir, output_dir))
    cohort = load_cohort(cohort_path)
    metadata = json.loads((model_dir / "train.json").read_text(encoding="utf-8"))
    model_path = model_dir / "model.txt"
    if metadata["cohort_sha256"] != sha256_file(cohort_path) or \
            metadata["model_sha256"] != sha256_file(model_path):
        raise ValueError("Model or cohort differs from the locked training artifacts")
    current = code_provenance()
    if current["source_code_sha256"] != metadata["source_code_sha256"] or \
            current["commit"] != metadata["commit"]:
        raise ValueError("Training source code changed; restore the source snapshot first")
    model = t1.HazardGBM(feats=metadata["features"])
    model.booster = lgb.Booster(model_file=str(model_path))
    if model.booster.feature_name() != model.feats + t1.WEEK_FEATS:
        raise ValueError("Feature order mismatch")
    horizon = int(cohort["split_protocol"]["label_horizon_days"])
    if horizon != int(t1.CAP) or horizon < 91:
        raise ValueError("This evaluator requires complete 120-day follow-up")
    rows, bins = [], []
    for entry in cohort["worlds"]:
        role = entry["role"]
        if role == "train":
            continue
        world = entry["name"]
        frame = _rows(SYNTH / world, cohort["split_protocol"]["origin"],
                      role=role, protocol=cohort["split_protocol"])
        if (frame.obs_window < horizon).any():
            raise ValueError(f"{world}: some labels lack full {horizon}-day follow-up")
        H = model.hazards(frame)
        _, survival = t1.pmf_from_hazard(H)
        rem = frame.remaining.to_numpy(dtype=float)
        q = t1.quantiles_from_hazard(H)
        qm = quantile_metrics(rem, q, horizon)
        world_result = {"world": world, "role": role, "n": int(len(frame)),
                        "n_unique_invoices": int(frame.invoice_id.nunique()),
                        "min_followup_days": float(frame.obs_window.min()),
                        "quantiles": qm}
        for week, days in ((4, 28), (13, 91)):
            metrics, reliability = probability_metrics(rem, 1 - survival[:, week - 1], days)
            world_result[f"probability_{week}w"] = metrics
            bins.extend({"world": world, "role": role, "horizon_weeks": week, **item}
                        for item in reliability)
        rows.append(world_result)
        print(f"{world}: {len(frame):,} snapshots", flush=True)
    if not rows:
        raise ValueError("No validation/test Worlds")
    report = {
        "protocol": "complete 120-day follow-up; binary Brier/logloss/AUC/ECE10; finite-quantile CDF crossing; resolved-only pinball",
        "cohort": str(cohort_path.relative_to(ROOT)),
        "cohort_sha256": metadata["cohort_sha256"],
        "model_sha256": metadata["model_sha256"],
        "training_source_code_sha256": metadata["source_code_sha256"],
        "evaluator_sha256": sha256_file(Path(__file__)),
        "label_horizon_days": horizon,
        "worlds": rows,
        "limits": ["Synthetic only", "Repeated invoice snapshots are correlated",
                   "Capped quantiles are not exact 120-day payment dates",
                   "Resolved-only pinball excludes invoices still open at day 120",
                   "No long-horizon Q90 validation from 120-day follow-up"],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                               encoding="utf-8")
    pd.DataFrame(bins).to_csv(output_dir / "reliability_bins.csv", index=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--output-dir", type=Path,
                        default=DEFAULT_MODEL_DIR / "censor_aware_evaluation_20261028")
    args = parser.parse_args()
    report = evaluate(args.cohort, args.model_dir, args.output_dir)
    print(json.dumps({"worlds": len(report["worlds"]),
                      "results": str(args.output_dir / "results.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
