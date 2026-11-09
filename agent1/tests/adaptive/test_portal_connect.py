"""Verify one-use portal authentication using isolated stores and synthetic credentials."""

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import io
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from agent1_service.api import create_app
from agent1_service.workspace.portal_connect import PortalTickets


AUTH = {"Authorization": "Bearer synthetic-portal-key"}


@pytest.fixture
def connection(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT1_COMPANY_PROFILE_FILE", raising=False)
    app = create_app(tmp_path / "data", key_dir=tmp_path / "keys", token="synthetic-portal-key", firm_id="TEST_A")
    with TestClient(app) as client:
        yield client, app


def issue(client, company="TEST_A", headers=None):
    return client.post("/v1/portal-connect/tickets", json=dict(company=company), headers=AUTH if headers is None else headers)


def test_ticket_connects_same_company_once_without_creating_public_access(connection):
    client, _ = connection
    assert client.get("/v1/workspace").status_code == 401
    minted = issue(client)
    assert minted.status_code == 201
    assert minted.json()["expires_in"] == 60
    assert "synthetic-portal-key" not in minted.text
    ticket = minted.json()["ticket"]
    exchange = client.post("/v1/portal-connect/redeem", json=dict(ticket=ticket))
    assert exchange.status_code == 200
    assert exchange.headers["cache-control"] == "no-store"
    assert exchange.headers["referrer-policy"] == "no-referrer"
    assert exchange.json() == dict(company="TEST_A", key="synthetic-portal-key")
    access = client.get("/v1/access", headers={"Authorization": "Bearer " + exchange.json()["key"]})
    assert access.json() == dict(company="TEST_A", role="accountant")
    assert client.post("/v1/portal-connect/redeem", json=dict(ticket=ticket)).status_code == 401
    assert client.get("/v1/workspace").status_code == 401


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Bearer synthetic-reader"}])
def test_issuance_requires_accountant_authentication(connection, monkeypatch, headers):
    client, _ = connection
    monkeypatch.setenv("AGENT1_VIEWER_TOKEN", "synthetic-reader")
    assert issue(client, headers=headers).status_code == 401


def test_issuance_checks_company_and_schema(connection):
    client, _ = connection
    assert issue(client, company="TEST_B").status_code == 409
    assert client.post("/v1/portal-connect/tickets", headers=AUTH, json=dict(company="TEST_A", key="injected")).status_code == 422
    assert client.post("/v1/portal-connect/redeem", json=dict(ticket="short")).status_code == 422


def test_ticket_expires_at_sixty_seconds(connection):
    client, app = connection
    now = [100.0]
    app.state.portal_tickets.clock = lambda: now[0]
    ticket = issue(client).json()["ticket"]
    now[0] += 60
    assert client.post("/v1/portal-connect/redeem", json=dict(ticket=ticket)).status_code == 401


def test_foreign_origin_cannot_redeem_ticket(connection):
    client, _ = connection
    ticket = issue(client).json()["ticket"]
    assert client.post("/v1/portal-connect/redeem", json=dict(ticket=ticket), headers={"Origin": "https://example.com"}).status_code == 403
    assert client.post("/v1/portal-connect/redeem", json=dict(ticket=ticket), headers={"Origin": "http://testserver"}).status_code == 200


def test_other_agent_process_cannot_redeem_ticket(connection, tmp_path):
    client, _ = connection
    ticket = issue(client).json()["ticket"]
    other_app = create_app(tmp_path / "other", key_dir=tmp_path / "other-keys", token="other-key", firm_id="TEST_B")
    with TestClient(other_app) as other:
        assert other.post("/v1/portal-connect/redeem", json=dict(ticket=ticket)).status_code == 401
    assert client.post("/v1/portal-connect/redeem", json=dict(ticket=ticket)).status_code == 200


def test_concurrent_redemption_succeeds_only_once():
    tickets = PortalTickets()
    ticket = tickets.issue("TEST_A", "synthetic-key")["ticket"]
    def redeem(_):
        try:
            return tickets.redeem(ticket, "TEST_A")
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(redeem, range(2)))
    assert results.count("synthetic-key") == 1
    assert results.count(401) == 1


def test_ticket_capacity_recovers_after_expiry():
    now = [0]
    tickets = PortalTickets(limit=1, clock=lambda: now[0])
    tickets.issue("TEST_A", "synthetic-key")
    with pytest.raises(HTTPException) as error:
        tickets.issue("TEST_A", "synthetic-key")
    assert error.value.status_code == 429
    now[0] = 60
    assert tickets.issue("TEST_A", "synthetic-key")["expires_in"] == 60


@pytest.fixture
def portal(connection, monkeypatch):
    client, _ = connection
    path = Path(__file__).resolve().parents[3] / "portal" / "server.py"
    spec = importlib.util.spec_from_file_location("portal_connect_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "company", lambda: dict(code="TEST_A"))
    monkeypatch.setattr(module, "agent1_key", lambda: "synthetic-portal-key")
    monkeypatch.setattr(module, "ORIGINS", ("http://localhost:9912",))
    monkeypatch.setattr(module, "ORIGIN", "http://localhost:9912")
    monkeypatch.setattr(module, "agent_url", lambda aid, path="": "http://127.0.0.1:8011" + path)
    def call(method, url, body=None, headers=None, timeout=None):
        response = client.request(method, urlsplit(url).path, json=body, headers=headers)
        return response.status_code, response.json()
    monkeypatch.setattr(module, "call", call)
    return module


def test_portal_handoff_round_trip_and_fragment_only_ticket(portal, connection):
    client, _ = connection
    result = portal.agent1_connect_link("TEST_A", "http://localhost:9912")
    target = urlsplit(result["url"])
    assert target.scheme + "://" + target.netloc == "http://127.0.0.1:8011"
    assert parse_qs(target.query) == dict(portal=["http://localhost:9912"])
    assert "synthetic-portal-key" not in result["url"]
    ticket = parse_qs(target.fragment)["portal-connect"][0]
    assert client.post("/v1/portal-connect/redeem", json=dict(ticket=ticket)).json()["company"] == "TEST_A"


def test_portal_rejects_company_change_and_foreign_origin(portal):
    with pytest.raises(ValueError, match="Doanh nghiệp đã đổi"):
        portal.agent1_connect_link("TEST_B", "http://localhost:9912")
    with pytest.raises(PermissionError):
        portal.agent1_connect_link("TEST_A", "https://example.com")


@pytest.mark.parametrize("headers", [{"Origin": "http://localhost:9912"}, {"Origin": "https://example.com", "X-Platform": "1"}])
def test_portal_route_requires_same_origin_and_platform_header(portal, headers):
    handler = object.__new__(portal.Handler)
    handler.path = "/api/agents/agent1/connect-link"
    handler.headers = headers
    handler.rfile = io.BytesIO(json.dumps(dict(company="TEST_A")).encode())
    with pytest.raises(PermissionError):
        handler.route("POST")


def test_portal_route_issues_valid_link(portal):
    raw = json.dumps(dict(company="TEST_A")).encode()
    handler = object.__new__(portal.Handler)
    handler.path = "/api/agents/agent1/connect-link"
    handler.headers = {"Origin": "http://localhost:9912", "X-Platform": "1", "Content-Length": str(len(raw))}
    handler.rfile = io.BytesIO(raw)
    handler.send = lambda status, body: (status, body)
    status, body = handler.route("POST")
    assert status == 200 and "#portal-connect=" in body["url"]
