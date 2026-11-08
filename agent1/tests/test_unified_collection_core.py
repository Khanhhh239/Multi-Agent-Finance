import numpy as np
import pandas as pd
import pytest

from experiments.unified_collection_v2.features import SnapshotBuilder as V6SnapshotBuilder, model_view
from experiments.t1_competing_v6.run import write_bytes_once
from experiments.unified_collection_v2.core import (
    CREDIT, OPEN, PAID, WRITEOFF, FEATURES, LabelIndex, PathState, advance,
    encode, feature_matrix, fit_vocabulary, observed_rows, origin_view,
)
from experiments.unified_collection_v2.scoring import crps, research_decision, score_paths
from experiments.unified_collection_v2.calibration import fit_calibration, transform
from experiments.unified_collection_v2.copula import conditional_uniforms
from experiments.unified_collection_v2.rollout import simulate_receipts


def ledger():
    inv = pd.DataFrame({
        "invoice_id": ["partial", "written", "credited_paid", "credit_only"],
        "firm_id": ["F"]*4, "customer_id": ["A", "B", "C", "D"],
        "issue_date": pd.to_datetime(["2023-12-01"]*4),
        "due_date": pd.to_datetime(["2024-01-31"]*4), "term_days": [61]*4,
        "amount_gross": [120., 100., 100., 100.], "currency": ["VND"]*4,
        "paid_date_true": pd.to_datetime(["2024-01-10", None, "2024-01-05", None]),
        "writeoff_date": pd.to_datetime([None, "2024-01-03", None, None]),
        "credit_note_date": pd.to_datetime([None, None, "2024-01-03", "2024-01-03"]),
        "credit_note": [0., 0., 40., 100.],
        "closure_type": ["paid", "writeoff", "paid_after_credit_note", "credit_note"],
    })
    pay = pd.DataFrame({"invoice_id": ["partial", "partial", "written", "credited_paid", "partial"],
                        "pay_date_true": pd.to_datetime(["2024-01-02", "2024-01-10", "2024-01-02", "2024-01-05", "2023-12-20"]),
                        "amount": [20., 80., 15., 60., 20.]})
    origin = model_view(V6SnapshotBuilder(inv, pay).snapshot("2024-01-01"), "2024-01-01")
    return inv, pay, origin


class ConstantModel:
    # Sorted by cash, credit and state. Writeoff shares the zero-cash atom.
    vocabulary = [
        {"cash_fraction": 0., "credit_fraction": 0., "status": OPEN},
        {"cash_fraction": 0., "credit_fraction": 0., "status": WRITEOFF},
        {"cash_fraction": .5, "credit_fraction": 0., "status": OPEN},
        {"cash_fraction": 1., "credit_fraction": 0., "status": PAID},
    ]

    def predict(self, x, *, week=None):
        return np.tile([.7, .1, .1, .1], (len(x), 1))


def test_dated_cash_credit_writeoff_and_absorbing_full_payment():
    inv, pay, origin = ledger()
    origin["world"], origin["partition"] = "source", "fit"
    x, keys, pairs, detail = observed_rows(origin, LabelIndex(inv, pay), "2024-05-01", [0, .25, .5, .75, 1])
    assert x.shape == (5, len(FEATURES))
    assert keys[:, 2].tolist() == [OPEN, WRITEOFF, PAID, CREDIT, PAID]
    np.testing.assert_allclose(pairs, [[.2, 0], [.15, 0], [.6, .4], [0, 1], [1, 0]])
    assert detail.cash_actual.sum() == 175
    assert detail.iloc[-1].opening == 80
    vocabulary = fit_vocabulary(keys, pairs)
    assert (encode(keys, vocabulary) >= 0).all()
    assert any(v["key"][0] == 5 and v["cash_fraction"] == 1 for v in vocabulary)


def test_accounting_rejects_overcollection_and_keeps_noncash_out_of_receipts():
    s = PathState.start(3)
    cash, credit, writeoff = advance(s, [0, 1, 2], [.2, 0, .6], [0, 1, .4], [WRITEOFF, CREDIT, PAID])
    np.testing.assert_allclose(cash, [.2, 0, .6])
    np.testing.assert_allclose(writeoff, [.8, 0, 0])
    np.testing.assert_allclose(cash+credit+writeoff+s.remaining, np.ones(3))
    with pytest.raises(ValueError, match="open rows"):
        advance(s, [0], [0], [0], [OPEN])
    with pytest.raises(ValueError, match="Invalid"):
        advance(PathState.start(1), [0], [.8], [.3], [PAID])
    with pytest.raises(ValueError, match="extinguish"):
        advance(PathState.start(1), [0], [.9], [0], [PAID])


def test_future_labels_never_enter_forecast_features_and_origin_context_stays_frozen():
    _, _, origin = ledger()
    polluted = origin.assign(cause=WRITEOFF, time_days=1, cash_actual_91=999999, stress_at_due=1000)
    pd.testing.assert_frame_equal(origin_view(origin), origin_view(polluted))
    state = PathState.start(len(origin))
    first = feature_matrix(origin, 1, state)
    advance(state, [0], [.5], [0], [OPEN])
    later = feature_matrix(origin, 2, state)
    np.testing.assert_equal(first[:, :len(FEATURES)-13], later[:, :len(FEATURES)-13])
    assert later[0, FEATURES.index("remaining_origin_ratio")] == .5
    assert later[0, FEATURES.index("cash_origin_ratio")] == .5
    assert later[0, FEATURES.index("week_dtd_k")] == first[0, FEATURES.index("week_dtd_k")]-7


def test_incomplete_followup_and_post_writeoff_recovery_fail_closed():
    inv, pay, origin = ledger()
    with pytest.raises(ValueError, match="follow-up"):
        observed_rows(origin, LabelIndex(inv, pay), "2024-02-01", [0, .25, .5, .75, 1])
    pay.loc[2, "pay_date_true"] = pd.Timestamp("2024-02-01")
    with pytest.raises(ValueError, match="Post-writeoff"):
        LabelIndex(inv, pay)


def test_generated_paths_match_analytic_cash_expectation_with_partial_receipts():
    _, _, origin = ledger()
    origin = origin.iloc[:2]
    result = simulate_receipts(ConstantModel(), origin, n=30000, seed=3, rho_firm=0, rho_customer=0, return_invoice_cash=True)
    # E[next cash | open amount] = .15*amount;
    # E[next remaining | open amount] = .75*amount, with writeoff absorbing.
    expected = .15*.75**np.arange(13)*origin.amount_open.sum()
    np.testing.assert_allclose(result["cash"].mean(0), expected, atol=.5)
    assert result["invoice_cash"].sum(2).max() <= 100+1e-8
    assert result["predicted_rows"] < result["active_rows"]//10
    assert max(a["max_accounting_error_vnd"] for a in result["audit"]) < 1e-8


def test_weekly_fresh_factors_preserve_conditional_uniforms_and_create_customer_dependence():
    rng = np.random.default_rng(4)
    first = conditional_uniforms(rng, 60000, np.array([0, 0, 0]), np.array([0, 0, 1]), .2, .3)
    second = conditional_uniforms(rng, 60000, np.array([0, 0, 0]), np.array([0, 0, 1]), .2, .3)
    previous_low = first[:, 0] < .2
    assert abs((second[previous_low, 0] < .3).mean()-.3) < .02
    assert np.corrcoef(first.T)[0, 1] > np.corrcoef(first.T)[0, 2]+.15
    assert abs(first.mean()-.5) < .005


def test_empty_ledger_still_returns_thirteen_weeks():
    result = simulate_receipts(ConstantModel(), pd.DataFrame(), n=5)
    assert result["cash"].shape == (5, 13)
    assert result["cash"].sum() == 0


def test_probability_calibration_discloses_unsupported_outcomes():
    p = np.tile([.8, .2], (10, 1))
    y = np.array([0, 0, 0, 0, 0, 0, 0, 0, 1, 1])
    result = fit_calibration(p, y, p, np.r_[y[:-1], -1], {"penalty": .002, "max_iterations": 10})
    assert result["selected"] == "identity" and result["select_unknown_rows"] == 1
    np.testing.assert_allclose(transform(p, result).sum(1), 1)


def test_distribution_scores_and_path_shortfall_have_distinct_targets():
    samples = np.array([[0., 2.], [2., 4.]])
    np.testing.assert_allclose(crps(samples, [1., 3.]), [.5, .5])
    paths = np.ones((10, 13))
    paths[:3, 2] = -1
    truth = np.ones(13)
    truth[2] = -1
    scores = score_paths(paths, truth, 1)
    assert scores["shortfall_p4"] == .3
    assert scores["brier_4"] == pytest.approx(.49)


def test_existing_artifacts_cannot_be_overwritten(tmp_path):
    file = tmp_path/"model.txt"
    write_bytes_once(file, b"original")
    write_bytes_once(file, b"original")
    with pytest.raises(ValueError, match="overwrite"):
        write_bytes_once(file, b"changed")

