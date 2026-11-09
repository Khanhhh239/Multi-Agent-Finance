"""Input-only evaluation adapters for full-catalog, dense, and hybrid retrieval."""

from __future__ import annotations

import asyncio
import os
from functools import cache, partial
from time import perf_counter
from typing import Any, Literal

from agent4.core.catalog import MetricCatalog
from agent4.core.context import query_intake
from agent4.core.errors import ContractError

from .catalog_adapter import build_canonical_catalog, build_full_catalog_retrieval_result
from .config import FewshotConfig, load_config
from .embedding import EmbeddingProvider
from .errors import ConfigurationError
from .llm_selector import LLMMetricSelector
from .orchestrator import orchestrate_retrieval
from .recovery import SelectionTrace, _select_from_retrieval, select_metrics_with_recovery


@cache
def _e0_pipeline():
    config = load_config()
    if (
        config.retrieval.mode != "full_catalog"
        or config.fewshot.enabled
        or config.llm.provider != "ollama"
        or config.llm.model != "qwen3:4b"
        or config.llm.temperature != 0
        or config.llm.max_retries != 0
    ):
        raise ConfigurationError(
            "E0 requires full catalog, Ollama qwen3:4b and zero-shot selection."
        )
    return build_canonical_catalog(), LLMMetricSelector(config.llm)


async def predict_e0(request: dict[str, Any]) -> dict[str, Any]:
    started = perf_counter()
    catalog, selector = _e0_pipeline()
    retrieval = build_full_catalog_retrieval_result(
        request["user_query"], catalog, request["auth_context"]
    )
    return await _select(request, retrieval, catalog, selector, started)


@cache
def _online_pipeline(config_path: str | None):
    config = load_config(config_path)
    return (
        build_canonical_catalog(),
        config,
        EmbeddingProvider(config.embedding),
        LLMMetricSelector(config.llm),
    )


async def _predict_online(
    request: dict[str, Any],
    mode: Literal["dense_only", "hybrid"],
    *,
    select: bool,
    fewshot_strategy: Literal["static", "hybrid"] | None = None,
) -> dict[str, Any]:
    started = perf_counter()
    catalog, config, provider, selector = _online_pipeline(
        os.getenv("AGENT4_METRIC_SELECTION_CONFIG")
    )
    if select and (config.llm.max_retries or (config.fewshot.enabled and fewshot_strategy is None)):
        raise ConfigurationError(
            "Selection ablations require their assigned strategy and no retries."
        )
    config = config.model_copy(
        update={"retrieval": config.retrieval.model_copy(update={"mode": mode})}
    )
    query = query_intake(
        {
            "api_version": "v1",
            "question": request["user_query"],
            "locale": request["locale"],
            "options": request.get("options"),
        }
    )
    retrieve = partial(
        orchestrate_retrieval,
        query,
        catalog,
        provider,
        config=config,
        auth_context=request["auth_context"],
        query_context=request["query_context"],
    )
    retrieval = (
        await asyncio.to_thread(retrieve) if provider.config.provider == "ollama" else retrieve()
    )
    if retrieval["status"] == "retrieval_unavailable":
        return {
            "id": request["id"],
            "retrieved_metric_ids": [],
            "stage_latency_ms": {"retrieval_ms": (perf_counter() - started) * 1000},
            "final_status": "temporarily_unavailable",
            "error": {"stage": "metric_retrieval", "code": "retrieval_unavailable"},
        }
    if select:
        fewshot = (
            config.fewshot.model_copy(update={"strategy": fewshot_strategy})
            if fewshot_strategy is not None
            else None
        )
        return await _select(request, retrieval, catalog, selector, started, fewshot=fewshot)
    return {
        "id": request["id"],
        "retrieved_metric_ids": [item["metric_id"] for item in retrieval["candidates"]],
        "stage_latency_ms": {"retrieval_ms": (perf_counter() - started) * 1000},
    }


async def predict_retrieval_dense(request: dict[str, Any]) -> dict[str, Any]:
    return await _predict_online(request, "dense_only", select=False)


async def predict_retrieval_hybrid(request: dict[str, Any]) -> dict[str, Any]:
    return await _predict_online(request, "hybrid", select=False)


async def predict_e1(request: dict[str, Any]) -> dict[str, Any]:
    return await _predict_online(request, "dense_only", select=True)


async def predict_e2(request: dict[str, Any]) -> dict[str, Any]:
    return await _predict_online(request, "hybrid", select=True)


async def predict_e3(request: dict[str, Any]) -> dict[str, Any]:
    return await _predict_online(request, "hybrid", select=True, fewshot_strategy="static")


async def predict_e4(request: dict[str, Any]) -> dict[str, Any]:
    return await _predict_online(request, "hybrid", select=True, fewshot_strategy="hybrid")


async def predict_e5(request: dict[str, Any]) -> dict[str, Any]:
    catalog, config, provider, selector = _online_pipeline(
        os.getenv("AGENT4_METRIC_SELECTION_CONFIG")
    )
    trace = SelectionTrace()
    try:
        query = query_intake(
            {
                "api_version": "v1",
                "question": request["user_query"],
                "locale": request["locale"],
                "options": request.get("options"),
            }
        )
        validated = await select_metrics_with_recovery(
            query,
            catalog,
            auth_context=request["auth_context"],
            query_context=request["query_context"],
            config=config,
            embedding_provider=provider,
            selector=selector,
            seed=request["seed"],
            trace=trace,
        )
    except ContractError as exc:
        return _prediction(request["id"], trace, error=exc)
    return _prediction(request["id"], trace, validated=validated)


async def _select(
    request: dict[str, Any],
    retrieval: dict[str, Any],
    catalog: MetricCatalog,
    selector: LLMMetricSelector,
    started: float,
    *,
    fewshot: FewshotConfig | None = None,
) -> dict[str, Any]:
    trace = SelectionTrace(stage_latency_ms={"retrieval_ms": (perf_counter() - started) * 1000})
    try:
        validated = await _select_from_retrieval(
            request["user_query"],
            request.get("locale", "vi-VN"),
            retrieval,
            catalog,
            request["auth_context"],
            request["query_context"],
            selector,
            request["seed"],
            trace,
            fewshot=fewshot,
        )
    except ContractError as exc:
        return _prediction(request["id"], trace, error=exc)
    return _prediction(request["id"], trace, validated=validated)


def _prediction(
    case_id: str,
    trace: SelectionTrace,
    *,
    validated: dict[str, Any] | None = None,
    error: ContractError | None = None,
) -> dict[str, Any]:
    prediction: dict[str, Any] = {
        "id": case_id,
        "retrieved_metric_ids": trace.retrieved_metric_ids,
        "stage_latency_ms": trace.stage_latency_ms,
    }
    if trace.usage is not None:
        prediction["usage"] = trace.usage
    if trace.selected_example_ids:
        prediction["selected_example_ids"] = trace.selected_example_ids
    if trace.recovery_triggered:
        prediction["warning_codes"] = ["recovery_triggered", f"recovery_{trace.recovery_reason}"]
    if trace.candidate_expanded:
        prediction.setdefault("warning_codes", []).append("candidate_expanded")
    if error is not None:
        prediction["final_status"] = error.final_status
        if error.stage == "metrics_validation":
            prediction["selection"] = {"status": "unsupported", "metric_ids": []}
            prediction.setdefault("warning_codes", []).append(error.code)
        else:
            stage = error.stage
            if stage == "llm_metric_selection" and error.code == "invalid_request":
                stage = "metric_selection"
            elif stage == "metric_retrieval":
                stage = "retrieval"
            prediction["error"] = {"stage": stage, "code": error.code}
        return prediction

    assert validated is not None
    clarification = validated.get("clarification_question")
    prediction["selection"] = {
        "status": "ambiguous" if clarification else "resolved",
        "metric_ids": validated["metric_ids"],
        "clarification_question": clarification,
    }
    if clarification:
        prediction["final_status"] = "needs_clarification"
    return prediction


predict = predict_e5
