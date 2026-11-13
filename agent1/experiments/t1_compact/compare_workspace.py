"""Compare the frozen World candidate with the existing Workspace T1/T6 run.

This is a diagnostic on previously inspected demo origins, not model selection
or a new independent test. Neither T6 nor the partial-cash override is tuned.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1.adaptive.compact_t1 import load_workspace_bundle, sha256
from agent1.adaptive.methods import forecast


def run(output, baseline):
    spec = importlib.util.spec_from_file_location("t6_diagnostic_helpers", ROOT/"scripts/business/backtest_t6_baseline.py")
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    data, inventory = helpers.load_demo(baseline/"inputs")
    original = pd.read_csv(baseline/"weekly.csv")
    results, timings = [], []
    plans = output/"workspace_plans"
    plans.mkdir(exist_ok=True)
    for cutoff in original.cutoff.unique():
        bundle = load_workspace_bundle(output/"artifact", cutoff)
        rows = original[original.cutoff == cutoff].reset_index(drop=True)
        start = time.perf_counter()
        cache_path = plans/f"{cutoff}.json"
        if cache_path.exists():
            plan = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            plan = forecast(data, cutoff, float(rows.opening_balance.iloc[0]), bundle,
                            cash_floor=200_000_000, include_operating=False)
            cache_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        print(f"Computed Workspace forecast {cutoff}", flush=True)
        timings.append(dict(cutoff=cutoff, forecast_seconds=time.perf_counter()-start))
        past = helpers.knowledge_snapshot(data, cutoff)
        replay = forecast(past, cutoff, float(rows.opening_balance.iloc[0]), bundle,
                          cash_floor=200_000_000, include_operating=False)
        for a, b in zip(plan["weeks"], replay["weeks"]):
            for key in ("cash_in", "cash_out", "balance", "low", "high"):
                if not np.isclose(a[key], b[key], atol=.01, rtol=0):
                    raise ValueError("Candidate forecast depends on future data")
        cumulative_actual_ar = rows.actual_opening_ar_in.cumsum().to_numpy()
        candidate_ar = np.cumsum([w["cash_in"] for w in plan["weeks"]])
        for i, week in enumerate(plan["weeks"]):
            results.append(dict(cutoff=cutoff, week=i+1, actual_balance=float(rows.actual_balance.iloc[i]),
                                old_balance=float(rows.predicted_balance.iloc[i]), candidate_balance=week["balance"],
                                old_absolute_ar_error=abs(float(rows.cumulative_ar_error.iloc[i])),
                                candidate_absolute_ar_error=abs(float(candidate_ar[i]-cumulative_actual_ar[i])),
                                old_interval_hit=bool(rows.interval_hit.iloc[i]),
                                candidate_interval_hit=bool(week["low"] <= rows.actual_balance.iloc[i] <= week["high"])))
        print(f"Workspace diagnostic {cutoff} complete", flush=True)
    frame = pd.DataFrame(results)
    frame.to_csv(output/"workspace_comparison_weekly.csv", index=False)
    summary = dict(kind="previously_inspected_demo_diagnostic_not_selection", independent_origins=4, company_count=1,
                   old_bank_mae=float(abs(frame.old_balance-frame.actual_balance).mean()),
                   candidate_bank_mae=float(abs(frame.candidate_balance-frame.actual_balance).mean()),
                   old_cumulative_ar_mae=float(frame.old_absolute_ar_error.mean()),
                   candidate_cumulative_ar_mae=float(frame.candidate_absolute_ar_error.mean()),
                   old_bank_coverage=float(frame.old_interval_hit.mean()), candidate_bank_coverage=float(frame.candidate_interval_hit.mean()),
                   future_removal_invariance=True, timings=timings,
                   baseline_summary_sha256=sha256(baseline/"summary.json"), baseline_weekly_sha256=sha256(baseline/"weekly.csv"),
                   artifact_metadata_sha256=sha256(output/"artifact/metadata.json"), input_inventory=inventory,
                   unchanged="T6 simulation settings, partial-cash profile, no operating/new-credit inflows and no invented future expenses")
    (output/"workspace_comparison.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=ROOT/"outputs/t6/baseline_workspace_trained_t1_20261112")
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        run(args.output.resolve(), args.baseline.resolve())
