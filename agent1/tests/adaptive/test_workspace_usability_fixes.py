"""Regressions for strict forecast inputs and the four reported usability defects."""
import csv
from pathlib import Path

import pytest

from test_t0_t9_uat_pack import client, core, PACK


def capture(page, name):
    output = Path(__file__).resolve().parents[2] / "outputs/ui_checks/usability_fixes"
    output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output / (name + ".png")))


@pytest.mark.parametrize("value", [True, False])
@pytest.mark.parametrize("field", [
    "opening_balance", "cash_floor", "expense_multiplier", "horizon_weeks",
    "delay_days", "simulation_paths", "shap_limit", "simulation_seed", "confirmed_weeks",
])
def test_prediction_rejects_boolean_numbers_without_saving(client, monkeypatch, field, value):
    from agent1_service.workspace import t1_lifecycle

    monkeypatch.setattr(t1_lifecycle, "load_active", lambda *a: pytest.fail("Invalid request must not load a model"))
    body = dict(cutoff="2026-11-11", opening_balance=100000000, payments_complete=True)
    body[field] = [value] if field == "confirmed_weeks" else value
    before = client.get("/v1/workspace").json()["dataset_hash"]
    response = client.post("/v1/predict", json=body)
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"][:2] == ["body", field]
    assert client.get("/v1/forecasts").json() == []
    assert client.get("/v1/workspace").json()["dataset_hash"] == before


@pytest.fixture
def page(client, browser_runtime, serve_app):
    runtime, chrome = browser_runtime
    with serve_app(client.app) as origin, runtime.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(chrome), headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.goto(origin + "/workspace#forecast")
        page.locator("#connect-top").click()
        page.locator("#token-input").fill("uat-fixture-test")
        page.locator("#connect-form button[type=submit]").click()
        runtime.expect(page.locator("#connection-state")).to_contain_text("Đã kết nối")
        try:
            yield page, runtime
        finally:
            browser.close()


def test_browser_reference_error_preview_does_not_call_rows_valid(client, page):
    core(client)
    page, runtime = page
    page.locator('nav [data-view="data"]').click()
    page.locator("#table-kind").select_option("payments")
    page.locator("#date-format").select_option("%Y-%m-%d")
    page.locator("#number-format").select_option("plain")
    page.locator("#imported-by").fill("Regression reviewer")
    page.locator("#import-file").set_input_files(str(PACK / "negative/N08_overallocated__payments.csv"))
    page.locator("#import-form button[type=submit]").click()
    runtime.expect(page.locator("#preview-title")).to_contain_text("Chưa thể lưu · 1 lỗi cần sửa")
    runtime.expect(page.locator("#preview-title")).not_to_contain_text("dòng hợp lệ")
    runtime.expect(page.locator("#commit-import")).to_be_disabled()
    page.locator("#preview-panel").scroll_into_view_if_needed()
    capture(page, "preview_reference_error")


def test_browser_invalid_weeks_identify_field_and_recover_after_edit(page):
    page, runtime = page
    page.locator("#forecast-cutoff").fill("11-11-26")
    page.locator("#opening-balance").fill("100000000")
    page.locator("#horizon-weeks").fill("4")
    page.locator("#forecast-form > details > summary").click()
    page.locator("#forecast-complete").check()
    requests = []
    page.on("request", lambda r: requests.append(r) if r.url.endswith("/v1/predict") else None)
    field = page.locator("#confirmed-weeks")
    for invalid in ["abc", "1,0", "1,5", "1.5"]:
        field.fill(invalid)
        page.locator("#forecast-submit").click()
        runtime.expect(field).to_be_focused()
        runtime.expect(field).to_have_attribute("aria-invalid", "true")
        runtime.expect(page.locator("#confirmed-weeks-error")).to_contain_text("từ 1 đến 4")
        runtime.expect(page.locator("#notice")).not_to_contain_text("Input should")
    assert not requests
    capture(page, "weeks_field_guidance")
    field.fill("1,2")
    runtime.expect(page.locator("#confirmed-weeks-error")).to_have_count(0)
    assert field.get_attribute("aria-invalid") is None
    # Also cover server-side errors instead of only client-side validation.
    page.route("**/v1/predict", lambda route: route.fulfill(status=422, json={"detail": [
        {"loc": ["body", "confirmed_weeks", 0], "type": "int_type", "msg": "Input should be a valid integer"},
    ]}))
    page.locator("#forecast-submit").click()
    runtime.expect(page.locator("#confirmed-weeks-error")).to_contain_text("ví dụ 1,2,3")
    runtime.expect(field).to_be_focused()


@pytest.mark.parametrize("width", [1500, 390])
def test_browser_saved_plan_restores_inputs_and_requires_fresh_confirmation(client, page, width):
    core(client)
    customer = next(csv.DictReader((PACK / "01_core/01_invoices.csv").read_text(encoding="utf-8-sig").splitlines()))["customer_id"]
    body = dict(cutoff="2026-11-11", opening_balance=250000000, cash_floor=100000000,
                horizon_weeks=4, confirmed_weeks=[1, 3], payments_complete=True,
                delay_days=8, expense_multiplier=1.125, delay_customer=customer,
                shared_customer_risk=True, simulation_paths=100, shap_limit=0)
    response = client.post("/v1/predict", json=body)
    assert response.status_code == 200, response.text
    saved = response.json()
    page, runtime = page
    page.set_viewport_size({"width": width, "height": 1000})
    page.locator("#opening-balance").fill("42")
    page.locator("#forecast-complete").check()
    page.locator(".history-menu > summary").click()
    page.locator("#saved-plans").click()
    page.locator("#plans-list button").first.click()
    for field, value in {
        "forecast-cutoff": "11-11-26", "opening-balance": "250000000", "cash-floor": "100000000",
        "horizon-weeks": "4", "confirmed-weeks": "1,3", "scenario-preset": "custom",
        "delay-days": "8", "expense-change": "12.5", "delay-customer": customer,
    }.items():
        runtime.expect(page.locator("#" + field)).to_have_value(value)
    runtime.expect(page.locator("#common-risk")).to_be_checked()
    runtime.expect(page.locator("#forecast-comparison")).to_contain_text("Chi 112,5% kế hoạch")
    runtime.expect(page.locator("#include-operating")).not_to_be_checked()
    runtime.expect(page.locator("#forecast-complete")).not_to_be_checked()
    runtime.expect(page.locator("#forecast-input-context")).to_contain_text("Đã điền tham số từ kế hoạch đã lưu")
    page.locator("#forecast-input-context").scroll_into_view_if_needed()
    capture(page, f"saved_inputs_{width}")
    page.locator("#forecast-complete").check()
    with page.expect_response("**/v1/predict") as prediction:
        page.locator("#forecast-submit").click()
    assert prediction.value.status == 200, prediction.value.text()
    sent = prediction.value.request.post_data_json
    for key in ["cutoff", "opening_balance", "cash_floor", "horizon_weeks", "confirmed_weeks", "delay_days",
                "expense_multiplier", "delay_customer", "shared_customer_risk"]:
        assert sent[key] == body[key], key
    assert client.get("/v1/forecasts/" + saved["id"]).json() == saved
    runtime.expect(page.locator("#forecast-input-context")).to_be_hidden()
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")


def test_browser_edit_pending_bank_opens_visible_correction_and_reuses_loaded_record(client, page):
    core(client)
    before = client.get("/v1/workspace").json()["dataset_hash"]
    bank_id = client.get("/v1/reconciliation").json()["pending"][0]["bank_id"]
    page, runtime = page
    page.locator('nav [data-view="data"]').click()
    page.locator("#load-pending").click()
    row = page.locator("#pending-rows tbody tr").filter(has_text=bank_id)
    edit = row.get_by_role("button", name="Sửa dòng sao kê", exact=True)
    edit.click()
    editor = page.locator("#source-correction-editors fieldset")
    runtime.expect(editor).to_have_count(1)
    flow = editor.locator("label").filter(has_text="Loại dòng tiền").locator("input")
    runtime.expect(flow).to_be_focused()
    runtime.expect(flow).to_be_in_viewport()
    flow.fill("other_external")
    edit.click()
    runtime.expect(editor).to_have_count(1)
    runtime.expect(flow).to_be_focused()
    runtime.expect(flow).to_be_in_viewport()
    runtime.expect(flow).to_have_value("other_external")
    capture(page, "pending_bank_correction_visible")
    assert client.get("/v1/workspace").json()["dataset_hash"] == before


def test_browser_outside_ar_history_is_collapsed_and_paginated_without_hiding_review(client, page):
    core(client)
    before = client.get("/v1/workspace").json()["dataset_hash"]
    payload = client.get("/v1/reconciliation").json()
    case = dict(bank_id="NEEDS-REVIEW", date="2026-11-18", account="DP-VND01",
                available_minor=10000000, status="auto", reason="unique_transport",
                reason_text="Đối chiếu chứng từ", memo="Thanh toán hóa đơn",
                candidates=[], allocations=[dict(invoice_id="DEMO-INVOICE", amount_minor=10000000)])
    outside = [dict(case, bank_id=f"OUT-{i:04}", reason="non_ar_bank_movement", allocations=[])
               for i in range(625)]
    payload["proposal"] = dict(id="DISPLAY-ONLY", cutoff="2026-11-18", stale=False,
                               cases=outside + [case])
    page, runtime = page
    page.route("**/v1/reconciliation", lambda route: route.fulfill(json=payload))
    page.locator('nav [data-view="data"]').click()
    page.locator("#load-pending").click()
    cases = page.locator("#reconciliation-cases")
    runtime.expect(cases.get_by_role("button", name="Duyệt phân bổ", exact=True)).to_have_count(1)
    group = page.locator("#reconciliation-outside-ar")
    runtime.expect(group.locator("summary")).to_contain_text("625 giao dịch")
    assert group.get_attribute("open") is None
    runtime.expect(group.locator("tbody tr")).to_have_count(0)
    group.locator("summary").click()
    runtime.expect(group.locator("tbody tr")).to_have_count(25)
    runtime.expect(group.get_by_role("button", name="Trang trước", exact=True)).to_be_disabled()
    group.get_by_role("button", name="Trang sau", exact=True).click()
    runtime.expect(group).to_contain_text("Dòng 26–50 / 625")
    runtime.expect(group.locator("tbody tr").first).to_contain_text("OUT-0025")
    capture(page, "outside_ar_compact_lookup")
    group.locator("summary").click()
    runtime.expect(group.locator("table")).to_be_hidden()
    assert client.get("/v1/workspace").json()["dataset_hash"] == before
