"""Deterministic phrase and token retrieval over governed metric names."""

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Collection
from typing import Any

from agent4.core.catalog import MetricCatalog
from agent4.core.errors import ContractError, enforce_exact_keys

LEXICAL_INDEX_VERSION = "metric-lexical-index-v2"
_STAGE = "lexical_retrieval"
_STOP_WORDS = {
    "and",
    "the",
    "for",
    "of",
    "in",
    "is",
    "what",
    "how",
    "và",
    "của",
    "là",
    "bao",
    "nhiêu",
    "này",
    "theo",
}


def lexical_tokens(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold()))


def metric_terms(metric: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    labels = tuple(
        dict.fromkeys(label for label in (metric["label"], metric.get("label_en")) if label)
    )
    aliases = tuple(dict.fromkeys([*metric.get("aliases", ()), *metric.get("synonyms", ())]))
    return labels, aliases


def phrase_matches(query: str, term: str) -> bool:
    phrase = " ".join(lexical_tokens(term))
    return bool(phrase) and f" {phrase} " in query


def lexical_retrieve(
    request: dict[str, Any],
    catalog: MetricCatalog,
    *,
    allowed_metric_ids: Collection[str] | None = None,
) -> dict[str, Any]:
    enforce_exact_keys(request, {"query", "top_k", "index_version"}, stage=_STAGE)
    if (
        not isinstance(request["query"], str)
        or not request["query"].strip()
        or type(request["top_k"]) is not int
        or request["top_k"] < 1
        or request["index_version"] != LEXICAL_INDEX_VERSION
    ):
        raise ContractError("invalid_request", _STAGE, "Invalid lexical retrieval request.")

    query = lexical_tokens(request["query"])
    phrase_query = f" {' '.join(query)} "
    query_terms = set(query) - _STOP_WORDS
    entries = []
    frequency: Counter[str] = Counter()
    for metric in catalog.list_approved_metrics():
        if allowed_metric_ids is not None and metric["metric_id"] not in allowed_metric_ids:
            continue
        labels, aliases = metric_terms(metric)
        shared = {
            token for term in (*labels, *aliases) for token in lexical_tokens(term)
        } & query_terms
        frequency.update(shared)
        entries.append((metric["metric_id"], labels, aliases, shared))

    hits = []
    for metric_id, labels, aliases, shared in entries:
        label_hits = [term for term in labels if phrase_matches(phrase_query, term)]
        alias_hits = [term for term in aliases if phrase_matches(phrase_query, term)]
        score = sum(math.log1p(len(entries) / frequency[token]) for token in sorted(shared))
        score += max((8 + len(lexical_tokens(term)) for term in label_hits), default=0)
        score += max((4 + len(lexical_tokens(term)) for term in alias_hits), default=0)
        if score:
            evidence = list(dict.fromkeys([*label_hits, *alias_hits])) or sorted(shared)
            hits.append({"metric_id": metric_id, "score": score, "matched_terms": evidence})
    hits.sort(key=lambda hit: (-hit["score"], hit["metric_id"]))
    return {
        "source": "lexical",
        "hits": [
            {**hit, "rank": rank} for rank, hit in enumerate(hits[: request["top_k"]], start=1)
        ],
    }
