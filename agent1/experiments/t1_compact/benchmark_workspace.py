"""Time grouped SHAP with the retained large company's real observed context."""
import argparse
import csv
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1.adaptive.compact_t1 import CompactT1, explain_compact, workspace_context


def run(output, inputs):
    # Frozen demo format has only these explicit columns. This benchmark reads
    # three tables, not bank schedules or outcomes after the requested origin.
    data = {}
    for index, kind in ((1, "invoices"), (3, "payments"), (6, "actions")):
        with (inputs/f"{index:02}_{kind}.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows = [{k: v for k, v in r.items() if v != ""} for r in csv.DictReader(stream)]
        for row in rows:
            if "amount" in row:
                row["amount"] = int(row["amount"])
        data[kind] = rows
    started = time.perf_counter()
    model = CompactT1.load(output/"artifact")
    load_seconds = time.perf_counter()-started
    cutoff = "2026-07-31"
    started = time.perf_counter()
    context = workspace_context(data, cutoff)
    context_seconds = time.perf_counter()-started
    opened = context[(context.remaining_amount > .01) & context.written_off_at.isna()].copy()
    opened.attrs["compact_context"] = context
    p = model.distribution(opened)[:, :4].sum(1)
    indices = np.unique(np.linspace(0, len(opened)-1, min(20, len(opened))).round().astype(int))
    records = [dict(invoice_id=str(opened.iloc[i].invoice_id), customer_id=str(opened.iloc[i].customer_id), payment_probability_4w=float(p[i])) for i in indices]
    measured = {}
    for count in (1, len(records)):
        durations = []
        for repeat in range(21):
            rows = [dict(r) for r in records[:count]]
            started = time.perf_counter()
            reference = explain_compact(rows, opened, [(1., model)], cutoff)
            durations.append(time.perf_counter()-started)
        measured[str(count)] = dict(first_call_seconds=durations[0], p50_seconds=float(np.median(durations[1:])),
                                    p95_seconds=float(np.quantile(durations[1:], .95)), max_seconds=max(durations),
                                    repetitions=len(durations), reference_count=reference["count"])
    result = dict(cutoff=cutoff, invoice_history_count=len(context), open_invoice_count=len(opened),
                  model_load_seconds=load_seconds, ledger_context_build_seconds=context_seconds,
                  shap_with_feature_preparation=measured,
                  single_invoice_p95_within_one_second=measured["1"]["p95_seconds"] <= 1.,
                  cold_shap_within_one_second=measured["1"]["first_call_seconds"] <= 1.,
                  scope="SHAP includes feature preparation from the shared observed ledger context. Context construction, model loading, HTTP and full T6 forecasting are measured separately or excluded.",
                  processor=platform.processor(), python=platform.python_version())
    (output/"latency_workspace.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, default=ROOT/"outputs/t6/baseline_workspace_trained_t1_20261112/inputs")
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        run(args.output.resolve(), args.inputs.resolve())
