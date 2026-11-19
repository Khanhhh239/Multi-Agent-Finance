"""Contract tests for the provider-neutral Agent 4 authentication gateway."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from agent4 import gateway
from agent4.api import create_cloud_app
from agent4.metric_selection.config import MetricSelectionConfig

_ROOT = Path(__file__).resolve().parents[3]
_WAREHOUSE = _ROOT / "portal/workspace/datasets/enterprise-x10-v3-smoke/warehouse.duckdb"
_POLICY = {
    "tenants": {
        "tenant-a": {
            "users": {
                "subject-a": {
                    "roles": ["finance_analyst"],
                    "allowed_views": ["mgmt", "tax", "gl"],
                    "allowed_metrics": ["net_revenue", "gross_profit", "gross_margin_pct"],
                    "allowed_branches": ["*"],
                    "allowed_departments": ["*"],
                    "policy_version": "cloud-gateway-test-v1",
                }
            }
        }
    }
}


def _config() -> MetricSelectionConfig:
    return MetricSelectionConfig(
        llm={"provider": "mock", "model": "gateway-test-model"},
        embedding={"provider": "hashing"},
        retrieval={"mode": "full_catalog"},
    )


@pytest.fixture
def rsa_keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


def _token(private, *, subject: str = "subject-a", tenant: str = "tenant-a") -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": "https://issuer.example.test/",
            "aud": "agent4-cloud",
            "sub": subject,
            "tenant_id": tenant,
            "iat": now,
            "exp": now + 300,
        },
        private,
        algorithm="RS256",
        headers={"kid": "gateway-test-key"},
    )


def _configure(monkeypatch, *, limit: int = 30) -> None:
    monkeypatch.setenv("AGENT4_OIDC_ISSUER", "https://issuer.example.test/")
    monkeypatch.setenv("AGENT4_OIDC_AUDIENCE", "agent4-cloud")
    monkeypatch.setenv(
        "AGENT4_OIDC_JWKS_URL", "https://issuer.example.test/.well-known/jwks.json"
    )
    monkeypatch.setenv("AGENT4_AUTH_POLICY_JSON", json.dumps(_POLICY))
    monkeypatch.setenv("AGENT4_RATE_LIMIT_PER_MINUTE", str(limit))


def _patch_factory(monkeypatch):
    monkeypatch.setattr(
        gateway,
        "create_cloud_app",
        lambda: create_cloud_app(
            warehouses={"tenant-a": _WAREHOUSE},
            selection_config=_config(),
            allow_test_providers=True,
        ),
    )


@pytest.mark.asyncio
async def test_gateway_health_is_public_but_agent_routes_are_not(monkeypatch):
    _configure(monkeypatch)
    _patch_factory(monkeypatch)
    app = gateway.create_gateway_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/healthz")).status_code == 200
        assert (await client.get("/readyz")).status_code == 200
        assert (await client.get("/health")).status_code == 401
        denied = await client.get("/v1/metrics", headers={"X-Tenant-Id": "tenant-a"})
    assert denied.status_code == 401
    assert denied.json() == {"error": {"code": "authentication_required"}}
    assert "WWW-Authenticate" in denied.headers


@pytest.mark.asyncio
async def test_gateway_uses_verified_token_and_server_policy(monkeypatch, rsa_keys):
    _configure(monkeypatch)
    _patch_factory(monkeypatch)
    private, public = rsa_keys

    async def fake_signing_key(self, token, *, algorithms):
        del self, token
        assert algorithms == ("RS256",)
        return public

    monkeypatch.setattr(gateway._JwksCache, "signing_key", fake_signing_key)
    app = gateway.create_gateway_app()
    token = _token(private)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/v1/metrics",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "attacker-tenant",
                "X-Roles": "administrator",
            },
        )
    assert response.status_code == 200
    assert {item["metric_id"] for item in response.json()} == {
        "net_revenue",
        "gross_profit",
        "gross_margin_pct",
    }


@pytest.mark.asyncio
async def test_gateway_rejects_unknown_subject_and_limits_requests(monkeypatch, rsa_keys):
    _configure(monkeypatch, limit=3)
    _patch_factory(monkeypatch)
    private, public = rsa_keys

    async def fake_signing_key(self, token, *, algorithms):
        del self, token, algorithms
        return public

    monkeypatch.setattr(gateway._JwksCache, "signing_key", fake_signing_key)
    app = gateway.create_gateway_app()
    token = _token(private)
    unknown = _token(private, subject="not-authorized")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        denied = await client.get("/v1/metrics", headers={"Authorization": f"Bearer {unknown}"})
        first = await client.get("/v1/metrics", headers={"Authorization": f"Bearer {token}"})
        second = await client.get("/v1/metrics", headers={"Authorization": f"Bearer {token}"})
        third = await client.get("/v1/metrics", headers={"Authorization": f"Bearer {token}"})
    assert denied.status_code == 401
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.headers["Retry-After"]


def test_gateway_requires_identity_provider_and_server_policy(monkeypatch):
    for name in (
        "AGENT4_OIDC_ISSUER",
        "AGENT4_OIDC_AUDIENCE",
        "AGENT4_OIDC_JWKS_URL",
        "AGENT4_AUTH_POLICY_JSON",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(Exception, match="AGENT4_OIDC_ISSUER"):
        gateway.GatewaySettings.from_env()
