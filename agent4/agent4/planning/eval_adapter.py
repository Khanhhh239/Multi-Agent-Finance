"""Offline, input-only adapter for the M2.1 clarification benchmark.

A catalog phrase matcher supplies M1 inputs for this component evaluation.
Metric validation and planning use the production implementations.
"""

from __future__ import annotations

import re
from functools import cache
from time import perf_counter
from typing import Any

from agent4.core.context import query_intake
from agent4.core.errors import ContractError
from agent4.metric_selection.catalog_adapter import (
    build_canonical_catalog,
    build_full_catalog_retrieval_result,
)
from agent4.metric_selection.validator import validate_metrics

# English aliases and deliberately ambiguous terms missing from the registry.
_ALIASES = {
    "admin_expenses": ("administrative expense", "administrative expenses"),
    "debt_balance": ("loan balance", "outstanding loan"),
    "gross_margin_pct": ("profit margin", "tỷ suất lợi nhuận", "biên lợi nhuận"),
    "net_margin_pct": ("profit margin", "biên lợi nhuận"),
    "gross_profit": ("profit", "lợi nhuận"),
    "net_profit": ("profit", "lợi nhuận"),
    "ar_balance": ("công nợ", "outstanding balance"),
    "ap_balance": ("công nợ", "outstanding balance"),
}


@cache
def _catalog():
    return build_canonical_catalog()


@cache
def _aliases() -> tuple[tuple[str, re.Pattern[str]], ...]:
    return tuple(
        (metric_id, re.compile(r"\b(?:" + "|".join(map(re.escape, terms)) + r")\b"))
        for metric in _catalog().list_approved_metrics()
        for metric_id in [metric["metric_id"]]
        if (
            terms := sorted(
                {
                    metric["label"].casefold(),
                    metric_id.replace("_", " "),
                    *[term.casefold() for term in metric["aliases"]],
                    *_ALIASES.get(metric_id, ()),
                },
                key=lambda term: (-len(term), term),
            )
        )
    )


def _selection(question: str, locale: str) -> dict[str, Any]:
    mentions: dict[tuple[int, int], set[str]] = {}
    for metric_id, pattern in _aliases():
        for match in pattern.finditer(question):
            mentions.setdefault(match.span(), set()).add(metric_id)

    # Prefer a specific metric name over shorter phrases nested in it.
    chosen: list[tuple[int, int]] = []
    ids: set[str] = set()
    ambiguous = False
    for start, end in sorted(mentions, key=lambda span: (span[0] - span[1], span)):
        if any(start < other_end and other_start < end for other_start, other_end in chosen):
            continue
        chosen.append((start, end))
        matched = mentions[(start, end)]
        ambiguous |= len(matched) > 1
        ids.update(matched)
    status = "ambiguous" if ambiguous else "resolved" if ids else "unsupported"
    clarification = {
        "en-US": "Which financial metric would you like to see?",
        "vi-VN": "Bạn muốn xem chỉ tiêu tài chính nào?",
    }
    return {
        "status": status,
        "metric_ids": sorted(ids) if status == "resolved" else [],
        "clarification_question": clarification[locale] if ambiguous else None,
        "unsupported_reason": None,
    }


def _prepare(request: dict[str, Any]) -> tuple[dict, dict, dict]:
    query = query_intake(
        {
            "api_version": "v1",
            "question": request["user_query"],
            "locale": request["locale"],
            "options": request.get("options"),
        }
    )
    draft = _selection(query["normalized_question"], query["locale"])
    catalog = _catalog()
    auth = request["auth_context"]
    context = request["query_context"]
    candidates = build_full_catalog_retrieval_result(query["question"], catalog, auth)
    metrics = validate_metrics(draft, candidates, catalog, auth, context)
    selection = {
        "status": draft["status"],
        "metric_ids": metrics["metric_ids"],
        "clarification_question": draft["clarification_question"],
    }
    return query, metrics, selection


def _benchmark_plan(draft: dict, question: str) -> dict:
    """Translate the planning contract into the runner's v2 schema."""
    aliases = {"branch_code": "branch", "department_code": "department"}
    if re.search(r"\b(?:khách hàng|customers?|kh\d+|khle-\w+)\b", question):
        aliases["partner_code"] = "customer"
    elif re.search(r"\b(?:nhà cung cấp|vendors?|suppliers?|ncc-[\w-]+)\b", question):
        aliases["partner_code"] = "vendor"
    return {
        **draft,
        "operation": {"ranking": "rank"}.get(draft["operation"], draft["operation"]),
        "dimensions": [aliases.get(dim, dim) for dim in draft["dimensions"]],
        "filters": [
            {
                "field": aliases.get(flt["field"], flt["field"]),
                "operator": {"=": "eq", "IN": "in"}[flt["op"]],
                "values": [flt["value"]] if flt["op"] == "=" else flt["value"],
            }
            for flt in draft["filters"]
        ],
    }


async def predict_baseline(request: dict[str, Any]) -> dict[str, Any]:
    """Run the same upstream stages without the planner absent at baseline."""
    try:
        _, metrics, selection = _prepare(request)
    except ContractError as error:
        return _error_prediction(request, error)
    return {
        "id": request["id"],
        "selection": selection,
        "final_status": "needs_clarification"
        if metrics["status"] == "needs_clarification"
        else None,
    }


async def predict(request: dict[str, Any]) -> dict[str, Any]:
    # Keep baseline runnable in a checkout without planner.py.
    from agent4.planning.planner import build_semantic_plan_draft

    try:
        query, metrics, selection = _prepare(request)
        started = perf_counter()
        draft = build_semantic_plan_draft(query, metrics, request["query_context"])
        planning_ms = (perf_counter() - started) * 1000
    except ContractError as error:
        return _error_prediction(request, error)
    return {
        "id": request["id"],
        "selection": selection,
        "plan": _benchmark_plan(draft, query["normalized_question"]),
        "final_status": draft["status"],
        "stage_latency_ms": {"planning_ms": planning_ms},
    }


def _error_prediction(request: dict[str, Any], error: ContractError) -> dict[str, Any]:
    return {
        "id": request["id"],
        "final_status": error.final_status,
        "error": {"stage": error.stage, "code": error.code},
    }
