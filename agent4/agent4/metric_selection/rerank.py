"""Rerank authorized candidates using catalog metadata and query evidence."""

from collections.abc import Collection
from typing import Any

import yaml

from agent4.core.catalog import MetricCatalog
from agent4.core.errors import ContractError, enforce_exact_keys

from .config import ExpansionConfig
from .errors import ConfigurationError
from .lexical import lexical_tokens, metric_terms, phrase_matches

RERANKER_VERSION = "metadata-reranker-v2"
_STAGE = "metric_rerank"


def expand_related_candidates(
    candidates: list[dict[str, Any]], allowed_metric_ids: Collection[str], config: ExpansionConfig
) -> list[dict[str, Any]]:
    """Append authorized one-hop targets before the reranker receives its input set."""
    remaining = config.max_candidates - len(candidates)
    if not config.enabled or not config.max_hops or remaining <= 0 or not candidates:
        return candidates
    try:
        data = yaml.safe_load(config.relationship_path.read_text(encoding="utf-8"))
        relationships = data["relationships"]
        if not isinstance(relationships, list) or any(
            not isinstance(edge, dict)
            or any(
                not isinstance(edge.get(key), str) or not edge[key] for key in ("source", "target")
            )
            for edge in relationships
        ):
            raise ValueError("Invalid relationship records")
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError) as exc:
        raise ConfigurationError("Cannot load metric relationships.") from exc

    ranks = {item["metric_id"]: item["rank"] for item in candidates}
    edges = sorted(
        (ranks[edge["source"]], edge["target"])
        for edge in relationships
        if edge["source"] in ranks and edge["target"] in allowed_metric_ids
    )
    target_ids = list(dict.fromkeys(target for _, target in edges if target not in ranks))
    return [
        *candidates,
        *(
            {
                "metric_id": metric_id,
                "rank": rank,
                "retrieval_sources": ["relationship"],
                "dense_score": None,
                "lexical_score": None,
                "fusion_score": None,
            }
            for rank, metric_id in enumerate(target_ids[:remaining], start=len(candidates) + 1)
        ),
    ]


def rerank_candidates(
    normalized_query: dict[str, Any],
    fusion_result: dict[str, Any],
    catalog: MetricCatalog,
    requested_view: str | None = None,
    *,
    auth_context: dict[str, Any],
) -> dict[str, Any]:
    """Score and reorder the original set, rejecting unauthorized inputs."""
    enforce_exact_keys(
        fusion_result, {"status", "candidates"}, {"fusion_method", "fusion_version"}, stage=_STAGE
    )
    if not isinstance(fusion_result["candidates"], list):
        raise ContractError("invalid_request", _STAGE, "Reranking candidates must be an array.")
    query_tokens = lexical_tokens(normalized_query["normalized_question"])
    phrase_query = f" {' '.join(query_tokens)} "
    query_terms = set(query_tokens)
    locale = normalized_query["locale"]
    if requested_view is not None and requested_view not in (
        auth_context.get("allowed_views") or []
    ):
        raise ContractError(
            "forbidden", _STAGE, "Requested view is not authorized.", final_status="forbidden"
        )

    ranked = []
    seen = set()
    for candidate in fusion_result["candidates"]:
        enforce_exact_keys(
            candidate,
            {
                "metric_id",
                "rank",
                "retrieval_sources",
                "dense_score",
                "lexical_score",
                "fusion_score",
            },
            {"mention_score"},
            stage=_STAGE,
        )
        metric_id = candidate["metric_id"]
        sources = candidate["retrieval_sources"]
        fusion_score = candidate["fusion_score"]
        if (
            not isinstance(metric_id, str)
            or not isinstance(sources, list)
            or any(not isinstance(source, str) for source in sources)
            or (
                fusion_score is not None
                and (type(fusion_score) not in (int, float) or not 0 <= fusion_score <= 3)
            )
        ):
            raise ContractError("invalid_request", _STAGE, "Invalid reranking candidate.")
        metric = catalog.get(metric_id)
        if metric is None or not catalog.validate_access(metric_id, auth_context):
            raise ContractError(
                "forbidden", _STAGE, "Candidate is not authorized.", final_status="forbidden"
            )
        if metric_id in seen:
            raise ContractError("invalid_request", _STAGE, "Duplicate reranking candidate.")
        seen.add(metric_id)
        labels, aliases = metric_terms(metric)
        localized_label = metric["label"] if locale == "vi-VN" else metric.get("label_en")
        label_match = 0.0
        language_match = 0.0
        if localized_label and phrase_matches(phrase_query, localized_label):
            label_match, language_match = 1.0, 1.0
        elif any(phrase_matches(phrase_query, term) for term in labels):
            label_match, language_match = 1.0, 0.5
        elif any(phrase_matches(phrase_query, term) for term in aliases):
            label_match, language_match = 0.95, 0.75
        else:
            for term in (*labels, *aliases):
                tokens = set(lexical_tokens(term))
                if tokens:
                    label_match = max(label_match, 0.5 * len(tokens & query_terms) / len(tokens))

        view_compatibility = float(
            requested_view is None or requested_view in metric["supported_views"]
        )
        score = 0.60 * label_match + 0.25 * view_compatibility + 0.15 * language_match
        ranked.append(
            (
                score,
                fusion_score or 0.0,
                metric_id,
                {
                    "metric_id": metric_id,
                    "rerank_score": score,
                    "score_components": {
                        "label_match": label_match,
                        "view_compatibility": view_compatibility,
                        "language_match": language_match,
                    },
                    "retrieval_sources": list(sources),
                },
            )
        )

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return {
        "ranked_candidates": [
            {**item, "rank": rank} for rank, (_, _, _, item) in enumerate(ranked, start=1)
        ],
        "reranker_version": RERANKER_VERSION,
    }
