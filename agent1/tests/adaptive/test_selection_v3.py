import numpy as np
import pandas as pd
import pytest
from agent1.adaptive.collections import budget_metrics
from experiments.t1_compact.historical_workspace import DistributionEnsemble
from agent1.adaptive.operating import fit_candidate, predict_candidate
from agent1.adaptive.risk import train_risk, predict_risk


def test_budget_metric_uses_value_not_only_count():
    bad = budget_metrics([3, 2, 1], [1, 1, 100], 1)
    good = budget_metrics([1, 2, 3], [1, 1, 100], 1)
    assert good["normalized_value"] == 1
    assert bad["normalized_value"] == 0.01
    assert good["precision"] == bad["precision"] == 1


@pytest.mark.parametrize("name", ["gaussian_gru", "gaussian_gru_wide", "gaussian_lstm"])
def test_recurrent_candidates_train_and_predict(name):
    pytest.importorskip("torch")
    y = np.column_stack([100 + 10 * np.sin(np.arange(80)), 50 + np.arange(80) % 5])
    model = fit_candidate(name, y)
    p = predict_candidate(name, model, y)
    assert p.shape == (13, 2)
    assert np.isfinite(p).all() and (p >= 0).all()


def test_cash_pool_preserves_mean():
    y = np.ones((104, 2)) * 10
    model = fit_candidate("pool:seasonal,gbm", y)
    assert np.allclose(predict_candidate("pool:seasonal,gbm", model, y), 10)


def test_writeoff_requires_mature_labels_and_ignores_future_actions():
    data = {"invoices": [], "payments": [], "actions": []}
    for i, day in enumerate(pd.date_range("2014-01-01", "2025-01-01", freq="10D")):
        data["invoices"].append(
            dict(
                invoice_id=str(i),
                customer_id=str(i % 20),
                amount=100 + i % 7,
                issue_date=str(day.date()),
                due_date=str((day + pd.Timedelta(days=30)).date()),
                known_at=str(day.date()),
            )
        )
        if i % 3 == 0:
            when = str((day + pd.Timedelta(days=200)).date())
            data["actions"].append(
                dict(invoice_id=str(i), kind="write_off", date=when, known_at=when)
            )
    result = train_risk(data, "2026-01-01")
    assert result["status"] == "evaluated"
    assert result["audit_n"] >= 20
    modified = {
        **data,
        "actions": data["actions"]
        + [
            dict(
                invoice_id="1",
                kind="write_off",
                date="2014-07-01",
                known_at="2027-01-01",
            )
        ],
    }
    again = train_risk(modified, "2026-01-01")
    assert again["validation"] == result["validation"]
    assert again["audit_brier"] == result["audit_brier"]
    assert train_risk(data, "2014-06-01")["status"] == "insufficient_labels"


def test_demo_training_is_explicit_and_company_isolated(monkeypatch):
    from agent1_service.workspace.api import demo_training_allowed

    monkeypatch.delenv("AGENT1_DEMO_TRAINING", raising=False)
    assert not demo_training_allowed("DEMO_DAIPHAT")
    monkeypatch.setenv("AGENT1_DEMO_TRAINING", "1")
    assert demo_training_allowed("DEMO_DAIPHAT")
    assert not demo_training_allowed("SME")
