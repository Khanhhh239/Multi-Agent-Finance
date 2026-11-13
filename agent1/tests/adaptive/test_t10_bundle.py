"""T10 evidence is about a frozen result; sensitivities replay its full cash law."""

from copy import deepcopy
from io import BytesIO

from fastapi.testclient import TestClient
import numpy as np
from openpyxl import load_workbook
import pytest

from agent1.adaptive.cash_adapter import PartialModel
from agent1.adaptive.methods import forecast
from agent1.adaptive.t10_explanations import freeze_replay, replay_scenario
from agent1_service.api import create_app
from agent1_service.workspace.forecast_export import workbook_bytes

CUTOFF = "2026-02-10"


class Timing:
    def distribution(self, frame, ages, horizon=13):
        p = np.zeros((len(frame), horizon+1))
        p[:, 0], p[:, 2], p[:, -1] = .2, .3, .5
        return p


@pytest.fixture
def inputs():
    data = dict(invoices=[dict(invoice_id=str(i), customer_id=c, amount=100_000_000,
                issue_date="2026-01-01", due_date="2026-02-01", known_at="2026-01-01")
                for i, c in enumerate(("A", "B", "A"))],
                payments=[dict(payment_id="P", invoice_id="0", amount=40_000_000,
                    payment_date="2026-02-01", known_at="2026-02-01")],
                outflows=[dict(expense_id="RENT", amount=120_000_000, date="2026-02-12",
                               known_at=CUTOFF, category="rent")])
    partial = PartialModel(np.full(6, .6), tuple(np.array([.25, .5]) for _ in range(6)),
                           tuple(np.array([.4, .6]) for _ in range(6)), "2026-01-31",
                           dict(cells=[dict(weeks=40, effective_weeks=30., partial_weeks=20)
                                       for _ in range(6)], prior_sha256="GLOBAL", prior_strength=30))
    model = Timing()
    bundle = dict(model=model, anchor=model, weight=1., partial=partial, asof="2026-01-31",
                  t1_version="test-t1", adapter_version=partial.version)
    kwargs = dict(cutoff=CUTOFF, balance=10_000_000, horizon_weeks=4, cash_floor=5_000_000,
                  shap_limit=0, simulation_seed=123, simulation_paths=2000)
    return data, bundle, kwargs


def frozen(inputs, **overrides):
    data, bundle, kwargs = inputs
    kwargs = dict(kwargs, **overrides)
    plan = forecast(data, bundle=bundle, **kwargs)
    plan["id"] = "FORECAST"
    snapshot = freeze_replay(plan, data, bundle, kwargs)
    return plan, snapshot


def test_exact_partial_engine_facts_and_support_are_saved_for_every_invoice(inputs):
    plan, _ = frozen(inputs)
    identity = plan["t10"]["identity"]
    assert identity["t1_version"] == "test-t1"
    assert identity["partial_version"] == inputs[1]["partial"].digest
    assert identity["t6"] == plan["t6_version"]
    assert plan["t10"]["feature_cash_attribution"]["status"] == "not_computed"
    assert plan["t10"]["partial_profile"]["evidence"]["cells"][0]["weeks"] == 40
    assert plan["t10"]["partial_profile"]["mean_ratios"] == pytest.approx([.4]*6)
    invoices = plan["cash_decomposition"]["invoices"]
    assert len(invoices) == 3
    row = next(r for r in invoices if r["invoice_id"] == "0")
    assert row["outstanding"] == 60_000_000
    first = row["receipt_explanation"]["weeks"][0]
    assert first["expected_from_settlement"] == 12_000_000
    assert first["expected_from_partial"] == 11_520_000
    assert first["expected_receipt"] == 23_520_000
    assert first["expected_remaining_debt"] == 36_480_000
    profile = plan["t10"]["partial_profile"]
    for row in invoices:
        remaining = row["outstanding"]
        for w, expected in zip(row["receipt_explanation"]["weeks"], row["expected_by_week"]):
            assert w["expected_opening_debt"] == pytest.approx(remaining)
            full = sum(s["expected_opening_debt"] for s in w["partial_states"]) * w["settlement_hazard"]
            pieces = sum(s["expected_opening_debt"] * (1-w["settlement_hazard"]) *
                         profile["probability"][s["cell"]] * profile["mean_ratios"][s["cell"]]
                         for s in w["partial_states"])
            assert full == pytest.approx(w["expected_from_settlement"])
            assert pieces == pytest.approx(w["expected_from_partial"])
            assert full + pieces == pytest.approx(expected)
            remaining -= expected
            assert remaining == pytest.approx(w["expected_remaining_debt"])
        assert remaining == pytest.approx(row["expected_after_horizon"])
    wb = load_workbook(BytesIO(workbook_bytes(plan, "TEST")))
    assert wb["Bằng chứng partial theo tuần"].max_row == 13
    assert wb["Profile partial và hỗ trợ"].max_row == 13
    assert "So sánh thời điểm" not in wb.sheetnames  # Superseded expectation-only generator removed.


def test_partial_list_atoms_remain_auditable_and_nonserializable_t1_is_rejected(inputs):
    data, bundle, kwargs = inputs
    bundle["partial"] = PartialModel([.5]*6, tuple([.5] for _ in range(6)),
                                     tuple([1.] for _ in range(6)), "2026-01-31", {"cells": []})
    plan, snapshot = frozen(inputs)
    assert plan["t10"]["partial_support_status"] == "support_not_recorded"
    assert plan["t10"]["partial_profile"]["ratios"] == [[.5]]*6
    assert replay_scenario(plan, snapshot)["delta_any_shortfall_probability"] == 0
    assert load_workbook(BytesIO(workbook_bytes(plan, "TEST")))["Profile partial và hỗ trợ"].max_row == 7
    class LocalTiming(Timing):
        pass
    bundle["model"] = LocalTiming()
    with pytest.raises(ValueError, match="artifact"):
        forecast(data, bundle=bundle, **kwargs)


@pytest.mark.parametrize("shared", [False, True])
def test_noop_is_exact_with_existing_delay_and_shared_customer_paths(inputs, shared):
    plan, snapshot = frozen(inputs, delay_days=7, delay_customer="A", shared_customer_risk=shared)
    compared = replay_scenario(plan, snapshot)
    assert compared["delta_any_shortfall_probability"] == 0
    assert compared["delta_probability_mc_standard_error"] == 0
    for w in compared["weeks"]:
        assert w["baseline"] == w["scenario"]
        assert w["delta"]["expected_balance"] == 0
        assert set(w["delta"]["balance_quantiles"].values()) == {0}


def test_customer_delay_replays_full_distribution_with_paired_randomness(inputs):
    plan, snapshot = frozen(inputs)
    compared = replay_scenario(plan, snapshot, customer_id="A", customer_delay_weeks=2)
    assert compared["random_numbers"]["paired"]
    assert compared["t10"]["partial_profile"] == plan["t10"]["partial_profile"]
    assert compared["t10"]["identity"] == plan["t10"]["identity"]
    assert compared["delta_any_shortfall_probability"] >= 0
    for w in compared["weeks"]:
        assert w["delta"]["expected_balance"] <= 1e-6
        assert all(v <= 1e-6 for v in w["delta"]["balance_quantiles"].values())
        assert w["delta"]["below_floor_probability"] >= 0
    before = {r["invoice_id"]: r for r in plan["cash_decomposition"]["invoices"]}
    after = {r["invoice_id"]: r for r in compared["scenario_cash_decomposition"]["invoices"]}
    assert before["1"] == after["1"]  # Other customer has identical expected adapter evidence.
    # Independently compare path by path: no partitioning/re-drawing other invoices.
    data, bundle, kwargs = inputs
    baseline = np.asarray(forecast(data, bundle=bundle, return_paths=True, **kwargs)["balance_paths"])
    shifted = np.asarray(forecast(data, bundle=bundle, return_paths=True,
                                 receipt_shifts={"A": 2}, **kwargs)["balance_paths"])
    assert (shifted <= baseline + 1e-6).all()
    assert compared["delta_any_shortfall_probability"] == pytest.approx(
        (shifted < kwargs["cash_floor"]).any(1).mean() - (baseline < kwargs["cash_floor"]).any(1).mean())


def test_expense_deferral_is_not_removed_money_and_has_full_quantiles(inputs):
    plan, snapshot = frozen(inputs)
    compared = replay_scenario(plan, snapshot, expense_id="RENT", expense_delay_weeks=1)
    assert compared["weeks"][0]["delta"]["expected_balance"] == 120_000_000
    assert compared["weeks"][0]["delta"]["balance_quantiles"] == pytest.approx(
        {"0.1": 120_000_000, "0.5": 120_000_000, "0.9": 120_000_000})
    assert compared["weeks"][-1]["delta"]["expected_balance"] == 0
    assert compared["delta_any_shortfall_probability"] <= 0
    pushed = replay_scenario(plan, snapshot, expense_id="RENT", expense_delay_weeks=5)
    assert pushed["outflows_pushed_beyond_horizon"][0]["amount"] == 120_000_000
    assert pushed["weeks"][-1]["delta"]["expected_balance"] == pytest.approx(120_000_000)


def test_calibrated_saved_band_is_not_mistaken_for_a_simulated_quantile(inputs):
    data, bundle, kwargs = inputs
    plan = forecast(data, bundle=bundle, **kwargs)
    plan.update(id="F", band_status="calibrated_out_of_sample")
    for row in plan["weeks"]:
        row["low"] -= 999_000_000
        row["high"] += 999_000_000
    snapshot = freeze_replay(plan, data, bundle, kwargs)
    result = replay_scenario(plan, snapshot)
    assert result["band_status"] == "raw_simulation"
    assert result["saved_band_status"] == "calibrated_out_of_sample"
    assert result["weeks"][0]["baseline"]["low"] == plan["weeks"][0]["balance_quantiles"]["0.1"]
    assert result["weeks"][0]["baseline"]["low"] != plan["weeks"][0]["low"]


def test_stale_engine_or_tampered_facts_fail_closed(inputs, monkeypatch):
    from agent1.adaptive import t10_explanations as t10
    plan, snapshot = frozen(inputs)
    for altered in ("data", "bundle", "kwargs"):
        corrupt = deepcopy(snapshot)
        corrupt[altered] = "CHANGED"
        with pytest.raises(ValueError, match="thay đổi"):
            replay_scenario(plan, corrupt)
    corrupt = deepcopy(plan)
    corrupt["cash_decomposition"]["invoices"][0]["expected_by_week"][0] += 1
    with pytest.raises(ValueError, match="thay đổi"):
        replay_scenario(corrupt, snapshot)
    monkeypatch.setattr(t10, "engine_identity", lambda: dict(version="NEW-ENGINE"))
    with pytest.raises(ValueError, match="engine/runtime"):
        replay_scenario(plan, snapshot)
    with pytest.raises(ValueError, match="cũ"):
        replay_scenario(dict(id="OLD"), None)


@pytest.mark.parametrize("scenario", [dict(customer_id="MISSING"), dict(expense_id="NO"),
                                      dict(expense_delay_weeks=2), dict(customer_delay_weeks=-1)])
def test_invalid_scenarios_do_not_silently_change_scope(inputs, scenario):
    plan, snapshot = frozen(inputs)
    with pytest.raises(ValueError):
        replay_scenario(plan, snapshot, **scenario)


def test_api_reads_saved_artifact_after_active_data_and_model_change(inputs, tmp_path, monkeypatch):
    from agent1_service.workspace import t1_lifecycle
    data, bundle, kwargs = inputs
    monkeypatch.setattr(t1_lifecycle, "load_active", lambda *a, **k: (bundle, None))
    app = create_app(state_dir=tmp_path/"state", key_dir=tmp_path/"keys", token="t10", firm_id="F")
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer t10"
        store = app.state.store
        store.put_many("F", {"company_datasets": [dict(id="DATA", data=data)],
                             "company_dataset_active": [dict(id="active", version="DATA")]})
        response = client.post("/v1/predict", json=dict(cutoff=CUTOFF, opening_balance=kwargs["balance"],
            cash_floor=kwargs["cash_floor"], horizon_weeks=4, payments_complete=True,
            shap_limit=0, simulation_seed=123, simulation_paths=2000))
        assert response.status_code == 200, response.text
        plan = response.json()
        path = "/v1/forecasts/" + plan["id"]
        assert store.one("F", "company_forecast_replays", plan["id"])
        assert store.one("F", "company_forecast_engines", plan["t6_version"]["source_sha256"])
        store.put_many("F", {"company_dataset_active": [dict(id="active", version="MISSING")],
                             "company_model_active": [dict(id="active", version="MISSING")]})
        monkeypatch.setattr(t1_lifecycle, "load_active", lambda *a, **k: pytest.fail("Must not load today's T1"))
        evidence = client.get(path+"/explanations")
        assert evidence.status_code == 200, evidence.text
        assert evidence.json()["t10"] == plan["t10"]
        assert "bundle" not in client.get(path+"/explanations").json()  # No internal pickle in response.
        compared = client.post(path+"/scenarios", json=dict(customer_id="A", customer_delay_weeks=1))
        assert compared.status_code == 200, compared.text
        result = compared.json()
        assert client.get(path+"/scenarios/"+result["id"]).json() == result
        assert client.get(path+"/scenarios").json()[0]["id"] == result["id"]
        assert client.get(path).json()["t10"] == plan["t10"]
        assert client.post(path+"/scenarios", json=dict(simulation_seed=999)).status_code == 422
        store.put("F", "company_predictions", [dict(id="OLD", weeks=[])])
        assert client.get("/v1/forecasts/OLD/explanations").status_code == 409
        assert client.post("/v1/forecasts/OLD/scenarios", json={}).status_code == 409


def test_actual_global_bundle_grouped_shap_and_replay_keep_the_same_targets(inputs):
    from agent1.adaptive.t1_catalog import GlobalCatalog
    data, _, kwargs = inputs
    bundle = GlobalCatalog().default_bundle(CUTOFF)
    plan = forecast(data, bundle=bundle, **dict(kwargs, shap_limit=1))
    explained = plan["collections"][0]["payment_explanation"]
    assert explained["target"] == "payment_probability_4w"
    assert explained["status"] == "available"
    assert explained["additivity_error"] < 1e-10
    assert explained["probability"] == plan["collections"][0]["payment_probability_4w"]
    plan["id"] = "GLOBAL"
    snapshot = freeze_replay(plan, data, bundle, kwargs)
    replayed = replay_scenario(plan, snapshot)
    assert replayed["delta_any_shortfall_probability"] == 0


def test_operating_and_new_credit_residuals_keep_the_same_random_draws(inputs, monkeypatch):
    from agent1.adaptive import operating, new_credit
    data, bundle, kwargs = inputs
    bundle["operating"] = dict(accounts=["Q"], name="fixture", model=None,
        residuals=np.tile(np.array([[[0., 0.]], [[100_000., -20_000.]]]), (1, 13, 1)),
        credit=dict(kind="fixture", residuals=np.tile([[0.], [30_000.]], (1, 13))))
    monkeypatch.setattr(operating, "available_history", lambda *a: (np.zeros((60, 2)), 0))
    monkeypatch.setattr(operating, "predict_candidate", lambda *a: np.tile([1_000_000, 600_000], (13, 1)))
    monkeypatch.setattr(new_credit, "build", lambda *a: object())
    monkeypatch.setattr(new_credit, "point", lambda *a: np.full(13, 200_000.))
    plan, snapshot = frozen(inputs, include_operating=True, delay_days=7, delay_customer="B")
    noop = replay_scenario(plan, snapshot)
    assert all(w["baseline"] == w["scenario"] for w in noop["weeks"])
    changed = replay_scenario(plan, snapshot, customer_id="A", customer_delay_weeks=1)
    assert changed["delta_any_shortfall_probability"] >= 0
    assert all(w["delta"]["expected_balance"] <= 1e-6 for w in changed["weeks"])
