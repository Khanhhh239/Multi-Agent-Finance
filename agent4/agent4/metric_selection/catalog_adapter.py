"""Adapt the engine registry for selection without changing the default catalog."""

from __future__ import annotations

from typing import Any

from agent4.core.catalog import CATALOG_VERSION, MetricCatalog
from agent4.engine.metrics import REGISTRY, MetricDef


def metric_def_to_catalog_dict(
    metric: MetricDef, *, status: str = "approved", verified_handler: bool = True
) -> dict[str, Any]:
    operations = ["aggregate", "compare", "comparison"]
    if {"month", "quarter", "year"}.intersection(metric.group_bys):
        operations.append("timeseries")
    if metric.group_bys:
        operations.extend(("breakdown", "rank", "ranking"))
    return {
        "metric_id": metric.id,
        "label": metric.label,
        "description": metric.description,
        "aliases": list(metric.synonyms),
        "category": metric.category,
        "unit": metric.unit,
        "kind": metric.kind,
        "period_type": metric.period_type,
        "supported_views": list(metric.views),
        "supported_dimensions": list(metric.group_bys),
        "supported_operations": operations,
        "default_view": metric.default_view,
        "status": status,
        "verified_handler": verified_handler,
        "owner": "finance",
        "catalog_version": CATALOG_VERSION,
    }


def build_canonical_catalog() -> MetricCatalog:
    return MetricCatalog([metric_def_to_catalog_dict(metric) for metric in REGISTRY.values()])


def build_full_catalog_retrieval_result(
    query: str, catalog: MetricCatalog, auth_context: dict[str, Any]
) -> dict[str, Any]:
    candidates = [
        {
            "metric_id": metric["metric_id"],
            "rank": rank,
            "retrieval_sources": ["catalog_full"],
            "dense_score": None,
            "lexical_score": None,
            "fusion_score": None,
            "rerank_score": None,
        }
        for rank, metric in enumerate(catalog.list_visible_metrics(auth_context), start=1)
    ]
    return {
        "status": "candidates_found" if candidates else "empty_candidates",
        "query": query,
        "candidates": candidates,
        "catalog_hash": catalog.get_catalog_hash(),
        "embedding_model": None,
        "dense_index_version": None,
        "lexical_index_version": None,
        "reranker_version": None,
    }
