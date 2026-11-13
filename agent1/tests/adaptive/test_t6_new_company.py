"""Frozen new-company evaluation boundaries and proper joint path scores."""

import json
from copy import deepcopy

import numpy as np
import pytest

from agent1.adaptive.cash_adapter import PartialModel
from agent1.adaptive.data import fingerprint
from experiments.t6_backtest.new_company import (
    freeze_predictions, lock_protocol, path_scores, score_frozen,
)


class FixedTiming:
    def distribution(self, frame, ages, horizon=13):
        p = np.zeros((len(frame), horizon+1)); p[:, 0] = .5; p[:, -1] = .5
        return p


class Catalog:
    digest = "frozen-global"

    def default_bundle(self, cutoff):
        model = FixedTiming()
        partial = PartialModel(np.full(6, .4), tuple(np.array([.25]) for _ in range(6)),
                               tuple(np.ones(1) for _ in range(6)), "2024-01-01", {})
        return dict(model=model, anchor=model, weight=1., partial=partial,
                    asof="2024-01-01", t1_version="frozen")


def fixture_data():
    return dict(invoices=[dict(invoice_id="OLD", customer_id="C", amount=100,
        issue_date="2024-12-01", due_date="2025-01-01", known_at="2024-12-01"),
        dict(invoice_id="FUTURE", customer_id="C", amount=20, issue_date="2025-01-03",
             due_date="2025-01-03", known_at="2025-01-03")],
        payments=[dict(payment_id="P", invoice_id="OLD", amount=40, bank_id="B",
            payment_date="2025-01-04", known_at="2025-01-04")],
        bank=[dict(bank_id="B", account="Q", amount=40, date="2025-01-04",
                   known_at="2025-01-04", direction="in", component="other")],
        statements=[dict(statement_id="PAST", account="Q", start_date="2024-12-01",
            end_date="2025-01-01", known_at="2025-01-01", opening_balance=10, closing_balance=10),
            dict(statement_id="FUTURE", account="Q", start_date="2025-01-02",
            end_date="2025-04-02", known_at="2025-04-02", opening_balance=10, closing_balance=50)],
        outflows=[])


def company(data):
    return dict(firm_id="../new-firm", cutoff="2025-01-01", truth_asof="2025-04-02",
                accounts=["Q"], opening_balance=10, synthetic=True,
                dataset_sha256=fingerprint(data), heldout_from_global_and_policy_selection=True)


def test_joint_score_separates_same_weekly_marginals_and_measures_any_shortfall():
    persistent = np.array([[0., 100.], [100., 0.]])
    shared = np.array([[0., 0.], [100., 100.]])
    actual = [0., 100.]
    a, b = path_scores(persistent, actual, 50), path_scores(shared, actual, 50)
    assert a["crps_balance_vnd"] == b["crps_balance_vnd"] == 25
    assert a["energy_path_vnd"] < b["energy_path_vnd"]
    assert a["any_shortfall_probability"] == 1 and b["any_shortfall_probability"] == .5
    assert a["brier_any_shortfall"] == 0 and b["brier_any_shortfall"] == .25
    assert path_scores(np.tile(actual, (5, 1)), actual, 50)["energy_path_vnd"] == 0
    shifted = path_scores(persistent+1e13, np.array(actual)+1e13, 1e13+50)
    assert shifted == a


def test_protocol_lock_history_only_adaptation_then_frozen_future_scoring(tmp_path):
    data, catalog = fixture_data(), Catalog()
    protocol_path = tmp_path/"protocol.json"
    spec = company(data)
    locked = lock_protocol(protocol_path, [spec], catalog, simulation_paths=100)
    assert lock_protocol(protocol_path, [spec], catalog, simulation_paths=100) == locked
    with pytest.raises(ValueError, match="Locked protocol"):
        lock_protocol(protocol_path, [spec], catalog, simulation_paths=200)
    with pytest.raises(FileNotFoundError):
        score_frozen(protocol_path, spec["firm_id"], data)
    calls = []
    def adapt(history, cutoff, **kwargs):
        calls.append(history)
        assert [r["invoice_id"] for r in history["invoices"]] == ["OLD"]
        assert not history["payments"] and not history["bank"]
        assert [s["statement_id"] for s in history["statements"]] == ["PAST"]
        assert kwargs["policy"].interval_days == 28 and kwargs["policy"].lookback_days == 730
        return dict(kwargs["incumbent"], promotion_status="kept_incumbent")
    before = deepcopy(data)
    folder = freeze_predictions(protocol_path, spec["firm_id"], data, catalog, trainer=adapt)
    assert folder.parent == tmp_path and data == before
    freeze_predictions(protocol_path, spec["firm_id"], data, catalog, trainer=adapt)
    assert len(calls) == 1
    result = score_frozen(protocol_path, spec["firm_id"], data)
    assert result["models"]["global"] == result["models"]["adapted"]
    assert result["models"]["global"]["weeks"] == 13
    for metric in ("mae_balance_vnd", "energy_path_vnd", "crps_balance_vnd", "brier_any_shortfall"):
        assert np.isfinite(result["models"]["global"][metric])
    plan = json.loads((folder/"adapted.json").read_text(encoding="utf-8"))
    plan["balance_paths"][0][0] += 1
    (folder/"adapted.json").write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ValueError, match="forecast changed"):
        score_frozen(protocol_path, spec["firm_id"], data)


def test_holdout_declaration_overlap_and_changed_data_are_rejected(tmp_path):
    data, catalog = fixture_data(), Catalog()
    case = company(data)
    with pytest.raises(ValueError, match="holdout"):
        lock_protocol(tmp_path/"bad.json", [dict(case, heldout_from_global_and_policy_selection=False)], catalog)
    with pytest.raises(ValueError, match="Development"):
        lock_protocol(tmp_path/"bad.json", [case], catalog, development_firms=[case["firm_id"]])
    path = tmp_path/"protocol.json"
    lock_protocol(path, [case], catalog)
    data["payments"][0]["amount"] = 99
    with pytest.raises(ValueError, match="data changed"):
        freeze_predictions(path, case["firm_id"], data, catalog)
