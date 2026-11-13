"""Measure the frozen 18-feature ensemble on every test firm's last cohort."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
from threadpoolctl import threadpool_limits
from agent1.adaptive.compact_t1 import CompactT1, explain_compact, sha256
from experiments.t1_compact.compare_workspace_worlds import SOURCE, LANDMARK, read_json, write_json
from experiments.t1_compact.train import world_ledgers


def run(output):
    model = CompactT1.load(LANDMARK / "artifact")
    definition = dict(
        version="world18-shap-multiple-tenants-v1", diagnostic_only=True,
        source_sha256=sha256(Path(__file__)),
        model_metadata_sha256=sha256(LANDMARK / "artifact/metadata.json"),
        target="full ensemble probability of cash settlement within 4 weeks",
        sampling="20 distinct invoices spaced by outstanding amount in each firm's last test origin",
        threads=2, cache="fresh per request", model_loading_included=False,
        ledger_context_construction_included=False, feature_preparation_included=True,
        concurrent_training_may_be_running=True,
    )
    path = output / "world18_shap_protocol.json"
    if path.exists() and read_json(path) != definition:
        raise ValueError("SHAP benchmark definition changed")
    write_json(path, definition)
    results = []
    for entry in read_json(SOURCE / "inventory.json"):
        if entry["role"] != "test":
            continue
        prepared = read_json(LANDMARK / "prepared" / f"{entry['name']}.json")
        import pandas as pd
        frame = pd.read_parquet(LANDMARK / "prepared" / f"{entry['name']}.parquet")
        for firm, ledger in world_ledgers(SOURCE / entry["directory"]):
            target = output / "world18_shap" / entry["name"] / f"{firm}.json"
            if target.exists():
                results.append(read_json(target))
                continue
            origin = frame[frame.firm == firm].origin.max()
            context = ledger.snapshot(origin)
            opened = context[(context.remaining_amount > .01) & context.written_off_at.isna()].copy()
            opened.attrs["compact_context"] = context
            probabilities = model.distribution(opened)[:, :4].sum(1)
            positions = np.unique(np.linspace(0, len(opened)-1, min(20, len(opened))).astype(int))
            order = np.argsort(opened.remaining_amount.to_numpy(), kind="stable")
            samples = []
            for position in order[positions]:
                row = opened.iloc[position]
                rows = [dict(invoice_id=str(row.invoice_id), customer_id=str(row.customer_id),
                             payment_probability_4w=float(probabilities[position]))]
                started = time.perf_counter()
                reference = explain_compact(rows, opened, [(1., model)], origin, model_asof=model.metadata["available_asof"])
                elapsed = time.perf_counter() - started
                explanation = rows[0]["payment_explanation"]
                if explanation["status"] != "available" or explanation["additivity_error"] > 1e-10:
                    raise ValueError("Global ensemble SHAP failed faithfulness check")
                samples.append(dict(invoice_id=str(row.invoice_id), seconds=elapsed,
                                    additivity_error=explanation["additivity_error"]))
            result = dict(world=entry["name"], firm=firm, origin=str(origin.date()),
                          population=len(opened), samples=samples,
                          p95_seconds=float(np.quantile([r["seconds"] for r in samples], .95)),
                          reference=explanation["reference"])
            write_json(target, result)
            results.append(result)
            print(f"World18 SHAP {entry['name']}/{firm}, n={len(opened)}, p95={result['p95_seconds']:.3f}s", flush=True)
    write_json(output / "world18_shap.json", dict(contexts=results,
               max_context_p95_seconds=max(r["p95_seconds"] for r in results),
               max_additivity_error=max(s["additivity_error"] for r in results for s in r["samples"])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        run(args.output.resolve())
