"""Recompute cached validation, greedy selection and the frozen final test."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1.adaptive.compact_t1 import FEATURES, CompactT1, sha256
from experiments.t1_compact.train import risk_rows, write_json
from experiments.t1_compact.train_ensemble import (
    additions,
    cumulative_probabilities,
    evaluation_context,
    load_role,
    score_cumulative,
    stable_improvement,
    test_metrics,
)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def assert_scores(actual, expected):
    for key in ("score", "brier4", "brier13"):
        assert np.isclose(actual[key], expected[key], atol=1e-12, rtol=0), key
    assert actual["windows"].keys() == expected["windows"].keys()
    for key, value in actual["windows"].items():
        assert np.isclose(value, expected["windows"][key], atol=1e-12, rtol=0), key


def verify(output):
    output = output.resolve()
    protocol = read_json(output / "protocol.json")
    frozen = read_json(output / "frozen.json")
    result = read_json(output / "test_results.json")
    selection = read_json(output / "selection.json")
    source = Path(protocol["source"])
    checks = {
        output / "protocol.json": frozen["protocol_sha256"],
        output / "artifact/metadata.json": frozen["artifact_metadata_sha256"],
        output / "single_reference/metadata.json": frozen["reference_metadata_sha256"],
        output / "selection.json": frozen["selection_sha256"],
        output / "validation_rows.parquet": frozen["validation_rows_sha256"],
        output / "frozen.json": result["frozen_sha256"],
        output / "test_predictions.npz": result["test_predictions_sha256"],
        source / "protocol.json": protocol["source_protocol_sha256"],
        source / "data_audit.json": protocol["source_audit_sha256"],
        source / "inventory.json": protocol["source_inventory_sha256"],
    }
    checks.update(
        {
            output / "runtime_source" / file: digest
            for file, digest in protocol["source_hashes"].items()
        }
    )
    checks.update(
        {
            Path(file): digest
            for file, digest in protocol["latency_input_hashes"].items()
        }
    )
    for path, digest in checks.items():
        assert sha256(path) == digest, str(path)
    audit = read_json(source / "data_audit.json")
    train = load_role(source, "train", audit)
    validation = load_role(source, "validation", audit)
    pd.testing.assert_frame_equal(
        validation, pd.read_parquet(output / "validation_rows.parquet")
    )
    context = evaluation_context(validation)
    features = validation[list(FEATURES)].to_numpy(float)
    x, y, weights = risk_rows(train, tuple(range(len(FEATURES))))
    count = min(len(y), protocol["budget"]["risk_rows"])
    indices = np.sort(
        np.random.default_rng(protocol["seed"]).choice(len(y), count, replace=False)
    )
    x, y, weights = x[indices], y[indices], weights[indices]
    weights *= len(weights) / weights.sum()
    sample_hash = hashlib.sha256(
        indices.tobytes() + x.tobytes() + y.tobytes() + weights.tobytes()
    ).hexdigest()
    assert sample_hash == read_json(output / "training_sample.json")["sample_sha256"]
    results = read_json(output / "candidate_results.json")
    assert [entry["name"] for entry in results] == [
        entry["name"] for entry in protocol["candidates"]
    ]
    predictions = {}
    trials_checked = 0
    warnings_by_trial = {}
    for entry in results:
        if not entry["eligible"]:
            assert entry["status"] == "unavailable"
            continue
        assert (
            entry["status"] == "trained"
            and entry["trials_completed"] == entry["trials"]
        )
        trial_scores = []
        for trial in range(entry["trials"]):
            directory = output / "trials" / f"{entry['name']}_{trial}"
            record = read_json(directory / "trial.json")
            assert record["sample_sha256"] == sample_hash
            assert record["protocol_sha256"] == frozen["protocol_sha256"]
            assert sha256(directory / "validation.npz") == record["prediction_sha256"]
            assert (
                sha256(directory / "model/metadata.json")
                == record["model_metadata_sha256"]
            )
            model = CompactT1.load(directory / "model")
            with np.load(directory / "validation.npz", allow_pickle=False) as cache:
                cached = cache["distribution"]
            np.testing.assert_allclose(
                model.distribution_from_features(features), cached, atol=1e-12, rtol=0
            )
            measured = score_cumulative(cumulative_probabilities(cached), context)
            assert_scores(measured, record)
            trial_scores.append(record["score"])
            trials_checked += 1
            if record["warnings"]:
                warnings_by_trial[f"{entry['name']}_{trial}"] = record["warnings"]
        assert entry["selected_trial"] == int(np.argmin(trial_scores))
        path = output / "validation_predictions" / f"{entry['name']}.npz"
        assert sha256(path) == entry["prediction_sha256"]
        with np.load(path, allow_pickle=False) as cache:
            predictions[entry["name"]] = cumulative_probabilities(cache["distribution"])
        measured = score_cumulative(predictions[entry["name"]], context)
        assert np.isclose(measured["score"], entry["score"], atol=1e-12, rtol=0)

    timing = read_json(output / "latency_trials.json")
    steps = selection["steps"]
    ranked = sorted(
        predictions,
        key=lambda name: (score_cumulative(predictions[name], context)["score"], name),
    )
    assert [item["members"][0] for item in selection["ranked_singles"]] == ranked
    single_passes = [
        item for item in timing if len(item["members"]) == 1 and item["passed"]
    ]
    assert single_passes and steps[0]["members"] == single_passes[0]["members"]
    searched = 0
    for before in steps:
        if len(before["members"]) == 3:
            break
        searched += len(additions(before, predictions, context, protocol["stability"]))
    assert searched == selection["combination_count"]
    for position, step in enumerate(steps):
        pooled = sum(
            weight * predictions[name]
            for name, weight in zip(step["members"], step["weights"])
        )
        assert_scores(score_cumulative(pooled, context), step)
        assert step["latency"]["passed"] and step["latency"]["p95_seconds"] <= 1.0
        assert step["latency"]["max_additivity_error"] < 1e-10
        if position:
            assert set(steps[position - 1]["members"]) < set(step["members"])
            assert stable_improvement(steps[position - 1], step, protocol["stability"])
    selected = selection["selected"]
    assert (
        frozen["members"] == selected["members"]
        and frozen["weights"] == selected["weights"]
    )
    model = CompactT1.load(output / "artifact")
    assert [member.variant for member in model.members] == frozen["members"]
    np.testing.assert_array_equal(model.weights, frozen["weights"])
    pooled = sum(
        weight * predictions[name]
        for name, weight in zip(frozen["members"], frozen["weights"])
    )
    assert_scores(
        score_cumulative(
            cumulative_probabilities(model.distribution_from_features(features)),
            context,
        ),
        selected,
    )
    np.testing.assert_allclose(
        cumulative_probabilities(model.distribution_from_features(features)),
        pooled,
        atol=1e-12,
        rtol=0,
    )

    test = load_role(source, "test", audit)
    assert set(test.world).isdisjoint(set(train.world) | set(validation.world))
    assert train.origin.max() + pd.Timedelta(days=91) < validation.origin.min()
    assert validation.origin.max() + pd.Timedelta(days=91) < test.origin.min()
    measured, _worlds, distribution = test_metrics(model, test)
    assert_scores(measured, result["selected"])
    reference = CompactT1.load(output / "single_reference")
    measured_reference, _, _ = test_metrics(reference, test)
    assert_scores(measured_reference, result["best_validation_single"])
    with np.load(output / "test_predictions.npz", allow_pickle=False) as cache:
        np.testing.assert_allclose(
            distribution, cache["distribution"], atol=1e-12, rtol=0
        )
    assert result["selection_uses_test"] is False
    report = {
        "passed": True,
        "provenance_hashes_checked": len(checks),
        "candidates_checked": len(predictions),
        "fitted_trials_checked": trials_checked,
        "validation_anchors_recomputed": len(validation),
        "validation_windows": len(context["windows"]),
        "cached_combinations_recomputed": searched,
        "test_anchors_recomputed": len(test),
        "selected_members": frozen["members"],
        "selected_weights": frozen["weights"],
        "shap_p95_seconds": selected["latency"]["p95_seconds"],
        "max_shap_additivity_error": selected["latency"]["max_additivity_error"],
        "fit_warnings": warnings_by_trial,
    }
    write_json(output / "verification.json", report)
    print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    with threadpool_limits(limits=2), threadpool_limits(limits=1, user_api="blas"):
        verify(parser.parse_args().output)
