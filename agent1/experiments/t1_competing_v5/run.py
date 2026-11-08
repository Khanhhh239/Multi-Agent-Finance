"""Independent v5 competing-risks experiment on immutable v4 synthetic Worlds.

Run ``python -m experiments.t1_competing_v5.run`` from the repository root.
No v4 artifact is written. Validation/test Worlds are never used for fitting.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from agent1.data.world_manifest import code_provenance, load_cohort, sha256_file
from agent1.models import t1
from agent1.models.features import SnapshotBuilder, model_snapshot_view
from agent1.paths import ROOT, SYNTH
from analysis.analyze_t1_v4_payment_survival import predicted_cdf as v4_paid_cdf
from experiments.t1_competing_v5.core import (
    OPEN, PAID, WRITEOFF, aalen_johansen, cumulative_incidence,
    expand_weekly, label_first_event, observed_state, predict_hazards,
)

HERE = Path(__file__).resolve().parent
PROTOCOL_PATH = HERE / "protocol.json"
OUTPUT = ROOT / "outputs/data/v5_competing_risks_53w_20261028"
TRAIN_META = OUTPUT / "train.json"
MODEL_PATH = OUTPUT / "model.txt"


def read_inputs() -> tuple[dict, dict, dict, dict]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    cohort_path = ROOT / protocol["source_cohort"]
    cohort = load_cohort(cohort_path)
    old_path = ROOT / protocol["source_model_v4"]
    old_meta = json.loads((old_path.parent / "train.json").read_text(encoding="utf-8"))
    if old_meta["cohort_sha256"] != sha256_file(cohort_path) or \
            old_meta["model_sha256"] != sha256_file(old_path):
        raise ValueError("The locked v4 cohort/model hashes changed")
    provenance = code_provenance()
    if any(provenance[key] != cohort[key] for key in provenance):
        raise ValueError("Restore the saved v4 generator source snapshot first")
    if cohort["split_protocol"]["origin"] != protocol["origin"]:
        raise ValueError("The v5 temporal split does not match v4's origin")
    return protocol, cohort, old_meta, provenance


def source_hashes() -> dict[str, str]:
    return {path.name: sha256_file(path) for path in
            (HERE / "core.py", HERE / "run.py", PROTOCOL_PATH)}


def world_snapshots(world: str, cutoffs: pd.DatetimeIndex, label_end: str) -> pd.DataFrame:
    directory = SYNTH / world
    invoices = pd.read_parquet(directory / "invoices.parquet")
    payments = pd.read_parquet(directory / "payments.parquet")
    promises = pd.read_parquet(directory / "promises.parquet")
    if "closure_type" not in invoices:
        raise ValueError(f"{world}: closure_type is required for first-event policy")
    closure = invoices.set_index("invoice_id")["closure_type"]
    builder = SnapshotBuilder(invoices, payments, promises)
    parts = []
    for cutoff in cutoffs:
        raw = builder.snapshot(cutoff)
        if raw.empty:
            continue
        visible = model_snapshot_view(raw, cutoff)
        visible["label_date"] = raw["label_date"].to_numpy()
        visible["writeoff_date"] = raw["writeoff_date"].to_numpy()
        visible["closure_type"] = visible["invoice_id"].map(closure)
        parts.append(visible)
    if not parts:
        raise ValueError(f"{world}: no open snapshots")
    return label_first_event(pd.concat(parts, ignore_index=True), label_end)


def train(protocol: dict, cohort: dict, old_meta: dict, provenance: dict) -> dict:
    expected = {
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "cohort_sha256": old_meta["cohort_sha256"],
        "v4_model_sha256": old_meta["model_sha256"],
        "source_hashes": source_hashes(),
        "commit": provenance["commit"],
        "source_code_sha256": provenance["source_code_sha256"],
    }
    if TRAIN_META.exists() or MODEL_PATH.exists():
        if not TRAIN_META.exists() or not MODEL_PATH.exists():
            raise ValueError("Incomplete v5 artifact; inspect rather than overwrite")
        metadata = json.loads(TRAIN_META.read_text(encoding="utf-8"))
        if any(metadata.get(k) != v for k, v in expected.items()) or \
                sha256_file(MODEL_PATH) != metadata.get("model_sha256"):
            raise ValueError("Existing v5 artifact differs; use a new versioned directory")
        return metadata

    cutoffs = pd.date_range(protocol["train_first_cutoff"], protocol["train_last_cutoff"],
                            freq=f'{protocol["train_stride_days"]}D')
    label_end = pd.Timestamp(protocol["train_label_end"])
    if (label_end - cutoffs.max()).days < 7 * protocol["horizon_weeks"]:
        raise ValueError("Training snapshots lack the full model risk horizon")
    matrix_parts, label_parts, audit = [], [], []
    for index, entry in enumerate(cohort["worlds"]):
        if entry["role"] != "train":
            continue
        world = entry["name"]
        frame = world_snapshots(world, cutoffs, protocol["train_label_end"])
        population = len(frame)
        cap = protocol["max_train_snapshots_per_world"]
        if len(frame) > cap:
            frame = frame.sample(cap, random_state=protocol["train_seed"] + index)
        frame = frame.reset_index(drop=True)
        x, y, counts = expand_weekly(frame, old_meta["features"])
        matrix_parts.append(x)
        label_parts.append(y)
        audit.append({"world": world, "population_snapshots": population,
                      "sampled_snapshots": len(frame), "weekly_rows": len(y),
                      "weekly_labels": counts,
                      "first_event_counts": {"paid": int((frame.cause == PAID).sum()),
                                             "writeoff": int((frame.cause == WRITEOFF).sum()),
                                             "censored": int((frame.cause == OPEN).sum())}})
        print(f"train {world}: {population:,} snapshots, {len(y):,} weekly rows", flush=True)
    x, y = np.vstack(matrix_parts), np.concatenate(label_parts)
    if len(np.unique(y)) != 3:
        raise ValueError("Training must include open, paid and write-off labels")
    feature_names = old_meta["features"] + t1.WEEK_FEATS
    dataset = lgb.Dataset(x, y, feature_name=feature_names, free_raw_data=True)
    booster = lgb.train(protocol["lightgbm"], dataset, num_boost_round=protocol["rounds"])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(MODEL_PATH))
    metadata = {**expected, "model_sha256": sha256_file(MODEL_PATH),
                "features": old_meta["features"], "weekly_feature_names": feature_names,
                "rounds": protocol["rounds"], "n_snapshots": sum(a["sampled_snapshots"] for a in audit),
                "n_weekly_rows": len(y), "weekly_label_counts":
                {name: int((y == value).sum()) for name, value in
                 (("open", OPEN), ("paid", PAID), ("writeoff", WRITEOFF))},
                "world_audit": audit, "fit_roles": ["train"]}
    TRAIN_META.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    return metadata


def v5_state_at_day(fp: np.ndarray, fw: np.ndarray, so: np.ndarray,
                    hazards: np.ndarray, day: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Week-end CIF; within-week days use a proportional partial-week transition."""
    full, partial = divmod(day, 7)
    if partial == 0:
        return fp[:, full - 1], fw[:, full - 1], so[:, full - 1]
    p0 = np.zeros(len(fp)) if full == 0 else fp[:, full - 1]
    w0 = np.zeros(len(fp)) if full == 0 else fw[:, full - 1]
    s0 = np.ones(len(fp)) if full == 0 else so[:, full - 1]
    h = hazards[:, full, :].astype(float)
    event = h[:, PAID] + h[:, WRITEOFF]
    fraction = 1 - np.power(h[:, OPEN], partial / 7)
    p = p0 + s0 * np.divide(h[:, PAID], event, out=np.zeros_like(event), where=event > 0) * fraction
    w = w0 + s0 * np.divide(h[:, WRITEOFF], event, out=np.zeros_like(event), where=event > 0) * fraction
    return p, w, s0 * (1 - fraction)


def evaluate(protocol: dict, cohort: dict, old_meta: dict, metadata: dict) -> dict:
    if metadata["source_hashes"] != source_hashes() or \
            metadata["model_sha256"] != sha256_file(MODEL_PATH):
        raise ValueError("v5 model or experiment source changed")
    booster = lgb.Booster(model_file=str(MODEL_PATH))
    if booster.feature_name() != metadata["weekly_feature_names"]:
        raise ValueError("v5 model feature order changed")
    old_model = t1.HazardGBM(feats=old_meta["features"])
    old_model.booster = lgb.Booster(model_file=str(ROOT / protocol["source_model_v4"]))
    if old_model.booster.feature_name() != old_meta["features"] + t1.WEEK_FEATS:
        raise ValueError("v4 model feature order changed")
    cutoffs = pd.date_range(protocol["eval_first_cutoff"], protocol["eval_last_cutoff"],
                            freq=f'{protocol["eval_stride_days"]}D')
    cutoffs = cutoffs[(pd.Timestamp(protocol["eval_label_end"]) - cutoffs).days >= 371]
    if cutoffs.empty:
        raise ValueError("No evaluation cutoff has 365 days of follow-up")
    horizons = protocol["evaluation_horizons_days"]
    event_rows, aj_rows, hazard_rows, comparison_rows = [], [], [], []
    for entry in cohort["worlds"]:
        if entry["role"] == "train":
            continue
        world, role = entry["name"], entry["role"]
        frame = world_snapshots(world, cutoffs, protocol["eval_label_end"])
        frame = frame.sort_values(["cutoff", "invoice_id"]).drop_duplicates("invoice_id").reset_index(drop=True)
        if frame.obs_days.min() < 371:
            raise ValueError(f"{world}: evaluation anchor lacks full 53-week follow-up")
        event_rows.append({"world": world, "role": role, "n_invoices": len(frame),
                           "first_cutoff": str(frame.cutoff.min().date()),
                           "last_cutoff": str(frame.cutoff.max().date()),
                           "paid_events_by_365": int(((frame.cause == PAID) &
                                                       (frame.time_days <= 365)).sum()),
                           "writeoff_events_by_365": int(((frame.cause == WRITEOFF) &
                                                           (frame.time_days <= 365)).sum()),
                           "open_at_365": int((observed_state(frame, 365) == OPEN).sum())})
        hz = predict_hazards(booster, frame, metadata["features"])
        fp, fw, so = cumulative_incidence(hz)
        old_hz = old_model.hazards(frame)
        for row in aalen_johansen(frame, horizons):
            aj_rows.append({"world": world, "role": role, "n": len(frame), **row})
        times = frame.time_days.to_numpy()
        causes = frame.cause.to_numpy()
        for week in range(1, protocol["horizon_weeks"] + 1):
            left, right = 7 * (week - 1), 7 * week
            risk = times > left
            n_risk = int(risk.sum())
            npay = int(((times > left) & (times <= right) & (causes == PAID)).sum())
            nwrite = int(((times > left) & (times <= right) & (causes == WRITEOFF)).sum())
            hazard_rows.append({"world": world, "role": role, "week": week,
                                "n_at_risk": n_risk, "n_paid": npay, "n_writeoff": nwrite,
                                "actual_paid_hazard": npay / n_risk if n_risk else None,
                                "actual_writeoff_hazard": nwrite / n_risk if n_risk else None,
                                "v5_paid_hazard_on_risk": float(hz[risk, week - 1, PAID].mean()) if n_risk else None,
                                "v5_writeoff_hazard_on_risk": float(hz[risk, week - 1, WRITEOFF].mean()) if n_risk else None,
                                "v4_paid_hazard_on_risk": float((old_hz[risk, week - 1] if week <= 13 else
                                    np.clip(old_hz[risk, -4:].mean(axis=1), .02, .6)).mean()) if n_risk else None})
        for day in horizons:
            actual = observed_state(frame, day)
            p5, w5, o5 = v5_state_at_day(fp, fw, so, hz, day)
            p4 = v4_paid_cdf(old_hz, day)
            for name, p, w, o in (("v5_competing", p5, w5, o5),
                                  ("v4_paid_only", p4, np.zeros(len(p4)), 1 - p4)):
                target_p = (actual == PAID).astype(float)
                target_w = (actual == WRITEOFF).astype(float)
                target_o = (actual == OPEN).astype(float)
                comparison_rows.append({"world": world, "role": role, "model": name,
                    "day": day, "n": len(frame),
                    "actual_paid": float(target_p.mean()), "pred_paid": float(p.mean()),
                    "paid_gap": float(p.mean() - target_p.mean()),
                    "actual_writeoff": float(target_w.mean()), "pred_writeoff": float(w.mean()),
                    "writeoff_gap": float(w.mean() - target_w.mean()),
                    "actual_open": float(target_o.mean()), "pred_open": float(o.mean()),
                    "paid_brier": float(np.mean((p - target_p) ** 2)),
                    "writeoff_brier": float(np.mean((w - target_w) ** 2)),
                    "three_state_brier": float(np.mean((p-target_p)**2 + (w-target_w)**2 + (o-target_o)**2))})
        print(f"eval {world}: {len(frame):,} unique invoices", flush=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    tables = {"event_audit.csv": event_rows, "aj_curves.csv": aj_rows,
              "actual_weekly_hazards.csv": hazard_rows, "comparison.csv": comparison_rows}
    for filename, rows in tables.items():
        pd.DataFrame(rows).to_csv(OUTPUT / filename, index=False)
    result = {"model_sha256": metadata["model_sha256"],
              "cohort_sha256": metadata["cohort_sha256"],
              "protocol_sha256": metadata["protocol_sha256"],
              "source_hashes": metadata["source_hashes"],
              "evaluation_worlds": len(event_rows),
              "evaluation_invoices": sum(row["n_invoices"] for row in event_rows),
              "horizons_days": horizons,
              "outputs_sha256": {filename: sha256_file(OUTPUT / filename) for filename in tables}}
    (OUTPUT / "summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("all", "train", "evaluate"), default="all")
    args = parser.parse_args()
    protocol, cohort, old_meta, provenance = read_inputs()
    metadata = train(protocol, cohort, old_meta, provenance) if args.stage != "evaluate" else \
        json.loads(TRAIN_META.read_text(encoding="utf-8"))
    print(json.dumps({"v5_train": {key: metadata[key] for key in
                                   ("n_snapshots", "n_weekly_rows", "weekly_label_counts")}}), flush=True)
    if args.stage != "train":
        print(json.dumps(evaluate(protocol, cohort, old_meta, metadata)), flush=True)


if __name__ == "__main__":
    main()
