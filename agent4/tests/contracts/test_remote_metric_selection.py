"""Provider wire contracts, safe model normalization, and index recovery."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
import pytest

from agent4.core.catalog import MetricCatalog
from agent4.core.context import query_intake
from agent4.core.errors import ContractError
from agent4.metric_selection.config import (
    EmbeddingConfig,
    LLMSelectionConfig,
    MetricSelectionConfig,
    RetrievalConfig,
    load_config,
)
from agent4.metric_selection.embedding import EmbeddingProvider
from agent4.metric_selection.errors import ConfigurationError
from agent4.metric_selection.index import load_index, load_or_build_index
from agent4.metric_selection.llm_selector import (
    LLMMetricSelector,
    SelectionFormatError,
    validate_llm_selection_draft,
)
from agent4.metric_selection.orchestrator import orchestrate_retrieval


def test_config_environment_overrides_and_redacts_credentials(monkeypatch, tmp_path):
    path = tmp_path / "selection.yaml"
    path.write_text("llm: {model: old, max_tokens: 128}\nembedding: {dimensions: 768}\n")
    env = {
        "AGENT4_LLM_PROVIDER": "openai",
        "AGENT4_LLM_BASE_URL": "https://chat.test/v1",
        "AGENT4_LLM_MODEL": "chat-test",
        "AGENT4_EMBED_PROVIDER": "openai",
        "AGENT4_EMBED_BASE_URL": "https://embedding.test",
        "AGENT4_EMBED_MODEL": "embed-test",
        "AGENT4_EMBED_DIMENSIONS": "64",
        "AGENT4_RETRIEVAL_MODE": "hybrid",
        "AGENT4_LLM_API_KEY": "llm-test-credential",
        "AGENT4_EMBED_API_KEY": "embed-test-credential",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    config = load_config(path)
    assert config.llm.provider == config.embedding.provider == "openai"
    assert (config.llm.model, config.llm.base_url, config.llm.max_tokens) == (
        "chat-test",
        "https://chat.test/v1",
        128,
    )
    assert (config.embedding.model, config.embedding.base_url, config.embedding.dimensions) == (
        "embed-test",
        "https://embedding.test",
        64,
    )
    assert config.retrieval.mode == "hybrid"
    assert config.llm.api_key == env["AGENT4_LLM_API_KEY"]
    assert config.embedding.api_key == env["AGENT4_EMBED_API_KEY"]
    for value in (config.model_dump_json(), repr(config)):
        assert "test-credential" not in value
    monkeypatch.setenv("AGENT4_EMBED_DIMENSIONS", "invalid")
    with pytest.raises(ConfigurationError, match="dimensions") as error:
        load_config(path)
    assert "test-credential" not in str(error.value)


def _draft(status="resolved", ids=None, clarification=None, reason=None):
    return {
        "status": status,
        "metric_ids": ["net_revenue"] if ids is None else ids,
        "clarification_question": clarification,
        "unsupported_reason": reason,
    }


def _mock_chat(monkeypatch, handler):
    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("structured", [True, False])
async def test_openai_chat_schema_thinking_and_resolved_cleanup(monkeypatch, structured):
    noisy = _draft(clarification="Which revenue drop?", reason="Outside current scope -- unsure")
    with pytest.raises(SelectionFormatError):
        validate_llm_selection_draft(noisy)

    def respond(request):
        assert request.url.path == "/tunnel/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "test-chat"
        assert payload["seed"] == 77
        assert payload["max_tokens"] == 1024
        assert payload["stream"] is False
        if structured:
            assert payload["response_format"]["type"] == "json_schema"
            assert payload["response_format"]["json_schema"]["strict"] is True
            assert (
                payload["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
            )
        else:
            assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": "<think>Private reasoning\n</think>\n" + json.dumps(noisy)
                        },
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 20},
            },
        )

    _mock_chat(monkeypatch, respond)
    selector = LLMMetricSelector(
        LLMSelectionConfig(
            provider="openai",
            base_url="https://model.test/tunnel/v1/",
            model="test-chat",
            api_key="test-key",
            structured_output=structured,
        )
    )
    draft, usage = await selector.select("Revenue?", [{"metric_id": "net_revenue"}], seed=77)
    assert draft == _draft()
    assert usage == {"input_tokens": 11, "output_tokens": 20}


@pytest.mark.asyncio
@pytest.mark.parametrize("clarification", [None, "", "  "])
async def test_ollama_supplies_missing_clarification(monkeypatch, clarification):
    def respond(request):
        payload = json.loads(request.content)
        assert payload["options"]["num_predict"] == 256
        assert payload["think"] is False
        return httpx.Response(
            200,
            json={
                "done_reason": "stop",
                "message": {"content": json.dumps(_draft("ambiguous", [], clarification))},
            },
        )

    _mock_chat(monkeypatch, respond)
    selector = LLMMetricSelector(LLMSelectionConfig(max_tokens=256))
    draft, _ = await selector.select("Which figure?", [])
    assert draft["clarification_question"] == (
        "Bạn vui lòng làm rõ chỉ số tài chính và kỳ thời gian cần tra cứu?"
    )


@pytest.mark.asyncio
async def test_unsafe_inactive_messages_are_rejected_before_normalization(monkeypatch):
    # JSON escaping must not hide SQL in an otherwise discarded field.
    content = json.dumps(_draft(reason="SELECT amount FROM accounts")).replace(
        "SELECT", r"\u0053ELECT"
    )
    _mock_chat(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"done_reason": "stop", "message": {"content": content}}
        ),
    )
    with pytest.raises(ContractError, match="prohibited") as error:
        await LLMMetricSelector().select("Revenue?", [])
    assert not isinstance(error.value, SelectionFormatError)


@pytest.mark.parametrize(
    "reason",
    [
        "SELECT amount FROM accounts",
        "DROP TABLE example",
        "DELETE FROM example",
        "INSERT INTO example",
        "UPDATE example SET amount = 0",
        "ALTER TABLE example",
        "look here;--",
    ],
)
def test_selection_output_rejects_statement_forms(reason):
    with pytest.raises(ContractError, match="prohibited"):
        validate_llm_selection_draft(_draft("unsupported", [], reason=reason))


def test_plain_explanation_is_accepted():
    reason = "The revenue drop -- from one period to the next -- needs a date."
    assert (
        validate_llm_selection_draft(_draft("unsupported", [], reason=reason))["unsupported_reason"]
        == reason
    )


@pytest.mark.parametrize("invalid", [False, True])
def test_openai_embedding_batch_uses_response_indices(invalid):
    def respond(request):
        assert request.url.path == "/v1/embeddings"
        assert request.headers["authorization"] == "Bearer test-embedding-key"
        assert json.loads(request.content) == {
            "model": "embed-test",
            "input": ["a", "b"],
            "dimensions": 64,
        }
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0, 2] + [0] * 62},
                    {"index": 1 if invalid else 0, "embedding": [3] + [0] * 63},
                ]
            },
        )

    provider = EmbeddingProvider(
        EmbeddingConfig(
            provider="openai",
            base_url="https://model.test",
            model="embed-test",
            api_key="test-embedding-key",
            dimensions=64,
        ),
        transport=httpx.MockTransport(respond),
    )
    request = {
        "texts": ["a", "b"],
        "model_id": "embed-test",
        "model_version": "1",
        "normalize": True,
    }
    if invalid:
        with pytest.raises(ContractError) as error:
            provider.embed(request)
        assert error.value.code == "retrieval_unavailable"
    else:
        assert [row["values"][:2] for row in provider.embed(request)["vectors"]] == [[1, 0], [0, 1]]


def _remote_embedding(path, calls, provider_name="openai", *, outage=False):
    def respond(request):
        texts = json.loads(request.content)["input"]
        calls.append(len(texts))
        if outage:
            return httpx.Response(503)
        vectors = [[1.0] * 64 for _ in texts]
        if provider_name == "ollama":
            return httpx.Response(200, json={"embeddings": vectors})
        return httpx.Response(
            200,
            json={"data": [{"index": i, "embedding": v} for i, v in enumerate(vectors)]},
        )

    return EmbeddingProvider(
        EmbeddingConfig(provider=provider_name, model="embed-test", dimensions=64, cache_path=path),
        transport=httpx.MockTransport(respond),
    )


@pytest.mark.parametrize("provider_name", ["ollama", "openai"])
def test_remote_retrieval_rebuilds_missing_and_stale_index(tmp_path, analyst_auth, provider_name):
    calls = []
    path = tmp_path / "index.npz"
    provider = _remote_embedding(path, calls, provider_name)
    config = MetricSelectionConfig(
        embedding=provider.config, retrieval=RetrievalConfig(mode="dense_only")
    )
    query = query_intake({"api_version": "v1", "locale": "vi-VN", "question": "Doanh thu?"})

    def retrieve(catalog):
        return orchestrate_retrieval(
            query, catalog, provider, auth_context=analyst_auth, config=config
        )

    legacy, canonical = MetricCatalog(), MetricCatalog(canonical=True)
    assert retrieve(legacy)["status"] == "candidates_found"
    assert retrieve(canonical)["status"] == "candidates_found"
    assert load_index(path).metadata["catalog_hash"] == canonical.get_catalog_hash()
    assert sum(size > 1 for size in calls) == 4  # 14 documents then 70 documents in batches of 32.
    assert retrieve(canonical)["status"] == "candidates_found"
    assert sum(size > 1 for size in calls) == 4


@pytest.mark.parametrize(
    "scenario", ["corrupt", "cache_disabled", "provider_cache_disabled", "outage"]
)
def test_remote_index_unavailable_without_safe_rebuild(tmp_path, scenario):
    calls = []
    path = tmp_path / "index.npz"
    if scenario == "corrupt":
        path.write_bytes(b"invalid archive")
    provider = _remote_embedding(path, calls, outage=scenario == "outage")
    if scenario == "provider_cache_disabled":
        provider.config = provider.config.model_copy(update={"cache_enabled": False})
    with pytest.raises(ContractError) as error:
        load_or_build_index(MetricCatalog(), provider, cache_enabled=scenario != "cache_disabled")
    assert error.value.code == "retrieval_unavailable"
    assert len(calls) == (1 if scenario == "outage" else 0)
    assert path.exists() == (scenario == "corrupt")


def test_concurrent_remote_index_build_publishes_once(tmp_path):
    calls = []
    provider = _remote_embedding(tmp_path / "index.npz", calls)
    catalog = MetricCatalog()
    barrier = Barrier(2)

    def load():
        barrier.wait(timeout=2)
        return load_or_build_index(catalog, provider, cache_enabled=True).metric_ids

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.submit(load), executor.submit(load)
        assert first.result(timeout=5) == second.result(timeout=5)
    assert len(calls) == 1
