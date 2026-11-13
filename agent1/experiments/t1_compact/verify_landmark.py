"""Independently recompute the eighteen-feature cash/survival comparison."""

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
from agent1.adaptive.compact_t1 import CompactT1, sha256
from agent1.adaptive.landmark_features import FEATURES
from experiments.t1_compact.train import risk_rows, write_json
from experiments.t1_compact.train_ensemble import stable_improvement
from experiments.t1_compact.train_landmark import (
    context_for,
    evaluate,
    pool_predictions,
    score_prediction,
    summarize_prediction,
)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_score(actual, expected):
    for key in (
        "score",
        "brier4",
        "brier13",
        "integrated_brier13",
        "cash_bias13_fraction",
    ):
        assert np.isclose(actual[key], expected[key], atol=1e-12, rtol=0), key
    for key in ("cash_weekly_mae_vnd", "cash_cumulative_mae_vnd"):
        assert np.isclose(actual[key], expected[key], atol=0.0001, rtol=0), key
    assert actual["windows"].keys() == expected["windows"].keys()
    for key, value in actual["windows"].items():
        assert np.isclose(value, expected["windows"][key], atol=1e-12, rtol=0), key


def prepared_role(output, role):
    frames = []
    for entry in read(output / f"{role}_data_audit.json"):
        path = output / "prepared" / f"{entry['world']}.parquet"
        assert sha256(path) == entry["sha256"]
        assert sha256(output / "protocol.json") == entry["protocol_sha256"]
        frame = pd.read_parquet(path)
        assert set(frame.role) == {role}
        assert np.isfinite(frame[list(FEATURES)]).all().all()
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def verify(output):
    output = output.resolve()
    protocol, frozen = read(output / "protocol.json"), read(output / "frozen.json")
    result, selection = (
        read(output / "test_results.json"),
        read(output / "selection.json"),
    )
    assert len(protocol["features"]) == 18 and protocol["features"] == list(FEATURES)
    assert sha256(output / "frozen.json") == result["frozen_sha256"]
    assert sha256(output / "protocol.json") == frozen["protocol_sha256"]
    assert sha256(output / "selection.json") == frozen["selection_sha256"]
    assert (
        sha256(output / "artifact/metadata.json") == frozen["artifact_metadata_sha256"]
    )
    assert (
        sha256(output / "single_reference/metadata.json")
        == frozen["single_metadata_sha256"]
    )
    assert (
        sha256(output / "survival_reference/metadata.json")
        == frozen["survival_metadata_sha256"]
    )
    for name, digest in protocol["source_hashes"].items():
        assert sha256(output / "runtime_source" / name) == digest, name
    train, validation = (
        prepared_role(output, "train"),
        prepared_role(output, "validation"),
    )
    pd.testing.assert_frame_equal(
        validation, pd.read_parquet(output / "validation_rows.parquet")
    )
    assert (
        sha256(output / "validation_rows.parquet") == frozen["validation_rows_sha256"]
    )
    context = context_for(validation)
    x, y, weights = risk_rows(train, tuple(range(len(FEATURES))), FEATURES)
    indices = np.sort(
        np.random.default_rng(protocol["seed"]).choice(
            len(y), min(len(y), 100000), replace=False
        )
    )
    x, y, weights = x[indices], y[indices], weights[indices]
    weights *= len(weights) / weights.sum()
    sample_hash = hashlib.sha256(
        indices.tobytes() + x.tobytes() + y.tobytes() + weights.tobytes()
    ).hexdigest()
    assert sample_hash == read(output / "training_sample.json")["sample_sha256"]
    candidates = read(output / "candidate_results.json")
    assert [item["name"] for item in candidates] == [
        item["name"] for item in protocol["candidates"]
    ]
    predictions, warnings_by_trial = {}, {}
    count = 0
    for entry in candidates:
        if not entry["eligible"]:
            assert entry["status"] == "unavailable"
            continue
        scores = []
        for trial in range(entry["trials"]):
            directory = output / "trials" / f"{entry['name']}_{trial}"
            record = read(directory / "trial.json")
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
                model.distribution_from_features(
                    validation[list(FEATURES)].to_numpy(float)
                ),
                cached,
                atol=1e-12,
                rtol=0,
            )
            measured = score_prediction(summarize_prediction(cached, context), context)
            check_score(measured, record)
            scores.append(measured["score"])
            if record["warnings"]:
                warnings_by_trial[f"{entry['name']}_{trial}"] = record["warnings"]
            count += 1
        assert entry["selected_trial"] == int(np.argmin(scores))
        path = output / "validation_predictions" / f"{entry['name']}.npz"
        assert sha256(path) == entry["prediction_sha256"]
        with np.load(path, allow_pickle=False) as cache:
            predictions[entry["name"]] = summarize_prediction(
                cache["distribution"], context
            )
    assert "survival" in predictions
    searches = read(output / "ensemble_search.json")
    assert len(searches) == selection["combination_count"]
    for trial in searches:
        check_score(
            score_prediction(
                pool_predictions(predictions, trial["members"], trial["weights"]),
                context,
            ),
            trial,
        )
    for position, step in enumerate(selection["steps"]):
        check_score(
            score_prediction(
                pool_predictions(predictions, step["members"], step["weights"]), context
            ),
            step,
        )
        assert step["latency"]["passed"] and step["latency"]["p95_seconds"] <= 1.0
        assert step["latency"]["max_additivity_error"] < 1e-10
        assert all(
            item["count"] == item["population"] and item["audit_sample_count"] == 3
            for item in step["latency"]["references"].values()
        )
        if position:
            before = selection["steps"][position - 1]
            assert stable_improvement(before, step, protocol["stability"])
            assert (
                step["integrated_brier13"]
                <= before["integrated_brier13"] * 1.02 + 0.0001
            )
    test = prepared_role(output, "test")
    assert set(test.world).isdisjoint(set(train.world) | set(validation.world))
    assert set(train.world).isdisjoint(set(validation.world))
    assert train.origin.max() + pd.Timedelta(days=91) < validation.origin.min()
    assert validation.origin.max() + pd.Timedelta(days=91) < test.origin.min()
    context = context_for(test)
    previous = Path(protocol["previous"])
    assert (
        sha256(previous / "artifact/metadata.json")
        == frozen["previous_artifact_metadata_sha256"]
    )
    for name, directory in (
        ("selected", output / "artifact"),
        ("best_validation_single", output / "single_reference"),
        ("survival", output / "survival_reference"),
        ("previous_10_feature_ensemble", previous / "artifact"),
    ):
        model = CompactT1.load(directory)
        measured, distribution = evaluate(model, test, context)
        check_score(measured, result[name])
        with np.load(output / f"test_{name}.npz", allow_pickle=False) as cache:
            np.testing.assert_allclose(
                distribution, cache["distribution"], atol=1e-12, rtol=0
            )
    survival = CompactT1.load(output / "survival_reference")
    assert survival.variant == "survival" and survival.active == (2,)
    model = CompactT1.load(output / "artifact")
    assert [member.variant for member in model.members] == frozen["members"]
    np.testing.assert_array_equal(model.weights, frozen["weights"])
    assert result["selection_uses_test"] is False
    report = {
        "passed": True,
        "features_checked": len(FEATURES),
        "candidates_checked": len(predictions),
        "trials_checked": count,
        "validation_anchors": len(validation),
        "combinations_recomputed": len(searches),
        "test_anchors": len(test),
        "cash_clipped_validation_rows": int(validation.cash_label_clipped.sum()),
        "cash_clipped_test_rows": int(test.cash_label_clipped.sum()),
        "validation_partial_override_rows": int(validation.partial_override.sum()),
        "test_partial_override_rows": int(test.partial_override.sum()),
        "selected_members": frozen["members"],
        "selected_weights": frozen["weights"],
        "survival_reference_checked": True,
        "fit_warnings": warnings_by_trial,
    }
    write_json(output / "verification.json", report)
    print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    with threadpool_limits(limits=2), threadpool_limits(limits=1, user_api="blas"):
        verify(parser.parse_args().output)
