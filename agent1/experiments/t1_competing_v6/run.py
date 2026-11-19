"""Versioned v6 training, calibration, cash head, holdouts and inference.

All v4/v5 sources and artifacts are read-only. Every new artifact is created
exclusively; an existing different file is an error, never an overwrite.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import zipfile

import lightgbm as lgb
import numpy as np
import pandas as pd

from agent1.data.world_manifest import code_provenance, create_world_manifest, load_cohort, sha256_file, verify_world_manifest
from agent1.models import t1
from agent1.paths import ROOT, SYNTH
from agent1.synth.shocks import ShockEpisode
from agent1.synth.world import World, WorldConfig
from analysis.analyze_t1_v4_payment_survival import predicted_cdf as v4_paid_cdf
from experiments.t1_competing_v5.core import predict_hazards as v5_hazards
from . import calibration
from .core import STATE_NAMES, PAID, WRITEOFF, cash_matrix, expand_weekly, label_events, observed_state, paid_quantiles, predict_cash_fraction, predict_hazards, state_at_day
from .features import ReceiptIndex, V6_FEATURES, V6SnapshotBuilder, model_view
from .metrics import cash_score, paired_company_bootstrap, reliability, score, subgroup_masks

HERE = Path(__file__).resolve().parent
PROTOCOL_PATH = HERE / "protocol.json"


def write_bytes_once(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Refusing to overwrite existing different artifact: {path}")
        return
    with path.open("xb") as stream:
        stream.write(data)


def write_json(path, value):
    write_bytes_once(path, (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))


def write_csv(path, frame):
    write_bytes_once(path, frame.to_csv(index=False, lineterminator="\n").encode("utf-8"))


def write_parquet(path, frame):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError(f"Parquet cache already exists: {path}")
    with path.open("xb") as stream:
        frame.to_parquet(stream, index=False)


def source_hashes():
    files = sorted(HERE.glob("*.py")) + [PROTOCOL_PATH, HERE / "requirements.txt"]
    return {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in files}


def protected_hashes(protocol):
    directories = [ROOT / protocol["v4_directory"], ROOT / protocol["v5_directory"], ROOT / "experiments/t1_competing_v5"]
    directories += sorted(SYNTH.glob("v4_shortpay_4shock_20261028_*"))
    files = []
    for directory in directories:
        if directory.is_file():
            files.append(directory)
        elif directory.is_dir():
            files.extend(p for p in directory.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    return {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in sorted(set(files))}


def prepare(protocol):
    output = ROOT / protocol["output_directory"]
    if output.parent != ROOT / "outputs/data" or not output.name.startswith("t1_competing_v6_"):
        raise ValueError("v6 output must remain in its own versioned directory")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "protocol.lock.json", protocol)
    hashes = protected_hashes(protocol)
    write_json(output / "preservation_before.json", hashes)
    write_json(output / "source_hashes.json", source_hashes())
    cohort = load_cohort(ROOT / protocol["source_cohort"])
    current = code_provenance()
    if any(current[k] != cohort[k] for k in current):
        raise ValueError("Shared generator source differs from the locked v4 cohort")
    for version in ("v4", "v5"):
        directory = ROOT / protocol[f"{version}_directory"]
        meta = json.loads((directory / "train.json").read_text(encoding="utf-8"))
        if sha256_file(directory / "model.txt") != meta["model_sha256"] or sha256_file(ROOT / protocol["source_cohort"]) != meta["cohort_sha256"]:
            raise ValueError(f"Locked {version} artifact changed")
    raw_sources = {"calibration": SYNTH/"calibration_fit.json", "wdi": ROOT/"data/raw/wdi_vn/wdi_vietnam.csv",
                   "oxcgrt": ROOT/"data/raw/oxcgrt/OxCGRT_compact_national_v1.csv",
                   "shock_design": SYNTH/"v4_shortpay_4shock_20261028_design.json"}
    for name, path in raw_sources.items():
        if sha256_file(path) != cohort["source_data_sha256"][name]:
            raise ValueError(f"Raw generator input changed: {name}")
    snapshot = output / "source_snapshot.zip"
    if not snapshot.exists():
        with zipfile.ZipFile(snapshot, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for relative in source_hashes():
                archive.write(ROOT / relative, relative)
    environment = {"python": platform.python_version(), "packages": {name: importlib.metadata.version(name) for name in ("numpy", "pandas", "scipy", "lightgbm", "pyarrow", "holidays", "pytest")}}
    write_json(output / "environment.json", environment)
    return output, cohort


def verify_preserved(output, protocol):
    before = json.loads((output / "preservation_before.json").read_text(encoding="utf-8"))
    after = protected_hashes(protocol)
    if before != after:
        raise ValueError("Protected v4/v5 source or data changed during v6")
    return {"passed": True, "files_verified": len(before), "v4_v5_overwritten": False}


def firm_partition(world, firm_ids, protocol):
    names = sorted(set(firm_ids), key=lambda name: hashlib.sha256(f"{protocol['seed']}:{world}:{name}".encode()).hexdigest())
    n = protocol["calibration_firms_per_world"]
    if len(names) <= n or n < 4 or n % 2:
        raise ValueError("Not enough source firms for disjoint model/calibration partitions")
    return {"fit": names[n:], "calibration_fit": names[:n//2], "calibration_select": names[n//2:n]}


def balanced_sample(frame, cap, seed):
    if len(frame) <= cap:
        return frame.reset_index(drop=True)
    groups = list(frame.groupby("firm_id", sort=True))
    quota = cap // len(groups)
    chosen = np.concatenate([g.sample(min(len(g), quota), random_state=seed+i).index.to_numpy() for i, (_, g) in enumerate(groups)])
    remaining = frame.loc[~frame.index.isin(chosen)]
    if len(chosen) < cap:
        chosen = np.r_[chosen, remaining.sample(cap-len(chosen), random_state=seed).index.to_numpy()]
    return frame.loc[chosen].sort_index().reset_index(drop=True)


def load_world(world):
    directory = SYNTH / world
    invoices = pd.read_parquet(directory / "invoices.parquet")
    payments = pd.read_parquet(directory / "payments.parquet")
    promises = pd.read_parquet(directory / "promises.parquet")
    if not invoices.currency.eq("VND").all() or ("fx_adjustment" in payments and payments.fx_adjustment.fillna(0).ne(0).any()):
        raise ValueError("v6 cash head currently requires VND without FX adjustments")
    return V6SnapshotBuilder(invoices, payments, promises), ReceiptIndex(payments)


def build_frame(builder, world, cutoffs, label_end):
    lookup = builder.inv.set_index("invoice_id")
    parts = []
    for cutoff in cutoffs:
        raw = builder.snapshot(cutoff)
        if raw.empty:
            continue
        visible = model_view(raw, cutoff)
        for column in ("label_date", "writeoff_date", "credit_note_date", "closure_type"):
            visible[column] = visible.invoice_id.map(lookup[column])
        parts.append(visible)
    if not parts:
        raise ValueError(f"No open snapshots: {world}")
    result = label_events(pd.concat(parts, ignore_index=True), label_end)
    result["world"] = world
    return result


def training_data(output, cohort, protocol):
    fit_parts, cal_fit_parts, cal_select_parts, audit = [], [], [], []
    cutoffs = pd.date_range(protocol["train_first_cutoff"], protocol["train_last_cutoff"], freq=f"{protocol['train_stride_days']}D")
    if (pd.Timestamp(protocol["train_label_end"])-cutoffs.max()).days < 371:
        raise ValueError("Training labels lack full 53-week observation")
    for index, entry in enumerate(cohort["worlds"]):
        if entry["role"] != "train":
            continue
        world = entry["name"]
        cache = output / "cache" / f"train_{world}.parquet"
        audit_path = cache.with_suffix(".json")
        if cache.exists() and audit_path.exists():
            detail = json.loads(audit_path.read_text(encoding="utf-8"))
            if sha256_file(cache) != detail["cache_sha256"]:
                raise ValueError("Training cache hash mismatch")
            cached = pd.read_parquet(cache)
        else:
            builder, receipts = load_world(world)
            partition = firm_partition(world, builder.inv.firm_id.unique(), protocol)
            full = build_frame(builder, world, cutoffs, protocol["train_label_end"])
            fit = full[full.firm_id.isin(partition["fit"])]
            population = len(fit)
            fit = balanced_sample(fit, protocol["max_train_snapshots_per_world"], protocol["seed"]+index)
            fit["partition"] = "fit"
            selected = [fit]
            for name in ("calibration_fit", "calibration_select"):
                part = full[full.firm_id.isin(partition[name]) & full.cutoff.ge(protocol["calibration_first_cutoff"])]
                part = part.sort_values(["cutoff", "invoice_id"]).drop_duplicates("invoice_id")
                if len(part) > protocol["calibration_max_invoices_per_world"]:
                    part = part.sample(protocol["calibration_max_invoices_per_world"], random_state=protocol["seed"]+index)
                part = part.copy()
                part["partition"] = name
                selected.append(part)
            cached = pd.concat(selected, ignore_index=True)
            cash = receipts.targets(cached, protocol["cash_horizons_days"], protocol["train_label_end"])
            for i, day in enumerate(protocol["cash_horizons_days"]):
                cached[f"cash_actual_{day}"] = cash[:, i]
            write_parquet(cache, cached)
            detail = {"world": world, "eligible_fit_snapshots": population, "sampled_fit_snapshots": len(fit), "firms": partition, "cache_sha256": sha256_file(cache)}
            write_json(audit_path, detail)
            del full, builder, receipts
        audit.append(detail)
        fit_parts.append(cached[cached.partition.eq("fit")])
        cal_fit_parts.append(cached[cached.partition.eq("calibration_fit")])
        cal_select_parts.append(cached[cached.partition.eq("calibration_select")])
        print(f"v6 source {world}: {len(fit_parts[-1]):,} fit, {len(cal_fit_parts[-1]):,}/{len(cal_select_parts[-1]):,} calibration", flush=True)
    return tuple(pd.concat(parts, ignore_index=True) for parts in (fit_parts, cal_fit_parts, cal_select_parts)), audit


def train(output, cohort, protocol):
    meta_path = output / "train.json"
    if meta_path.exists():
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        for name, key in (("model.txt", "model_sha256"), ("cash_model.txt", "cash_model_sha256")):
            if sha256_file(output / name) != metadata[key]:
                raise ValueError("Existing v6 model hash mismatch")
        return metadata
    (frame, _, _), audit = training_data(output, cohort, protocol)
    print("v6 expanding weekly risk rows", flush=True)
    x, y = expand_weekly(frame, V6_FEATURES)
    active = sorted(np.unique(y).tolist())
    mapping = {cause: i for i, cause in enumerate(active)}
    encoded = np.array([mapping[int(c)] for c in y], dtype=np.int8)
    parameters = {**protocol["lightgbm"], "num_class": len(active)}
    names = V6_FEATURES + t1.WEEK_FEATS
    model = lgb.train(parameters, lgb.Dataset(x, encoded, feature_name=names), num_boost_round=protocol["rounds"])
    write_bytes_once(output / "model.txt", model.model_to_string().encode("utf-8"))
    count = {STATE_NAMES[c]: int((y == c).sum()) for c in range(4)}
    n_weekly_rows = len(y)
    del x, y, encoded, model
    gc.collect()
    print("v6 training cumulative cash receipt head", flush=True)
    cash_x = np.vstack([cash_matrix(frame, V6_FEATURES, day) for day in protocol["cash_horizons_days"]])
    denominator = frame.amount_open.to_numpy(float).clip(1)
    cash_y = np.concatenate([np.clip(frame[f"cash_actual_{day}"].to_numpy()/denominator, 0, 1) for day in protocol["cash_horizons_days"]])
    cash_parameters = {**protocol["lightgbm"], "objective": "regression_l2", "monotone_constraints": [0]*len(V6_FEATURES)+[1]}
    cash_model = lgb.train(cash_parameters, lgb.Dataset(cash_x, cash_y, feature_name=V6_FEATURES+["horizon_days"]), num_boost_round=protocol["cash_rounds"])
    write_bytes_once(output / "cash_model.txt", cash_model.model_to_string().encode("utf-8"))
    baseline_frame = frame.sort_values("cutoff").drop_duplicates(["world", "invoice_id"])
    baseline = {str(day): np.bincount(observed_state(baseline_frame, day), minlength=4).astype(float).tolist() for day in protocol["evaluation_horizons_days"]}
    baseline = {day: (np.array(counts)/sum(counts)).tolist() for day, counts in baseline.items()}
    metadata = {"protocol_sha256": sha256_file(PROTOCOL_PATH), "source_hashes": source_hashes(),
                "cohort_sha256": sha256_file(ROOT/protocol["source_cohort"]), "fit_roles": ["train"],
                "features": V6_FEATURES, "weekly_features": names, "rounds": protocol["rounds"],
                "cash_rounds": protocol["cash_rounds"], "n_snapshots": len(frame), "n_weekly_rows": n_weekly_rows,
                "weekly_label_counts": count, "active_causes": active,
                "credit_note_risk_learned": 3 in active,
                "model_sha256": sha256_file(output/"model.txt"), "cash_model_sha256": sha256_file(output/"cash_model.txt"),
                "world_audit": audit, "train_only_empirical_baseline": baseline,
                "high_amount_train_p90": float(frame.amount_open.quantile(.9))}
    write_json(meta_path, metadata)
    return metadata


def calibrate(output, cohort, protocol, metadata):
    path = output / "calibration.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    (_, fit, selection), _ = training_data(output, cohort, protocol)
    booster = lgb.Booster(model_file=str(output/"model.txt"))
    print(f"v6 calibration: {len(fit):,} fit / {len(selection):,} selection anchors on disjoint source firms", flush=True)
    hazards = predict_hazards(booster, fit, V6_FEATURES, metadata["active_causes"])
    candidate = calibration.fit(fit, hazards, metadata["active_causes"], protocol)
    selection_hazards = predict_hazards(booster, selection, V6_FEATURES, metadata["active_causes"])
    selected = calibration.select_on_source_firms(selection, selection_hazards, candidate, protocol)
    selected["n_fit_anchors"] = len(fit)
    selected["n_selection_anchors"] = len(selection)
    selected["candidate"] = candidate
    write_json(path, selected)
    return selected


def build_fresh_holdouts(output, cohort, protocol):
    registry = []
    for entry in protocol["fresh_holdouts"]:
        if not entry["name"].startswith("v6_holdout_"):
            raise ValueError("Fresh World must use a new v6 directory")
        config = json.loads((SYNTH/entry["template"]/"config.json").read_text(encoding="utf-8"))
        config.update(name=entry["name"], seed=entry["seed"], n_firms=entry["n_firms"], write_xml=0)
        directory = SYNTH/entry["name"]
        if (directory/"manifest.json").exists():
            manifest = verify_world_manifest(directory)
            if manifest["config"] != config:
                raise ValueError("Existing fresh World has a different configuration")
        elif directory.exists():
            raise ValueError("Incomplete fresh World; inspect without overwriting")
        else:
            parsed = {**config, "shock_schedule": [ShockEpisode(**episode) for episode in config["shock_schedule"]]}
            print(f"v6 generating fresh holdout {entry['name']}", flush=True)
            World(WorldConfig(**parsed)).run(directory)
            if json.loads((directory/"config.json").read_text(encoding="utf-8")) != config:
                raise ValueError("Generated fresh configuration differs from the predeclared design")
            manifest = create_world_manifest(directory, {k: cohort[k] for k in ("commit", "source_code_sha256", "source_data_sha256")})
        registry.append({"name": entry["name"], "role": "fresh_test", "manifest_sha256": sha256_file(directory/"manifest.json"), "seed": manifest["seed"]})
    write_json(output/"fresh_holdout_registry.json", registry)
    return registry


def load_models(output, protocol, metadata):
    models = {"v6": lgb.Booster(model_file=str(output/"model.txt")), "cash": lgb.Booster(model_file=str(output/"cash_model.txt"))}
    for version in ("v4", "v5"):
        directory = ROOT/protocol[f"{version}_directory"]
        models[version] = lgb.Booster(model_file=str(directory/"model.txt"))
        models[f"{version}_meta"] = json.loads((directory/"train.json").read_text(encoding="utf-8"))
    if models["v6"].feature_name() != metadata["weekly_features"]:
        raise ValueError("v6 model feature order differs from metadata")
    return models


def all_probabilities(frame, models, selected, metadata, horizons):
    h6 = predict_hazards(models["v6"], frame, V6_FEATURES, metadata["active_causes"])
    hc = calibration.transform(h6, selected)
    h5 = v5_hazards(models["v5"], frame, models["v5_meta"]["features"])
    h5_four = np.zeros((len(frame), 53, 4), dtype=np.float32)
    h5_four[:, :, :3] = h5
    old = t1.HazardGBM(feats=models["v4_meta"]["features"])
    old.booster = models["v4"]
    h4 = old.hazards(frame)
    result = {}
    for day in horizons:
        p4 = v4_paid_cdf(h4, day)
        p4_four = np.column_stack((1-p4, p4, np.zeros((len(frame), 2))))
        result[day] = {"v4": p4_four, "v5": state_at_day(h5_four, day), "v6_raw": state_at_day(h6, day), "v6": state_at_day(hc, day),
                       "train_empirical": np.tile(metadata["train_only_empirical_baseline"][str(day)], (len(frame), 1))}
    return result, hc


def evaluate(output, cohort, protocol, metadata, selected, fresh):
    if (output/"evaluation.json").exists():
        saved = json.loads((output/"evaluation.json").read_text(encoding="utf-8"))
        for name, digest in saved["outputs_sha256"].items():
            if sha256_file(output/name) != digest:
                raise ValueError("Existing evaluation artifact changed")
        return saved
    models = load_models(output, protocol, metadata)
    cutoffs = pd.date_range(protocol["eval_first_cutoff"], protocol["eval_last_cutoff"], freq=f"{protocol['eval_stride_days']}D")
    comparisons, subgroups, bootstrap, cash_rows, bins, rolling = [], [], [], [], [], []
    entries = [entry for entry in cohort["worlds"] if entry["role"] != "train"] + fresh
    for entry in entries:
        world, role = entry["name"], entry["role"]
        builder, receipts = load_world(world)
        frame = build_frame(builder, world, cutoffs, protocol["eval_label_end"])
        frame = frame.sort_values(["cutoff", "invoice_id"]).drop_duplicates("invoice_id").reset_index(drop=True)
        if frame.obs_days.min() < 371:
            raise ValueError("Evaluation lacks full follow-up")
        print(f"v6 eval {world}: {len(frame):,} independent invoice anchors", flush=True)
        predictions, hazards = all_probabilities(frame, models, selected, metadata, protocol["evaluation_horizons_days"])
        for day, probabilities in predictions.items():
            for name, probability in probabilities.items():
                comparisons.append({"world": world, "role": role, "model": name, "day": day, **score(frame, probability, day)})
                if day in (28, 91, 365):
                    for group, keep in subgroup_masks(frame, metadata["high_amount_train_p90"]):
                        if keep.sum() >= 100:
                            subgroups.append({"world": world, "role": role, "model": name, "day": day, "group": group, **score(frame.loc[keep], probability[keep], day)})
                    actual = observed_state(frame, day)
                    for cause, label in ((PAID, "paid"), (WRITEOFF, "writeoff")):
                        for row in reliability(probability[:, cause], actual == cause)[1]:
                            bins.append({"world": world, "role": role, "model": name, "day": day, "cause": label, **row})
            if day in (28, 91, 365):
                for name in ("v6_raw", "v6"):
                    bootstrap.append({"world": world, "role": role, "model": name, "day": day, **paired_company_bootstrap(frame, probabilities[name], probabilities["v5"], day, protocol["bootstrap_replicates"], protocol["seed"])})
        actual_cash = receipts.targets(frame, protocol["cash_horizons_days"], protocol["eval_label_end"])
        forecast_cash = predict_cash_fraction(models["cash"], frame, V6_FEATURES, protocol["cash_horizons_days"]) * frame.amount_open.to_numpy()[:, None]
        for i, day in enumerate(protocol["cash_horizons_days"]):
            for name, forecast in (("v6_cash_head", forecast_cash[:, i]), ("v5_full_payment_proxy", predictions[day]["v5"][:, PAID]*frame.amount_open.to_numpy())):
                cash_rows.append({"world": world, "role": role, "model": name, "day": day, **cash_score(frame, actual_cash[:, i], forecast)})
        for cutoff in protocol["rolling_cutoffs"]:
            part = build_frame(builder, world, [pd.Timestamp(cutoff)], protocol["eval_label_end"])
            rolling_predictions, _ = all_probabilities(part, models, selected, metadata, (28, 91, 365))
            for day, values in rolling_predictions.items():
                for name in ("v5", "v6_raw", "v6"):
                    rolling.append({"world": world, "role": role, "cutoff": cutoff, "model": name, "day": day, **score(part, values[name], day)})
        exported = frame[["world", "invoice_id", "firm_id", "cutoff", "amount_open", "time_days", "cause"]].copy()
        for day in (28, 91, 365):
            for label, cause in (("paid", PAID), ("writeoff", WRITEOFF)):
                exported[f"p_{label}_{day}d"] = predictions[day]["v6"][:, cause]
        for column, values in paid_quantiles(hazards).items():
            exported[column] = values
        write_parquet(output/"evaluation_predictions"/f"{world}.parquet", exported)
        del frame, builder, receipts, predictions, hazards
        gc.collect()
    tables = {"comparison.csv": comparisons, "subgroups.csv": subgroups, "company_bootstrap.csv": bootstrap, "cash_comparison.csv": cash_rows, "reliability_bins.csv": bins, "rolling_origins.csv": rolling}
    for name, rows in tables.items():
        write_csv(output/name, pd.DataFrame(rows))
    result = pd.DataFrame(comparisons)
    checks = result[result.model.eq("v6") & result.day.isin((28, 91, 365))].copy()
    checks["paid_ece_pass"] = checks.paid_ece.le(protocol["acceptance"]["max_paid_ece"])
    checks["writeoff_gap_pass"] = (checks.day != 365) | checks.writeoff_gap.abs().le(protocol["acceptance"]["max_writeoff_gap_365"])
    reference = result[result.model.eq("v5")][["world", "day", "paid_brier"]].rename(columns={"paid_brier": "v5_paid_brier"})
    checks = checks.merge(reference, on=["world", "day"], validate="one_to_one")
    checks["short_paid_brier_pass"] = (checks.day == 365) | checks.paid_brier.le(checks.v5_paid_brier * (1 + protocol["acceptance"]["max_paid_brier_relative_worsening_short"]))
    passed = checks.paid_ece_pass & checks.writeoff_gap_pass & checks.short_paid_brier_pass
    summary = {"evaluation_worlds": len(entries), "evaluation_anchors": int(result[result.model.eq("v6") & result.day.eq(365)].n.sum()),
               "old_holdout_scope": "diagnostic, previously inspected", "fresh_scope": "predeclared independent seeds, same generator and shock families",
               "model_sha256": metadata["model_sha256"], "calibration_selected": selected["selected"],
               "research_checks_all_passed": bool(passed.all()),
               "failed_checks": checks[~passed][["world", "role", "day", "paid_ece", "writeoff_gap", "paid_brier", "v5_paid_brier", "paid_ece_pass", "writeoff_gap_pass", "short_paid_brier_pass"]].to_dict("records"),
               "outputs_sha256": {name: sha256_file(output/name) for name in tables},
               "limitations": ["synthetic only", "credit-only risk not estimable without training events", "writeoff recoveries unsupported", "CI clustered by firm, not across new Worlds", "cash head restricted to current VND cohort"]}
    write_json(output/"evaluation.json", summary)
    return summary


def infer(output, cohort, protocol, metadata, selected):
    booster = lgb.Booster(model_file=str(output/"model.txt"))
    cash_model = lgb.Booster(model_file=str(output/"cash_model.txt"))
    parts = []
    for entry in cohort["worlds"]:
        builder, _ = load_world(entry["name"])
        raw = builder.snapshot(protocol["inference_as_of"])
        frame = model_view(raw, protocol["inference_as_of"])
        hazards = calibration.transform(predict_hazards(booster, frame, V6_FEATURES, metadata["active_causes"]), selected)
        result = frame[["invoice_id", "firm_id", "customer_id", "cutoff", "amount_open"]].copy()
        result["world"], result["role"] = entry["name"], entry["role"]
        for day in (28, 91, 180, 365):
            probability = state_at_day(hazards, day)
            for cause, label in enumerate(STATE_NAMES):
                result[f"p_{label}_{day}d"] = probability[:, cause]
        cash = predict_cash_fraction(cash_model, frame, V6_FEATURES, protocol["cash_horizons_days"])
        for i, day in enumerate(protocol["cash_horizons_days"]):
            result[f"expected_receipts_{day}d_vnd"] = cash[:, i]*frame.amount_open.to_numpy()
        for column, values in paid_quantiles(hazards).items():
            result[column] = values
        parts.append(result)
    result = pd.concat(parts, ignore_index=True)
    write_csv(output/"inference_2025-12-31"/"predictions.csv", result)
    summary = {"as_of": protocol["inference_as_of"], "n_open": len(result), "amount_open": float(result.amount_open.sum()),
               "q90_not_reached_by_365": int(result.q90_days.isna().sum()), "q50_not_reached_by_365": int(result.q50_days.isna().sum()),
               "credit_note_risk_learned": metadata["credit_note_risk_learned"],
               "p_paid_365_mean": float(result.p_paid_365d.mean()), "p_writeoff_365_mean": float(result.p_writeoff_365d.mean()),
               "predictions_sha256": sha256_file(output/"inference_2025-12-31"/"predictions.csv"),
               "scope": "synthetic forecasts without future outcomes; not observed accuracy or production activation"}
    write_json(output/"inference_2025-12-31"/"summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("all", "prepare", "train", "calibrate", "fresh", "evaluate", "infer"), default="all")
    args = parser.parse_args()
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    output, cohort = prepare(protocol)
    if args.stage == "prepare":
        print(json.dumps(verify_preserved(output, protocol)))
        return
    metadata = train(output, cohort, protocol)
    if args.stage == "train":
        print(json.dumps({"n_snapshots": metadata["n_snapshots"], "n_weekly_rows": metadata["n_weekly_rows"], **verify_preserved(output, protocol)}))
        return
    selected = calibrate(output, cohort, protocol, metadata)
    if args.stage == "calibrate":
        print(json.dumps({"selected": selected["selected"], **verify_preserved(output, protocol)}))
        return
    if args.stage in ("all", "fresh", "evaluate"):
        fresh = build_fresh_holdouts(output, cohort, protocol)
        if args.stage != "fresh":
            evaluate(output, cohort, protocol, metadata, selected, fresh)
    if args.stage in ("all", "infer"):
        infer(output, cohort, protocol, metadata, selected)
    preservation = verify_preserved(output, protocol)
    write_json(output/"preservation_after.json", preservation)
    print(json.dumps({"stage": args.stage, "output": str(output.relative_to(ROOT)), **preservation}), flush=True)


if __name__ == "__main__":
    main()
