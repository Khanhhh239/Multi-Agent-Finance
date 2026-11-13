"""Reciprocal rank fusion with per-source provenance."""

import math
from typing import Any

from agent4.core.errors import ContractError, enforce_exact_keys

_STAGE = "retrieval_fusion"


def fuse_candidates(
    dense_out: dict[str, Any],
    lexical_out: dict[str, Any],
    rrf_k: int = 60,
    *,
    mention_out: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if type(rrf_k) is not int or rrf_k < 1:
        raise ContractError("invalid_request", _STAGE, "RRF k must be a positive integer.")
    sources = [("dense", dense_out), ("lexical", lexical_out)]
    if mention_out is not None:
        sources.append(("mention", mention_out))

    by_metric: dict[str, dict[str, Any]] = {}
    for source, result in sources:
        enforce_exact_keys(result, {"source", "hits"}, stage=_STAGE)
        if result["source"] != source or not isinstance(result["hits"], list):
            raise ContractError("invalid_request", _STAGE, "Invalid retriever result.")

        best_hits: dict[str, tuple[int, float]] = {}
        for hit in result["hits"]:
            enforce_exact_keys(
                hit,
                {"metric_id", "rank", "score"},
                {"index_version", "matched_terms"},
                stage=_STAGE,
            )
            metric_id, rank, score = hit["metric_id"], hit["rank"], hit["score"]
            if (
                not isinstance(metric_id, str)
                or not metric_id
                or type(rank) is not int
                or rank < 1
                or type(score) not in (int, float)
                or (type(score) is float and not math.isfinite(score))
            ):
                raise ContractError("invalid_request", _STAGE, "Invalid retrieval hit.")
            current = best_hits.get(metric_id)
            if current is None or (rank, -score) < (current[0], -current[1]):
                best_hits[metric_id] = (rank, score)

        for metric_id, (rank, score) in best_hits.items():
            entry = by_metric.setdefault(
                metric_id,
                {
                    "metric_id": metric_id,
                    "retrieval_sources": [],
                    "dense_score": None,
                    "lexical_score": None,
                    "fusion_score": 0.0,
                },
            )
            entry["retrieval_sources"].append(source)
            entry[f"{source}_score"] = score
            entry["fusion_score"] += 1.0 / (rrf_k + rank)

    ranked = sorted(by_metric.values(), key=lambda item: (-item["fusion_score"], item["metric_id"]))
    return {
        "status": "candidates_found" if ranked else "empty_candidates",
        "candidates": [{**item, "rank": rank} for rank, item in enumerate(ranked, start=1)],
        "fusion_method": "rrf",
        "fusion_version": "rrf-v1",
    }
