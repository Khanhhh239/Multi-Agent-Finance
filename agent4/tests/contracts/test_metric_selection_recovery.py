"""Exercise the production recovery pipeline with hashing and mocked HTTP only."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import yaml
from pydantic import ValidationError

from agent4.core.catalog import MetricCatalog
from agent4.core.context import query_intake
from agent4.core.errors import ContractError
from agent4.metric_selection import (
    LLMMetricSelector,
    MetricSelectionConfig,
    RecoveryConfig,
    SelectionTrace,
    select_metrics_with_recovery,
    validate_metrics,
)
from agent4.metric_selection.config import EmbeddingConfig, LLMSelectionConfig, RetrievalConfig
from agent4.metric_selection.embedding import EmbeddingProvider
from agent4.metric_selection.eval_adapter import predict, predict_e5
from agent4.metric_selection.index import build_index
from vals.run_eval import Prediction


def _query(question: str = "Doanh thu thuần?") -> dict:
    return query_intake({"api_version": "v1", "locale": "vi-VN", "question": question})


def _draft(*ids: str) -> dict:
    return {
        "status": "resolved",
        "metric_ids": list(ids),
        "clarification_question": None,
        "unsupported_reason": None,
    }


def _config(**recovery: bool) -> MetricSelectionConfig:
    return MetricSelectionConfig(
        retrieval=RetrievalConfig(mode="lexical_only", lexical_top_k=1),
        llm=LLMSelectionConfig(max_retries=1),
        recovery=RecoveryConfig(**recovery),
    )


@pytest.fixture
def analyst_auth(analyst_auth: dict, request: pytest.FixtureRequest) -> dict:
    # Each test's simulated model is independent, even when the prompt is identical.
    return {**analyst_auth, "policy_hash": f"{analyst_auth['policy_hash']}/{request.node.name}"}


@pytest.fixture
def stub_model(monkeypatch: pytest.MonkeyPatch):
    original_client = httpx.AsyncClient

    def install(*responses: str | dict | httpx.Response) -> list[dict]:
        calls = []

        def handle(request: httpx.Request) -> httpx.Response:
            calls.append(json.loads(request.content))
            response = responses[len(calls) - 1]
            if isinstance(response, httpx.Response):
                return response
            return httpx.Response(
                200,
                json={
                    "done_reason": "stop",
                    "prompt_eval_count": 30,
                    "eval_count": 5,
                    "message": {
                        "content": response if isinstance(response, str) else json.dumps(response)
                    },
                },
            )

        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda **kwargs: original_client(transport=httpx.MockTransport(handle), **kwargs),
        )
        return calls

    return install


@pytest.mark.asyncio
async def test_empty_fallback_uses_only_visible_metrics(selection_catalog: MetricCatalog) -> None:
    auth = {
        "allowed_views": ["mgmt"],
        "allowed_metrics": ["net_revenue", "experimental_cash_burn", "unverified_custom_kpi"],
    }
    config = _config(enable_empty_candidate_fallback=True)
    selector = LLMMetricSelector(LLMSelectionConfig(provider="mock"))
    result = await select_metrics_with_recovery(
        _query("xyzq"), selection_catalog, auth_context=auth, config=config, selector=selector
    )
    assert result["metric_ids"] == ["net_revenue"]
    assert result["initial_retrieved_metric_ids"] == []
    assert result["retrieved_metric_ids"] == ["net_revenue"]
    assert result["retrieval_result"]["candidates"][0]["retrieval_sources"] == [
        "catalog_full_fallback"
    ]
    assert result["recovery_triggered"] and result["recovery_reason"] == "empty_candidates"
    assert result["stage_latency_ms"].keys() == {"retrieval_ms", "llm_ms", "validation_ms"}


@pytest.mark.asyncio
async def test_degraded_lexical_and_unavailable_status(
    selection_catalog: MetricCatalog, tmp_path: Path
) -> None:
    path = tmp_path / "offline.npz"
    embedding = EmbeddingConfig(cache_path=path)
    build_index(selection_catalog, EmbeddingProvider(embedding))
    stale_provider = EmbeddingProvider(EmbeddingConfig(cache_path=path, model_version="new"))
    config = MetricSelectionConfig(
        retrieval=RetrievalConfig(mode="hybrid"),
        embedding=embedding,
        llm=LLMSelectionConfig(provider="mock"),
    )
    auth = {"allowed_views": ["mgmt"], "allowed_metrics": ["net_revenue"]}
    with pytest.raises(ContractError) as error:
        await select_metrics_with_recovery(
            _query(),
            selection_catalog,
            auth_context=auth,
            config=config,
            embedding_provider=stale_provider,
        )
    assert error.value.code == "retrieval_unavailable"
    assert error.value.final_status == "temporarily_unavailable" and error.value.retryable

    config.recovery = RecoveryConfig(
        degraded_lexical_fallback=True, enable_empty_candidate_fallback=True
    )
    for provider in (stale_provider, EmbeddingProvider(embedding, available=False)):
        result = await select_metrics_with_recovery(
            _query(),
            selection_catalog,
            auth_context=auth,
            config=config,
            embedding_provider=provider,
        )
        assert result["metric_ids"] == ["net_revenue"]
        assert result["recovery_reason"] == "retrieval_unavailable"
        assert result["retrieval_result"]["candidates"][0]["retrieval_sources"] == [
            "lexical_fallback"
        ]

    trace = SelectionTrace()
    with pytest.raises(ContractError) as error:
        await select_metrics_with_recovery(
            _query("xyzq"),
            selection_catalog,
            auth_context=auth,
            config=config,
            embedding_provider=stale_provider,
            trace=trace,
        )
    assert error.value.code == "retrieval_unavailable" and error.value.retryable
    assert (
        trace.recovery_reason == "retrieval_unavailable" and "llm_ms" not in trace.stage_latency_ms
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", ["{broken draft", {"status": "resolved"}])
async def test_schema_retry_uses_fixed_reminder_and_revalidates(
    selection_catalog: MetricCatalog, analyst_auth: dict, stub_model, malformed
) -> None:
    calls = stub_model(malformed, _draft("net_revenue"))
    result = await select_metrics_with_recovery(
        _query(), selection_catalog, auth_context=analyst_auth, config=_config()
    )
    assert result["metric_ids"] == ["net_revenue"]
    assert result["recovery_reason"] == "invalid_selection_format"
    assert result["usage"] == {"input_tokens": 60, "output_tokens": 10}
    assert len(calls) == 2
    first, second = (call["messages"] for call in calls)
    assert first[1] == second[1]
    assert second[0]["content"].startswith(first[0]["content"])
    assert "Return exactly one JSON object" in second[0]["content"][len(first[0]["content"]) :]
    assert "broken draft" not in str(second)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("responses", "code", "calls_expected"),
    [
        (("{broken", "{still broken"), "invalid_request", 2),
        (("{broken", _draft("SELECT SUM(credit_amount) FROM v_mgmt")), "invalid_request", 2),
        ((_draft("SELECT SUM(credit_amount) FROM v_mgmt"),), "invalid_request", 1),
        (
            (
                httpx.Response(
                    200,
                    json={"done_reason": "length", "message": {"content": "SELECT * FROM payroll"}},
                ),
            ),
            "invalid_request",
            1,
        ),
        ((httpx.Response(503),), "llm_unavailable", 1),
    ],
)
async def test_retry_is_bounded_and_excludes_unsafe_or_infrastructure_errors(
    selection_catalog: MetricCatalog,
    analyst_auth: dict,
    stub_model,
    responses,
    code: str,
    calls_expected: int,
) -> None:
    calls = stub_model(*responses)
    trace = SelectionTrace()
    with pytest.raises(ContractError) as error:
        await select_metrics_with_recovery(
            _query(), selection_catalog, auth_context=analyst_auth, config=_config(), trace=trace
        )
    assert error.value.code == code and len(calls) == calls_expected
    assert trace.recovery_triggered is (calls_expected == 2)
    assert "validation_ms" not in trace.stage_latency_ms


@pytest.mark.asyncio
async def test_expansion_revalidates_same_draft_without_another_model_call(
    selection_catalog: MetricCatalog, analyst_auth: dict, stub_model
) -> None:
    calls = stub_model(_draft("gross_profit"))
    result = await select_metrics_with_recovery(
        _query(),
        selection_catalog,
        auth_context=analyst_auth,
        config=_config(enable_candidate_expansion=True),
    )
    assert result["initial_retrieved_metric_ids"] == ["net_revenue"]
    assert result["retrieved_metric_ids"] == ["net_revenue", "gross_profit"]
    assert result["metric_ids"] == ["gross_profit"]
    assert "gross_profit" in result["validated_capabilities"]
    assert result["candidate_expanded"] and result["recovery_reason"] == "metric_outside_candidates"
    assert result["retrieval_result"]["candidates"][-1]["retrieval_sources"] == [
        "candidate_expansion"
    ]
    assert len(calls) == 1
    with pytest.raises(ContractError) as error:
        validate_metrics(
            _draft("gross_profit"),
            {"candidates": [{"metric_id": "net_revenue"}]},
            selection_catalog,
            analyst_auth,
        )
    assert error.value.code == "metric_outside_candidates"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("ids", "context", "allowed", "code", "expanded"),
    [
        (["unknown_kpi"], {}, None, "unknown_metric", False),
        (["experimental_cash_burn"], {}, None, "metric_outside_candidates", False),
        (["unverified_custom_kpi"], {}, None, "metric_outside_candidates", False),
        (["gross_profit"], {}, ["net_revenue"], "metric_outside_candidates", False),
        (["cash_balance"], {"requested_view": "tax"}, None, "unsupported_view", True),
        (["net_revenue", "cash_balance"], {}, None, "incompatible_metrics", True),
        (
            ["gross_profit"],
            {"requested_dimensions": ["missing_dimension"]},
            None,
            "unsupported_metric",
            True,
        ),
        (
            ["gross_profit"],
            {"requested_operation": "missing_operation"},
            None,
            "unsupported_metric",
            True,
        ),
    ],
)
async def test_expansion_keeps_catalog_and_validator_guards(
    selection_catalog: MetricCatalog,
    cfo_auth: dict,
    stub_model,
    ids,
    context,
    allowed,
    code: str,
    expanded: bool,
) -> None:
    calls = stub_model(_draft(*ids))
    trace = SelectionTrace()
    with pytest.raises(ContractError) as error:
        await select_metrics_with_recovery(
            _query(),
            selection_catalog,
            auth_context={**cfo_auth, "allowed_metrics": allowed},
            query_context=context,
            config=_config(enable_candidate_expansion=True),
            trace=trace,
        )
    assert error.value.code == code
    assert len(calls) == 1 and trace.candidate_expanded is expanded


@pytest.mark.asyncio
async def test_forbidden_view_never_reaches_the_model(
    selection_catalog: MetricCatalog, analyst_auth: dict, stub_model
) -> None:
    calls = stub_model()
    with pytest.raises(ContractError) as error:
        await select_metrics_with_recovery(
            _query(),
            selection_catalog,
            auth_context=analyst_auth,
            query_context={"requested_view": "tax"},
            config=_config(enable_empty_candidate_fallback=True, enable_candidate_expansion=True),
        )
    assert error.value.code == "forbidden_metric" and error.value.final_status == "forbidden"
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question", "responses", "reason", "code"),
    [
        ("xyzq", ("{broken",), "empty_candidates", "invalid_request"),
        (
            "Doanh thu thuần?",
            ("{broken", _draft("gross_profit")),
            "invalid_selection_format",
            "metric_outside_candidates",
        ),
    ],
)
async def test_recovery_budget_is_shared_across_stages(
    selection_catalog: MetricCatalog,
    analyst_auth: dict,
    stub_model,
    question: str,
    responses,
    reason: str,
    code: str,
) -> None:
    calls = stub_model(*responses)
    trace = SelectionTrace()
    with pytest.raises(ContractError) as error:
        await select_metrics_with_recovery(
            _query(question),
            selection_catalog,
            auth_context=analyst_auth,
            config=_config(enable_empty_candidate_fallback=True, enable_candidate_expansion=True),
            trace=trace,
        )
    assert error.value.code == code
    assert (
        len(calls) == len(responses)
        and trace.recovery_reason == reason
        and not trace.candidate_expanded
    )


@pytest.mark.asyncio
async def test_e5_adapter_records_recovery_with_runner_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "recovery.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "retrieval": {"mode": "lexical_only"},
                "llm": {"provider": "mock"},
                "recovery": {"enable_empty_candidate_fallback": True},
            }
        )
    )
    monkeypatch.setenv("AGENT4_METRIC_SELECTION_CONFIG", str(config))
    assert predict is predict_e5
    result = Prediction.model_validate(
        await predict(
            {
                "id": "offline-e5",
                "user_query": "xyzq",
                "locale": "vi-VN",
                "seed": 20261101,
                "query_context": {},
                "auth_context": {"allowed_views": ["mgmt"], "allowed_metrics": ["net_revenue"]},
                "expected_metric_ids": ["invented_kpi"],
                "case_category": "authorization_and_security",
            }
        )
    )
    assert result.warning_codes == ["recovery_triggered", "recovery_empty_candidates"]
    assert result.retrieved_metric_ids == ["net_revenue"]
    assert result.selection is not None and result.selection.metric_ids == ["net_revenue"]


def test_config_rejects_multiple_model_retries() -> None:
    with pytest.raises(ValidationError, match="max_retries"):
        LLMSelectionConfig(max_retries=2)
