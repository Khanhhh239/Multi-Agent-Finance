"""Aligned candidate selection, refit, independent weights and fresh audit/test.

Run each phase in order. Fresh test is not opened until artifact and audit are
locked. Historical test stays a separately labelled regression diagnostic.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import time
import warnings

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.pipeline import Pipeline
from threadpoolctl import threadpool_limits

from agent1.adaptive.compact_t1 import CompactT1, sha256, workspace_context
from agent1.adaptive.landmark_features import FEATURES, SCHEMA, LandmarkHazard, LandmarkRule, LandmarkEnsemble
from agent1.adaptive.ledger_bridge import workspace_data, CONTRACT
from experiments.t1_compact.aligned_data import prepare_existing, write
from experiments.t1_compact.fresh_refit_worlds import generate, generate_onboarding, prepare, DESIGN, ORIGINS, ONBOARDING
from experiments.t1_compact.train import risk_rows, world_ledgers
from experiments.t1_compact.train_ensemble import candidate_specs, empirical_hazards, weight_grid, benchmark_ensemble
from experiments.t1_compact.train_landmark import fit_candidates, select, context_for, summarize_prediction, score_prediction

SOURCE = ROOT / "outputs/t1/compact_world_20261112"
OLD = ROOT / "outputs/t1/landmark18_survival_cash_20261112/artifact"


def protocol(output):
    value = dict(version="aligned-landmark-refit-v1", contract=CONTRACT, features=list(FEATURES),
                 source_inventory_sha256=sha256(SOURCE / "inventory.json"), candidates=candidate_specs(),
                 neural_max_iter=[400, 600], require_neural_convergence=True,
                 risk_row_limit=100000, seed=261112, maximum_members=3, weight_step=.05,
                 initial_fit="8 existing train Worlds, 2020-01 to 2023-09, labels through 2023-12",
                 selection="3 existing validation Worlds, Jan-Mar 2024, labels through June 2024",
                 refit="selected member configurations, train + original validation, fresh deterministic 100000 risk-row sample",
                 post_refit_weights="two new Worlds, Jul-Dec 2024; members/configurations locked, labels through 2025-03-31",
                 available_asof="2025-04-01", independent_world_design=DESIGN, origins=ORIGINS,
                 additional_fresh_test=ONBOARDING,
                 stability=dict(minimum_mean_gain=.0001, minimum_window_gain=.00001,
                                minimum_window_fraction=.75, maximum_window_regression=.001),
                 audit_gate=dict(max_cash_score_ratio_to_old=1.02, max_ibrier_ratio_to_old=1.02,
                                 ibrier_slack=.0001, single_invoice_shap_p95_seconds=1.),
                 adaptation=dict(fit_offsets_days=[1001, 301], stride_days=56,
                                 validation_offsets_days=[210, 182], audit_offset_days=91,
                                 fit_label_end_offset=210, max_snapshots_per_origin=50,
                                 neural_epochs=[5, 20], learning_rate=.0001,
                                 global_replay_fraction=.30, local_weight_grid=[0., .25, .5, .75, 1.],
                                 audit_minimum_gain=.0001, minimum_fit_rows=60,
                                 minimum_validation_rows=20, minimum_audit_rows=20,
                                 scratch_max_iter=400,
                                 final_refit="locked adaptation mode/epochs/weight, all mature local fit+validation+audit rows; no future labels"),
                 evaluation="equal World/firm/origin cash score 50% weekly + 50% cumulative; Brier and SHAP diagnostics; paired firm bootstrap",
                 limitations=["All Worlds share one simulator family; fresh seeds do not establish real-company performance.",
                              "Local adaptation of a test tenant is allowed using its past only, never global cross-tenant fitting.",
                              "Old test results are regression diagnostics, never new independent evidence."])
    if (output/"target_contract.json").exists():
        value["version"]="aligned-landmark-refit-cash-calendar-v2"
        value["target_contract_sha256"]=sha256(output/"target_contract.json")
    path = output / "protocol.json"
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != value:
            raise ValueError("Protocol changed; use a new run directory")
    else:
        write(path, value)
    return value


def load_role(output, role):
    paths = []
    for path in sorted((output / "prepared").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["role"] == role:
            data = path.with_suffix(".parquet")
            if sha256(data) != record["sha256"]:
                raise ValueError("Prepared input changed")
            paths.append(data)
    return pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)


def contexts(output, frame, source=SOURCE):
    inventory_file = source / ("inventory.json" if source == SOURCE else "fresh_inventory.json")
    inventory = json.loads(inventory_file.read_text(encoding="utf-8"))
    result = []
    for world in sorted(frame.world.unique()):
        entry = next(e for e in inventory if e["name"] == world)
        origin = frame[frame.world == world].origin.max()
        largest = None
        for firm, ledger in world_ledgers(source / entry["directory"]):
            history = workspace_context(workspace_data(ledger), origin)
            opened = history[(history.remaining_amount > .01) & history.written_off_at.isna()].copy()
            opened.attrs["compact_context"] = history
            if len(opened) and (largest is None or len(opened) > len(largest["opened"])):
                largest = dict(name=f"{world}/{firm}", origin=origin, opened=opened)
        result.append(largest)
    return result


def sample_risk(frame, limit=100000):
    x, y, w = risk_rows(frame, tuple(range(18)), FEATURES)
    idx = np.sort(np.random.default_rng(261112).choice(len(y), min(len(y), limit), replace=False))
    w = w[idx]
    return x[idx], y[idx], w * len(w) / w.sum()


def fit_like(model, frame):
    x, y, w = sample_risk(frame)
    messages = []
    if isinstance(model, LandmarkRule):
        return LandmarkRule(model.name, empirical_hazards(x, y, w)), messages
    estimator = clone(model.booster)
    options = {f"{estimator.steps[-1][0]}__sample_weight": w} if isinstance(estimator, Pipeline) else {"sample_weight": w}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        estimator.fit(x, y, **options)
    messages = sorted({str(r.message) for r in caught})
    if model.name.startswith("neural") and any("Maximum iterations" in m for m in messages):
        raise ValueError("Refit neural did not converge; artifact not accepted")
    return LandmarkHazard(estimator, model.name), messages


def measured(model, frame):
    ctx = context_for(frame)
    p = model.distribution_from_features(frame[list(FEATURES)].to_numpy(float))
    return score_prediction(summarize_prediction(p, ctx), ctx), p


def run_train(output):
    config = protocol(output)
    if (output / "frozen.json").exists():
        print("Artifact already frozen", flush=True)
        return
    train, val = load_role(output, "train"), load_role(output, "validation")
    if set(train.world) & set(val.world) or train.origin.max()+pd.Timedelta(days=91) >= val.origin.min():
        raise ValueError("Training/selection leakage")
    models, predictions, ctx = fit_candidates(train, val, output, config)
    initial, selection = select(models, predictions, ctx, contexts(output, val), output, config)
    initial.save(output / "pre_refit_artifact", dict(available_asof="2024-07-01", contract=CONTRACT))
    chosen = selection["selected"]["members"]
    combined = pd.concat([train, val], ignore_index=True)
    fitted = []
    for name in chosen:
        model, messages = fit_like(models[name], combined)
        directory = output / "refit_members" / name
        model.save(directory, dict(contract=CONTRACT, warnings=messages, refit=True))
        fitted.append(model)
        print(f"Refit {name}: {messages}", flush=True)
    # Keep a converged Neural reference for the predeclared local continuation
    # experiment, even if the global selection did not retain a Neural member.
    neural_names = [n for n in models if n.startswith("neural")]
    best_neural = min(neural_names, key=lambda n: score_prediction(predictions[n], ctx)["score"])
    reference, messages = fit_like(models[best_neural], combined)
    reference.save(output / "adaptation_neural", dict(contract=CONTRACT, warnings=messages, refit=True))
    x, y, w = sample_risk(combined, 4096)
    np.savez_compressed(output / "global_replay.npz", x=x, y=y, weights=w)
    weight_val = load_role(output, "weight_validation")
    ctx = context_for(weight_val)
    member_p = [m.distribution_from_features(weight_val[list(FEATURES)].to_numpy(float)) for m in fitted]
    options = [[1.]] if len(fitted) == 1 else list(weight_grid(len(fitted)))
    trials = []
    for weights in options:
        p = sum(w*p for w, p in zip(weights, member_p))
        trials.append(dict(weights=list(weights), **score_prediction(summarize_prediction(p, ctx), ctx)))
    best = min(trials, key=lambda r: (r["score"], r["weights"]))
    model = LandmarkEnsemble(fitted, best["weights"])
    latency = benchmark_ensemble(model, contexts(output, weight_val, source=output))
    write(output / "post_refit_weight_selection.json", dict(trials=trials, selected=best, latency=latency,
                                                            original_selection_weights=selection["selected"]["weights"]))
    if not latency["passed"]:
        raise ValueError("Post-refit artifact failed SHAP budget")
    model.save(output / "artifact", dict(available_asof=config["available_asof"], synthetic=True,
               activation="research_candidate", data_fingerprint=sha256(output / "protocol.json"),
               source_sha256=sha256(ROOT / "agent1/adaptive/landmark_features.py"),
               feature_context_contract=CONTRACT, refit=True, selection_members=chosen,
               protocol_sha256=sha256(output / "protocol.json")))
    frozen = dict(artifact_metadata_sha256=sha256(output / "artifact/metadata.json"),
                  protocol_sha256=sha256(output / "protocol.json"), members=chosen, weights=best["weights"],
                  weight_selection_sha256=sha256(output / "post_refit_weight_selection.json"),
                  adaptation_neural_sha256=sha256(output / "adaptation_neural/metadata.json"),
                  replay_sha256=sha256(output / "global_replay.npz"),
                  source_sha256={str(p.relative_to(ROOT)): sha256(p) for p in [
                      *sorted((ROOT / "agent1/adaptive").glob("*.py")), Path(__file__),
                      ROOT / "experiments/t1_compact/aligned_data.py", ROOT / "experiments/t1_compact/fresh_refit_worlds.py",
                      ROOT / "experiments/t1_compact/train_landmark.py"]})
    write(output / "frozen.json", frozen)
    print(json.dumps(dict(event="refit_frozen", members=chosen, weights=best["weights"])), flush=True)


def audit(output):
    frozen = json.loads((output / "frozen.json").read_text(encoding="utf-8"))
    if frozen["artifact_metadata_sha256"] != sha256(output / "artifact/metadata.json"):
        raise ValueError("Artifact changed after freeze")
    if (output/"target_contract.json").exists():
        from experiments.t1_compact.build_corrected_study import copy_role
        frame=copy_role(output,"audit")
    else:
        frame = prepare(output, "audit")
    results = {}
    for name, directory in [("refit", output / "artifact"), ("old_global", OLD), ("pre_refit", output / "pre_refit_artifact")]:
        results[name], p = measured(CompactT1.load(directory), frame)
        np.savez_compressed(output / f"audit_{name}.npz", distribution=p)
    guard = protocol(output)["audit_gate"]
    passed = (results["refit"]["score"] <= results["old_global"]["score"]*guard["max_cash_score_ratio_to_old"]
              and results["refit"]["integrated_brier13"] <= results["old_global"]["integrated_brier13"]*guard["max_ibrier_ratio_to_old"]+guard["ibrier_slack"])
    write(output / "audit_results.json", dict(results=results, passed=bool(passed),
                                             frozen_sha256=sha256(output / "frozen.json"),
                                             audit_used_for_retraining=False))
    print(json.dumps(dict(event="audit", passed=bool(passed), results=results)), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/t1/aligned_refit_20261112")
    parser.add_argument("--phase", required=True, choices=["prepare", "train", "audit"])
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(exist_ok=True, parents=True)
    with threadpool_limits(limits=2), threadpool_limits(limits=1, user_api="blas"):
        protocol(output)
        if args.phase == "prepare":
            generate(SOURCE, output)
            generate_onboarding(SOURCE, output)
            prepare_existing(SOURCE, output, "train")
            prepare_existing(SOURCE, output, "validation")
            prepare(output, "weight_validation")
        elif args.phase == "train":
            run_train(output)
        else:
            audit(output)
