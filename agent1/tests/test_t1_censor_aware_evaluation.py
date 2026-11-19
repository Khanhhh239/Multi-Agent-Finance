"""Protect T1 evaluation from treating right-censored rows as day-120 events."""

import numpy as np
import pytest

from analysis.evaluate_t1_censor_aware import probability_metrics, quantile_metrics


def test_binary_horizon_uses_full_followup_nonpayment_as_zero():
    remaining = np.array([12., 50., np.inf, 130.])
    prediction = np.array([.8, .7, .2, .3])
    four, _ = probability_metrics(remaining, prediction, 28)
    thirteen, _ = probability_metrics(remaining, prediction, 91)
    assert four["n_paid_by_horizon"] == 1
    assert thirteen["n_paid_by_horizon"] == 2
    assert four["brier"] == pytest.approx(np.mean((prediction - [1, 0, 0, 0]) ** 2))
    assert thirteen["brier"] == pytest.approx(np.mean((prediction - [1, 1, 0, 0]) ** 2))


def test_capped_q90_does_not_count_censored_as_covered():
    remaining = np.array([12., np.inf, 130.])
    quantiles = np.array([[5., 10., 30.], [20., 60., 120.], [30., 70., 100.]])
    result = quantile_metrics(remaining, quantiles, 120)
    assert result["n_resolved_by_horizon"] == 1
    assert result["q90"]["n_finite"] == 2
    assert result["q90"]["observed_cdf_at_finite_quantile"] == .5
    assert result["finite_q10_q90_interval"]["observed_coverage"] == .5
    assert result["capped_q90_paid_by_horizon_rate"] == 0
    assert result["numeric_interval_hit_by_horizon"] == pytest.approx(1 / 3)
    assert result["legacy_clipped_label_coverage"] == pytest.approx(2 / 3)
    assert result["legacy_false_hits_from_censoring"] == 1
    assert result["q50"]["resolved_only_pinball"] == pytest.approx(1.)


def test_quantile_rejects_prediction_beyond_followup():
    with pytest.raises(ValueError, match="exceeds"):
        quantile_metrics(np.array([np.inf]), np.array([[10., 90., 121.]]), 120)
