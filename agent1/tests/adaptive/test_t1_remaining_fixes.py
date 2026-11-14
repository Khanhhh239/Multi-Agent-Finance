"""Remaining review regressions: component clocks, atomic inputs and provenance."""
import base64
from copy import deepcopy
import json
import re

import pandas as pd
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from fastapi.testclient import TestClient

from agent1.adaptive import methods, risk, t1_update
from agent1.adaptive.data import fingerprint, validate_dataset
from agent1.adaptive.operating import select_operating
from agent1.adaptive.t1_data import visible_data
from agent1.adaptive.t1_update import train_update, UpdatePolicy
from agent1_service.api import create_app
from agent1_service.store import Store
from agent1_service.workspace import api as workspace_api, t1_lifecycle as life
from test_t1_periodic import catalog, invoice, history, FixedModel, seed_store, fake_fit, set_time


def cold_data():
    return dict(invoices=[invoice(1, "2024-12-01", 100)], payments=[], outflows=[])


def publish(store, identifier, data, **batches):
    store.put_many("A", dict(company_datasets=[dict(id=identifier, data=deepcopy(data))],
        company_dataset_active=[dict(id="active", version=identifier)], **batches))


def test_retained_t1_cannot_authorize_risk_trained_later(catalog, monkeypatch):
    monkeypatch.setattr(risk, "train_risk", lambda *args: dict(status="evaluated", model=None, prior=.99))
    bundle = methods.train(cold_data(), "2025-12-31", catalog=catalog)
    assert bundle["asof"] == "2020-01-01"
    assert bundle["risk"]["fitted_through"] == "2025-12-31"
    assert bundle["serving_manifest"]["auxiliary_timing"]["risk"]["ready_on"] == "2025-12-31"
    with pytest.raises(ValueError, match="rủi ro xóa nợ"):
        methods.forecast(cold_data(), "2025-01-01", 0, bundle, shap_limit=0)
    plan = methods.forecast(cold_data(), "2025-12-31", 0, bundle, shap_limit=0)
    assert plan["collections"][0]["write_off_probability_365d_at_issue"] == .99


@pytest.mark.parametrize("name", ["risk", "operating"])
@pytest.mark.parametrize("timing", [
    dict(fitted_through="2025-12-31", ready_on="2020-01-01"),
    dict(fitted_through="2020-01-01", ready_on="2025-12-31"),
    {},  # Pre-fix bundle: update_asof bounds its undated auxiliary fits.
])
def test_each_used_component_obeys_both_clocks(catalog, name, timing):
    bundle = catalog.default_bundle("2025-12-31")
    bundle.update(update_asof="2025-12-31")
    bundle[name] = dict(status="evaluated", model=None, prior=.8, **timing)
    with pytest.raises(ValueError, match="chưa sẵn sàng"):
        methods.forecast(cold_data(), "2025-01-01", 0, bundle,
                         include_operating=name == "operating", shap_limit=0)
    if name == "operating":
        # A component the user did not request must not block the AR forecast.
        assert methods.forecast(cold_data(), "2025-01-01", 0, bundle, shap_limit=0)["outstanding"] == 100


def test_legacy_global_fallback_preserves_auxiliary_upper_bound(catalog):
    legacy = dict(asof="2020-01-01", update_asof="2025-12-31",
                  risk=dict(status="evaluated", model=None, prior=.8))
    bundle = catalog.default_bundle("2025-01-01", auxiliary=legacy)
    assert "update_asof" not in bundle
    assert bundle["risk"]["ready_on"] == "2025-12-31"
    with pytest.raises(ValueError, match="rủi ro xóa nợ"):
        methods.forecast(cold_data(), "2025-01-01", 0, bundle, shap_limit=0)


def test_explicit_older_risk_can_serve_after_a_later_t1_update_attempt(catalog):
    bundle = catalog.default_bundle("2025-12-31")
    bundle.update(update_asof="2025-12-31", risk=dict(status="evaluated", model=None, prior=.8,
        fitted_through="2024-12-01", ready_on="2024-12-01"))
    plan = methods.forecast(cold_data(), "2025-01-01", 0, bundle, shap_limit=0)
    assert plan["collections"][0]["write_off_probability_365d_at_issue"] == .8


def test_real_operating_fit_has_its_own_clock_and_old_fit_can_serve(catalog):
    data = dict(cold_data(), bank=[], statements=[], bank_scope=dict(accounts=["Q"]))
    balance = 0
    for i, end in enumerate(pd.date_range("2020-01-07", "2025-12-30", freq="7D")):
        amount = 1_000_000 + i * 100_000
        day = str(end.date())
        data["bank"].append(dict(bank_id=f"B{i}", account="Q", date=day, known_at=day,
            amount=amount, direction="in", component="cash_sale"))
        data["statements"].append(dict(statement_id=f"S{i}", account="Q",
            start_date=str((end - pd.Timedelta(days=6)).date()), end_date=day,
            known_at=day, opening_balance=balance, closing_balance=balance + amount))
        balance += amount
    validate_dataset(data)
    bundle = catalog.default_bundle("2025-12-30")
    bundle["operating"] = select_operating(data, "2025-12-30", include_new_credit=False)
    assert bundle["operating"]["ready_on"] == "2025-12-30"
    assert bundle["operating"]["fitted_through"] == "2025-12-30"
    with pytest.raises(ValueError, match="bán thu ngay"):
        methods.forecast(data, "2024-12-31", 0, bundle, include_operating=True, shap_limit=0)
    bundle["operating"] = select_operating(data, "2024-12-31", include_new_credit=False)
    assert bundle["operating"]["ready_on"] == "2024-12-31"
    plan = methods.forecast(data, "2024-12-31", 0, bundle, include_operating=True, shap_limit=0)
    assert plan["weeks"][0]["cash_in"] > 0


def test_future_t1_parameter_date_is_also_checked(catalog):
    bundle = catalog.default_bundle("2025-12-31")
    bundle["t1_parameter_asof"] = "2025-12-31"
    with pytest.raises(ValueError, match="Tham số T1"):
        methods.forecast(cold_data(), "2025-01-01", 0, bundle, shap_limit=0)


@pytest.mark.parametrize("has_coverage", [False, True])
def test_forecast_snapshot_survives_external_import_and_activation(tmp_path, catalog, monkeypatch, has_coverage):
    monkeypatch.setenv("AGENT1_T1_GLOBAL_CATALOG", str(catalog.path))
    app = create_app(state_dir=tmp_path/"state", key_dir=tmp_path/"keys", token="review", firm_id="A")
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer review"
        store = app.state.store
        store.connection.execute("PRAGMA journal_mode=WAL")
        before, after = cold_data(), cold_data()
        after["payments"] = [dict(payment_id="P", invoice_id="1", amount=40,
            payment_date="2025-01-01", known_at="2025-01-01")]
        bundle = catalog.default_bundle("2025-01-01")
        old_coverage = dict(id="OLD", complete=True, start_date="2024-12-01",
            end_date="2025-01-01", known_at="2025-01-01")
        publish(store, "BEFORE", before,
            company_payment_coverage=[old_coverage] if has_coverage else [],
            company_models=[life.metadata(bundle, "OLD", "2025-01-01")],
            company_weights=[dict(id="OLD", **life.encode(bundle))],
            company_model_active=[dict(id="active", version="OLD")])
        other = Store(store.path, Fernet.generate_key())
        other.cipher = store.cipher
        load, compute = life.load_active, workspace_api.forecast

        def concurrent_import(*args, **kwargs):
            assert store.connection.in_transaction
            publish(other, "AFTER", after,
                company_models=[life.metadata(bundle, "NEW", "2025-01-01")],
                company_weights=[dict(id="NEW", **life.encode(bundle))],
                company_model_active=[dict(id="active", version="NEW")],
                company_payment_coverage=[dict(id="NEW", complete=True, start_date="2024-12-01",
                    end_date="2025-01-01", known_at="2025-01-01")])
            return load(*args, **kwargs)

        def outside_transaction(*args, **kwargs):
            assert not store.connection.in_transaction
            return compute(*args, **kwargs)

        monkeypatch.setattr(life, "load_active", concurrent_import)
        monkeypatch.setattr(workspace_api, "forecast", outside_transaction)
        try:
            response = client.post("/v1/predict", json=dict(cutoff="2025-01-01", opening_balance=0,
                payments_complete=True, shap_limit=0))
            assert response.status_code == 200, response.text
            plan = response.json()
            replay = store.one("A", "company_forecast_replays", plan["id"])
            assert plan["outstanding"] == 100
            assert plan["company_bundle_version"] == "OLD"
            assert plan["t1_input_dataset_hash"] == fingerprint(visible_data(replay["data"], "2025-01-01"))
            assert plan["dataset_hash"] == fingerprint(replay["data"])
            assert replay["data"].get("payment_coverage", []) == ([old_coverage] if has_coverage else [])
            assert store.one("A", "company_dataset_active", "active")["version"] == "AFTER"
            assert store.one("A", "company_model_active", "active")["version"] == "NEW"
        finally:
            other.connection.close()


def test_selected_global_and_proposal_preserve_frozen_t1_fit_date(catalog):
    base = catalog.default_bundle("2025-12-31")
    base.update(model=FixedModel(0), anchor=FixedModel(0), t1_version="bad-incumbent")
    result = train_update(history(), "2025-12-31", incumbent=base, catalog=catalog,
        grids={n: () for n in ("neural", "lightgbm", "xgboost")},
        policy=UpdatePolicy(lookback_days=365, stride_days=56, minimum_fit_snapshots=20,
            minimum_fit_invoices=10, minimum_validation_snapshots=10, minimum_audit_snapshots=10))
    assert result["promotion_status"] == "accepted_historical_audit"
    selected = result["locked_spec"]["method"]
    assert selected.startswith("global_")
    expected = catalog.metadata["models"][selected.removeprefix("global_")]["available_asof"]
    assert result["t1_parameter_asof"] == result["proposal"]["t1_parameter_asof"] == expected
    assert result["asof"] == result["partial"].fitted_through == "2025-12-31"


@pytest.mark.parametrize("refit", [False, True])
def test_incumbent_keeps_fit_date_and_real_refit_advances_it(catalog, monkeypatch, refit):
    # Isolate parameter-clock branches with fixed distributions; causal label
    # construction, selection, final partial fitting and proposal remain real.
    catalog.models = {name: FixedModel(0) for name in catalog.models}
    base = catalog.default_bundle("2025-12-31")
    base.update(t1_parameter_asof="2023-01-01", t1_version="incumbent")
    grids = {n: () for n in ("neural", "lightgbm", "xgboost")}
    if refit:
        grids["neural"] = ((.0001, 1),)
        monkeypatch.setattr(t1_update, "learn", lambda *args: (FixedModel(5), {}))
    else:
        base.update(model=FixedModel(5), anchor=FixedModel(5))
        # An unchanged T1 can be accepted with a changed partial. This test
        # isolates provenance from the numerical audit acceptance threshold.
        monkeypatch.setattr(t1_update, "improves", lambda *args: True)
    result = train_update(history(), "2025-12-31", incumbent=base, catalog=catalog, grids=grids,
        policy=UpdatePolicy(lookback_days=365, stride_days=56, minimum_fit_snapshots=20,
            minimum_fit_invoices=10, minimum_validation_snapshots=10, minimum_audit_snapshots=10, alphas=(1.0,)))
    assert result["promotion_status"] == "accepted_historical_audit"
    expected = "2025-12-31" if refit else "2023-01-01"
    assert result["t1_parameter_asof"] == result["proposal"]["t1_parameter_asof"] == expected
    assert result["locked_spec"]["method"] == ("neural_local_0_a1.0" if refit else "incumbent")
    assert bool(result["training_trace"]) == refit


@pytest.mark.parametrize("parameter_date", ["2020-01-01", "2025-01-01"])
def test_shadow_and_promotion_keep_proposal_parameter_clock(tmp_path, catalog, monkeypatch, parameter_date):
    store, _ = seed_store(tmp_path, catalog)

    def fitter(*args, **kwargs):
        result = fake_fit(*args, **kwargs)
        result["proposal"]["t1_parameter_asof"] = parameter_date
        return result

    try:
        set_time(monkeypatch, "2025-01-01T12:00:00")
        life.run_cycle(store, "A", "2025-01-01", payments_complete=True, catalog=catalog, trainer=fitter)
        row = store.get("A", "company_t1_challengers")[0]
        shadow = life.decode(store.one("A", "company_t1_challenger_weights", row["artifact_id"]))
        assert shadow["t1_parameter_asof"] == parameter_date
        assert shadow["asof"] == "2025-01-01"
        set_time(monkeypatch, "2025-04-02T12:00:00")
        result = life.run_cycle(store, "A", "2025-04-02", payments_complete=True, catalog=catalog, trainer=fitter)
        saved = life.decode(store.one("A", "company_weights", result["model_id"]))
        assert saved["t1_parameter_asof"] == saved["serving_manifest"]["t1_parameter_asof"] == parameter_date
        assert saved["asof"] == "2025-04-02"
    finally:
        store.connection.close()


def decrypt_report(path, password):
    packed = json.loads(re.search(r"const encrypted=(.*);", path.read_text(encoding="utf-8")).group(1))
    b = {k: base64.b64decode(v) for k, v in packed.items()}
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b["salt"], iterations=600000).derive(password.encode())
    return json.loads(AESGCM(key).decrypt(b["nonce"], b["ciphertext"], None))


def test_encrypted_report_matches_artifact_metadata_and_decision_each_cycle(tmp_path, catalog, monkeypatch):
    secret = tmp_path/"password.txt"
    secret.write_text("test-password", encoding="utf-8")
    monkeypatch.setenv("AGENT1_REPORT_PASSWORD_FILE", str(secret))
    monkeypatch.setenv("AGENT1_REPORT_DIR", str(tmp_path/"reports"))
    store = Store(tmp_path/"isolated.db", Fernet.generate_key())
    try:
        publish(store, "D", cold_data())
        previous = None
        for day in ("2025-01-01", "2025-01-29"):
            set_time(monkeypatch, day + "T12:00:00")
            decision = life.run_cycle(store, "A", day, payments_complete=True, catalog=catalog)
            saved = life.decode(store.one("A", "company_weights", decision["model_id"]))
            metadata = store.one("A", "company_models", decision["model_id"])
            report = decrypt_report(tmp_path/"reports"/f"Agent1_train_{decision['model_id']}.html", "test-password")["training"]
            assert metadata["encrypted_report"]
            assert report["update_period"] == saved["update_period"] == metadata["update_period"] == decision["update_period"]
            assert report["update_period"]["previous_cycle_asof"] == previous
            assert report["update_period"]["current_asof"] == day
            for key in ("asof", "update_asof", "t1_parameter_asof", "partial_version", "adapter_version", "serving_manifest"):
                assert report[key] == saved[key] == metadata[key]
            assert report["serving_manifest"] == decision["serving_manifest"]
            assert report["partial_fitted_through"] == saved["partial"].fitted_through
            previous = day
    finally:
        store.connection.close()
