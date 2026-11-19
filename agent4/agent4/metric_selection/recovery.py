"""Governed selection with at most one recovery action per request."""

from __future__ import annotations

import re
import unicodedata
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from functools import partial
from time import perf_counter
from typing import Any

import httpx

from agent4.core.cache import build_scoped_cache_key, file_revision
from agent4.core.catalog import MetricCatalog
from agent4.core.errors import ContractError

from .catalog_adapter import build_full_catalog_retrieval_result
from .config import FewshotConfig, MetricSelectionConfig, backend_cache_identity
from .embedding import EmbeddingProvider
from .fewshot import EXAMPLE_BANK_VERSION, load_example_bank, retrieve_dynamic_fewshot
from .index import MetricVectorIndex
from .lexical import LEXICAL_INDEX_VERSION, lexical_retrieve
from .llm_selector import (
    INJECTION_PATTERNS,
    LLMMetricSelector,
    SelectionFormatError,
    validate_llm_selection_draft,
)
from .mentions import retrieve_mentions
from .orchestrator import _RETRIEVAL_SELECTION_CACHE, _cache_scope, _retrieve_with_revision
from .validator import require_authorized_view, validate_metrics


@dataclass
class _CheckedSelection:
    draft: dict[str, Any]
    example_ids: list[str]
    retried_schema: bool


@dataclass
class SelectionTrace:
    """Per-request observations, including stages that raised a contract error."""

    initial_retrieved_metric_ids: list[str] = field(default_factory=list)
    retrieved_metric_ids: list[str] = field(default_factory=list)
    retrieval_result: dict[str, Any] | None = None
    selected_example_ids: list[str] = field(default_factory=list)
    stage_latency_ms: dict[str, float] = field(default_factory=dict)
    stage_breakdown_ms: dict[str, float] = field(default_factory=dict)
    stage_status: dict[str, str] = field(default_factory=dict)
    stage_errors: dict[str, dict[str, Any]] = field(default_factory=dict)
    stage_breakdown_status: dict[str, str] = field(default_factory=dict)
    stage_breakdown_errors: dict[str, dict[str, Any]] = field(default_factory=dict)
    recovery_reason: str | None = None
    candidate_expanded: bool = False
    usage: dict[str, int] | None = None
    selection_cache_hit: bool | None = None
    selection_draft: dict[str, Any] | None = None

    @property
    def recovery_triggered(self) -> bool:
        return self.recovery_reason is not None

    @contextmanager
    def measure(self, stage: str):
        with self._measure(stage, detailed=False):
            yield

    @contextmanager
    def measure_detail(self, stage: str):
        with self._measure(stage, detailed=True):
            yield

    @contextmanager
    def _measure(self, stage: str, *, detailed: bool):
        started = perf_counter()
        latency = self.stage_breakdown_ms if detailed else self.stage_latency_ms
        statuses = self.stage_breakdown_status if detailed else self.stage_status
        errors = self.stage_breakdown_errors if detailed else self.stage_errors
        try:
            yield
        except ContractError as exc:
            statuses[stage] = "error"
            errors[stage] = {
                "code": exc.code,
                "stage": exc.stage,
                "retryable": exc.retryable,
                "type": type(exc).__name__,
            }
            raise
        except Exception as exc:
            statuses[stage] = "error"
            errors[stage] = {
                "code": "unexpected_error",
                "stage": stage,
                "retryable": False,
                "type": type(exc).__name__,
            }
            raise
        else:
            statuses[stage] = "ok"
        finally:
            latency[stage] = latency.get(stage, 0.0) + (perf_counter() - started) * 1000


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


class GovernedLexicalSelector:
    """Deterministic governed fallback selector when the remote model is unavailable."""

    _OUT_OF_DOMAIN = re.compile(
        r"\b(?:dự báo|forecast|tỷ giá|giá cổ phiếu|bitcoin|ev/ebitda|altman)\b",
        re.IGNORECASE,
    )

    @classmethod
    def select_draft(
        cls,
        question: str,
        locale: str,
        candidates: list[dict[str, Any]],
        catalog: MetricCatalog,
    ) -> dict[str, Any]:
        vi = locale == "vi-VN"
        normalized = " ".join(unicodedata.normalize("NFKC", question).casefold().split())
        if INJECTION_PATTERNS.search(normalized) or cls._OUT_OF_DOMAIN.search(normalized):
            return validate_llm_selection_draft(
                {
                    "status": "unsupported",
                    "metric_ids": [],
                    "clarification_question": None,
                    "unsupported_reason": (
                        "Chỉ tiêu hoặc yêu cầu nằm ngoài phạm vi hỗ trợ."
                        if vi
                        else "Requested metric is outside the supported catalog."
                    ),
                }
            )
        if not candidates:
            return validate_llm_selection_draft(
                {
                    "status": "unsupported",
                    "metric_ids": [],
                    "clarification_question": None,
                    "unsupported_reason": (
                        "Không tìm thấy chỉ tiêu phù hợp." if vi else "No matching metric found."
                    ),
                }
            )

        # Conservative ambiguity guards before lexical resolution
        if re.search(r"\b(?:công nợ|outstanding balances?|debt)\b", normalized) and not re.search(
            r"\b(?:phải thu|phải trả|khách hàng|nhà cung cấp|ncc|quá hạn|tuổi nợ|"
            r"sắp đến hạn|nhân viên|sales|receivable|payable|loan|vay|debt to equity)\b",
            normalized,
        ):
            return cls._ambiguous(
                "Bạn muốn xem công nợ phải thu hay công nợ phải trả?"
                if vi
                else "Would you like accounts receivable or accounts payable?"
            )
        if not re.search(
            r"\b(?:gộp|ròng|sau thuế|trước thuế|hoạt động|thuần|ebitda|tính thuế|chịu thuế|"
            r"gross|net|operating|before tax|after tax)\b",
            normalized,
        ):
            if re.search(r"\b(?:(?:biên|tỷ suất) lợi nhuận|margin)\b", normalized):
                return cls._ambiguous(
                    "Bạn muốn xem biên lợi nhuận gộp hay biên lợi nhuận ròng?"
                    if vi
                    else "Would you like gross margin or net profit margin?"
                )
            if re.search(r"\b(?:lợi nhuận|lãi|lời|profit)\b", normalized):
                return cls._ambiguous(
                    "Bạn muốn xem lợi nhuận gộp, lợi nhuận hoạt động hay lợi nhuận ròng?"
                    if vi
                    else "Would you like gross profit, operating profit, or net profit?"
                )
        if re.search(r"\bdòng tiền\b", normalized) and not re.search(
            r"\b(?:thuần|biến động|theo nhóm|thu chi|cơ cấu|lưu chuyển)\b", normalized
        ):
            return cls._ambiguous("Bạn muốn xem số dư tiền hay dòng tiền thuần trong kỳ?")

        full_candidates = [catalog.get(item["metric_id"]) or item for item in candidates]
        mention_hits = retrieve_mentions(question, full_candidates)["hits"]
        unique_ids = [hit["metric_id"] for hit in mention_hits if hit["score"] > 0]
        shared_terms = {
            term for hit in mention_hits if hit["score"] == 0 for term in hit["matched_terms"]
        }
        unique_terms = {
            term for hit in mention_hits if hit["score"] > 0 for term in hit["matched_terms"]
        }
        if shared_terms - unique_terms:
            return cls._ambiguous(
                "Bạn vui lòng làm rõ chỉ tiêu tài chính cụ thể muốn tra cứu?"
                if vi
                else "Please clarify which specific financial metric you would like to see."
            )
        if unique_ids:
            periods = {(catalog.get(mid) or {}).get("period_type") for mid in unique_ids[:8]}
            if len(periods) > 1:
                return validate_llm_selection_draft(
                    {
                        "status": "unsupported",
                        "metric_ids": [],
                        "clarification_question": None,
                        "unsupported_reason": (
                            "Không thể kết hợp chỉ tiêu dòng kỳ và số dư."
                            if vi
                            else "Cannot combine flow and snapshot metrics."
                        ),
                    }
                )
            return validate_llm_selection_draft(
                {
                    "status": "resolved",
                    "metric_ids": unique_ids[:8],
                    "clarification_question": None,
                    "unsupported_reason": None,
                }
            )

        allowed_ids = {item["metric_id"] for item in candidates}
        lex_hits = lexical_retrieve(
            {"query": question, "top_k": 5, "index_version": LEXICAL_INDEX_VERSION},
            catalog,
            allowed_metric_ids=allowed_ids,
        )["hits"]
        if not lex_hits or lex_hits[0]["score"] < 2.5:
            return validate_llm_selection_draft(
                {
                    "status": "unsupported",
                    "metric_ids": [],
                    "clarification_question": None,
                    "unsupported_reason": (
                        "Chỉ tiêu chưa có trong danh mục hỗ trợ."
                        if vi
                        else "Metric is not in the supported catalog."
                    ),
                }
            )
        if len(lex_hits) == 1 and lex_hits[0]["score"] >= 3.5:
            return validate_llm_selection_draft(
                {
                    "status": "resolved",
                    "metric_ids": [lex_hits[0]["metric_id"]],
                    "clarification_question": None,
                    "unsupported_reason": None,
                }
            )
        if (
            len(lex_hits) >= 2
            and lex_hits[0]["score"] >= 6.0
            and (lex_hits[0]["score"] - lex_hits[1]["score"]) >= 2.5
        ):
            return validate_llm_selection_draft(
                {
                    "status": "resolved",
                    "metric_ids": [lex_hits[0]["metric_id"]],
                    "clarification_question": None,
                    "unsupported_reason": None,
                }
            )
        return cls._ambiguous(
            "Bạn vui lòng làm rõ chỉ tiêu tài chính cụ thể muốn tra cứu?"
            if vi
            else "Please clarify which specific financial metric you would like to see."
        )

    @staticmethod
    def _ambiguous(prompt: str) -> dict[str, Any]:
        return validate_llm_selection_draft(
            {
                "status": "ambiguous",
                "metric_ids": [],
                "clarification_question": prompt,
                "unsupported_reason": None,
            }
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
        _retrieve_with_revision,
        normalized_query,
        catalog,
        provider,
        auth_context=auth_context,
        query_context=context,
        index=index,
        trace=trace,
    )
    with trace.measure("retrieval_ms"):
        # The retrieval stack contains synchronous provider clients and NumPy
        # index operations. Running it through asyncio.to_thread leaves the
        # Future pending in the supported Python/DuckDB/httpx runtime after a
        # provider call. The Free slice serializes the single expensive query;
        # provider timeouts remain bounded by the selection config.
        retrieval, revision = retrieve(config=config)
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
            retrieval, _ = retrieve(config=lexical_config)
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
        degraded_lexical_fallback=config.recovery.degraded_lexical_fallback,
        llm_lexical_fallback=config.recovery.llm_lexical_fallback,
        retrieval_revision=revision,
        cache_enabled=config.cache_enabled,
    )
    observations = asdict(trace)
    observations.pop("selection_cache_hit")
    # Keep the public selection result contract stable. Detailed diagnostics
    # remain available on the PipelineTrace used by the API logger.
    for key in (
        "stage_breakdown_ms",
        "stage_status",
        "stage_errors",
        "stage_breakdown_status",
        "stage_breakdown_errors",
    ):
        observations.pop(key, None)
    return {**validated, **observations, "recovery_triggered": trace.recovery_triggered}


def _select_examples(
    question: str,
    locale: str,
    candidate_ids: list[str],
    auth_context: dict[str, Any],
    query_context: dict[str, Any],
    config: FewshotConfig,
    *,
    catalog_hash: str,
    cache_enabled: bool,
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
        load_example_bank(
            config.example_bank_path, catalog_hash=catalog_hash, cache_enabled=cache_enabled
        ),
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
    degraded_lexical_fallback: bool = False,
    llm_lexical_fallback: bool = False,
    retrieval_revision: str | None = None,
    cache_enabled: bool = True,
) -> dict[str, Any]:
    trace.retrieved_metric_ids = _candidate_ids(retrieval)
    trace.retrieval_result = retrieval
    key = None
    if (
        retrieval_revision is not None
        and type(selector) is LLMMetricSelector
        and trace.recovery_reason in (None, "empty_candidates")
        and trace.retrieved_metric_ids
    ):
        key = _selection_key(
            retrieval_revision, catalog, auth_context, query_context, selector, seed, fewshot, trace
        )
    cached = _RETRIEVAL_SELECTION_CACHE.get(key) if key is not None else None
    trace.selection_cache_hit = cached is not None if key is not None else None

    draft = {
        "status": "unsupported",
        "metric_ids": [],
        "clarification_question": None,
        "unsupported_reason": None,
    }
    degraded_llm = False
    if cached is not None:
        draft = cached.draft
        trace.selected_example_ids = cached.example_ids
        trace.usage = {"input_tokens": 0, "output_tokens": 0}
        if cached.retried_schema:
            trace.recovery_reason = "invalid_selection_format"
    elif trace.retrieved_metric_ids:
        allowed_views = set(auth_context["allowed_views"])
        candidates = []
        for row in retrieval["candidates"]:
            metric_id = row["metric_id"]
            metric = catalog.get(metric_id)
            metric["supported_views"] = sorted(
                allowed_views.intersection(metric["supported_views"])
            )
            if row.get("mention_score", 0) > 0:
                metric["matched_terms"] = row["matched_terms"]
            candidates.append(metric)
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
                    catalog_hash=catalog.get_catalog_hash(),
                    cache_enabled=cache_enabled,
                )
                trace.selected_example_ids = [example["example_id"] for example in examples]
        select = partial(selector.select, question, candidates, examples=examples, seed=seed)
        with trace.measure("llm_ms"), trace.measure_detail("llm_metric_selection"):
            try:
                draft, trace.usage = await select()
            except SelectionFormatError as exc:
                if trace.recovery_triggered or not retry_schema:
                    raise
                trace.recovery_reason = "invalid_selection_format"
                draft, usage = await select(remind_schema=True)
                if exc.usage is not None and usage is not None:
                    trace.usage = {key: exc.usage[key] + usage[key] for key in usage}
            except ContractError as exc:
                is_offline_transport = exc.__cause__ is None or isinstance(
                    exc.__cause__, (httpx.RequestError, httpx.InvalidURL)
                )
                can_fallback = llm_lexical_fallback or (
                    degraded_lexical_fallback and is_offline_transport
                )
                if (
                    exc.code != "llm_unavailable"
                    or not can_fallback
                    or trace.recovery_reason not in (None, "retrieval_unavailable")
                ):
                    raise
                if trace.recovery_reason is None:
                    trace.recovery_reason = "llm_unavailable"
                degraded_llm = True
                draft = GovernedLexicalSelector.select_draft(
                    question, locale, candidates, catalog
                )

    # Record only the schema-checked status and IDs the model was allowed to see.
    candidates = set(trace.retrieved_metric_ids)
    draft_ids = draft["metric_ids"]
    trace.selection_draft = {
        "status": draft["status"],
        "candidate_metric_ids": [metric_id for metric_id in draft_ids if metric_id in candidates],
        "outside_candidate_count": sum(metric_id not in candidates for metric_id in draft_ids),
    }
    with trace.measure("validation_ms"):
        try:
            validated = validate_metrics(draft, retrieval, catalog, auth_context, query_context)
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
            validated = validate_metrics(draft, expanded, catalog, auth_context, query_context)
    if key is not None and cached is None and not degraded_llm:
        _RETRIEVAL_SELECTION_CACHE.set(
            key,
            _CheckedSelection(
                draft,
                trace.selected_example_ids,
                trace.recovery_reason == "invalid_selection_format",
            ),
            row_count=len(draft["metric_ids"]),
        )
    return validated


def _selection_key(
    revision: str,
    catalog: MetricCatalog,
    auth_context: dict[str, Any],
    context: dict[str, Any],
    selector: LLMMetricSelector,
    seed: int,
    fewshot: FewshotConfig | None,
    trace: SelectionTrace,
) -> str | None:
    scope = _cache_scope(auth_context, catalog.get_catalog_hash())
    if scope is None:
        return None
    relevant = {
        key: context[key]
        for key in ("requested_view", "requested_dimensions", "requested_operation", "time_mode")
        if key in context
    }
    if "requested_dimensions" in relevant and not isinstance(
        relevant["requested_dimensions"], list
    ):
        return None
    try:
        bank_revision = None
        if fewshot and fewshot.max_examples and fewshot.token_budget and fewshot.strategy != "zero":
            bank_revision = file_revision(fewshot.example_bank_path)
        return build_scoped_cache_key(
            "validated-selection",
            **scope,
            retrieval_revision=revision,
            candidate_ids=trace.retrieved_metric_ids,
            prior_recovery=trace.recovery_reason,
            query_context=relevant,
            selector=backend_cache_identity(selector.config),
            seed=seed,
            example_bank=bank_revision,
        )
    except (OSError, TypeError):
        # Uncacheable context or artifact still goes through the normal selection path.
        return None
