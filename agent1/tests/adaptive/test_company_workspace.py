"""Synthetic fixtures verify mechanics only; never production method selection evidence."""

import time
from datetime import date, timedelta
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from agent1.adaptive.data import (
    parse_rows,
    suggested_mapping,
    observed,
    validate_dataset,
    fingerprint,
)
from agent1.adaptive.methods import Method, features, forecast, train
from agent1_service.api import create_app


def company_data(days=210):
    data = dict(invoices=[], payments=[], outflows=[])
    start = date(2025, 1, 1)
    for day in range(days):
        issued = start + timedelta(days=day)
        for k in range(2):
            iid = f"INV-{day}-{k}"
            amount = float(100000 * (1 + day % 9))
            data["invoices"].append(
                dict(
                    invoice_id=iid,
                    customer_id=f"C{day % 19}",
                    issue_date=str(issued),
                    due_date=str(issued + timedelta(days=21)),
                    known_at=str(issued),
                    amount=amount,
                    currency="VND",
                )
            )
            if (day + k) % 5:
                paid = issued + timedelta(days=14 + (day % 4) * 7)
                data["payments"].append(
                    dict(
                        payment_id="PAY-" + iid,
                        invoice_id=iid,
                        payment_date=str(paid),
                        known_at=str(paid),
                        amount=amount,
                    )
                )
    data["outflows"] = [
        dict(
            expense_id="EXP1",
            date="2025-08-07",
            known_at="2025-07-01",
            amount=1500000.0,
            category="rent",
        )
    ]
    return data


@pytest.fixture
def client(tmp_path):
    app = create_app(
        state_dir=tmp_path / "data",
        key_dir=tmp_path / "keys",
        token="company-test-token",
        firm_id="SME",
    )
    with TestClient(app) as c:
        c.headers["Authorization"] = "Bearer company-test-token"
        yield c


def upload(client, kind, rows):
    file = pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig")
    response = client.post(
        "/v1/imports/preview",
        files={"file": ("data.csv", file, "text/csv")},
        data={"kind": kind, "date_format": "%Y-%m-%d", "number_format": "plain"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def import_all(client, data):
    for kind, rows in data.items():
        preview = upload(client, kind, rows)
        assert preview["can_commit"], preview
        assert (
            client.post("/v1/imports/" + preview["id"] + "/commit").status_code == 200
        )


def test_vietnamese_mapping_strict_money_dates():
    raw = pd.DataFrame(
        [
            {
                "Mã hóa đơn": "HD1",
                "Mã khách hàng": "KH1",
                "Ngày lập": "01/01/2026",
                "Hạn thanh toán": "31/01/2026",
                "Số tiền": "1.500.000,50",
            }
        ]
    )
    mapping = suggested_mapping(raw.columns, "invoices")
    rows, errors, warnings = parse_rows(raw, "invoices", mapping)
    assert not errors and rows[0]["amount"] == 1500000.5 and warnings
    for invalid in ["1.2.3", "1,000.00", "NaN", "inf", "-50", "=SUM(1,2)"]:
        raw.loc[0, "Số tiền"] = invalid
        assert parse_rows(raw, "invoices", mapping)[1]
    raw.loc[0, "Số tiền"] = "1000"
    raw.loc[0, "Ngày lập"] = "31/02/2026"
    assert parse_rows(raw, "invoices", mapping)[1]


def test_excel_native_date_and_numeric_values():
    raw = pd.DataFrame(
        [
            dict(
                invoice_id="I",
                customer_id="C",
                issue_date=pd.Timestamp("2026-01-01"),
                due_date=pd.Timestamp("2026-02-01"),
                amount=1500000.5,
            )
        ]
    )
    rows, errors, _ = parse_rows(
        raw, "invoices", suggested_mapping(raw.columns, "invoices")
    )
    assert not errors and rows[0]["amount"] == 1500000.5


def test_duplicates_orphans_overpayments_and_schedule_clock():
    data = company_data(2)
    raw = pd.DataFrame(data["invoices"][:1] * 2)
    assert parse_rows(
        raw, "invoices", suggested_mapping(raw.columns, "invoices"), "%Y-%m-%d", "plain"
    )[1]
    data["payments"].append(
        dict(
            payment_id="bad",
            invoice_id="absent",
            payment_date="2025-01-01",
            known_at="2025-01-01",
            amount=5,
        )
    )
    with pytest.raises(ValueError, match="chưa có"):
        validate_dataset(data)
    data["payments"][-1]["invoice_id"] = data["invoices"][0]["invoice_id"]
    data["payments"][-1]["amount"] = 1e12
    with pytest.raises(ValueError, match="vượt"):
        validate_dataset(data)
    raw = pd.DataFrame(
        [dict(expense_id="X", date="2026-12-01", amount=100, category="rent")]
    )
    assert parse_rows(
        raw, "outflows", suggested_mapping(raw.columns, "outflows"), "%Y-%m-%d", "plain"
    )[1]


def test_future_and_late_payment_do_not_leak_or_erase_partial_payments():
    data = company_data(1)
    iid = data["invoices"][0]["invoice_id"]
    data["payments"] = [
        dict(
            payment_id="A",
            invoice_id=iid,
            payment_date="2025-01-03",
            known_at="2025-01-03",
            amount=40000,
        ),
        dict(
            payment_id="B",
            invoice_id=iid,
            payment_date="2025-01-05",
            known_at="2025-02-10",
            amount=60000,
        ),
    ]
    early = observed(data, "2025-02-01").set_index("invoice_id").loc[iid]
    assert pd.isna(early.settled) and early.remaining_amount == 60000
    late = observed(data, "2025-02-11").set_index("invoice_id").loc[iid]
    assert late.settled == pd.Timestamp(
        "2025-01-05"
    ) and late.settled_known_at == pd.Timestamp("2025-02-10")
    frame = observed(data, "2025-02-11")
    target = frame.iloc[:1].copy()
    target.issue_date = pd.Timestamp("2025-02-01")
    assert features(target, frame)[0, -1] == 0


def test_full_week_risk_includes_only_complete_observation():
    data = company_data(1)
    data["payments"] = [
        dict(
            payment_id="P",
            invoice_id=data["invoices"][0]["invoice_id"],
            payment_date="2025-01-03",
            known_at="2025-01-03",
            amount=100000,
        )
    ]
    model = Method("survival").fit(observed(data, "2025-01-06"), "2025-01-06")
    assert model.hazard[0] == pytest.approx(0.5 / 5)
    model = Method("survival").fit(observed(data, "2025-01-08"), "2025-01-08")
    assert model.hazard[0] == pytest.approx(1.5 / 7)
    p = model.distribution(model.history)
    assert np.allclose(p.sum(axis=1), 1) and (p >= 0).all()


def test_training_cohorts_refits_and_audit_is_not_selection():
    data = company_data()
    calls = []
    original = Method.fit

    def fit(self, frame, clock):
        calls.append((self.name, pd.Timestamp(clock), frame.issue_date.max()))
        return original(self, frame, clock)

    with patch.object(Method, "fit", fit):
        bundle = train(data, "2025-08-01", names=["customer", "survival", "logistic"])
    assert (
        bundle["train_n"] >= 60
        and bundle["validation_n"] >= 20
        and bundle["audit"]["n"] >= 20
    )
    assert all(latest <= clock for _, clock, latest in calls)
    assert {"2025-05-09", "2025-06-06", "2025-07-04"}.issubset(
        {str(clock.date()) for _, clock, _ in calls}
    )
    assert {str(clock.date()) for _, clock, _ in calls}.issuperset(
        {
            "2025-04-11",
            "2025-06-06",
            "2025-08-01",
        }
    )
    assert [r["method"] for r in bundle["selection"]] == [
        "customer",
        "survival",
        "logistic",
        "pool",
    ]
    assert np.isfinite(bundle["audit"]["log_loss4"])
    assert (
        bundle["audit"]["improvement_ci_low"] <= bundle["audit"]["improvement_ci_high"]
    )
    assert bundle["weight"] == 0 if not bundle["audit"]["accepted"] else True


def test_late_invoice_not_used_in_issue_origin_evaluation():
    data = company_data()
    for invoice in data["invoices"]:
        invoice["known_at"] = "2025-08-01"
    with pytest.raises(ValueError, match="Chưa đủ"):
        train(data, "2025-08-01", names=["customer"])


def test_forecast_cash_identity_asof_and_stress():
    data = company_data()
    baseline = forecast(data, "2025-08-01", 1000000)
    stressed = forecast(
        data, "2025-08-01", 1000000, delay_days=14, expense_multiplier=1.2
    )
    assert stressed["weeks"][0]["cash_in"] <= baseline["weeks"][0]["cash_in"]
    balance = 1000000
    for week in baseline["weeks"]:
        balance += week["cash_in"] - week["cash_out"]
        assert week["balance"] == pytest.approx(balance)
        assert week["low"] <= week["high"]
    future = dict(data)
    future["outflows"] = data["outflows"] + [
        dict(
            expense_id="future",
            date="2025-08-08",
            known_at="2025-08-02",
            amount=1e12,
            category="x",
        )
    ]
    assert forecast(future, "2025-08-01", 1000000) == baseline
    with pytest.raises(ValueError, match="sau ngày"):
        forecast(data, "2025-08-01", 0, bundle={"asof": "2025-09-01"})


def test_api_auth_static_no_secret_and_preview_atomicity(client):
    assert (
        client.get(
            "/v1/workspace", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    html = client.get("/workspace")
    assert html.status_code == 200 and "Sổ điều hành" in html.text
    assert "company-test-token" not in html.text
    for asset in [
        "app.js",
        "style.css",
        "vendor/uPlot.iife.min.js",
        "vendor/TABLER-LICENSE.txt",
    ]:
        assert client.get("/workspace-assets/" + asset).status_code == 200
    data = company_data(2)
    a = upload(client, "invoices", data["invoices"][:1])
    b = upload(client, "invoices", data["invoices"][1:])
    assert client.post("/v1/imports/" + a["id"] + "/commit").status_code == 200
    assert client.post("/v1/imports/" + b["id"] + "/commit").status_code == 409
    counts = client.get("/v1/workspace").json()["counts"]
    assert counts["invoices"] == 1
    bad = upload(client, "payments", data["payments"])
    assert (
        not bad["can_commit"]
        and client.post("/v1/imports/" + bad["id"] + "/commit").status_code == 422
    )
    assert client.get("/v1/workspace").json()["counts"] == counts


def test_api_requires_completeness_and_rejects_demo(client):
    assert client.post("/v1/training", json={"asof": "2025-08-01"}).status_code == 422
    assert (
        client.post(
            "/v1/predict", json={"cutoff": "2025-08-01", "opening_balance": 0}
        ).status_code
        == 422
    )
    raw = client.get("/v1/templates/invoices").content
    preview = client.post(
        "/v1/imports/preview",
        files={"file": ("demo.csv", raw)},
        data={"kind": "invoices"},
    ).json()
    assert preview["can_commit"]
    assert client.post("/v1/imports/" + preview["id"] + "/commit").status_code == 200
    assert (
        client.post(
            "/v1/training", json={"asof": "2026-11-01", "payments_complete": True}
        ).status_code
        == 422
    )
    assert client.delete("/v1/records/invoices/DEMO_HD001").status_code == 200
    assert client.get("/v1/workspace").json()["counts"]["invoices"] == 0


def test_api_end_to_end_real_models_version_activation_and_update(client):
    data = company_data()
    import_all(client, data)
    original = train
    # Bounded algorithms for integration speed; full-bag execution is checked separately.
    with patch(
        "agent1_service.workspace.api.train",
        lambda data, asof, progress: original(
            data, asof, progress, names=["customer", "survival", "logistic"]
        ),
    ):
        started = client.post(
            "/v1/training", json={"asof": "2025-08-01", "payments_complete": True}
        )
        assert started.status_code == 202
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            result = client.get("/v1/workspace").json()
            if result["jobs"][0]["status"] in ["completed", "failed"]:
                break
            time.sleep(0.05)
        assert result["jobs"][0]["status"] == "completed", result
    assert result["active_version"] is None
    version = result["versions"][0]
    assert (
        not {"artifact", "model", "selection", "selected_method", "selected_weight"}
        & version.keys()
    )
    assert client.post("/v1/models/absent/activate").status_code == 404
    assert client.post("/v1/models/" + version["id"] + "/activate").status_code == 200
    prediction = client.post(
        "/v1/predict",
        json={
            "cutoff": "2025-08-01",
            "opening_balance": 1e6,
            "payments_complete": True,
        },
    )
    assert prediction.status_code == 200, prediction.text
    assert (
        prediction.json()["model_version"] == version["id"]
        and len(prediction.json()["weeks"]) == 13
    )
    assert prediction.json()["pilot_ready"] is False
    # A prior internally generated artifact can be reactivated, without refitting.
    stored = client.app.state.store.get("SME", "company_models")[0]
    second = dict(stored, id="second-version")
    client.app.state.store.put("SME", "company_models", [second])
    assert client.post("/v1/models/second-version/activate").status_code == 200
    assert client.get("/v1/workspace").json()["active_version"] == "second-version"
    assert client.post("/v1/models/" + version["id"] + "/activate").status_code == 200
    assert client.get("/v1/workspace").json()["active_version"] == version["id"]
    update = dict(data["invoices"][0], amount=200000)
    preview = upload(client, "invoices", [update])
    assert preview["updates"] == 1
    assert client.post("/v1/imports/" + preview["id"] + "/commit").status_code == 200
    assert client.get("/v1/workspace").json()["needs_retraining"] is True
    assert client.post(
        "/v1/predict",
        json={
            "cutoff": "2025-08-01",
            "opening_balance": 1e6,
            "payments_complete": True,
        },
    ).json()["stale_model"]
    assert (
        client.delete(
            "/v1/records/invoices/" + data["payments"][0]["invoice_id"]
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "method",
    [
        "due",
        "customer",
        "survival",
        "logistic",
        "forest",
        "extra",
        "hist",
        "lightgbm",
        "xgboost",
    ],
)
def test_every_registered_method_can_fit_and_predict(method):
    data = company_data(65)
    frame = observed(data, "2025-04-01")
    model = Method(method).fit(frame, "2025-04-01")
    p = model.distribution(frame.iloc[:5], ages=np.arange(5) * 7)
    assert p.shape == (5, 14) and np.isfinite(p).all() and np.allclose(p.sum(1), 1)


def test_model_and_data_are_encrypted_at_rest(client):
    data = company_data(1)
    preview = upload(client, "invoices", data["invoices"])
    client.post("/v1/imports/" + preview["id"] + "/commit")
    connection = client.app.state.store.connection
    payload = connection.execute(
        "select payload from records where kind='company_datasets'"
    ).fetchone()[0]
    assert b"INV-0-0" not in payload
    assert client.app.state.store.get("another-company", "company_datasets") == []
    assert fingerprint(data) != fingerprint(dict(data, invoices=[]))


def test_browser_security_headers_and_unknown_fields(client):
    response = client.get("/workspace")
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.get("/v1/workspace").headers["x-content-type-options"] == "nosniff"
    assert (
        client.post(
            "/v1/training",
            json={"asof": "2025-08-01", "payments_complete": True, "firm": "another"},
        ).status_code
        == 422
    )


def test_delete_and_duplicate_training_blocked_until_worker_finishes(client):
    from threading import Event

    started, release = Event(), Event()

    def worker(*_):
        started.set()
        release.wait(5)
        raise ValueError("Expected test failure")

    with patch("agent1_service.workspace.api.train", worker):
        try:
            body = {"asof": "2025-08-01", "payments_complete": True}
            assert client.post("/v1/training", json=body).status_code == 202
            assert started.wait(2)
            assert client.delete("/data").status_code == 409
            assert client.post("/v1/training", json=body).status_code == 409
        finally:
            release.set()


def test_interrupted_job_is_recoverable_on_restart(tmp_path):
    first = create_app(
        state_dir=tmp_path / "data",
        key_dir=tmp_path / "keys",
        token="test",
        firm_id="SME",
    )
    with TestClient(first):
        first.state.store.put(
            "SME",
            "company_jobs",
            [
                dict(
                    id="interrupted",
                    status="running",
                    message="Old",
                    created_at="2026-01-01",
                )
            ],
        )
    second = create_app(
        state_dir=tmp_path / "data",
        key_dir=tmp_path / "keys",
        token="test",
        firm_id="SME",
    )
    with TestClient(second) as client:
        status = client.get(
            "/v1/workspace", headers={"Authorization": "Bearer test"}
        ).json()
        assert status["jobs"][0]["status"] == "failed"
        assert "khởi động lại" in status["jobs"][0]["message"]


def test_variable_forecast_horizon_and_excel_export(client):
    from datetime import date
    from io import BytesIO
    from openpyxl import load_workbook

    data = company_data()
    # This expense is known at the forecast origin, but falls beyond week 13.
    data["outflows"].append(
        dict(
            expense_id="LATE",
            date="2025-12-10",
            known_at="2025-07-01",
            amount=800000,
            category="rent",
        )
    )
    import_all(client, data)
    body = dict(cutoff="2025-08-01", opening_balance=10000000, payments_complete=True)
    standard = client.post("/v1/predict", json=body).json()
    assert len(standard["weeks"]) == 13
    short = client.post("/v1/predict", json={**body, "horizon_weeks": 1}).json()
    assert short["weeks"] == standard["weeks"][:1]
    assert short["collections"] == standard["collections"]
    response = client.post("/v1/predict", json={**body, "horizon_weeks": 26})
    assert response.status_code == 200, response.text
    plan = response.json()
    assert len(plan["weeks"]) == 26
    assert plan["weeks"][18]["cash_out"] == 800000
    assert plan["weeks"][-1]["date"] == "2026-01-30"
    assert plan["inference_ms"] >= 0
    assert (
        client.post(
            "/v1/predict", json={**body, "horizon_weeks": 2, "confirmed_weeks": [3]}
        ).status_code
        == 422
    )

    exported = client.get("/v1/forecasts/" + plan["id"] + "/xlsx")
    assert exported.status_code == 200, exported.text
    workbook = load_workbook(BytesIO(exported.content))
    assert workbook.sheetnames == [
        "Kết quả dự báo",
        "Kế hoạch từng tuần",
        "Khoản cần chú ý",
    ]
    weeks = workbook["Kế hoạch từng tuần"]
    assert weeks.max_row == 27
    assert weeks["B27"].value.date() == date(2026, 1, 30)
    assert weeks["B27"].number_format == "dd-mm-yy"
    assert weeks["E20"].value == 800000
    assert workbook["Khoản cần chú ý"].max_row == len(plan["collections"]) + 1
