"""Synthetic inputs verify company scoping and import formats, not forecast accuracy."""

import csv
import importlib.util
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent1_service.api import create_app


def write_profile(path, **changes):
    data = dict(code="SME", date_format="iso", number_format="plain")
    data.update(changes)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def profile_client(tmp_path, monkeypatch):
    path = tmp_path / "company-profile.json"
    write_profile(path)
    monkeypatch.setenv("AGENT1_COMPANY_PROFILE_FILE", str(path))
    app = create_app(tmp_path / "data", key_dir=tmp_path / "keys", token="profile-test", firm_id="SME")
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer profile-test"
        yield client, path


def preview_invoice(client, content, **formats):
    return client.post(
        "/v1/imports/preview",
        files={"file": ("invoices.csv", content, "text/csv")},
        data=dict(kind="invoices", **formats),
    )


def test_workspace_receives_only_agent1_settings(profile_client):
    client, path = profile_client
    write_profile(path, legal_name="Private name", tax_code="Private tax code", filing_period="QUARTER")
    response = client.get("/v1/workspace")
    assert response.status_code == 200
    assert response.json()["company_profile"] == dict(code="SME", date_format="iso", number_format="plain", managed=True)
    assert "Private" not in response.text
    assert client.get("/v1/workspace", headers={"Authorization": "Bearer wrong"}).status_code == 401


@pytest.mark.parametrize("date_format", ["iso", "dmy"])
@pytest.mark.parametrize("number_format", ["plain", "vi-VN"])
def test_template_and_preview_follow_company_formats(profile_client, date_format, number_format):
    client, path = profile_client
    write_profile(path, date_format=date_format, number_format=number_format)
    template = client.get("/v1/templates/invoices")
    assert template.status_code == 200
    row = next(csv.DictReader(io.StringIO(template.content.decode("utf-8-sig"))))
    assert row["due_date"] == ("2026-01-31" if date_format == "iso" else "31/01/2026")
    assert row["amount"] == ("15000000" if number_format == "plain" else "15.000.000,00")
    preview = preview_invoice(client, template.content)
    assert preview.status_code == 200, preview.text
    assert preview.json()["can_commit"]
    assert preview.json()["sample"][0]["issue_date"] == "2026-01-01"
    assert preview.json()["sample"][0]["amount"] == 15000000
    assert client.post("/v1/imports/" + preview.json()["id"] + "/commit").status_code == 200


def test_mismatched_formats_do_not_stage_or_write_data(profile_client):
    client, _ = profile_client
    template = client.get("/v1/templates/invoices").content
    for formats in [dict(date_format="%d/%m/%Y"), dict(number_format="vi-VN")]:
        assert preview_invoice(client, template, **formats).status_code == 409
    assert client.get("/v1/workspace").json()["counts"]["invoices"] == 0


def test_profile_change_invalidates_previous_preview(profile_client):
    client, path = profile_client
    template = client.get("/v1/templates/invoices").content
    preview = preview_invoice(client, template).json()
    assert preview["can_commit"]
    write_profile(path, date_format="dmy")
    assert client.post("/v1/imports/" + preview["id"] + "/commit").status_code == 409
    workspace = client.get("/v1/workspace").json()
    assert workspace["counts"]["invoices"] == 0
    assert workspace["company_profile"]["date_format"] == "dmy"


def test_profile_of_another_company_is_rejected(profile_client):
    client, path = profile_client
    write_profile(path, code="OTHER")
    assert client.get("/v1/workspace").status_code == 409
    assert client.get("/v1/templates/invoices").status_code == 409
    assert preview_invoice(client, b"invoice_id\nI1\n").status_code == 409


@pytest.mark.parametrize("content", ["not json", "[]", '{"code":"SME","date_format":"bad","number_format":"plain"}'])
def test_unreadable_profile_does_not_fall_back_to_wrong_formats(profile_client, content):
    client, path = profile_client
    path.write_text(content, encoding="utf-8")
    assert client.get("/v1/workspace").status_code == 503


def test_independent_agent_retains_manual_format_choices(profile_client, monkeypatch):
    client, _ = profile_client
    monkeypatch.delenv("AGENT1_COMPANY_PROFILE_FILE")
    assert client.get("/v1/workspace").json()["company_profile"]["managed"] is False
    template = client.get("/v1/templates/invoices", params=dict(date_format="%d-%m-%y", number_format="plain"))
    assert b"31-01-26" in template.content
    preview = preview_invoice(client, template.content, date_format="%d-%m-%y", number_format="plain")
    assert preview.status_code == 200 and preview.json()["can_commit"]


def test_portal_publishes_scoped_profiles_and_rejects_invalid_formats(tmp_path, monkeypatch):
    server_path = Path(__file__).resolve().parents[3] / "portal" / "server.py"
    spec = importlib.util.spec_from_file_location("portal_profile_test", server_path)
    portal = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(portal)
    monkeypatch.setattr(portal, "WORK", tmp_path)
    monkeypatch.setattr(portal, "COMPANY_FILE", tmp_path / "company.json")
    company = dict(code="TEST_A", legal_name="Test company", date_format="iso", number_format="plain")
    portal.save_company(company)
    path_a = tmp_path / "agent1_profiles" / "TEST_A.json"
    assert json.loads(path_a.read_text()) == dict(code="TEST_A", date_format="iso", number_format="plain")
    portal.save_company(dict(company, code="TEST_B", date_format="dmy"))
    assert json.loads(path_a.read_text())["code"] == "TEST_A"
    for changes in [dict(date_format="bad"), dict(number_format="bad")]:
        with pytest.raises(ValueError, match="định dạng"):
            portal.save_company(dict(company, **changes))
    assert portal.company()["code"] == "TEST_B"
