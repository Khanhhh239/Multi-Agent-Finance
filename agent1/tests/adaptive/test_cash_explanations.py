"""Money conservation and counterfactual scope, not predictive-quality evidence."""

import base64
import pickle
from copy import deepcopy
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from agent1.adaptive.cash_adapter import PartialModel
from agent1.adaptive.data import fingerprint
from agent1.adaptive.methods import forecast
from agent1_service.api import create_app
from agent1_service.workspace.forecast_export import workbook_bytes
from fastapi.testclient import TestClient
from openpyxl import load_workbook

CUTOFF = "2026-02-10"


class ReceiptProfile:
    """Fixture probabilities with a genuine unresolved tail, independent of horizon."""

    def distribution(self, frame, ages, horizon=13):
        result = np.zeros((len(frame), horizon + 1))
        for i, iid in enumerate(frame.invoice_id):
            for week, fraction in {
                "A": [(1, 0.25), (3, 0.5)],
                "B": [(2, 0.5), (4, 0.5)],
            }.get(iid, []):
                result[i, min(week - 1, horizon)] += fraction
            result[i, -1] += 1 - result[i].sum()
        return result


@pytest.fixture
def book():
    return {
        "invoices": [
            {
                "invoice_id": iid,
                "customer_id": customer,
                "amount": amount,
                "issue_date": "2026-01-01",
                "due_date": "2026-02-20",
                "known_at": "2026-01-01",
            }
            for iid, customer, amount in [
                ("A", "C1", 1000),
                ("B", "C1", 600),
                ("C", "C2", 300),
                ("D", "C3", 500),
            ]
        ],
        "payments": [
            {
                "payment_id": "P",
                "invoice_id": "A",
                "amount": 200,
                "payment_date": "2026-01-20",
                "known_at": "2026-01-20",
            }
        ],
        "outflows": [
            {
                "expense_id": iid,
                "date": day,
                "known_at": "2026-02-01",
                "amount": amount,
                "category": "rent",
            }
            for iid, day, amount in [
                ("E1", "2026-02-11", 500),
                ("E2", "2026-02-24", 400),
                ("E3", "2026-03-10", 100),
            ]
        ],
        "actions": [
            {
                "event_id": "CONTACT",
                "invoice_id": "A",
                "date": "2026-02-09",
                "known_at": "2026-02-09",
                "kind": "contact",
            },
            {
                "event_id": "LOSS",
                "invoice_id": "D",
                "date": "2026-02-09",
                "known_at": "2026-02-09",
                "kind": "write_off",
            },
        ],
    }


def bundle(partial_probability=0.0):
    return {
        "asof": CUTOFF,
        "partial": PartialModel(np.full(6, partial_probability), tuple(np.array([0.5]) for _ in range(6)), tuple(np.ones(1) for _ in range(6)), "2024-01-01", {}),
        "model": ReceiptProfile(),
        "anchor": ReceiptProfile(),
        "weight": 0.35,
    }


def test_full_ledger_contributions_reconcile_to_served_path_and_do_not_follow_queue(
    book,
):
    plan = forecast(
        book, CUTOFF, 100, bundle(), horizon_weeks=4, cash_floor=50, confirmed_weeks=[3]
    )
    d = plan["cash_decomposition"]
    assert d["scope"]["open_invoices"] == 3 and d["scope"]["written_off_count"] == 1
    assert {r["invoice_id"] for r in d["invoices"]} == {"A", "B", "C"}
    assert {r["invoice_id"] for r in plan["collections"]} == {"B", "C"}
    invoices = {r["invoice_id"]: r for r in d["invoices"]}
    assert (
        invoices["A"]["outstanding"] == 800
        and invoices["A"]["received_before_cutoff"] == 200
    )
    np.testing.assert_allclose(invoices["A"]["expected_by_week"], [200, 0, 400, 0])
    np.testing.assert_allclose(invoices["B"]["expected_by_week"], [0, 300, 0, 300])
    assert (
        invoices["C"]["expected_in"] == 0
        and invoices["C"]["expected_after_horizon"] == 300
    )
    c1 = next(r for r in d["customers"] if r["customer_id"] == "C1")
    np.testing.assert_allclose(c1["expected_by_week"], [200, 300, 400, 300])
    np.testing.assert_allclose(
        [w["balance"] for w in d["weeks"]], [-200, -300, 100, 300]
    )
    np.testing.assert_allclose(
        [w["opening_balance"] for w in d["weeks"]], [100, -200, -300, 100]
    )
    for w, actual in zip(d["weeks"], plan["weeks"]):
        assert w["cash_in"] == actual["cash_in"] and w["cash_out"] == actual["cash_out"]
        assert w["balance"] == actual["balance"]
        assert w["opening_balance"] + w["net_change"] == w["balance"]
    assert d["totals"]["closing_balance"] == plan["weeks"][-1]["balance"]
    assert d["risk_focus"]["trigger"] == "expected_shortfall"
    assert d["risk_focus"]["week"] == 1 and d["risk_focus"]["expected_shortfall"] == 250
    assert d["risk_focus"]["largest_scheduled_outflows"][0]["expense_id"] == "E1"
    assert d["risk_focus"]["unknown_outflow_weeks"] == [1, 2, 4]


def test_tail_is_reported_as_residual_without_an_invented_receipt_date(book):
    plan = forecast(book, CUTOFF, 100, bundle(), horizon_weeks=4)
    d = plan["cash_decomposition"]
    assert d["totals"]["expected_after_horizon"] == 500
    assert "timing_comparison" not in d
    for invoice in d["invoices"]:
        assert invoice["expected_in"] + invoice["expected_after_horizon"] == invoice["outstanding"]
        assert invoice["receipt_explanation"]["t1_tail_probability"] >= 0


@pytest.mark.parametrize("horizon", [1, 4, 26, 52])
def test_any_horizon_and_existing_customer_delay_use_the_actual_shifted_cash(
    book, horizon
):
    plan = forecast(
        book,
        CUTOFF,
        100,
        bundle(),
        horizon_weeks=horizon,
        delay_days=14,
        delay_customer="C1",
        expense_multiplier=1.5,
    )
    d = plan["cash_decomposition"]
    np.testing.assert_allclose(
        [w["balance"] for w in d["weeks"]], [w["balance"] for w in plan["weeks"]]
    )
    assert d["totals"]["cash_out"] == sum(w["cash_out"] for w in plan["weeks"])
    assert all(r["amount"] == r["original_amount"] * 1.5 for r in d["outflows"])
    assert len(d["invoices"][0]["expected_by_week"]) == horizon
    assert sum(w["ar_in"] for w in d["weeks"][:2]) == 0


def test_future_events_do_not_change_decomposition(book):
    before = forecast(book, CUTOFF, 100, bundle(), horizon_weeks=4)[
        "cash_decomposition"
    ]
    later = deepcopy(book)
    later["payments"].append(
        {
            "payment_id": "F",
            "invoice_id": "B",
            "amount": 600,
            "payment_date": "2026-02-09",
            "known_at": "2026-02-11",
        }
    )
    later["outflows"].append(
        {
            "expense_id": "F",
            "date": "2026-02-12",
            "known_at": "2026-02-11",
            "amount": 999999,
            "category": "rent",
        }
    )
    later["actions"].append(
        {
            "event_id": "F",
            "invoice_id": "C",
            "kind": "write_off",
            "date": "2026-02-09",
            "known_at": "2026-02-11",
        }
    )
    after = forecast(later, CUTOFF, 100, bundle(), horizon_weeks=4)[
        "cash_decomposition"
    ]
    assert before == after


def test_empty_ar_still_explains_spending_and_does_not_invent_customers(book):
    settled = book["invoices"][0]
    book = {
        "invoices": [settled],
        "payments": [
            {
                "payment_id": "CLOSED",
                "invoice_id": "A",
                "amount": 1000,
                "payment_date": CUTOFF,
                "known_at": CUTOFF,
            }
        ],
        "outflows": [
            {
                "expense_id": "E",
                "date": "2026-02-11",
                "known_at": CUTOFF,
                "amount": 100,
                "category": "rent",
            }
        ],
    }
    plan = forecast(book, CUTOFF, 200, horizon_weeks=1)
    d = plan["cash_decomposition"]
    assert not d["invoices"] and not d["customers"]
    assert d["risk_focus"]["trigger"] == "minimum_expected_balance"
    assert d["totals"]["closing_balance"] == 100
    assert plan["t10"]["checks"]["accounting_reconciles"]


def test_operating_and_new_credit_stay_separate_and_variable_cost_is_not_counted_twice(
    book, monkeypatch
):
    from agent1.adaptive import new_credit, operating

    book["outflows"] = [
        {
            "expense_id": "VARIABLE-1",
            "date": "2026-02-11",
            "known_at": CUTOFF,
            "amount": 80,
            "category": "variable_cost",
        },
        {
            "expense_id": "VARIABLE-2",
            "date": "2026-02-18",
            "known_at": CUTOFF,
            "amount": 10,
            "category": "variable_cost",
        },
        {
            "expense_id": "RENT",
            "date": "2026-02-11",
            "known_at": CUTOFF,
            "amount": 100,
            "category": "rent",
        },
    ]
    monkeypatch.setattr(
        operating, "available_history", lambda *args: (np.zeros((60, 2)), 0)
    )
    monkeypatch.setattr(
        operating, "predict_candidate", lambda *args: np.tile([100, 60], (13, 1))
    )
    monkeypatch.setattr(new_credit, "build", lambda *args: object())
    monkeypatch.setattr(new_credit, "point", lambda *args: np.full(13, 20))
    trained = bundle()
    trained["operating"] = {
        "accounts": ["Q"],
        "name": "fixture",
        "model": None,
        "residuals": np.zeros((1, 13, 2)),
        "credit": {"kind": "fixture", "residuals": np.zeros((1, 13))},
    }
    plan = forecast(
        book,
        CUTOFF,
        100,
        trained,
        horizon_weeks=26,
        include_operating=True,
        expense_multiplier=1.5,
    )
    d = plan["cash_decomposition"]
    assert d["weeks"][0]["scheduled_out"] == 270
    assert d["weeks"][0]["variable_cost_topup"] == 0
    assert d["weeks"][1]["scheduled_out"] == 15
    assert d["weeks"][1]["variable_cost_topup"] == 75
    assert d["weeks"][1]["cash_out"] == 90
    assert d["totals"]["cash_sale_in"] == 1300
    assert d["totals"]["new_credit_in"] == 260
    assert (
        d["weeks"][13]["cash_sale_in"]
        == d["weeks"][13]["new_credit_in"]
        == d["weeks"][13]["variable_cost_topup"]
        == 0
    )
    for i, week in enumerate(d["weeks"]):
        assert week["cash_in"] - week["ar_in"] == (120 if i < 13 else 0)
        assert week["cash_out"] == plan["weeks"][i]["cash_out"]


def test_simulation_only_alert_is_not_misreported_as_expected_shortfall(book):
    book["outflows"] = book["outflows"][:1]
    plan = forecast(book, CUTOFF, 350, bundle(), horizon_weeks=4)
    assert plan["weeks"][0]["balance"] == 50
    assert plan["weeks"][0]["below_floor_probability"] >= 0.25
    focus = plan["cash_decomposition"]["risk_focus"]
    assert focus["trigger"] == "simulation_only" and focus["expected_shortfall"] == 0
    assert focus["first_expected_shortfall_week"] is None


def test_partial_adapter_explains_repeated_cash_instead_of_four_week_settlement():
    origin = date(2024, 1, 1)
    data = {"invoices": [], "payments": [], "outflows": []}
    for i in range(21):
        issue = origin if i < 20 else date(2026, 2, 3)
        data["invoices"].append(
            {
                "invoice_id": str(i),
                "customer_id": "C",
                "amount": 100,
                "issue_date": str(issue),
                "due_date": str(issue + timedelta(days=60)),
                "known_at": str(issue),
            }
        )
        for j, (days, amount) in enumerate(
            [(7, 20), (14, 40), (21, 40)] if i < 20 else [(7, 20)]
        ):
            when = str(issue + timedelta(days=days))
            data["payments"].append(
                {
                    "payment_id": f"{i}-{j}",
                    "invoice_id": str(i),
                    "amount": amount,
                    "payment_date": when,
                    "known_at": when,
                }
            )
    plan = forecast(data, CUTOFF, 0, bundle(1.0), horizon_weeks=4)
    assert plan["partial_cash_supported"] == 1
    invoice = plan["cash_decomposition"]["invoices"][0]
    assert invoice["receipt_basis"] == "settlement_partial_adapter"
    np.testing.assert_allclose(invoice["expected_by_week"], [40, 20, 10, 5])
    assert invoice["expected_in"] == 75
    assert plan["collections"][0]["payment_probability_4w"] == 0


def test_export_contains_full_contributions_scenarios_and_legacy_support(book):
    plan = forecast(book, CUTOFF, 100, bundle(), horizon_weeks=4)
    wb = load_workbook(BytesIO(workbook_bytes(plan, "TEST")))
    assert wb["Thu theo hóa đơn"].max_row == 4
    assert wb["Thu theo khách"].max_row == 3
    assert wb["Phân rã từng tuần"]["J5"].value == 300
    assert wb["Bằng chứng partial theo tuần"].max_row == 13
    del plan["cash_decomposition"]
    del plan["t5"]
    del plan["t10"]
    legacy = load_workbook(BytesIO(workbook_bytes(plan, "TEST")))
    assert legacy.sheetnames == [
        "Kết quả dự báo",
        "Kế hoạch từng tuần",
        "Khoản cần chú ý",
    ]


def test_api_persists_provenance_and_uses_saved_values_on_get_and_export(
    tmp_path, book
):
    app = create_app(
        state_dir=tmp_path / "data",
        key_dir=tmp_path / "keys",
        token="cash-test",
        firm_id="TEST",
    )
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer cash-test"
        digest = fingerprint(book)
        app.state.store.put("TEST", "company_datasets", [{"id": digest, "data": book}])
        app.state.store.put(
            "TEST", "company_dataset_active", [{"id": "active", "version": digest}]
        )
        app.state.store.put(
            "TEST",
            "company_weights",
            [
                {
                    "id": "W",
                    "artifact": base64.b64encode(pickle.dumps(bundle())).decode(),
                }
            ],
        )
        app.state.store.put(
            "TEST",
            "company_models",
            [{"id": "CASH-MODEL", "artifact_id": "W", "dataset_hash": digest}],
        )
        app.state.store.put(
            "TEST", "company_model_active", [{"id": "active", "version": "CASH-MODEL"}]
        )
        response = client.post(
            "/v1/predict",
            json={
                "cutoff": CUTOFF,
                "opening_balance": 100,
                "payments_complete": True,
                "horizon_weeks": 4,
            },
        )
        assert response.status_code == 200, response.text
        plan = response.json()
        d = plan["cash_decomposition"]
        assert d["dataset_hash"] == digest and d["model_version"].startswith("global:")
        assert plan["company_bundle_version"] == "CASH-MODEL"
        assert d["cutoff"] == CUTOFF
        assert d["model_asof"] <= CUTOFF
        app.state.store.put(
            "TEST", "company_dataset_active", [{"id": "active", "version": "CHANGED"}]
        )
        app.state.store.put(
            "TEST", "company_model_active", [{"id": "active", "version": "CHANGED"}]
        )
        assert (
            client.get("/v1/forecasts/" + plan["id"]).json()["cash_decomposition"] == d
        )
        exported = client.get("/v1/forecasts/" + plan["id"] + "/xlsx")
        assert exported.status_code == 200
        wb = load_workbook(BytesIO(exported.content))
        assert "Bằng chứng partial theo tuần" in wb.sheetnames


def test_browser_cash_breakdown_filters_groups_and_compares_on_desktop_and_mobile(
    tmp_path, book, browser_runtime, client_proxy,
):
    playwright, chrome = browser_runtime
    app = create_app(
        state_dir=tmp_path / "data",
        key_dir=tmp_path / "keys",
        token="cash-browser-test",
        firm_id="TEST",
    )
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer cash-browser-test"
        digest = fingerprint(book)
        app.state.store.put("TEST", "company_datasets", [{"id": digest, "data": book}])
        app.state.store.put(
            "TEST", "company_dataset_active", [{"id": "active", "version": digest}]
        )
        response = client.post(
            "/v1/predict",
            json={
                "cutoff": CUTOFF,
                "opening_balance": 100,
                "payments_complete": True,
                "horizon_weeks": 4,
            },
        )
        assert response.status_code == 200, response.text
        output = (
            Path(__file__).resolve().parents[2] / "outputs/ui_checks/cash_decomposition"
        )
        output.mkdir(parents=True, exist_ok=True)

        with playwright.sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(chrome), headless=True)
            try:
                page = browser.new_page(viewport={"width": 1500, "height": 1000})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/*", client_proxy(client))
                page.goto("http://testserver/workspace#forecast")
                playwright.expect(page.locator("#connection-state")).to_contain_text(
                    "Đã kết nối"
                )
                page.locator(".history-menu > summary").click()
                page.locator("#saved-plans").click()
                page.locator("#plans-list button").first.click()
                panel = page.locator("#cash-decomposition")
                playwright.expect(panel).to_contain_text("T1 + adapter partial")
                playwright.expect(panel).to_contain_text("Chạy lại T6")
                playwright.expect(panel).to_contain_text("không giới hạn 30")
                contributions = panel.locator(".table-scroll").first
                playwright.expect(contributions.locator("tbody tr")).to_have_count(3)
                page.get_by_label("Nhóm đóng góp dự thu").select_option("customers")
                playwright.expect(contributions.locator("tbody tr")).to_have_count(2)
                page.get_by_label("Nhóm đóng góp dự thu").select_option("invoices")
                page.get_by_label("Tìm khoản dự thu").fill("A")
                playwright.expect(contributions.locator("tbody tr")).to_have_count(1)
                playwright.expect(contributions).to_contain_text("800")
                page.get_by_label("Tìm khoản dự thu").fill("")
                page.get_by_label("Kỳ phân rã dòng tiền").select_option("1")
                panel.get_by_text(
                    "Lịch chi đã biết và số tiền sau kịch bản", exact=True
                ).click()
                expenses = panel.locator("details").first
                playwright.expect(expenses).to_contain_text("E1")
                assert "E2" not in expenses.inner_text()
                panel.get_by_text("Vì sao dự thu số tiền này? · T1 + adapter partial", exact=True).click()
                page.get_by_label("Hóa đơn giải thích partial").select_option("A")
                playwright.expect(panel).to_contain_text("Dư nợ tại ngày chốt 800 VND")
                panel.get_by_text("Nếu khách trả chậm hoặc dời khoản chi? · Chạy lại T6", exact=True).click()
                page.get_by_label("Khách trả chậm", exact=True).select_option("C1")
                page.get_by_label("Số tuần trả chậm thêm").fill("2")
                page.get_by_role("button", name="So sánh với forecast đã lưu", exact=True).click()
                playwright.expect(panel).to_contain_text("Xác suất thiếu tiền ít nhất một tuần")
                playwright.expect(panel).to_contain_text("Δ P50")
                for width in (1500, 390):
                    page.set_viewport_size({"width": width, "height": 1000})
                    page.wait_for_function(
                        "() => document.documentElement.scrollWidth <= innerWidth"
                    )
                    panel.screenshot(path=str(output / f"cash_{width}.png"))
                    assert panel.bounding_box()["width"] <= width
                assert not errors, errors
            finally:
                browser.close()
