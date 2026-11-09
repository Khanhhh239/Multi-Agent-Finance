"""Governed example-bank loading and deterministic, budgeted few-shot selection."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from itertools import combinations, product
from pathlib import Path
from typing import Any

from agent4.core.context import SUPPORTED_LOCALES
from agent4.core.errors import ContractError, enforce_exact_keys
from agent4.engine.metrics import REGISTRY

from .config import FewshotConfig
from .lexical import lexical_tokens
from .llm_selector import selection_example_payload

EXAMPLE_BANK_VERSION = "fewshot-v4"
_BANK_STAGE = "fewshot_example_bank"
_STAGE = "fewshot_retrieval"
_STRATEGIES = ("zero", "static", "similarity", "coverage", "hybrid")
_TAGS = {"decision_tags", "confusable_metrics"}
_RECORD_KEYS = {
    "example_id",
    "question",
    "locale",
    "intent",
    "expected_selection",
    "context_constraints",
    "quality_status",
    "source",
    "example_version",
    "token_count",
}
_CONTEXT_KEYS = {"supported_views", "required_dimensions", "required_time_modes"}
_REQUEST_KEYS = {
    "question",
    "locale",
    "candidate_metric_ids",
    "context",
    "max_examples",
    "token_budget",
    "selection_strategy",
    "example_bank_version",
    "compatible_only",
}


def _default_example(
    example_id: str,
    question: str,
    metric_id: str,
    views: list[str],
    tokens: int,
    *,
    approved: bool = True,
) -> dict[str, Any]:
    return {
        "example_id": example_id,
        "question": question,
        "locale": "vi-VN",
        "intent": "metric_selection",
        "expected_selection": {"status": "resolved", "metric_ids": [metric_id]},
        "context_constraints": {
            "supported_views": views,
            "required_dimensions": [],
            "required_time_modes": ["range"],
        },
        "quality_status": "approved" if approved else "draft",
        "source": "human_reviewed" if approved else "synthetic_unreviewed",
        "example_version": EXAMPLE_BANK_VERSION,
        "token_count": tokens,
    }


DEFAULT_FEWSHOT_BANK = [
    _default_example(
        "fs-margin-001",
        "Tỷ suất lợi nhuận ròng quý trước là bao nhiêu?",
        "net_profit_margin",
        ["mgmt"],
        185,
    ),
    _default_example(
        "fs-rev-001",
        "Doanh thu thuần tháng 7/2026 là bao nhiêu?",
        "net_revenue",
        ["mgmt", "tax"],
        160,
    ),
    _default_example(
        "fs-opex-001",
        "Tổng chi phí hoạt động trong quý 1/2026 là bao nhiêu?",
        "operating_expense",
        ["mgmt", "tax"],
        175,
    ),
    _default_example(
        "fs-unapproved-999", "Ví dụ chưa được duyệt", "net_revenue", ["mgmt"], 120, approved=False
    ),
]


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(_text(item) for item in value)


def _question_key(question: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", question).casefold().split()).rstrip("?.! ")


def _estimated_tokens(payload: dict[str, Any]) -> int:
    # Count UTF-8 bytes of the actual prompt item and its separator as a conservative estimate.
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + 1


def _approved_example(record: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        raise ContractError("invalid_request", _BANK_STAGE, "Expected a few-shot example object.")
    if record.get("quality_status") != "approved":
        return None
    enforce_exact_keys(record, _RECORD_KEYS, _TAGS, stage=_BANK_STAGE)
    context = record["context_constraints"]
    enforce_exact_keys(context, _CONTEXT_KEYS, stage=_BANK_STAGE)
    if (
        not all(_text(record[key]) for key in ("example_id", "intent", "source", "example_version"))
        or not isinstance(record["locale"], str)
        or record["locale"] not in SUPPORTED_LOCALES
        or not all(_string_list(context[key]) for key in _CONTEXT_KEYS)
        or not all(_string_list(record.get(key, [])) for key in _TAGS)
        or type(record["token_count"]) is not int
        or record["token_count"] < 1
    ):
        raise ContractError("invalid_request", _BANK_STAGE, "Invalid few-shot example metadata.")
    try:
        payload = selection_example_payload(record)
    except ContractError:
        # An invalid or unsafe prompt item is ineligible even if marked approved.
        return None
    return {
        **record,
        **payload,
        "token_count": max(record["token_count"], _estimated_tokens(payload)),
    }


def _legacy_example(record: dict[str, Any]) -> dict[str, Any] | None:
    enforce_exact_keys(record, {"id", "question", "answer"}, _TAGS, stage=_BANK_STAGE)
    if not _text(record["id"]) or not all(_string_list(record.get(key, [])) for key in _TAGS):
        raise ContractError("invalid_request", _BANK_STAGE, "Invalid legacy few-shot metadata.")
    try:
        payload = selection_example_payload(
            {"question": record["question"], "expected_selection": record["answer"]}
        )
    except ContractError:
        return None
    expected = payload["expected_selection"]
    ids = expected["metric_ids"]
    confusable = record.get("confusable_metrics", [])
    if not {*ids, *confusable} <= REGISTRY.keys():
        raise ContractError(
            "invalid_request", _BANK_STAGE, "Example references an unknown registry metric."
        )
    view_ids = ids or (confusable if expected["status"] == "ambiguous" else [])
    views = (
        sorted(set.intersection(*(set(REGISTRY[metric_id].views) for metric_id in view_ids)))
        if view_ids
        else ["mgmt"]
    )
    return {
        **payload,
        "example_id": record["id"],
        "locale": "vi-VN",
        "intent": "metric_selection",
        "context_constraints": {
            "supported_views": views,
            "required_dimensions": [],
            "required_time_modes": sorted(
                {
                    "as_of" if REGISTRY[metric_id].period_type == "snapshot" else "range"
                    for metric_id in ids
                }
            ),
        },
        "quality_status": "approved",
        "source": "repository_curated",
        "example_version": EXAMPLE_BANK_VERSION,
        "token_count": _estimated_tokens(payload),
        "decision_tags": record.get("decision_tags", []),
        "confusable_metrics": confusable,
    }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    record = dict(pairs)
    if len(record) != len(pairs):
        raise ValueError("Duplicate JSON keys")
    return record


def load_example_bank(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Read a server-configured JSONL bank, normalizing the repository's legacy records."""
    bank_path = Path(path) if path is not None else FewshotConfig().example_bank_path
    examples = []
    seen: set[str] = set()
    try:
        with bank_path.open(encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                record = json.loads(line, object_pairs_hook=_unique_object)
                if not isinstance(record, dict):
                    raise TypeError("Expected a JSON object")
                example = _legacy_example(record) if "id" in record else _approved_example(record)
                if example is not None:
                    if example["example_id"] in seen:
                        raise ValueError("Duplicate example ID")
                    seen.add(example["example_id"])
                    examples.append(example)
    except (OSError, TypeError, ValueError, ContractError) as exc:
        raise ContractError(
            "fewshot_unavailable",
            _BANK_STAGE,
            "Example bank could not be loaded.",
            retryable=True,
            final_status="temporarily_unavailable",
        ) from exc
    return examples


@dataclass
class _Option:
    record: dict[str, Any]
    matched: set[str]
    pairs: set[tuple[str, ...]]
    tags: set[str]
    structure: str
    similarity: float
    compatibility: float


def _eligible_options(request: dict[str, Any], bank: list[dict[str, Any]]) -> list[_Option]:
    question = _question_key(request["question"])
    tokens = set(lexical_tokens(question))
    candidates = set(request["candidate_metric_ids"])
    context = request["context"]
    view = context.get("view", "mgmt")
    dimensions = set(context.get("dimensions", []))
    time_mode = context.get("time_mode")
    options = []
    seen_ids = set()
    seen_questions = set()
    for item in bank:
        example = _approved_example(item)
        if example is None:
            continue
        example_question = _question_key(example["question"])
        constraints = example["context_constraints"]
        expected = example["expected_selection"]
        ids = set(expected["metric_ids"])
        confusable = set(example.get("confusable_metrics", []))
        relevant_ids = confusable if expected["status"] == "ambiguous" else ids
        if (
            example["example_version"] != request["example_bank_version"]
            or example["locale"] != request["locale"]
            or example_question == question
            or example["example_id"] in seen_ids
            or example_question in seen_questions
            or (request["compatible_only"] and not relevant_ids <= candidates)
            or view not in constraints["supported_views"]
            or (
                "dimensions" in context
                and not set(constraints["required_dimensions"]) <= dimensions
            )
            or (
                time_mode
                and constraints["required_time_modes"]
                and time_mode not in constraints["required_time_modes"]
            )
        ):
            continue
        seen_ids.add(example["example_id"])
        seen_questions.add(example_question)
        matched = ids & candidates
        alternatives = confusable & candidates
        pairs = product(matched, alternatives) if ids else combinations(sorted(alternatives), 2)
        tags = set(example.get("decision_tags", []))
        structure = expected["status"]
        if structure == "resolved":
            if len(ids) > 1:
                structure = "multi_metric"
            elif "comparison" in tags or "compare" in example["intent"]:
                structure = "comparison"
            else:
                structure = "single_metric"
        example_tokens = set(lexical_tokens(example_question))
        options.append(
            _Option(
                example,
                matched,
                {tuple(sorted((a, b))) for a, b in pairs if a != b},
                tags,
                structure,
                len(tokens & example_tokens) / max(1, len(tokens | example_tokens)),
                len(matched) / len(ids) if ids else 1.0,
            )
        )
    return options


def retrieve_dynamic_fewshot(
    request: dict[str, Any],
    example_bank: list[dict[str, Any]] | None = None,
    available: bool = True,
    *,
    config: FewshotConfig | None = None,
) -> dict[str, Any]:
    """Choose compatible examples without modifying the candidate set or request."""
    enforce_exact_keys(request, _REQUEST_KEYS, stage=_STAGE)
    context = request["context"]
    enforce_exact_keys(context, set(), {"view", "dimensions", "time_mode"}, stage=_STAGE)
    strategy = request["selection_strategy"]
    if (
        strategy not in _STRATEGIES
        or not _text(request["question"])
        or not isinstance(request["locale"], str)
        or request["locale"] not in SUPPORTED_LOCALES
        or not _text(request["example_bank_version"])
        or not _string_list(request["candidate_metric_ids"])
        or type(request["compatible_only"]) is not bool
        or any(
            type(request[key]) is not int or request[key] < 0
            for key in ("max_examples", "token_budget")
        )
        or not _text(context.get("view", "mgmt"))
        or not _string_list(context.get("dimensions", []))
        or ("time_mode" in context and not _text(context["time_mode"]))
    ):
        raise ContractError("invalid_request", _STAGE, "Invalid few-shot request.")
    result = {
        "status": "no_compatible_examples" if available else "fewshot_unavailable",
        "examples": [],
        "total_token_count": 0,
        "example_bank_version": request["example_bank_version"],
        "selection_strategy": strategy,
    }
    remaining = request["token_budget"]
    if not available or strategy == "zero" or not remaining or not request["max_examples"]:
        return result
    if example_bank is not None and not isinstance(example_bank, list):
        raise ContractError("invalid_request", _BANK_STAGE, "Expected a list of few-shot examples.")

    options = _eligible_options(
        request, DEFAULT_FEWSHOT_BANK if example_bank is None else example_bank
    )
    config = config or FewshotConfig()
    covered_ids: set[str] = set()
    covered_pairs: set[tuple[str, ...]] = set()
    covered_tags: set[str] = set()
    structures: set[str] = set()

    def priority(option: _Option) -> tuple[float, ...]:
        diverse = float(option.structure not in structures)
        if strategy == "static":
            return (diverse,)
        if strategy == "similarity":
            return (option.similarity,)
        pair_gain = len(option.pairs - covered_pairs)
        metric_gain = len(option.matched - covered_ids)
        tag_gain = len(option.tags - covered_tags)
        if strategy == "coverage":
            return (pair_gain, metric_gain, tag_gain, diverse)
        score = (
            config.alpha * option.similarity
            + config.beta * metric_gain
            + config.gamma * (pair_gain + tag_gain)
            + config.delta * diverse
        )
        return (score, option.similarity)

    for rank in range(1, request["max_examples"] + 1):
        affordable = (option for option in options if option.record["token_count"] <= remaining)
        best = max(affordable, key=priority, default=None)
        if best is None:
            break
        options.remove(best)
        covered_ids.update(best.matched)
        covered_pairs.update(best.pairs)
        covered_tags.update(best.tags)
        structures.add(best.structure)
        example = best.record
        remaining -= example["token_count"]
        result["examples"].append(
            {
                "example_id": example["example_id"],
                "question": example["question"],
                "expected_selection": example["expected_selection"],
                "matched_metric_ids": sorted(best.matched),
                "similarity_score": best.similarity,
                "compatibility_score": best.compatibility,
                "rank": rank,
                "token_count": example["token_count"],
            }
        )
    if result["examples"]:
        result.update(
            status="examples_found", total_token_count=request["token_budget"] - remaining
        )
    return result
