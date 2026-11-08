import httpx
import pytest

from agent4.metric_selection.api import create_app
from agent4.metric_selection.config import load_config
from agent4.metric_selection.factory import build_pipeline
from agent4.metric_selection.llm import MockLLMProvider


def make_app(monkeypatch):
    monkeypatch.delenv("AGENT4_METRIC_DEBUG", raising=False)
    config = load_config()
    config = config.model_copy(
        update={
            "embedding": config.embedding.model_copy(update={"cache_enabled": False}),
            "llm": config.llm.model_copy(update={"provider": "mock"}),
        }
    )
    provider = MockLLMProvider(
        {"status": "resolved", "metric_ids": ["net_revenue"]}
    )
    pipeline = build_pipeline(config, llm_provider=provider)
    return create_app(pipeline=pipeline)


@pytest.mark.asyncio
async def test_metric_selection_endpoint(monkeypatch):
    transport = httpx.ASGITransport(app=make_app(monkeypatch))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/metrics/select",
            json={"question": "Doanh thu thuần tháng này?", "context": {}},
        )
    assert response.status_code == 200
    assert response.json() == {
        "status": "resolved",
        "metric_ids": ["net_revenue"],
    }


@pytest.mark.asyncio
async def test_debug_is_forbidden_by_default(monkeypatch):
    transport = httpx.ASGITransport(app=make_app(monkeypatch))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/metrics/select",
            json={"question": "Doanh thu?", "debug": True},
        )
    assert response.status_code == 403
