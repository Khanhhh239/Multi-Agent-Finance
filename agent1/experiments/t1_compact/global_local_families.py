"""Frozen development comparison: A1 Neural, LightGBM and XGBoost continuation.

Each family pools against its own global. The existing Neural/customer global
and the preceding A1 pipeline are explicit additional controls. No final test
or service activation is part of this experiment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import shutil
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from importlib.metadata import version
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from agent1.adaptive.compact_t1 import CompactT1, sha256
from agent1.adaptive.landmark_adaptation import pool
from agent1.adaptive.landmark_features import FEATURES, LandmarkHazard
from experiments.t1_compact.aligned_data import write
from experiments.t1_compact.neural_data_ablation import (
    SOURCE,
    lock,
    read,
    sampled_risk,
    train_neural,
)
from experiments.t1_compact.refit_landmark import OLD, measured
from experiments.t1_compact.train_landmark import (
    context_for,
    score_prediction,
    summarize_prediction,
)
from threadpoolctl import threadpool_limits

PRIOR = ROOT / "outputs/t1/neural_data_ablation_20261113"
PRETRAIN = OLD.parent
DEFAULT_OUTPUT = ROOT / "outputs/t1/global_local_families_20261113"
FAMILIES = ("neural", "lightgbm", "xgboost")
# Equal four learning configurations per family, with algorithm-specific units.
# These are locked before this run reads any development evaluation outcomes.
GRID = {
    "neural": [(lr, n) for lr in (0.00005, 0.0001) for n in (5, 20)],
    "lightgbm": [(lr, n) for lr in (0.01, 0.05) for n in (16, 64)],
    "xgboost": [(lr, n) for lr in (0.02, 0.08) for n in (12, 48)],
}
ALPHAS = (0.0, 0.25, 0.5, 0.75, 1.0)


def fingerprint(arrays):
    h = hashlib.sha256()
    for array in arrays:
        a = np.ascontiguousarray(array)
        h.update(str((a.dtype.str, a.shape)).encode())
        h.update(a.tobytes())
    return h.hexdigest()


def mix_training(arrays, replay, fraction):
    x, y, w = arrays
    rx, ry, rw = replay
    count = len(y) + len(ry)
    weights = (
        np.concatenate([(1 - fraction) * w / w.sum(), fraction * rw / rw.sum()]) * count
    )
    return np.concatenate([x, rx]), np.concatenate([y, ry]), weights


def tree_count(model):
    if model.name == "lightgbm":
        return model.booster.booster_.current_iteration()
    return model.booster.get_booster().num_boosted_rounds()


def tree_dump(model):
    if model.name == "lightgbm":
        return model.booster.booster_.dump_model()["tree_info"]
    return model.booster.get_booster().get_dump(dump_format="json")


def continue_tree(reference, arrays, replay, *, learning_rate, rounds, fraction=0.30):
    """Append trees; assert unchanged original trees and starting predictions."""
    if reference.name not in ("lightgbm", "xgboost"):
        raise ValueError("Expected a fitted global tree classifier")
    started = time.perf_counter()
    before = pickle.dumps(reference, protocol=pickle.HIGHEST_PROTOCOL)
    old_count, old_dump = tree_count(reference), tree_dump(reference)
    x, y, weights = mix_training(arrays, replay, fraction)
    estimator = deepcopy(reference.booster)
    estimator.set_params(n_estimators=rounds, learning_rate=learning_rate, n_jobs=2)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        if reference.name == "lightgbm":
            estimator.fit(
                x, y, sample_weight=weights, init_model=reference.booster.booster_
            )
        else:
            estimator.fit(
                x, y, sample_weight=weights, xgb_model=reference.booster.get_booster()
            )
    model = LandmarkHazard(estimator, reference.name)
    actual = tree_count(model) - old_count
    if actual != rounds or tree_dump(model)[:old_count] != old_dump:
        raise AssertionError("Continuation did not append exactly the requested trees")
    probe = x[: min(128, len(x))]
    if reference.name == "lightgbm":
        prefix = estimator.booster_.predict(
            probe, num_iteration=old_count, num_threads=1
        )
    else:
        prefix = estimator.get_booster().inplace_predict(
            probe, iteration_range=(0, old_count)
        )
    np.testing.assert_allclose(
        prefix, reference.predict_hazard(probe), atol=1e-7, rtol=1e-6
    )
    if pickle.dumps(reference, protocol=pickle.HIGHEST_PROTOCOL) != before:
        raise AssertionError("Global tree was mutated")
    return model, {
        "training_seconds": time.perf_counter() - started,
        "learning_rate": learning_rate,
        "rounds_requested": rounds,
        "rounds_added": actual,
        "global_rounds": old_count,
        "old_trees_unchanged": True,
        "global_unchanged": True,
        "prefix_max_error": float(abs(prefix - reference.predict_hazard(probe)).max()),
        "mixed_training_sha256": fingerprint((x, y, weights)),
        "warning_messages": sorted({str(w.message) for w in caught}),
    }


def load_globals(protocol):
    current = CompactT1.load(OLD)
    result = {"neural": next(m for m in current.members if m.name == "neural")}
    for name in ("lightgbm", "xgboost"):
        result[name] = CompactT1.load(
            Path(protocol["global_models"][name]["directory"])
        )
    return current, result


def make_protocol(output, workers):
    parent = read(PRIOR / "protocol.json")
    sample = read(PRETRAIN / "training_sample.json")["sample_sha256"]
    models, paths = {}, [PRIOR / "protocol.json", PRETRAIN / "training_sample.json"]
    for name in FAMILIES:
        trials = [
            read(PRETRAIN / "trials" / f"{name}_{i}" / "trial.json") for i in (0, 1)
        ]
        selected = min(trials, key=lambda r: (r["score"], r["trial"]))
        directory = PRETRAIN / "trials" / f"{name}_{selected['trial']}" / "model"
        for trial in trials:
            if trial["sample_sha256"] != sample:
                raise ValueError(
                    "Global candidates did not share the same training table"
                )
            p = PRETRAIN / "trials" / f"{name}_{trial['trial']}"
            if sha256(p / "model/metadata.json") != trial["model_metadata_sha256"]:
                raise ValueError("Pretrained model metadata changed")
            paths.append(p / "trial.json")
        CompactT1.load(directory)  # Verify model hashes before freezing the run.
        paths += [p for p in directory.rglob("*") if p.is_file()]
        models[name] = {
            "directory": str(directory),
            "trial": selected["trial"],
            "historical_validation_cash": selected["score"],
            "sample_sha256": sample,
        }
    if (
        read(Path(models["neural"]["directory"]) / "metadata.json")["model_sha256"]
        != read(OLD / "member_0/metadata.json")["model_sha256"]
    ):
        raise ValueError("Neural reference differs from current global member")
    paths += [p for p in OLD.rglob("*") if p.is_file()]
    paths.append(SOURCE / "current_global_replay.npz")
    for job in parent["jobs"]:
        for origin in job["origins"]:
            target = PRIOR / "contexts" / job["world"] / job["firm"] / origin
            receipt = read(target / "data_receipt.json")
            for name, digest in receipt["files"].items():
                if sha256(target / name) != digest:
                    raise ValueError("Verified census cache changed")
                paths.append(target / name)
            paths += [
                target / "data_receipt.json",
                target / "A1.json",
                target / "A1_predictions.npz",
            ]
            arm_receipt = read(target / "A1_receipt.json")
            for name in ("A1.json", "A1_predictions.npz"):
                if sha256(target / name) != arm_receipt["files"][name]:
                    raise ValueError("Prior A1 evidence changed")
    source_paths = sorted(
        {
            Path(__file__),
            *list((ROOT / "agent1/adaptive").glob("*.py")),
            *list((ROOT / "experiments/t1_compact").glob("*.py")),
        }
    )
    value = {
        "version": "global-local-families-a1-development-v1",
        "synthetic": True,
        "data_role": "reused development, historical inspected Worlds + Dai Phat; NOT final test",
        "final_test_opened": False,
        "jobs": parent["jobs"],
        "contexts": parent["development_contexts"],
        "features": list(FEATURES),
        "local_data": {"arm": "A1", "snapshot_cap": None, "risk_row_cap": 12000},
        "config": parent["adaptation"],
        "grid": {
            name: [{"learning_rate": lr, "budget": n} for lr, n in GRID[name]]
            for name in FAMILIES
        },
        "alpha_grid": list(ALPHAS),
        "global_models": models,
        "global_training": "all three frozen family candidates shared the SAME original 100000 risk rows, labels and weights; original Neural is retained, no global refit",
        "global_label_limitation": "Pretrained artifacts retain historical pre-cash-calendar labels, equally for all families; local labels/replay use the corrected contract, unchanged from the cap study.",
        "selection": "per-enterprise dated validation only: minimum cash among IBS <= own-family global * 1.02 + .0001; tie by budget, learning rate, alpha",
        "audit": "chosen model only, >= .0001 cash gain and same IBS guard against OWN family global; no alternate search",
        "final_refit": "restart from original family global, same locked LR/budget/alpha, mature fit+validation+audit, A1 risk cap; raw and audited branches both retained",
        "pooling": "all primary families: (1-alpha)*own-family standalone global + alpha*adapted standalone family; current 75/25 Neural/customer and historical A1 remain additional controls",
        "replay": str(SOURCE / "current_global_replay.npz"),
        "replay_weight_mass": 0.30,
        "budgets": {
            "neural": "epochs; actual Adam updates logged",
            "lightgbm": "additional boosting rounds",
            "xgboost": "additional boosting rounds",
        },
        "tree_mechanism": "append new trees, retain old tree structures/values; init_model / xgb_model; no refresh/refit variant in this study",
        "workers": workers,
        "native_threads_per_worker": 2,
        "blas_threads_per_worker": 1,
        "score": parent["score"],
        "future_model_selection": "excluded; report all locked procedures without choosing per-context winner from future outcomes",
        "input_sha256": {str(p): sha256(p) for p in sorted(set(paths))},
        "source_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in source_paths},
        "versions": {
            n: version(n)
            for n in ("numpy", "pandas", "scikit-learn", "lightgbm", "xgboost")
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    lock(output / "protocol.json", value)
    for p in source_paths:
        dst = output / "source_snapshot" / p.relative_to(ROOT)
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
        elif sha256(dst) != sha256(p):
            raise ValueError("Source snapshot changed")
    return value


def score(p, rows):
    ctx = context_for(rows)
    return score_prediction(summarize_prediction(p, ctx), ctx)


def guard(metrics, base):
    return metrics["integrated_brier13"] <= base["integrated_brier13"] * 1.02 + 0.0001


def train(reference, arrays, replay, spec, config):
    if reference.name == "neural":
        local_config = dict(config, learning_rate=spec["learning_rate"])
        model, trace = train_neural(
            reference, arrays, replay, spec["budget"], local_config
        )
        trace["mixed_training_sha256"] = fingerprint(mix_training(arrays, replay, 0.30))
    else:
        model, trace = continue_tree(
            reference,
            arrays,
            replay,
            learning_rate=spec["learning_rate"],
            rounds=spec["budget"],
        )
    return model, dict(spec, **trace)


def adapt(reference, arrays, final_arrays, replay, rows, protocol, evaluation):
    config = protocol["config"]
    name = reference.name
    preds = {"evaluation_global": measured(reference, evaluation)[1]}
    record = {
        "family": name,
        "status": "insufficient_mature_local_windows",
        "audit_passed": False,
        "tuning": [],
        "training": [],
    }
    models = {"raw": reference, "audited": reference}
    if arrays is None:
        return models, record, preds
    val = rows[rows.role == "validation"].reset_index(drop=True)
    audit = rows[rows.role == "audit"].reset_index(drop=True)
    base = {"validation": measured(reference, val), "audit": measured(reference, audit)}
    preds.update({f"{stage}_global": value[1] for stage, value in base.items()})
    eligible = []
    selected_models = {}
    for i, spec in enumerate(protocol["grid"][name]):
        model, trace = train(reference, arrays, replay, spec, config)
        record["training"].append(dict(stage="selection", trial=i, **trace))
        selected_models[i] = model
        for alpha in ALPHAS:
            p = pool(reference, model, alpha).distribution_from_features(
                val[list(FEATURES)].to_numpy(float)
            )
            metrics = score(p, val)
            valid = guard(metrics, base["validation"][0])
            record["tuning"].append(
                dict(trial=i, alpha=alpha, guard=bool(valid), **spec, **metrics)
            )
            preds[f"validation_t{i}_a{alpha}"] = p
            if valid:
                eligible.append(
                    (metrics["score"], spec["budget"], spec["learning_rate"], alpha, i)
                )
    _, _, _, alpha, trial = min(eligible)
    spec = protocol["grid"][name][trial]
    selected = pool(reference, selected_models[trial], alpha)
    am, ap = measured(selected, audit)
    passed = am["score"] <= base["audit"][0]["score"] - config[
        "audit_minimum_gain"
    ] and guard(am, base["audit"][0])
    final, trace = train(reference, final_arrays, replay, spec, config)
    record["training"].append(dict(stage="final_refit", trial=trial, **trace))
    models["raw"] = pool(reference, final, alpha)
    models["audited"] = models["raw"] if passed else reference
    preds["audit_selected"] = ap
    record.update(
        status="adapted",
        selected_trial=trial,
        selected_alpha=alpha,
        selected_spec=spec,
        validation_global=base["validation"][0],
        audit_global=base["audit"][0],
        audit_selected=am,
        audit_passed=bool(passed),
    )
    return models, record, preds


def run_job(output, job, protocol):
    output = Path(output)
    phash = sha256(output / "protocol.json")
    with threadpool_limits(limits=2), threadpool_limits(limits=1, user_api="blas"):
        current, globals_ = load_globals(protocol)
        before = {
            name: pickle.dumps(m, protocol=pickle.HIGHEST_PROTOCOL)
            for name, m in globals_.items()
        }
        with np.load(Path(protocol["replay"]), allow_pickle=False) as f:
            replay = tuple(f[k] for k in ("x", "y", "weights"))
        for origin in job["origins"]:
            target = output / "contexts" / job["world"] / job["firm"] / origin
            target.mkdir(parents=True, exist_ok=True)
            done = target / "receipt.json"
            if done.exists():
                receipt = read(done)
                if receipt["protocol_sha256"] != phash:
                    raise ValueError("Context protocol changed")
                for p, h in receipt["files"].items():
                    if sha256(target / p) != h:
                        raise ValueError("Checkpoint changed")
                continue
            src = PRIOR / "contexts" / job["world"] / job["firm"] / origin
            full = pd.read_parquet(src / "local_census.parquet")
            evaluation = pd.read_parquet(src / "evaluation_census.parquet")
            fit = full[full.role == "fit"].reset_index(drop=True) if len(full) else full
            sizes = {
                role: int((full.role == role).sum()) if len(full) else 0
                for role in ("fit", "validation", "audit")
            }
            config = protocol["config"]
            enough = all(
                sizes[role] >= config[f"minimum_{role}_rows"] for role in sizes
            )
            data = {
                "sizes": sizes,
                "evaluation_snapshots": len(evaluation),
                "fit": None,
                "final": None,
            }
            arrays = final_arrays = None
            if enough:
                if (
                    fit.origin.max() + pd.Timedelta(days=91)
                    > full[full.role == "validation"].origin.min()
                    or full[full.role == "validation"].origin.max()
                    + pd.Timedelta(days=91)
                    > full[full.role == "audit"].origin.min()
                ):
                    raise ValueError("Overlapping local outcome windows")
                if full.label_end.max() > pd.Timestamp(origin):
                    raise ValueError("Local future labels")
                arrays, data["fit"] = sampled_risk(fit, 12000)
                final_arrays, data["final"] = sampled_risk(full, 12000)
                data["fit_arrays_sha256"] = fingerprint(arrays)
                data["final_arrays_sha256"] = fingerprint(final_arrays)
                data["fit_mixed_sha256"] = fingerprint(
                    mix_training(arrays, replay, 0.30)
                )
                data["final_mixed_sha256"] = fingerprint(
                    mix_training(final_arrays, replay, 0.30)
                )
            write(target / "data.json", data)
            for name, reference in globals_.items():
                family_done = target / f"{name}_receipt.json"
                if family_done.exists():
                    receipt = read(family_done)
                    if receipt["protocol_sha256"] != phash:
                        raise ValueError("Family protocol changed")
                    for p, h in receipt["files"].items():
                        if sha256(target / p) != h:
                            raise ValueError("Family checkpoint changed")
                    continue
                started = time.perf_counter()
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    models, record, preds = adapt(
                        reference,
                        arrays,
                        final_arrays,
                        replay,
                        full,
                        protocol,
                        evaluation,
                    )
                for mode, model in models.items():
                    preds[f"evaluation_{mode}"] = measured(model, evaluation)[1]
                record.update(
                    world=job["world"],
                    firm=job["firm"],
                    origin=origin,
                    evaluation={
                        mode: score(p, evaluation)
                        for mode, p in preds.items()
                        if mode.startswith("evaluation_")
                    },
                    elapsed_seconds=time.perf_counter() - started,
                    warning_messages=sorted({str(w.message) for w in caught}),
                )
                write(target / f"{name}.json", record)
                np.savez_compressed(target / f"{name}_predictions.npz", **preds)
                with (target / f"{name}_models.pkl").open("wb") as f:
                    pickle.dump(models, f, protocol=pickle.HIGHEST_PROTOCOL)
                names = [
                    f"{name}.json",
                    f"{name}_predictions.npz",
                    f"{name}_models.pkl",
                ]
                write(
                    family_done,
                    {
                        "protocol_sha256": phash,
                        "files": {n: sha256(target / n) for n in names},
                    },
                )
                print(
                    f"{job['world']}/{job['firm']}/{origin} {name}: cash={record['evaluation']['evaluation_raw']['score']:.6f}; audit={record['audit_passed']}",
                    flush=True,
                )
            # No future outcomes are used by adaptation or any selection above.
            current_metrics, current_p = measured(current, evaluation)
            prior_metrics = read(src / "A1.json")["evaluation"]
            write(
                target / "controls.json",
                {
                    "current_global": current_metrics,
                    "prior_neural_A1_raw": prior_metrics["finetuned"],
                    "prior_neural_A1_audited": prior_metrics["audited"],
                },
            )
            np.savez_compressed(target / "current_global.npz", distribution=current_p)
            files = {
                p.name: sha256(p)
                for p in target.iterdir()
                if p.is_file() and p.name != "receipt.json"
            }
            write(done, {"protocol_sha256": phash, "files": files})
        for name, reference in globals_.items():
            if (
                pickle.dumps(reference, protocol=pickle.HIGHEST_PROTOCOL)
                != before[name]
            ):
                raise ValueError("Global model mutated")
    return {"world": job["world"], "firm": job["firm"]}


def summarize(output, protocol):
    rows, traces, choices = [], [], []
    for job in protocol["jobs"]:
        for origin in job["origins"]:
            target = output / "contexts" / job["world"] / job["firm"] / origin
            if not (target / "receipt.json").exists():
                raise ValueError(f"Missing completed context: {target}")
            key = {
                "world": job["world"],
                "firm": job["firm"],
                "origin": origin,
                "scenario": job["scenario"],
            }
            for name in FAMILIES:
                r = read(target / f"{name}.json")
                for mode, metrics in r["evaluation"].items():
                    rows.append(
                        dict(
                            key,
                            method=f"{name}_{mode.removeprefix('evaluation_')}",
                            **{k: v for k, v in metrics.items() if k != "windows"},
                        )
                    )
                choices.append(
                    dict(
                        key,
                        family=name,
                        status=r["status"],
                        audit_passed=r["audit_passed"],
                        alpha=r.get("selected_alpha"),
                        **r.get("selected_spec", {}),
                    )
                )
                traces += [dict(key, family=name, **t) for t in r["training"]]
            for name, metrics in read(target / "controls.json").items():
                rows.append(
                    dict(
                        key,
                        method=name,
                        **{k: v for k, v in metrics.items() if k != "windows"},
                    )
                )
    frame = pd.DataFrame(rows)
    frame.to_csv(output / "by_context.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(traces).to_csv(
        output / "training.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(choices).to_csv(
        output / "choices.csv", index=False, encoding="utf-8-sig"
    )
    results = {}
    for cohort, scenarios in {
        "established": ["baseline", "credit", "supply"],
        "onboarding": ["short_history"],
        "dai_phat": ["demo"],
    }.items():
        part = frame[frame.scenario.isin(scenarios)]
        metric_columns = [
            "score",
            "integrated_brier13",
            "cash_weekly_mae_vnd",
            "cash_cumulative_mae_vnd",
        ]
        means = (
            part.groupby(["method", "world", "firm"])[metric_columns]
            .mean()
            .groupby(["method", "world"])
            .mean()
            .groupby("method")
            .mean()
        )
        results[cohort] = means.to_dict(orient="index")
    write(output / "results.json", results)
    write(
        output / "completion.json",
        {
            "protocol_sha256": sha256(output / "protocol.json"),
            "contexts": protocol["contexts"],
            "family_contexts": len(choices),
            "final_test_opened": False,
        },
    )
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--init-only", action="store_true")
    args = parser.parse_args()
    protocol = make_protocol(args.output, args.workers)
    print(
        f"Locked {protocol['contexts']} reused development contexts; {sha256(args.output / 'protocol.json')}",
        flush=True,
    )
    if args.init_only:
        return
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        tasks = {
            executor.submit(run_job, args.output, j, protocol): j
            for j in protocol["jobs"]
        }
        for future in as_completed(tasks):
            print(json.dumps(future.result()), flush=True)
    print(json.dumps(summarize(args.output, protocol), indent=2), flush=True)


if __name__ == "__main__":
    main()
