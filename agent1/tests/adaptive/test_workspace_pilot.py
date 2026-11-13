from datetime import date, timedelta
import numpy as np
import pandas as pd
import pytest
from cryptography.fernet import Fernet, InvalidToken
from fastapi.testclient import TestClient
from agent1.adaptive.cash_history import weekly_cash, evaluate_plan
from agent1.adaptive.data import validate_dataset
from agent1.adaptive.methods import forecast
from agent1.adaptive.cash_adapter import fit_partial
from agent1.adaptive.operating import select_operating
from agent1_service.workspace.recovery import transfer
from agent1_service.api import create_app
from agent1_service.store import Store


class Tail:
    """Serializable serving fixture; its artifact must survive a saved forecast."""
    def distribution(self, frame, ages, horizon=13):
        x = np.zeros((len(frame), horizon + 1))
        x[:, -1] = 1
        return x


class Half:
    def distribution(self, frame, ages):
        p = np.zeros((len(frame), 14))
        p[:, 0] = 0.5
        p[:, -1] = 0.5
        return p


def book():
    start = "2026-01-01"
    return dict(
        invoices=[
            dict(
                invoice_id=i,
                customer_id="C",
                amount=amt,
                issue_date=start,
                known_at=start,
                due_date="2026-01-15",
                currency="VND",
            )
            for i, amt in (("A", 30.0), ("B", 70.0))
        ],
        payments=[],
        outflows=[],
        bank=[
            dict(
                bank_id="T",
                account="Q",
                direction="in",
                amount=100.0,
                date="2026-02-01",
                known_at="2026-02-01",
            )
        ],
        statements=[
            dict(
                statement_id="S",
                account="Q",
                start_date=start,
                end_date="2026-02-07",
                opening_balance=50.0,
                closing_balance=150.0,
                known_at="2026-02-07",
            )
        ],
    )


def test_bank_conservation_coverage_and_actual_balance():
    d = book()
    validate_dataset(d)
    actual = weekly_cash(d, "2026-02-01", 2, "2026-02-07", ["Q"])
    assert actual[0, 0] == 100 and np.isnan(actual[1]).all()
    assert np.isnan(weekly_cash(d, "2026-02-01", 1, "2026-02-06", ["Q"])).all()
    plan = forecast(d, "2026-01-31", 999, confirmed_weeks=[1])
    assert plan["weeks"][0]["outflow_status"] == "confirmed_zero"
    assert plan["unknown_outflow_weeks"] == list(range(2, 14))
    assert 0 <= plan["weeks"][0]["cash_in"] <= plan["outstanding"]
    assert plan["t1_provenance"]["source"] == "global_catalog"
    rows = evaluate_plan(d, plan, "2026-02-07", ["Q"])
    assert rows[0]["actual_balance"] == 150 and not rows[1]["balance_available"]
    d["statements"][0]["closing_balance"] -= 1
    with pytest.raises(ValueError, match="sao kê"):
        validate_dataset(d)


@pytest.mark.parametrize("horizon", [1, 13, 26, 52])
def test_actual_balances_cover_the_entire_selected_forecast_horizon(horizon):
    data = book()
    end = str(date(2026, 1, 31) + timedelta(weeks=horizon))
    data["statements"][0].update(end_date=end, known_at=end)
    validate_dataset(data)
    plan = forecast(data, "2026-01-31", 150, horizon_weeks=horizon)
    actuals = evaluate_plan(data, plan, end, ["Q"])
    assert len(actuals) == horizon
    assert all(row["covered"] and row["balance_available"] for row in actuals)
    assert actuals[-1]["week"] == horizon
    assert actuals[-1]["actual_balance"] == 150


def test_allocations_roles_recovery(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT1_AGENT4_TOKEN", "reader-a")
    app = create_app(
        tmp_path / "work", token="accountant-a", firm_id="A", key_dir=tmp_path / "keys"
    )
    root = {"Authorization": "Bearer accountant-a"}
    reader = {"Authorization": "Bearer reader-a"}
    with TestClient(app) as c:
        d = book()
        from agent1.adaptive.data import fingerprint

        digest = fingerprint(d)
        app.state.store.put("A", "company_datasets", [dict(id=digest, data=d)])
        app.state.store.put(
            "A", "company_dataset_active", [dict(id="active", version=digest)]
        )
        req = dict(payment_id="pay-A", bank_id="T", invoice_id="A", amount=30.0,
                   reviewed_by="Test reviewer", note="Test bank evidence")
        assert c.post("/v1/allocations", json=req, headers=root).is_success
        assert c.post("/v1/allocations", json=req, headers=root).json()["replayed"]
        assert c.get("/v1/reconciliation", headers=root).json()["unallocated"] == 70
        assert (
            c.post(
                "/v1/allocations",
                json=dict(req, payment_id="pay-B", invoice_id="B", amount=71.0),
                headers=root,
            ).status_code
            == 422
        )
        assert c.post(
            "/v1/allocations",
            json=dict(req, payment_id="pay-B", invoice_id="B", amount=70.0),
            headers=root,
        ).is_success
        assert c.get("/v1/reconciliation", headers=root).json()["pending_count"] == 0
        body = dict(cutoff="2026-02-07", opening_balance=150, payments_complete=True)
        plan = c.post("/v1/predict", json=body, headers=root).json()
        assert c.get("/v1/forecasts/" + plan["id"], headers=reader).json() == plan
        assert c.post("/v1/predict", json=body, headers=reader).status_code == 401
        assert c.get("/v1/reconciliation", headers=reader).status_code == 401
        monkeypatch.delenv("AGENT1_AGENT4_TOKEN")
        assert c.get("/v1/forecasts", headers=reader).status_code == 401
        key = tmp_path / "keys/encryption.key"
        backup = tmp_path / "backup/agent1.db"
        transfer(tmp_path / "work/agent1.db", backup, key)
    restored = tmp_path / "rehearsal/agent1.db"
    transfer(backup, restored, key)
    registry = Store(restored, key.read_bytes())
    assert registry.one("A", "company_predictions", plan["id"]) == plan
    assert registry.one("B", "company_predictions", plan["id"]) is None
    registry.connection.close()
    with pytest.raises(ValueError):
        transfer(backup, restored, key)
    wrong = tmp_path / "keys/wrong.key"
    wrong.write_bytes(Fernet.generate_key())
    with pytest.raises(InvalidToken):
        transfer(backup, tmp_path / "invalid.db", wrong)
    assert not (tmp_path / "invalid.db").exists()


def test_actions_skip_writeoff_and_dispute():
    d = book()
    d["actions"] = [
        dict(
            event_id=str(i),
            invoice_id=id,
            date="2026-01-30",
            known_at="2026-01-30",
            kind=kind,
        )
        for i, (id, kind) in enumerate([("A", "write_off"), ("B", "dispute")])
    ]
    validate_dataset(d)
    r = forecast(d, "2026-01-31", 0)
    assert r["open_invoices"] == 1 and r["collections"][0]["disputed"]
    d["actions"].append(dict(d["actions"][-1], event_id="later", kind="skip"))
    assert forecast(d, "2026-01-31", 0)["collections"] == []


def test_weekly_candidates_require_verified_history_and_do_not_duplicate_obligations():
    d = book()
    d["statements"] = []
    d["bank"] = []
    start = date(2023, 1, 1)
    for i in range(105):
        day = start + timedelta(weeks=i)
        end = day + timedelta(days=6)
        d["bank"].extend(
            dict(
                bank_id=f"{i}{direction}",
                account="Q",
                date=str(day),
                known_at=str(day),
                amount=amount,
                direction=direction,
                component=component,
            )
            for direction, amount, component in [
                ("in", 100, "cash_sale"),
                ("out", 60, "variable_cost"),
            ]
        )
        d["statements"].append(
            dict(
                statement_id=str(i),
                account="Q",
                start_date=str(day),
                end_date=str(end),
                opening_balance=i * 40,
                closing_balance=(i + 1) * 40,
                known_at=str(end),
            )
        )
    validate_dataset(d)
    from threadpoolctl import threadpool_limits

    with threadpool_limits(1):
        bundle = select_operating(d, str(end))
    assert bundle["name"] == "seasonal" and bundle["reference_mae"] == 0
    assert select_operating(d, str(start + timedelta(weeks=30))) is None
    # Known variable obligations of 80 exceed estimated 60; do not charge 140.
    d["invoices"][0].update(
        issue_date=str(start), known_at=str(start), due_date=str(start)
    )
    d["outflows"] = [
        dict(
            date=str(end + timedelta(days=1)),
            known_at=str(end),
            category="variable_cost",
            amount=80,
            expense_id="E",
        )
    ]

    result = forecast(
        d,
        str(end),
        0,
        dict(asof=str(end), operating=bundle, weight=1, model=Tail(), anchor=Tail(),
             partial=fit_partial(pd.DataFrame(), "2024-01-01", prior=None)),
        include_operating=True,
    )
    assert result["weeks"][0]["cash_out"] == 80 and result["weeks"][0]["cash_in"] == 100
    long = forecast(
        d,
        str(end),
        0,
        dict(asof=str(end), operating=bundle, weight=1, model=Tail(), anchor=Tail(),
             partial=fit_partial(pd.DataFrame(), "2024-01-01", prior=None)),
        include_operating=True,
        horizon_weeks=52,
    )
    assert len(long["weeks"]) == 52 and long["operating_weeks"] == 13
    assert long["weeks"][:13] == result["weeks"]
    assert long["weeks"][13]["cash_in"] == long["weeks"][13]["cash_out"] == 0
    assert long["weeks"][13]["balance"] == long["weeks"][12]["balance"]


def test_new_credit_excludes_opening_ar_and_requires_bank_links():
    from agent1.adaptive.new_credit import select_credit, build, point, receipts

    d = dict(invoices=[], payments=[], bank=[], statements=[], outflows=[])
    start = date(2023, 1, 1)
    for i in range(108):
        day = start + timedelta(weeks=i)
        end = day + timedelta(days=6)
        for j in range(2):
            iid = f"{i}_{j}"
            t = str(day)
            d["invoices"].append(
                dict(
                    invoice_id=iid,
                    customer_id=str(j),
                    issue_date=t,
                    due_date=t,
                    known_at=t,
                    amount=50.0,
                )
            )
            d["payments"].append(
                dict(
                    payment_id=iid,
                    bank_id=iid,
                    invoice_id=iid,
                    payment_date=t,
                    known_at=t,
                    amount=50.0,
                )
            )
            d["bank"].append(
                dict(
                    bank_id=iid,
                    account="Q",
                    date=t,
                    known_at=t,
                    direction="in",
                    amount=50.0,
                )
            )
        d["statements"].append(
            dict(
                statement_id=str(i),
                account="Q",
                start_date=t,
                end_date=str(end),
                opening_balance=i * 100,
                closing_balance=(i + 1) * 100,
                known_at=str(end),
            )
        )
    chosen = select_credit(d, str(end), ["Q"])
    assert chosen["audit_mae"] < 1e-8 and chosen["zero_mae"] == 100
    assert np.allclose(point(build(d, str(end), ["Q"]), chosen["kind"]), 100)
    del d["payments"][-1]["bank_id"]
    assert receipts(d, str(end - timedelta(weeks=13)), str(end), ["Q"]) is None


def test_concentrated_customer_stress_raises_joint_shortfall():
    d = book()
    d["outflows"] = [
        dict(expense_id="E1", date="2026-02-01", known_at="2026-01-30", amount=20.0, category="rent")
    ]

    bundle = dict(asof="2026-01-30", model=Half(), anchor=Half(), weight=1,
                  partial=fit_partial(pd.DataFrame(), "2024-01-01", prior=None))
    base = forecast(d, "2026-01-31", 0, bundle)
    stressed = forecast(d, "2026-01-31", 0, bundle, shared_customer_risk=True)
    assert stressed["weeks"][0]["balance"] > 0
    assert (
        stressed["weeks"][0]["below_floor_probability"]
        > base["weeks"][0]["below_floor_probability"] + 0.10
    )
    assert stressed["alerts"][0]["week"] == 1


def test_isolated_worker_reports_errors_without_saving_a_model():
    from agent1_service.workspace.train_worker import isolated_train

    with pytest.raises(ValueError, match="Chưa có hóa đơn"):
        isolated_train({"invoices": []}, "2026-01-01", False, lambda _: None)


def test_old_versions_protected_and_metadata_only(tmp_path, monkeypatch):
    app = create_app(
        tmp_path / "work", token="accountant", firm_id="A", key_dir=tmp_path / "keys"
    )
    with TestClient(app) as c:
        c.headers["Authorization"] = "Bearer accountant"
        store = app.state.store
        store.put(
            "A",
            "company_models",
            [
                dict(id=i, artifact_id=i, created_at="2020", dataset_hash="abc")
                for i in ["active", "used", "spare"]
            ],
        )
        store.put("A", "company_model_active", [dict(id="active", version="active")])
        store.put("A", "company_forecast_index", [dict(id="f", model_version="used")])
        store.put(
            "A",
            "company_dataset_active",
            [dict(id="active", version="abc", counts={"invoices": 50000})],
        )
        original = store.one

        def no_weights(firm, kind, identifier):
            assert kind not in ("company_datasets", "company_weights")
            return original(firm, kind, identifier)

        monkeypatch.setattr(store, "one", no_weights)
        assert c.get("/v1/workspace").json()["counts"]["invoices"] == 50000
        for v in ["active", "used"]:
            assert c.delete(f"/v1/models/{v}?confirm={v}").status_code == 409
        assert c.delete("/v1/models/spare?confirm=no").status_code == 422
        assert c.delete("/v1/models/spare?confirm=spare").is_success
