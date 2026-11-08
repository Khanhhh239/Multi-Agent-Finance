"""Evaluate the already selected Nov-05 candidate against saved Khanh predictions.

No fitting, calibration, candidate selection, or service registration occurs.
The research freeze is written BEFORE reading evaluation outcomes.
"""
from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import time

import lightgbm as lgb
import numpy as np
import pandas as pd

from analysis.benchmark_t1_khanh_vs_v6 import (
    ROOT, DAYS, V6, bootstrap_difference, probability_score, restricted_score,
    sha, write_csv, write_json,
)
from experiments.t1_competing_v6.core import observed_state, paid_quantiles, state_at_day
from experiments.t1_competing_v6.metrics import score
from experiments.t1_competing_v6.run import build_frame, load_world
from experiments.t1_v6_practical.model import ARMS, predict_hazards
from experiments.t1_v6_practical.sidecars import OBSERVATION_DESIGN, build_features

BASE = ROOT / "outputs/analysis/t1_khanh_vs_v6_20261105"
PRACTICAL = ROOT / "outputs/data/t1_v6_practical_20261105_r2"
DEFAULT = ROOT / "outputs/analysis/t1_v6_final_vs_khanh_20261105"
KEYS = ["world", "invoice_id", "firm_id", "cutoff"]
LABELS = ["time_days", "cause", "obs_days", "amount_open"]
FINAL_SHA = "c7d51abf10fb0e692f98c928966680a1140de64bb7617959e467d47a60dfea50"


def validate_pair(frame, saved):
    """Reject reordered, substituted, censored, or differently labeled anchors."""
    if len(frame) != len(saved) or not frame[KEYS].equals(saved[KEYS]):
        raise ValueError("Paired anchor keys/order changed")
    if frame.duplicated(KEYS).any() or frame.obs_days.lt(max(DAYS)).any():
        raise ValueError("Duplicate or insufficiently observed anchors")
    for column in LABELS:
        if not np.array_equal(frame[column].to_numpy(), saved[column].to_numpy()):
            raise ValueError(f"Paired outcome changed: {column}")


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    prior = json.loads((BASE / "protocol.lock.json").read_text(encoding="utf-8"))
    selected = json.loads((PRACTICAL / "final_selection.lock.json").read_text(encoding="utf-8"))
    meta = json.loads((PRACTICAL / "models/both.json").read_text(encoding="utf-8"))
    if selected["selected"] != "both" or selected["models_sha256"]["both"] != FINAL_SHA:
        raise ValueError("Candidate differs from the prior source-only selection")
    if sha(PRACTICAL / "models/both.txt") != FINAL_SHA or meta["features"] != ARMS["both"]:
        raise ValueError("Candidate model/feature order changed")
    protected = dict(prior["protected"])
    # Retain the complete previously protected population plus all reused evidence.
    for path in sorted(BASE.rglob("*")):
        if path.is_file():
            protected[path.relative_to(ROOT).as_posix()] = sha(path)
    for folder in (ROOT / "experiments/t1_v6_practical", ROOT / "experiments/t1_credit_context"):
        for path in sorted(folder.glob("*.py")):
            protected[path.relative_to(ROOT).as_posix()] = sha(path)
    for path in (PRACTICAL / "models/both.txt", PRACTICAL / "models/both.json",
                 PRACTICAL / "final_selection.lock.json", PRACTICAL / "protocol.lock.json",
                 PRACTICAL / "source_snapshot.zip", PRACTICAL / "fresh_scores.csv",
                 PRACTICAL / "fresh_bootstrap.csv", V6 / "train.json"):
        protected[path.relative_to(ROOT).as_posix()] = sha(path)
    for relative, digest in protected.items():
        if sha(ROOT / relative) != digest:
            raise ValueError(f"Changed protected input: {relative}")
    protocol = {
        "scope": "retrospective evaluation of fixed Nov-05 candidate; no selection or fitting",
        "entries": prior["entries"], "days": list(DAYS), "eval_label_end": prior["eval_label_end"],
        "primary": prior["primary"], "baseline": prior["baseline"],
        "baseline_predictions": str(BASE.relative_to(ROOT) / "predictions"),
        "candidate": "V6 + industry + ledger behavior (both), 2026-11-05",
        "candidate_sha256": FINAL_SHA, "features": ARMS["both"],
        "calibration": "identity; no calibration fit in this evaluation",
        "observation_design": OBSERVATION_DESIGN,
        "observation_warning": "new features use the previously locked synthetic ERP observation process, not verified SME records; original 64 baseline features retain their original assumptions",
        "cash_policy": "no new cash head; Nov-01 cash metrics remain historical",
        "decision_policy": "research candidate fixed by user instruction and previous source selection before this evaluation; do not reselect using these Worlds",
        "bootstrap": "1000 paired company draws within each fixed World; then equal-World average; no uncertainty across new economies",
        "protected": protected, "script_sha256": sha(Path(__file__)),
        "prior_benchmark_protocol_sha256": sha(BASE / "protocol.lock.json"),
        "source_selection_sha256": sha(PRACTICAL / "final_selection.lock.json"),
    }
    write_json(output / "protocol.lock.json", protocol)
    write_json(output / "research_candidate.lock.json", {
        "name": "T1 V6 practical 2026-11-05", "status": "frozen_research_candidate",
        "model_path": str((PRACTICAL / "models/both.txt").relative_to(ROOT)),
        "model_sha256": FINAL_SHA, "features": ARMS["both"], "weekly_features": 7,
        "weeks": 53, "calibration": "identity", "active_causes": [0, 1, 2],
        "selection": "existing source-only selection; frozen before this retrospective comparison",
        "cash_head": "not included in this candidate freeze",
        "service_activated": False, "product_gate_status_changed": False,
        "limitations": ["synthetic evidence", "not all research criteria passed on prior fresh Worlds",
                        "original baseline observation assumptions remain", "not a production acceptance"],
        "protocol_sha256": sha(output / "protocol.lock.json"),
    })
    return protocol


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT)
    args = parser.parse_args()
    output = args.output.resolve()
    protocol = prepare(output)
    model = lgb.Booster(model_file=str(PRACTICAL / "models/both.txt"))
    active = json.loads((V6 / "train.json").read_text(encoding="utf-8"))["active_causes"]
    policy = json.loads((V6 / "protocol.lock.json").read_text(encoding="utf-8"))
    cutoffs = pd.date_range(policy["eval_first_cutoff"], policy["eval_last_cutoff"], freq=f"{policy['eval_stride_days']}D")
    for folder in ("predictions", "features"):
        (output / folder).mkdir()
    rows, primary_rows, boot_rows, q_rows, coverage, slices = [], [], [], [], [], []
    primary_draws, relative_draws = [], []
    old_q = pd.read_csv(BASE / "quantiles_restricted120.csv")
    for index, entry in enumerate(protocol["entries"]):
        world, role = entry["name"], entry["role"]
        start = time.monotonic()
        print(f"Evaluate frozen Nov-05 candidate: {world}", flush=True)
        saved = pd.read_parquet(BASE / "predictions" / f"{world}.parquet")
        builder, receipts = load_world(world)
        frame = build_frame(builder, world, cutoffs, protocol["eval_label_end"])
        frame = frame.sort_values(["cutoff", "invoice_id"]).drop_duplicates("invoice_id").reset_index(drop=True)
        validate_pair(frame, saved)
        del builder, receipts
        extra = build_features(ROOT / "data/synthetic" / world, frame)
        if list(extra) != ARMS["both"][64:] or len(extra) != len(frame):
            raise ValueError("Unexpected added feature schema or alignment")
        exported_features = pd.concat([frame[KEYS + ["customer_id"]], extra], axis=1)
        exported_features.to_parquet(output / "features" / f"{world}.parquet", index=False)
        for column in extra:
            coverage.append({"world": world, "feature": column, "n": len(frame),
                             "missing_fraction": float(extra[column].isna().mean())})
        frame = pd.concat([frame, extra], axis=1)
        hazards = predict_hazards(model, frame, ARMS["both"], active)
        exported = saved.copy()
        primary_old, primary_new, primary_original = [], [], []
        for day in DAYS:
            states = state_at_day(hazards, day)
            truth = observed_state(frame, day) == 1
            old, original = saved[f"khanh_refit_paid_{day}"].to_numpy(), saved[f"v6_paid_{day}"].to_numpy()
            new = states[:, 1]
            for label, p in (("khanh_refit", old), ("v6_original", original), ("v6_final", new)):
                result = probability_score(truth, p)
                if label == "v6_final":
                    joint = score(frame, states, day)
                    result.update({k: joint[k] for k in ("four_state_brier", "writeoff_brier", "writeoff_gap", "pred_writeoff", "actual_writeoff")})
                rows.append({"world": world, "role": role, "model": label, "day": day, **result})
            exported[f"v6_final_paid_{day}"] = new
            exported[f"v6_final_writeoff_{day}"] = states[:, 2]
            exported[f"v6_final_open_{day}"] = states[:, 0]
            difference = (new - truth) ** 2 - (old - truth) ** 2
            ci, _ = bootstrap_difference(frame, difference, 261105 + index * 100 + day)
            boot_rows.append({"world": world, "role": role, "day": day, **ci})
            if day in (28, 91):
                primary_old.append((old - truth) ** 2)
                primary_original.append((original - truth) ** 2)
                primary_new.append((new - truth) ** 2)
        error_old, error_original, error_new = [np.mean(x, axis=0) for x in (primary_old, primary_original, primary_new)]
        ci, draws = bootstrap_difference(frame, error_new - error_old, 261105 + index)
        primary_draws.append(draws)
        ci_original, draws_original = bootstrap_difference(frame, error_new - error_original, 261105 + index)
        relative_draws.append(draws_original)
        primary_rows.append({"world": world, "role": role, "n": len(frame),
            "khanh_primary": float(error_old.mean()), "original_primary": float(error_original.mean()),
            "final_primary": float(error_new.mean()), "improvement_pct": float(100 * (1 - error_new.mean() / error_old.mean())),
            **ci, "delta_vs_original": float((error_new - error_original).mean()),
            "vs_original_ci_low": ci_original["ci_low"], "vs_original_ci_high": ci_original["ci_high"]})
        quantiles = pd.DataFrame(paid_quantiles(hazards))
        q_rows.append({"world": world, "role": role, "model": "v6_final", "n": len(frame),
                       **restricted_score(frame, quantiles[["q10_days", "q50_days", "q90_days"]].to_numpy())})
        for column in quantiles:
            exported[column] = quantiles[column]
        exported.to_parquet(output / "predictions" / f"{world}.parquet", index=False)
        # Descriptive overdue/calendar slices; same definition as the earlier report.
        inv = pd.read_parquet(ROOT / "data/synthetic" / world / "invoices.parquet", columns=["firm_id", "invoice_id", "due_date"])
        detail = exported.merge(inv, on=["firm_id", "invoice_id"], how="left", validate="one_to_one")
        if detail.due_date.isna().any():
            raise ValueError("Missing due date in descriptive slices")
        dpd = (detail.cutoff - detail.due_date).dt.days
        detail["overdue_group"] = pd.cut(dpd, [-np.inf, 0, 30, 90, 180, np.inf], labels=["not_overdue", "1_30", "31_90", "91_180", "over_180"])
        detail["anchor_month"] = detail.cutoff.dt.month
        for dimension in ("overdue_group", "anchor_month"):
            for group, part in detail.groupby(dimension, observed=True):
                result = {"world": world, "dimension": dimension, "group": str(group), "n": len(part)}
                for label, prefix in (("khanh", "khanh_refit"), ("final", "v6_final")):
                    losses = []
                    for day in (28, 91, 365):
                        y = ((part.cause == 1) & (part.time_days <= day)).to_numpy(float)
                        loss = (part[f"{prefix}_paid_{day}"].to_numpy() - y) ** 2
                        result[f"{label}_brier_{day}"] = float(loss.mean())
                        if day in (28, 91):
                            losses.append(loss)
                    result[f"{label}_primary"] = float(np.mean(losses))
                slices.append(result)
        print(f"  {len(frame):,} anchors; primary Khanh {error_old.mean():.6f}, Nov-05 {error_new.mean():.6f}; {time.monotonic()-start:.1f}s", flush=True)
        del frame, extra, exported_features, hazards, exported, detail, inv, saved
        gc.collect()
    scores, primary = pd.DataFrame(rows), pd.DataFrame(primary_rows)
    aggregate = []
    for (label, day), part in scores.groupby(["model", "day"]):
        fields = [k for k in part.select_dtypes(include="number") if k not in ("day", "n")]
        aggregate.append({"model": label, "day": int(day), "n": int(part.n.sum()),
                          **{k: float(part[k].mean()) for k in fields if part[k].notna().all()}})
    slices = pd.DataFrame(slices)
    slice_aggregate = slices.groupby(["dimension", "group"], as_index=False).agg(
        n=("n", "sum"), worlds=("world", "count"), khanh_primary=("khanh_primary", "mean"), final_primary=("final_primary", "mean"),
        khanh_brier365=("khanh_brier_365", "mean"), final_brier365=("final_brier_365", "mean"))
    slice_aggregate["primary_improvement_pct"] = 100 * (1 - slice_aggregate.final_primary / slice_aggregate.khanh_primary)
    slice_aggregate["brier365_improvement_pct"] = 100 * (1 - slice_aggregate.final_brier365 / slice_aggregate.khanh_brier365)
    q_rows = pd.concat([old_q.assign(model=old_q.model.replace({"v6": "v6_original"})), pd.DataFrame(q_rows)], ignore_index=True)
    for name, data in (("scores.csv", scores), ("aggregate_scores.csv", pd.DataFrame(aggregate)),
                       ("primary_by_world.csv", primary), ("bootstrap.csv", pd.DataFrame(boot_rows)),
                       ("quantiles_restricted120.csv", q_rows), ("feature_missingness.csv", pd.DataFrame(coverage)),
                       ("slices_by_world.csv", slices), ("slices_equal_world.csv", slice_aggregate)):
        write_csv(output / name, data)
    a, b, c = primary[["khanh_primary", "original_primary", "final_primary"]].mean()
    low, high = np.quantile(np.mean(primary_draws, axis=0), [.025, .975])
    lo_original, hi_original = np.quantile(np.mean(relative_draws, axis=0), [.025, .975])
    if primary.n.sum() != 65221 or len(primary) != 6:
        raise ValueError("Benchmark population changed")
    summary = {"anchors": int(primary.n.sum()), "worlds": len(primary), "candidate_sha256": FINAL_SHA,
        "primary": {"khanh": a, "v6_original": b, "v6_final": c, "improvement_vs_khanh_pct": 100 * (1 - c / a),
                    "delta_vs_khanh": c - a, "ci_low": low, "ci_high": high,
                    "improvement_vs_original_pct": 100 * (1 - c / b), "delta_vs_original": c - b,
                    "vs_original_ci_low": lo_original, "vs_original_ci_high": hi_original},
        "worlds_final_better_than_khanh": int((primary.final_primary < primary.khanh_primary).sum()),
        "weights": "equal weight per fixed World", "scope": protocol["scope"],
        "research_candidate_frozen_before_evaluation": True, "fitted": False, "service_changed": False}
    write_json(output / "summary.json", summary)
    changed = [r for r, h in protocol["protected"].items() if sha(ROOT / r) != h]
    if changed:
        raise ValueError(f"Protected inputs changed: {changed}")
    outputs = {p.relative_to(output).as_posix(): sha(p) for p in output.rglob("*") if p.is_file()}
    write_json(output / "verification.json", {
        "protected_files_checked": len(protocol["protected"]), "changed_protected_files": changed,
        "same_anchors_order_labels_amounts": True, "baseline_predictions_reused": True,
        "candidate_fixed_before_evaluation": True, "no_fit_or_calibration": True,
        "result_sha256": outputs, "cash_head_retrained": False,
    })
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
