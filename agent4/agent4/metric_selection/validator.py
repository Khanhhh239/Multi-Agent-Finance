"""Deterministic authority for metric selections."""

from __future__ import annotations

from typing import Any

from agent4.core.catalog import MetricCatalog
from agent4.core.errors import ContractError

from .llm_selector import validate_llm_selection_draft

STAGE = "metrics_validation"


def _reject(
    code: str, message: str, *, final_status: str = "unsupported", **details: Any
) -> ContractError:
    return ContractError(code, STAGE, message, details=details, final_status=final_status)


def require_authorized_view(auth_context: dict[str, Any], query_context: dict[str, Any]) -> str:
    requested_view = query_context.get("requested_view") or "mgmt"
    if requested_view not in (auth_context.get("allowed_views") or []):
        raise _reject(
            "forbidden_metric",
            "Requested view is not authorized.",
            final_status="forbidden",
            requested_view=requested_view,
        )
    return requested_view


def validate_metrics(
    llm_selection: dict[str, Any],
    retrieval_result: dict[str, Any],
    catalog: MetricCatalog,
    auth_context: dict[str, Any],
    query_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate every selected metric against candidates, governance and capabilities."""
    draft = validate_llm_selection_draft(llm_selection)
    catalog_hash = catalog.get_catalog_hash()
    if draft["status"] == "ambiguous":
        return {
            "status": "needs_clarification",
            "metric_ids": [],
            "catalog_hash": catalog_hash,
            "validated_capabilities": {},
            "warnings": [],
            "clarification_question": draft["clarification_question"]
            or "Bạn vui lòng làm rõ chỉ tiêu tài chính cần truy vấn?",
        }
    ids = draft["metric_ids"]
    if draft["status"] == "unsupported" or not ids:
        raise _reject("unsupported_metric", "No supported metric was selected.")

    context = query_context or {}
    requested_view = require_authorized_view(auth_context, context)
    operation = context.get("requested_operation") or "aggregate"
    dimensions = set(context.get("requested_dimensions") or ())
    candidates = {candidate["metric_id"] for candidate in retrieval_result.get("candidates", [])}
    allowed_metrics = auth_context.get("allowed_metrics")
    capabilities = {}
    period_types = set()
    for metric_id in ids:
        if not catalog.contains(metric_id):
            raise _reject(
                "unknown_metric", "Metric is absent from the catalog.", metric_id=metric_id
            )
        if metric_id not in candidates:
            raise _reject(
                "metric_outside_candidates",
                "Metric is absent from the candidates.",
                metric_id=metric_id,
            )
        capability = catalog.get_capability(metric_id)
        if capability["status"] != "approved":
            raise _reject("unsupported_metric", "Metric is not approved.", metric_id=metric_id)
        if capability["verified_handler"] is not True:
            raise _reject(
                "unsupported_data_source", "Metric has no verified handler.", metric_id=metric_id
            )
        if allowed_metrics is not None and metric_id not in allowed_metrics:
            raise _reject(
                "forbidden_metric",
                "Metric is not authorized.",
                final_status="forbidden",
                metric_id=metric_id,
            )
        if requested_view not in capability["supported_views"]:
            raise _reject(
                "unsupported_view",
                "Metric does not support the requested view.",
                metric_id=metric_id,
                view=requested_view,
            )
        missing_dimensions = dimensions.difference(capability["supported_dimensions"])
        if missing_dimensions:
            raise _reject(
                "unsupported_metric",
                "Metric does not support all requested dimensions.",
                metric_id=metric_id,
                dimensions=sorted(missing_dimensions),
            )
        if operation not in capability["supported_operations"]:
            raise _reject(
                "unsupported_metric",
                "Metric does not support the requested operation.",
                metric_id=metric_id,
                operation=operation,
            )
        period_types.add(capability["period_type"])
        capabilities[metric_id] = {
            field: capability[field]
            for field in (
                "period_type",
                "supported_views",
                "supported_dimensions",
                "supported_operations",
            )
        }

    if {"flow", "snapshot"} <= period_types:
        raise _reject(
            "incompatible_metrics", "Flow and snapshot metrics cannot be selected together."
        )
    return {
        "status": "validated",
        "metric_ids": ids,
        "catalog_hash": catalog_hash,
        "validated_capabilities": capabilities,
        "warnings": [],
    }
