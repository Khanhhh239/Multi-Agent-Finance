"""Review 5–8: registry retention, serving labels and visible update lifecycle."""
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from agent1.adaptive.bundle_metadata import serving_mode
from agent1.adaptive.data import fingerprint
from agent1_service.api import create_app
from agent1_service.workspace import t1_lifecycle as life
from test_t1_periodic import catalog, invoice, set_time


@pytest.fixture
def workspace(tmp_path, catalog, monkeypatch):
    monkeypatch.setenv("AGENT1_T1_GLOBAL_CATALOG", str(catalog.path))
    set_time(monkeypatch, "2026-11-14T12:00:00")
    app = create_app(state_dir=tmp_path/"state", key_dir=tmp_path/"keys", token="review", firm_id="A")
    d = dict(invoices=[invoice(1, "2026-10-01")], payments=[], outflows=[])
    bundle = catalog.default_bundle("2026-11-14")
    bundle["dataset_hash"] = fingerprint(d)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer review"
        store = app.state.store
        store.put_many("A", {"company_datasets": [dict(id="D", data=d)],
                              "company_dataset_active": [dict(id="active", version="D")],
                              "company_models": [life.metadata(bundle, n, "2026-11-14T00:00:00Z")
                                                 for n in ("old", "new", "unused")],
                              "company_weights": [dict(id=n, **life.encode(bundle)) for n in ("old", "new", "unused")],
                              "company_model_active": [dict(id="active", version="old")]})
        yield client, store, bundle


def predict(client):
    response = client.post("/v1/predict", json=dict(cutoff="2026-11-14", opening_balance=100,
                                                  payments_complete=True, shap_limit=0))
    assert response.status_code == 200, response.text
    return response.json()


def test_saved_forecast_keeps_exact_registry_and_unused_duplicate_can_be_deleted(workspace):
    client, store, _ = workspace
    plan = predict(client)
    assert plan["company_bundle_version"] == "old"
    assert store.one("A", "company_forecast_index", plan["id"])["company_bundle_version"] == "old"
    assert plan["model_version"].startswith("global:")
    assert client.post("/v1/models/new/activate").status_code == 200
    assert client.delete("/v1/models/old?confirm=old").status_code == 409
    assert store.one("A", "company_models", "old") and store.one("A", "company_weights", "old")
    # Identical parameter hashes do not imply this unused registry was used.
    assert client.delete("/v1/models/unused?confirm=unused").status_code == 200
    assert client.get("/v1/forecasts/"+plan["id"]).json()["company_bundle_version"] == "old"


@pytest.mark.parametrize("source", ["payload", "unindexed_payload", "registry_id", "bundle_hash", "replay_id", "replay_hash"])
def test_legacy_saved_forecasts_protect_registry_from_available_provenance(workspace, source):
    client, store, bundle = workspace
    assert client.post("/v1/models/new/activate").status_code == 200
    index = dict(id="F", model_version=bundle["t1_version"])
    payload = dict(id="F", model_version=bundle["t1_version"])
    if source in ("payload", "unindexed_payload"):
        payload["company_bundle_version"] = "old"
    elif source == "registry_id":
        index["model_version"] = payload["model_version"] = "old"
    if source not in ("unindexed_payload", "replay_id", "replay_hash"):
        store.put("A", "company_forecast_index", [index])
    if source not in ("replay_id", "replay_hash"):
        store.put("A", "company_predictions", [payload])
    else:
        replay = dict(id="F", company_bundle_version="old") if source == "replay_id" else dict(
            id="F", identity=dict(t1_version=bundle["t1_version"]))
        store.put("A", "company_forecast_replays", [replay])
    assert client.delete("/v1/models/old?confirm=old").status_code == 409
    assert store.one("A", "company_weights", "old")


def test_other_tenant_and_explicit_global_forecast_do_not_pin_unused_registry(workspace):
    client, store, bundle = workspace
    assert client.post("/v1/models/new/activate").status_code == 200
    store.put("B", "company_predictions", [dict(id="B", company_bundle_version="old")])
    store.put("A", "company_forecast_index", [dict(id="GLOBAL", company_bundle_version=None,
                                                  model_version=bundle["t1_version"])])
    assert client.delete("/v1/models/old?confirm=old").status_code == 200
    assert store.one("B", "company_predictions", "B")["company_bundle_version"] == "old"


def test_model_deleted_during_inference_prevents_an_orphan_forecast_commit(workspace, monkeypatch):
    from agent1.adaptive import t10_explanations
    client, store, _ = workspace
    original = t10_explanations.freeze_replay

    def concurrent_delete(*args, **kwargs):
        snapshot = original(*args, **kwargs)
        store.put("A", "company_model_active", [dict(id="active", version="new")])
        store.remove("A", [("company_models", "old"), ("company_weights", "old")])
        return snapshot

    monkeypatch.setattr(t10_explanations, "freeze_replay", concurrent_delete)
    response = client.post("/v1/predict", json=dict(cutoff="2026-11-14", opening_balance=0,
                                                  payments_complete=True, shap_limit=0))
    assert response.status_code == 409, response.text
    assert not store.get("A", "company_predictions")
    assert not store.get("A", "company_forecast_index")
    assert not store.get("A", "company_forecast_replays")


@pytest.mark.parametrize("version,method,provenance,local_weeks,expected", [
    ("global:X", "global_default", "global_local_selector", 0, "global_fallback"),
    ("bundle:X", "global_neural", "global_local_selector", 0, "global_selected"),
    ("bundle:X", "neural_local_0_a0.0", "global_local_selector", 0, "global_selected"),
    ("bundle:X", "neural_local_0_a0.5", "global_local_selector", 0, "company_adapted"),
    ("bundle:X", "global_neural", "global_local_selector", 3, "company_adapted"),
    ("bundle:X", "incumbent", "global_local_selector", 0, "saved_model"),
    ("bundle:X", "neural_local_0_aUNKNOWN", "global_local_selector", 0, "saved_model"),
    ("test:X", "", "", 0, "saved_model"),
])
def test_serving_state_describes_parameters_instead_of_registry_existence(version, method, provenance, local_weeks, expected):
    partial = SimpleNamespace(evidence=dict(prior_sha256="GLOBAL" if local_weeks else None,
                                            cells=[dict(weeks=local_weeks)]))
    bundle = dict(t1_version=version, serving_method=method, partial=partial,
                  t1_provenance=dict(source=provenance, local_adaptation="local" in method))
    assert serving_mode(bundle) == expected


def test_api_persists_global_fallback_state_even_with_company_registry(workspace):
    client, store, _ = workspace
    plan = predict(client)
    assert plan["company_bundle_version"] == "old"
    assert plan["mode"] == plan["serving_mode"] == "global_fallback"
    assert store.one("A", "company_predictions", plan["id"])["serving_mode"] == "global_fallback"


def seed_lifecycle(store):
    store.put_many("A", {
        "company_t1_update_state": [dict(id="current", last_cycle_asof="2026-11-14", next_due="2026-12-12")],
        "company_t1_update_runs": [dict(id="RUN", created_at="2026-11-14T00:00:00Z", status="kept_incumbent")],
        "company_t1_challengers": [
            dict(id="WAIT", origin="2026-11-14", status="pending", snapshot=dict(secret="PRIVATE"), artifact_id="SECRET"),
            dict(id="READY", origin="2026-08-01", status="pending"),
            dict(id="COVERAGE", origin="2026-08-02", status="pending", policy=dict(minimum_audit_snapshots=20),
                 evaluation=dict(status="insufficient_eligible_outcomes", rows=5)),
            *[dict(id=status, origin="2026-06-01", status=status, evaluated_asof="2026-10-01")
              for status in ("accepted", "rejected", "stale_incumbent")],
        ],
    })


def test_workspace_and_lifecycle_api_expose_dates_and_statuses_without_private_snapshots(workspace):
    client, store, _ = workspace
    seed_lifecycle(store)
    response = client.get("/v1/workspace")
    updates = response.json()["t1_updates"]
    assert updates == client.get("/v1/t1/updates").json()
    assert updates["due"] is False and updates["pending_count"] == 3
    statuses = {r["id"]: r for r in updates["challengers"]}
    assert statuses["WAIT"]["matures_on"] == "2027-02-13"
    assert statuses["WAIT"]["display_status"] == "waiting_for_91_days"
    assert statuses["READY"]["display_status"] == "ready_for_audit"
    assert statuses["COVERAGE"]["display_status"] == "insufficient_eligible_outcomes"
    assert statuses["COVERAGE"]["eligible_rows"] == 5
    assert "PRIVATE" not in response.text and "SECRET" not in response.text
    assert '"snapshot":' not in response.text and '"artifact_id":' not in str(updates)


def test_status_polling_uses_small_metadata_after_legacy_backfill(workspace, monkeypatch):
    client, store, _ = workspace
    seed_lifecycle(store)
    read = store.one
    transactional_reads = []

    def observe_backfill(firm, kind, identifier):
        if kind == "company_t1_challengers":
            transactional_reads.append(store.connection.in_transaction)
        return read(firm, kind, identifier)

    monkeypatch.setattr(store, "one", observe_backfill)
    assert client.get("/v1/workspace").status_code == 200
    assert transactional_reads and all(transactional_reads)
    index = store.get("A", "company_t1_challenger_index")
    assert len(index) == 6 and all("snapshot" not in row and "artifact_id" not in row for row in index)
    get, one = store.get, store.one

    def metadata_get(firm, kind):
        assert kind != "company_t1_challengers", "Polling must not deserialize all snapshots"
        return get(firm, kind)

    def metadata_one(firm, kind, identifier):
        assert kind != "company_t1_challengers", "An indexed poll must not reopen a raw snapshot"
        return one(firm, kind, identifier)

    monkeypatch.setattr(store, "get", metadata_get)
    monkeypatch.setattr(store, "one", metadata_one)
    assert client.get("/v1/workspace").json()["t1_updates"]["pending_count"] == 3
    assert client.get("/v1/t1/updates").json()["pending_count"] == 3


@pytest.mark.parametrize("width", [1500, 390])
def test_browser_shows_schedule_challenger_states_and_legacy_global_label(
        workspace, monkeypatch, browser_runtime, client_proxy, tmp_path, width):
    from playwright.sync_api import expect
    client, store, _ = workspace
    seed_lifecycle(store)
    plan = predict(client)
    # Represent a saved pre-fix payload: the original company_trained label is
    # corrected for display from its frozen provenance, without rewriting it.
    plan.pop("serving_mode")
    plan["mode"] = "company_trained"
    store.put("A", "company_predictions", [plan])
    runtime, chrome = browser_runtime
    with runtime.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(chrome), headless=True)
        try:
            page = browser.new_page(viewport=dict(width=width, height=960))
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route("**/*", client_proxy(client))
            page.goto("http://testserver/workspace#training")
            panel = page.locator("#t1-updates")
            expect(panel).to_contain_text("12-12-26")
            page.locator(".challenger-history > summary").click()
            expect(panel).to_contain_text("13-02-27")
            expect(panel).to_contain_text("Chờ đủ 13 tuần")
            expect(panel).to_contain_text("5/20 khoản đủ dữ liệu thực tế")
            expect(panel).to_contain_text("Đã được chấp nhận")
            expect(panel).to_contain_text("Không đạt kiểm định")
            expect(panel).to_contain_text("phiên bản đối chứng đã thay đổi")
            expect(page.locator("#train-button")).to_be_disabled()
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
            page.screenshot(path=str(tmp_path/f"training-{width}.png"), full_page=True)
            set_time(monkeypatch, "2027-02-13T12:00:00")
            page.reload()
            expect(panel).to_contain_text("Đã đủ 13 tuần; chờ lượt kiểm định")
            page.locator("#train-asof").fill("13-02-27")
            page.locator("#train-asof").blur()
            expect(page.locator("#train-button")).to_be_enabled()
            page.locator("#train-asof").fill("14-11-26")
            page.locator("#train-asof").blur()
            expect(page.locator("#train-button")).to_be_disabled()
            page.locator("nav details").evaluate_all("items => items.forEach(item => item.open = true)")
            page.locator('nav [data-view="forecast"]').click()
            page.locator(".history-menu > summary").click()
            page.locator("#saved-plans").click()
            page.locator("#plans-list button").first.click()
            expect(page.locator("#forecast-mode")).to_have_text("MÔ HÌNH NỀN DỰ PHÒNG")
            assert "Phiên bản mới không tự" not in page.locator("#view-guide").inner_text()
            assert "Hệ thống tự chuyển sang phiên bản mới" in page.locator("#view-guide").inner_text()
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
            assert not errors
        finally:
            browser.close()
