"""Vietnamese-safe BM25 retrieval with exact phrase boosts."""

from __future__ import annotations

import math
from collections import Counter

from ..catalog.adapter import MetricCatalogAdapter
from ..schemas import MetricCandidate
from .embedding import normalize_text, tokenize


class LexicalRetriever:
    def __init__(self, catalog: MetricCatalogAdapter, k1: float = 1.5, b: float = 0.75) -> None:
        self.catalog = catalog
        self.k1 = k1
        self.b = b
        self._records: list[tuple[str, list[str], list[str]]] = []
        document_frequency: Counter[str] = Counter()
        for metric in catalog:
            phrases = [metric.id.replace("_", " "), metric.label, *metric.synonyms]
            text = " ".join(
                [metric.id.replace("_", " "), metric.label, metric.description, *metric.synonyms]
            )
            tokens = tokenize(text)
            self._records.append((metric.id, tokens, [normalize_text(p) for p in phrases]))
            document_frequency.update(set(tokens))
        self._document_frequency = document_frequency
        self._avg_length = sum(len(record[1]) for record in self._records) / max(
            len(self._records), 1
        )

    def _score(self, query: str, tokens: list[str], phrases: list[str]) -> float:
        query_tokens = tokenize(query)
        if not query_tokens:
            return 0.0
        counts = Counter(tokens)
        score = 0.0
        total = len(self._records)
        for token in set(query_tokens):
            frequency = counts[token]
            if not frequency:
                continue
            document_frequency = self._document_frequency[token]
            inverse_frequency = math.log(
                1 + (total - document_frequency + 0.5) / (document_frequency + 0.5)
            )
            denominator = frequency + self.k1 * (
                1 - self.b + self.b * len(tokens) / max(self._avg_length, 1)
            )
            score += inverse_frequency * frequency * (self.k1 + 1) / denominator
        normalized_query = normalize_text(query)
        for phrase in phrases:
            if phrase and phrase in normalized_query:
                word_count = len(tokenize(phrase))
                score += 2.0 + min(word_count, 5) * 0.6
                if normalized_query == phrase:
                    score += 3.0
        return score

    def retrieve(self, query: str, top_k: int) -> list[MetricCandidate]:
        ranked = [
            (self._score(query, tokens, phrases), metric_id)
            for metric_id, tokens, phrases in self._records
        ]
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [
            MetricCandidate(
                metric_id=metric_id,
                lexical_score=score,
                retrieval_sources=["lexical"],
            )
            for score, metric_id in ranked[:top_k]
            if score > 0
        ]
