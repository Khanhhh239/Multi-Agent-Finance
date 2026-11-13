"""Benchmark ensemble SHAP using the actual Workspace observation context."""
import argparse
import os
from pathlib import Path
import sys

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import pandas as pd
from threadpoolctl import threadpool_limits
from agent1.adaptive.compact_t1 import CompactT1, workspace_context, sha256
from experiments.t1_compact.compare_workspace_worlds import (
    SOURCE, LANDMARK, read_json, write_json, workspace_data, past_data, shap_latency,
)
from experiments.t1_compact.train import world_ledgers


def run(output):
    model = CompactT1.load(LANDMARK / "artifact")
    results = []
    for entry in read_json(SOURCE / "inventory.json"):
        if entry["role"] != "test":
            continue
        frame = pd.read_parquet(LANDMARK / "prepared" / f"{entry['name']}.parquet")
        for firm, ledger in world_ledgers(SOURCE / entry["directory"]):
            directory = output / "world18_serving_shap" / entry["name"]
            path = directory / "shap" / f"{firm}.json"
            if path.exists():
                results.append(dict(world=entry["name"], **read_json(path)))
                continue
            origin = frame[frame.firm == firm].origin.max()
            context = workspace_context(past_data(workspace_data(ledger), origin), origin)
            opened = context[(context.remaining_amount > .01) & context.written_off_at.isna()].copy()
            opened.attrs["compact_context"] = context
            result = shap_latency(opened, [(1., model)], origin, directory, firm)
            results.append(dict(world=entry["name"], **result))
            print(f"Serving SHAP {entry['name']}/{firm}, p95={result['p95_seconds']:.3f}s", flush=True)
    write_json(output / "world18_serving_shap.json", dict(
        source_sha256=sha256(Path(__file__)),
        model_metadata_sha256=sha256(LANDMARK / "artifact/metadata.json"),
        model_available_asof=model.metadata["available_asof"],
        context="unmodified Workspace workspace_context with dated claim revisions",
        concurrent_training_may_be_running=True, contexts=results,
        max_context_p95_seconds=max(r["p95_seconds"] for r in results),
        max_additivity_error=max(s["additivity_error"] for r in results for s in r["samples"]),
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        run(args.output.resolve())
