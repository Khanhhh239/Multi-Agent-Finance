"""Paired variation for actual serving cash forecasts, with fixed World scope."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
import pandas as pd
from agent1.adaptive.compact_t1 import sha256
from experiments.t1_compact.compare_workspace_worlds import read_json, write_json


def run(output):
    rows = pd.read_csv(output / "serving_by_firm_origin.csv")
    firms = rows.groupby(["world", "firm", "model"]).score.mean().unstack("model")
    worlds = rows.groupby(["world", "model"]).score.mean().unstack("model")
    origins = rows.groupby(["origin", "model"]).score.mean().unstack("model")
    delta = firms.workspace - firms.world18
    rng = np.random.default_rng(261112)
    draws = []
    for world, group in delta.groupby(level="world"):
        values = group.to_numpy()
        draws.append(values[rng.integers(0, len(values), size=(10000, len(values)))].mean(1))
    reference = read_json(output / "serving_results.json")["results"]
    np.testing.assert_allclose(delta.mean(), reference["workspace"]["score"]-reference["world18"]["score"], atol=1e-12, rtol=0)
    if len(firms) != 18 or len(rows) != 216:
        raise ValueError("Incomplete serving comparison")
    result = dict(
        source_sha256=sha256(Path(__file__)),
        source_csv_sha256=sha256(output / "serving_by_firm_origin.csv"),
        delta_definition="Workspace minus World18; positive favors World18",
        mean_delta=float(delta.mean()),
        ci95_delta=list(map(float, np.quantile(np.mean(draws, axis=0), [.025, .975]))),
        world18_world_wins=int((worlds.world18 < worlds.workspace).sum()),
        world18_firm_wins=int((delta > 1e-12).sum()),
        world18_origin_wins=int((origins.world18 < origins.workspace).sum()),
        scope="firms resampled within three fixed reused-test synthetic Worlds, preserving each firm's six origins",
        passed=True,
    )
    firms.to_csv(output / "serving_by_firm.csv")
    worlds.to_csv(output / "serving_by_world.csv")
    write_json(output / "serving_verification.json", result)
    print(result, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run(args.output.resolve())
