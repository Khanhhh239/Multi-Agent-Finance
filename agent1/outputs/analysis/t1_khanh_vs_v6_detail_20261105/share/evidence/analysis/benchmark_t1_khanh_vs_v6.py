"""Paired, retrospective comparison of Khanh's native T1 and frozen V6.

The old estimator is refit from an isolated Git snapshot on exactly V6's fit
anchors. This is a model-version comparison, not recovery of a pushed booster.
The common 46 input features use the same V6 snapshot values in both arms.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import types

import lightgbm as lgb
import numpy as np
import pandas as pd

from experiments.t1_competing_v6 import calibration
from experiments.t1_competing_v6.core import PAID, observed_state, predict_cash_fraction, predict_hazards, state_at_day
from experiments.t1_competing_v6.features import V6_FEATURES
from experiments.t1_competing_v6.metrics import cash_score, reliability
from experiments.t1_competing_v6.run import build_frame, load_world

ROOT = Path(__file__).resolve().parents[1]
V6 = ROOT / "outputs/data/t1_competing_v6_20261101"
DEFAULT_OUTPUT = ROOT / "outputs/analysis/t1_khanh_vs_v6_20261105"
COMMIT = "70c0ceb0653161f70535b4c8b9fb3cee63b7405f"
V6_SHA = "9375373bcf413618642cb12f39c7d9a63bb5f24bac24a7c64b9e2eb54f95db44"
DAYS = (28, 91, 120, 180, 270, 365)
CASH_DAYS = (28, 91, 180, 365)
LEGACY_FILES = ("__init__.py", "threads.py", "calendar_vn.py", "models/__init__.py",
                "models/features.py", "models/t1.py", "rules/__init__.py", "rules/rules_history.json")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def write_csv(path, frame):
    with Path(path).open("x", encoding="utf-8", newline="") as stream:
        frame.to_csv(stream, index=False, lineterminator="\n")


def old_module(output):
    """Import only the archived implementation and its archived local dependencies."""
    prefix = "_khanh_t1_70c0ceb"
    if prefix not in sys.modules:
        package = types.ModuleType(prefix)
        package.__path__ = [str(Path(output) / "legacy" / "agent1")]
        sys.modules[prefix] = package
    return importlib.import_module(prefix + ".models.t1")


def paid_cdf(hazards, day):
    h = np.asarray(hazards, float)
    if h.ndim != 2 or h.shape[1] != 13 or not np.isfinite(h).all() or np.any((h < 0) | (h >= 1)):
        raise ValueError("Expected native 13-week binary hazards")
    if day <= 0 or (day <= 91 and day % 7):
        raise ValueError("Use week ends through day 91, or geometric-tail horizons")
    survival = np.cumprod(1 - h, axis=1)
    if day <= 91:
        return 1 - survival[:, day // 7 - 1]
    tail = np.clip(h[:, -4:].mean(axis=1), .02, .6)
    return 1 - survival[:, -1] * (1 - tail) ** ((day - 91) / 7)


def legacy_labels(module, frame, label_end):
    features = importlib.import_module(module.__package__ + ".features")
    return features.add_labels(frame, label_end)


def probability_score(truth, probability):
    y, p = np.asarray(truth, float), np.asarray(probability, float)
    if y.shape != p.shape or not len(y) or not np.isin(y, [0, 1]).all() or not np.isfinite(p).all() or np.any((p < 0) | (p > 1)):
        raise ValueError("Invalid paired binary observations")
    return {"n": len(y), "actual_paid": float(y.mean()), "pred_paid": float(p.mean()),
            "paid_gap": float((p - y).mean()), "paid_brier": float(((p - y) ** 2).mean()),
            "paid_ece": reliability(p, y)[0]}


def restricted_score(frame, quantiles, cap=120):
    """Proper quantile scores for min(time-to-paid,120), including never paid."""
    times = (pd.to_datetime(frame.label_date) - frame.cutoff).dt.days.to_numpy(float)
    target = np.minimum(np.where(np.isfinite(times), times, np.inf), cap)
    q = np.clip(np.nan_to_num(np.asarray(quantiles, float), nan=cap), 0, cap)
    if q.shape != (len(frame), 3) or not np.isfinite(q).all() or np.any(np.diff(q, axis=1) < -1e-7):
        raise ValueError("Invalid restricted quantiles")
    error = target[:, None] - q
    alphas = np.array([.1, .5, .9])
    loss = np.maximum(alphas * error, (alphas - 1) * error).mean(axis=1)
    return {"restricted_pinball120": float(loss.mean()),
            "restricted_median_mae120": float(np.abs(error[:, 1]).mean())}


def bootstrap_difference(frame, difference, seed, replicates=1000):
    groups = pd.DataFrame({"firm": frame.firm_id.to_numpy(), "d": difference}).groupby("firm").d.agg(["sum", "count"])
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(groups), size=(replicates, len(groups)))
    sampled = groups["sum"].to_numpy()[draws].sum(axis=1) / groups["count"].to_numpy()[draws].sum(axis=1)
    low, high = np.quantile(sampled, [.025, .975])
    return {"firms": len(groups), "delta_v6_minus_khanh": float(np.mean(difference)),
            "ci_low": float(low), "ci_high": float(high), "replicates": replicates}, sampled


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    if sha(V6 / "model.txt") != V6_SHA:
        raise ValueError("Frozen V6 model changed")
    cohort_path = ROOT / "data/synthetic/v4_shortpay_4shock_20261028_cohort.json"
    cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
    entries = [{"name": e["name"], "role": e["role"]} for e in cohort["worlds"] if e["role"] != "train"]
    entries += json.loads((V6 / "fresh_holdout_registry.json").read_text(encoding="utf-8"))
    caches = [V6 / "cache" / f"train_{e['name']}.parquet" for e in cohort["worlds"] if e["role"] == "train"]
    protected = [cohort_path, V6 / "model.txt", V6 / "cash_model.txt", V6 / "calibration.json", V6 / "train.json", V6 / "protocol.lock.json"]
    protected += caches + [p.with_suffix(".json") for p in caches]
    protected += sorted((ROOT / "experiments/t1_competing_v6").glob("*.py"))
    protected += [ROOT / "agent1/models/t1.py", ROOT / "agent1/models/features.py"]
    for e in entries:
        protected += [V6 / "evaluation_predictions" / f"{e['name']}.parquet"]
        protected += sorted((ROOT / "data/synthetic" / e["name"]).glob("*.parquet"))
    locks = {p.relative_to(ROOT).as_posix(): sha(p) for p in protected}
    legacy = {}
    for name in LEGACY_FILES:
        data = subprocess.check_output(["git", "show", f"{COMMIT}:agent1/{name}"], cwd=ROOT)
        path = output / "legacy/agent1" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        legacy[name] = sha(path)
    old = old_module(output)
    model = old.HazardGBM(params={"num_threads": 4})
    protocol = {"commit": COMMIT, "baseline": "native HazardGBM default refit; not recovered pushed booster",
                "common_input": "exact same V6 fit anchors/order and values of the common 46 features; not a full replay of old ingestion",
                "baseline_features": old.FEATURES, "baseline_week_features": old.WEEK_FEATS,
                "baseline_parameters": model.p, "baseline_rounds": model.rounds,
                "baseline_training_labels": "exact legacy add_labels; write-off remains a non-paid observation through label end",
                "fit_n": 200000, "fit_caches": [p.relative_to(ROOT).as_posix() for p in caches],
                "train_label_end": "2024-07-01", "eval_label_end": "2025-12-31",
                "entries": entries, "days": DAYS,
                "primary": "Paid Brier mean of days 28 and 91; equal weight per World",
                "secondary": "Paid Brier/ECE at each day; native geometric extrapolation beyond91 explicitly labeled; restricted quantile scores120; cash head vs native T1 full-payment proxy",
                "writeoff_policy": "no zero-padding or comparison of legacy cure with finite-horizon Write-off",
                "evaluation_scope": "retrospective paired benchmark; every evaluation World has already been inspected; not fresh confirmation",
                "selection": "none; native defaults and frozen V6; no test-based tuning",
                "v6_model_sha256": V6_SHA, "protected": locks, "legacy_sha256": legacy,
                "script_sha256": sha(Path(__file__)), "python": platform.python_version(),
                "packages": {k: importlib.metadata.version(k) for k in ("numpy", "pandas", "lightgbm", "pyarrow")}}
    if old.K != 13 or len(old.FEATURES) != 46 or not old.FULL_WEEK_ONLY:
        raise ValueError("Unexpected archived T1 configuration")
    write_json(output / "protocol.lock.json", protocol)
    return protocol


def fit(output, protocol):
    old = old_module(output)
    parts = []
    for relative in protocol["fit_caches"]:
        path = ROOT / relative
        if sha(path) != protocol["protected"][relative]:
            raise ValueError("Changed fit cache")
        metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        if sha(path) != metadata["cache_sha256"]:
            raise ValueError("V6 cache disagrees with original manifest")
        frame = pd.read_parquet(path)
        parts.append(frame.loc[frame.partition.eq("fit")].copy())
    frame = pd.concat(parts, ignore_index=True)
    if len(frame) != protocol["fit_n"] or set(frame.partition) != {"fit"}:
        raise ValueError("Wrong fit population")
    frame = legacy_labels(old, frame, protocol["train_label_end"])
    print(f"Training archived T1: {len(frame):,} snapshots, {frame.firm_id.groupby(frame.world).nunique().sum()} firms; 600 rounds", flush=True)
    start = time.monotonic()
    model = old.HazardGBM(params={"num_threads": 4})
    # Native parameters, feature order, labels and expand() are executed unchanged.
    model.fit(frame)
    model_path = output / "khanh_refit_model.txt"
    model.booster.save_model(str(model_path))
    write_json(output / "train.json", {"model_sha256": sha(model_path), "fit_n": len(frame),
               "fit_firms": int(frame.groupby("world").firm_id.nunique().sum()),
               "unique_invoices": int(frame[["world", "invoice_id"]].drop_duplicates().shape[0]),
               "parameters": model.p, "rounds": model.rounds, "feature_names": model.booster.feature_name(),
               "seconds": time.monotonic() - start, "protocol_sha256": sha(output / "protocol.lock.json")})
    print(f"T1 trained in {time.monotonic() - start:.1f}s", flush=True)


def evaluate(output, protocol):
    meta = json.loads((output / "train.json").read_text(encoding="utf-8"))
    if sha(output / "khanh_refit_model.txt") != meta["model_sha256"] or sha(output / "protocol.lock.json") != meta["protocol_sha256"]:
        raise ValueError("Trained model or locked protocol changed")
    old = old_module(output)
    baseline = old.HazardGBM(params={"num_threads": 4})
    baseline.booster = lgb.Booster(model_file=str(output / "khanh_refit_model.txt"))
    if baseline.booster.feature_name() != old.FEATURES + old.WEEK_FEATS:
        raise ValueError("Legacy feature order changed")
    v6 = lgb.Booster(model_file=str(V6 / "model.txt"))
    cash = lgb.Booster(model_file=str(V6 / "cash_model.txt"))
    v6meta = json.loads((V6 / "train.json").read_text(encoding="utf-8"))
    selected = json.loads((V6 / "calibration.json").read_text(encoding="utf-8"))
    policy = json.loads((V6 / "protocol.lock.json").read_text(encoding="utf-8"))
    rows, cash_rows, q_rows, boot_rows, primary_rows, primary_boot = [], [], [], [], [], []
    max_prediction_difference = 0.0
    pred_dir = output / "predictions"
    pred_dir.mkdir(exist_ok=True)
    for index, entry in enumerate(protocol["entries"]):
        world, role = entry["name"], entry["role"]
        start = time.monotonic()
        print(f"Evaluating {world}", flush=True)
        builder, receipts = load_world(world)
        cutoffs = pd.date_range(policy["eval_first_cutoff"], policy["eval_last_cutoff"], freq=f"{policy['eval_stride_days']}D")
        frame = build_frame(builder, world, cutoffs, protocol["eval_label_end"])
        frame = frame.sort_values(["cutoff", "invoice_id"]).drop_duplicates("invoice_id").reset_index(drop=True)
        saved = pd.read_parquet(V6 / "evaluation_predictions" / f"{world}.parquet")
        keys = ["world", "invoice_id", "firm_id", "cutoff"]
        if not frame[keys].equals(saved[keys]) or not np.array_equal(frame.cause, saved.cause) or not np.array_equal(frame.time_days, saved.time_days):
            raise ValueError("Paired anchors or original evaluation labels changed")
        h_old = baseline.hazards(frame)
        h6 = calibration.transform(predict_hazards(v6, frame, V6_FEATURES, v6meta["active_causes"]), selected)
        exported = frame[keys + ["time_days", "cause", "obs_days", "amount_open"]].copy()
        primary_old, primary_new = [], []
        for day in DAYS:
            truth = observed_state(frame, day) == PAID
            p_old = paid_cdf(h_old, day)
            p_new = state_at_day(h6, day)[:, PAID]
            for name, probability in (("khanh_refit", p_old), ("v6", p_new)):
                rows.append({"world": world, "role": role, "model": name, "day": day, **probability_score(truth, probability)})
                exported[f"{name}_paid_{day}"] = probability
            if day in (28, 91, 365):
                delta = float(np.max(np.abs(p_new - saved[f"p_paid_{day}d"].to_numpy())))
                max_prediction_difference = max(max_prediction_difference, delta)
                if delta > 2e-7:
                    raise ValueError("Frozen V6 predictions were not reproduced")
            difference = (p_new - truth) ** 2 - (p_old - truth) ** 2
            b, _ = bootstrap_difference(frame, difference, 261105 + index * 100 + day)
            boot_rows.append({"world": world, "role": role, "day": day, "metric": "paid_brier", **b})
            if day in (28, 91):
                primary_old.append((p_old - truth) ** 2)
                primary_new.append((p_new - truth) ** 2)
        error_old = np.mean(primary_old, axis=0)
        error_new = np.mean(primary_new, axis=0)
        b, sampled = bootstrap_difference(frame, error_new - error_old, 261105 + index)
        primary_boot.append(sampled)
        primary_rows.append({"world": world, "role": role, "n": len(frame),
                             "khanh_paid_brier28_91": float(error_old.mean()), "v6_paid_brier28_91": float(error_new.mean()), **b})
        q_old = old.quantiles_from_hazard(h_old)
        q_new = saved[["q10_days", "q50_days", "q90_days"]].to_numpy(float)
        for name, q in (("khanh_refit", q_old), ("v6", q_new)):
            q_rows.append({"world": world, "role": role, "model": name, "n": len(frame), **restricted_score(frame, q)})
        actual_cash = receipts.targets(frame, CASH_DAYS, protocol["eval_label_end"])
        prediction_cash = predict_cash_fraction(cash, frame, V6_FEATURES, CASH_DAYS) * frame.amount_open.to_numpy()[:, None]
        for j, day in enumerate(CASH_DAYS):
            old_proxy = paid_cdf(h_old, day) * frame.amount_open.to_numpy()
            for name, prediction in (("khanh_t1_full_payment_proxy", old_proxy), ("v6_cash_head", prediction_cash[:, j])):
                cash_rows.append({"world": world, "role": role, "model": name, "day": day, **cash_score(frame, actual_cash[:, j], prediction)})
        with (pred_dir / f"{world}.parquet").open("xb") as stream:
            exported.to_parquet(stream, index=False)
        print(f"  {len(frame):,} anchors; primary {error_old.mean():.6f} -> {error_new.mean():.6f}; {time.monotonic()-start:.1f}s", flush=True)
        del builder, receipts, frame, saved, h_old, h6, exported
        gc.collect()
    scores = pd.DataFrame(rows)
    primary = pd.DataFrame(primary_rows)
    a = float(primary.khanh_paid_brier28_91.mean())
    b = float(primary.v6_paid_brier28_91.mean())
    low, high = np.quantile(np.mean(primary_boot, axis=0), [.025, .975])
    aggregate = []
    for scope in ("all_equal_world", "validation", "test", "fresh_test"):
        subset = scores if scope == "all_equal_world" else scores[scores.role.eq(scope)]
        for (model, day), group in subset.groupby(["model", "day"]):
            weights = np.ones(len(group)) if scope == "all_equal_world" else group.n.to_numpy()
            aggregate.append({"scope": scope, "model": model, "day": int(day), "n": int(group.n.sum()),
                              **{m: float(np.average(group[m], weights=weights)) for m in ("paid_brier", "paid_ece", "paid_gap", "actual_paid", "pred_paid")}})
    for name, data in (("scores.csv", scores), ("aggregate_scores.csv", pd.DataFrame(aggregate)),
                       ("primary_by_world.csv", primary), ("bootstrap.csv", pd.DataFrame(boot_rows)),
                       ("quantiles_restricted120.csv", pd.DataFrame(q_rows)), ("cash_scores.csv", pd.DataFrame(cash_rows))):
        write_csv(output / name, data)
    changed = [relative for relative, digest in protocol["protected"].items() if sha(ROOT / relative) != digest]
    if changed:
        raise ValueError(f"Protected artifacts changed: {changed}")
    summary = {"baseline": protocol["baseline"], "baseline_sha256": meta["model_sha256"], "v6_sha256": V6_SHA,
               "evaluation_anchors": int(primary.n.sum()), "worlds": len(primary),
               "primary": {"metric": protocol["primary"], "khanh": a, "v6": b, "improvement_pct": 100 * (1 - b / a),
                           "delta_v6_minus_khanh": b - a, "ci_low": float(low), "ci_high": float(high),
                           "point_winner": "v6" if b < a else "khanh_refit", "resampling": "1000 firm resamples within each fixed World, then equal-World mean; not uncertainty across new economies"},
               "worlds_v6_better_primary": int((primary.v6_paid_brier28_91 < primary.khanh_paid_brier28_91).sum()),
               "v6_prediction_max_abs_difference_from_saved": max_prediction_difference,
               "protected_files_checked": len(protocol["protected"]), "changed_protected_files": changed,
               "protocol_sha256": sha(output / "protocol.lock.json"),
               "limitations": [protocol["evaluation_scope"], protocol["common_input"],
                               "comparison of model versions including native configuration; not isolated component attribution",
                               "binary Paid scores only; no padded-zero Write-off scores for legacy T1",
                               "post91 legacy tail is geometric extrapolation, not a fitted 53-week model",
                               "restricted quantile metric is for min(time-to-paid,120), not uncapped time-to-payment",
                               "cash comparison uses T1 full-payment proxy, not the complete legacy T6 pipeline"]}
    write_json(output / "summary.json", summary)
    print(json.dumps(summary["primary"], ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--stage", choices=("all", "train", "evaluate"), default="all")
    args = parser.parse_args()
    os.environ["AGENT1_EXPAND_LEGACY"] = "0"
    if args.stage in ("all", "train"):
        protocol = prepare(args.output)
        fit(args.output, protocol)
    else:
        protocol = json.loads((args.output / "protocol.lock.json").read_text(encoding="utf-8"))
    if args.stage in ("all", "evaluate"):
        evaluate(args.output, protocol)


if __name__ == "__main__":
    main()
