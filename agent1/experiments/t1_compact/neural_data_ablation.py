"""Development-only Neural data-cap ablation; never opens a new final test.

Historical inspected Worlds and Dai Phat are explicitly development fixtures.
All scoring uses census landmarks. Training caps are applied independently,
including when validation/audit origins join the final, mature local refit.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
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
from agent1.adaptive.landmark_adaptation import continue_neural, pool
from agent1.adaptive.landmark_features import FEATURES, LandmarkHazard
from agent1.adaptive.ledger_bridge import workspace_data
from experiments.t1_compact.aligned_data import landmarks, write
from experiments.t1_compact.refit_landmark import OLD, measured
from experiments.t1_compact.train import risk_rows, sample_indices, world_ledgers
from scripts.business.backtest_t1_dai_phat_adaptation import demo_ledger
from scripts.business.backtest_t6_baseline import CUTOFFS, load_demo
from sklearn.neural_network import MLPClassifier
from threadpoolctl import threadpool_limits

SOURCE = ROOT / "outputs/t1/aligned_cashcalendar_20261113"
DEMO = ROOT / "outputs/t1/dai_phat_adaptation_20261113"
DEFAULT_OUTPUT = ROOT / "outputs/t1/neural_data_ablation_20261113"
ARMS = {"A0": (50, 12000), "A1": (None, 12000), "A2": (None, None)}
SEED = 261112


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def lock(path, value):
    if path.exists():
        if read(path) != value:
            raise ValueError(f"Locked experiment changed; use a new output: {path}")
    else:
        write(path, value)


def make_protocol(output, workers):
    """Freeze cohort, sources, fitted starting state and controls before fitting."""
    input_paths = [
        SOURCE / "fresh_inventory.json",
        SOURCE / "protocol.json",
        SOURCE / "current_global_replay.npz",
        DEMO / "protocol.json",
    ]
    jobs = []
    for entry in read(SOURCE / "fresh_inventory.json"):
        if entry["role"] != "fresh_test":
            continue
        prepared = SOURCE / "prepared" / (entry["name"] + ".parquet")
        receipt = read(prepared.with_suffix(".json"))
        if sha256(prepared) != receipt["sha256"]:
            raise ValueError("Historical development input changed")
        keys = pd.read_parquet(prepared, columns=["firm", "origin"]).drop_duplicates()
        directory = Path(entry["directory"])
        if sha256(directory / "manifest.json") != entry["manifest_sha256"]:
            raise ValueError("Historical World manifest changed")
        manifest = read(directory / "manifest.json")
        for name, digest in manifest["files"].items():
            path = directory / name
            if sha256(path) != digest:
                raise ValueError(f"World file changed: {path}")
            input_paths.append(path)
        input_paths += [
            prepared,
            prepared.with_suffix(".json"),
            directory / "manifest.json",
        ]
        for firm, part in keys.groupby("firm", sort=True):
            jobs.append(
                {
                    "world": entry["name"],
                    "firm": str(firm),
                    "directory": str(directory),
                    "origins": [
                        str(pd.Timestamp(t).date()) for t in sorted(part.origin)
                    ],
                    "scenario": entry["scenario"],
                    "evaluation_label_end": "2025-12-31",
                }
            )
    input_paths += sorted((DEMO / "inputs").glob("*"))
    input_paths += sorted(p for p in OLD.rglob("*") if p.is_file())
    jobs.append(
        {
            "world": "dai_phat",
            "firm": "DP",
            "directory": str(DEMO / "inputs"),
            "origins": list(CUTOFFS),
            "scenario": "demo",
            "evaluation_label_end": read(DEMO / "protocol.json")["truth_asof"],
        }
    )
    source_paths = sorted(
        {
            Path(__file__),
            *list((ROOT / "agent1/adaptive").glob("*.py")),
            *list((ROOT / "experiments/t1_compact").glob("*.py")),
            ROOT / "scripts/business/backtest_t1_dai_phat_adaptation.py",
            ROOT / "scripts/business/backtest_t6_baseline.py",
        }
    )
    config = read(SOURCE / "protocol.json")["adaptation"]
    value = {
        "version": "neural-data-cap-development-v1",
        "synthetic": True,
        "data_role": "development: already inspected historical cohorts; NOT final test",
        "final_test_opened": False,
        "global_retraining": False,
        "jobs": jobs,
        "development_contexts": sum(len(j["origins"]) for j in jobs),
        "arms": {
            name: {"snapshot_cap": caps[0], "risk_row_cap": caps[1]}
            for name, caps in ARMS.items()
        },
        "adaptation": config,
        "features": list(FEATURES),
        "seed": SEED,
        "validation_audit_evaluation": "census of all eligible landmarks, shared across arms",
        "training": "arm-specific caps on fit; same caps on mature fit+validation+audit final refit",
        "sampler": "original stable snapshot hash; seeded uniform weekly risk-row sample, weights renormalized",
        "global_artifact": str(OLD),
        "replay": str(SOURCE / "current_global_replay.npz"),
        "replay_weight_mass": config["global_replay_fraction"],
        "workers": workers,
        "blas_threads_per_worker": 1,
        "selection": "validation cash13 + original Brier guard; tie by epochs then alpha; audit accepts locked choice or global",
        "reweighting": "excluded: isolate Neural data caps; global alpha=0 remains available",
        "matched_updates": {
            "trigger": "A2 lower mean raw-finetuned development cash score than A0 or A1 on the 3 established Worlds",
            "controls": ["A2_U0", "A2_U1"],
            "budget": "for each epoch trial and final refit, exactly the corresponding A0/A1 Adam step count; A2 full risk table and original batch size",
            "mechanism": "truncate last partial_fit epoch at optimizer update boundary; pin sklearn and stochastic-loop source hash",
            "limitation": "equal updates can expose fewer rows than a full A2 epoch; coverage and completed epochs recorded; not perfect causal identification",
        },
        "score": "0.5 * (sum absolute weekly cash errors + mean absolute cumulative errors), normalized by outstanding; equal World/firm/origin",
        "limitations": [
            "Shared synthetic simulator, development evidence only.",
            "Repeated snapshots/risk rows are correlated, not additional independent invoices.",
            "A0 census validation/audit differs from the historical capped evaluation.",
            "Full follow-up and existing claim/late-cash eligibility rules retained.",
        ],
        "input_sha256": {
            str(p): sha256(p) for p in sorted(set(input_paths)) if p.is_file()
        },
        "source_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in source_paths},
        "versions": {
            name: version(name)
            for name in ("numpy", "pandas", "scikit-learn", "lightgbm", "xgboost")
        },
        "stochastic_loop_sha256": hashlib.sha256(
            inspect.getsource(MLPClassifier._fit_stochastic).encode()
        ).hexdigest(),
    }
    output.mkdir(parents=True, exist_ok=True)
    lock(output / "protocol.json", value)
    for source in source_paths:
        target = output / "source_snapshot" / source.relative_to(ROOT)
        if target.exists():
            if sha256(target) != sha256(source):
                raise ValueError("Source snapshot changed")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return value


def capped_snapshots(frame, cap):
    if cap is None or frame.empty:
        return frame.reset_index(drop=True).copy()
    parts = []
    for (role, world, firm, origin), part in frame.groupby(
        ["role", "world", "firm", "origin"], sort=False
    ):
        idx = sample_indices(part, cap, f"{world}:{firm}:{pd.Timestamp(origin).date()}")
        parts.append(part.iloc[idx])
    return pd.concat(parts, ignore_index=True)


def sampled_risk(frame, cap):
    x, y, w = risk_rows(frame, tuple(range(len(FEATURES))), FEATURES)
    n = len(y) if cap is None else min(len(y), cap)
    idx = np.sort(np.random.default_rng(SEED).choice(len(y), n, replace=False))
    # risk_rows concatenates weeks, each in surviving landmark order.
    owners = np.concatenate(
        [
            np.flatnonzero(frame.paid_days.to_numpy(float) > (week - 1) * 7)
            for week in range(1, 14)
        ]
    )
    w = w[idx]
    return (x[idx], y[idx], w * len(w) / w.sum()), {
        "snapshots": len(frame),
        "unique_invoices": int(frame.invoice_id.nunique()),
        "risk_rows_available": len(y),
        "risk_rows_used": n,
        "event_rows_used": int(y[idx].sum()),
        "snapshots_represented": int(np.unique(owners[idx]).size),
        "unique_invoices_represented": int(
            frame.iloc[np.unique(owners[idx])].invoice_id.nunique()
        ),
        "sample_sha256": hashlib.sha256(
            idx.tobytes() + x[idx].tobytes() + y[idx].tobytes() + w.tobytes()
        ).hexdigest(),
    }


def step_budget(reference, local_rows, replay_rows, epochs):
    classifier = reference.booster[-1]
    batch = classifier.batch_size
    if batch == "auto":
        batch = 200
    return epochs * math.ceil(
        (local_rows + replay_rows) / min(batch, local_rows + replay_rows)
    )


class _BudgetReached(Exception):
    pass


def train_neural(reference, arrays, replay, epochs, config, update_limit=None):
    """Primary path calls runtime unchanged; optional control truncates Adam."""
    started = time.perf_counter()
    before = int(reference.booster[-1]._optimizer.t)
    local_rows, replay_rows = len(arrays[1]), len(replay[1])
    expected = step_budget(reference, local_rows, replay_rows, epochs)
    if update_limit is None:
        model = continue_neural(
            reference,
            *arrays,
            replay,
            epochs=epochs,
            learning_rate=config["learning_rate"],
            replay_fraction=config["global_replay_fraction"],
        )
        completed_epochs = epochs
        seen = np.ones(local_rows + replay_rows, dtype=bool)
    else:
        if not 0 < update_limit <= expected:
            raise ValueError("Invalid matched update limit")
        estimator = deepcopy(reference.booster)
        classifier = estimator[-1]
        classifier.set_params(learning_rate_init=config["learning_rate"])
        optimizer = classifier._optimizer
        optimizer.learning_rate_init = config["learning_rate"]
        optimizer.learning_rate = config["learning_rate"]
        x = np.concatenate([arrays[0], replay[0]])
        y = np.concatenate([arrays[1], replay[1]])
        r = config["global_replay_fraction"]
        weights = np.concatenate(
            [(1 - r) * arrays[2] / arrays[2].sum(), r * replay[2] / replay[2].sum()]
        ) * len(y)
        transformed = estimator[:-1].transform(x)
        original_update = optimizer.update_params

        def limited_update(params, grads):
            if optimizer.t - before >= update_limit:
                raise _BudgetReached()
            original_update(params, grads)

        optimizer.update_params = limited_update
        # Reconstruct sklearn's deterministic permutation to report exposure.
        # This estimator has an integer random_state, reinitialized per partial_fit.
        if not isinstance(classifier.random_state, int) or not classifier.shuffle:
            raise ValueError("Matched exposure audit requires seeded shuffled MLP")
        order = np.random.RandomState(classifier.random_state).permutation(len(y))
        batch = min(classifier.batch_size, len(y))
        per_epoch = math.ceil(len(y) / batch)
        seen = np.zeros(len(y), dtype=bool)
        if update_limit >= per_epoch:
            seen[:] = True
        else:
            seen[order[: update_limit * batch]] = True
        completed_epochs = 0
        try:
            for _ in range(epochs):
                classifier.partial_fit(transformed, y, sample_weight=weights)
                completed_epochs += 1
                if optimizer.t - before == update_limit:
                    break
        except _BudgetReached:
            pass
        finally:
            # Do not serialize a closure bound to a different optimizer.
            del optimizer.update_params
        model = LandmarkHazard(estimator, reference.name)
    updates = int(model.booster[-1]._optimizer.t) - before
    if updates != (expected if update_limit is None else update_limit):
        raise AssertionError("Adam update count mismatch")
    for original, frozen in zip(reference.booster[:-1], model.booster[:-1]):
        for field in ("mean_", "scale_", "var_"):
            if hasattr(original, field):
                np.testing.assert_array_equal(
                    getattr(original, field), getattr(frozen, field)
                )
    return model, {
        "epochs_requested": epochs,
        "complete_epochs": completed_epochs,
        "optimizer_updates": updates,
        "update_limit": update_limit,
        "local_risk_rows": local_rows,
        "replay_risk_rows": replay_rows,
        "local_risk_rows_exposed": int(seen[:local_rows].sum()),
        "replay_risk_rows_exposed": int(seen[local_rows:].sum()),
        "training_seconds": time.perf_counter() - started,
        "effective_learning_rate_init": float(
            model.booster[-1]._optimizer.learning_rate_init
        ),
        "frozen_scaler": True,
    }


def make_frames(ledger, data, job, origin):
    pieces = []
    stamp = lambda offset: origin - pd.Timedelta(days=offset)
    specs = [
        ("fit", pd.date_range(stamp(1001), stamp(301), freq="56D"), stamp(210)),
        ("validation", [stamp(210), stamp(182)], stamp(91)),
        ("audit", [stamp(91)], origin),
    ]
    for role, clocks, label_end in specs:
        for clock in clocks:
            part = landmarks(
                ledger,
                data,
                clock,
                label_end,
                job["world"],
                job["firm"],
                role,
                cap=None,
                build_cash=role != "fit",
            )
            if len(part):
                part["label_end"] = label_end
                pieces.append(part)
    full = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()
    evaluation = landmarks(
        ledger,
        data,
        origin,
        job["evaluation_label_end"],
        job["world"],
        job["firm"],
        "development_evaluation",
        cap=None,
    )
    if evaluation.empty:
        raise ValueError("Declared development context has no eligible invoices")
    return full, evaluation


def load_frames(target, ledger, data, job, origin):
    receipt = target / "data_receipt.json"
    if receipt.exists():
        for name, digest in read(receipt)["files"].items():
            if sha256(target / name) != digest:
                raise ValueError("Prepared census changed")
        return pd.read_parquet(target / "local_census.parquet"), pd.read_parquet(
            target / "evaluation_census.parquet"
        )
    started = time.perf_counter()
    full, evaluation = make_frames(ledger, data, job, origin)
    target.mkdir(parents=True, exist_ok=True)
    full.to_parquet(target / "local_census.parquet", index=False)
    evaluation.to_parquet(target / "evaluation_census.parquet", index=False)
    write(
        receipt,
        {
            "files": {
                name: sha256(target / name)
                for name in ("local_census.parquet", "evaluation_census.parquet")
            },
            "preparation_seconds": time.perf_counter() - started,
            "scoring_snapshot_cap": None,
        },
    )
    return full, evaluation


def arm_models(global_model, reference, replay, frame, arm, config, matched_base=None):
    caps = ARMS[arm] if matched_base is None else ARMS["A2"]
    training = capped_snapshots(frame, caps[0])
    fit = (
        training[training.role == "fit"].reset_index(drop=True)
        if len(training)
        else training
    )
    val = (
        frame[frame.role == "validation"].reset_index(drop=True)
        if len(frame)
        else frame
    )
    audit = frame[frame.role == "audit"].reset_index(drop=True) if len(frame) else frame
    record = {
        "arm": arm,
        "status": "insufficient_mature_local_windows",
        "fit_snapshots": len(fit),
        "validation_snapshots": len(val),
        "audit_snapshots": len(audit),
        "final_training_snapshots": len(training),
        "audit_passed": False,
        "tuning": [],
        "training": [],
    }
    base = {"finetuned": global_model, "audited": global_model}
    if (
        len(fit) < config["minimum_fit_rows"]
        or len(val) < config["minimum_validation_rows"]
        or len(audit) < config["minimum_audit_rows"]
    ):
        return base, record
    if (
        fit.origin.max() + pd.Timedelta(days=91) > val.origin.min()
        or val.origin.max() + pd.Timedelta(days=91) > audit.origin.min()
    ):
        raise ValueError("Overlapping local outcome windows")
    arrays, record["fit_data"] = sampled_risk(fit, caps[1])
    final_arrays, record["final_data"] = sampled_risk(training, caps[1])
    if matched_base is not None:
        budget_training = capped_snapshots(frame, ARMS[matched_base][0])
        budget_fit = budget_training[budget_training.role == "fit"].reset_index(
            drop=True
        )
        bfit, _ = sampled_risk(budget_fit, ARMS[matched_base][1])
        bfull, _ = sampled_risk(budget_training, ARMS[matched_base][1])
        record["matched_to"] = matched_base
    global_val = measured(global_model, val)[0]
    candidates = []
    validation_predictions = {}
    for epochs in config["neural_epochs"]:
        budget = (
            None
            if matched_base is None
            else min(
                step_budget(reference, len(bfit[1]), len(replay[1]), epochs),
                step_budget(reference, len(arrays[1]), len(replay[1]), epochs),
            )
        )
        model, trace = train_neural(reference, arrays, replay, epochs, config, budget)
        record["training"].append(dict(stage="selection", **trace))
        for alpha in config["local_weight_grid"]:
            pooled = pool(global_model, model, alpha)
            metrics, prediction = measured(pooled, val)
            guard = (
                metrics["integrated_brier13"]
                <= global_val["integrated_brier13"] * 1.02 + 0.0001
            )
            record["tuning"].append(
                dict(epochs=epochs, alpha=alpha, guard=bool(guard), **metrics)
            )
            validation_predictions[f"e{epochs}_a{alpha}"] = prediction
            if guard:
                candidates.append((metrics["score"], epochs, alpha, pooled))
    _, epochs, alpha, selected = min(candidates, key=lambda c: c[:3])
    # Validation alone locks epochs/alpha. Audit cannot try another candidate.
    audit_global, _ = measured(global_model, audit)
    audit_selected, _ = measured(selected, audit)
    accepted = (
        audit_selected["score"] <= audit_global["score"] - config["audit_minimum_gain"]
        and audit_selected["integrated_brier13"]
        <= audit_global["integrated_brier13"] * 1.02 + 0.0001
    )
    record.update(
        status="adapted",
        selected_epochs=epochs,
        selected_alpha=alpha,
        audit_passed=bool(accepted),
        audit_global=audit_global,
        audit_selected=audit_selected,
        validation_global=global_val,
        selected_validation=next(
            t for t in record["tuning"] if t["epochs"] == epochs and t["alpha"] == alpha
        ),
    )
    budget = (
        None
        if matched_base is None
        else min(
            step_budget(reference, len(bfull[1]), len(replay[1]), epochs),
            step_budget(reference, len(final_arrays[1]), len(replay[1]), epochs),
        )
    )
    final, trace = train_neural(reference, final_arrays, replay, epochs, config, budget)
    record["training"].append(dict(stage="final_refit", **trace))
    base["finetuned"] = pool(global_model, final, alpha)
    base["audited"] = base["finetuned"] if accepted else global_model
    record["final_refit_label_end"] = str(training.label_end.max().date())
    record["final_refit_uses_future_labels"] = False
    # All probabilities are saved, so selection and audits can be recomputed.
    predictions = {f"validation_{key}": p for key, p in validation_predictions.items()}
    for stage, rows in (("audit", audit),):
        predictions[f"{stage}_selected"] = measured(selected, rows)[1]
        predictions[f"{stage}_global"] = measured(global_model, rows)[1]
    return base, dict(record, _predictions=predictions)


def run_job(output, job, arms, config):
    output = Path(output)
    protocol_hash = sha256(output / "protocol.json")
    with threadpool_limits(limits=2), threadpool_limits(limits=1, user_api="blas"):
        global_model = CompactT1.load(OLD)
        reference = next(
            m
            for m in global_model.members
            if isinstance(m, LandmarkHazard) and m.name.startswith("neural")
        )
        reference_hash = hashlib.sha256(pickle.dumps(reference)).hexdigest()
        with np.load(SOURCE / "current_global_replay.npz", allow_pickle=False) as saved:
            replay = tuple(saved[k] for k in ("x", "y", "weights"))
        if job["world"] == "dai_phat":
            data, _ = load_demo(Path(job["directory"]))
            ledger = demo_ledger(data)
        else:
            ledger = next(
                ledger
                for firm, ledger in world_ledgers(Path(job["directory"]))
                if firm == job["firm"]
            )
            data = workspace_data(ledger)
        for origin_text in job["origins"]:
            started = time.perf_counter()
            origin = pd.Timestamp(origin_text)
            target = output / "contexts" / job["world"] / job["firm"] / origin_text
            done = target / "receipt.json"
            if done.exists():
                old = read(done)
                if old["protocol_sha256"] != protocol_hash:
                    raise ValueError("Context protocol changed")
                for name, digest in old["files"].items():
                    if sha256(target / name) != digest:
                        raise ValueError("Context checkpoint changed")
                if all(arm in old["arms"] for arm in arms):
                    continue
            full, evaluation = load_frames(target, ledger, data, job, origin)
            npred = {"global": measured(global_model, evaluation)[1]}
            files = dict(read(done)["files"]) if done.exists() else {}
            for arm in arms:
                arm_file = target / f"{arm}.json"
                arm_receipt = target / f"{arm}_receipt.json"
                if arm_receipt.exists():
                    locked = read(arm_receipt)
                    if locked["protocol_sha256"] != protocol_hash:
                        raise ValueError("Arm protocol changed")
                    for name, digest in locked["files"].items():
                        if sha256(target / name) != digest:
                            raise ValueError("Arm checkpoint changed")
                    continue
                matched_base = {"A2_U0": "A0", "A2_U1": "A1"}.get(arm)
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    models, record = arm_models(
                        global_model, reference, replay, full, arm, config, matched_base
                    )
                saved_predictions = record.pop("_predictions", {})
                metrics = {}
                for name, model in models.items():
                    metrics[name], prediction = measured(model, evaluation)
                    saved_predictions[f"evaluation_{name}"] = prediction
                saved_predictions["evaluation_global"] = npred["global"]
                record.update(
                    world=job["world"],
                    firm=job["firm"],
                    origin=origin_text,
                    evaluation_rows=len(evaluation),
                    evaluation=metrics,
                    evaluation_global=measured(global_model, evaluation)[0],
                    warning_messages=sorted({str(w.message) for w in caught}),
                )
                write(arm_file, record)
                np.savez_compressed(
                    target / f"{arm}_predictions.npz", **saved_predictions
                )
                with (target / f"{arm}_models.pkl").open("wb") as stream:
                    pickle.dump(models, stream, protocol=pickle.HIGHEST_PROTOCOL)
                names = [f"{arm}.json", f"{arm}_predictions.npz", f"{arm}_models.pkl"]
                arm_files = {name: sha256(target / name) for name in names}
                write(
                    arm_receipt, {"protocol_sha256": protocol_hash, "files": arm_files}
                )
                print(
                    f"{job['world']}/{job['firm']}/{origin_text} {arm}: {record['status']}; "
                    f"cash={metrics['finetuned']['score']:.6f}; audit={record['audit_passed']}",
                    flush=True,
                )
            all_arms = sorted(
                p.name.removesuffix("_receipt.json")
                for p in target.glob("*_receipt.json")
                if p.name != "data_receipt.json"
            )
            files.update({"data_receipt.json": sha256(target / "data_receipt.json")})
            for arm in all_arms:
                files.update(read(target / f"{arm}_receipt.json")["files"])
                files[f"{arm}_receipt.json"] = sha256(target / f"{arm}_receipt.json")
            write(
                done,
                {
                    "protocol_sha256": protocol_hash,
                    "arms": all_arms,
                    "files": files,
                    "elapsed_seconds": time.perf_counter() - started,
                },
            )
        if hashlib.sha256(pickle.dumps(reference)).hexdigest() != reference_hash:
            raise AssertionError("Global Neural was mutated")
    return {"world": job["world"], "firm": job["firm"], "contexts": len(job["origins"])}


def summarize(output, protocol, require_complete=True):
    rows, traces, data_rows = [], [], []
    for job in protocol["jobs"]:
        for origin in job["origins"]:
            target = output / "contexts" / job["world"] / job["firm"] / origin
            if require_complete and not (target / "receipt.json").exists():
                raise ValueError(f"Incomplete context: {target}")
            for path in sorted(target.glob("A*.json")):
                if path.name.endswith("_receipt.json"):
                    continue
                r = read(path)
                key = {
                    "world": r["world"],
                    "firm": r["firm"],
                    "origin": r["origin"],
                    "arm": r["arm"],
                    "scenario": job["scenario"],
                    "adapted": r["status"] == "adapted",
                    "audit_passed": r["audit_passed"],
                    "selected_epochs": r.get("selected_epochs"),
                    "selected_alpha": r.get("selected_alpha"),
                    "evaluation_rows": r["evaluation_rows"],
                }
                for mode, metrics in {
                    **r["evaluation"],
                    "global": r["evaluation_global"],
                }.items():
                    rows.append(
                        dict(
                            key,
                            mode=mode,
                            **{k: v for k, v in metrics.items() if k != "windows"},
                        )
                    )
                for t in r["training"]:
                    traces.append(dict(key, **t))
                for stage in ("fit", "final"):
                    if f"{stage}_data" in r:
                        data_rows.append(dict(key, stage=stage, **r[f"{stage}_data"]))
    metrics = pd.DataFrame(rows)
    if metrics.empty:
        raise ValueError("No finished development results")
    metrics.to_csv(output / "by_context.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(traces).to_csv(
        output / "training_updates.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(data_rows).to_csv(
        output / "training_data.csv", index=False, encoding="utf-8-sig"
    )
    groups = {
        "established_worlds": metrics[
            metrics.scenario.isin(["baseline", "credit", "supply"])
        ],
        "onboarding": metrics[metrics.scenario == "short_history"],
        "dai_phat": metrics[metrics.scenario == "demo"],
    }
    summaries = {}
    for group, frame in groups.items():
        summaries[group] = {}
        for (arm, mode), part in frame.groupby(["arm", "mode"]):
            means = (
                part.groupby(["world", "firm"])[
                    [
                        "score",
                        "integrated_brier13",
                        "cash_weekly_mae_vnd",
                        "cash_cumulative_mae_vnd",
                    ]
                ]
                .mean()
                .groupby("world")
                .mean()
                .mean()
            )
            summaries[group][f"{arm}_{mode}"] = dict(
                means.to_dict(),
                contexts=len(part),
                firms=len(part[["world", "firm"]].drop_duplicates()),
                worlds=part.world.nunique(),
                adapted_contexts=int(part.adapted.sum()),
                accepted_contexts=int(part.audit_passed.sum()),
            )
    primary = summaries["established_worlds"]
    controls = []
    for baseline, control in (("A0", "A2_U0"), ("A1", "A2_U1")):
        if (
            f"{baseline}_finetuned" in primary
            and "A2_finetuned" in primary
            and primary["A2_finetuned"]["score"]
            < primary[f"{baseline}_finetuned"]["score"]
        ):
            controls.append(control)
    result = {
        "status": "complete" if require_complete else "partial",
        "data_role": "reused development only",
        "groups": summaries,
        "matched_update_controls_triggered": controls,
        "final_test_opened": False,
        "model_activation": False,
    }
    write(output / "results.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument(
        "--job", help="Optional smoke job world/firm; does not finalize the run"
    )
    parser.add_argument("--summarize", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 4:
        parser.error("workers must be in [1, 4]")
    output = args.output.resolve()
    protocol = make_protocol(output, args.workers)
    if args.prepare_only:
        print(
            json.dumps(
                {
                    "protocol_sha256": sha256(output / "protocol.json"),
                    "jobs": len(protocol["jobs"]),
                    "contexts": protocol["development_contexts"],
                }
            ),
            flush=True,
        )
        return
    if args.summarize:
        print(json.dumps(summarize(output, protocol), ensure_ascii=False), flush=True)
        return
    jobs = [
        job
        for job in protocol["jobs"]
        if not args.job or f"{job['world']}/{job['firm']}" == args.job
    ]
    if not jobs:
        parser.error("Unknown development job")

    def phase(arms):
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = [
                executor.submit(run_job, str(output), job, arms, protocol["adaptation"])
                for job in jobs
            ]
            for future in as_completed(futures):
                print(json.dumps(future.result()), flush=True)

    phase(list(ARMS))
    if args.job:
        print("Smoke job finished; full development run still required", flush=True)
        return
    results = summarize(output, protocol)
    if results["matched_update_controls_triggered"]:
        phase(results["matched_update_controls_triggered"])
        results = summarize(output, protocol)
    write(
        output / "completion.json",
        {
            "protocol_sha256": sha256(output / "protocol.json"),
            "results_sha256": sha256(output / "results.json"),
            "contexts": protocol["development_contexts"],
            "final_test_opened": False,
            "finished_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        },
    )
    print(json.dumps(results, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
