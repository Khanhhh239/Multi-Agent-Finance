"""Browser sessions and an auditable, read-only view of imported company data."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from agent1_service.api import create_app


AUTH = {"Authorization": "Bearer catalog-test-key"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT1_COMPANY_PROFILE_FILE", raising=False)
    app = create_app(tmp_path / "data", key_dir=tmp_path / "keys", token="catalog-test-key", firm_id="CATALOG")
    with TestClient(app) as c:
        c.headers.update(AUTH)
        yield c


def invoice(identifier="I1", amount=10000000):
    return dict(invoice_id=identifier, customer_id="C1", issue_date="2026-10-01", due_date="2026-10-31",
                known_at="2026-10-01", amount=amount, currency="VND")


def preview(client, kind, rows, name="source.csv"):
    response = client.post("/v1/imports/preview", files={"file": (name, pd.DataFrame(rows).to_csv(index=False).encode(), "text/csv")},
                           data=dict(kind=kind, date_format="%Y-%m-%d", number_format="plain", imported_by="Kế toán thử nghiệm"))
    assert response.is_success, response.text
    return response.json()


def commit(client, kind, rows, name="source.csv"):
    p = preview(client, kind, rows, name)
    assert p["can_commit"], p
    response = client.post("/v1/imports/" + p["id"] + "/commit")
    assert response.is_success, response.text
    return p, response.json()


def test_browser_session_survives_reload_and_logout_revokes_it(client):
    result = client.post("/v1/session", headers={"Origin": "http://testserver"})
    assert result.is_success
    cookie = result.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/v1" in cookie
    assert "catalog-test-key" not in cookie and "catalog-test-key" not in result.text
    client.headers.pop("Authorization")
    assert client.get("/v1/access").json() == dict(company="CATALOG", role="accountant")
    assert client.get("/v1/workspace").is_success
    old_cookies = dict(client.cookies)
    assert client.delete("/v1/session").is_success
    assert client.get("/v1/workspace").status_code == 401
    client.cookies.update(old_cookies)
    assert client.get("/v1/workspace").status_code == 401


def test_browser_session_expiry_origin_and_role_are_enforced(client, monkeypatch):
    assert client.post("/v1/session", headers={"Origin": "https://foreign.example"}).status_code == 403
    client.post("/v1/session")
    client.headers.pop("Authorization")
    assert client.post("/v1/reconciliation/run", json={}, headers={"Origin": "http://testserver:9999"}).status_code == 403
    assert client.delete("/v1/session", headers={"Origin": "https://foreign.example"}).status_code == 403
    sessions = client.app.state.workspace_sessions
    original_clock = sessions.clock
    sessions.clock = lambda: float("inf")
    assert client.get("/v1/access").status_code == 401
    sessions.clock = original_clock
    monkeypatch.setenv("AGENT1_VIEWER_TOKEN", "reader-test-key")
    assert client.post("/v1/session", headers={"Authorization": "Bearer reader-test-key"}).is_success
    assert client.get("/v1/access").json()["role"] == "reader"
    assert client.get("/v1/records?kind=invoices").status_code == 401
    assert client.get("/v1/imports").status_code == 401
    monkeypatch.delenv("AGENT1_VIEWER_TOKEN")
    assert client.get("/v1/access").status_code == 401


def test_company_and_port_do_not_share_browser_sessions(client, tmp_path):
    client.post("/v1/session")
    cookies = dict(client.cookies)
    app = create_app(tmp_path / "other", key_dir=tmp_path / "other-keys", token="other-key", firm_id="OTHER")
    with TestClient(app) as other:
        other.cookies.update(cookies)
        assert other.get("/v1/workspace").status_code == 401
    with TestClient(client.app, base_url="http://testserver:9999") as other_port:
        other_port.cookies.update(cookies)
        assert other_port.get("/v1/workspace").status_code == 401


def test_import_history_records_duplicate_counts_debt_and_commit_retry(client):
    p, first = commit(client, "invoices", [invoice()], "invoices.csv")
    assert (first["new"], first["changed"], first["unchanged"]) == (1, 0, 0)
    repeat, second = commit(client, "invoices", [invoice()], "invoices-again.csv")
    assert (second["new"], second["changed"], second["unchanged"]) == (0, 0, 1)
    assert client.post("/v1/imports/" + p["id"] + "/commit").json()["replayed"]
    history = client.get("/v1/imports").json()
    assert history["total"] == 2
    first_batch = next(r for r in history["rows"] if r["id"] == p["id"])
    assert first_batch["source_file"] == "invoices.csv"
    assert first_batch["imported_by"] == "Kế toán thử nghiệm"
    assert first_batch["outstanding_before"] == 0 and first_batch["outstanding_after"] == 10000000
    assert "record_ids" not in first_batch
    assert client.get("/v1/imports/" + repeat["id"]).json()["records"] == [dict(kind="invoices", identifier="I1")]
    assert client.get("/v1/workspace").json()["counts"]["invoices"] == 1
    bad = preview(client, "payments", [dict(payment_id="P", invoice_id="absent", payment_date="2026-10-15", amount=10)])
    assert not bad["can_commit"]
    assert client.get("/v1/imports").json()["rows"][0]["status"] == "invalid"
    assert client.get("/v1/imports/" + bad["id"]).json()["errors"]


def test_record_search_filter_and_pagination(client):
    commit(client, "invoices", [invoice("I" + str(n).zfill(2)) for n in range(30)])
    page = client.get("/v1/records?kind=invoices&limit=25").json()
    assert page["total"] == 30 and len(page["rows"]) == 25
    next_page = client.get("/v1/records?kind=invoices&offset=25").json()
    assert len(next_page["rows"]) == 5
    assert not {r["identifier"] for r in page["rows"]} & {r["identifier"] for r in next_page["rows"]}
    assert client.get("/v1/records?kind=invoices&q=I29&status=open").json()["total"] == 1
    assert client.get("/v1/records?kind=invoices&date_from=2026-10-02").json()["total"] == 0
    assert client.get("/v1/records?kind=invoices&date_from=2026-11-01&date_to=2026-10-01").status_code == 422
    assert client.get("/v1/records?kind=invoices&limit=101").status_code == 422
    assert client.get("/v1/records?kind=secret").status_code == 422


def test_legacy_checks_without_file_metadata_remain_visible_and_read_only(client):
    p = preview(client, "invoices", [invoice()])
    store = client.app.state.store
    saved = store.one("CATALOG", "company_previews", p["id"])
    for field in ("source_file", "source_sha256", "imported_by", "row_count", "valid_rows", "error_count"):
        saved.pop(field)
    store.put("CATALOG", "company_previews", [saved])
    store.put("OTHER", "company_previews", [dict(saved, id="other-company-check")])
    before = client.get("/v1/workspace").json()
    writes_before = store.connection.total_changes

    history = client.get("/v1/imports?kind=invoices").json()
    assert history["total"] == history["legacy_count"] == 1
    row = history["rows"][0]
    assert row["id"] == p["id"] and row["status"] == "legacy_preview"
    assert row["source_file"] is None and row["imported_by"] == ""
    assert row["rows"] is None and row["valid_rows"] == 1 and row["error_count"] == 0
    assert row["created_at"] == saved["created_at"]
    assert "outstanding_before" not in row and "new" not in row
    assert client.get("/v1/imports?kind=bank").json()["total"] == 0
    page = client.get("/v1/imports?offset=1&limit=1").json()
    assert page["total"] == 1 and not page["rows"]
    detail = client.get("/v1/imports/" + p["id"]).json()
    assert detail["batch"] == row and detail["records"] == []
    assert "Không thể xác định đã lưu hay chưa" in detail["batch"]["note"]
    assert client.get("/v1/imports/other-company-check").status_code == 404
    assert client.get("/v1/workspace").json() == before
    assert store.connection.total_changes == writes_before


def test_legacy_invalid_checks_keep_errors_and_do_not_duplicate_confirmed_imports(client):
    bad = preview(client, "payments", [dict(payment_id="P", invoice_id="absent", payment_date="2026-10-15", amount=10)])
    store = client.app.state.store
    saved = store.one("CATALOG", "company_previews", bad["id"])
    for field in ("source_file", "source_sha256", "imported_by", "row_count", "valid_rows", "error_count"):
        saved.pop(field)
    store.put("CATALOG", "company_previews", [saved])
    p, _ = commit(client, "invoices", [invoice()])
    confirmed_preview = store.one("CATALOG", "company_previews", p["id"])
    confirmed_preview.pop("source_file")
    store.put("CATALOG", "company_previews", [confirmed_preview])

    history = client.get("/v1/imports").json()
    assert history["total"] == 2 and history["legacy_count"] == 1
    rows = {row["id"]: row for row in history["rows"]}
    assert rows[p["id"]]["status"] == "committed"
    assert rows[p["id"]]["source_file"] == "source.csv"
    assert rows[bad["id"]]["status"] == "invalid" and rows[bad["id"]]["error_count"] > 0
    detail = client.get("/v1/imports/" + bad["id"]).json()
    assert detail["errors"] and detail["batch"]["status"] == "invalid"


def test_record_links_show_imported_payments_decisions_and_reversal(client):
    commit(client, "invoices", [invoice()])
    commit(client, "bank", [dict(bank_id="B1", account="A", date="2026-10-15", direction="in", amount=5000000,
                                known_at="2026-10-31", customer_id="C1", memo="I1")])
    commit(client, "payments", [dict(payment_id="P1", invoice_id="I1", bank_id="B1", payment_date="2026-10-15",
                                    amount=2000000, known_at="2026-10-31")])
    req = dict(payment_id="MANUAL", invoice_id="I1", bank_id="B1", amount=3000000, reviewed_by="Reviewer", note="Bank evidence")
    approved = client.post("/v1/allocations", json=req)
    assert approved.is_success, approved.text
    detail = client.get("/v1/records/invoices/I1").json()
    assert {(r["kind"], r["identifier"]) for r in detail["related"]} == {("payments", "P1"), ("payments", "MANUAL"), ("bank", "B1")}
    assert detail["decisions"][0]["decision_id"] == approved.json()["decision_id"]
    assert client.get("/v1/records?kind=invoices").json()["rows"][0]["remaining_amount"] == 5000000
    assert client.get("/v1/records?kind=bank").json()["rows"][0]["status"] == "allocated"
    response = client.post("/v1/reconciliation/reverse", json=dict(idempotency_key="reverse-test", decision_id=approved.json()["decision_id"], reviewed_by="Reviewer", note="Recheck"))
    assert response.is_success, response.text
    reversed_detail = client.get("/v1/records/payments/MANUAL").json()
    assert reversed_detail["deleted"]
    assert reversed_detail["record"]["invoice_id"] == "I1"
    assert reversed_detail["record"]["bank_id"] == "B1"
    assert {(r["kind"], r["identifier"]) for r in reversed_detail["related"]} >= {("invoices", "I1"), ("bank", "B1")}
    assert reversed_detail["decisions"][0]["decision_id"] == approved.json()["decision_id"]
    assert reversed_detail["decisions"][0]["reversal"]["note"] == "Recheck"
    assert client.get("/v1/records/invoices/I1").json()["decisions"][0]["reversal"]["note"] == "Recheck"
    assert client.get("/v1/records?kind=invoices").json()["rows"][0]["remaining_amount"] == 8000000


def test_distinct_payment_ids_are_distinct_and_large_vnd_is_exact(client):
    amount = 100000000000000001
    p, _ = commit(client, "invoices", [invoice(amount=amount)])
    record = client.get("/v1/records?kind=invoices").json()["rows"][0]
    assert record["amount"] == str(amount) and record["remaining_amount"] == str(amount)
    assert client.get("/v1/imports/" + p["id"]).json()["batch"]["outstanding_after"] == str(amount)
    payment = dict(payment_id="P1", invoice_id="I1", payment_date="2026-10-15", known_at="2026-10-31", amount=1000)
    commit(client, "payments", [payment, dict(payment, payment_id="P2")])
    assert client.get("/v1/records?kind=payments").json()["total"] == 2
    assert client.get("/v1/records?kind=invoices").json()["rows"][0]["remaining_amount"] == str(amount - 2000)


def test_import_log_and_dataset_rollback_together(client, monkeypatch):
    p = preview(client, "invoices", [invoice()])
    store = client.app.state.store
    original = store.put_many

    def fail(firm, batches):
        if "company_imports" in batches:
            raise RuntimeError("simulated write failure")
        return original(firm, batches)

    monkeypatch.setattr(store, "put_many", fail)
    with pytest.raises(RuntimeError, match="simulated"):
        client.post("/v1/imports/" + p["id"] + "/commit")
    assert client.get("/v1/workspace").json()["counts"]["invoices"] == 0
    assert client.get("/v1/imports").json()["rows"][0]["status"] == "preview"
    monkeypatch.setattr(store, "put_many", original)
    assert client.post("/v1/imports/" + p["id"] + "/commit").is_success
