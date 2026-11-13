"""Predeclared global, local and continued-global comparisons on fresh Worlds."""
from __future__ import annotations
import argparse
import json
import os
import pickle
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
from threadpoolctl import threadpool_limits

from agent1.adaptive.compact_t1 import CompactT1, workspace_context, sha256
from agent1.adaptive.landmark_features import FEATURES, LandmarkEnsemble, LandmarkHazard, LandmarkRule
from agent1.adaptive.landmark_adaptation import continue_neural, pool
from agent1.adaptive.ledger_bridge import workspace_data
from experiments.t1_compact.aligned_data import landmarks, write
from experiments.t1_compact.compare_workspace_worlds import fit_local, serving, distribution, past_data
from experiments.t1_compact.fresh_refit_worlds import prepare
from experiments.t1_compact.refit_landmark import protocol, load_role, measured, sample_risk, OLD
from experiments.t1_compact.train import world_ledgers
from experiments.t1_compact.train_ensemble import weight_grid,empirical_hazards
from experiments.t1_compact.train_landmark import context_for, score_prediction, summarize_prediction

NAMES = ("old_global", "global_refit", "global_reweighted", "global_finetuned", "global_adapted_audited", "local_neural18", "workspace")
COMPARISON = "comparison_current_global"


def execution_protocol(output):
    sources = [Path(__file__), ROOT/"experiments/t1_compact/aligned_data.py",
               ROOT/"experiments/t1_compact/refit_landmark.py",
               *sorted((ROOT/"agent1/adaptive").glob("*.py"))]
    value = dict(frozen_sha256=sha256(output/"frozen.json"),
                 global_protocol_sha256=sha256(output/"protocol.json"),
                 source_sha256={str(p.relative_to(ROOT)):sha256(p) for p in sources},
                 selection_uses_future_test=False, global_retraining_on_test=False,
                 eligible_global_adaptation="past fit/validation/audit only; fixed continuation budgets; audit may reject to global",
                 raw_scratch_is_architecture_control=True)
    value["continuation_base"] = "current frozen 75/25 global; refit remains a separate audited challenger"
    value["continuation_metadata_sha256"] = sha256(OLD/"metadata.json")
    value["replay_scope"] = "aligned original train Worlds only; original validation excluded from continuation replay"
    path = output/"adaptation_current_global_protocol.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != value:
        raise ValueError("Adaptation sources/protocol changed; inspect before resuming")
    if not path.exists():
        write(path,value)


def score(model, frame):
    return measured(model, frame)[0]


def local_frames(ledger, data, origin, world, firm, output, config):
    cache = output / "local_rows" / world / firm / f"{origin.date()}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    def stamp(offset):
        return origin-pd.Timedelta(days=offset)
    pieces = []
    specs = [("fit", list(pd.date_range(stamp(1001), stamp(301), freq="56D")), stamp(210)),
             ("validation", [stamp(210), stamp(182)], stamp(91)),
             ("audit", [stamp(91)], origin)]
    for role, origins, label_end in specs:
        for clock in origins:
            part = landmarks(ledger, data, clock, label_end, world, firm, role,
                             cap=config["max_snapshots_per_origin"], build_cash=role != "fit")
            if len(part):
                pieces.append(part)
    frame = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()
    if len(frame):
        cache.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(cache, index=False)
    return frame


def fit_scratch(reference, frame, maximum):
    x, y, w = sample_risk(frame, 12000)
    if np.unique(y).size<2:
        return LandmarkRule("survival",empirical_hazards(x,y,w)),["One local target class; empirical local Survival fallback, no Neural fitted."]
    estimator = clone(reference.booster)
    estimator.steps[-1][1].set_params(max_iter=maximum, batch_size=min(1024, len(y)))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        estimator.fit(x, y, **{f"{estimator.steps[-1][0]}__sample_weight": w})
    return LandmarkHazard(estimator, reference.name), sorted({str(r.message) for r in caught})


def adapt(global_model, reference, replay, frame, config):
    if frame.empty:
        return {name: global_model for name in ("global_reweighted", "global_finetuned", "global_adapted_audited", "local_neural18")}, dict(status="insufficient_mature_local_windows", audit_passed=False, rows={})
    fit = frame[frame.role == "fit"].reset_index(drop=True)
    val = frame[frame.role == "validation"].reset_index(drop=True)
    audit = frame[frame.role == "audit"].reset_index(drop=True)
    base = {name: global_model for name in ("global_reweighted", "global_finetuned", "global_adapted_audited", "local_neural18")}
    record = dict(rows={"fit": len(fit), "validation": len(val), "audit": len(audit)},
                  local_fit_label_end=str((val.origin.min()).date()) if len(val) else None)
    if len(fit) < config["minimum_fit_rows"] or len(val) < config["minimum_validation_rows"] or len(audit) < config["minimum_audit_rows"]:
        return base, dict(record, status="insufficient_mature_local_windows", audit_passed=False)
    if fit.origin.max()+pd.Timedelta(days=91) > val.origin.min() or val.origin.max()+pd.Timedelta(days=91) > audit.origin.min():
        raise ValueError("Local fit/validation/audit windows overlap labels")
    global_score = score(global_model, val)
    # Reweight the already selected global members; no tenant data fits them.
    options = [[1.]] if len(global_model.members) == 1 else list(weight_grid(len(global_model.members)))
    weighted = []
    for weights in options:
        m = LandmarkEnsemble(global_model.members, weights)
        weighted.append((score(m, val)["score"], list(weights), m))
    _, best_weights, reweighted = min(weighted, key=lambda r: (r[0], r[1]))
    base["global_reweighted"] = reweighted
    x, y, w = sample_risk(fit, 12000)
    candidates, tuning = [], []
    for epochs in config["neural_epochs"]:
        m = continue_neural(reference, x, y, w, replay, epochs=epochs,
                            learning_rate=config["learning_rate"], replay_fraction=config["global_replay_fraction"])
        for weight in config["local_weight_grid"]:
            pooled = pool(global_model, m, weight)
            metrics = score(pooled, val)
            guard = metrics["integrated_brier13"] <= global_score["integrated_brier13"]*1.02+.0001
            tuning.append(dict(epochs=epochs, weight=weight, guard=guard, **metrics))
            if guard:
                candidates.append((metrics["score"], epochs, weight, pooled))
    _, epochs, weight, tuned = min(candidates, key=lambda r: (r[0], r[1], r[2]))
    # Choose the adaptation mode solely on validation; audit can only accept
    # that locked choice or reject to global, not search more modes.
    mode = "finetuned" if score(tuned, val)["score"] < score(reweighted, val)["score"] else "reweighted"
    proposed = tuned if mode == "finetuned" else reweighted
    audit_global, audit_proposed = score(global_model, audit), score(proposed, audit)
    accepted = (audit_proposed["score"] <= audit_global["score"]-config["audit_minimum_gain"]
                and audit_proposed["integrated_brier13"] <= audit_global["integrated_brier13"]*1.02+.0001)
    # Final local refit uses only fully mature observations known by origin.
    # Epochs and weights are locked. Future test evaluates this actual refit.
    full = pd.concat([fit, val, audit], ignore_index=True)
    fx, fy, fw = sample_risk(full, 12000)
    final_neural = continue_neural(reference, fx, fy, fw, replay, epochs=epochs,
                                  learning_rate=config["learning_rate"], replay_fraction=config["global_replay_fraction"])
    base["global_finetuned"] = pool(global_model, final_neural, weight)
    base["global_adapted_audited"] = (base["global_finetuned"] if mode == "finetuned" else reweighted) if accepted else global_model
    scratch, scratch_messages = fit_scratch(reference, full, config["scratch_max_iter"])
    base["local_neural18"] = scratch
    return base, dict(record, status="adapted", reweighted_weights=best_weights,
                      continuation_epochs=epochs, continuation_weight=weight,
                      selected_validation_mode=mode, audit_passed=bool(accepted),
                      audit_global=audit_global, audit_proposed=audit_proposed,
                      final_local_refit=True, frozen_scaler=True, global_replay_fraction=config["global_replay_fraction"],
                      scratch_warnings=scratch_messages, tuning=tuning)


def run_world(output, world):
    execution_protocol(output)
    config = protocol(output)["adaptation"]
    if not (output / "audit_results.json").exists():
        raise ValueError("Global audit must finish before fresh test")
    frozen = json.loads((output / "frozen.json").read_text(encoding="utf-8"))
    if frozen["artifact_metadata_sha256"] != sha256(output / "artifact/metadata.json"):
        raise ValueError("Frozen artifact changed")
    frame = load_role(output, "fresh_test")
    frame = frame[frame.world == world].reset_index(drop=True)
    entry = next(e for e in json.loads((output / "fresh_inventory.json").read_text(encoding="utf-8")) if e["name"] == world)
    refit_model = CompactT1.load(output / "artifact")
    global_model = old = CompactT1.load(OLD)
    reference = next(m for m in global_model.members if isinstance(m,LandmarkHazard) and m.name.startswith("neural"))
    with np.load(output / "current_global_replay.npz", allow_pickle=False) as saved:
        replay = tuple(saved[k] for k in ("x", "y", "weights"))
    for firm, ledger in world_ledgers(output / entry["directory"]):
        data = workspace_data(ledger)
        for origin, part in frame[frame.firm == firm].groupby("origin", sort=True):
            target = output / COMPARISON / world / firm / str(origin.date())
            if (target / "receipt.json").exists():
                receipt = json.loads((target / "receipt.json").read_text(encoding="utf-8"))
                if receipt["prediction_sha256"] != sha256(target / "predictions.npz"):
                    raise ValueError("Comparison cache changed")
                continue
            started = time.perf_counter()
            rows = local_frames(ledger, data, origin, world, firm, output, config)
            models, record = adapt(global_model, reference, replay, rows, config)
            models.update(old_global=old, global_refit=refit_model)
            predictions = {name: model.distribution_from_features(part[list(FEATURES)].to_numpy(float)) for name, model in models.items()}
            local = past_data(data, origin)
            baseline_root=json.loads((output/"target_contract.json").read_text(encoding="utf-8"))["baseline_cache"] if (output/"target_contract.json").exists() else None
            reused=None
            if baseline_root:
                old_path=Path(baseline_root)/COMPARISON/world/firm/str(origin.date())
                old_receipt=json.loads((old_path/"receipt.json").read_text(encoding="utf-8"))
                if sha256(old_path/"models.pkl")!=old_receipt["models_sha256"] or sha256(old_path/"predictions.npz")!=old_receipt["prediction_sha256"]:
                    raise ValueError("Workspace baseline cache changed")
                old_rows=pd.read_parquet(Path(baseline_root)/"prepared"/f"{world}.parquet")
                old_rows=old_rows[(old_rows.firm==firm)&(old_rows.origin==origin)]
                np.testing.assert_array_equal(old_rows.invoice_id,part.invoice_id)
                np.testing.assert_array_equal(old_rows[list(FEATURES)],part[list(FEATURES)])
                with (old_path/"models.pkl").open("rb") as stream:
                    bundle=pickle.load(stream)["workspace"]
                messages,fallback=old_receipt["workspace_warnings"],old_receipt["workspace_fallback"]
                reused=dict(directory=str(old_path),models_sha256=old_receipt["models_sha256"],unchanged_workspace_inputs=True)
            else:
                bundle, messages, fallback = fit_local(local, origin)
            history = workspace_context(local, origin)
            targets = history.set_index("invoice_id").loc[part.invoice_id].reset_index()
            targets.attrs["compact_context"] = history
            np.testing.assert_allclose(global_model.prepare(targets), part[list(FEATURES)].to_numpy(float), atol=1e-12, rtol=0)
            predictions["workspace"] = distribution(serving(bundle, history, origin), targets, origin)
            if reused:
                with np.load(Path(reused["directory"])/"predictions.npz",allow_pickle=False) as cached_baseline:
                    np.testing.assert_allclose(predictions["workspace"],cached_baseline["workspace"],atol=1e-12,rtol=0)
                reused["predictions_reconstructed_exactly"]=True
            if record["status"] != "adapted":
                # A local-only control must not silently borrow the pretrained
                # global model when its local fitting windows are insufficient.
                predictions["local_neural18"] = predictions["workspace"].copy()
                models["local_neural18"] = None
                record["scratch_fallback"] = "workspace_history_baseline"
            target.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(target / "predictions.npz", **predictions)
            # Runtime bundles are retained for direct forecast/SHAP integration.
            with (target / "models.pkl").open("wb") as stream:
                pickle.dump(dict(models=models, workspace=bundle), stream)
            record.update(world=world, firm=firm, origin=str(origin.date()), anchors=len(part),
                          workspace_method=bundle["selected_method"] if bundle else "customer_fallback",
                          workspace_audit=bundle["audit"] if bundle else None,
                          workspace_fallback=fallback, workspace_warnings=messages,
                          workspace_reused=reused,
                          prediction_sha256=sha256(target / "predictions.npz"),
                          models_sha256=sha256(target / "models.pkl"),
                          frozen_sha256=sha256(output / "frozen.json"), seconds=time.perf_counter()-started)
            write(target / "receipt.json", record)
            print(json.dumps(dict(event="context", world=world, firm=firm, origin=str(origin.date()),
                                  status=record["status"], audit=record["audit_passed"], seconds=record["seconds"])), flush=True)


def summarize(output):
    frame = load_role(output, "fresh_test")
    predictions = {name: np.zeros((len(frame), 14)) for name in NAMES}
    records = []
    for (world, firm, origin), part in frame.groupby(["world", "firm", "origin"], sort=True):
        target = output / COMPARISON / world / firm / str(origin.date())
        records.append(json.loads((target / "receipt.json").read_text(encoding="utf-8")))
        with np.load(target / "predictions.npz", allow_pickle=False) as saved:
            for name in NAMES:
                predictions[name][part.index] = saved[name]
    ctx = context_for(frame)
    results, rows = {}, []
    for name, p in predictions.items():
        results[name] = score_prediction(summarize_prediction(p, ctx), ctx)
        for key, indices in frame.groupby(["world", "firm", "origin"]).indices.items():
            sub = frame.iloc[indices].reset_index(drop=True)
            context = context_for(sub)
            metrics = score_prediction(summarize_prediction(p[indices], context), context)
            rows.append(dict(model=name, world=key[0], firm=key[1], origin=str(key[2].date()), **{k:v for k,v in metrics.items() if k != "windows"}))
    table = pd.DataFrame(rows)
    table.to_csv(output / "fresh_by_firm_origin.csv", index=False)
    firm_scores = table.groupby(["world", "firm", "model"]).score.mean().unstack("model")
    rng = np.random.default_rng(261112)
    comparisons = {}
    for name in NAMES:
        delta = firm_scores.workspace-firm_scores[name]
        samples = []
        for _ in range(5000):
            samples.append(np.mean([rng.choice(group.to_numpy(), len(group), replace=True).mean() for _, group in delta.groupby(level="world")]))
        comparisons[name] = dict(workspace_minus_model=float(delta.groupby(level="world").mean().mean()),
                                 ci95=list(map(float,np.quantile(samples,[.025,.975]))),
                                 firms_better_than_workspace=int((delta>0).sum()), firms=len(delta))
    slices = []
    masks = dict(partial_receipts=frame.received_fraction>0, no_receipts=frame.received_fraction==0,
                 new_customer=frame.customer_settlements_raw==0,
                 sparse_customer=frame.customer_settlements_raw<5,
                 overdue90=frame.age_days-frame.term_days>90)
    for label, mask in masks.items():
        ids = np.flatnonzero(mask)
        if not len(ids):
            continue
        subctx = context_for(frame.iloc[ids].reset_index(drop=True))
        for name, p in predictions.items():
            metrics = score_prediction(summarize_prediction(p[ids], subctx), subctx)
            slices.append(dict(slice=label, model=name, anchors=len(ids), **{k:v for k,v in metrics.items() if k != "windows"}))
    pd.DataFrame(slices).to_csv(output / "fresh_slices.csv", index=False)
    firm_scores.to_csv(output / "fresh_by_firm.csv")
    write(output / "fresh_results.json", dict(results=results, comparisons=comparisons,
                                              anchors=len(frame), worlds=frame.world.nunique(), firms=len(firm_scores),
                                              contexts=len(records), adapted_contexts=sum(r["status"]=="adapted" for r in records),
                                              audit_accepted_contexts=sum(r["audit_passed"] for r in records),
                                              global_refitting_on_test=False, dated_local_adaptation=True))
    print(json.dumps(results), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/t1/aligned_refit_20261112")
    parser.add_argument("--world")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    with threadpool_limits(limits=2), threadpool_limits(limits=1, user_api="blas"):
        if args.prepare:
            if not (args.output / "audit_results.json").exists():
                raise ValueError("Fresh test opens only after global audit")
            if (args.output/"target_contract.json").exists():
                from experiments.t1_compact.build_corrected_study import copy_role
                copy_role(args.output.resolve(),"fresh_test")
            else:
                prepare(args.output, "fresh_test")
        if args.world:
            run_world(args.output.resolve(), args.world)
        if args.summarize:
            summarize(args.output.resolve())
