"""Behavioral cash, censoring and paired-bundle regression tests."""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from agent1.adaptive.cash_adapter import (
    LABEL_CONTRACT, PartialModel, bundle_version, expected_cash, fit_partial, sample_cash,
)
from agent1.adaptive.landmark_features import FEATURES
from agent1.adaptive.t1_data import landmarks, risk_rows, score_audit_snapshot, snapshot_for_audit


def partial(q=1.0, ratio=0.5):
    return PartialModel(np.full(6, q), tuple(np.array([ratio]) for _ in range(6)),
                        tuple(np.ones(1) for _ in range(6)), "2024-01-01",
                        {"label_contract": LABEL_CONTRACT})


def frame(n=1):
    f = pd.DataFrame(np.zeros((n, len(FEATURES))), columns=FEATURES)
    f["invoice_id"] = [str(i) for i in range(n)]
    f["customer_id"] = ["C"] * n
    f["origin"] = pd.Timestamp("2025-01-01")
    f["label_end"] = pd.Timestamp("2025-01-08")
    f["followup_days"] = 7
    f["paid_days"] = np.inf
    for w in range(1, 14):
        f[f"cash_{w}"] = 0.0
    return f


def ledger(*, coverage=True):
    data = {"invoices": [dict(invoice_id="0", customer_id="C", issue_date="2024-12-01",
                              due_date="2024-12-31", known_at="2024-12-01", amount=100)],
            "payments": [dict(payment_id="a", invoice_id="0", payment_date="2025-01-03",
                              known_at="2025-01-04", amount=40),
                         dict(payment_id="b", invoice_id="0", payment_date="2025-01-12",
                              known_at="2025-01-13", amount=60)]}
    if coverage:
        data["payment_coverage"] = [dict(complete=True, start_date="2024-12-01",
                                          end_date="2025-04-02", known_at="2025-04-02")]
    return data


def test_future_partial_starts_without_past_receipt_and_settles_residual():
    f = frame()
    p = np.zeros((1, 14))
    p[0, 2] = 1
    cash = expected_cash(p, f, partial())
    np.testing.assert_allclose(cash[0, :4], [0.5, 0.25, 0.25, 0])
    draws = sample_cash(p, f, partial(), [100], np.random.default_rng(9), 100)
    np.testing.assert_allclose(draws[:, :3], np.tile([50, 25, 25], (100, 1)))
    np.testing.assert_allclose(draws.sum(1), 100)


def test_exact_mean_matches_repeated_receipt_monte_carlo_with_state_changes():
    f = frame()
    model = partial(0.2)
    model.probability[1::2] = 0.8
    p = np.full((1, 14), 1 / 14)
    analytic = expected_cash(p, f, model)[0]
    samples = sample_cash(p, f, model, [1], np.random.default_rng(4), 100000)
    np.testing.assert_allclose(samples.mean(0), analytic[:13], atol=0.002)
    assert (samples.sum(1) <= 1 + 1e-12).all()
    assert np.any((samples > 0).sum(1) > 1)
    assert np.any(samples.sum(1) == 0)
    assert analytic.sum() == pytest.approx(1)


def test_zero_partial_preserves_any_valid_t1_and_invalid_probabilities_fail():
    f = frame(2)
    p = np.random.default_rng(8).dirichlet(np.ones(14), size=2)
    np.testing.assert_allclose(expected_cash(p, f, partial(0)), p)
    for bad in (p * 2, p[:, :13], np.full((2, 14), np.nan)):
        with pytest.raises(ValueError):
            expected_cash(bad, f, partial())


def test_local_partial_incidence_and_ratio_shrink_to_global_then_gain_weight():
    one, many = frame(), frame(200)
    one["cash_1"] = many["cash_1"] = 0.25
    prior = partial(0.1, 0.6)
    small = fit_partial(one, "2025-01-08", prior=prior)
    large = fit_partial(many, "2025-01-08", prior=prior)
    assert 0.1 < small.probability[0] < large.probability[0] < 1
    assert 0.25 < large.means[0] < small.means[0] < 0.6
    incomplete = one.copy()
    incomplete["followup_days"] = 6
    censored = fit_partial(incomplete, "2025-01-08", prior=prior)
    np.testing.assert_allclose(censored.probability, prior.probability)
    settled = one.copy()
    settled["paid_days"] = 3
    ignored = fit_partial(settled, "2025-01-08", prior=prior)
    np.testing.assert_allclose(ignored.probability, prior.probability)
    with pytest.raises(ValueError, match="Nhãn partial"):
        fit_partial(one, "2025-01-07", prior=prior)


def test_absent_or_gapped_payment_scope_is_censored_and_late_scope_cannot_leak():
    data = ledger(coverage=False)
    unobserved = landmarks(data, "2025-01-01", "2025-04-02")
    assert unobserved.followup_days.tolist() == [0]
    with pytest.raises(ValueError, match="tuần risk"):
        risk_rows(unobserved)
    data["payment_coverage"] = [dict(complete=True, start_date="2025-01-02",
                                    end_date="2025-01-09", known_at="2025-01-09")]
    covered = landmarks(data, "2025-01-01", "2025-04-02")
    assert covered.followup_days.tolist() == [8]
    (x, y, _), _ = risk_rows(covered)
    assert x[:, -1].tolist() == [1]
    assert y.tolist() == [0]
    assert covered.cash_1.tolist() == [0.4]
    # Confirmation received after the label cutoff cannot turn absence into 0.
    data["payment_coverage"][0]["known_at"] = "2025-04-03"
    assert landmarks(data, "2025-01-01", "2025-04-02").followup_days.tolist() == [0]


def test_noncash_closure_never_creates_cash_full_settlement():
    data = ledger()
    original = deepcopy(data["invoices"][0])
    credit = dict(original, amount=40, known_at="2025-01-05")
    data["invoices"] = [credit]
    data["record_history"] = {"invoices": [original, credit]}
    data["payments"] = data["payments"][:1]
    assert landmarks(data, "2025-01-01", "2025-04-02").empty
    data = ledger()
    data["actions"] = [dict(event_id="w", invoice_id="0", kind="write_off",
                             date="2025-01-06", known_at="2025-01-06")]
    assert landmarks(data, "2025-01-01", "2025-04-02").empty


class NeverSettles:
    def distribution_from_features(self, x):
        p = np.zeros((len(x), 14))
        p[:, -1] = 1
        return p

    def distribution(self, frame, ages, horizon=13):
        return self.distribution_from_features(frame)


def test_serving_validation_and_paths_share_the_cash_law_for_never_paid_debt():
    from agent1.adaptive.methods import forecast

    data = ledger()
    data["payments"] = []
    model, adapter = NeverSettles(), partial()
    target = landmarks(data, "2025-01-01", "2025-04-02")
    expected = expected_cash(model.distribution_from_features(target), target, adapter)
    bundle = dict(model=model, anchor=model, weight=1.0, partial=adapter, asof="2024-01-01")
    plan = forecast(data, "2025-01-01", 0, bundle, shap_limit=0)
    np.testing.assert_allclose([w["cash_in"] for w in plan["weeks"]], expected[0, :13] * 100)
    for week in plan["weeks"]:
        assert week["low"] == pytest.approx(week["balance"])
        assert week["high"] == pytest.approx(week["balance"])
    delayed = forecast(data, "2025-01-01", 0, bundle, delay_days=7, shap_limit=0)
    assert delayed["weeks"][0]["cash_in"] == 0
    np.testing.assert_allclose([w["cash_in"] for w in delayed["weeks"]][1:],
                               [w["cash_in"] for w in plan["weeks"]][:-1])


def test_paired_audit_freezes_each_bundles_own_adapter():
    data = ledger()
    model = NeverSettles()
    baseline = {"model": model, "partial": partial(0)}
    challenger = {"model": model, "partial": partial(1, 0.4)}
    assert bundle_version(model, baseline["partial"]) != bundle_version(model, challenger["partial"])
    snapshot = snapshot_for_audit(data, "2025-01-01", baseline, challenger,
                                  "old", "new", "2025-01-01T12:00:00")
    assert snapshot["baseline_distribution"] == snapshot["challenger_distribution"]
    assert snapshot["baseline_cash"] != snapshot["challenger_cash"]
    result = score_audit_snapshot(snapshot, data, "2025-04-02", minimum_rows=1)
    assert result["status"] == "scored"
    assert result["baseline"]["integrated_brier13"] == result["challenger"]["integrated_brier13"]
    assert result["baseline"]["score"] != result["challenger"]["score"]
    # Mutating the source law after freezing cannot rewrite paired cash.
    challenger["partial"].probability[:] = 0
    assert score_audit_snapshot(snapshot, data, "2025-04-02", minimum_rows=1) == result
