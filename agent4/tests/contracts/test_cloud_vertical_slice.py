"""Contract tests for the non-demo Agent 4 cloud slice."""

from pathlib import Path

import httpx
import pytest

from agent4.api import create_cloud_app
from agent4.metric_selection.config import MetricSelectionConfig
from agent4.metric_selection.errors import ConfigurationError

_ROOT = Path(__file__).resolve().parents[3]
_SMOKE_WAREHOUSE = _ROOT / "portal/workspace/datasets/enterprise-x10-v3-smoke/warehouse.duckdb"
_CLAIMS = {"tenant_id": "tenant-a", "user_id": "user-a", "roles": ["finance_analyst"]}
_POLICY = {
    "allowed_views": ["mgmt", "tax", "gl"],
    "allowed_metrics": ["net_revenue", "gross_profit", "gross_margin_pct"],
    "allowed_branches": ["*"],
    "allowed_departments": ["*"],
    "policy_version": "cloud-test-v1",
}


def _config() -> MetricSelectionConfig:
    return MetricSelectionConfig(
        llm={"provider": "mock", "model": "cloud-test-model"},
        embedding={"provider": "hashing"},
        retrieval={"mode": "full_catalog"},
    )


def _app(*, warehouse: Path = _SMOKE_WAREHOUSE):
    return create_cloud_app(
        warehouses={"tenant-a": warehouse},
        selection_config=_config(),
        allow_test_providers=True,
    )


def _inject_policy(app):
    @app.middleware("http")
    async def trusted_gateway(request, call_next):
        request.state.idp_claims = _CLAIMS
        request.state.server_policy = _POLICY
        return await call_next(request)


@pytest.mark.asyncio
async def test_cloud_health_readiness_and_deny_by_default():
    app = _app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/healthz")).json() == {"status": "live"}
        assert (await client.get("/readyz")).json() == {
            "status": "ready",
            "checks": {"config": "ready", "warehouse_artifact": "ready"},
        }
        metrics = await client.get("/v1/metrics")
        assert metrics.status_code == 403
        query = await client.post(
            "/v1/query",
            headers={"X-Demo-Persona": "cfo_full"},
            json={
                "api_version": "v1",
                "question": "Doanh thu thuần tháng 08/2026?",
                "locale": "vi-VN",
            },
        )
        assert query.status_code == 403
        assert query.json()["error"]["stage"] == "auth_policy_context"
        assert "demo_evidence" not in query.json()


@pytest.mark.asyncio
async def test_cloud_query_and_catalog_use_only_trusted_gateway_context():
    app = _app()
    _inject_policy(app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        metrics = await client.get("/v1/metrics")
        assert metrics.status_code == 200
        assert {item["metric_id"] for item in metrics.json()} == {
            "net_revenue",
            "gross_profit",
            "gross_margin_pct",
        }
        assert all("sql_expr" not in item for item in metrics.json())

        response = await client.post(
            "/v1/query",
            json={
                "api_version": "v1",
                "question": "Doanh thu thuần tháng 08/2026?",
                "locale": "vi-VN",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["data"]["row_count"] == 1
        assert "api_key" not in response.text.lower()

        portal_shape = await client.post(
            "/api/agent4/query",
            headers={"X-Platform": "1"},
            json={"question": "Doanh thu thuần tháng 08/2026?", "options": {"include_table": True}},
        )
        assert portal_shape.status_code == 200
        assert portal_shape.json()["status"] == "ready"
        portal_metrics = await client.get("/api/agent4/metrics")
        assert portal_metrics.status_code == 200


@pytest.mark.asyncio
async def test_cloud_readiness_does_not_leak_artifact_path(tmp_path):
    missing = tmp_path / "private" / "warehouse.duckdb"
    app = _app(warehouse=missing)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"config": "ready", "warehouse_artifact": "missing"},
    }
    assert str(missing) not in response.text


@pytest.mark.asyncio
async def test_cloud_admission_returns_retryable_503_when_slot_is_busy():
    app = _app()
    await app.state.query_slots.acquire()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/query",
                json={
                    "api_version": "v1",
                    "question": "Doanh thu thuần tháng 08/2026?",
                    "locale": "vi-VN",
                },
            )
    finally:
        app.state.query_slots.release()
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert response.json()["error"] == {
        "code": "query_busy",
        "stage": "query_admission",
        "message": "Agent 4 is serving another expensive query.",
        "retryable": True,
        "details": {},
    }


def test_cloud_mode_rejects_demo_environment_and_wildcard_cors(monkeypatch):
    monkeypatch.setenv("AGENT4_DEMO_MODE", "1")
    with pytest.raises(ConfigurationError, match="cannot run"):
        _app()

    monkeypatch.delenv("AGENT4_DEMO_MODE")
    monkeypatch.setenv("AGENT4_CORS_ORIGINS", "*")
    with pytest.raises(ConfigurationError, match="wildcard"):
        _app()


@pytest.mark.asyncio
async def test_cloud_cors_allows_only_explicit_origin(monkeypatch):
    monkeypatch.setenv("AGENT4_CORS_ORIGINS", "https://portal.example.test")
    app = _app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        allowed = await client.options(
            "/healthz",
            headers={
                "Origin": "https://portal.example.test",
                "Access-Control-Request-Method": "GET",
            },
        )
        denied = await client.options(
            "/healthz",
            headers={
                "Origin": "https://attacker.example.test",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://portal.example.test"
    assert "access-control-allow-origin" not in denied.headers
