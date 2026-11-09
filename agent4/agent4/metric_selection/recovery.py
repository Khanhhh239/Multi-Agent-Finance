"""Governed selection with at most one recovery action per request."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from functools import partial
from time import perf_counter
from typing import Any

from agent4.core.catalog import MetricCatalog
from agent4.core.errors import ContractError

from .catalog_adapter import build_full_catalog_retrieval_result
from .config import FewshotConfig, MetricSelectionConfig
from .embedding import EmbeddingProvider
from .fewshot import EXAMPLE_BANK_VERSION, load_example_bank, retrieve_dynamic_fewshot
from .index import MetricVectorIndex
from .llm_selector import LLMMetricSelector, SelectionFormatError
from .orchestrator import orchestrate_retrieval
from .validator import require_authorized_view, validate_metrics


@dataclass
class SelectionTrace:
    """Per-request observations, including stages that raised a contract error."""

    initial_retrieved_metric_ids: list[str] = field(default_factory=list)
    retrieved_metric_ids: list[str] = field(default_factory=list)
    retrieval_result: dict[str, Any] | None = None
    selected_example_ids: list[str] = field(default_factory=list)
    stage_latency_ms: dict[str, float] = field(default_factory=dict)
    recovery_reason: str | None = None
    candidate_expanded: bool = False
    usage: dict[str, int] | None = None

    @property
    def recovery_triggered(self) -> bool:
        return self.recovery_reason is not None

    @contextmanager
    def measure(self, stage: str):
        started = perf_counter()
        try:
            yield
        finally:
            self.stage_latency_ms[stage] = (
                self.stage_latency_ms.get(stage, 0.0) + (perf_counter() - started) * 1000
            )


def _candidate_ids(retrieval: dict[str, Any]) -> list[str]:
    return [candidate["metric_id"] for candidate in retrieval["candidates"]]


def _retrieval_unavailable() -> ContractError:
    return ContractError(
        "retrieval_unavailable",
        "metric_retrieval",
        "Metric retrieval is temporarily unavailable.",
        retryable=True,
        final_status="temporarily_unavailable",
    )


async def select_metrics_with_recovery(
    normalized_query: dict[str, Any],
    catalog: MetricCatalog,
    *,
    auth_context: dict[str, Any],
    query_context: dict[str, Any] | None = None,
    config: MetricSelectionConfig | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    index: MetricVectorIndex | None = None,
    selector: LLMMetricSelector | None = None,
    seed: int = 20261101,
    trace: SelectionTrace | None = None,
) -> dict[str, Any]:
    """Retrieve, select, and validate. A fresh trace also captures failed calls."""
    config = config or MetricSelectionConfig()
    trace = trace if trace is not None else SelectionTrace()
    context = query_context or {}
    require_authorized_view(auth_context, context)
    provider = embedding_provider or EmbeddingProvider(config.embedding)
    retrieve = partial(
        orchestrate_retrieval,
        normalized_query,
        catalog,
        provider,
        auth_context=auth_context,
        query_context=context,
        index=index,
    )
    with trace.measure("retrieval_ms"):
        if (
            provider.config.provider == "ollama"
            and config.retrieval.mode in ("dense_only", "hybrid")
            and config.retrieval.dense_enabled
        ):
            retrieval = await asyncio.to_thread(retrieve, config=config)
        else:
            retrieval = retrieve(config=config)
        trace.initial_retrieved_metric_ids = _candidate_ids(retrieval)
        status = retrieval["status"]
        if status == "retrieval_unavailable":
            if trace.recovery_triggered or not config.recovery.degraded_lexical_fallback:
                raise _retrieval_unavailable()
            trace.recovery_reason = status
            lexical_config = config.model_copy(
                update={
                    "retrieval": config.retrieval.model_copy(
                        update={"mode": "lexical_only", "lexical_enabled": True}
                    ),
                    "expansion": config.expansion.model_copy(update={"enabled": False}),
                }
            )
            retrieval = retrieve(config=lexical_config)
            if retrieval["status"] != "candidates_found":
                raise _retrieval_unavailable()
            for candidate in retrieval["candidates"]:
                candidate["retrieval_sources"] = ["lexical_fallback"]
        elif (
            status == "empty_candidates"
            and not trace.recovery_triggered
            and config.recovery.enable_empty_candidate_fallback
            and config.retrieval.mode != "full_catalog"
        ):
            trace.recovery_reason = status
            retrieval = build_full_catalog_retrieval_result(
                normalized_query["question"], catalog, auth_context
            )
            for candidate in retrieval["candidates"]:
                candidate["retrieval_sources"] = ["catalog_full_fallback"]

    validated = await _select_from_retrieval(
        normalized_query["question"],
        normalized_query["locale"],
        retrieval,
        catalog,
        auth_context,
        context,
        selector or LLMMetricSelector(config.llm),
        seed,
        trace,
        fewshot=config.fewshot if config.fewshot.enabled else None,
        retry_schema=config.llm.max_retries == 1,
        expand_candidates=config.recovery.enable_candidate_expansion,
    )
    return {**validated, **asdict(trace), "recovery_triggered": trace.recovery_triggered}


def _select_examples(
    question: str,
    locale: str,
    candidate_ids: list[str],
    auth_context: dict[str, Any],
    query_context: dict[str, Any],
    config: FewshotConfig,
) -> list[dict[str, Any]]:
    view = query_context.get("requested_view") or "mgmt"
    if (
        view not in auth_context["allowed_views"]
        or not config.max_examples
        or not config.token_budget
        or config.strategy == "zero"
    ):
        return []
    context: dict[str, Any] = {"view": view}
    if "requested_dimensions" in query_context:
        context["dimensions"] = query_context["requested_dimensions"]
    if "time_mode" in query_context:
        context["time_mode"] = query_context["time_mode"]
    return retrieve_dynamic_fewshot(
        {
            "question": question,
            "locale": locale,
            "candidate_metric_ids": candidate_ids,
            "context": context,
            "max_examples": config.max_examples,
            "token_budget": config.token_budget,
            "selection_strategy": config.strategy,
            "example_bank_version": EXAMPLE_BANK_VERSION,
            "compatible_only": True,
        },
        load_example_bank(config.example_bank_path),
        config=config,
    )["examples"]


async def _select_from_retrieval(
    question: str,
    locale: str,
    retrieval: dict[str, Any],
    catalog: MetricCatalog,
    auth_context: dict[str, Any],
    query_context: dict[str, Any],
    selector: LLMMetricSelector,
    seed: int,
    trace: SelectionTrace,
    *,
    fewshot: FewshotConfig | None = None,
    retry_schema: bool = False,
    expand_candidates: bool = False,
) -> dict[str, Any]:
    trace.retrieved_metric_ids = _candidate_ids(retrieval)
    trace.retrieval_result = retrieval
    allowed_views = set(auth_context["allowed_views"])
    candidates = []
    for metric_id in trace.retrieved_metric_ids:
        metric = catalog.get(metric_id)
        metric["supported_views"] = sorted(allowed_views.intersection(metric["supported_views"]))
        candidates.append(metric)

    draft = {
        "status": "unsupported",
        "metric_ids": [],
        "clarification_question": None,
        "unsupported_reason": None,
    }
    if candidates:
        examples = None
        if fewshot is not None:
            with trace.measure("fewshot_ms"):
                examples = _select_examples(
                    question,
                    locale,
                    trace.retrieved_metric_ids,
                    auth_context,
                    query_context,
                    fewshot,
                )
                trace.selected_example_ids = [example["example_id"] for example in examples]
        select = partial(selector.select, question, candidates, examples=examples, seed=seed)
        with trace.measure("llm_ms"):
            try:
                draft, trace.usage = await select()
            except SelectionFormatError as exc:
                if trace.recovery_triggered or not retry_schema:
                    raise
                trace.recovery_reason = "invalid_selection_format"
                draft, usage = await select(remind_schema=True)
                if exc.usage is not None and usage is not None:
                    trace.usage = {key: exc.usage[key] + usage[key] for key in usage}

    with trace.measure("validation_ms"):
        try:
            return validate_metrics(draft, retrieval, catalog, auth_context, query_context)
        except ContractError as exc:
            if (
                exc.code != "metric_outside_candidates"
                or not expand_candidates
                or trace.recovery_triggered
            ):
                raise
            missing = set(draft["metric_ids"]) - set(trace.retrieved_metric_ids)
            visible = {metric["metric_id"] for metric in catalog.list_visible_metrics(auth_context)}
            if not missing or not missing <= visible:
                raise
            trace.recovery_reason = exc.code
            trace.candidate_expanded = True
            added = [metric_id for metric_id in draft["metric_ids"] if metric_id in missing]
            expanded = {
                **retrieval,
                "candidate_expanded": True,
                "candidates": [
                    *retrieval["candidates"],
                    *(
                        {
                            "metric_id": metric_id,
                            "rank": rank,
                            "retrieval_sources": ["candidate_expansion"],
                            "dense_score": None,
                            "lexical_score": None,
                            "fusion_score": None,
                            "rerank_score": None,
                        }
                        for rank, metric_id in enumerate(
                            added, start=len(trace.retrieved_metric_ids) + 1
                        )
                    ),
                ],
            }
            trace.retrieved_metric_ids = _candidate_ids(expanded)
            trace.retrieval_result = expanded
            return validate_metrics(draft, expanded, catalog, auth_context, query_context)
