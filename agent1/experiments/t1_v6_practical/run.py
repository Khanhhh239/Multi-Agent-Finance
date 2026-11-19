"""Run P0-P4 with source-only selection and a locked fresh evaluation.

Every output is versioned/exclusive. Resume verifies code, protocol, cached data
and model hashes. No old test observations are loaded for modeling; preservation
may hash historical files. No production model is changed.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import gc
import hashlib
import importlib.metadata
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from agent1.paths import ROOT, SYNTH
from agent1.models import t1
from agent1.data.world_manifest import create_world_manifest, source_provenance, verify_world_manifest
from agent1.synth.shocks import ShockEpisode
from agent1.synth.world import World, WorldConfig
from experiments.t1_competing_v6.core import state_at_day
from experiments.t1_competing_v6.metrics import score, paired_company_bootstrap
from experiments.t1_competing_v6.run import load_world, build_frame, balanced_sample
from experiments.t1_credit_context.practical import PRACTICAL_CONTEXT_FEATURES
from .design import protocol
from .ledger import BEHAVIOR_FEATURES
from .model import ARMS, expand_weekly, predict_hazards
from .sidecars import build_features


HERE = Path(__file__).resolve().parent
ORIGINAL = ROOT / "outputs/data/t1_competing_v6_20261101"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_once(path, data):
    encoded = (json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError(f"Refusing different existing artifact: {path}")
    else:
        with path.open("xb") as stream:
            stream.write(encoded)


def save_frame(path, frame):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError(f"Frame already exists: {path}")
    frame.to_parquet(path, index=False)
    json_once(path.with_suffix(".sha256.json"), {"sha256": digest(path), "n": len(frame)})


def read_frame(path):
    meta = json.loads(Path(path).with_suffix(".sha256.json").read_text(encoding="utf-8"))
    if digest(path) != meta["sha256"]:
        raise ValueError("Cached experiment frame changed")
    return pd.read_parquet(path)


def csv_once(path, rows):
    data = pd.DataFrame(rows).to_csv(index=False).encode()
    path = Path(path)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("Different existing evaluation CSV")
    else:
        path.write_bytes(data)


def prepare(out):
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(HERE.glob("*.py")) + [ROOT / "experiments/t1_credit_context/practical.py", ROOT / "experiments/t1_credit_context/features.py"]
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in files}
    json_once(out / "protocol.lock.json", protocol())
    json_once(out / "code.lock.json", hashes)
    json_once(out / "environment.json", {p: importlib.metadata.version(p) for p in ["numpy", "pandas", "lightgbm", "pyarrow", "pytest"]})
    before = out / "preservation_before.json"
    if not before.exists():
        old = json.loads((ROOT / "outputs/analysis/t1_credit_context_20261105/verification.json").read_text(encoding="utf-8"))["prerequisites_sha256"]
        shared = {str(p.relative_to(ROOT)): digest(p) for p in (ROOT / "agent1").rglob("*.py")}
        json_once(before, {**old, **shared})
    json_once(out / "source_provenance.json", source_provenance())
    raw_manifest = json.loads((ROOT / "data/raw/MANIFEST.json").read_text(encoding="utf-8"))
    for source in raw_manifest.values():
        for item in source["files"]:
            if digest(ROOT / "data/raw" / item["path"]) != item["sha256"]:
                raise ValueError("Raw generator source differs from inventory manifest")
    meta = json.loads((ORIGINAL / "train.json").read_text(encoding="utf-8"))
    if digest(ORIGINAL / "model.txt") != meta["model_sha256"]:
        raise ValueError("Original v6 model changed")
    return protocol(), meta


def attach(world, frame, out):
    extra = build_features(SYNTH / world, frame, out / "observed_sidecars" / world)
    if len(extra) != len(frame) or extra.filter(like="macro_").shape[1]:
        raise ValueError("Feature alignment or macro exclusion failed")
    return pd.concat([frame.reset_index(drop=True), extra], axis=1)


def source_frames(out, spec, meta):
    fit_path, val_path = out / "fit.parquet", out / "source_validation.parquet"
    if fit_path.exists() and val_path.exists():
        return read_frame(fit_path), read_frame(val_path)
    parts, validation = [], []
    old_protocol = json.loads((ORIGINAL / "protocol.lock.json").read_text(encoding="utf-8"))
    dates = pd.date_range(spec["eval_first_cutoff"], spec["eval_last_cutoff"], freq="28D")
    for detail in meta["world_audit"]:
        world = detail["world"]
        world_fit = out / "prepared" / f"{world}_fit.parquet"
        world_val = out / "prepared" / f"{world}_validation.parquet"
        if world_fit.exists() and world_val.exists():
            parts.append(read_frame(world_fit)); validation.append(read_frame(world_val))
            continue
        print(f"Prepare observed features {world}", flush=True)
        cache = ORIGINAL / "cache" / f"train_{world}.parquet"
        if digest(cache) != detail["cache_sha256"]:
            raise ValueError("Original source snapshot cache changed")
        cached = pd.read_parquet(cache)
        fit = cached[cached.partition.eq("fit")].reset_index(drop=True)
        builder, _ = load_world(world)
        reserved = detail["firms"]["calibration_fit"] + detail["firms"]["calibration_select"]
        builder.inv = builder.inv[builder.inv.firm_id.isin(reserved)].copy()
        val = build_frame(builder, world, dates, spec["eval_label_end"])
        val = val.sort_values(["cutoff", "invoice_id"]).drop_duplicates("invoice_id").reset_index(drop=True)
        if set(val.firm_id) & set(fit.firm_id):
            raise ValueError("Source selection companies overlap fit")
        combined = pd.concat([fit, val], ignore_index=True)
        combined = attach(world, combined, out)
        enriched_fit, enriched_val = combined.iloc[:len(fit)].copy(), combined.iloc[len(fit):].copy()
        save_frame(world_fit, enriched_fit); save_frame(world_val, enriched_val)
        parts.append(enriched_fit); validation.append(enriched_val)
        print(f"Prepared {world}: {len(fit)} fit / {len(val)} source anchors", flush=True)
        del builder, combined, cached
        gc.collect()
    fit, val = pd.concat(parts, ignore_index=True), pd.concat(validation, ignore_index=True)
    if len(fit) != 200000 or fit.obs_days.min() < 371 or val.obs_days.min() < 371:
        raise ValueError("Unexpected fit population or follow-up")
    save_frame(fit_path, fit); save_frame(val_path, val)
    json_once(out / "source_frame_protocol.json", old_protocol)
    return fit, val


def fit_model(out, name, arm, frame, meta, parameters):
    path, info = out / "models" / f"{name}.txt", out / "models" / f"{name}.json"
    if path.exists() and info.exists():
        saved = json.loads(info.read_text(encoding="utf-8"))
        if digest(path) != saved["sha256"] or saved["features"] != ARMS[arm] or saved["n_snapshots"] != len(frame):
            raise ValueError("Existing fitted candidate differs")
        return lgb.Booster(model_file=str(path))
    print(f"Fit {name}: {len(frame)} snapshots, {len(ARMS[arm])} snapshot features", flush=True)
    x, y = expand_weekly(frame, ARMS[arm])
    active = meta["active_causes"]
    if sorted(np.unique(y)) != active:
        raise ValueError("Cause support differs from locked v6")
    encoded = np.array([{c: i for i, c in enumerate(active)}[int(c)] for c in y], dtype=np.int8)
    model = lgb.train({**parameters, "num_class": len(active)},
                      lgb.Dataset(x, encoded, feature_name=ARMS[arm] + t1.WEEK_FEATS), num_boost_round=160)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(model.model_to_string())
    json_once(info, {"features": ARMS[arm], "n_snapshots": len(frame), "n_weekly_rows": len(y),
                     "weekly_counts": np.bincount(y, minlength=4).tolist(), "sha256": digest(path), "arm": arm})
    del x, y, encoded
    gc.collect()
    return model


def evaluate(out, name, arm, model, frame, meta, split):
    folder = out / "predictions" / split
    path = folder / f"{name}.parquet"
    score_path = folder / f"{name}_scores.csv"
    if path.exists() and score_path.exists():
        integrity = json.loads(score_path.with_suffix(".sha256.json").read_text(encoding="utf-8"))
        if digest(score_path) != integrity["sha256"]:
            raise ValueError("Cached evaluation scores changed")
        return read_frame(path), pd.read_csv(score_path, float_precision="round_trip").to_dict("records")
    prediction_parts, rows = [], []
    for world, part in frame.groupby("world", sort=False):
        print(f"Score {split}/{name}/{world}: {len(part)} anchors", flush=True)
        part = part.reset_index(drop=True)
        hazards = predict_hazards(model, part, ARMS[arm], meta["active_causes"])
        predicted = part[["world", "firm_id", "invoice_id", "cutoff", "amount_open", "cause", "time_days", "obs_days"]].copy()
        for day in (28, 91, 365):
            probability = state_at_day(hazards, day)
            rows.append({"split": split, "model": name, "arm": arm, "world": world, "day": day, **score(part, probability, day)})
            for c in range(4):
                predicted[f"p_{day}_{c}"] = probability[:, c]
        prediction_parts.append(predicted)
    predictions = pd.concat(prediction_parts, ignore_index=True)
    save_frame(path, predictions); csv_once(score_path, rows)
    json_once(score_path.with_suffix(".sha256.json"), {"sha256": digest(score_path)})
    return predictions, rows


def choose(rows, reference="v6"):
    table = pd.DataFrame(rows)
    if not table.split.eq("source").all() or not table.world.str.startswith("v4_shortpay_4shock_20261028_train_").all():
        raise ValueError("Only reserved companies in source Worlds may select candidates")
    base = table[table.model.eq(reference)].set_index(["world", "day"])
    averages, eligible = {}, []
    for name in table.model.unique():
        part = table[table.model.eq(name)].set_index(["world", "day"])
        means = part.xs(365, level="day")[["four_state_brier", "writeoff_brier"]].mean()
        averages[name] = {"joint365": float(means.four_state_brier), "writeoff365": float(means.writeoff_brier)}
        short = part.loc[part.index.get_level_values("day").isin([28, 91]), "paid_brier"]
        safety = bool(short.le(base.loc[short.index, "paid_brier"] * 1.02 + 1e-12).all())
        improve = bool(means.four_state_brier < base.xs(365, level="day").four_state_brier.mean()
                       and means.writeoff_brier < base.xs(365, level="day").writeoff_brier.mean())
        averages[name].update(short_paid_safe=safety, eligible=safety and improve)
        if safety and improve:
            eligible.append(name)
    # Augmented models have their arm encoded after "aug_".
    winner = min(eligible, key=lambda n: (averages[n]["joint365"], len(ARMS[n.removeprefix("aug_")]), n)) if eligible else reference
    return {"selected": winner, "source_equal_world_means": averages, "test_outcomes_used": False}


def support(fit, target, out, prefix):
    rows = []
    for name in ARMS["both"]:
        train = pd.to_numeric(fit[name], errors="raise").to_numpy(float)
        test = pd.to_numeric(target[name], errors="raise").to_numpy(float)
        a, b = train[np.isfinite(train)], test[np.isfinite(test)]
        rows.append({"feature": name, "train_min": float(a.min()) if len(a) else None,
                     "train_max": float(a.max()) if len(a) else None,
                     "target_finite_n": len(b), "target_missing_fraction": float((~np.isfinite(test)).mean()),
                     "train_missing_fraction": float((~np.isfinite(train)).mean()),
                     "outside_train_range_fraction": float(((b < a.min()) | (b > a.max())).mean()) if len(a) and len(b) else None})
    csv_once(out / f"{prefix}_support.csv", rows)
    return rows


def make_world(out, cfg):
    if pd.Timestamp(cfg["start"]) < pd.Timestamp("2019-01-01"):
        raise ValueError("Current complete World economic rules require start >= 2019-01-01")
    directory = SYNTH / cfg["name"]
    provenance = json.loads((out / "source_provenance.json").read_text(encoding="utf-8"))
    if directory.exists():
        saved = verify_world_manifest(directory, validate=True)
        if saved["config"] != cfg:
            raise ValueError("Existing new World config differs from locked design")
        return
    print(f"Generate predeclared World {cfg['name']}", flush=True)
    values = {**cfg, "shock_schedule": [ShockEpisode(**e) for e in cfg["shock_schedule"]]}
    World(WorldConfig(**values)).run(directory, verbose=False)
    create_world_manifest(directory, provenance)


def augment_frame(out, spec):
    path = out / "augmented_fit.parquet"
    if path.exists():
        return read_frame(path)
    parts = []
    old = json.loads((ORIGINAL / "protocol.lock.json").read_text(encoding="utf-8"))
    dates = pd.date_range(old["train_first_cutoff"], old["train_last_cutoff"], freq="28D")
    for i, cfg in enumerate(spec["augment_worlds"]):
        make_world(out, cfg)
        builder, _ = load_world(cfg["name"])
        frame = build_frame(builder, cfg["name"], dates, old["train_label_end"])
        frame = balanced_sample(frame, 50000, 202611051 + i).reset_index(drop=True)
        frame = attach(cfg["name"], frame, out)
        parts.append(frame)
        del builder
        gc.collect()
    added = pd.concat(parts, ignore_index=True)
    save_frame(path, added)
    return added


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/data/t1_v6_practical_20261105_r2")
    parser.add_argument("--stage", choices=["prepare", "primary", "select", "fresh", "all"], default="all")
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to((ROOT / "outputs/data").resolve()) or out == ORIGINAL.resolve():
        raise ValueError("Use a separate outputs/data experiment directory")
    spec, meta = prepare(out)
    old = json.loads((ORIGINAL / "protocol.lock.json").read_text(encoding="utf-8"))
    fit, val = source_frames(out, spec, meta)
    inputs = {"fit_sha256": digest(out / "fit.parquet"), "validation_sha256": digest(out / "source_validation.parquet")}
    json_once(out / "data.lock.json", inputs)
    if args.stage == "prepare":
        return
    models, predictions, all_rows = {}, {}, []
    for arm in ARMS:
        models[arm] = fit_model(out, arm, arm, fit, meta, old["lightgbm"])
        if arm == "v6":
            sample = val.iloc[:128]
            original = lgb.Booster(model_file=str(ORIGINAL / "model.txt"))
            delta = float(np.max(np.abs(predict_hazards(models[arm], sample, ARMS[arm], meta["active_causes"])
                                       - predict_hazards(original, sample, ARMS[arm], meta["active_causes"]))))
            if delta > 1e-8:
                raise ValueError(f"Baseline refit does not reproduce v6: {delta}")
            json_once(out / "baseline_reproduction.json", {"max_hazard_delta": delta,
                       "model_text_sha256_equal": digest(out / "models/v6.txt") == digest(ORIGINAL / "model.txt")})
        predictions[arm], rows = evaluate(out, arm, arm, models[arm], val, meta, "source")
        all_rows.extend(rows)
    csv_once(out / "primary_source_scores.csv", all_rows)
    primary = choose(all_rows)
    json_once(out / "primary_selection.json", primary)
    support_rows = support(fit, val, out, "primary_source")
    if args.stage == "primary":
        return
    rule = spec["support_trigger"]
    trigger = any(r["feature"] in rule["features"] and r["outside_train_range_fraction"] is not None
                  and r["outside_train_range_fraction"] > rule["max_outside_train_range_fraction"] for r in support_rows)
    json_once(out / "augmentation_decision.json", {"triggered": trigger, "rule": rule, "target": "source validation only"})
    arm_by_name = {arm: arm for arm in ARMS}
    if trigger:
        added = augment_frame(out, spec)
        augmented = pd.concat([fit, added], ignore_index=True)
        for arm in dict.fromkeys(["v6", primary["selected"]]):
            name = "aug_" + arm
            models[name] = fit_model(out, name, arm, augmented, meta, old["lightgbm"])
            arm_by_name[name] = arm
            predictions[name], rows = evaluate(out, name, arm, models[name], val, meta, "source")
            all_rows.extend(rows)
        support(augmented, val, out, "augmented_source")
        del augmented, added
        gc.collect()
    selection = choose(all_rows)
    selection["models_sha256"] = {name: digest(out / "models" / f"{name}.txt") for name in models}
    selection["protocol_sha256"] = digest(out / "protocol.lock.json")
    selection["fresh_outcomes_seen"] = False
    json_once(out / "final_selection.lock.json", selection)
    csv_once(out / "all_source_scores.csv", all_rows)
    if args.stage == "select":
        return
    # Fresh World generation and reads occur only after immutable selection.
    fresh_parts = []
    dates = pd.date_range(spec["eval_first_cutoff"], spec["eval_last_cutoff"], freq="28D")
    for cfg in spec["fresh_worlds"]:
        path = out / "prepared" / f"{cfg['name']}_fresh.parquet"
        make_world(out, cfg)
        if path.exists():
            fresh_parts.append(read_frame(path)); continue
        builder, _ = load_world(cfg["name"])
        frame = build_frame(builder, cfg["name"], dates, spec["eval_label_end"])
        frame = frame.sort_values(["cutoff", "invoice_id"]).drop_duplicates("invoice_id").reset_index(drop=True)
        frame = attach(cfg["name"], frame, out)
        save_frame(path, frame); fresh_parts.append(frame)
        del builder
        gc.collect()
    fresh = pd.concat(fresh_parts, ignore_index=True)
    support(fit, fresh, out, "fresh_vs_primary_fit")
    fresh_rows, fresh_predictions = [], {}
    for name, model in models.items():
        fresh_predictions[name], rows = evaluate(out, name, arm_by_name[name], model, fresh, meta, "fresh")
        fresh_rows.extend(rows)
    csv_once(out / "fresh_scores.csv", fresh_rows)
    bootstrap, slices = [], []
    selected = selection["selected"]
    for world, part in fresh.groupby("world", sort=False):
        chosen = fresh_predictions[selected].query("world == @world").reset_index(drop=True)
        base = fresh_predictions["v6"].query("world == @world").reset_index(drop=True)
        part = part.reset_index(drop=True)
        if not chosen.invoice_id.equals(part.invoice_id) or not base.invoice_id.equals(part.invoice_id):
            raise ValueError("Paired evaluation row alignment failed")
        for day in (28, 91, 365):
            p, q = (x[[f"p_{day}_{c}" for c in range(4)]].to_numpy() for x in (chosen, base))
            boot = paired_company_bootstrap(part, p, q, day, 400, 20261105)
            boot["delta_brier_vs_v6"] = boot.pop("delta_brier_vs_v5")
            bootstrap.append({"world": world, "model": selected, "day": day, **boot})
            onset = min(pd.Timestamp(e["start"]) for cfg in spec["fresh_worlds"] if cfg["name"] == world for e in cfg["shock_schedule"])
            for label, mask in (("before_episode", part.cutoff.lt(onset)), ("after_episode", part.cutoff.ge(onset)),
                                ("buyer_industry_unknown", part.buyer_industry_unknown.eq(1)),
                                ("partial_receipts", part.paid_frac_so_far.between(1e-9, 1-1e-9))):
                if mask.any():
                    slices.append({"world": world, "day": day, "group": label, "model": selected, **score(part.loc[mask], p[mask], day)})
    csv_once(out / "fresh_bootstrap.csv", bootstrap); csv_once(out / "fresh_slices.csv", slices)
    # Missing industry sensitivity is descriptive only, after final freeze.
    masked = fresh.copy()
    masked[PRACTICAL_CONTEXT_FEATURES] = 0.
    masked[["buyer_industry_unknown", "seller_industry_unknown"]] = 1.
    _, masked_rows = evaluate(out, selected + "_industry_missing", arm_by_name[selected], models[selected], masked, meta, "sensitivity")
    csv_once(out / "industry_missing_sensitivity.csv", masked_rows)
    table = pd.DataFrame(fresh_rows)
    candidate = table[table.model.eq(selected)].set_index(["world", "day"])
    baseline = table[table.model.eq("v6")].set_index(["world", "day"])
    checks = []
    for world in candidate.index.get_level_values("world").unique():
        c, b = candidate.loc[world], baseline.loc[world]
        checks.append({"world": world, "paid_ece_pass": bool(c.paid_ece.le(.05).all()),
                       "writeoff_gap365_pass": bool(abs(c.loc[365, "writeoff_gap"]) <= .03),
                       "short_paid_brier_pass": bool(c.loc[[28, 91], "paid_brier"].le(b.loc[[28, 91], "paid_brier"]*1.02+1e-12).all())})
    preserved = json.loads((out / "preservation_before.json").read_text(encoding="utf-8"))
    changed = [p for p, value in preserved.items() if digest(ROOT / p) != value]
    if changed:
        raise ValueError("Protected historical files changed")
    final = {"selected": selected, "primary_selected": primary["selected"], "augmentation_triggered": trigger,
             "n_original_fit": len(fit), "n_source_validation": len(val), "n_fresh_anchors": len(fresh),
             "fresh_company_count": int(fresh.groupby("world").firm_id.nunique().sum()),
             "fresh_checks": checks, "all_fresh_research_checks_pass": all(all(r[k] for k in ["paid_ece_pass", "writeoff_gap365_pass", "short_paid_brier_pass"]) for r in checks),
             "fresh_selection_performed": False, "test_000_observations_loaded_for_modeling": False, "service_model_changed": False,
             "protected_files_checked": len(preserved), "changed_protected_files": changed,
             "evidence": spec["evidence"], "original_v6_model_sha256": meta["model_sha256"]}
    json_once(out / "summary.json", final)
    print(json.dumps(final, indent=2), flush=True)


if __name__ == "__main__":
    main()
