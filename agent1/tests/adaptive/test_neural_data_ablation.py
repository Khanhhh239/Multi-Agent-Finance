"""Protect the experiment's cap, census and optimizer-budget contracts."""

from copy import deepcopy

import numpy as np
import pandas as pd
from agent1.adaptive.landmark_adaptation import continue_neural
from agent1.adaptive.landmark_features import FEATURES, LandmarkHazard
from experiments.t1_compact import neural_data_ablation as experiment
from experiments.t1_compact.neural_data_ablation import (
    capped_snapshots,
    sampled_risk,
    step_budget,
    train_neural,
)
from experiments.t1_compact.refit_landmark import sample_risk
from experiments.t1_compact.train import sample_indices
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def test_training_caps_preserve_original_hash_sample_without_capping_census():
    census = pd.DataFrame(
        {
            "invoice_id": [f"I{i}" for i in range(90)] * 3,
            "role": np.repeat(["fit", "validation", "audit"], 90),
            "world": "W",
            "firm": "F",
            "origin": np.repeat(
                pd.to_datetime(["2023-01-01", "2024-01-01", "2024-04-01"]), 90
            ),
        }
    )
    original = census.copy(deep=True)
    capped = capped_snapshots(census, 50)
    assert capped.groupby("role").size().to_dict() == {
        "audit": 50,
        "fit": 50,
        "validation": 50,
    }
    for _, part in census.groupby("role"):
        expected = part.iloc[
            sample_indices(part, 50, f"W:F:{part.origin.iloc[0].date()}")
        ]
        assert list(capped[capped.role == part.role.iloc[0]].invoice_id) == list(
            expected.invoice_id
        )
    assert len(capped_snapshots(census, None)) == 270
    pd.testing.assert_frame_equal(census, original)


def test_weekly_sampler_matches_original_and_full_arm_retains_every_row():
    rng = np.random.default_rng(5)
    frame = pd.DataFrame(rng.normal(size=(1200, 18)), columns=FEATURES)
    frame["world"], frame["firm"], frame["origin"] = (
        "W",
        "F",
        pd.Timestamp("2024-01-01"),
    )
    frame["invoice_id"] = [f"I{i}" for i in range(len(frame))]
    frame["paid_days"] = np.inf
    expected = sample_risk(frame, 12000)
    actual, counts = sampled_risk(frame, 12000)
    for a, b in zip(actual, expected):
        np.testing.assert_array_equal(a, b)
    assert counts["risk_rows_available"] == 15600
    assert counts["risk_rows_used"] == 12000
    full, counts = sampled_risk(frame, None)
    assert len(full[1]) == counts["risk_rows_used"] == 15600
    assert counts["unique_invoices_represented"] == 1200


def test_measured_continuation_matches_runtime_and_budget_truncates_exactly():
    rng = np.random.default_rng(7)
    x = rng.normal(size=(130, 19))
    y = (x[:, 0] > 0).astype(int)
    pipeline = make_pipeline(
        StandardScaler(),
        MLPClassifier(
            hidden_layer_sizes=(4,),
            batch_size=16,
            max_iter=100,
            tol=0.01,
            n_iter_no_change=3,
            random_state=3,
        ),
    )
    pipeline.fit(x, y)
    reference = LandmarkHazard(pipeline, "neural")
    before = deepcopy(pipeline[-1].coefs_)
    arrays = (x[:90], 1 - y[:90], np.ones(90))
    replay = (x[90:], y[90:], np.ones(40))
    config = {"learning_rate": 0.0001, "global_replay_fraction": 0.30}
    ordinary = continue_neural(reference, *arrays, replay, epochs=3)
    measured, trace = train_neural(reference, arrays, replay, 3, config)
    assert trace["optimizer_updates"] == step_budget(reference, 90, 40, 3) == 27
    exact, exact_trace = train_neural(
        reference, arrays, replay, 3, config, update_limit=27
    )
    for a, b, c in zip(
        ordinary.booster[-1].coefs_,
        measured.booster[-1].coefs_,
        exact.booster[-1].coefs_,
    ):
        np.testing.assert_array_equal(a, b)
        np.testing.assert_array_equal(a, c)
    assert exact_trace["optimizer_updates"] == 27
    limited, limited_trace = train_neural(
        reference, arrays, replay, 3, config, update_limit=4
    )
    assert limited_trace["optimizer_updates"] == 4
    assert limited_trace["complete_epochs"] == 0
    assert (
        limited_trace["local_risk_rows_exposed"]
        + limited_trace["replay_risk_rows_exposed"]
        == 64
    )
    assert np.isfinite(limited.booster.predict_proba(x)).all()
    for a, b in zip(before, reference.booster[-1].coefs_):
        np.testing.assert_array_equal(a, b)


def test_a0_scores_full_validation_and_audit_but_caps_final_refit(monkeypatch):
    frame = pd.DataFrame(np.ones((270, 18)), columns=FEATURES)
    frame["role"] = np.repeat(["fit", "validation", "audit"], 90)
    frame["origin"] = np.repeat(
        pd.to_datetime(["2023-01-01", "2024-01-01", "2024-04-01"]), 90
    )
    frame["label_end"] = frame.origin + pd.Timedelta(days=91)
    frame["invoice_id"] = [f"I{i}" for i in range(270)]
    frame["world"], frame["firm"], frame["paid_days"] = "W", "F", np.inf
    original = frame.copy(deep=True)
    scored_lengths, trained_rows = [], []

    def fake_score(model, rows):
        scored_lengths.append(len(rows))
        return {"score": 0.1, "integrated_brier13": 0.1}, np.tile(
            [0.0] * 13 + [1.0], (len(rows), 1)
        )

    def fake_train(reference, arrays, replay, epochs, config, update_limit=None):
        trained_rows.append(len(arrays[1]))
        return object(), {"optimizer_updates": 1}

    monkeypatch.setattr(experiment, "measured", fake_score)
    monkeypatch.setattr(experiment, "train_neural", fake_train)
    config = {
        "minimum_fit_rows": 1,
        "minimum_validation_rows": 1,
        "minimum_audit_rows": 1,
        "neural_epochs": [5, 20],
        "local_weight_grid": [0.0, 1.0],
        "audit_minimum_gain": 0.0001,
    }
    _, record = experiment.arm_models(object(), None, None, frame, "A0", config)
    assert set(scored_lengths) == {90}
    assert trained_rows == [650, 650, 1950]
    assert record["final_data"]["snapshots"] == 150
    assert record["validation_snapshots"] == record["audit_snapshots"] == 90
    pd.testing.assert_frame_equal(frame, original)
