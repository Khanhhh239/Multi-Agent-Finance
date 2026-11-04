from __future__ import annotations

from ..catalog.document_builder import MetricDocumentBuilder
from ..schemas import MetricCandidate
from .cross_encoder import CrossEncoder
from .metadata_ranker import MetadataRanker


class CandidateReranker:
    def __init__(
        self,
        documents: MetricDocumentBuilder,
        metadata_ranker: MetadataRanker | None,
        cross_encoder: CrossEncoder | None = None,
        *,
        final_top_k: int = 12,
        metadata_weight: float = 1.0,
        cross_encoder_weight: float = 0.4,
    ) -> None:
        self.documents = documents
        self.metadata_ranker = metadata_ranker
        self.cross_encoder = cross_encoder
        self.final_top_k = final_top_k
        self.metadata_weight = metadata_weight
        self.cross_encoder_weight = cross_encoder_weight

    def rerank(
        self,
        question: str,
        candidates: list[MetricCandidate],
        context: dict | None = None,
    ) -> list[MetricCandidate]:
        if not candidates:
            return []
        cross_scores: list[float] = [0.0] * len(candidates)
        if self.cross_encoder:
            documents = [self.documents.build(candidate.metric_id) for candidate in candidates]
            raw = self.cross_encoder.score(question, documents)
            if len(raw) != len(candidates):
                raise ValueError("Cross-encoder returned the wrong number of scores")
            minimum, maximum = min(raw), max(raw)
            if maximum > minimum:
                cross_scores = [(score - minimum) / (maximum - minimum) for score in raw]

        ranked: list[MetricCandidate] = []
        count = len(candidates)
        for index, (candidate, cross_score) in enumerate(zip(candidates, cross_scores)):
            item = candidate.model_copy(deep=True)
            base_score = 1.0 - (index / max(count, 1)) * 0.45
            components = {"retrieval_rank": base_score}
            if self.metadata_ranker:
                metadata_components = self.metadata_ranker.components(question, item, context)
                components.update(metadata_components)
            if self.cross_encoder:
                components["cross_encoder"] = cross_score * self.cross_encoder_weight
            metadata_score = sum(
                value for name, value in components.items() if name not in {"retrieval_rank", "cross_encoder"}
            )
            item.rerank_score = (
                base_score
                + metadata_score * self.metadata_weight
                + components.get("cross_encoder", 0.0)
            )
            item.score_components.update(components)
            ranked.append(item)
        ranked.sort(key=lambda item: (-(item.rerank_score or 0.0), item.metric_id))
        return ranked[: self.final_top_k]
