"""Find catalog phrases in questions without treating overlapping names as extra metrics."""

from collections import defaultdict
from typing import Any

from .lexical import lexical_tokens, metric_terms


def retrieve_mentions(question: str, metrics: list[dict[str, Any]]) -> dict[str, Any]:
    tokens = lexical_tokens(question)
    phrases: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for metric in metrics:
        labels, aliases = metric_terms(metric)
        for term in (*labels, *aliases):
            phrase = lexical_tokens(term)
            if phrase:
                phrases[phrase].add(metric["metric_id"])

    spans = []
    for phrase, ids in phrases.items():
        for start in range(len(tokens) - len(phrase) + 1):
            end = start + len(phrase)
            if tokens[start:end] == phrase:
                spans.append((start, end, ids))

    selected: list[tuple[int, int]] = []
    matches: dict[str, list[str]] = defaultdict(list)
    scores: dict[str, int] = {}
    for start, end, ids in sorted(spans, key=lambda span: (span[0] - span[1], span[0])):
        if any(start < other_end and other_start < end for other_start, other_end in selected):
            continue
        selected.append((start, end))
        for metric_id in sorted(ids):
            term = " ".join(tokens[start:end])
            if term not in matches[metric_id]:
                matches[metric_id].append(term)
            # A shared phrase is evidence for retrieval, but not a unique mention.
            scores.setdefault(metric_id, 0)
            if len(ids) == 1:
                scores[metric_id] = max(scores[metric_id], end - start)
    ranked = sorted(matches, key=lambda metric_id: (-scores[metric_id], metric_id))
    return {
        "source": "mention",
        "hits": [
            {
                "metric_id": metric_id,
                "rank": rank,
                "score": scores[metric_id],
                "matched_terms": matches[metric_id],
            }
            for rank, metric_id in enumerate(ranked, start=1)
        ],
    }
