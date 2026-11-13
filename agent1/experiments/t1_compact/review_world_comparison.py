"""Audit finished comparison artifacts and describe paired firm-level variation.

The bootstrap resamples firms within each of three fixed synthetic Worlds. It
does not estimate uncertainty over unseen simulators, industries or real SMEs.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
import pandas as pd
from experiments.t1_compact.compare_workspace_worlds import (
    LANDMARK, SOURCE, MODEL_NAMES, read_json, write_json,
)
from experiments.t1_compact.train_landmark import context_for, score_prediction, summarize_prediction


def audit(output):
    results = read_json(output / "results.json")
    frame = pd.read_csv(output / "by_firm.csv")
    worlds = pd.read_csv(output / "by_world.csv")
    by_origin = pd.read_csv(output / "by_origin.csv")
    reference = read_json(LANDMARK / "test_results.json")
    aliases = dict(world18="selected", world10="previous_10_feature_ensemble", world_survival="survival")
    for name, alias in aliases.items():
        for metric, value in reference[alias].items():
            if metric == "windows":
                continue
            if not np.isclose(results["results"][name][metric], value, atol=1e-8, rtol=1e-12):
                raise ValueError(f"Previously frozen score did not reproduce: {name}/{metric}")
    fits = pd.read_csv(output / "workspace_fits.csv")
    if len(fits) != 108 or results["anchors"] != 5486:
        raise ValueError("Incomplete comparison")
    if fits.duplicated(["world", "firm", "origin"]).any():
        raise ValueError("Duplicate Workspace checkpoints")
    all_frames, all_predictions = [], {name: [] for name in MODEL_NAMES}
    for entry in read_json(SOURCE / "inventory.json"):
        if entry["role"] != "test":
            continue
        part = pd.read_parquet(LANDMARK / "prepared" / f"{entry['name']}.parquet")
        p = np.zeros((len(part), 14))
        for (firm, origin), group in part.groupby(["firm", "origin"]):
            path = output / entry["name"] / "checkpoints" / firm / f"{origin.date()}.npz"
            with np.load(path, allow_pickle=False) as saved:
                p[group.index] = saved["distribution"]
        with np.load(output / entry["name"] / "predictions.npz", allow_pickle=False) as saved:
            np.testing.assert_allclose(p, saved["workspace"], atol=1e-12, rtol=0)
            for name in MODEL_NAMES:
                all_predictions[name].append(saved[name])
        all_frames.append(part)
    data = pd.concat(all_frames, ignore_index=True)
    context = context_for(data)
    for name in MODEL_NAMES:
        measured = score_prediction(summarize_prediction(np.concatenate(all_predictions[name]), context), context)
        if measured != results["results"][name]:
            raise ValueError("Aggregated prediction/metric mismatch")
    comparisons = {}
    for other in ("world18", "world10", "world_survival"):
        paired = frame[frame.model.isin(["workspace", other])].pivot(
            index=["world", "firm"], columns="model", values="score")
        paired["delta"] = paired.workspace - paired[other]
        rng = np.random.default_rng(261112)
        draws = []
        for world, group in paired.groupby(level="world"):
            delta = group.delta.to_numpy()
            draws.append(delta[rng.integers(0, len(delta), size=(10000, len(delta)))].mean(1))
        bootstrap = np.mean(draws, axis=0)
        world_pair = worlds[worlds.model.isin(["workspace", other])].pivot(index="world", columns="model", values="score")
        origin_pair = by_origin[by_origin.model.isin(["workspace", other])].pivot(index="origin", columns="model", values="score")
        comparisons[other] = dict(
            delta_definition=f"Workspace cash score minus {other}; positive favors {other}",
            mean_delta=float(paired.delta.mean()),
            ci95_delta=list(map(float, np.quantile(bootstrap, [.025, .975]))),
            world_wins_for_other=int((world_pair[other] < world_pair.workspace).sum()),
            firm_wins_for_other=int((paired.delta > 1e-12).sum()),
            firm_ties=int((abs(paired.delta) <= 1e-12).sum()),
            origin_wins_for_other=int((origin_pair[other] < origin_pair.workspace).sum()),
            uncertainty_scope="firms resampled within three fixed reused-test synthetic Worlds; all origins of each firm stay together",
        )
    write_json(output / "verification.json", dict(
        passed=True, checkpoint_predictions_recomputed=True,
        frozen_global_scores_reproduced=True, common_anchors=5486,
        workspace_origins=108, comparisons=comparisons,
        test_previously_inspected=True, independent_fresh_test=False,
    ))
    print(json.dumps(comparisons, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    audit(args.output.resolve())
