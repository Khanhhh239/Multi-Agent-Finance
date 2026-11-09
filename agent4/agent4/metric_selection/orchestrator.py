"""Route online retrieval through authorized catalog and persisted index boundaries."""

from typing import Any

from agent4.core.catalog import MetricCatalog
from agent4.core.errors import ContractError, enforce_exact_keys

from .catalog_adapter import build_full_catalog_retrieval_result
from .config import MetricSelectionConfig
from .dense import dense_retrieve
from .embedding import EmbeddingProvider
from .fusion import fuse_candidates
from .index import INDEX_VERSION, MetricVectorIndex, load_index
from .lexical import LEXICAL_INDEX_VERSION, lexical_retrieve
from .rerank import expand_related_candidates, rerank_candidates


def orchestrate_retrieval(
    normalized_query: dict[str, Any],
    catalog: MetricCatalog,
    embedding_provider: EmbeddingProvider | None = None,
    *,
    auth_context: dict[str, Any],
    config: MetricSelectionConfig | None = None,
    query_context: dict[str, Any] | None = None,
    index: MetricVectorIndex | None = None,
) -> dict[str, Any]:
    """Retrieve online from an offline index and apply the server-owned visibility policy."""
    stage = "metric_retrieval"
    enforce_exact_keys(
        normalized_query,
        {"contract_version", "question", "normalized_question", "locale", "options"},
        stage=stage,
    )
    if (
        normalized_query["contract_version"] != "normalized-query.v1"
        or not isinstance(normalized_query["question"], str)
        or not isinstance(normalized_query["normalized_question"], str)
        or normalized_query["locale"] not in ("vi-VN", "en-US")
    ):
        raise ContractError("invalid_request", stage, "Invalid normalized query.")
    config = config or MetricSelectionConfig()
    settings = config.retrieval
    question = normalized_query["question"]
    query = normalized_query["normalized_question"]
    requested_view = (query_context or {}).get("requested_view")
    if requested_view is not None and not isinstance(requested_view, str):
        raise ContractError("invalid_request", stage, "Requested view must be a string.")
    if requested_view is not None and requested_view not in (
        auth_context.get("allowed_views") or []
    ):
        auth_context = {**auth_context, "allowed_views": []}

    if settings.mode == "full_catalog":
        return build_full_catalog_retrieval_result(question, catalog, auth_context)

    catalog_hash = catalog.get_catalog_hash()
    result = {
        "status": "empty_candidates",
        "query": question,
        "candidates": [],
        "catalog_hash": catalog_hash,
        "embedding_model": None,
        "dense_index_version": None,
        "lexical_index_version": None,
        "reranker_version": None,
    }
    allowed_ids = {metric["metric_id"] for metric in catalog.list_visible_metrics(auth_context)}
    if not allowed_ids or not query.strip():
        return result

    dense = {"source": "dense", "hits": []}
    lexical = {"source": "lexical", "hits": []}
    if settings.dense_enabled and settings.mode in ("dense_only", "hybrid"):
        provider = embedding_provider or EmbeddingProvider(config.embedding)
        try:
            if index is None:
                index = load_index(
                    provider.config.cache_path,
                    catalog_hash=catalog_hash,
                    embedding_provider=provider,
                )
            if index.is_stale(catalog_hash, provider) or not provider.normalize:
                return {**result, "status": "retrieval_unavailable"}
            result.update(embedding_model=provider.model_id, dense_index_version=INDEX_VERSION)
            vector = provider.embed(
                {
                    "texts": [query],
                    "model_id": provider.model_id,
                    "model_version": provider.model_version,
                    "normalize": True,
                }
            )["vectors"][0]
            dense = dense_retrieve(
                {
                    "query": query,
                    "query_embedding": vector,
                    "top_k": settings.dense_top_k,
                    "catalog_hash": catalog_hash,
                    "index_version": INDEX_VERSION,
                },
                catalog,
                index,
                allowed_metric_ids=allowed_ids,
            )
        except ContractError as exc:
            if exc.code != "retrieval_unavailable":
                raise
            return {**result, "status": "retrieval_unavailable"}

    if settings.lexical_enabled and settings.mode in ("lexical_only", "hybrid"):
        lexical = lexical_retrieve(
            {
                "query": query,
                "top_k": settings.lexical_top_k,
                "index_version": LEXICAL_INDEX_VERSION,
            },
            catalog,
            allowed_metric_ids=allowed_ids,
        )
        result["lexical_index_version"] = LEXICAL_INDEX_VERSION

    fused = fuse_candidates(dense, lexical, settings.rrf_k)
    candidates = fused["candidates"]
    if not candidates:
        return result
    if settings.mode != "dense_only":
        candidates = candidates[: settings.fusion_top_k]
        candidates = expand_related_candidates(candidates, allowed_ids, config.expansion)
        if config.reranking.metadata_enabled:
            reranked = rerank_candidates(
                normalized_query,
                {**fused, "candidates": candidates},
                catalog,
                requested_view,
                auth_context=auth_context,
            )
            by_id = {candidate["metric_id"]: candidate for candidate in candidates}
            candidates = [
                {
                    **by_id[item["metric_id"]],
                    "rank": item["rank"],
                    "rerank_score": item["rerank_score"],
                }
                for item in reranked["ranked_candidates"]
            ]
            result["reranker_version"] = reranked["reranker_version"]
        candidates = candidates[: config.reranking.final_top_k]
    return {
        **result,
        "status": "candidates_found",
        "candidates": [{"rerank_score": None, **candidate} for candidate in candidates],
    }
