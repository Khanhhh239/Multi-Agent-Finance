"""Adapt the engine registry for selection without changing the default catalog."""

from __future__ import annotations

from typing import Any

from agent4.core.catalog import MetricCatalog, metric_def_to_catalog_dict
from agent4.engine.metrics import REGISTRY


def build_canonical_catalog() -> MetricCatalog:
    """Build the metadata-only catalog used by the selection and planning experiments."""
    return MetricCatalog(
        [metric_def_to_catalog_dict(metric, verified_handler=True) for metric in REGISTRY.values()]
    )


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
