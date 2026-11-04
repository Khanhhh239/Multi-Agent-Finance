from __future__ import annotations

from ..schemas import MetricCandidate


class AdaptiveFewshotPolicy:
    def __init__(self, min_examples: int = 0, max_examples: int = 4) -> None:
        self.min_examples = min_examples
        self.max_examples = max_examples

    def choose_count(
        self,
        candidates: list[MetricCandidate],
        boundaries: set[str],
        dense_lexical_disagreement: bool = False,
    ) -> int:
        if self.max_examples == 0:
            return 0
        plausible = candidates[:4]
        margin = float("inf")
        if len(plausible) >= 2:
            first = plausible[0].rerank_score or 0.0
            second = plausible[1].rerank_score or 0.0
            margin = first - second
        if not boundaries and not dense_lexical_disagreement and margin >= 0.12:
            return self.min_examples
        desired = max(self.min_examples, 1)
        desired += min(len(boundaries), 2)
        if dense_lexical_disagreement:
            desired += 1
        if margin < 0.05:
            desired += 1
        return min(desired, self.max_examples)
