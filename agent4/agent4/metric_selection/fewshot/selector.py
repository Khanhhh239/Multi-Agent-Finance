from __future__ import annotations

from ..catalog.adapter import MetricCatalogAdapter
from ..catalog.relationships import RelationshipRegistry
from ..retrieval.embedding import tokenize
from ..schemas import MetricCandidate
from .adaptive_policy import AdaptiveFewshotPolicy
from .example_bank import ExampleBank, FewshotExample


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


class FewshotSelector:
    def __init__(
        self,
        bank: ExampleBank,
        catalog: MetricCatalogAdapter,
        relationships: RelationshipRegistry,
        policy: AdaptiveFewshotPolicy,
        *,
        strategy: str = "adaptive",
        initial_pool_size: int = 15,
        alpha: float = 1.0,
        beta: float = 0.5,
        gamma: float = 0.5,
        delta: float = 0.25,
    ) -> None:
        self.bank = bank
        self.catalog = catalog
        self.relationships = relationships
        self.policy = policy
        self.strategy = strategy
        self.initial_pool_size = initial_pool_size
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.delta = delta

    def boundaries(self, candidates: list[MetricCandidate]) -> set[str]:
        metric_ids = {candidate.metric_id for candidate in candidates[:8]}
        boundaries: set[str] = set()
        for relationship in self.relationships.relationships:
            if relationship.source in metric_ids and relationship.target in metric_ids:
                tag = relationship.metadata.get("decision_tag")
                if tag:
                    boundaries.add(str(tag))
        metrics = [self.catalog.get(metric_id) for metric_id in metric_ids]
        categories = {(metric.category, metric.kind, metric.unit) for metric in metrics}
        if any(unit == "%" for _, _, unit in categories) and any(
            unit == "VND" for _, _, unit in categories
        ):
            boundaries.add("amount_vs_ratio")
        if any(metric.period_type == "snapshot" for metric in metrics) and any(
            metric.period_type == "flow" for metric in metrics
        ):
            boundaries.add("snapshot_vs_flow")
        return boundaries

    def select(
        self,
        question: str,
        candidates: list[MetricCandidate],
        *,
        dense_top_id: str | None = None,
        lexical_top_id: str | None = None,
    ) -> list[FewshotExample]:
        if self.strategy == "zero" or not self.bank.examples:
            return []
        boundaries = self.boundaries(candidates)
        disagreement = bool(
            dense_top_id and lexical_top_id and dense_top_id != lexical_top_id
        )
        if self.strategy == "adaptive":
            count = self.policy.choose_count(candidates, boundaries, disagreement)
        else:
            count = self.policy.max_examples
        if count == 0:
            return []
        if self.strategy == "static":
            return sorted(self.bank.examples, key=lambda example: example.id)[:count]

        query_tokens = set(tokenize(question))
        candidate_ids = {candidate.metric_id for candidate in candidates}
        pool = sorted(
            self.bank.examples,
            key=lambda example: (
                -_jaccard(query_tokens, set(tokenize(example.question))),
                example.id,
            ),
        )[: self.initial_pool_size]
        if self.strategy == "similarity":
            return pool[:count]

        selected: list[FewshotExample] = []
        covered: set[str] = set()
        while pool and len(selected) < count:
            best: FewshotExample | None = None
            best_score = float("-inf")
            for example in pool:
                example_tags = set(example.decision_tags)
                marginal = len((example_tags & boundaries) - covered)
                relevance = _jaccard(query_tokens, set(tokenize(example.question)))
                referenced = set(example.answer.metric_ids) | set(example.confusable_metrics)
                candidate_relevance = len(referenced & candidate_ids) / max(len(referenced), 1)
                redundancy = max(
                    (
                        _jaccard(
                            set(tokenize(example.question)),
                            set(tokenize(chosen.question)),
                        )
                        for chosen in selected
                    ),
                    default=0.0,
                )
                score = (
                    self.alpha * marginal
                    + self.beta * relevance
                    + self.gamma * candidate_relevance
                    - self.delta * redundancy
                )
                if score > best_score or (
                    score == best_score and best is not None and example.id < best.id
                ):
                    best, best_score = example, score
            if best is None:
                break
            selected.append(best)
            covered.update(best.decision_tags)
            pool.remove(best)
        return selected
