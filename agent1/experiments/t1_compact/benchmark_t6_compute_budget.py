"""Compare Monte Carlo and SHAP budgets in an isolated forecast experiment.

Production forecast settings are read from source. Only this process substitutes
the simulation count and limits explanation calls. Every invoice still enters
cash forecasting, and the displayed collection queue remains intact.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
import inspect
import os
from pathlib import Path
import statistics
import sys
import time

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
from threadpoolctl import threadpool_limits

from agent1.adaptive import explanations, methods
from agent1.adaptive.compact_t1 import load_workspace_bundle, sha256
from experiments.t1_compact.compare_workspace_worlds import (
    LANDMARK, SOURCE, past_data, workspace_data, write_json,
)
from experiments.t1_compact.train import world_ledgers


def forecast_with_simulations(simulations):
    """Change only literal path counts in a private copy of forecast()."""
    tree = ast.parse(inspect.getsource(methods.forecast))
    replacements = []

    class SimulationCount(ast.NodeTransformer):
        def visit_Constant(self, node):
            if type(node.value) is int and node.value == 400:
                replacements.append(node.lineno)
                return ast.copy_location(ast.Constant(value=simulations), node)
            return node

    tree = SimulationCount().visit(tree)
    if not replacements:
        raise ValueError("Forecast no longer has the expected simulation settings")
    simulation_timing = {"started": 0., "seconds": 0.}

    def start_simulation_timer():
        simulation_timing["started"] = time.perf_counter()

    def stop_simulation_timer():
        simulation_timing["seconds"] = time.perf_counter() - simulation_timing["started"]

    function = tree.body[0]
    instrumented, starts, stops = [], 0, 0
    for statement in function.body:
        targets = statement.targets if isinstance(statement, ast.Assign) else []
        if any(isinstance(target, ast.Name) and target.id == "rng" for target in targets):
            instrumented.append(ast.Expr(ast.Call(func=ast.Name(id="_start_simulation_timer", ctx=ast.Load()), args=[], keywords=[])))
            starts += 1
        instrumented.append(statement)
        if any(isinstance(target, ast.Tuple)
               and [name.id for name in target.elts if isinstance(name, ast.Name)] == ["low", "high"]
               for target in targets):
            instrumented.append(ast.Expr(ast.Call(func=ast.Name(id="_stop_simulation_timer", ctx=ast.Load()), args=[], keywords=[])))
            stops += 1
    if (starts, stops) != (1, 1):
        raise ValueError("Could not locate the complete Monte Carlo block")
    function.body = instrumented
    namespace = dict(methods.forecast.__globals__)
    namespace.update(_start_simulation_timer=start_simulation_timer,
                     _stop_simulation_timer=stop_simulation_timer)
    exec(compile(ast.fix_missing_locations(tree), "<forecast-budget-experiment>", "exec"), namespace)
    return namespace["forecast"], replacements, simulation_timing


@contextmanager
def explanation_budget(limit):
    original = explanations.explain_collections
    timing = {"seconds": 0., "explained_rows": 0}

    def explain_first(rows, *args, **kwargs):
        selected = rows[:limit]
        started = time.perf_counter()
        reference = original(selected, *args, **kwargs)
        timing["seconds"] += time.perf_counter() - started
        timing["explained_rows"] += len(selected)
        output_field = kwargs.get("output_field", "payment_explanation")
        for row in rows[limit:]:
            row[output_field] = {"status": "deferred", "reason": "experimental_explanation_budget"}
        return reference

    explanations.explain_collections = explain_first
    try:
        yield timing
    finally:
        explanations.explain_collections = original


def run(output, repetitions):
    world, firm, cutoff = "compact_06_test", "F014", "2025-09-29"
    ledger = next(ledger for name, ledger in world_ledgers(SOURCE / "worlds" / world) if name == firm)
    data = past_data(workspace_data(ledger), cutoff)
    bundle = load_workspace_bundle(LANDMARK / "artifact", cutoff)
    settings = [(400, 30), (1000, 30), (1000, 10)]
    forecasts = {simulations: forecast_with_simulations(simulations)
                 for simulations in (400, 1000)}
    records = {setting: [] for setting in settings}
    reference_point, reference_queue = None, None
    # Warm the complete data/forecast path before rotating measured case order.
    with explanation_budget(10):
        forecasts[1000][0](data, cutoff, 0., bundle)
    for repeat in range(repetitions):
        offset = repeat % len(settings)
        for simulations, shap_limit in settings[offset:] + settings[:offset]:
            forecast, replaced_lines, simulation_timing = forecasts[simulations]
            with explanation_budget(shap_limit) as timing:
                started = time.perf_counter()
                plan = forecast(data, cutoff, 0., bundle)
                seconds = time.perf_counter() - started
            point = np.asarray([[week[key] for key in ("cash_in", "cash_out", "balance")]
                                for week in plan["weeks"]])
            queue = [(row["invoice_id"], row["payment_probability_4w"]) for row in plan["collections"]]
            if reference_point is None:
                reference_point, reference_queue = point, queue
            np.testing.assert_allclose(point, reference_point, atol=.01, rtol=0)
            if queue != reference_queue:
                raise ValueError("Compute budget changed collection ranking or payment probabilities")
            records[(simulations, shap_limit)].append(dict(
                repetition=repeat+1, forecast_seconds=seconds,
                shap_seconds=timing["seconds"], simulation_seconds=simulation_timing["seconds"],
                other_seconds=seconds-timing["seconds"]-simulation_timing["seconds"],
                explained_rows=timing["explained_rows"],
                displayed_invoices=len(plan["collections"]), open_invoices=plan["open_invoices"]))
            print(f"paths={simulations}, SHAP={shap_limit}, run={repeat+1}, total={seconds:.3f}s, MC={simulation_timing['seconds']:.4f}s, SHAP={timing['seconds']:.3f}s", flush=True)
    cases = []
    for simulations, shap_limit in settings:
        runs = records[(simulations, shap_limit)]
        cases.append(dict(simulations=simulations, shap_limit=shap_limit,
                          median_forecast_seconds=statistics.median(r["forecast_seconds"] for r in runs),
                          median_shap_seconds=statistics.median(r["shap_seconds"] for r in runs),
                          median_simulation_seconds=statistics.median(r["simulation_seconds"] for r in runs),
                          median_other_seconds=statistics.median(r["other_seconds"] for r in runs),
                          replaced_source_lines=forecasts[simulations][1], runs=runs))
    result = dict(world=world, firm=firm, cutoff=cutoff, horizon_weeks=13,
                  repetitions=repetitions, threads=2, cases=cases,
                  forecast_source_sha256=sha256(Path(methods.__file__)),
                  experiment_source_sha256=sha256(Path(__file__)),
                  model_metadata_sha256=sha256(LANDMARK / "artifact/metadata.json"),
                  all_point_forecasts_equal=True, collection_queue_unchanged=True,
                  production_settings_changed=False,
                  case_order="one full warmup followed by rotating case order in each repetition",
                  measurement="warm model, full forecast including context construction and explanations",
                  limitation="one synthetic company/origin; zero opening balance is a compute fixture; median timing is not a latency SLA or accuracy test")
    write_json(output / "compute_budget_comparison.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("repetitions must be positive")
    with threadpool_limits(limits=2):
        run(args.output.resolve(), args.repetitions)
