from __future__ import annotations

from ..schemas import MetricCandidate


def reciprocal_rank_fusion(
    rankings: list[tuple[str, list[MetricCandidate]]],
    top_k: int,
    k: int = 60,
) -> list[MetricCandidate]:
    merged: dict[str, MetricCandidate] = {}
    for source, candidates in rankings:
        for rank, candidate in enumerate(candidates, start=1):
            current = merged.setdefault(candidate.metric_id, MetricCandidate(metric_id=candidate.metric_id))
            current.fusion_score = (current.fusion_score or 0.0) + 1.0 / (k + rank)
            if candidate.dense_score is not None:
                current.dense_score = candidate.dense_score
            if candidate.lexical_score is not None:
                current.lexical_score = candidate.lexical_score
            if source not in current.retrieval_sources:
                current.retrieval_sources.append(source)
    return sorted(
        merged.values(),
        key=lambda item: (-(item.fusion_score or 0.0), item.metric_id),
    )[:top_k]
