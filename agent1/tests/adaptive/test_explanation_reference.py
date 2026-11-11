"""Background representativeness, sensitivity and hybrid support checks."""

import itertools

import numpy as np
import pandas as pd
import pytest
from agent1.adaptive.explanation_reference import (
    HybridSupport,
    reference_plan,
    stability_report,
)
from agent1.adaptive.explanations import explain_collections
from agent1.adaptive.methods import Method


def cohort(n):
    rng = np.random.default_rng(42)
    age = rng.integers(0, 365, n)
    term = rng.choice([7, 30, 60, 90], n, p=[0.1, 0.5, 0.3, 0.1])
    count = rng.integers(0, 100, n)
    delay = np.where(count, rng.uniform(-10, 60, n), 5)
    return np.column_stack(
        (rng.normal(15, 2, n), term, delay, np.full(n, 5), np.log1p(count), age)
    )


def test_small_cohort_is_a_census_and_does_not_depend_on_input_order():
    x = cohort(50)
    ids = [f"ID-{i}" for i in range(len(x))]
    selected, weights, info = reference_plan(ids, x)
    again, w2, metadata = reference_plan(ids[::-1], x[::-1])
    assert info == metadata
    np.testing.assert_array_equal(x[selected], x[::-1][again])
    np.testing.assert_array_equal(weights, w2)
    assert info["selection"] == "census" and info["count"] == len(x)
    np.testing.assert_allclose(weights.sum(0), 1)
    np.testing.assert_allclose(weights[:, 0], 1 / len(x))
    assert info["max_weighted_cdf_distance"] < 1e-12
    assert info["audit_sample_count"] == 3


def test_large_sample_preserves_stratum_mass_and_covers_the_population():
    x = cohort(2000)
    # Include a rare but distinct segment to exercise unequal sampling weights.
    x[-25:, 0] = 30
    ids = [f"I{i}" for i in range(len(x))]
    selected, weights, info = reference_plan(ids, x)
    assert info["selection"] == "weighted_stratified_sample" and info["count"] == 128
    assert len(selected) <= 512 and len(set(selected)) == len(selected)
    np.testing.assert_allclose(weights.sum(0), 1)
    assert info["max_weighted_cdf_distance"] < 0.12
    assert len(info["strata_population"]) == 16
    assert sum(info["strata_population"]) == len(x)
    assert max(weights[:, 0]) > min(weights[weights[:, 0] > 0, 0])
    assert np.any(x[selected[weights[:, 0] > 0], 0] == 30)
    permutation = np.random.default_rng(8).permutation(len(x))
    selected2, weights2, info2 = reference_plan(
        [ids[i] for i in permutation], x[permutation]
    )
    assert info2 == info
    np.testing.assert_array_equal(x[selected], x[permutation][selected2])
    np.testing.assert_array_equal(weights, weights2)


def test_stability_flags_direction_magnitude_and_leading_feature_changes():
    primary = np.array([0.1, 0.09, 0.002, 0, 0, 0])
    audits = np.array(
        [
            [0.08, 0.11, -0.002, 0, 0, 0],
            [0.1, 0.09, 0.002, 0, 0, 0],
            [0.16, 0.08, 0.001, 0, 0, 0],
        ]
    )
    factors, checks = stability_report(primary, audits, 100)
    assert factors[0]["status"] == "unstable"
    assert set(factors[0]["reasons"]) == {"top_feature_changed", "magnitude_changed"}
    assert "direction_changed" in factors[2]["reasons"]
    assert factors[2]["min_contribution_pp"] == -0.2
    assert checks["top_feature_agreement"] == pytest.approx(2 / 3)
    assert checks["scope"] == "background_sampling_sensitivity_only"
    assert factors[3]["status"] == "stable" and not factors[3]["meaningful"]
    insufficient, checks = stability_report(primary, np.empty((0, 6)), 5)
    assert not checks["checked"]
    assert all(f["status"] == "insufficient" for f in insufficient)


def test_support_detects_broken_history_constraints_and_unseen_correlated_pairs():
    x = np.zeros((40, 6))
    x[:, 0] = 10
    x[:, 1] = x[:, 5] = np.arange(40)
    check = HybridSupport(x)
    assert not check.unsupported(x).any()
    hybrid = x[[0, 0]].copy()
    hybrid[0, 5] = 39  # age/term bin pair absent from the open cohort
    hybrid[1, 2] = 12  # no customer history, yet delay differs from company
    assert check.unsupported(hybrid).all()


def test_weighted_background_replays_ensemble_shap_by_all_720_permutations():
    # Trained rule/history models still execute their real serving distributions.
    n = 620
    clock = pd.Timestamp("2026-10-31")
    age = np.arange(n) % 200
    issue = clock - pd.to_timedelta(age, unit="D")
    frame = pd.DataFrame(
        {
            "invoice_id": [f"INV-{i}" for i in range(n)],
            "customer_id": [f"C{i % 10}" for i in range(n)],
            "amount": 100000 + np.arange(n) * 1000,
            "issue_date": issue,
            "known_at": issue,
            "due_date": issue + pd.to_timedelta(7 + np.arange(n) % 60, unit="D"),
            "settled": pd.NaT,
            "settled_known_at": pd.NaT,
        }
    )
    first, second = (
        Method("due").fit(frame, clock),
        Method("customer").fit(frame, clock),
    )
    components = [(0.4, first), (0.6, second)]
    p = sum(
        w * m.distribution(frame.iloc[:1], age[:1], horizon=4)[:, :4].sum(1)[0]
        for w, m in components
    )
    row = {
        "invoice_id": "INV-0",
        "customer_id": "C0",
        "payment_probability_4w": float(p),
    }
    snapshot = explain_collections([row], frame, components, clock)
    e = row["payment_explanation"]
    assert e["reference"]["selection"] == "weighted_stratified_sample"
    primary = snapshot["sample_sets"][0]
    indices, weights = np.array(primary["positions"]), np.array(primary["weights"])
    target = np.array([np.log1p(100000), 7, 0, 0, 0, 0])
    game = np.zeros(64)
    for (weight, model), member in zip(components, snapshot["prepared_inputs"]):
        background = np.asarray(member["values"])[indices]
        for mask in range(64):
            keep = (mask & (1 << np.arange(6))) != 0
            hybrid = np.where(keep, target, background)
            prediction = model.distribution_from_features(
                hybrid[:, :5], hybrid[:, 5], horizon=4
            )[:, :4].sum(1)
            game[mask] += weight * np.dot(prediction, weights)
    expected = np.zeros(6)
    for order in itertools.permutations(range(6)):
        mask = 0
        for j in order:
            next_mask = mask | (1 << j)
            expected[j] += (game[next_mask] - game[mask]) / 720
            mask = next_mask
    actual = {f["feature"]: f["contribution"] for f in e["factors"]}
    np.testing.assert_allclose(
        [
            actual[k]
            for k in (
                "amount",
                "term_days",
                "customer_delay_days",
                "company_delay_days",
                "customer_history_count",
                "age_days",
            )
        ],
        expected,
        atol=1e-12,
    )
    assert e["baseline_probability"] == pytest.approx(game[0], abs=1e-12)
    assert e["reconstructed_probability"] == pytest.approx(p, abs=1e-12)
