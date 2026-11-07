"""Input-only adapter for the E0 full-catalog benchmark."""

from __future__ import annotations

from functools import cache
from time import perf_counter
from typing import Any

from agent4.core.errors import ContractError

from .catalog_adapter import build_canonical_catalog, build_full_catalog_retrieval_result
from .config import load_config
from .errors import ConfigurationError
from .llm_selector import LLMMetricSelector
from .validator import validate_metrics


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
    question = request["user_query"]
    auth = request["auth_context"]
    retrieval = build_full_catalog_retrieval_result(question, catalog, auth)
    candidate_ids = [candidate["metric_id"] for candidate in retrieval["candidates"]]
    candidates = []
    allowed_views = set(auth["allowed_views"])
    for metric_id in candidate_ids:
        metric = catalog.get(metric_id)
        metric["supported_views"] = sorted(allowed_views.intersection(metric["supported_views"]))
        candidates.append(metric)
    stage_latency = {"retrieval_ms": (perf_counter() - started) * 1000}
    prediction = {
        "id": request["id"],
        "retrieved_metric_ids": candidate_ids,
        "stage_latency_ms": stage_latency,
    }

    if candidates:
        started = perf_counter()
        try:
            draft, usage = await selector.select(question, candidates, seed=request["seed"])
            prediction["usage"] = usage
        except ContractError as exc:
            stage = "metric_selection" if exc.code == "invalid_request" else exc.stage
            return {
                **prediction,
                "final_status": exc.final_status,
                "error": {"stage": stage, "code": exc.code},
            }
        finally:
            stage_latency["llm_ms"] = (perf_counter() - started) * 1000
    else:
        draft = {
            "status": "unsupported",
            "metric_ids": [],
            "clarification_question": None,
            "unsupported_reason": None,
        }

    started = perf_counter()
    try:
        validated = validate_metrics(draft, retrieval, catalog, auth, request["query_context"])
    except ContractError as exc:
        return {
            **prediction,
            "selection": {"status": "unsupported", "metric_ids": []},
            "final_status": exc.final_status,
            "warning_codes": [exc.code],
        }
    finally:
        stage_latency["validation_ms"] = (perf_counter() - started) * 1000

    clarification = validated.get("clarification_question")
    prediction["selection"] = {
        "status": "ambiguous" if clarification else "resolved",
        "metric_ids": validated["metric_ids"],
        "clarification_question": clarification,
    }
    if clarification:
        prediction["final_status"] = "needs_clarification"
    return prediction


predict = predict_e0
