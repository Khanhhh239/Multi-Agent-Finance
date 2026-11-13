"""Actual T6/SHAP replay and multi-context Monte Carlo budget verification."""
from __future__ import annotations
import argparse
import json
import os
import pickle
from pathlib import Path
import sys
import time

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from agent1.adaptive.compact_t1 import workspace_context, sha256
from experiments.t1_compact.historical_workspace import partial_distribution, forecast
from agent1.adaptive.ledger_bridge import workspace_data, CONTRACT
from experiments.t1_compact.aligned_data import write
from experiments.t1_compact.compare_workspace_worlds import past_data, serving, shap_latency
from experiments.t1_compact.refit_landmark import load_role
from experiments.t1_compact.train import world_ledgers
from experiments.t1_compact.train_ensemble import benchmark_ensemble
from experiments.t1_compact.compare_adaptation import COMPARISON


def bundle_for(model, base, cutoff, adapted=False):
    result = dict(base or {})
    result.update(model=model, anchor=model, weight=1., asof=str(cutoff.date()),
                  selected_method="global_adapted", feature_schema=model.feature_schema)
    result["t1_provenance"]=dict(source="research_company_adapted" if adapted else "research_global_retained",
                                  local_adaptation=adapted,synthetic=True,real_pilot_accepted=False)
    return result


def run(output):
    frame = load_role(output, "fresh_test")
    inventory = json.loads((output / "fresh_inventory.json").read_text(encoding="utf-8"))
    contexts = []
    for entry in inventory:
        if entry["role"] != "fresh_test":
            continue
        origin = frame[frame.world == entry["name"]].origin.max()
        best = None
        for firm, ledger in world_ledgers(output / entry["directory"]):
            data = workspace_data(ledger)
            history = workspace_context(data, origin)
            opened = history[(history.remaining_amount > .01) & history.written_off_at.isna()].copy()
            opened.attrs["compact_context"] = history
            if len(opened) and (best is None or len(opened)>len(best["opened"])):
                best = dict(name=f"{entry['name']}/{firm}", world=entry["name"], firm=firm,
                            data=data, origin=origin, opened=opened)
        contexts.append(best)
    records, timings, mc_results = [], [], []
    models_to_measure = ("old_global", "global_refit", "global_finetuned", "global_adapted_audited", "local_neural18")
    latency = {}
    for context in contexts:
        origin, world, firm = context["origin"], context["world"], context["firm"]
        path = output / COMPARISON / world / firm / str(origin.date()) / "models.pkl"
        with path.open("rb") as stream:
            saved = pickle.load(stream)
        data, opened = context["data"], context["opened"]
        local = past_data(data, origin)
        for name in models_to_measure:
            model = saved["models"][name]
            if model is None:
                latency[f"{context['name']}/{name}"] = dict(status="local_model_unavailable", fallback="workspace")
                continue
            measured = benchmark_ensemble(model, [context], repetitions=20)
            latency[f"{context['name']}/{name}"] = measured
        # Workspace has a different explanation protocol; measure the actual
        # selected components rather than pretending it shares 18 features.
        history = workspace_context(local, origin)
        components = serving(saved["workspace"], history, origin)
        local_latency = shap_latency(opened, components, origin, output / "runtime_workspace", world+"_"+firm)
        latency[f"{context['name']}/workspace"] = local_latency
        model = saved["models"]["global_adapted_audited"]
        receipt=json.loads((path.parent/"receipt.json").read_text(encoding="utf-8"))
        bundle = bundle_for(model, saved["workspace"], origin, receipt["audit_passed"])
        plan = forecast(data, str(origin.date()), 0., bundle, simulation_paths=1000, shap_limit=30)
        truncated = forecast(local, str(origin.date()), 0., bundle, simulation_paths=1000, shap_limit=0)
        p = model.distribution(opened)
        cash, _ = partial_distribution(data, opened, origin, p)
        expected = (cash[:, :13]*opened.remaining_amount.to_numpy(float)[:,None]).sum(0)
        np.testing.assert_allclose([r["cash_in"] for r in plan["weeks"]], expected, atol=.01, rtol=0)
        for field in ("cash_in", "cash_out", "balance", "low", "high", "below_floor_probability"):
            np.testing.assert_allclose([r[field] for r in plan["weeks"]], [r[field] for r in truncated["weeks"]], atol=.01, rtol=0)
        errors = [r["payment_explanation"]["additivity_error"] for r in plan["collections"]]
        if errors and max(errors)>1e-10:
            raise ValueError("Runtime SHAP additivity failed")
        write(output / "runtime_plans" / f"{world}_{firm}.json", plan)
        records.append(dict(context=context["name"], open_invoices=len(opened), explained=len(errors),
                            max_additivity_error=max(errors,default=0.), future_removal_invariance=True,
                            full_cash_forecast_agreement=True, opening_balance_fixture=0))
        # Warm complete paths, then rotate measured budgets. No AST rewrites
        # or monkeypatches: these are the public forecast parameters.
        settings = [(400,30),(1000,30),(1000,10)]
        reference_queue = [(r["invoice_id"],r["payment_probability_4w"]) for r in plan["collections"]]
        point = np.array([[r[k] for k in ("cash_in","cash_out","balance")] for r in plan["weeks"]])
        for repeat in range(3):
            order = settings[repeat:]+settings[:repeat]
            for paths, count in order:
                started = time.perf_counter()
                current = forecast(local, str(origin.date()), 0., bundle, simulation_paths=paths, shap_limit=count)
                seconds = time.perf_counter()-started
                np.testing.assert_allclose(np.array([[r[k] for k in ("cash_in","cash_out","balance")] for r in current["weeks"]]),point,atol=.01,rtol=0)
                if [(r["invoice_id"],r["payment_probability_4w"]) for r in current["collections"]] != reference_queue:
                    raise ValueError("Compute budget changed the collection queue")
                timings.append(dict(context=context["name"], simulation_paths=paths, shap_limit=count,
                                    repeat=repeat, seconds=seconds, open_invoices=len(opened)))
        # Numerical simulation variability, against a 10000-path reference.
        # This measures MC precision, not real cash-interval calibration.
        precision_floor=float(np.median(np.cumsum(expected)))
        reference = forecast(local,str(origin.date()),0.,bundle,simulation_paths=10000,shap_limit=0,cash_floor=precision_floor)
        reference_band = np.array([[r[k] for k in ("low","high")] for r in reference["weeks"]])
        reference_risk = np.array([r["below_floor_probability"] for r in reference["weeks"]])
        for paths in (400,1000):
            for seed in range(5):
                current = forecast(local,str(origin.date()),0.,bundle,simulation_paths=paths,shap_limit=0,simulation_seed=seed,cash_floor=precision_floor)
                band = np.array([[r[k] for k in ("low","high")] for r in current["weeks"]])
                risk = np.array([r["below_floor_probability"] for r in current["weeks"]])
                mc_results.append(dict(context=context["name"], simulation_paths=paths, seed=seed,
                                       cash_floor_fixture=precision_floor,
                                       band_absolute_difference_vnd=float(abs(band-reference_band).mean()),
                                       risk_absolute_difference=float(abs(risk-reference_risk).mean())))
        write(output / "runtime_verification.json", dict(passed=True, contexts=records, partial=True))
        write(output / "runtime_shap.json", latency)
        print(f"Verified T6/SHAP and budgets: {context['name']}",flush=True)
    table = pd.DataFrame(timings)
    table.to_csv(output / "compute_budget_runs.csv",index=False)
    table.groupby(["simulation_paths","shap_limit"]).seconds.agg(["count","median","min","max"]).to_csv(output / "compute_budget_summary.csv")
    pd.DataFrame(mc_results).to_csv(output / "monte_carlo_precision.csv",index=False)
    write(output / "runtime_verification.json", dict(passed=True, contexts=records, partial=False,
         expected_cash_invariant_to_mc=True, collection_queue_invariant_to_budget=True,
         fixture_scope="AR-only with zero opening balance; not a bank-balance accuracy backtest"))
    audit = json.loads((output / "audit_results.json").read_text(encoding="utf-8"))
    selected = "artifact" if audit["passed"] else "serving_artifact"
    serving_key = "/global_refit" if audit["passed"] else "/old_global"
    global_shap_pass = all(value["passed"] for key,value in latency.items() if key.endswith(serving_key))
    accepted = bool(global_shap_pass)
    required = [selected+"/metadata.json","frozen.json","audit_results.json","fresh_results.json","verification.json","adaptation_current_global_protocol.json","runtime_verification.json","runtime_shap.json"]
    write(output / "release.json", dict(research_integration_accepted=accepted, real_pilot_accepted=False,
          feature_context_contract=CONTRACT, artifact_directory=selected, refit_accepted=bool(audit["passed"]),
          required_hashes={name:sha256(output/name) for name in required},
          service_default_automatically_changed=False, global_shap_pass=global_shap_pass))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=ROOT/"outputs/t1/aligned_refit_20261112")
    args = parser.parse_args()
    with threadpool_limits(limits=2), threadpool_limits(limits=1,user_api="blas"):
        run(args.output.resolve())
