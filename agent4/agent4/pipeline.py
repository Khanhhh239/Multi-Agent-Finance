"""Production orchestration for the governed query contracts."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from functools import cache
from pathlib import Path
from uuid import uuid4

from agent4.answer.evidence import build_evidence_preview
from agent4.answer.generator import generate_grounded_answer
from agent4.answer.result_validator import safe_display_text, validate_result
from agent4.answer.validator import validate_answer
from agent4.core.catalog import LEGACY_METRIC_IDS, MetricCatalog
from agent4.core.config import AppConfig
from agent4.core.context import (
    ROW_SCOPE_FIELDS,
    build_auth_context,
    build_runtime_context,
    query_intake,
)
from agent4.core.errors import FINAL_STATUSES, ContractError
from agent4.engine.metrics import REGISTRY
from agent4.metric_selection.config import MetricSelectionConfig, load_config
from agent4.metric_selection.recovery import SelectionTrace, select_metrics_with_recovery
from agent4.planning.clarification import ClarificationSessionStore, resolve_clarification_turn
from agent4.planning.planner import _filters, build_semantic_plan_draft, detect_query_views
from agent4.planning.validator import (
    PlanClarification,
    validate_requested_row_scope,
    validate_semantic_plan_draft,
)
from agent4.sql.compiler import compile_sql
from agent4.sql.executor import _RESULT_CACHE, execute_safe_sql
from agent4.sql.safety import validate_sql_safety

_LOG = logging.getLogger(__name__)
_SESSIONS = ClarificationSessionStore()
_DATA_KEYS = ("columns", "rows", "row_count", "truncated")
_WRITE_INTENT = re.compile(
    r"\b(?:execute|make|send|initiate)\s+(?:a\s+)?(?:wire transfer|payment)\b"
    r"|\b(?:xóa bút toán|hạch toán lại|thực hiện chuyển khoản|thanh toán cho nhà cung cấp)\b",
    re.IGNORECASE,
)


@dataclass
class PipelineTrace:
    selection: SelectionTrace = field(default_factory=SelectionTrace)
    selected_metrics: dict | None = None
    plan: dict | None = None
    execution: dict | None = None
    sql_cache_hit: bool | None = None
    include_demo_evidence: bool = False
    demo_evidence: dict | None = field(default=None, repr=False)


def build_final_response(
    request_id: str,
    status: str,
    *,
    error: ContractError | None = None,
    answer: str = "",
    data: dict | None = None,
    interpretation: dict | None = None,
    provenance: dict | None = None,
    warnings: list[str] | None = None,
    evidence: dict | None = None,
    clarification: dict | None = None,
) -> dict:
    if status not in FINAL_STATUSES:
        raise ContractError("invalid_request", "final_response", "Invalid final status.")
    response = {
        "api_version": "v1",
        "request_id": request_id,
        "status": status,
        "error": error.to_dict() if error else None,
        "answer": answer,
        "data": data,
        "interpretation": interpretation,
        "provenance": provenance,
        "warnings": warnings or [],
    }
    if evidence is not None:
        response["evidence"] = evidence
    if clarification is not None:
        response["clarification"] = clarification
    return response


def build_observability_record(
    response: dict,
    trace_id: str,
    trace: PipelineTrace,
    catalog_hash: str,
    config: MetricSelectionConfig,
) -> dict:
    """Project telemetry explicitly to avoid logging prompts, SQL or result rows."""
    data = response["data"] or {}
    provenance = response["provenance"] or {}
    selection = trace.selection
    retrieval = selection.retrieval_result or {}
    return {
        "request_id": response["request_id"],
        "trace_id": trace_id,
        "catalog_hash": catalog_hash,
        "model": config.llm.model,
        "prompt_version": config.prompt_version,
        "dense_index_version": retrieval.get("dense_index_version"),
        "embedding_model": retrieval.get("embedding_model"),
        "stage_latencies_ms": dict(selection.stage_latency_ms),
        "candidate_count": len(selection.retrieved_metric_ids),
        "selected_metric_ids": (trace.selected_metrics or {}).get("metric_ids", []),
        "selected_example_ids": list(selection.selected_example_ids),
        "usage": selection.usage,
        "query_fingerprint": provenance.get("query_fingerprint"),
        "data_watermark": provenance.get("data_watermark"),
        "row_count": data.get("row_count"),
        "truncated": data.get("truncated"),
        "status": response["status"],
        "error_code": (response["error"] or {}).get("code"),
        "cache_stats": {
            "selection_hit": selection.selection_cache_hit,
            "sql_result_hit": trace.sql_cache_hit,
            "sql_result": _RESULT_CACHE.stats(),
        },
    }


async def run_governed_pipeline(
    request_payload: dict,
    idp_claims: dict | None,
    server_policy: dict | None,
    *,
    warehouses: dict[str, Path] | None = None,
    app_config: AppConfig | None = None,
    selection_config: MetricSelectionConfig | None = None,
    catalog: MetricCatalog | None = None,
    sessions: ClarificationSessionStore | None = None,
    trace: PipelineTrace | None = None,
    seed: int = 20261101,
) -> dict:
    request_id, trace_id = uuid4().hex, uuid4().hex
    app_config = app_config or AppConfig()
    config = selection_config or load_config()
    catalog = catalog or MetricCatalog(canonical=True)
    sessions = sessions if sessions is not None else _SESSIONS
    trace = trace if trace is not None else PipelineTrace()
    if trace.include_demo_evidence:
        trace.demo_evidence = {"trace_id": trace_id}
    if warehouses is None:
        tenant = os.getenv("AGENT4_WAREHOUSE_TENANT_ID")
        warehouses = {tenant: app_config.db_path} if tenant else {}
    try:
        response = await _run(
            request_payload,
            idp_claims,
            server_policy,
            request_id,
            trace_id,
            warehouses,
            app_config,
            config,
            catalog,
            sessions,
            trace,
            seed,
        )
    except ContractError as exc:
        response = build_final_response(request_id, exc.final_status, error=exc)
    _LOG.info(
        "governed_query",
        extra={
            "query_event": build_observability_record(
                response, trace_id, trace, catalog.get_catalog_hash(), config
            )
        },
    )
    return response


async def _run(
    payload,
    claims,
    policy,
    request_id,
    trace_id,
    warehouses,
    app_config,
    config,
    catalog,
    sessions,
    trace,
    seed,
) -> dict:
    measure = trace.selection.measure
    with measure("intake"):
        auth = build_auth_context(claims, policy)
        query = query_intake(payload, app_config.max_question_length)
        options = query["options"]
        if options.get("use_cache") is False:
            config = config.model_copy(update={"cache_enabled": False})
        locale = query["locale"]
        tenant = auth["tenant_id"]
        runtime = build_runtime_context(
            request_id, trace_id, auth, locale, "Asia/Ho_Chi_Minh", catalog.get_catalog_hash()
        )
    sid = query.get("session_id")
    cap = min(1000, app_config.default_row_cap)
    if sid is not None:
        with measure("clarification"):
            plan = resolve_clarification_turn(
                sessions, sid, query["question"], catalog, auth, row_cap=cap
            )
        if isinstance(plan, dict):
            return build_final_response(
                request_id,
                "needs_clarification",
                answer=plan["question_for_user"],
                clarification=plan,
            )
    else:
        with measure("request_scope"):
            views = _check_request_scope(query["question"], catalog, auth)
        context = {}
        if len(views) == 1:
            context["requested_view"] = next(iter(views))
        elif not views and "mgmt" not in auth["allowed_views"] and "tax" in auth["allowed_views"]:
            context["requested_view"] = "tax"
        with measure("metric_selection"):
            metrics = await select_metrics_with_recovery(
                query,
                catalog,
                auth_context=auth,
                query_context=context,
                config=config,
                seed=seed,
                trace=trace.selection,
            )
        trace.selected_metrics = {
            key: metrics.get(key) for key in ("status", "metric_ids", "clarification_question")
        }
        with measure("planning"):
            draft = build_semantic_plan_draft(query, metrics, context)
            trace.plan = draft
        with measure("plan_validation"):
            plan = validate_semantic_plan_draft(draft, metrics, catalog, auth, row_cap=cap)
        if isinstance(plan, PlanClarification):
            clarification = None
            if options.get("clarification_mode") == "guided":
                with measure("clarification"):
                    session_query = query
                    if len(warehouses) == 1 and tenant in warehouses:
                        session_query = {
                            **query,
                            "reporting_calendar": {
                                "data_watermark": app_config.reporting_data_watermark,
                                "last_closed_month": app_config.reporting_last_closed_month,
                            },
                        }
                    clarification = sessions.start(draft, metrics, catalog, auth, session_query)
            return build_final_response(
                request_id,
                "needs_clarification",
                answer=plan.question_for_user,
                clarification=clarification,
            )
    if tenant not in warehouses:
        raise ContractError(
            "forbidden", "sql_safety", "Warehouse access is unavailable.", final_status="forbidden"
        )
    with measure("sql_compiler"):
        bound = compile_sql(plan, catalog, row_cap=cap)
    with measure("sql_safety"):
        safe = validate_sql_safety(
            bound,
            catalog,
            runtime,
            warehouse_tenant_id=tenant,
            warehouse_path=warehouses[tenant],
        )
    trace.execution = {
        "attempted": True,
        "succeeded": False,
        "safety_passed": True,
        "query_fingerprint": bound.fingerprint,
    }
    with measure("sql_execution"):
        execution = await asyncio.to_thread(
            execute_safe_sql,
            safe,
            timeout_ms=app_config.query_timeout_ms,
            use_cache=config.cache_enabled,
        )
    trace.execution["succeeded"] = True
    trace.sql_cache_hit = execution["cache_hit"]
    with measure("result_validation"):
        result = validate_result(execution, plan, catalog)
    with measure("answer"):
        draft_answer = generate_grounded_answer(plan, result, catalog, locale=locale)
        answer = validate_answer(draft_answer, result, plan, catalog, locale=locale)
    evidence = None
    if options.get("include_evidence_preview"):
        with measure("evidence"):
            evidence = build_evidence_preview(
                answer,
                result,
                plan,
                catalog,
                bound,
                locale=locale,
                explain_metrics=options["explain_metrics"],
            )
    data = {key: result["result"][key] for key in _DATA_KEYS}
    if not options["include_table"]:
        data.update(columns=[], rows=[])
    time = {
        key: value.isoformat() if hasattr(value, "isoformat") else value
        for key, value in asdict(plan.time).items()
    }
    if trace.demo_evidence is not None:
        trace.demo_evidence.update(
            sql=safe["safe_bound_query"].query.sql,
            semantic_plan={
                "metric_ids": list(plan.metric_ids),
                "operation": plan.operation,
                "view": plan.view,
                "time": time,
                "dimensions": list(plan.dimensions),
                "filters": [
                    {**asdict(item), "value": "[REDACTED]"}
                    if item.field == "partner_code"
                    else asdict(item)
                    for item in plan.filters
                ],
                "sort": asdict(plan.sort) if plan.sort else None,
                "top_k": plan.top_k,
                "row_cap": plan.row_cap,
            },
        )
    return build_final_response(
        request_id,
        "no_data" if result["status"] == "no_data" else "ready",
        answer=answer["answer"],
        data=data,
        interpretation={
            "metric_ids": list(plan.metric_ids),
            "dimensions": list(plan.dimensions),
            "view": plan.view,
            "time": time,
        },
        provenance={
            "catalog_hash": bound.catalog_hash,
            "data_watermark": execution["data_watermark"],
            "source": plan.view,
            "query_fingerprint": bound.fingerprint,
        },
        warnings=answer["warnings"],
        evidence=evidence,
    )


@cache
def _registry_labels() -> tuple[tuple[str, str], ...]:
    return tuple(
        (label, metric.id)
        for metric in REGISTRY.values()
        for label in (metric.id, metric.label.casefold())
    )


def _check_request_scope(question: str, catalog: MetricCatalog, auth: dict) -> set[str]:
    original = unicodedata.normalize("NFKC", question)
    normalized = " ".join(original.casefold().split())
    try:
        views = detect_query_views(normalized)
    except ContractError:
        raise _unsupported_request() from None
    if safe_display_text(normalized) == "[REDACTED]" or _WRITE_INTENT.search(normalized):
        raise _unsupported_request()

    if len(views) == 1 and not views.issubset(auth["allowed_views"]):
        raise ContractError(
            "forbidden_metric",
            "request_scope",
            "Requested view is not authorized.",
            final_status="forbidden",
        )
    row_restricted = any(key in auth and auth[key] != ["*"] for key in ROW_SCOPE_FIELDS)
    if row_restricted:
        filters, _ = _filters(normalized, original)
        validate_requested_row_scope(filters, auth)

    allowed = auth["allowed_metrics"]
    for identifier in re.findall(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b", normalized):
        if catalog.contains(identifier):
            capability = catalog.get_capability(identifier)
            if capability["metadata_only"]:
                raise ContractError(
                    "unsupported_metric",
                    "request_scope",
                    "Metric has no verified handler.",
                    final_status="unsupported",
                )
            if capability["status"] != "approved" or capability["verified_handler"] is not True:
                raise _unsupported_request()
            if allowed is not None and identifier not in allowed:
                raise _forbidden_metric()
    if allowed is not None:
        matched: dict[str, set[str]] = {}
        for label, metric_id in _registry_labels():
            if re.search(rf"\b{re.escape(label)}\b", normalized):
                matched.setdefault(label, set()).add(metric_id)
        labels = catalog.list_approved_metrics()
        labels.extend(
            catalog.list_metrics(
                approved_only=True,
                allowed_metrics=[alias for alias in LEGACY_METRIC_IDS if alias in allowed],
            )
        )
        for metric in labels:
            terms = [metric.get(field) for field in ("metric_id", "label", "label_en")]
            if row_restricted:
                terms.extend(metric.get("aliases", []))
            for term in terms:
                label = (term or "").casefold()
                if label and re.search(rf"\b{re.escape(label)}\b", normalized):
                    matched.setdefault(label, set()).add(metric["metric_id"])
        for label, metric_ids in matched.items():
            if any(label != other and label in other for other in matched):
                continue
            if not metric_ids.intersection(allowed):
                raise _forbidden_metric()
    return views


def _forbidden_metric() -> ContractError:
    return ContractError(
        "forbidden_metric",
        "request_scope",
        "Requested metric is not authorized.",
        final_status="forbidden",
    )


def _unsupported_request() -> ContractError:
    return ContractError(
        "unsupported_request",
        "request_scope",
        "This request is outside the read-only query contract.",
        final_status="unsupported",
    )
