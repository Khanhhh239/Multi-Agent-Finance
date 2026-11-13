"""Fill independent late-firm checkpoints while the main World runners work.

No model settings change. This worker writes only firm-specific checkpoints
and SHAP records; the main runner alone publishes complete World predictions.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from experiments.t1_compact import compare_workspace_worlds as comparison
from threadpoolctl import threadpool_limits


def run(output, world, firms):
    original_ledgers = comparison.world_ledgers
    original_json = comparison.write_json
    original_npz = comparison.np.savez_compressed
    original_sha = comparison.sha256

    def selected_ledgers(directory):
        yield from ((firm, ledger) for firm, ledger in original_ledgers(directory) if firm in firms)

    def checkpoint_json(path, value):
        if path.name not in ("fits.json", "receipt.json"):
            original_json(path, value)

    def checkpoint_npz(path, **values):
        if Path(path).name != "predictions.npz":
            original_npz(path, **values)

    def checkpoint_sha(path):
        if Path(path).name == "predictions.npz":
            return "not-published-by-checkpoint-worker"
        return original_sha(path)

    comparison.world_ledgers = selected_ledgers
    comparison.write_json = checkpoint_json
    comparison.np.savez_compressed = checkpoint_npz
    comparison.sha256 = checkpoint_sha
    try:
        with threadpool_limits(limits=2):
            comparison.run_world(output, world)
    finally:
        comparison.world_ledgers = original_ledgers
        comparison.write_json = original_json
        comparison.np.savez_compressed = original_npz
        comparison.sha256 = original_sha


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--world", required=True)
    parser.add_argument("--firms", required=True, nargs="+")
    args = parser.parse_args()
    run(args.output.resolve(), args.world, set(args.firms))
