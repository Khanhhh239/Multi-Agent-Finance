"""T6 operating cash law, account scope and calibration compatibility."""
from copy import deepcopy
from datetime import datetime
import pickle
import sys

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import numpy as np
import pandas as pd
import pytest
from threadpoolctl import threadpool_limits

from agent1.adaptive.cash_history import calibrate_bands
from agent1.adaptive.data import validate_dataset
from agent1.adaptive.methods import forecast
from agent1.adaptive.operating import operating_identity, select_operating
from agent1.adaptive.t1_catalog import GlobalCatalog
from agent1.adaptive.t10_explanations import freeze_replay, replay_scenario
from agent1_service.api import create_app
from agent1_service.store import Store
from agent1_service.workspace import t1_lifecycle


@pytest.fixture(scope="module")
def case():
    data = dict(invoices=[dict(invoice_id="I", customer_id="C", amount=100,
        issue_date="2020-01-01", due_date="2020-02-01", known_at="2020-01-01")],
        payments=[], outflows=[], bank=[], statements=[])
    balance = 0
    for i, end in enumerate(pd.date_range("2022-01-04", periods=200, freq="7D")):
        day, amount = str(end.date()), 1_000_000 + i * 100_000
        data["bank"].append(dict(bank_id=f"B{i}", account="Q", date=day,
            known_at=day, amount=amount, direction="in", component="cash_sale"))
        data["statements"].append(dict(statement_id=f"S{i}", account="Q",
            start_date=str((end-pd.Timedelta(days=6)).date()), end_date=day,
            known_at=day, opening_balance=balance, closing_balance=balance+amount))
        balance += amount
    cutoff = str(end.date())
    validate_dataset(data)
    with threadpool_limits(1):
        operating = select_operating(data, cutoff, include_new_credit=False)
    bundle = GlobalCatalog().default_bundle(cutoff)
    bundle["operating"] = operating
    return data, cutoff, bundle


def run(data, cutoff, bundle, **kwargs):
    opening_balance = kwargs.pop("opening_balance", 0)
    with threadpool_limits(1):
        return forecast(data, cutoff, opening_balance, bundle, include_operating=True,
                        shap_limit=0, **kwargs)


def assert_path_mean(plan):
    paths = np.asarray(plan["balance_paths"])
    expected = np.array([w["expected_balance"] for w in plan["weeks"]])
    se = paths.std(0, ddof=1)/np.sqrt(len(paths))
    np.testing.assert_array_less(np.abs(paths.mean(0)-expected), 6*se+1)


def test_real_operating_fit_uses_the_same_expectation_as_its_paths(case):
    data, cutoff, bundle = case
    assert bundle["operating"]["name"] == "gbm"
    assert bundle["operating"]["residuals"][:, 0, 0].mean() > 500_000
    plan = run(data, cutoff, bundle, return_paths=True, simulation_paths=10000)
    assert_path_mean(plan)
    assert plan["cash_decomposition"]["totals"]["closing_balance"] == pytest.approx(
        plan["weeks"][-1]["expected_balance"])


def test_clipped_sales_credit_and_known_variable_costs_share_one_cash_law(case, monkeypatch):
    from agent1.adaptive import new_credit, operating

    data, cutoff, bundle = case
    data = deepcopy(data)
    data["payments"] = [dict(payment_id="P", invoice_id="I", amount=100,
                             payment_date="2020-01-02", known_at="2020-01-02")]
    data["outflows"] = [dict(expense_id="V", amount=30, category="variable_cost",
        date=str((pd.Timestamp(cutoff)+pd.Timedelta(days=1)).date()), known_at=cutoff)]
    selected = dict(bundle, operating=dict(accounts=["Q"], name="fixture", model=None,
        version="fixture-law", fitted_through=cutoff, ready_on=cutoff,
        residuals=np.tile(np.array([[[-30., -30.]], [[30., 20.]]]), (1, 13, 1)),
        credit=dict(kind="fixture", residuals=np.tile([[-30.], [30.]], (1, 13)))))
    monkeypatch.setattr(operating, "predict_candidate", lambda *a: np.tile([10., 20.], (13, 1)))
    monkeypatch.setattr(new_credit, "build", lambda *a: object())
    monkeypatch.setattr(new_credit, "point", lambda *a: np.full(13, 10.))
    plan = run(data, cutoff, selected, expense_multiplier=1.5,
               return_paths=True, simulation_paths=10000, horizon_weeks=1)
    week = plan["cash_decomposition"]["weeks"][0]
    assert week["cash_sale_in"] == 20
    assert week["new_credit_in"] == 20
    assert week["scheduled_out"] == 45
    assert week["variable_cost_topup"] == 7.5
    assert plan["weeks"][0]["expected_balance"] == -12.5
    assert_path_mean(plan)


@pytest.mark.parametrize("scope", [[], ["Q", "R"]])
def test_operating_scope_change_is_rejected(case, scope):
    data, cutoff, bundle = case
    changed = dict(data, bank_scope=dict(accounts=scope)) if scope else dict(
        data, bank=[], statements=[])
    with pytest.raises(ValueError, match="Phạm vi tài khoản"):
        run(changed, cutoff, bundle)
    # An unused learner does not block an AR-only forecast after a scope change.
    assert forecast(changed, cutoff, 0, bundle, shap_limit=0)["operating_included"] is False


def test_api_rejects_old_account_scope_and_accepts_a_refitted_learner(case, tmp_path):
    data, cutoff, bundle = case
    expanded = deepcopy(data)
    expanded["bank"].extend(dict(r, bank_id="R-"+r["bank_id"], account="R", amount=2*r["amount"])
                           for r in data["bank"])
    expanded["statements"].extend(dict(r, statement_id="R-"+r["statement_id"], account="R",
        opening_balance=2*r["opening_balance"], closing_balance=2*r["closing_balance"])
        for r in data["statements"])
    validate_dataset(expanded)
    with threadpool_limits(1):
        updated = select_operating(expanded, cutoff, include_new_credit=False)
    assert updated["version"] != bundle["operating"]["version"]
    app = create_app(state_dir=tmp_path/"state", key_dir=tmp_path/"keys", token="review", firm_id="A")
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer review"
        store = app.state.store
        store.put_many("A", {
            "company_datasets": [dict(id="expanded", data=expanded)],
            "company_dataset_active": [dict(id="active", version="expanded")],
            "company_weights": [dict(id="scope", **t1_lifecycle.encode(bundle))],
            "company_models": [t1_lifecycle.metadata(bundle, "scope", cutoff+"T12:00:00Z")],
            "company_model_active": [dict(id="active", version="scope")],
        })
        body = dict(cutoff=cutoff, opening_balance=0, payments_complete=True,
                    include_operating=True, shap_limit=0, horizon_weeks=1)
        response = client.post("/v1/predict", json=body)
        assert response.status_code == 422 and "Phạm vi tài khoản" in response.text
        assert not store.ids("A", "company_predictions")
        store.put("A", "company_weights", [dict(id="scope", **t1_lifecycle.encode(dict(bundle, operating=updated)))])
        response = client.post("/v1/predict", json=body)
        assert response.status_code == 200, response.text
        plan = response.json()
        assert plan["accounts"] == plan["operating_identity"]["accounts"] == ["Q", "R"]
        assert plan["operating_identity"]["version"] == updated["version"]
        assert plan["cash_decomposition"]["weeks"][0]["cash_sale_in"] > 60_000_000


def test_calibration_excludes_other_or_unversioned_operating_fits(case):
    data, cutoff, bundle = case
    old_bundle = dict(bundle, operating=dict(name="seasonal", model=None, accounts=["Q"],
        version="historical-seasonal", fitted_through="2024-01-01", ready_on="2024-01-01",
        credit=None, residuals=np.zeros((3, 13, 2))))

    def plan(day, selected):
        opening = sum(r["amount"] for r in data["bank"] if r["date"] <= day)
        result = run(data, day, selected, horizon_weeks=1, opening_balance=opening)
        result.update(created_at=day+"T12:00:00Z", accounts=["Q"],
                      model_version=selected["t1_version"], scenario={}, confirmed_weeks=[])
        return result

    past = [plan(str((pd.Timestamp(cutoff)-pd.Timedelta(weeks=2*i)).date()), old_bundle)
            for i in range(1, 13)]
    current = plan(cutoff, bundle)
    assert past[0]["t10"]["identity"] != current["t10"]["identity"]
    raw = deepcopy(current["weeks"])
    calibrate_bands(current, past, data)
    assert current["calibration_origins"] == 0 and current["weeks"] == raw
    compatible = plan(cutoff, old_bundle)
    calibrate_bands(compatible, past, data)
    assert compatible["calibration_origins"] == 12
    assert compatible["band_status"] == "calibrated_out_of_sample"
    # A refit of the same algorithm also has a different residual/model law.
    refitted = [dict(p, operating_identity=dict(p["operating_identity"], version="other-seasonal-fit"))
                for p in past]
    current = plan(cutoff, old_bundle)
    calibrate_bands(current, refitted, data)
    assert current["calibration_origins"] == 0
    # Legacy plans and fits remain readable but cannot establish compatibility.
    for missing in (None, dict(operating_identity(old_bundle["operating"]), version=None)):
        legacy = [dict(p, operating_identity=missing) for p in past]
        current = plan(cutoff, old_bundle)
        calibrate_bands(current, legacy, data)
        assert current["calibration_origins"] == 0
    legacy_current = plan(cutoff, old_bundle)
    legacy_current["operating_identity"]["version"] = None
    calibrate_bands(legacy_current, past, data)
    assert legacy_current["calibration_origins"] == 0


def test_operating_version_survives_serialization_and_paired_replay(case):
    data, cutoff, bundle = case
    restored = pickle.loads(pickle.dumps(bundle))
    assert operating_identity(restored["operating"]) == operating_identity(bundle["operating"])
    kwargs = dict(cutoff=cutoff, balance=0, include_operating=True, horizon_weeks=1,
                  shap_limit=0, simulation_paths=1000, simulation_seed=7)
    with threadpool_limits(1):
        plan = forecast(data, bundle=bundle, **kwargs)
        plan["id"] = "OPERATING"
        snapshot = freeze_replay(plan, data, bundle, kwargs)
        compared = replay_scenario(plan, snapshot)
    assert plan["t10"]["identity"]["operating"] == plan["operating_identity"]
    assert compared["weeks"][0]["baseline"] == compared["weeks"][0]["scenario"]
    assert compared["delta_any_shortfall_probability"] == 0


@pytest.fixture(scope="module")
def cost_case():
    data = dict(invoices=[dict(invoice_id="I", customer_id="C", amount=1,
        issue_date="2020-01-01", due_date="2020-02-01", known_at="2020-01-01")],
        payments=[dict(payment_id="P", invoice_id="I", amount=1,
            payment_date="2020-01-02", known_at="2020-01-02")],
        bank=[], statements=[], outflows=[])
    for i, end in enumerate(pd.date_range(end="2026-01-31", periods=156, freq="7D")):
        day = str(end.date())
        data["bank"].append(dict(bank_id=f"B{i}", account="Q", date=day,
            known_at=day, amount=100, direction="out", component="variable_cost"))
        data["statements"].append(dict(statement_id=f"S{i}", account="Q",
            start_date=str((end-pd.Timedelta(days=6)).date()), end_date=day,
            known_at=day, opening_balance=-100*i, closing_balance=-100*(i+1)))
    cutoff = str(end.date())
    data["outflows"] = [dict(expense_id="V", date="2026-02-01", known_at=cutoff,
                             amount=100, category="variable_cost")]
    validate_dataset(data)
    with threadpool_limits(1):
        operating = select_operating(data, cutoff, include_new_credit=False)
    assert operating["name"] == "seasonal" and not operating["residuals"].any()
    bundle = dict(GlobalCatalog().default_bundle(cutoff), operating=operating)
    return data, cutoff, bundle


@pytest.mark.parametrize("week,delay,horizon,multiplier", [
    (1, 1, 2, 1.), (1, 3, 2, 1.), (13, 1, 14, 1.5),
])
def test_variable_cost_deferral_moves_each_path_without_refilling_the_old_week(
        cost_case, week, delay, horizon, multiplier):
    data, cutoff, bundle = cost_case
    data = deepcopy(data)
    data["outflows"][0]["date"] = str((pd.Timestamp(cutoff)+pd.Timedelta(weeks=week)).date())
    kwargs = dict(horizon_weeks=horizon, expense_multiplier=multiplier, return_paths=True)
    base = run(data, cutoff, bundle, **kwargs)
    changed = run(data, cutoff, bundle, expense_shifts={"V": delay}, **kwargs)
    delta = np.zeros(horizon)
    delta[week-1] = 100*multiplier
    if week+delay <= horizon:
        delta[week+delay-1] -= 100*multiplier
    np.testing.assert_allclose(
        np.asarray(changed["balance_paths"])-base["balance_paths"],
        np.tile(delta.cumsum(), (1000, 1)), atol=1e-9)
    assert [w["variable_cost_topup"] for w in changed["cash_decomposition"]["weeks"]] == [
        w["variable_cost_topup"] for w in base["cash_decomposition"]["weeks"]]
    assert_path_mean(changed)
    pushed = changed["t5"]["outflows_pushed_beyond_horizon"]
    assert bool(pushed) == (week+delay > horizon)
    if pushed:
        assert pushed[0]["expense_id"] == "V" and pushed[0]["amount"] == 100*multiplier


def seed_bundle(store, data, cutoff, bundle):
    store.put_many("A", {
        "company_datasets": [dict(id="D", data=data)],
        "company_dataset_active": [dict(id="active", version="D")],
        "company_weights": [dict(id="M", **t1_lifecycle.encode(bundle))],
        "company_models": [t1_lifecycle.metadata(bundle, "M", cutoff+"T12:00:00Z")],
        "company_model_active": [dict(id="active", version="M")],
    })


def test_api_variable_deferral_preserves_saved_baseline_and_moves_money(cost_case, tmp_path):
    data, cutoff, bundle = cost_case
    app = create_app(state_dir=tmp_path/"state", key_dir=tmp_path/"keys", token="review", firm_id="A")
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer review"
        seed_bundle(app.state.store, data, cutoff, bundle)
        response = client.post("/v1/predict", json=dict(cutoff=cutoff, opening_balance=1000,
            include_operating=True, payments_complete=True, shap_limit=0, horizon_weeks=2))
        assert response.status_code == 200, response.text
        plan = response.json()
        path = "/v1/forecasts/"+plan["id"]
        response = client.post(path+"/scenarios", json=dict(expense_id="V", expense_delay_weeks=1))
        assert response.status_code == 200, response.text
        moved = response.json()
        assert [w["delta"]["expected_balance"] for w in moved["weeks"]] == [100, 0]
        assert moved["weeks"][0]["delta"]["balance_quantiles"] == {"0.1": 100, "0.5": 100, "0.9": 100}
        response = client.post(path+"/scenarios", json=dict(expense_id="V", expense_delay_weeks=3))
        assert response.status_code == 200, response.text
        assert [w["delta"]["expected_balance"] for w in response.json()["weeks"]] == [100, 100]
        assert response.json()["outflows_pushed_beyond_horizon"][0]["expense_id"] == "V"
        assert client.get(path).json() == plan


@pytest.mark.parametrize("has_history", [True, False])
def test_scheduler_refreshes_operating_scope_or_clears_an_ineligible_fit(
        cost_case, tmp_path, monkeypatch, capsys, has_history):
    from agent1_service.jobs import t1_update as job

    data, cutoff, bundle = cost_case
    data = deepcopy(data)
    old_day = str((pd.Timestamp(cutoff)-pd.Timedelta(days=28)).date())
    with threadpool_limits(1):
        old_fit = select_operating(data, old_day, include_new_credit=False)
    old_bundle = dict(bundle, operating=old_fit)
    if has_history:
        data["bank"].extend(dict(r, bank_id="R-"+r["bank_id"], account="R") for r in list(data["bank"]))
        data["statements"].extend(dict(r, statement_id="R-"+r["statement_id"], account="R")
                                  for r in list(data["statements"]))
    else:
        data.update(bank=[], statements=[])
    validate_dataset(data)
    state, keys = tmp_path/"state", tmp_path/"keys"
    keys.mkdir()
    key = Fernet.generate_key()
    (keys/"encryption.key").write_bytes(key)
    store = Store(state/"agent1.db", key)
    try:
        seed_bundle(store, data, old_day, old_bundle)
    finally:
        store.connection.close()
    monkeypatch.setenv("AGENT1_KEY_DIR", str(keys))
    monkeypatch.delenv("AGENT1_REPORT_DIR", raising=False)
    monkeypatch.delenv("AGENT1_REPORT_PASSWORD_FILE", raising=False)
    monkeypatch.setattr(t1_lifecycle, "now", lambda: datetime.fromisoformat(cutoff+"T12:00:00+07:00"))
    monkeypatch.setattr(sys, "argv", ["t1_update", "--firm", "A", "--state", str(state),
        "--cutoff", cutoff, "--catalog", str(GlobalCatalog().path), "--payments-complete"])
    with threadpool_limits(1):
        job.main()
    capsys.readouterr()
    store = Store(state/"agent1.db", key)
    try:
        current, metadata = t1_lifecycle.load_active(store, "A", cutoff)
        assert current["t1_version"] == bundle["t1_version"]
        assert current["risk"]["ready_on"] == cutoff
        assert metadata["operating_ready"] == has_history
        if has_history:
            assert current["operating"]["accounts"] == ["Q", "R"]
            assert current["operating"]["version"] != old_fit["version"]
            assert current["operating"]["ready_on"] == cutoff
            assert current["serving_manifest"]["auxiliary_timing"]["operating"]["ready_on"] == cutoff
            assert run(data, cutoff, current)["operating_included"]
        else:
            assert current["operating"] is None
            assert "operating" not in current["serving_manifest"]["auxiliary_timing"]
            with pytest.raises(ValueError, match="Chưa có phiên bản"):
                run(data, cutoff, current)
            assert forecast(data, cutoff, 0, current, shap_limit=0)["operating_included"] is False
    finally:
        store.connection.close()


def test_api_and_calibration_reject_forecasts_created_next_morning_in_vietnam(
        cost_case, tmp_path, monkeypatch):
    from agent1_service.workspace import api

    data, cutoff, bundle = cost_case
    clock = [datetime.fromisoformat(cutoff+"T12:00:00+00:00")]

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)

    monkeypatch.setattr(api, "datetime", FixedDatetime)
    app = create_app(state_dir=tmp_path/"state", key_dir=tmp_path/"keys", token="review", firm_id="A")
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer review"
        seed_bundle(app.state.store, data, cutoff, bundle)
        old = []
        for i in range(1, 13):
            day = str((pd.Timestamp(cutoff)-pd.Timedelta(weeks=2*i)).date())
            # 20:00 UTC is 03:00 of the following Vietnamese business day.
            clock[0] = datetime.fromisoformat(day+"T20:00:00+00:00")
            response = client.post("/v1/predict", json=dict(cutoff=day, opening_balance=1000,
                payments_complete=True, shap_limit=0, horizon_weeks=1, simulation_paths=100))
            assert response.status_code == 200, response.text
            old.append(response.json())
        response = client.get("/v1/forecasts/"+old[0]["id"]+"/actuals", params=dict(asof=cutoff))
        assert response.status_code == 200, response.text
        assert response.json()["covered_weeks"] == 1
        assert response.json()["prospective"] is False
        clock[0] = datetime.fromisoformat(cutoff+"T12:00:00+00:00")
        response = client.post("/v1/predict", json=dict(cutoff=cutoff, opening_balance=1000,
            payments_complete=True, shap_limit=0, horizon_weeks=1, simulation_paths=100))
        assert response.status_code == 200, response.text
        current = response.json()
        assert current["calibration_origins"] == 0
        assert current["band_status"] == "insufficient_out_of_sample_errors"
        # The calibrator itself also rejects them, independently of the API index.
        calibrate_bands(current, old, data)
        assert current["calibration_origins"] == 0
