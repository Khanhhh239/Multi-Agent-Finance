"""Audit actual Workspace feature/partial-cash semantics on the common cohort.

The original frozen World scores remain intact. This separately measures the
unmodified serving bridge, including dated claim revisions in its history.
"""
import argparse
import os
from pathlib import Path
import sys

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from experiments.t1_compact.historical_workspace import partial_distribution
from agent1.adaptive.compact_t1 import CompactT1, workspace_context, sha256
from agent1.adaptive.landmark_features import FEATURES
from experiments.t1_compact.compare_workspace_worlds import SOURCE, LANDMARK, workspace_data, past_data, read_json, write_json
from experiments.t1_compact.train import world_ledgers
from experiments.t1_compact.train_landmark import context_for, score_prediction


def prepare(output):
    model = CompactT1.load(LANDMARK / "artifact")
    write_json(output / "serving_protocol.json", dict(
        version="workspace-serving-semantics-diagnostic-v1", diagnostic_only=True,
        source_sha256=sha256(Path(__file__)),
        global_model_metadata_sha256=sha256(LANDMARK / "artifact/metadata.json"),
        refitting=False, new_tuning=False,
        purpose="actual Workspace context and partial_distribution, without changing frozen World metrics",
    ))
    reports = []
    for entry in read_json(SOURCE / "inventory.json"):
        if entry["role"] != "test":
            continue
        name = entry["name"]
        frame = pd.read_parquet(LANDMARK / "prepared" / f"{name}.parquet").reset_index(drop=True)
        p, override = np.zeros((len(frame), 14)), np.zeros((len(frame), 14))
        support = np.zeros(len(frame), bool)
        for firm, ledger in world_ledgers(SOURCE / entry["directory"]):
            data = workspace_data(ledger)
            parts = frame[frame.firm == firm]
            for origin, part in parts.groupby("origin", sort=True):
                local = past_data(data, origin)
                history = workspace_context(local, origin)
                targets = history.set_index("invoice_id").loc[part.invoice_id].reset_index()
                targets.attrs["compact_context"] = history
                np.testing.assert_allclose(targets.remaining_amount, part.amount_open, atol=.01, rtol=0)
                x = model.prepare(targets)
                delta = abs(x - part[list(FEATURES)].to_numpy(float))
                current = model.distribution_from_features(x)
                frozen = model.distribution_from_features(part[list(FEATURES)].to_numpy(float))
                p[part.index] = current
                base = np.zeros_like(current)
                base[:, -1] = 1.
                cash, has_profile = partial_distribution(local, targets, origin, base, return_support=True)
                override[part.index] = cash
                support[part.index] = has_profile
                reports.append(dict(world=name, firm=firm, origin=str(origin.date()), anchors=len(part),
                                    differing_features=[feature for feature, d in zip(FEATURES, delta.max(0)) if d>1e-8],
                                    max_feature_difference=float(delta.max()),
                                    max_probability4_difference=float(abs(current[:, :4].sum(1)-frozen[:, :4].sum(1)).max()),
                                    partial_support_changes=int(np.sum(has_profile != part.partial_override.to_numpy(bool))),
                                    max_cash_profile_difference=float(abs(cash-part[[f"override_week_{i}" for i in range(1,15)]].to_numpy(float)).max())))
            print(f"Serving context {name}/{firm} prepared", flush=True)
        np.savez_compressed(output / name / "serving_inputs.npz", world18=p, override=override, support=support)
    write_json(output / "serving_context_audit.json", reports)


def summarize(output):
    frames, predictions, profiles, supports = [], {name: [] for name in ("workspace", "world18")}, [], []
    for entry in read_json(SOURCE / "inventory.json"):
        if entry["role"] != "test":
            continue
        name = entry["name"]
        frames.append(pd.read_parquet(LANDMARK / "prepared" / f"{name}.parquet"))
        with np.load(output / name / "serving_inputs.npz", allow_pickle=False) as serving:
            predictions["world18"].append(serving["world18"])
            profiles.append(serving["override"])
            supports.append(serving["support"])
        with np.load(output / name / "predictions.npz", allow_pickle=False) as cached:
            predictions["workspace"].append(cached["workspace"])
    frame = pd.concat(frames, ignore_index=True)
    profile, supported = np.concatenate(profiles), np.concatenate(supports)
    context = context_for(frame)
    rows, results = [], {}
    for name, pieces in predictions.items():
        p = np.concatenate(pieces)
        cash = p.copy()
        cash[supported] = profile[supported]
        totals = np.zeros_like(context["truth_cash"])
        np.add.at(totals, context["codes"], cash[:, :13]*context["amounts"][:, None])
        prediction = dict(cdf=p[:, :13].cumsum(1), cash=totals/context["group_amount"][:, None])
        results[name] = score_prediction(prediction, context)
        for key, positions in frame.groupby(["world", "firm", "origin"]).indices.items():
            sub = frame.iloc[positions].reset_index(drop=True)
            ctx = context_for(sub)
            subcash = (cash[positions, :13]*ctx["amounts"][:, None]).sum(0, keepdims=True)/ctx["group_amount"][:, None]
            rows.append(dict(model=name, world=key[0], firm=key[1], origin=str(key[2].date()),
                             **score_prediction(dict(cdf=p[positions, :13].cumsum(1), cash=subcash), ctx)))
    pd.DataFrame(rows).drop(columns="windows").to_csv(output / "serving_by_firm_origin.csv", index=False)
    audit = read_json(output / "serving_context_audit.json")
    write_json(output / "serving_results.json", dict(results=results,
               differing_contexts=sum(bool(r["differing_features"]) for r in audit),
               max_probability4_difference=max(r["max_probability4_difference"] for r in audit),
               partial_support_changes=sum(r["partial_support_changes"] for r in audit),
               diagnostic_only=True, runtime_semantics_changed=False))
    print(results, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        if args.prepare:
            prepare(args.output.resolve())
        if args.summarize:
            summarize(args.output.resolve())
