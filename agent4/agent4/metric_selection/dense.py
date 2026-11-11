"""Cosine retrieval over a previously built metric index."""

from collections.abc import Collection
from typing import Any

import numpy as np

from agent4.core.catalog import CANONICAL_TO_LEGACY, LEGACY_METRIC_IDS, MetricCatalog
from agent4.core.errors import ContractError, enforce_exact_keys

from .embedding import DOCUMENT_VERSION
from .index import INDEX_VERSION, MetricVectorIndex

_STAGE = "dense_retrieval"


def dense_retrieve(
    request: dict[str, Any],
    catalog: MetricCatalog,
    index: MetricVectorIndex,
    *,
    allowed_metric_ids: Collection[str] | None = None,
) -> dict[str, Any]:
    enforce_exact_keys(
        request,
        {"query", "query_embedding", "top_k", "catalog_hash", "index_version"},
        stage=_STAGE,
    )
    if (
        not isinstance(request["query"], str)
        or not request["query"].strip()
        or type(request["top_k"]) is not int
        or request["top_k"] < 1
        or request["catalog_hash"] != catalog.get_catalog_hash()
        or request["index_version"] != INDEX_VERSION
    ):
        raise ContractError("invalid_request", _STAGE, "Invalid dense retrieval request.")
    if (
        index.metadata.get("catalog_hash") != request["catalog_hash"]
        or index.metadata.get("index_version") != INDEX_VERSION
        or index.metadata.get("document_version") != DOCUMENT_VERSION
        or index.metadata.get("normalized") is not True
    ):
        raise ContractError(
            "retrieval_unavailable",
            _STAGE,
            "Dense index is incompatible.",
            retryable=True,
            final_status="temporarily_unavailable",
        )

    embedding = request["query_embedding"]
    enforce_exact_keys(embedding, {"values", "dimension", "normalized"}, stage=_STAGE)
    dimension = index.metadata["dimension"]
    values = embedding["values"]
    if (
        embedding["normalized"] is not True
        or type(embedding["dimension"]) is not int
        or embedding["dimension"] != dimension
        or not isinstance(values, list)
        or len(values) != dimension
        or any(
            type(value) not in (int, float) or not -1.000001 <= value <= 1.000001
            for value in values
        )
    ):
        raise ContractError("invalid_request", _STAGE, "Invalid query embedding.")
    vector = np.asarray(values, dtype=np.float32)
    if not np.isclose(np.linalg.norm(vector), 1.0, atol=1e-6):
        raise ContractError("invalid_request", _STAGE, "Query embedding must have unit length.")

    candidates = catalog.list_metrics(approved_only=True, allowed_metrics=allowed_metric_ids)
    scores = dict(zip(index.metric_ids, np.clip(index.vectors @ vector, -1.0, 1.0), strict=True))
    ranked = []
    for metric in candidates:
        metric_id = metric["metric_id"]
        index_id = metric_id
        if index_id not in scores:
            index_id = LEGACY_METRIC_IDS.get(metric_id) or CANONICAL_TO_LEGACY.get(metric_id)
        if index_id in scores:
            ranked.append((metric_id, float(scores[index_id])))
    ranked.sort(key=lambda pair: (-pair[1], pair[0]))
    return {
        "source": "dense",
        "hits": [
            {"metric_id": metric_id, "rank": rank, "score": score, "index_version": INDEX_VERSION}
            for rank, (metric_id, score) in enumerate(ranked[: request["top_k"]], start=1)
        ],
    }
