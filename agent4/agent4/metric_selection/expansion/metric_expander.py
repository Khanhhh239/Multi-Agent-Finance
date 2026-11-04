from __future__ import annotations

from ..catalog.relationships import MetricRelationship, RelationshipRegistry
from ..retrieval.embedding import normalize_text
from ..schemas import MetricCandidate


class MetricExpander:
    def __init__(
        self,
        relationships: RelationshipRegistry,
        max_candidates: int = 30,
        max_hops: int = 1,
    ) -> None:
        if max_hops not in {0, 1}:
            raise ValueError("v1 expansion supports zero or one hop")
        self.relationships = relationships
        self.max_candidates = max_candidates
        self.max_hops = max_hops

    @staticmethod
    def _query_signal(question: str, edge: MetricRelationship) -> float:
        query = normalize_text(question)
        metadata = edge.metadata
        group_by = metadata.get("group_by")
        group_signals = {
            "customer": ("khách hàng", "khách nợ"),
            "salesperson": ("nhân viên", "sales", "kinh doanh"),
            "vendor": ("nhà cung cấp", "ncc"),
            "cost_category": ("khoản mục", "loại chi phí", "cơ cấu chi phí"),
        }
        if group_by and any(signal in query for signal in group_signals.get(group_by, ())):
            return 1.0
        return 0.0

    def expand(self, question: str, candidates: list[MetricCandidate]) -> list[MetricCandidate]:
        originals = [candidate.model_copy(deep=True) for candidate in candidates]
        if self.max_hops == 0 or len(originals) >= self.max_candidates:
            return originals[: self.max_candidates]
        known = {candidate.metric_id for candidate in originals}
        additions: list[tuple[float, str, MetricCandidate]] = []
        for rank, candidate in enumerate(originals):
            for edge in self.relationships.related(candidate.metric_id):
                if edge.target in known:
                    continue
                priority = self._query_signal(question, edge) + 1.0 / (rank + 1)
                expanded = MetricCandidate(
                    metric_id=edge.target,
                    fusion_score=(candidate.fusion_score or 0.0) * 0.75,
                    retrieval_sources=["expansion"],
                    expansion_source=f"{candidate.metric_id}:{edge.type}",
                    score_components={"expansion_priority": priority},
                )
                additions.append((priority, edge.target, expanded))
                known.add(edge.target)
        additions.sort(key=lambda item: (-item[0], item[1]))
        remaining = self.max_candidates - len(originals)
        originals.extend(item[2] for item in additions[:remaining])
        return originals
