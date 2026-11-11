"""Verify governed caches through the production M1 entry points."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import httpx
import numpy as np
import pytest

from agent4.core import cache as cache_module
from agent4.core.cache import LRUTTLCache, build_scoped_cache_key
from agent4.core.catalog import MetricCatalog
from agent4.core.context import build_auth_context, query_intake
from agent4.core.errors import ContractError
from agent4.metric_selection import select_metrics_with_recovery
from agent4.metric_selection.config import (
    EmbeddingConfig,
    FewshotConfig,
    MetricSelectionConfig,
    RecoveryConfig,
    RetrievalConfig,
)
from agent4.metric_selection.embedding import EmbeddingProvider
from agent4.metric_selection.eval_adapter import predict
from agent4.metric_selection.fewshot import load_example_bank
from agent4.metric_selection.index import build_index, load_index
from agent4.metric_selection.orchestrator import orchestrate_retrieval
from agent4.planning.planner import build_semantic_plan_draft
from agent4.planning.validator import validate_semantic_plan_draft
from vals.run_eval import DEFAULT_DATASET, BenchmarkCase


def _cache(**limits):
    return LRUTTLCache(
        **{
            "max_entries": 2,
            "ttl_seconds": 10,
            "max_bytes_budget": 16 * 1024,
            "max_rows_per_entry": 2,
            **limits,
        }
    )


def test_lru_ttl_and_snapshot_isolation(monkeypatch):
    clock = 0
    monkeypatch.setattr(cache_module, "monotonic", lambda: clock)
    cache = _cache()
    original = {"rows": [{"value": [10]}]}
    assert cache.set("first", original)
    original["rows"][0]["value"].append(20)

    clock = 1
    assert cache.set("second", {"rows": []})
    hit = cache.get("first")
    assert hit == {"rows": [{"value": [10]}]}
    hit["rows"][0]["value"].clear()
    assert cache.set("third", {"rows": []})
    assert cache.get("second") is None
    assert cache.get("first") == {"rows": [{"value": [10]}]}

    clock = 10
    assert cache.get("first") is None
    assert cache.get("third") == {"rows": []}
    stats = cache.stats()
    assert {key: stats[key] for key in ("hits", "misses", "evictions", "active_entries")} == {
        "hits": 3,
        "misses": 2,
        "evictions": 2,
        "active_entries": 1,
    }
    clock = 11
    assert cache.stats()["estimated_memory_kb"] == 0


def test_cache_byte_and_row_limits_under_concurrent_writes():
    cache = _cache(max_entries=100, max_bytes_budget=2500)
    assert not cache.set("too-many", {"rows": [1, 2, 3]}, row_count=1)
    assert not cache.set("too-large", "x" * 3000)

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert all(executor.map(lambda key: cache.set(key, {"payload": "x" * 1024}), range(50)))
    stats = cache.stats()
    assert stats["active_entries"] == 1
    assert stats["evictions"] == 49
    assert 0 < stats["estimated_memory_kb"] <= 2500 / 1024


@pytest.mark.parametrize("field", ["tenant_id", "policy_hash", "catalog_hash"])
def test_scoped_keys_require_and_bind_identity(field):
    scope = {"tenant_id": "tenant-a", "policy_hash": "policy-v1", "catalog_hash": "catalog-v1"}
    original = build_scoped_cache_key("test", **scope, query="a", view="mgmt")
    assert original == build_scoped_cache_key("test", **scope, view="mgmt", query="a")
    assert original != build_scoped_cache_key(
        "test", **{**scope, field: "other"}, query="a", view="mgmt"
    )
    with pytest.raises(ValueError, match="required"):
        build_scoped_cache_key("test", **{**scope, field: ""}, query="a", view="mgmt")


def _draft(metric_id):
    return {
        "status": "resolved",
        "metric_ids": [metric_id],
        "clarification_question": None,
        "unsupported_reason": None,
    }


def _write_bank(path, example_id):
    path.write_text(
        json.dumps(
            {
                "id": example_id,
                "question": "Doanh thu thuần tháng 4?",
                "answer": _draft("net_revenue"),
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _replace_preserving_mtime(path, replacement):
    mtime = path.stat().st_mtime_ns
    os.utime(replacement, ns=(mtime, mtime))
    replacement.replace(path)


def test_l1_artifacts_are_read_once_and_refreshed(tmp_path, monkeypatch, selection_catalog):
    path = tmp_path / "index.npz"
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, "example-a")
    provider = EmbeddingProvider(EmbeddingConfig(cache_path=path))
    build_index(selection_catalog, provider)
    catalog_hash = selection_catalog.get_catalog_hash()
    changed = MetricCatalog(selection_catalog.list_approved_metrics())
    changed_hash = changed.get_catalog_hash()

    opens = []
    np_load, path_open = np.load, Path.open

    def load(file, **kwargs):
        opens.append(file)
        return np_load(file, **kwargs)

    def open_file(file, *args, **kwargs):
        if file == bank:
            opens.append(file)
        return path_open(file, *args, **kwargs)

    monkeypatch.setattr(np, "load", load)
    monkeypatch.setattr(Path, "open", open_file)

    first_index = load_index(path, catalog_hash=catalog_hash, embedding_provider=provider)
    expected = first_index.vectors.copy()
    first_index.vectors[0, 0] = 99
    first_index.metadata.clear()
    hit_index = load_index(path, catalog_hash=catalog_hash, embedding_provider=provider)
    np.testing.assert_array_equal(hit_index.vectors, expected)
    assert hit_index.metadata["catalog_hash"] == catalog_hash
    first_bank = load_example_bank(bank, catalog_hash=catalog_hash)
    first_bank[0]["expected_selection"]["metric_ids"].clear()
    assert load_example_bank(bank, catalog_hash=catalog_hash)[0]["expected_selection"][
        "metric_ids"
    ] == ["net_revenue"]
    assert opens == [path, bank]

    different_model = EmbeddingProvider(EmbeddingConfig(cache_path=path, model_version="next"))
    with pytest.raises(ContractError, match="stale"):
        load_index(path, catalog_hash=catalog_hash, embedding_provider=different_model)
    assert opens == [path, bank]

    with pytest.raises(ContractError, match="stale"):
        load_index(path, catalog_hash=changed_hash, embedding_provider=provider)
    assert load_example_bank(bank, catalog_hash=changed_hash)[0]["example_id"] == "example-a"

    new_index = tmp_path / "new.npz"
    build_index(changed, provider, new_index, locale="en-US")
    _replace_preserving_mtime(path, new_index)
    new_bank = tmp_path / "new.jsonl"
    _write_bank(new_bank, "example-b")
    _replace_preserving_mtime(bank, new_bank)
    assert (
        load_index(path, catalog_hash=changed_hash, embedding_provider=provider).document_texts
        != hit_index.document_texts
    )
    assert load_example_bank(bank, catalog_hash=changed_hash)[0]["example_id"] == "example-b"
    assert opens == [path, bank, path, bank, path, bank]


@pytest.fixture
def auth(request):
    return build_auth_context(
        {"user_id": "analyst", "tenant_id": "cache-test", "roles": ["analyst"]},
        {
            "policy_version": request.node.name,
            "allowed_views": ["mgmt"],
            "allowed_metrics": ["net_revenue"],
        },
    )


@pytest.fixture
def backend(tmp_path, monkeypatch, selection_catalog):
    """Exercise real HTTP encoding and result validation with controllable provider failures."""
    config = MetricSelectionConfig(
        embedding=EmbeddingConfig(
            provider="ollama", dimensions=64, cache_path=tmp_path / "index.npz"
        ),
        retrieval=RetrievalConfig(mode="hybrid"),
        fewshot=FewshotConfig(
            enabled=True, strategy="static", example_bank_path=tmp_path / "bank.jsonl"
        ),
    )
    _write_bank(config.fewshot.example_bank_path, "example-a")
    embed_calls, model_calls = [], []
    errors = {"embed": False, "model": False}

    def embed(request):
        inputs = json.loads(request.content)["input"]
        embed_calls.extend(inputs)
        if errors["embed"]:
            return httpx.Response(503)
        return httpx.Response(200, json={"embeddings": [[1.0] * 64 for _ in inputs]})

    def select(request):
        prompt = json.loads(json.loads(request.content)["messages"][1]["content"])
        model_calls.append(prompt)
        if errors["model"]:
            return httpx.Response(503)
        metric_id = prompt["candidates"]["rows"][0][0]
        return httpx.Response(
            200,
            json={
                "done_reason": "stop",
                "message": {"content": json.dumps(_draft(metric_id))},
                "prompt_eval_count": 100,
                "eval_count": 10,
            },
        )

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(select),
            **kwargs,
        ),
    )
    provider = EmbeddingProvider(config.embedding, transport=httpx.MockTransport(embed))
    build_index(selection_catalog, provider)
    embed_calls.clear()
    return config, provider, embed_calls, model_calls, errors


def _query(question="Doanh thu thuần?"):
    return query_intake({"api_version": "v1", "question": question, "locale": "vi-VN"})


@pytest.mark.asyncio
async def test_warm_pipeline_matches_cold_and_revalidates(backend, selection_catalog, auth):
    config, provider, embed_calls, model_calls, _ = backend

    async def run(question="Doanh thu thuần tháng 9/2026?", **kwargs):
        return await select_metrics_with_recovery(
            _query(question),
            selection_catalog,
            config=config,
            auth_context=auth,
            embedding_provider=provider,
            **kwargs,
        )

    first = await run()
    expected = deepcopy(first)
    first["metric_ids"].clear()
    first["retrieval_result"]["candidates"][0]["retrieval_sources"].clear()
    first["selected_example_ids"].clear()
    first["validated_capabilities"]["net_revenue"]["supported_views"].clear()
    second = await run()
    assert {k: v for k, v in second.items() if k not in ("stage_latency_ms", "usage")} == {
        k: v for k, v in expected.items() if k not in ("stage_latency_ms", "usage")
    }
    assert second["selected_example_ids"] == ["example-a"]
    assert second["usage"] == {"input_tokens": 0, "output_tokens": 0}
    assert set(second["stage_latency_ms"]) == {"retrieval_ms", "validation_ms"}
    assert len(embed_calls) == len(model_calls) == 1

    query = _query("Doanh thu thuần tháng 9/2026?")
    draft = build_semantic_plan_draft(query, second, {})
    plan = validate_semantic_plan_draft(draft, second, selection_catalog, auth)
    assert plan.metric_ids == ("net_revenue",)
    assert plan.policy_hash == auth["policy_hash"]

    # The embedding sees normalized input. The selector still sees the original prompt.
    variant = "DOANH THU THUẦN THÁNG 9/2026!"
    assert (await run(variant))["retrieval_result"]["query"] == variant
    assert len(embed_calls) == 1 and len(model_calls) == 2
    assert (await run(seed=9))["usage"]["input_tokens"] == 100
    assert len(embed_calls) == 1 and len(model_calls) == 3

    # Changed validation constraints must reach the validator even with warm retrieval.
    with pytest.raises(ContractError) as error:
        await run(query_context={"requested_operation": "invalid"})
    assert error.value.code == "unsupported_metric"
    assert len(embed_calls) == 1 and len(model_calls) == 4

    config.cache_enabled = False
    uncached = await run()
    assert uncached["retrieval_result"] == expected["retrieval_result"]
    assert uncached["metric_ids"] == expected["metric_ids"]
    assert uncached["usage"] == expected["usage"]
    assert len(embed_calls) == 2 and len(model_calls) == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tenant_id", "other-tenant"),
        ("policy_hash", "other-policy"),
        ("allowed_views", ["mgmt", "tax"]),
        ("allowed_metrics", ["gross_profit"]),
    ],
)
async def test_online_caches_do_not_cross_authorization_boundaries(
    backend,
    selection_catalog,
    auth,
    field,
    value,
):
    config, provider, embed_calls, model_calls, _ = backend
    first = await select_metrics_with_recovery(
        _query(),
        selection_catalog,
        config=config,
        auth_context=auth,
        embedding_provider=provider,
    )
    assert first["metric_ids"] == ["net_revenue"]
    other = await select_metrics_with_recovery(
        _query(),
        selection_catalog,
        config=config,
        auth_context={**auth, field: value},
        embedding_provider=provider,
    )
    expected = "gross_profit" if field == "allowed_metrics" else "net_revenue"
    assert other["metric_ids"] == other["retrieved_metric_ids"] == [expected]
    assert len(embed_calls) == len(model_calls) == 2


@pytest.mark.asyncio
async def test_warm_pipeline_observes_new_artifacts_and_catalog(backend, selection_catalog, auth):
    config, provider, embed_calls, model_calls, _ = backend
    bank = config.fewshot.example_bank_path
    path = provider.config.cache_path

    async def run(catalog=selection_catalog):
        return await select_metrics_with_recovery(
            _query(),
            catalog,
            config=config,
            auth_context=auth,
            embedding_provider=provider,
        )

    assert (await run())["selected_example_ids"] == ["example-a"]
    _write_bank(bank, "example-b")
    assert (await run())["selected_example_ids"] == ["example-b"]
    assert len(embed_calls) == 1 and len(model_calls) == 2

    build_index(selection_catalog, provider, locale="en-US")
    embed_calls.clear()
    assert (await run())["metric_ids"] == ["net_revenue"]
    assert len(model_calls) == 3 and not embed_calls

    changed = MetricCatalog(selection_catalog.list_approved_metrics())
    assert (await run(changed))["catalog_hash"] == changed.get_catalog_hash()
    assert load_index(path).metadata["catalog_hash"] == changed.get_catalog_hash()
    assert len(model_calls) == 4
    assert len(embed_calls) == len(changed.list_approved_metrics()) + 1

    bank.unlink()
    with pytest.raises(ContractError) as error:
        await run(changed)
    assert error.value.code == "fewshot_unavailable"
    assert error.value.final_status == "temporarily_unavailable"

    path.unlink()
    with pytest.raises(ContractError) as error:
        await run(changed)
    assert error.value.code == "fewshot_unavailable"
    assert load_index(path).metadata["catalog_hash"] == changed.get_catalog_hash()


@pytest.mark.asyncio
async def test_transient_failures_and_degraded_results_do_not_pin_selection(
    backend,
    selection_catalog,
    auth,
):
    config, provider, embed_calls, model_calls, errors = backend
    query = _query()

    async def run():
        return await select_metrics_with_recovery(
            query,
            selection_catalog,
            config=config,
            auth_context=auth,
            embedding_provider=provider,
        )

    errors["embed"] = True
    for _ in range(2):
        result = orchestrate_retrieval(
            query,
            selection_catalog,
            provider,
            auth_context=auth,
            config=config,
        )
        assert result["status"] == "retrieval_unavailable"
    assert len(embed_calls) == 2

    config.recovery = RecoveryConfig(degraded_lexical_fallback=True)
    assert (await run())["recovery_reason"] == "retrieval_unavailable"
    assert (await run())["recovery_reason"] == "retrieval_unavailable"
    assert len(model_calls) == 2 and len(embed_calls) == 4

    errors["embed"], errors["model"] = False, True
    with pytest.raises(ContractError) as error:
        await run()
    assert error.value.code == "llm_unavailable"
    errors["model"] = False
    recovered = await run()
    assert recovered["recovery_reason"] is None
    assert "dense" in recovered["retrieval_result"]["candidates"][0]["retrieval_sources"]
    assert len(embed_calls) == 5 and len(model_calls) == 4
    assert (await run())["usage"] == {"input_tokens": 0, "output_tokens": 0}
    assert len(model_calls) == 4


@pytest.mark.asyncio
async def test_benchmark_adapter_scopes_legacy_auth_and_hits_cache(backend, tmp_path, monkeypatch):
    config, _, _, model_calls, _ = backend
    config.retrieval = RetrievalConfig(mode="full_catalog")
    config.fewshot.enabled = False
    config_path = tmp_path / "eval.yaml"
    config_path.write_text(config.model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("AGENT4_METRIC_SELECTION_CONFIG", str(config_path))

    with DEFAULT_DATASET.open(encoding="utf-8") as dataset:
        request = BenchmarkCase.model_validate_json(next(dataset)).adapter_input(seed=20261101)
    assert "policy_hash" not in request["auth_context"]
    request["auth_context"]["allowed_metrics"] = ["net_revenue"]
    cold, warm = await predict(request), await predict(request)
    assert cold["selection"] == warm["selection"]
    assert warm["selection"]["metric_ids"] == ["net_revenue"]
    assert warm["usage"] == {"input_tokens": 0, "output_tokens": 0}
    assert len(model_calls) == 1
