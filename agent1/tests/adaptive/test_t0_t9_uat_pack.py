"""Verify the delivered synthetic UAT files against the real import/T9 APIs."""

from collections import defaultdict
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from agent1.adaptive.data import observed
from agent1_service.api import create_app


PACK = Path(__file__).resolve().parents[2] / "pilot/t0_t9_uat_20261110"
FIRM = "DEMO_UAT_PACK"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from agent1.reconciliation import operations
    from agent1_service.workspace import api, catalog, reconciliation

    monkeypatch.delenv("AGENT1_COMPANY_PROFILE_FILE", raising=False)
    monkeypatch.delenv("AGENT1_BANK_ACCOUNTS_FILE", raising=False)
    for module, name in ((operations, "today"), (reconciliation, "today"),
                         (catalog, "today"), (api, "t9_today")):
        monkeypatch.setattr(module, name, lambda: "2026-11-11")
    app = create_app(tmp_path / "data", key_dir=tmp_path / "keys", token="uat-fixture-test", firm_id=FIRM)
    with TestClient(app) as connection:
        connection.headers["Authorization"] = "Bearer uat-fixture-test"
        yield connection


def preview(client, relative, kind):
    file = PACK / relative
    response = client.post("/v1/imports/preview", files={"file": (file.name, file.read_bytes())},
                           data=dict(kind=kind, date_format="%Y-%m-%d", number_format="plain",
                                     known_at="2026-10-01", imported_by="UAT fixture test"))
    assert response.is_success, response.text
    return response.json()


def load(client, relative, kind):
    result = preview(client, relative, kind)
    assert result["can_commit"], result
    response = client.post("/v1/imports/" + result["id"] + "/commit")
    assert response.is_success, response.text


def core(client):
    for filename, kind in (("01_invoices.csv", "invoices"), ("02_bank.csv", "bank"),
                           ("03_payments.csv", "payments"), ("04_statements.csv", "statements")):
        load(client, "01_core/" + filename, kind)


def data(client):
    store = client.app.state.store
    version = store.one(FIRM, "company_dataset_active", "active")["version"]
    return store.one(FIRM, "company_datasets", version)["data"]


def test_manifest_preserves_the_delivered_fixture_bytes():
    manifest = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["synthetic"]
    listed = set()
    for entry in manifest["files"]:
        content = (PACK / entry["path"]).read_bytes()
        assert len(content) == entry["bytes"], entry["path"]
        assert hashlib.sha256(content).hexdigest() == entry["sha256"], entry["path"]
        listed.add(entry["path"])
    actual = {file.relative_to(PACK).as_posix() for suffix in ("*.csv", "*.xml") for file in PACK.rglob(suffix)}
    assert listed == actual


def test_core_controls_and_proposals_match_the_published_answers(client):
    core(client)
    control = json.loads((PACK / "controls.json").read_text(encoding="utf-8"))
    source = data(client)
    assert len(source["invoices"]) == control["invoices"]
    assert len(source["bank"]) == control["bank_lines"]
    assert sum(row["amount"] for row in source["invoices"]) == control["invoice_face_total"]
    assert observed(source, "2026-10-31").remaining_amount.sum() == 110000000
    pending = client.get("/v1/reconciliation").json()
    assert (pending["pending_count"], pending["unallocated"]) == (11, 83990000)
    assert pending["total_received"] == control["initial_total_received"]
    result = client.post("/v1/reconciliation/run", json={})
    assert result.is_success, result.text
    proposal = result.json()
    expected = json.loads((PACK / "expected_proposals.json").read_text(encoding="utf-8"))
    allocations = defaultdict(dict)
    for row in proposal["allocations"]:
        allocations[row["payment_id"]][row["invoice_id"]] = row["amount_minor"]
    assert dict(allocations) == expected["allocations"]
    actual = {row["bank_id"]: row for row in proposal["cases"]}
    for case in expected["cases"]:
        assert {key: actual[case["bank_id"]][key] for key in case} == case
    before = client.get("/v1/workspace").json()["dataset_hash"]
    load(client, "01_core/01_invoices.csv", "invoices")
    assert client.get("/v1/workspace").json()["dataset_hash"] == before


def test_every_negative_file_is_blocked_without_changing_company_data(client):
    core(client)
    before = client.get("/v1/workspace").json()["dataset_hash"]
    files = sorted((PACK / "negative").glob("*.csv"))
    assert len(files) == 14
    for file in files:
        kind = file.stem.split("__", 1)[1]
        result = preview(client, file.relative_to(PACK), kind)
        assert not result["can_commit"] and result["error_count"], file.name
        assert client.post("/v1/imports/" + result["id"] + "/commit").status_code == 422
        assert client.get("/v1/workspace").json()["dataset_hash"] == before


def test_large_vnd_allocation_preserves_the_last_dong(client):
    load(client, "02_large_vnd/01_invoices.csv", "invoices")
    load(client, "02_large_vnd/02_bank.csv", "bank")
    source = data(client)
    response = client.post("/v1/allocations", json=dict(payment_id="UAT-LARGE", bank_id=source["bank"][0]["bank_id"],
        invoice_id=source["invoices"][0]["invoice_id"], amount=str(source["bank"][0]["amount"]),
        reviewed_by="UAT fixture test", note="Synthetic large VND bank fixture"))
    assert response.is_success, response.text
    assert client.get("/v1/records?kind=invoices").json()["rows"][0]["remaining_amount"] == 1


def test_lifecycle_files_preserve_historical_debt(client):
    for file in sorted((PACK / "03_lifecycle").glob("*.csv")):
        kind = "payments" if file.name.startswith("02_") else "invoice_events" if file.name.startswith("05_") else "invoices"
        load(client, file.relative_to(PACK), kind)
    source = data(client)
    for cutoff, identifier, amount in (("2026-10-19", "L_ORIGINAL", 6000000),
                                       ("2026-10-24", "L_REPLACEMENT", 6000000),
                                       ("2026-10-25", "L_REPLACEMENT", 500000)):
        rows = observed(source, cutoff)
        assert list(rows.invoice_id) == [identifier]
        assert rows.iloc[0].remaining_amount == amount
    assert observed(source, "2026-11-01").empty


def test_xml_fixture_passes_the_accounting_gate(client):
    result = preview(client, "03_lifecycle/optional_original.xml", "invoices")
    assert result["can_commit"] and result["mapping_locked"]
    assert result["sample"][0]["amount"] == 11000000


def test_pagination_fixture_keeps_the_105th_receipt_actionable(client):
    load(client, "04_pagination/01_invoices.csv", "invoices")
    load(client, "04_pagination/02_bank.csv", "bank")
    pending = client.get("/v1/reconciliation").json()
    assert pending["pending_count"] == 105 and len(pending["pending"]) == 100
    response = client.post("/v1/reconciliation/run", json={})
    assert response.is_success, response.text
    case = next(row for row in response.json()["cases"] if row["bank_id"] == "PAGE_B105")
    assert case["allocations"]
