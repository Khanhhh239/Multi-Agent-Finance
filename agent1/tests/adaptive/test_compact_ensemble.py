"""Regression checks for cached selection, artifact serving and pooled SHAP."""

import json

import numpy as np
import pandas as pd
import pytest
from agent1.adaptive.compact_ensemble import CompactEnsemble, CompactHazard
from agent1.adaptive.compact_t1 import (
    FEATURES,
    CompactT1,
    Ledger,
    explain_compact,
    load_workspace_bundle,
    sha256,
)
from experiments.t1_compact import train_ensemble as training
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline


def classifier(seed):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(100, 11))
    y = (x[:, seed % 3] + 0.3 * x[:, 3] > 0).astype(int)
    return CompactHazard(LogisticRegression().fit(x, y), f"fixture_{seed}")


def opened_ledger():
    invoices = pd.DataFrame(
        [
            {
                "invoice_id": f"I{i}",
                "customer_id": f"C{i % 2}",
                "amount": 100 * (i + 1),
                "issue_date": "2024-01-01",
                "due_date": f"2024-02-{i + 1:02}",
                "known_at": "2024-01-01",
            }
            for i in range(8)
        ]
    )
    payments = pd.DataFrame(columns=["invoice_id", "date", "known_at", "amount"])
    history = Ledger(invoices, payments).snapshot("2024-01-28")
    opened = history.copy()
    opened.attrs["compact_context"] = history
    return opened


def test_weighted_pool_roundtrip_and_shap_reconstruct_served_probability(tmp_path):
    model = CompactEnsemble([classifier(1), classifier(2)], [0.35, 0.65])
    opened = opened_ledger()
    expected = 0.35 * model.members[0].distribution(opened) + 0.65 * model.members[
        1
    ].distribution(opened)
    np.testing.assert_allclose(model.distribution(opened), expected, atol=1e-12)
    metadata = {
        "available_asof": "2024-07-01",
        "data_fingerprint": "fixture",
        "source_sha256": "fixture",
    }
    model.save(tmp_path, metadata)
    restored = CompactT1.load(tmp_path)
    np.testing.assert_allclose(restored.distribution(opened), expected, atol=1e-12)
    assert (
        load_workspace_bundle(tmp_path, "2024-07-01")["model"].variant
        == "compact_ensemble"
    )
    with pytest.raises(ValueError, match="after"):
        load_workspace_bundle(tmp_path, "2024-06-30")
    probability = restored.distribution(opened)[:, :4].sum(1)
    rows = [
        {
            "invoice_id": str(row.invoice_id),
            "customer_id": str(row.customer_id),
            "payment_probability_4w": float(probability[index]),
        }
        for index, row in enumerate(opened.iloc[:2].itertuples())
    ]
    explain_compact(rows, opened, [(1.0, restored)], "2024-01-28")
    for row in rows:
        explanation = row["payment_explanation"]
        assert explanation["additivity_error"] < 1e-10
        assert explanation["coalition_count"] == 64
    for horizon in (1, 4, 13, 26, 52):
        p = restored.distribution(opened, horizon=horizon)
        assert p.shape == (len(opened), horizon + 1)
        np.testing.assert_allclose(p.sum(1), 1.0, atol=1e-12)
        if horizon > 13:
            assert (p[:, 13:horizon] == 0).all()
    member = tmp_path / "member_0/model.joblib"
    member.write_bytes(member.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        CompactT1.load(tmp_path)


@pytest.mark.parametrize(
    "weights", [[-0.1, 1.1], [0.0, 1.0], [0.3, 0.3], [np.nan, 1.0]]
)
def test_invalid_pool_weights_are_rejected(weights):
    with pytest.raises(ValueError, match="weights"):
        CompactEnsemble([classifier(1), classifier(2)], weights)


def test_stability_requires_multiple_validation_windows():
    before = {"score": 0.2, "windows": {str(i): 0.2 for i in range(4)}}
    rule = {
        "minimum_mean_gain": 0.0001,
        "minimum_window_gain": 0.00001,
        "minimum_window_fraction": 0.75,
        "maximum_window_regression": 0.001,
    }
    concentrated = {
        "score": 0.18,
        "windows": {"0": 0.1, "1": 0.205, "2": 0.205, "3": 0.21},
    }
    stable = {"score": 0.19, "windows": {"0": 0.18, "1": 0.19, "2": 0.19, "3": 0.2}}
    assert not training.stable_improvement(before, concentrated, rule)
    assert training.stable_improvement(before, stable, rule)
    for size in (2, 3):
        grid = training.weight_grid(size)
        assert all(
            len(weights) == size
            and min(weights) > 0
            and sum(weights) == pytest.approx(1.0)
            for weights in grid
        )


def test_catalog_candidates_and_prediction_cache_validation():
    specs = training.candidate_specs()
    expected = {name for name, family, _, _ in training.CATALOG if family != "ensemble"}
    assert {spec["name"] for spec in specs} == expected
    assert all(
        spec["trials"] == (1 if spec["name"] in training.BASELINES else 2)
        for spec in specs
    )
    p = np.full((3, 14), 1 / 14)
    assert training.cumulative_probabilities(p).shape == (3, 2)
    p[0, 0] = np.nan
    with pytest.raises(ValueError, match="Invalid"):
        training.cumulative_probabilities(p)


def test_cached_search_keeps_complementary_member():
    truth = np.tile(np.array([[0.0, 0.0], [1.0, 1.0]]), (4, 1))
    windows = {}
    for index in range(4):
        weights = np.zeros(8)
        weights[2 * index : 2 * index + 2] = 0.5
        windows[str(index)] = weights
    context = {"truth": truth, "weights": np.full(8, 1 / 8), "windows": windows}
    first = np.tile(np.array([[0.1, 0.1], [0.6, 0.6]]), (4, 1))
    complementary = np.tile(np.array([[0.4, 0.4], [0.9, 0.9]]), (4, 1))
    current = {
        "members": ["first"],
        "weights": [1.0],
        **training.score_cumulative(first, context),
    }
    rule = {
        "minimum_mean_gain": 0.0001,
        "minimum_window_gain": 0.00001,
        "minimum_window_fraction": 0.75,
        "maximum_window_regression": 0.001,
    }
    trials = training.additions(
        current,
        {"first": first, "complementary": complementary, "duplicate": first},
        context,
        rule,
    )
    best = next(trial for trial in trials if trial["stable"])
    assert best["members"] == ["first", "complementary"]
    assert best["weights"] == [0.5, 0.5]
    assert best["score"] < current["score"]


def test_float32_hazards_retain_normalized_distribution():
    class Float32Classifier:
        def predict_proba(self, rows):
            return np.tile(np.array([0.87, 0.13], dtype=np.float32), (len(rows), 1))

    model = CompactHazard(Float32Classifier(), "fixture")
    distribution = model.distribution_from_features(np.ones((10, len(FEATURES))))
    training.cumulative_probabilities(distribution)
    np.testing.assert_allclose(distribution.sum(1), 1.0, atol=1e-12, rtol=0)


@pytest.mark.parametrize(
    "name",
    [
        entry["name"]
        for entry in training.candidate_specs()
        if entry["eligible"] and entry["name"] not in training.BASELINES
    ],
)
def test_each_learned_candidate_fits_serializes_and_predicts(name, tmp_path):
    rng = np.random.default_rng(12)
    features = rng.normal(size=(200, len(FEATURES)))
    rows = np.column_stack((features, rng.integers(1, 14, len(features))))
    labels = (features[:, 0] + rng.normal(size=len(features)) > 0).astype(int)
    estimator = training.estimator_for(name, 0)
    weights = np.ones(len(features))
    options = (
        {f"{estimator.steps[-1][0]}__sample_weight": weights}
        if isinstance(estimator, Pipeline)
        else {"sample_weight": weights}
    )
    estimator.fit(rows, labels, **options)
    parameters = training.estimator_parameters(estimator)
    json.dumps(parameters, allow_nan=False)
    model = CompactHazard(estimator, name)
    model.save(tmp_path, {"parameters": parameters})
    restored = CompactT1.load(tmp_path)
    p = restored.distribution_from_features(features)
    training.cumulative_probabilities(p)
    np.testing.assert_allclose(
        p, model.distribution_from_features(features), atol=1e-12, rtol=0
    )


def test_test_tables_are_loaded_only_after_freeze(tmp_path, monkeypatch):
    source, output = tmp_path / "source", tmp_path / "run"
    (source / "prepared").mkdir(parents=True)
    training.write_json(source / "protocol.json", training.LANDMARK_PROTOCOL)
    audit, inventory = [], []
    for index in range(14):
        role = "train" if index < 8 else "validation" if index < 11 else "test"
        world = f"world_{index}"
        origins = (
            ["2023-01-01"]
            if role == "train"
            else training.LANDMARK_PROTOCOL[f"{role}_origins"]
        )
        frame = pd.DataFrame(np.ones((len(origins), len(FEATURES))), columns=FEATURES)
        frame["world"], frame["role"], frame["kind"], frame["firm"] = (
            world,
            role,
            "fixture",
            "F",
        )
        frame["origin"] = pd.to_datetime(origins)
        frame["invoice_id"] = [f"I{i}" for i in range(len(frame))]
        frame["paid_days"], frame["amount_open"] = 14.0, 100.0
        path = source / "prepared" / f"{world}.parquet"
        frame.to_parquet(path, index=False)
        audit.append({"world": world, "role": role, "sha256": sha256(path)})
        inventory.append({"name": world, "role": role})
    training.write_json(source / "data_audit.json", audit)
    training.write_json(source / "inventory.json", inventory)
    monkeypatch.setattr(
        training,
        "candidate_specs",
        lambda: [
            {
                "name": "due",
                "family": "rule",
                "title": "due",
                "eligible": True,
                "reason": "available",
                "trials": 1,
            }
        ],
    )
    monkeypatch.setattr(training, "latency_contexts", lambda *args: [])
    monkeypatch.setattr(
        training,
        "benchmark_ensemble",
        lambda *args: {"passed": True, "p95_seconds": 0.01},
    )
    original = training.load_role
    test_reads = []

    def guarded_load(source_path, role, entries):
        if role == "test":
            assert (output / "frozen.json").exists()
            frozen = json.loads((output / "frozen.json").read_text())
            assert (
                sha256(output / "artifact/metadata.json")
                == frozen["artifact_metadata_sha256"]
            )
            test_reads.append(role)
        return original(source_path, role, entries)

    monkeypatch.setattr(training, "load_role", guarded_load)
    training.run(source, output, selection_only=True)
    assert not test_reads
    training.run(source, output)
    assert test_reads == ["test"]
    assert (
        json.loads((output / "test_results.json").read_text())["selection_uses_test"]
        is False
    )
