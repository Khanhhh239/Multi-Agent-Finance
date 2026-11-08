"""Conservative deterministic extraction for explicit multi-metric questions."""
from __future__ import annotations

import re

from ..catalog.adapter import MetricCatalogAdapter
from .embedding import normalize_text

SPLIT_RE = re.compile(r"\s+(?:và|so với|với)\s+|[,;]", flags=re.IGNORECASE)


class MentionExtractor:
    def __init__(self, catalog: MetricCatalogAdapter) -> None:
        self.phrases = sorted(
            {
                normalize_text(phrase)
                for metric in catalog
                for phrase in (metric.label, *metric.synonyms)
                if len(normalize_text(phrase)) >= 4
            },
            key=len,
            reverse=True,
        )

    def extract(self, question: str) -> list[str]:
        normalized = normalize_text(question)
        recognized = [phrase for phrase in self.phrases if phrase in normalized]
        if len(recognized) < 2 and not SPLIT_RE.search(normalized):
            return []
        parts = [part.strip(" ?.!:") for part in SPLIT_RE.split(normalized)]
        mentions = [part for part in parts if len(part.split()) >= 2]
        return list(dict.fromkeys(mentions)) if len(mentions) >= 2 else []
