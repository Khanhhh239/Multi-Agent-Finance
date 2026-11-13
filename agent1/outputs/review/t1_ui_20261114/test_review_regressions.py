"""Review probes: assert desired behavior; failures reproduce outstanding bugs.

These tests use isolated temporary stores, never a company database.
Run from repository root with PYTHONPATH=agent1;agent1/tests/adaptive.
"""

from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from test_company_workspace import accounting_invoice
from test_t1_periodic import catalog, invoice, seed_store, fake_fit, set_time
from agent1.adaptive.cash_adapter import fit_partial
from agent1.adaptive.data import fingerprint, validate_dataset
from agent1.adaptive.landmark_features import FEATURES
from agent1.adaptive.t1_data import landmarks
from agent1_service.api import create_app
from agent1_service.workspace import t1_lifecycle as life


def covered_data():
    original = accounting_invoice(
        issue_date="2024-12-01", due_date="2024-12-31", known_at="2024-12-01"
    )
    return dict(
        invoices=[original], payments=[], outflows=[],
        payment_coverage=[dict(complete=True, start_date="2024-12-01",
                               end_date="2025-08-01", known_at="2025-04-02")],
    )


def test_adjustment_and_reversal_must_invalidate_fixed_claim():
    data = covered_data()
    original = data["invoices"][0]
    credit = dict(original, invoice_id="CREDIT", invoice_no="CREDIT",
                  issue_date="2025-01-10", known_at="2025-01-10",
                  adjustment_type="adjustment", adjusts_invoice_id="ORIGINAL",
                  amount_net=-100, vat=-10, amount=-110)
    debit = dict(credit, invoice_id="DEBIT", invoice_no="DEBIT",
                 issue_date="2025-01-20", known_at="2025-01-20",
                 amount_net=100, vat=10, amount=110)
    data["invoices"].extend([credit, debit])
    validate_dataset(data)
    frame = landmarks(data, "2025-01-01", "2025-04-02")
    assert frame.empty, "Claim 1100 -> 990 -> 1100 survives as an unchanged target"


def test_day_120_customer_change_must_not_erase_mature_91_day_label():
    data = covered_data()
    expected = landmarks(data, "2025-01-01", "2025-04-02")
    original = data["invoices"][0]
    corrected = dict(original, customer_id="OTHER", known_at="2025-05-01", record_version=2)
    data["invoices"] = [corrected]
    data["record_history"] = {"invoices": [original, corrected]}
    actual = landmarks(data, "2025-01-01", "2025-05-02")
    assert actual.invoice_id.tolist() == expected.invoice_id.tolist()


def test_empty_prior_ratio_atom_must_not_become_observed_cash_behavior():
    frame = pd.DataFrame(np.zeros((1, 18)), columns=FEATURES)
    frame["invoice_id"] = ["I"]
    frame["origin"] = pd.Timestamp("2025-01-01")
    frame["label_end"] = pd.Timestamp("2025-01-08")
    frame["followup_days"] = 7
    frame["paid_days"] = np.inf
    for week in range(1, 14):
        frame[f"cash_{week}"] = 0.01 if week == 1 else 0.0
    empty_prior = fit_partial(pd.DataFrame(), "2020-01-01", prior=None)
    learned = fit_partial(frame, "2025-01-08", prior=empty_prior)
    assert learned.means[0] == pytest.approx(0.01), (
        "Only observed partial ratio is 1%; empty-prior placeholder makes it 48.42%"
    )


def test_saved_forecast_must_protect_its_registry_model_from_deletion(tmp_path, catalog, monkeypatch):
    monkeypatch.setenv("AGENT1_T1_GLOBAL_CATALOG", str(catalog.path))
    app = create_app(state_dir=tmp_path / "data", key_dir=tmp_path / "keys",
                     token="review-only", firm_id="A")
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer review-only"
        data = dict(invoices=[invoice(1, "2024-12-01")], payments=[], outflows=[])
        digest = fingerprint(data)
        bundle = catalog.default_bundle("2025-01-01")
        store = app.state.store
        store.put_many("A", {
            "company_datasets": [dict(id=digest, data=data)],
            "company_dataset_active": [dict(id="active", version=digest)],
            "company_models": [life.metadata(bundle, "old", "2024-12-01"),
                               life.metadata(bundle, "new", "2025-01-01")],
            "company_weights": [dict(id=name, **life.encode(bundle)) for name in ("old", "new")],
            "company_model_active": [dict(id="active", version="old")],
        })
        prediction = client.post("/v1/predict", json=dict(
            cutoff="2025-01-01", opening_balance=0, payments_complete=True, shap_limit=0,
        ))
        assert prediction.status_code == 200, prediction.text
        assert prediction.json()["company_bundle_version"] == "old"
        assert client.post("/v1/models/new/activate").status_code == 200
        response = client.delete("/v1/models/old?confirm=old")
        assert response.status_code == 409, response.text


def test_promoted_live_audit_metrics_must_survive_next_candidate_fit(tmp_path, catalog, monkeypatch):
    store, _ = seed_store(tmp_path, catalog)
    try:
        set_time(monkeypatch, "2025-01-01T12:00:00")
        life.run_cycle(store, "A", "2025-01-01", payments_complete=True,
                       catalog=catalog, trainer=fake_fit)
        set_time(monkeypatch, "2025-04-02T12:00:00")
        decision = life.run_cycle(store, "A", "2025-04-02", payments_complete=True,
                                  catalog=catalog, trainer=fake_fit)
        assert decision["status"] == "accepted_prospective_audit"
        accepted = next(row for row in store.get("A", "company_t1_challengers")
                        if row["status"] == "accepted")
        active = store.one("A", "company_models", decision["model_id"])
        assert active["audit"].get("challenger") == accepted["evaluation"]["challenger"]
    finally:
        store.connection.close()
