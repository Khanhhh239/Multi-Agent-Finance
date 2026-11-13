"""Capture real Workspace DOM/layout using an isolated TestClient store."""

import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from agent1.adaptive.data import fingerprint, SCHEMAS
from agent1.adaptive.t1_catalog import GlobalCatalog
from agent1_service.api import create_app
from agent1_service.workspace.t1_lifecycle import encode, metadata

OUT = Path(__file__).resolve().parent


def main():
    with tempfile.TemporaryDirectory(prefix="t1-ui-review-") as temp:
        directory = Path(temp)
        app = create_app(state_dir=directory / "data", key_dir=directory / "keys",
                         token="isolated-ui-review", firm_id="REVIEW")
        data = {kind: [] for kind in SCHEMAS}
        for i, amount in enumerate((100000000, 200000000, 300000000)):
            data["invoices"].append(dict(invoice_id=f"REVIEW-{i}", customer_id=f"KH-{i}",
                issue_date="2026-10-01", due_date="2026-10-31", known_at="2026-10-01", amount=amount))
        digest = fingerprint(data)
        bundle = GlobalCatalog().default_bundle("2026-11-14")
        bundle.update(dataset_hash=digest, update_asof="2026-11-14", train_n=0, validation_n=0,
                      promotion_status="kept_incumbent",
                      audit=dict(accepted=False, status="insufficient_local_windows"))
        with TestClient(app) as client:
            client.headers["Authorization"] = "Bearer isolated-ui-review"
            app.state.store.put_many("REVIEW", {
                "company_datasets": [dict(id=digest, data=data)],
                "company_dataset_active": [dict(id="active", version=digest)],
                "company_models": [metadata(bundle, "review-active", "2026-11-14T00:00:00Z")],
                "company_weights": [dict(id="review-active", **encode(bundle))],
                "company_model_active": [dict(id="active", version="review-active")],
                "company_t1_update_state": [dict(id="current", next_due="2026-12-12",
                    last_cycle_asof="2026-11-14", last_model_id="review-active")],
                "company_t1_challengers": [dict(id="review-challenger", status="pending", origin="2026-11-14",
                    baseline_version=bundle["t1_version"], challenger_version="review-pending", snapshot={})],
            })
            response = client.post("/v1/predict", json=dict(cutoff="2026-11-14", opening_balance=500000000,
                payments_complete=True, cash_floor=200000000, shap_limit=1))
            assert response.status_code == 200, response.text
            requests, errors, checks = [], [], []
            with sync_playwright() as runtime:
                browser = runtime.chromium.launch(
                    executable_path="C:/Program Files/Google/Chrome/Application/chrome.exe", headless=True)
                try:
                    page = browser.new_page(viewport=dict(width=1500, height=960))
                    page.on("pageerror", lambda error: errors.append(str(error)))

                    def proxy(route):
                        request = route.request
                        path = urlsplit(request.url)
                        requests.append(path.path)
                        result = client.request(request.method, path.path + ("?" + path.query if path.query else ""),
                            content=request.post_data_buffer,
                            headers={"Content-Type": request.headers.get("content-type", "application/json")})
                        route.fulfill(status=result.status_code, body=result.content,
                            headers={key: value for key, value in result.headers.items()
                                     if key not in ("content-length", "content-encoding")})

                    page.route("**/*", proxy)
                    page.goto("http://testserver/workspace#training")
                    expect(page.locator("#connection-state")).to_contain_text("Đã kết nối")
                    training = page.locator("#view-training").inner_text()
                    checks.append(dict(name="training_body", text=training))
                    lifecycle = client.get("/v1/t1/updates").json()
                    checks.append(dict(name="lifecycle_api", next_due=lifecycle["state"]["next_due"],
                                       pending=len(lifecycle["challengers"]),
                                       requested_by_browser="/v1/t1/updates" in requests,
                                       due_date_visible="12-12-26" in training))
                    for width in (1500, 390):
                        page.set_viewport_size(dict(width=width, height=960 if width == 1500 else 844))
                        for view in ("overview", "data", "records", "training", "forecast", "guide"):
                            page.locator("nav details").evaluate_all("items => items.forEach(item => item.open = true)")
                            page.locator(f'nav [data-view="{view}"]').click()
                            expect(page.locator(f"#view-{view}")).to_be_visible()
                            page.screenshot(path=str(OUT / f"ui_{view}_{width}.png"), full_page=True)
                            checks.append(dict(name="layout", width=width, view=view,
                                document_width=page.evaluate("document.documentElement.scrollWidth"),
                                overflow=page.evaluate("document.documentElement.scrollWidth > innerWidth")))
                        page.locator('nav [data-view="forecast"]').click()
                        page.locator(".history-menu > summary").click()
                        page.locator("#saved-plans").click()
                        page.locator("#plans-list button").first.click()
                        expect(page.locator("#forecast-output")).to_be_visible()
                        page.screenshot(path=str(OUT / f"ui_saved_forecast_{width}.png"), full_page=True)
                    checks.append(dict(name="saved_forecast_loaded", invoices=3))
                finally:
                    browser.close()
            result = dict(checks=checks, javascript_errors=errors, api_paths=sorted(set(requests)))
            (OUT / "ui_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(dict(javascript_errors=errors,
                overflows=[r for r in checks if r.get("overflow")],
                lifecycle=next(r for r in checks if r["name"] == "lifecycle_api")), ensure_ascii=False))


if __name__ == "__main__":
    main()
