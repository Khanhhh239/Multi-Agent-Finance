from __future__ import annotations

from pydantic import BaseModel, Field

from ..catalog.adapter import MetricCatalogAdapter
from ..schemas import MetricCandidate
from .dense import DenseRetriever
from .fusion import reciprocal_rank_fusion
from .lexical import LexicalRetriever
from .mentions import MentionExtractor


class CandidateGenerationResult(BaseModel):
    dense: list[MetricCandidate] = Field(default_factory=list)
    lexical: list[MetricCandidate] = Field(default_factory=list)
    fused: list[MetricCandidate] = Field(default_factory=list)


class CandidateGenerator:
    def __init__(
        self,
        dense: DenseRetriever | None,
        lexical: LexicalRetriever | None,
        mentions: MentionExtractor | None = None,
        *,
        dense_top_k: int = 15,
        lexical_top_k: int = 15,
        fusion_top_k: int = 20,
        rrf_k: int = 60,
    ) -> None:
        if dense is None and lexical is None:
            raise ValueError("At least one retriever is required")
        self.dense = dense
        self.lexical = lexical
        self.mentions = mentions
        self.dense_top_k = dense_top_k
        self.lexical_top_k = lexical_top_k
        self.fusion_top_k = fusion_top_k
        self.rrf_k = rrf_k

    def _retrieve_once(self, query: str) -> tuple[list[MetricCandidate], list[MetricCandidate]]:
        dense = self.dense.retrieve(query, self.dense_top_k) if self.dense else []
        lexical = self.lexical.retrieve(query, self.lexical_top_k) if self.lexical else []
        return dense, lexical

    def retrieve(self, question: str) -> CandidateGenerationResult:
        dense, lexical = self._retrieve_once(question)
        rankings: list[tuple[str, list[MetricCandidate]]] = []
        if dense:
            rankings.append(("dense", dense))
        if lexical:
            rankings.append(("lexical", lexical))
        if self.mentions:
            for index, mention in enumerate(self.mentions.extract(question)):
                mention_dense, mention_lexical = self._retrieve_once(mention)
                if mention_dense:
                    rankings.append((f"mention_{index}_dense", mention_dense))
                if mention_lexical:
                    rankings.append((f"mention_{index}_lexical", mention_lexical))
        fused = reciprocal_rank_fusion(rankings, self.fusion_top_k, self.rrf_k)
        return CandidateGenerationResult(dense=dense, lexical=lexical, fused=fused)


class FullCatalogCandidateGenerator:
    """Evaluation baseline that deliberately bypasses retrieval."""

    def __init__(self, catalog: MetricCatalogAdapter) -> None:
        self.catalog = catalog

    def retrieve(self, question: str) -> CandidateGenerationResult:
        del question
        candidates = [
            MetricCandidate(
                metric_id=metric_id,
                fusion_score=1.0,
                retrieval_sources=["full_catalog"],
            )
            for metric_id in self.catalog.metric_ids
        ]
        return CandidateGenerationResult(fused=candidates)
