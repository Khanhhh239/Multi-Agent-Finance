"""Local BM25 retrieval over public metric metadata, never ledger contents.

The smoke set is a development benchmark, not an independent evaluation set.
Embeddings are optional in the design and are deliberately not used here.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
import unicodedata

from rank_bm25 import BM25Okapi

from agent4.engine.metrics import GROUP_LABELS, REGISTRY


def normalize(text: str) -> str:
    """Normalize accents and punctuation, including Vietnamese đ and NFD text."""
    text = unicodedata.normalize("NFD", text.casefold()).replace("đ", "d")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"[a-z0-9_]+", text))


_STOPWORDS = frozenset("la bao nhieu nay nay trong tung hien tai cho toi xem cua va voi nao co khong duoc thang quy nam ngay cuoi ky dau tu den gan nhat".split())


def _tokens(text: str) -> list[str]:
    words = [word for word in normalize(text).split() if word not in _STOPWORDS and not word.isdigit()]
    return words + [f"{a}:{b}" for a, b in zip(words, words[1:])]


@dataclass(frozen=True)
class Candidate:
    metric: str
    score: float


def _hint(hints, name, default=None):
    return hints.get(name, default) if isinstance(hints, Mapping) else getattr(hints, name, default)


class MetricRetriever:
    """Rank the registry's label, description and synonyms without DB access.

    Scores are lexical ranking values, not probabilities. Hints only boost valid
    metadata capabilities; validation must still enforce views and dimensions.
    """

    def __init__(self):
        self._ids = tuple(REGISTRY)
        # Only these three public fields enter the index. Do not add account
        # formulas, data samples, descriptions from rows, or partner names.
        self._phrases = {
            key: tuple(normalize(p) for p in (metric.label, *metric.synonyms))
            for key, metric in REGISTRY.items()
        }
        self._index = BM25Okapi([
            _tokens(" ".join((m.label, m.description, *m.synonyms)))
            for m in REGISTRY.values()
        ])

    def topk(self, question: str, k: int = 8, hints=None) -> list[Candidate]:
        if k <= 0:
            return []
        query = normalize(question)
        tokens = _tokens(question)
        if not tokens:
            return []
        scores = self._index.get_scores(tokens)
        view = _hint(hints, "view_hint")
        group = _hint(hints, "group_by")
        if group is None:
            # Accommodate preprocess versions exposing grouping as a cue.
            for dimension, label in GROUP_LABELS.items():
                if f"theo {normalize(label)}" in query:
                    group = dimension
                    break
        ranked = []
        padded = f" {query} "
        for idx, metric_id in enumerate(self._ids):
            metric = REGISTRY[metric_id]
            score = max(0.0, float(scores[idx]))
            # The longest exact label/synonym match disambiguates near-identical
            # financial terms (gộp/ròng, được trừ/không được trừ) without relying
            # on question-specific routing or benchmark examples in the index.
            phrase_length = max((len(p.split()) for p in self._phrases[metric_id]
                                 if p and f" {p} " in padded), default=0)
            if phrase_length:
                score += 4.0 * phrase_length
            if score and view == "tax" and "tax" in metric.views:
                score += 2.0
            if score and group in metric.group_bys:
                score += 3.0
            if score:
                ranked.append(Candidate(metric_id, round(score, 8)))
        return sorted(ranked, key=lambda c: (-c.score, c.metric))[:k]

    @staticmethod
    def ambiguous(cands: list[Candidate]) -> bool:
        """Conservative routing hint; callers may ask a more specific question."""
        if not cands or cands[0].score < 3.0:
            return True
        return len(cands) > 1 and (cands[0].score - cands[1].score) / cands[0].score < 0.12
