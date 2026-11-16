"""Business wording, truthful status messages and usable touch targets."""
import time
from pathlib import Path

import pytest

from test_t0_t9_uat_pack import client, core
from test_workspace_usability_fixes import page


@pytest.mark.parametrize("decision, expected", [
    ({"status":"kept_incumbent","candidate_update_audit":{"status":"insufficient_local_windows"}},
     "Chưa đủ lịch sử để so sánh. Tiếp tục dùng phiên bản hiện có."),
    ({"status":"kept_incumbent","audit":{"status":"scored"}},
     "Chưa có bằng chứng phương án mới tốt hơn. Tiếp tục dùng phiên bản hiện có."),
    ({"status":"pending_prospective_audit"},
     "Tiếp tục dùng phiên bản hiện có. Phương án mới đang chờ đủ dữ liệu thực tế để so sánh."),
    ({"status":"accepted_historical_audit"},
     "Đã chọn phiên bản mới sau khi kiểm tra trên lịch sử."),
    ({"status":"accepted_prospective_audit"},
     "Đã chọn phiên bản mới sau khi đối chiếu dự báo đã lưu với thực tế."),
    ({"status":"not_due"},
     "Chưa đến lịch cập nhật tiếp theo. Bạn vẫn có thể lập dự báo bằng phiên bản đang dùng."),
    ({"status":"unknown"},
     "Đã lưu kết quả kiểm tra. Xem chi tiết phiên bản để biết bước tiếp theo."),
])
def test_training_job_message_matches_actual_decision(client, monkeypatch, decision, expected):
    from agent1_service.workspace import t1_lifecycle

    monkeypatch.setattr(t1_lifecycle, "run_cycle", lambda *a, **kw: decision)
    response = client.post("/v1/training", json={"asof":"2026-11-11","payments_complete":True})
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    deadline = time.monotonic() + 3
    while True:
        job = next(j for j in client.get("/v1/workspace").json()["jobs"] if j["id"] == job_id)
        if job["status"] in {"completed", "failed"} or time.monotonic() >= deadline:
            break
        time.sleep(0.01)
    assert job["status"] == "completed", job
    assert job["message"] == expected
    assert job["decision"] == decision


def screenshot(page, name):
    folder = Path(__file__).resolve().parents[2] / "outputs/ui_checks/ux_polish"
    folder.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(folder / (name + ".png")))


@pytest.mark.parametrize("width", [320, 390, 844])
def test_browser_mobile_targets_and_plain_language_preserve_evidence(client, page, width):
    core(client)
    response = client.post("/v1/predict", json={"cutoff":"2026-11-11","opening_balance":100000000,
        "cash_floor":200000000,"horizon_weeks":4,"payments_complete":True,"simulation_paths":100,"shap_limit":0})
    assert response.status_code == 200, response.text
    plan = response.json()
    page, runtime = page
    page.set_viewport_size({"width":width,"height":1000})
    page.locator(".history-menu > summary").click()
    page.locator("#saved-plans").click()
    page.locator("#plans-list button").first.click()
    runtime.expect(page.locator("#forecast-output")).to_be_visible()
    assert page.locator("#notice").evaluate("e => getComputedStyle(e).position") == "static"
    for selector in ["#refresh", "#export-forecast", ".history-menu > summary", "#forecast-complete", ".field-help > summary", "#collections-table button"]:
        target = page.locator(selector).first
        if selector == "#forecast-complete":
            box = target.locator("..").bounding_box()
        else:
            box = target.bounding_box()
        assert box["height"] >= 44, (width, selector, box)
        assert box["width"] >= 44, (width, selector, box)
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
    screenshot(page, f"forecast_{width}")
    title = page.get_by_text("Vì sao dự kiến thu được tiền?", exact=True)
    title.click()
    select = page.get_by_label("Hóa đơn cần xem cách dự thu")
    runtime.expect(select).to_be_visible()
    evidence = select.locator('xpath=ancestor::details[1]')
    visible_text = evidence.inner_text()
    assert "trả từng phần" in visible_text
    assert "SHAP" not in visible_text and "Adapter" not in visible_text
    title.scroll_into_view_if_needed()
    screenshot(page, f"receipts_{width}")
    evidence.get_by_text("Thông tin kỹ thuật và nguồn của kế hoạch", exact=True).click()
    runtime.expect(evidence).to_contain_text(plan["t10"]["identity"]["t1_version"])
    runtime.expect(evidence.get_by_role("button", name="Tải dữ liệu đối chiếu của kế hoạch")).to_be_visible()
    assert client.get("/v1/forecasts/" + plan["id"]).json() == plan
    if width == 390:
        scenario_title = page.get_by_text("Nếu khách trả chậm hoặc dời khoản chi?", exact=True)
        scenario_title.click()
        page.get_by_label("Số tuần trả chậm thêm").fill("1")
        with page.expect_response("**/scenarios") as compared:
            page.get_by_role("button", name="So sánh với kế hoạch đã lưu", exact=True).click()
        assert compared.value.status == 200, compared.value.text()
        result = page.get_by_label("Giả định của kết quả kịch bản").locator("..")
        runtime.expect(result).to_contain_text("Khả năng thiếu tiền ít nhất một tuần")
        assert "MC thô" not in result.inner_text()
        assert result.get_by_role("columnheader").count() == 4
        result.scroll_into_view_if_needed()
        screenshot(page, "scenario_simple_390")
        result.get_by_text("Cách tính và số liệu so sánh chi tiết", exact=True).click()
        assert "MC thô" in result.inner_text()
        assert client.get("/v1/forecasts/" + plan["id"]).json() == plan
    page.locator('nav .nav-more > summary').click()
    page.locator('nav [data-view="guide"]').click()
    guide = page.locator("#view-guide")
    assert "pit_withholding" not in guide.inner_text()
    guide.get_by_text("Hợp đồng, trả từng phần và khoản chi đặc biệt", exact=True).click()
    assert "pit_withholding" in guide.inner_text()
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")


def test_browser_legacy_job_status_is_consistent_and_does_not_follow_navigation(client, page):
    payload = client.get("/v1/workspace").json()
    decision = {"status":"kept_incumbent","candidate_update_audit":{"status":"insufficient_local_windows"}}
    payload["jobs"] = [{"id":"SYNTHETIC-OLD-JOB","status":"completed","message":"Đã chọn phiên bản mới; ứng viên đang chờ", "decision":decision}]
    payload["t1_updates"].update(runs=[decision], pending_count=0, challengers=[])
    payload["versions"] = [{"id":"SYNTHETIC-GLOBAL","update_asof":"2026-11-11","asof":"2024-07-01",
        "t1_parameter_asof":"2024-07-01","partial_fitted_through":"2024-06-30","promotion_status":"kept_incumbent",
        "candidate_update_audit":{"status":"insufficient_local_windows"},"train_n":0,"validation_n":0}]
    payload["active_version"] = "SYNTHETIC-GLOBAL"
    page, runtime = page
    page.route("**/v1/workspace", lambda route: route.fulfill(json=payload))
    page.locator('nav .nav-more > summary').click()
    page.locator('nav [data-view="training"]').click()
    page.locator("#refresh").click()
    message = "Chưa đủ lịch sử để so sánh. Tiếp tục dùng phiên bản hiện có."
    for selector in ["#notice", "#jobs", "#t1-updates", "#versions-list"]:
        runtime.expect(page.locator(selector)).to_contain_text(message)
    assert "ứng viên đang chờ" not in page.locator("#jobs").inner_text()
    assert "snapshot" not in page.locator("#versions-list").inner_text()
    runtime.expect(page.locator(".version-evidence")).not_to_have_attribute("open", "")
    screenshot(page, "consistent_training_status")
    page.locator(".version-evidence > summary").click()
    assert "Ước tính trả từng phần: 30-06-24" in page.locator("#versions-list").inner_text()
    page.locator('nav [data-view="forecast"]').click()
    runtime.expect(page.locator("#notice")).to_be_hidden()
    page.locator("#refresh").click()
    runtime.expect(page.locator("#notice")).to_be_hidden()
