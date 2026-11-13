"""T6 accounting and distribution acceptance, independently of model quality."""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from agent1.adaptive.cash_adapter import (
    PartialModel, expected_cash, iter_cash_paths, sample_cash,
)
from agent1.adaptive.methods import forecast


def partial(q=.4):
    return PartialModel(np.full(6, q), tuple(np.array([.2, .6]) for _ in range(6)),
                        tuple(np.array([.25, .75]) for _ in range(6)), "2024-01-01", {})


def test_each_invoice_path_conserves_residual_and_matches_t1_including_partial_tail():
    frame = pd.DataFrame(dict(invoice_id=["A", "B"], customer_id=["C", "D"],
                              age_days=[20, 150], term_days=[30, 30], received_fraction=[0, .3]))
    model = partial()
    model.probability[1::2] = .8
    p = np.random.default_rng(42).dirichlet(np.ones(14), size=2)
    amounts, count = [100., 70.], 80000
    for i, paths in enumerate(iter_cash_paths(p, frame, model, amounts, np.random.default_rng(7), count)):
        cash, debt = paths.receipts, paths.remaining
        assert (cash >= 0).all() and (debt >= 0).all()
        np.testing.assert_allclose(cash.cumsum(1)+debt, amounts[i], atol=1e-10)
        assert (np.diff(debt, axis=1) <= 0).all()
        np.testing.assert_allclose(np.bincount(paths.settlement_week, minlength=15)[1:]/count,
                                   p[i], atol=.004)
        for week in range(1, 14):
            settled = paths.settlement_week == week
            assert (debt[settled, week-1:] == 0).all()
            assert (cash[settled, week:] == 0).all()
        tail = paths.settlement_week == 14
        assert ((cash[tail].sum(1) > 0) & (debt[tail, -1] > 0)).any()
        analytic = expected_cash(p[i:i+1], frame.iloc[i:i+1], model)[0, :13]*amounts[i]
        np.testing.assert_allclose(cash.mean(0), analytic, atol=.3)


@pytest.mark.parametrize("amounts", ([-1], [np.nan], [1, 2]))
def test_path_adapter_rejects_invalid_open_balances(amounts):
    frame = pd.DataFrame(dict(invoice_id=["A"], customer_id=["C"], age_days=[0],
                              term_days=[30], received_fraction=[0]))
    p = np.zeros((1, 14)); p[0, -1] = 1
    with pytest.raises(ValueError, match="Dư nợ"):
        sample_cash(p, frame, partial(), amounts, np.random.default_rng(7), 100)
    with pytest.raises(ValueError, match="partial"):
        sample_cash(p, frame, None, [1], np.random.default_rng(7), 100)


class Timing:
    def distribution(self, frame, ages, horizon=13):
        p = np.zeros((len(frame), horizon+1))
        p[:, 0], p[:, -1] = .2, .8
        return p


def test_mean_median_quantiles_keep_all_debt_and_ignore_explanation_budget_and_risk(monkeypatch):
    from agent1.adaptive import explanations, risk

    monkeypatch.setattr(explanations, "explain_collections", lambda *args, **kw: None)
    data = dict(invoices=[dict(invoice_id=str(i), customer_id=str(i), amount=100,
        issue_date="2024-12-01", due_date="2025-01-01", known_at="2024-12-01") for i in range(45)],
        payments=[dict(payment_id="P", invoice_id="0", amount=40,
                       payment_date="2024-12-30", known_at="2024-12-30")], outflows=[])
    original = deepcopy(data["invoices"][0])
    credit = dict(original, amount=80, known_at="2024-12-31")
    data["invoices"][0] = credit
    data["record_history"] = {"invoices": [original, *deepcopy(data["invoices"][1:]), credit]}
    data["actions"] = [dict(event_id="contact", invoice_id="1", kind="contact",
                            date="2025-01-01", known_at="2025-01-01")]
    bundle = dict(model=Timing(), anchor=Timing(), weight=1., partial=partial(0), asof="2024-01-01")
    monkeypatch.setattr(risk, "predict_risk", lambda _, opened: [0.99]*len(opened))
    first = forecast(data, "2025-01-01", 10, bundle, shap_limit=0, return_paths=True)
    monkeypatch.setattr(risk, "predict_risk", lambda _, opened: [0.0]*len(opened))
    second = forecast(data, "2025-01-01", 10, bundle, shap_limit=30, return_paths=True)
    assert first["outstanding"] == 4440 and first["open_invoices"] == 45
    assert len(first["cash_decomposition"]["invoices"]) == 45
    assert first["collection_ranking"]["eligible_count"] == 44
    assert len(first["collections"]) == 30  # Display limit does not remove AR cash.
    assert first["weeks"] == second["weeks"]
    assert first["balance_paths"] == second["balance_paths"]
    assert first["weeks"][0]["expected_balance"] == pytest.approx(10+.2*4440)
    x = np.asarray(first["balance_paths"])
    for i, week in enumerate(first["weeks"]):
        assert week["expected_balance"] == week["balance"]
        assert week["median_balance"] == np.median(x[:, i])
        np.testing.assert_allclose(list(week["balance_quantiles"].values()), np.quantile(x[:, i], [.1, .5, .9]))
    assert first["any_below_floor_probability"] == (x < 0).any(1).mean()

    # A deliberately skewed single invoice demonstrates E[B] != median(B).
    one = deepcopy(data); one["invoices"] = one["invoices"][1:2]; one["payments"] = []
    one.pop("record_history")
    plan = forecast(one, "2025-01-01", 0, bundle, shap_limit=0)
    assert plan["weeks"][0]["expected_balance"] == 20
    assert plan["weeks"][0]["median_balance"] == 0


def test_calibration_uses_new_protocol_oos_only_and_preserves_mean_and_raw_quantiles(monkeypatch):
    from agent1.adaptive import cash_history

    def plan(cutoff, created=None, protocol="settlement-partial-paths-v2"):
        return dict(cutoff=cutoff, created_at=created or cutoff, accounts=["Q"],
                    model_version="BUNDLE", band_protocol=protocol, assumptions=[],
                    weeks=[dict(balance=10., expected_balance=10., median_balance=5.,
                                low=0., high=20., balance_quantiles={"0.1": 0., "0.5": 5., "0.9": 20.})])
    previous = [plan(str(day.date())) for day in pd.date_range("2024-01-01", periods=12, freq="14D")]
    monkeypatch.setattr(cash_history, "evaluate_plan", lambda *a: [dict(balance_available=True, actual_balance=30.)])
    current = plan("2025-01-01")
    cash_history.calibrate_bands(current, previous, {})
    week = current["weeks"][0]
    assert current["calibration_origins"] == 12 and current["band_status"] == "calibrated_out_of_sample"
    assert (week["raw_low"], week["raw_high"], week["low"], week["high"]) == (0, 20, -10, 30)
    assert week["balance"] == week["expected_balance"] == 10 and week["median_balance"] == 5
    assert week["balance_quantiles"] == {"0.1": 0., "0.5": 5., "0.9": 20.}
    for incompatible in ([dict(p, band_protocol="cash-v3-t5-ledger") for p in previous],
                         [dict(p, created_at="2026-01-01") for p in previous]):
        current = plan("2025-01-01")
        cash_history.calibrate_bands(current, incompatible, {})
        assert current["calibration_origins"] == 0 and current["weeks"][0]["low"] == 0
