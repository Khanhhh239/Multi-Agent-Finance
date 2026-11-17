"""Route online retrieval through authorized catalog and persisted index boundaries."""

from typing import Any

from agent4.core.cache import LRUTTLCache, build_scoped_cache_key, file_revision
from agent4.core.catalog import CANONICAL_TO_LEGACY, LEGACY_METRIC_IDS, MetricCatalog
from agent4.core.errors import ContractError, enforce_exact_keys

from .catalog_adapter import build_full_catalog_retrieval_result
from .config import MetricSelectionConfig, config_fingerprint
from .dense import dense_retrieve
from .embedding import EmbeddingProvider
from .fusion import fuse_candidates
from .index import INDEX_VERSION, MetricVectorIndex, load_or_build_index
from .lexical import LEXICAL_INDEX_VERSION, lexical_retrieve
from .mentions import retrieve_mentions
from .rerank import expand_related_candidates, rerank_candidates

_RETRIEVAL_SELECTION_CACHE = LRUTTLCache[str, Any](
    max_entries=512, ttl_seconds=1800, max_bytes_budget=12 * 1024**2, max_rows_per_entry=256
)


def _cache_scope(auth_context: dict[str, Any], catalog_hash: str) -> dict[str, Any] | None:
    tenant_id, policy_hash = auth_context.get("tenant_id"), auth_context.get("policy_hash")
    if all(isinstance(value, str) and value.strip() for value in (tenant_id, policy_hash)):
        allowed_metrics = auth_context.get("allowed_metrics")
        return {
            "tenant_id": tenant_id,
            "policy_hash": policy_hash,
            "catalog_hash": catalog_hash,
            "allowed_views": sorted(set(auth_context.get("allowed_views") or [])),
            "allowed_metrics": sorted(set(allowed_metrics))
            if allowed_metrics is not None
            else None,
        }
    return None


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
    result, _ = _retrieve_with_revision(
        normalized_query,
        catalog,
        embedding_provider,
        auth_context=auth_context,
        config=config,
        query_context=query_context,
        index=index,
    )
    return result


def _retrieve_with_revision(
    normalized_query: dict[str, Any],
    catalog: MetricCatalog,
    embedding_provider: EmbeddingProvider | None = None,
    *,
    auth_context: dict[str, Any],
    config: MetricSelectionConfig | None = None,
    query_context: dict[str, Any] | None = None,
    index: MetricVectorIndex | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Return a retrieval result and its scoped revision for downstream selection."""
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
    requested_view = (query_context or {}).get("requested_view")
    if requested_view is not None and not isinstance(requested_view, str):
        raise ContractError("invalid_request", stage, "Requested view must be a string.")
    catalog_hash = catalog.get_catalog_hash()
    scope = _cache_scope(auth_context, catalog_hash) if config.cache_enabled else None
    allowed_views = auth_context.get("allowed_views") or []
    if requested_view is not None and requested_view not in allowed_views:
        auth_context = {**auth_context, "allowed_views": []}

    settings = config.retrieval
    provider = None
    if settings.dense_enabled and settings.mode in ("dense_only", "hybrid"):
        provider = embedding_provider or EmbeddingProvider(config.embedding)
    key = None
    if (
        scope is not None
        and index is None
        and (provider is None or (type(provider) is EmbeddingProvider and provider.available))
    ):
        key = _retrieval_revision(normalized_query, requested_view, config, provider, scope)
        if key is not None and (cached := _RETRIEVAL_SELECTION_CACHE.get(key)) is not None:
            return cached, key

    result = _retrieve(
        normalized_query, catalog, auth_context, config, requested_view, provider, index, scope
    )
    if result["status"] == "retrieval_unavailable":
        return result, None
    if key is not None:
        _RETRIEVAL_SELECTION_CACHE.set(key, result, row_count=len(result["candidates"]))
    return result, key


def _retrieval_revision(
    query: dict[str, Any],
    requested_view: str | None,
    config: MetricSelectionConfig,
    provider: EmbeddingProvider | None,
    scope: dict[str, Any],
) -> str | None:
    try:
        index_revision = file_revision(provider.config.cache_path) if provider is not None else None
        relationships = None
        if (
            config.retrieval.mode in ("hybrid", "lexical_only")
            and config.expansion.enabled
            and config.expansion.max_hops
        ):
            relationships = file_revision(config.expansion.relationship_path)
    except OSError:
        # Let the normal stage decide whether a missing artifact is needed.
        return None
    return build_scoped_cache_key(
        "metric-retrieval",
        **scope,
        normalized_question=query["normalized_question"],
        question=query["question"],
        locale=query["locale"],
        requested_view=requested_view,
        config_hash=config_fingerprint(config),
        backend=provider.cache_identity() if provider is not None else None,
        index_revision=index_revision,
        relationships=relationships,
    )


def _retrieve(
    normalized_query: dict[str, Any],
    catalog: MetricCatalog,
    auth_context: dict[str, Any],
    config: MetricSelectionConfig,
    requested_view: str | None,
    provider: EmbeddingProvider | None,
    index: MetricVectorIndex | None,
    scope: dict[str, Any] | None,
) -> dict[str, Any]:
    settings = config.retrieval
    question = normalized_query["question"]
    query = normalized_query["normalized_question"]
    if settings.mode == "full_catalog" and not settings.mention_retrieval_enabled:
        return build_full_catalog_retrieval_result(question, catalog, auth_context)
    visible = catalog.list_visible_metrics(auth_context)
    if settings.mention_retrieval_enabled and requested_view:
        visible = [metric for metric in visible if requested_view in metric["supported_views"]]
    allowed_ids = {metric["metric_id"] for metric in visible}
    mentions = (
        _authorized_mentions(query, catalog, allowed_ids)
        if settings.mention_retrieval_enabled
        else None
    )
    if settings.mode == "full_catalog":
        full = build_full_catalog_retrieval_result(question, catalog, auth_context)
        if mentions is not None:
            full["candidates"] = _with_mentions(
                [
                    candidate
                    for candidate in full["candidates"]
                    if candidate["metric_id"] in allowed_ids
                ],
                mentions,
            )
            full["status"] = "candidates_found" if full["candidates"] else "empty_candidates"
        return full

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
    if not allowed_ids or not query.strip():
        return result

    dense = {"source": "dense", "hits": []}
    lexical = {"source": "lexical", "hits": []}
    if provider is not None:
        try:
            if index is None:
                index = load_or_build_index(catalog, provider, cache_enabled=config.cache_enabled)
            if index.is_stale(catalog_hash, provider) or not provider.normalize:
                return {**result, "status": "retrieval_unavailable"}
            result.update(embedding_model=provider.model_id, dense_index_version=INDEX_VERSION)
            cache_options = (
                {"cache_scope": scope}
                if scope is not None and type(provider) is EmbeddingProvider
                else {}
            )
            vector = provider.embed(
                {
                    "texts": [query],
                    "model_id": provider.model_id,
                    "model_version": provider.model_version,
                    "normalize": True,
                },
                input_type="query",
                **cache_options,
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

    fused = fuse_candidates(dense, lexical, settings.rrf_k, mention_out=mentions)
    candidates = fused["candidates"]
    if not candidates:
        return result
    if settings.mode != "dense_only":
        if mentions is not None:
            candidates = sorted(candidates, key=lambda row: -row.get("mention_score", 0))
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
        if mentions is not None:
            candidates = _with_mentions(candidates, mentions)
        candidates = candidates[: config.reranking.final_top_k]
    elif mentions is not None:
        candidates = _with_mentions(candidates, mentions)
    return {
        **result,
        "status": "candidates_found",
        "candidates": [{"rerank_score": None, **candidate} for candidate in candidates],
    }


def _authorized_mentions(
    query: str, catalog: MetricCatalog, allowed_ids: set[str]
) -> dict[str, Any]:
    # Resolve overlapping phrases before applying access, so a restricted longer
    # phrase cannot become evidence for an unrelated shorter phrase.
    mentions = retrieve_mentions(query, catalog.list_metrics())
    hits = []
    for hit in mentions["hits"]:
        metric_id = hit["metric_id"]
        if metric_id not in allowed_ids:
            metric_id = CANONICAL_TO_LEGACY.get(
                metric_id, LEGACY_METRIC_IDS.get(metric_id, metric_id)
            )
        if metric_id in allowed_ids:
            hits.append({**hit, "metric_id": metric_id, "rank": len(hits) + 1})
    return {**mentions, "hits": hits}


def _with_mentions(
    candidates: list[dict[str, Any]], mentions: dict[str, Any]
) -> list[dict[str, Any]]:
    hits = {hit["metric_id"]: hit for hit in mentions["hits"]}
    ordered = sorted(candidates, key=lambda row: -hits.get(row["metric_id"], {}).get("score", 0))
    result = []
    for rank, candidate in enumerate(ordered, start=1):
        hit = hits.get(candidate["metric_id"])
        row = {**candidate, "rank": rank}
        if hit is not None:
            row["mention_score"] = hit["score"]
            row["matched_terms"] = hit["matched_terms"]
            row["retrieval_sources"] = list(
                dict.fromkeys([*candidate["retrieval_sources"], "mention"])
            )
        result.append(row)
    return result
