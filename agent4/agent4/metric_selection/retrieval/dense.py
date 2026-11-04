from __future__ import annotations

import numpy as np

from ..catalog.index_builder import DenseIndex
from ..errors import EmbeddingProviderError
from ..schemas import MetricCandidate
from .embedding import EmbeddingProvider


class DenseRetriever:
    def __init__(self, index: DenseIndex, provider: EmbeddingProvider) -> None:
        self.index = index
        self.provider = provider

    def retrieve(self, query: str, top_k: int) -> list[MetricCandidate]:
        try:
            vector = np.asarray(self.provider.embed_query(query), dtype=np.float64)
        except Exception as exc:
            raise EmbeddingProviderError(f"Query embedding failed: {exc}") from exc
        if vector.ndim != 1 or vector.shape[0] != self.index.matrix.shape[1]:
            raise EmbeddingProviderError("Query embedding has an invalid dimension")
        norm = np.linalg.norm(vector)
        if norm:
            vector = vector / norm
        scores = self.index.matrix @ vector
        order = sorted(
            range(len(scores)),
            key=lambda idx: (-float(scores[idx]), self.index.metric_ids[idx]),
        )[:top_k]
        return [
            MetricCandidate(
                metric_id=self.index.metric_ids[idx],
                dense_score=float(scores[idx]),
                retrieval_sources=["dense"],
            )
            for idx in order
        ]
