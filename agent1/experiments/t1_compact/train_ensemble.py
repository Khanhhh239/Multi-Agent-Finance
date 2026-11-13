"""Fit the T1 catalog once, search cached validation predictions, then freeze/test.

The source run supplies identical landmark tables and locked World/time roles.
Test tables are loaded only after the selected artifact passes the SHAP gate.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import shutil
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    ExtraTreesClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import SplineTransformer, StandardScaler
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1.adaptive.compact_ensemble import CompactEnsemble, CompactHazard, CompactRule
from agent1.adaptive.compact_t1 import (
    FEATURES,
    SCHEMA,
    CompactT1,
    explain_compact,
    sha256,
    workspace_context,
)
from experiments.t1_compact.historical_workspace import CATALOG
from experiments.t1_compact.train import PROTOCOL as LANDMARK_PROTOCOL
from experiments.t1_compact.train import risk_rows, world_ledgers, write_json

SEED = 261112
BASELINES = ("due", "customer", "survival")
SOURCE_FILES = (
    "agent1/adaptive/compact_t1.py",
    "agent1/adaptive/compact_ensemble.py",
    "agent1/adaptive/methods.py",
    "agent1/adaptive/explanations.py",
    "experiments/t1_compact/train.py",
    "experiments/t1_compact/train_ensemble.py",
)


def candidate_specs():
    """Every individual catalog entry participates, including its named presets."""
    result = []
    for name, family, title, _ in CATALOG:
        if family == "ensemble":
            continue
        package = {"lightgbm": "lightgbm", "xgboost": "xgboost"}.get(name)
        eligible = package is None or importlib.util.find_spec(package) is not None
        result.append(
            {
                "name": name,
                "family": family,
                "title": title,
                "eligible": eligible,
                "reason": "available" if eligible else f"missing dependency {package}",
                "trials": 1 if name in BASELINES else 2,
            }
        )
    return result


def estimator_for(name, trial, feature_count=None):
    """Two predeclared configurations per learned entry share one risk sample."""
    feature_count = len(FEATURES) if feature_count is None else feature_count
    if name in ("logistic", "logistic_regularized", "spline"):
        strength = (0.1 if name == "logistic_regularized" else 1.0) / (10**trial)
        logistic = LogisticRegression(C=strength, max_iter=400, random_state=SEED)
        if name == "spline":
            transform = ColumnTransformer(
                [
                    (
                        "time",
                        SplineTransformer(n_knots=4 + trial, degree=2),
                        [2, feature_count],
                    )
                ],
                remainder="passthrough",
            )
            return make_pipeline(transform, StandardScaler(), logistic)
        return make_pipeline(StandardScaler(), logistic)
    if name in ("forest", "forest_shallow", "extra"):
        classifier = ExtraTreesClassifier if name == "extra" else RandomForestClassifier
        depth = 5 if name == "forest_shallow" else 8 + 2 * trial
        return classifier(
            n_estimators=64 + 32 * trial,
            max_depth=depth,
            min_samples_leaf=40 + 40 * trial,
            n_jobs=2,
            random_state=SEED,
        )
    if name in ("hist", "hist_regularized"):
        return HistGradientBoostingClassifier(
            max_iter=96 + 24 * trial,
            max_leaf_nodes=9 + 6 * trial,
            learning_rate=0.05,
            l2_regularization=10 if name == "hist_regularized" else 5,
            early_stopping=False,
            random_state=SEED,
        )
    if name == "lightgbm":
        from lightgbm import LGBMClassifier

        return LGBMClassifier(
            n_estimators=96 + 24 * trial,
            num_leaves=9 + 6 * trial,
            min_child_samples=100 - 20 * trial,
            learning_rate=0.05,
            reg_lambda=10 - 5 * trial,
            max_bin=63,
            verbosity=-1,
            deterministic=True,
            force_col_wise=True,
            n_jobs=2,
            random_state=SEED,
        )
    if name == "xgboost":
        from xgboost import XGBClassifier

        return XGBClassifier(
            n_estimators=96 + 24 * trial,
            max_depth=3 + trial,
            learning_rate=0.05,
            reg_lambda=10 - 5 * trial,
            tree_method="hist",
            n_jobs=2,
            random_state=SEED,
        )
    if name.startswith("neural"):
        shape = {
            "neural": (32, 16),
            "neural_wide": (64, 32),
            "neural_deep": (64, 32, 16),
        }[name]
        return make_pipeline(
            StandardScaler(),
            MLPClassifier(
                hidden_layer_sizes=shape,
                alpha=(0.1 if name == "neural_deep" else 0.01) * (10**trial),
                batch_size=1024,
                max_iter=30 + 15 * trial,
                early_stopping=False,
                random_state=SEED,
            ),
        )
    raise ValueError(f"Unknown compact candidate {name}")


def empirical_hazards(x, y, weights):
    buckets = np.minimum(np.maximum(x[:, 2], 0).astype(int) // 30, 4)
    weeks = x[:, -1].astype(int) - 1
    total = np.bincount(weeks, weights=weights, minlength=13)
    events = np.bincount(weeks, weights=weights * y, minlength=13)
    pooled = (events + 0.5) / (total + 5)
    result = np.empty((5, 13))
    for bucket in range(5):
        take = buckets == bucket
        risk = np.bincount(weeks[take], weights=weights[take], minlength=13)
        paid = np.bincount(weeks[take], weights=weights[take] * y[take], minlength=13)
        result[bucket] = (paid + 20 * pooled) / (risk + 20)
    return result


def estimator_parameters(estimator):
    return json.loads(
        json.dumps(estimator.get_params(deep=False), default=repr), parse_constant=str
    )


def load_role(source, role, audit):
    pieces = []
    for entry in audit:
        if entry["role"] != role:
            continue
        path = source / "prepared" / f"{entry['world']}.parquet"
        if sha256(path) != entry["sha256"]:
            raise ValueError(f"Prepared source hash mismatch {path}")
        frame = pd.read_parquet(path)
        if set(frame.role) != {role} or set(frame.world) != {entry["world"]}:
            raise ValueError("Prepared source role mismatch")
        pieces.append(frame)
    frame = pd.concat(pieces, ignore_index=True)
    if frame.duplicated(["world", "firm", "origin", "invoice_id"]).any():
        raise ValueError("Duplicate landmark keys")
    return frame


def row_weights(frame):
    firms = frame.groupby("world").firm.transform("nunique").to_numpy(float)
    origins = (
        frame.groupby(["world", "firm"]).origin.transform("nunique").to_numpy(float)
    )
    anchors = (
        frame.groupby(["world", "firm", "origin"])
        .invoice_id.transform("size")
        .to_numpy(float)
    )
    weights = 1 / (frame.world.nunique() * firms * origins * anchors)
    return weights / weights.sum()


def evaluation_context(frame):
    weights = row_weights(frame)
    windows = {}
    for origin in sorted(frame.origin.unique()):
        take = (frame.origin == origin).to_numpy()
        window_weights = np.zeros(len(frame))
        window_weights[take] = row_weights(frame[take])
        windows[str(pd.Timestamp(origin).date())] = window_weights
    truth = np.column_stack(
        [(frame.paid_days <= 7 * horizon).to_numpy(float) for horizon in (4, 13)]
    )
    return {"weights": weights, "windows": windows, "truth": truth}


def cumulative_probabilities(distribution):
    p = np.asarray(distribution, float)
    if p.ndim != 2 or p.shape[1] != 14 or not np.isfinite(p).all() or (p < 0).any():
        raise ValueError("Invalid cached payment distribution")
    if not np.allclose(p.sum(1), 1.0, atol=1e-12, rtol=0):
        raise ValueError("Cached payment distribution is not normalized")
    return np.column_stack((p[:, :4].sum(1), p[:, :13].sum(1)))


def score_cumulative(probabilities, context):
    error = (probabilities - context["truth"]) ** 2
    loss = error.mean(axis=1)
    return {
        "score": float(context["weights"] @ loss),
        "brier4": float(context["weights"] @ error[:, 0]),
        "brier13": float(context["weights"] @ error[:, 1]),
        "windows": {
            key: float(weights @ loss) for key, weights in context["windows"].items()
        },
    }


def stable_improvement(before, after, rule):
    gains = np.array(
        [before["windows"][key] - after["windows"][key] for key in before["windows"]]
    )
    return bool(
        before["score"] - after["score"] >= rule["minimum_mean_gain"]
        and (gains >= rule["minimum_window_gain"]).sum()
        >= int(np.ceil(len(gains) * rule["minimum_window_fraction"]))
        and gains.min() >= -rule["maximum_window_regression"]
    )


def weight_grid(size, units=20):
    if size == 2:
        return [(first / units, (units - first) / units) for first in range(1, units)]
    if size == 3:
        return [
            (first / units, second / units, (units - first - second) / units)
            for first in range(1, units - 1)
            for second in range(1, units - first)
        ]
    raise ValueError("Weight search requires two or three members")


def additions(current, predictions, context, rule):
    """Find stable additions using only the saved validation probabilities."""
    trials = []
    members = current["members"]
    for name in sorted(set(predictions) - set(members)):
        names = members + [name]
        for weights in weight_grid(len(names)):
            pooled = sum(
                weight * predictions[member] for weight, member in zip(weights, names)
            )
            measured = score_cumulative(pooled, context)
            trials.append(
                dict(
                    members=names,
                    weights=list(weights),
                    **measured,
                    stable=stable_improvement(current, measured, rule),
                )
            )
    return sorted(
        trials, key=lambda trial: (trial["score"], trial["members"], trial["weights"])
    )


def latency_contexts(source, validation, inputs):
    inventory = json.loads((source / "inventory.json").read_text(encoding="utf-8"))
    contexts = []
    for world in sorted(validation.world.unique()):
        entry = next(entry for entry in inventory if entry["name"] == world)
        origin = validation[validation.world == world].origin.max()
        largest = None
        for firm, ledger in world_ledgers(source / entry["directory"]):
            history = ledger.snapshot(origin)
            opened = history[
                (history.remaining_amount > 0.01) & history.written_off_at.isna()
            ].copy()
            if len(opened) and (
                largest is None or len(opened) > len(largest["opened"])
            ):
                opened.attrs["compact_context"] = history
                largest = {
                    "name": f"{world}/{firm}",
                    "origin": origin,
                    "opened": opened,
                }
        if largest is None:
            raise ValueError("Validation World has no latency context")
        contexts.append(largest)
    if inputs is not None:
        import csv

        data = {}
        for index, kind in ((1, "invoices"), (3, "payments"), (6, "actions")):
            with (inputs / f"{index:02}_{kind}.csv").open(
                encoding="utf-8-sig", newline=""
            ) as stream:
                rows = [
                    {key: value for key, value in row.items() if value != ""}
                    for row in csv.DictReader(stream)
                ]
            for row in rows:
                if "amount" in row:
                    row["amount"] = int(row["amount"])
            data[kind] = rows
        origin = pd.Timestamp("2026-07-31")
        history = workspace_context(data, origin)
        opened = history[
            (history.remaining_amount > 0.01) & history.written_off_at.isna()
        ].copy()
        opened.attrs["compact_context"] = history
        if opened.empty:
            raise ValueError("Workspace latency context is empty")
        contexts.append({"name": "workspace_large", "origin": origin, "opened": opened})
    return contexts


def benchmark_ensemble(model, contexts, repetitions=20):
    """Measure the whole served function and exact grouped SHAP, one invoice."""
    timings = {context["name"]: [] for context in contexts}
    records = []
    errors = []
    references = {}
    sensitivity_changes = []
    for context in contexts:
        opened = context["opened"]
        probabilities = model.distribution(opened)[:, :4].sum(1)
        records.append(
            [
                {
                    "invoice_id": str(row.invoice_id),
                    "customer_id": str(row.customer_id),
                    "payment_probability_4w": float(probabilities[position]),
                }
                for position, row in enumerate(opened.itertuples())
            ]
        )
    for repeat in range(repetitions + 1):
        for index, context in enumerate(contexts):
            position = (repeat * 997) % len(records[index])
            rows = [dict(records[index][position])]
            started = time.perf_counter()
            reference = explain_compact(
                rows, context["opened"], [(1.0, model)], context["origin"]
            )
            duration = time.perf_counter() - started
            errors.append(rows[0]["payment_explanation"]["additivity_error"])
            explanation = rows[0]["payment_explanation"]
            references[context["name"]] = {
                key: explanation["reference"].get(key)
                for key in (
                    "count",
                    "population",
                    "selection",
                    "audit_sample_count",
                    "max_weighted_cdf_distance",
                )
            }
            sensitivity_changes.extend(
                factor["stability"].get("max_change_pp", 0.0)
                for factor in explanation["factors"]
            )
            if repeat:
                timings[context["name"]].append(duration)
    measured = {
        name: {
            "p50_seconds": float(np.median(values)),
            "p95_seconds": float(np.quantile(values, 0.95)),
            "max_seconds": float(max(values)),
            "repetitions": len(values),
        }
        for name, values in timings.items()
    }
    p95 = max(result["p95_seconds"] for result in measured.values())
    return {
        "p95_seconds": p95,
        "passed": p95 <= 1.0,
        "contexts": measured,
        "open_populations": {
            context["name"]: len(context["opened"]) for context in contexts
        },
        "max_additivity_error": float(max(errors)),
        "background_count": reference["count"],
        "references": references,
        "max_background_sensitivity_change_pp": float(
            max(sensitivity_changes, default=0.0)
        ),
        "model_and_context_ready": True,
        "feature_preparation_included": True,
        "probability_pooling_included": True,
        "calibration": {"method": "identity"},
        "model_loading_included": False,
        "ledger_context_construction_included": False,
        "processor": platform.processor(),
        "python": platform.python_version(),
    }


def fit_candidates(train, validation, output, protocol):
    x, y, weights = risk_rows(train, tuple(range(len(FEATURES))))
    total = len(y)
    count = min(total, protocol["budget"]["risk_rows"])
    indices = np.sort(np.random.default_rng(SEED).choice(total, count, replace=False))
    x, y, weights = x[indices], y[indices], weights[indices]
    weights *= len(weights) / weights.sum()
    sample_hash = hashlib.sha256(
        indices.tobytes() + x.tobytes() + y.tobytes() + weights.tobytes()
    ).hexdigest()
    write_json(
        output / "training_sample.json",
        {
            "total_risk_rows": total,
            "fitted_risk_rows": count,
            "sample_sha256": sample_hash,
            "events": int(y.sum()),
        },
    )
    hazard = empirical_hazards(x, y, weights)
    features = validation[list(FEATURES)].to_numpy(float)
    context = evaluation_context(validation)
    models, predictions, records = {}, {}, []
    for spec in protocol["candidates"]:
        name = spec["name"]
        if not spec["eligible"]:
            records.append(dict(**spec, status="unavailable"))
            continue
        completed = []
        for trial in range(spec["trials"]):
            directory = output / "trials" / f"{name}_{trial}"
            directory.mkdir(parents=True, exist_ok=True)
            receipt = directory / "trial.json"
            if receipt.exists():
                record = json.loads(receipt.read_text(encoding="utf-8"))
                if record["sample_sha256"] != sample_hash or record[
                    "protocol_sha256"
                ] != sha256(output / "protocol.json"):
                    raise ValueError("Cached trial inputs changed")
                if (
                    sha256(directory / "validation.npz") != record["prediction_sha256"]
                    or sha256(directory / "model/metadata.json")
                    != record["model_metadata_sha256"]
                ):
                    raise ValueError("Cached trial hash mismatch")
                model = CompactT1.load(directory / "model")
                with np.load(directory / "validation.npz", allow_pickle=False) as cache:
                    distribution = cache["distribution"]
            else:
                started = time.perf_counter()
                caught_messages = []
                if name in BASELINES:
                    model = CompactRule(name, hazard)
                else:
                    estimator = estimator_for(name, trial)
                    fit_options = (
                        {f"{estimator.steps[-1][0]}__sample_weight": weights}
                        if isinstance(estimator, Pipeline)
                        else {"sample_weight": weights}
                    )
                    with warnings.catch_warnings(record=True) as caught:
                        warnings.simplefilter("always")
                        estimator.fit(x, y, **fit_options)
                    caught_messages = sorted(
                        {str(warning.message) for warning in caught}
                    )
                    model = CompactHazard(estimator, name)
                distribution = model.distribution_from_features(features)
                measured = score_cumulative(
                    cumulative_probabilities(distribution), context
                )
                model.save(
                    directory / "model",
                    {"candidate": name, "trial": trial, "sample_sha256": sample_hash},
                )
                np.savez_compressed(
                    directory / "validation.npz", distribution=distribution
                )
                record = dict(
                    name=name,
                    trial=trial,
                    **measured,
                    seconds=time.perf_counter() - started,
                    sample_sha256=sample_hash,
                    protocol_sha256=sha256(output / "protocol.json"),
                    prediction_sha256=sha256(directory / "validation.npz"),
                    model_metadata_sha256=sha256(directory / "model/metadata.json"),
                    parameters={}
                    if name in BASELINES
                    else estimator_parameters(estimator),
                    warnings=caught_messages,
                )
                # Estimator parameters can contain transformer objects. Their repr is
                # recorded for audit, while the fitted object is retained separately.
                write_json(receipt, record)
                print(
                    json.dumps(
                        {
                            "event": "fit",
                            "name": name,
                            "trial": trial,
                            "score": record["score"],
                            "seconds": record["seconds"],
                            "warnings": caught_messages,
                        }
                    ),
                    flush=True,
                )
            completed.append((record, model, distribution))
        best, model, distribution = min(
            completed, key=lambda item: (item[0]["score"], item[0]["trial"])
        )
        models[name] = model
        predictions[name] = cumulative_probabilities(distribution)
        destination = output / "validation_predictions" / f"{name}.npz"
        destination.parent.mkdir(exist_ok=True)
        np.savez_compressed(destination, distribution=distribution)
        records.append(
            dict(
                **spec,
                status="trained",
                selected_trial=best["trial"],
                score=best["score"],
                windows=best["windows"],
                prediction_sha256=sha256(destination),
                trials_completed=len(completed),
            )
        )
    write_json(output / "candidate_results.json", records)
    return models, predictions, records


def test_metrics(model, frame):
    distribution = model.distribution_from_features(
        frame[list(FEATURES)].to_numpy(float)
    )
    probabilities = cumulative_probabilities(distribution)
    result = score_cumulative(probabilities, evaluation_context(frame))
    result["anchors"] = len(frame)
    result["worlds"] = frame.world.nunique()
    result["firms"] = frame.groupby(["world", "firm"]).ngroups
    reliability = {}
    truth = evaluation_context(frame)["truth"]
    weights = row_weights(frame)
    for column, horizon in enumerate((4, 13)):
        probability = probabilities[:, column]
        bins = np.minimum((probability * 10).astype(int), 9)
        reliability[f"bias{horizon}"] = float(
            weights @ (probability - truth[:, column])
        )
        reliability[f"ece{horizon}"] = float(
            sum(
                abs(
                    np.sum(
                        weights[bins == bucket]
                        * (probability - truth[:, column])[bins == bucket]
                    )
                )
                for bucket in range(10)
            )
        )
    result.update(reliability)
    worlds = []
    for world in sorted(frame.world.unique()):
        take = (frame.world == world).to_numpy()
        worlds.append(
            dict(
                world=world,
                **score_cumulative(
                    probabilities[take], evaluation_context(frame[take])
                ),
            )
        )
    return result, worlds, distribution


def select_ensemble(models, predictions, validation, contexts, output, protocol):
    context = evaluation_context(validation)
    singles = [
        dict(members=[name], weights=[1.0], **score_cumulative(probability, context))
        for name, probability in predictions.items()
    ]
    singles.sort(key=lambda item: (item["score"], item["members"]))
    timing_records = []
    current = None
    for candidate in singles:
        pool = CompactEnsemble(
            [models[name] for name in candidate["members"]], candidate["weights"]
        )
        latency = benchmark_ensemble(pool, contexts)
        timing_records.append(
            dict(members=candidate["members"], weights=candidate["weights"], **latency)
        )
        print(
            json.dumps(
                {
                    "event": "shap_gate",
                    "members": candidate["members"],
                    "p95_seconds": latency["p95_seconds"],
                    "passed": latency["passed"],
                }
            ),
            flush=True,
        )
        if latency["passed"]:
            current = dict(candidate, latency=latency)
            break
    if current is None:
        write_json(output / "latency_trials.json", timing_records)
        raise ValueError("No single candidate meets the SHAP latency budget")
    steps = [current]
    searches = []
    while len(current["members"]) < 3:
        trials = additions(current, predictions, context, protocol["stability"])
        searches.extend(trials)
        accepted = None
        failed_member_sets = set()
        for candidate in trials:
            member_set = tuple(candidate["members"])
            if not candidate["stable"] or member_set in failed_member_sets:
                continue
            pool = CompactEnsemble(
                [models[name] for name in candidate["members"]], candidate["weights"]
            )
            latency = benchmark_ensemble(pool, contexts)
            timing_records.append(
                dict(
                    members=candidate["members"],
                    weights=candidate["weights"],
                    **latency,
                )
            )
            print(
                json.dumps(
                    {
                        "event": "shap_gate",
                        "members": candidate["members"],
                        "weights": candidate["weights"],
                        "p95_seconds": latency["p95_seconds"],
                        "passed": latency["passed"],
                    }
                ),
                flush=True,
            )
            if latency["passed"]:
                accepted = dict(candidate, latency=latency)
                break
            # Positive pooling weights preserve the inference workload. Reuse
            # a failed timing result for the other weights of these members.
            failed_member_sets.add(member_set)
        if accepted is None:
            break
        current = accepted
        steps.append(current)
    write_json(output / "ensemble_search.json", searches)
    write_json(output / "latency_trials.json", timing_records)
    residuals = {
        name: (probability - context["truth"]).ravel()
        for name, probability in predictions.items()
    }
    pd.DataFrame(residuals).corr().to_csv(
        output / "validation_residual_correlations.csv"
    )
    selection = {
        "selected": current,
        "steps": steps,
        "ranked_singles": singles,
        "stability": protocol["stability"],
        "combination_count": len(searches),
        "ensemble_candidate_policy": "Eligible individual models may join only after stable validation improvement and a passing whole-ensemble SHAP measurement.",
    }
    write_json(output / "selection.json", selection)
    return CompactEnsemble(
        [models[name] for name in current["members"]], current["weights"]
    ), selection


def build_protocol(source, inputs):
    if (
        json.loads((source / "protocol.json").read_text(encoding="utf-8"))
        != LANDMARK_PROTOCOL
    ):
        raise ValueError(
            "Source landmark protocol differs from the declared source split"
        )
    audit = json.loads((source / "data_audit.json").read_text(encoding="utf-8"))
    roles = {entry["world"]: entry["role"] for entry in audit}
    inventory = json.loads((source / "inventory.json").read_text(encoding="utf-8"))
    if (
        roles != {entry["name"]: entry["role"] for entry in inventory}
        or len(roles) != 14
    ):
        raise ValueError("Incomplete or inconsistent World roles")
    input_files = (
        {}
        if inputs is None
        else {
            str(inputs / file): sha256(inputs / file)
            for file in ("01_invoices.csv", "03_payments.csv", "06_actions.csv")
        }
    )
    return {
        "version": "compact-t1-cached-ensemble-v1",
        "seed": SEED,
        "source": str(source),
        "source_protocol_sha256": sha256(source / "protocol.json"),
        "source_audit_sha256": sha256(source / "data_audit.json"),
        "source_inventory_sha256": sha256(source / "inventory.json"),
        "feature_schema": SCHEMA,
        "feature_names": list(FEATURES),
        "feature_selection": "fixed shared ten-feature schema declared before fitting",
        "candidates": candidate_specs(),
        "budget": {
            "trials_per_learned_entry": 2,
            "cpu_threads": 2,
            "blas_threads": 1,
            "risk_rows": 100000,
            "sampling": "one shared seeded uniform risk-row sample with original World/firm/origin weights",
            "baseline_trials": 1,
            "validation_refits": 0,
        },
        "score": "equal World, then firm, then origin mean of Paid Brier4 and Brier13",
        "validation_origins": LANDMARK_PROTOCOL["validation_origins"],
        "available_asof": LANDMARK_PROTOCOL["available_asof"],
        "stability": {
            "minimum_mean_gain": 0.0001,
            "minimum_window_gain": 0.00001,
            "minimum_window_fraction": 0.75,
            "maximum_window_regression": 0.001,
        },
        "maximum_members": 3,
        "positive_weight_step": 0.05,
        "calibration": {"method": "identity"},
        "latency_budget": {
            "single_invoice_p95_seconds": 1.0,
            "repetitions_per_context": 20,
            "context_selection": "largest open firm in each validation World at the last validation origin, plus supplied Workspace inputs",
            "model_and_context_ready": True,
            "feature_preparation_included": True,
        },
        "latency_input_hashes": input_files,
        "source_hashes": {file: sha256(ROOT / file) for file in SOURCE_FILES},
        "limitations": [
            "The reused synthetic test Worlds were evaluated in the source experiment. Their final scores are reference evaluations on a reused holdout.",
            "World replay uses declared synthetic fallback assumptions for absent historical macro source files.",
            "Grouped exact SHAP uses at most 24 finite reference invoices and six groups. Background sensitivity and hybrid support are unmeasured.",
            "A bounded training budget and simulator-family evaluation leave real-company accuracy unverified.",
        ],
    }


def report(output, protocol, selection, result):
    chosen = selection["selected"]
    members = ", ".join(
        f"{name} {weight:.0%}"
        for name, weight in zip(chosen["members"], chosen["weights"])
    )
    trained = json.loads(
        (output / "candidate_results.json").read_text(encoding="utf-8")
    )
    rows = [
        "# T1 validation ensemble — 12/11/2026",
        "",
        f"Tổ hợp đã đóng băng gồm **{members}**.",
        "",
        (
            f"Validation Brier trung bình 4/13 tuần **{chosen['score']:.6f}**. "
            f"Test cuối **{result['selected']['score']:.6f}**. "
            f"SHAP một hóa đơn có p95 lớn nhất qua các context **{chosen['latency']['p95_seconds']:.4f} giây**."
        ),
        "",
        "## Quy trình đã chạy",
        "",
        (
            f"Đã train {sum(item['status'] == 'trained' for item in trained)} ứng viên trong danh mục T1. "
            "Mỗi ứng viên học có hai cấu hình tuning, dùng chung mẫu 100.000 risk-row và trọng số World/doanh nghiệp/origin. "
            "Ba baseline dùng một lượt ước lượng. Tuning giới hạn bằng số cấu hình và tài nguyên CPU. Thời gian từng lượt được lưu riêng."
        ),
        "",
        (
            "Giữ cố định mười feature chung trước khi train. Lưu toàn bộ phân phối validation của từng trial trong `trials/` "
            "và bản được chọn của từng model trong `validation_predictions/`. Tìm tổ hợp và trọng số từ các dự báo này. "
            "Xác suất dùng phép gộp lồi trực tiếp và cấu hình calibration identity."
        ),
        "",
        (
            "Bắt đầu từ model đơn có validation tốt nhất đáp ứng ngân sách SHAP. "
            "Mỗi lần thêm model yêu cầu giảm Brier trung bình ít nhất 0,0001, cải thiện ít nhất 3/4 cửa sổ "
            "với mức giảm tối thiểu 0,00001, và mức tăng lỗi mỗi cửa sổ tối đa 0,001. "
            "Trọng số dương trên lưới bước 0,05 được tìm lại cho toàn bộ thành viên sau mỗi lần thêm. "
            "Các ngưỡng này được khai báo trong protocol trước khi train."
        ),
        "",
        (
            f"Đã chấm {selection['combination_count']} cấu hình tổ hợp bằng validation. "
            "`selection.json` lưu từng bước thêm model. `latency_trials.json` lưu cổng SHAP cho toàn bộ tổ hợp được cân nhắc giữ lại. "
            "SHAP chạy trực tiếp qua hàm phân phối đang phục vụ, gồm tất cả thành viên và trọng số. "
            "Đo với model/context đã nạp, gồm chuẩn bị feature và 20 lần lặp mỗi context."
        ),
        "",
        (
            "`frozen.json` khóa hash artifact, feature, thành viên, trọng số và quyết định validation trước khi đọc bảng test. "
            "Test chỉ tạo số đo đánh giá cuối. `test_results.json` gồm tổ hợp đã khóa và model đơn tham chiếu đã khóa cùng lúc."
        ),
        "",
        "## Ứng viên",
        "",
        "| Model | Trial được chọn | Validation Brier |",
        "|---|---|---|",
    ]
    for item in sorted(trained, key=lambda item: item.get("score", float("inf"))):
        if item["status"] == "trained":
            rows.append(
                f"| {item['name']} | {item['selected_trial']} | {item['score']:.6f} |"
            )
        else:
            rows.append(f"| {item['name']} | {item['reason']} | — |")
    rows.extend(["", "## Giới hạn", ""])
    rows.extend(f"- {limitation}" for limitation in protocol["limitations"])
    (output / "REPORT.md").write_text("\n".join(rows) + "\n", encoding="utf-8")


def run(source, output, inputs=None, selection_only=False):
    source, output = source.resolve(), output.resolve()
    inputs = inputs.resolve() if inputs is not None else None
    output.mkdir(parents=True, exist_ok=True)
    protocol = build_protocol(source, inputs)
    protocol_path = output / "protocol.json"
    if (
        protocol_path.exists()
        and json.loads(protocol_path.read_text(encoding="utf-8")) != protocol
    ):
        raise ValueError("Experiment inputs or code changed. Use a new run directory.")
    write_json(protocol_path, protocol)
    for file in SOURCE_FILES:
        destination = output / "runtime_source" / file
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / file, destination)
    if (output / "test_results.json").exists():
        print(
            json.dumps({"event": "already_complete", "output": str(output)}), flush=True
        )
        return
    audit = json.loads((source / "data_audit.json").read_text(encoding="utf-8"))
    train = load_role(source, "train", audit)
    validation = load_role(source, "validation", audit)
    if (
        set(train.world) & set(validation.world)
        or train.origin.max() + pd.Timedelta(days=91) > validation.origin.min()
    ):
        raise ValueError("World/time leakage in training and validation")
    if set(validation.origin.dt.strftime("%Y-%m-%d")) != set(
        protocol["validation_origins"]
    ):
        raise ValueError("Validation windows differ from the locked protocol")
    if validation.origin.max() + pd.Timedelta(days=91) >= pd.Timestamp(
        protocol["available_asof"]
    ):
        raise ValueError("Validation labels unavailable at the declared serving date")
    row_path = output / "validation_rows.parquet"
    validation.to_parquet(row_path, index=False)
    print(
        json.dumps(
            {
                "event": "data_ready",
                "train_anchors": len(train),
                "validation_anchors": len(validation),
                "train_worlds": train.world.nunique(),
                "validation_worlds": validation.world.nunique(),
            }
        ),
        flush=True,
    )
    models, predictions, _records = fit_candidates(train, validation, output, protocol)
    contexts = latency_contexts(source, validation, inputs)
    frozen_path = output / "frozen.json"
    if frozen_path.exists():
        frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
        if (
            sha256(output / "artifact/metadata.json")
            != frozen["artifact_metadata_sha256"]
            or sha256(output / "selection.json") != frozen["selection_sha256"]
        ):
            raise ValueError("Frozen selection changed")
        selection = json.loads((output / "selection.json").read_text(encoding="utf-8"))
        model = CompactT1.load(output / "artifact")
    else:
        model, selection = select_ensemble(
            models, predictions, validation, contexts, output, protocol
        )
        model.save(
            output / "artifact",
            {
                "available_asof": protocol["available_asof"],
                "activation": "candidate_only",
                "synthetic": True,
                "data_fingerprint": protocol["source_audit_sha256"],
                "source_sha256": protocol["source_hashes"][
                    "agent1/adaptive/compact_ensemble.py"
                ],
                "protocol_sha256": sha256(protocol_path),
                "validation": selection["selected"],
            },
        )
        reference = selection["ranked_singles"][0]
        reference_name = reference["members"][0]
        models[reference_name].save(
            output / "single_reference", {"candidate": reference_name}
        )
        frozen = {
            "artifact_metadata_sha256": sha256(output / "artifact/metadata.json"),
            "reference_metadata_sha256": sha256(
                output / "single_reference/metadata.json"
            ),
            "selection_sha256": sha256(output / "selection.json"),
            "protocol_sha256": sha256(protocol_path),
            "validation_rows_sha256": sha256(row_path),
            "feature_names": list(FEATURES),
            "members": selection["selected"]["members"],
            "weights": selection["selected"]["weights"],
            "calibration": {"method": "identity"},
            "test_access": "pending final evaluation",
        }
        write_json(frozen_path, frozen)
        print(
            json.dumps(
                {
                    "event": "frozen",
                    "members": frozen["members"],
                    "weights": frozen["weights"],
                }
            ),
            flush=True,
        )
    if selection_only:
        return
    # The first test-table read and every test prediction occur below the freeze.
    model = CompactT1.load(output / "artifact")
    test = load_role(source, "test", audit)
    if set(test.world) & (
        set(train.world) | set(validation.world)
    ) or test.origin.min() < pd.Timestamp(protocol["available_asof"]):
        raise ValueError("World/time leakage in the final test")
    selected, worlds, distribution = test_metrics(model, test)
    reference_model = CompactT1.load(output / "single_reference")
    reference, reference_worlds, _ = test_metrics(reference_model, test)
    np.savez_compressed(output / "test_predictions.npz", distribution=distribution)
    write_json(output / "test_by_world.json", worlds)
    write_json(output / "reference_by_world.json", reference_worlds)
    result = {
        "selected": selected,
        "best_validation_single": reference,
        "frozen_sha256": sha256(frozen_path),
        "artifact_metadata_sha256": frozen["artifact_metadata_sha256"],
        "selection_uses_test": False,
        "evaluation_scope": "reused synthetic reference holdout",
        "test_predictions_sha256": sha256(output / "test_predictions.npz"),
    }
    write_json(output / "test_results.json", result)
    report(output, protocol, selection, result)
    print(
        json.dumps(
            {
                "event": "complete",
                "output": str(output),
                "members": frozen["members"],
                "weights": frozen["weights"],
                "validation": selection["selected"]["score"],
                "test": selected["score"],
                "shap_p95_seconds": selection["selected"]["latency"]["p95_seconds"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", type=Path, default=ROOT / "outputs/t1/compact_world_20261112"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--latency-inputs", type=Path)
    parser.add_argument("--selection-only", action="store_true")
    args = parser.parse_args()
    with threadpool_limits(limits=2), threadpool_limits(limits=1, user_api="blas"):
        run(args.source, args.output, args.latency_inputs, args.selection_only)
