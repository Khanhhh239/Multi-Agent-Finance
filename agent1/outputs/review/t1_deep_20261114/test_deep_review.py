"""Second review: desired-behavior probes, isolated stores only.

PYTHONPATH=agent1;agent1/tests/adaptive
These failing assertions describe open bugs; they do not change production.
"""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from fastapi.testclient import TestClient

from test_t1_periodic import catalog, invoice, set_time, history, FixedModel
from agent1.adaptive import methods, risk, training_report
from agent1.adaptive.data import fingerprint
from agent1.adaptive.t1_update import train_update, UpdatePolicy
from agent1_service.api import create_app
from agent1_service.workspace import t1_lifecycle as life


class FutureRisk:
    def predict_proba(self, x):
        return np.tile([0.01, 0.99], (len(x), 1))


def cold_data():
    return dict(invoices=[invoice(1, "2024-12-01", 100)], payments=[], outflows=[])


def publish(store, identifier, data):
    store.put_many("A", {
        "company_datasets": [dict(id=identifier, data=deepcopy(data))],
        "company_dataset_active": [dict(id="active", version=identifier)],
    })


def test_kept_t1_must_not_authorize_future_auxiliary_parameters(catalog, monkeypatch):
    data = cold_data()
    fitted = []

    def fit_risk(data, when):
        fitted.append(str(when.date()))
        return dict(status="evaluated", model=FutureRisk(), prior=0.99)

    monkeypatch.setattr(risk, "train_risk", fit_risk)
    bundle = methods.train(data, "2025-12-31", catalog=catalog)
    assert fitted == ["2025-12-31"]
    assert bundle["promotion_status"] == "kept_incumbent"
    assert bundle["asof"] == "2020-01-01"
    # T1 itself is old enough, but the risk parameters were fitted 364 days later.
    # Acceptable fixes can reject this request or omit/recover an eligible risk.
    try:
        plan = methods.forecast(data, "2025-01-01", 0, bundle, shap_limit=0)
    except ValueError:
        return
    assert all(r["write_off_probability_365d_at_issue"] is None for r in plan["collections"]), (
        "A kept T1 permits backdated forecasts to use risk freshly fitted at update_asof"
    )


def test_forecast_input_hash_must_describe_its_frozen_data(tmp_path, catalog, monkeypatch):
    monkeypatch.setenv("AGENT1_T1_GLOBAL_CATALOG", str(catalog.path))
    app = create_app(state_dir=tmp_path/"state", key_dir=tmp_path/"keys", token="review", firm_id="A")
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer review"
        store = app.state.store
        before = cold_data()
        after = deepcopy(before)
        after["payments"] = [dict(payment_id="P", invoice_id="1", amount=40,
                                  payment_date="2025-01-01", known_at="2025-01-01")]
        publish(store, "BEFORE", before)
        original = life.load_active

        def import_between_reads(*args, **kwargs):
            # Deterministic interleaving: current() already read BEFORE, then
            # an import commits before current_t1_data() computes the input hash.
            publish(store, "AFTER", after)
            return original(*args, **kwargs)

        monkeypatch.setattr(life, "load_active", import_between_reads)
        response = client.post("/v1/predict", json=dict(cutoff="2025-01-01", opening_balance=0,
                                                       payments_complete=True, shap_limit=0))
        assert response.status_code == 200, response.text
        plan = response.json()
        replay = store.one("A", "company_forecast_replays", plan["id"])
        assert plan["outstanding"] == 100
        expected = fingerprint(life.visible_data(replay["data"], "2025-01-01"))
        assert plan["t1_input_dataset_hash"] == expected, (
            "Prediction/replay use BEFORE, while the advertised T1 input hash uses AFTER"
        )


def test_encrypted_report_must_include_the_period_committed_with_its_model(tmp_path, catalog, monkeypatch):
    from agent1_service.store import Store
    from cryptography.fernet import Fernet
    store = Store(tmp_path/"isolated.db", Fernet.generate_key())
    captured = []
    monkeypatch.setattr(training_report, "save_training_report", lambda bundle, data, identifier:
                        captured.append(training_report.report_data(bundle, data, identifier)))
    set_time(monkeypatch, "2025-01-01T12:00:00")
    try:
        publish(store, "D", cold_data())
        decision = life.run_cycle(store, "A", "2025-01-01", payments_complete=True, catalog=catalog)
        saved = life.decode(store.one("A", "company_weights", decision["model_id"]))
        assert saved["update_period"]["current_asof"] == "2025-01-01"
        assert captured[0]["training"]["update_period"] == saved["update_period"], (
            "Report is generated before this cycle's update_period is attached"
        )
    finally:
        store.connection.close()


def test_selected_frozen_global_must_keep_its_parameter_fit_date(catalog):
    data = history()
    base = catalog.default_bundle("2025-12-31")
    base.update(model=FixedModel(0), anchor=FixedModel(0), t1_version="bad-incumbent")
    result = train_update(data, "2025-12-31", incumbent=base, catalog=catalog,
                          grids={n: () for n in ("neural", "lightgbm", "xgboost")},
                          policy=UpdatePolicy(lookback_days=365, stride_days=56,
                                              minimum_fit_snapshots=20, minimum_fit_invoices=10,
                                              minimum_validation_snapshots=10, minimum_audit_snapshots=10))
    assert result["promotion_status"] == "accepted_historical_audit", result["audit"]
    assert result["locked_spec"]["family"] is None
    selected = result["locked_spec"]["method"]
    assert selected.startswith("global_"), selected
    expected = catalog.metadata["models"][selected.removeprefix("global_")]["available_asof"]
    assert result["t1_parameter_asof"] == expected, (
        "A frozen global was selected and only partial was re-fit, but its T1 fit date advanced"
    )
