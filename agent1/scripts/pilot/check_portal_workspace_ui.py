"""Read-only UI checks against a running local Portal; requires Playwright and Chrome.

No files are imported and no accounting decisions are changed. Authentication
uses Portal's normal embedded/new-tab handoff in an isolated browser context.
"""

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


def check(output):
    output.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path="C:/Program Files/Google/Chrome/Application/chrome.exe", headless=True)
        context = browser.new_context(viewport=dict(width=1500, height=960), device_scale_factor=1)
        context.on("page", lambda page: page.on("pageerror", lambda error: errors.append(str(error))))
        page = context.new_page()
        try:
            page.goto("http://localhost:8800/#agent1", wait_until="domcontentloaded")
            frame = page.frame_locator("#agent-frame")
            expect(frame.locator("#connection-state")).to_contain_text("Đã kết nối", timeout=30000)
            checks.append("Agent 1 tự kết nối từ Portal localhost:8800")
            page.screenshot(path=str(output / "01_portal_agent1.png"), full_page=True)
            frame.locator('[data-view="records"]').click()
            expect(frame.locator("#records-status-text")).to_contain_text("bản ghi phù hợp", timeout=15000)
            page.screenshot(path=str(output / "02_record_catalog.png"), full_page=True)
            checks.append("Sổ dữ liệu hiện trong khung Portal và tải được danh sách")
            frame.locator("#records-kind").select_option("bank")
            frame.locator("#records-query").fill("B_EXISTING")
            frame.locator('#records-filter button[type="submit"]').click()
            expect(frame.locator("#records-table tbody tr")).to_have_count(1)
            frame.locator("#records-table").get_by_role("button", name="B_EXISTING", exact=True).click()
            expect(frame.locator("#record-detail-title")).to_contain_text("B_EXISTING")
            expect(frame.locator("#record-detail-content")).to_contain_text("I_EXISTING")
            page.screenshot(path=str(output / "03_record_links.png"), full_page=True)
            checks.append("Lọc sao kê B_EXISTING và mở hóa đơn/thanh toán liên quan")
            page.reload(wait_until="domcontentloaded")
            frame = page.frame_locator("#agent-frame")
            expect(frame.locator("#connection-state")).to_contain_text("Đã kết nối", timeout=30000)
            expect(frame.locator("#connect-dialog")).not_to_be_visible()
            checks.append("F5 Portal vẫn tự kết nối Agent 1")
            with page.expect_popup() as popup:
                page.locator("#agent-newtab").click()
            standalone = popup.value
            expect(standalone.locator("#connection-state")).to_contain_text("Đã kết nối", timeout=30000)
            dataset_before = standalone.evaluate("""async () => {
                const response = await fetch('/v1/workspace');
                if (!response.ok) throw new Error('Không đọc được phiên bản dữ liệu');
                const {dataset_hash, counts} = await response.json();
                return {dataset_hash, counts};
            }""")
            standalone.locator('[data-view="records"]').click()
            expect(standalone.locator("#records-status-text")).to_contain_text("bản ghi phù hợp")
            standalone.reload(wait_until="domcontentloaded")
            expect(standalone.locator("#connection-state")).to_contain_text("Đã kết nối", timeout=15000)
            expect(standalone.locator("#connect-dialog")).not_to_be_visible()
            expect(standalone.locator("#records-status-text")).to_contain_text("bản ghi phù hợp")
            standalone.screenshot(path=str(output / "04_standalone_after_f5.png"), full_page=True)
            checks.append("Mở tab riêng từ Portal; F5 giữ phiên và tải lại Sổ dữ liệu")
            standalone.set_viewport_size(dict(width=390, height=844))
            standalone.screenshot(path=str(output / "05_mobile_catalog.png"), full_page=True)
            assert standalone.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Trang tràn ngang trên mobile"
            checks.append("Màn 390px không tràn ngang toàn trang")
            standalone.set_viewport_size(dict(width=1500, height=960))
            standalone.locator('nav [data-view="data"]').click()
            toolbar = standalone.locator(".reconciliation-toolbar")
            toolbar.scroll_into_view_if_needed()
            boxes = [standalone.locator(selector).bounding_box() for selector in
                     ("#reconciliation-reviewer", "#run-reconciliation", "#load-pending")]
            assert all(boxes), "Không tìm thấy thanh đối soát"
            bottoms = [box["y"] + box["height"] for box in boxes]
            assert max(bottoms) - min(bottoms) < 3, "Các nút đối soát chưa thẳng hàng với ô nhập"
            toolbar.screenshot(path=str(output / "06_reconciliation_toolbar.png"))
            checks.append("Ô người xử lý và hai nút đối soát thẳng hàng")
            standalone.locator("#load-pending").click()
            expect(standalone.locator("#reconciliation-status")).not_to_have_text("")
            for width in (1500, 390):
                standalone.set_viewport_size(dict(width=width, height=960 if width == 1500 else 844))
                for view in ("overview", "data", "records", "training", "forecast", "guide"):
                    standalone.locator("nav details").evaluate_all("items => items.forEach(item => item.open = true)")
                    standalone.locator(f'nav [data-view="{view}"]').click()
                    expect(standalone.locator(f"#view-{view}")).to_be_visible()
                    assert standalone.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), f"Trang {view} tràn ngang ở {width}px"
                    standalone.screenshot(path=str(output / f"view_{view}_{width}.png"), full_page=True)
            checks.append("Cả sáu trang hiển thị ở 1500px và 390px, không tràn ngang toàn trang")
            dataset_after = standalone.evaluate("""async () => {
                const response = await fetch('/v1/workspace');
                const {dataset_hash, counts} = await response.json();
                return {dataset_hash, counts};
            }""")
            assert dataset_before == dataset_after, "Dữ liệu doanh nghiệp thay đổi trong lúc kiểm tra"
            checks.append("Mã phiên bản và số lượng bản ghi giữ nguyên sau kiểm tra UI")
            standalone.locator("#logout").click()
            expect(standalone.locator("#logout")).not_to_be_visible(timeout=15000)
            expect(standalone.locator("#connect-top")).to_be_visible()
            checks.append("Ngắt kết nối hủy phiên của trình duyệt kiểm thử")
            assert not errors, errors
            checks.append("Không có lỗi JavaScript trong các trang đã kiểm tra")
        except Exception:
            page.screenshot(path=str(output / "failure.png"), full_page=True)
            raise
        finally:
            browser.close()
    result = dict(portal="http://localhost:8800", checks=checks, javascript_errors=errors,
                  dataset_before=dataset_before, dataset_after=dataset_after)
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("agent1/outputs/ui_checks/20261111"))
    check(parser.parse_args().output)
