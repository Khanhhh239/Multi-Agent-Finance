"""Validate benchmark data or evaluate independently produced predictions.

No model, database connection, or test harness is constructed on import. An adapter
must be an async callable ``predict(request: dict) -> dict``; it receives only the
input side of each case. See docs/evaluation.md for the complete adapter contract.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import inspect
import json
import math
import random
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

# Support both `python vals/run_eval.py` and `python -m vals.run_eval`.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent4.engine.metrics import REGISTRY
from agent4.metric_selection.config import load_config
from agent4.metric_selection.errors import ConfigurationError
from agent4.text2sql.models import (
    AuthContext,
    FilterDraft,
    SemanticPlanDraft,
)

RUNNER_VERSION = "contract-eval.v1"
DEFAULT_DATASET = ROOT / "data/eval/contract_benchmark_questions.jsonl"
CATEGORIES = {
    "single_metric_aggregate",
    "timeseries_and_comparison",
    "dimensional_breakdown_filter_topk",
    "business_views",
    "ambiguous_needs_clarification",
    "unsupported_out_of_catalog",
    "no_data_and_edge_cases",
    "authorization_and_security",
    "multi_metrics",
}
FinalStatus = Literal[
    "ready",
    "needs_clarification",
    "unsupported",
    "forbidden",
    "no_data",
    "temporarily_unavailable",
    "error",
]
SelectionStatus = Literal["resolved", "ambiguous", "unsupported"]
Scalar = str | StrictInt | StrictBool | None
Adapter = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueryContext(StrictModel):
    reference_date: date
    timezone: Literal["Asia/Ho_Chi_Minh"]


class Column(StrictModel):
    key: str
    type: Literal["date", "string", "decimal", "integer", "boolean"]
    unit: str | None = None


class TableResult(StrictModel):
    columns: list[Column]
    rows: list[dict[str, Scalar]]
    row_count: StrictInt = Field(ge=0)
    truncated: bool

    @model_validator(mode="after")
    def consistent(self) -> TableResult:
        keys = [column.key for column in self.columns]
        if len(keys) != len(set(keys)) or self.row_count != len(self.rows):
            raise ValueError("Duplicate columns or inconsistent row_count")
        for row in self.rows:
            if set(row) != set(keys):
                raise ValueError("Result rows must match the declared columns")
            for column in self.columns:
                value = row[column.key]
                if value is None:
                    continue
                if column.type == "decimal":
                    try:
                        finite = Decimal(str(value)).is_finite()
                    except InvalidOperation as exc:
                        raise ValueError("Invalid decimal result") from exc
                    if isinstance(value, bool) or not finite:
                        raise ValueError("Decimal results must be finite numbers")
                elif column.type == "integer" and type(value) is not int:
                    raise ValueError("Integer column contains a non-integer")
                elif column.type == "boolean" and type(value) is not bool:
                    raise ValueError("Boolean column contains a non-boolean")
                elif column.type in {"date", "string"} and not isinstance(value, str):
                    raise ValueError("String/date column contains a non-string")
                if column.type == "date":
                    date.fromisoformat(value)
        return self


class ResultReference(StrictModel):
    snapshot_id: str = Field(min_length=1)
    method: Literal["independent_sql", "human_reconciliation"]
    reviewer: str = Field(min_length=1)
    version: str = Field(min_length=1)


class BenchmarkCase(StrictModel):
    schema_version: Literal["benchmark-case.v2"]
    dataset_version: str = Field(min_length=1)
    id: str = Field(pattern=r"^BM-\d{3}$")
    split: Literal["dev", "test"]
    case_category: str
    locale: Literal["vi-VN", "en-US"]
    user_query: str = Field(min_length=1, max_length=4000)
    auth_context: AuthContext
    query_context: QueryContext
    expected_selection_status: SelectionStatus
    expected_metric_ids: list[str]
    expected_dimensions: list[str]
    expected_filters: list[FilterDraft]
    expected_plan: SemanticPlanDraft | None
    expected_result: TableResult | None
    expected_final_status: FinalStatus
    expected_warning_codes: list[str]
    security_tags: list[str]
    fixture_requirements: list[str]
    review_status: Literal["draft", "approved"]
    notes: str
    result_reference: ResultReference | None = None

    @model_validator(mode="after")
    def consistent(self) -> BenchmarkCase:
        if self.case_category not in CATEGORIES:
            raise ValueError(f"Unknown category: {self.case_category}")
        if not self.user_query.strip():
            raise ValueError("user_query must not be blank")
        ids = self.expected_metric_ids
        if len(ids) != len(set(ids)) or set(ids) - REGISTRY.keys():
            raise ValueError("Expected metric IDs must be unique canonical catalog IDs")
        if (self.expected_selection_status == "resolved") != bool(ids):
            raise ValueError("Only resolved selections must have nonempty expected_metric_ids")
        if self.case_category == "single_metric_aggregate" and len(ids) != 1:
            raise ValueError("Single-metric cases must select exactly one metric")
        if self.case_category == "multi_metrics" and len(ids) < 2:
            raise ValueError("multi_metrics must explicitly request at least two metrics")
        if self.expected_plan is not None:
            plan = self.expected_plan
            if set(plan.metric_ids) != set(ids):
                raise ValueError("Plan metrics must match expected_metric_ids")
            if plan.dimensions != self.expected_dimensions or plan.filters != self.expected_filters:
                raise ValueError("Plan dimensions/filters must match top-level expectations")
            if plan.status == "ready":
                for metric_id in ids:
                    metric = REGISTRY[metric_id]
                    if plan.view not in metric.views:
                        raise ValueError(f"Unsupported catalog view for {metric_id}")
                    if set(plan.dimensions) - set(metric.group_bys):
                        raise ValueError(f"Unsupported catalog dimension for {metric_id}")
                    mode = "as_of" if metric.period_type == "snapshot" else "range"
                    if plan.time.mode != mode:
                        raise ValueError(f"Wrong time mode for {metric_id}")
        if self.expected_final_status in {"ready", "no_data"} and (
            self.expected_plan is None or self.expected_plan.status != "ready"
        ):
            raise ValueError("Executable cases require a ready expected_plan")
        if self.expected_result is not None:
            if self.review_status != "approved" or self.result_reference is None:
                raise ValueError("Numerical gold requires independent review and result_reference")
            if self.expected_final_status not in {"ready", "no_data"}:
                raise ValueError("Terminal rejection cases cannot carry a numerical result")
        if self.split == "test" and self.review_status != "approved":
            raise ValueError("Held-out test cases must be reviewed before evaluation")
        return self

    def adapter_input(self, seed: int) -> dict[str, Any]:
        """Explicit allowlist: no expected_*, category, fixture hints or review notes."""
        return {
            "contract_version": "evaluation-input.v1",
            "id": self.id,
            "user_query": self.user_query,
            "locale": self.locale,
            "auth_context": self.auth_context.model_dump(mode="json"),
            "query_context": self.query_context.model_dump(mode="json"),
            "options": {"include_table": True, "explain_metrics": True},
            "seed": seed,
        }


class Selection(StrictModel):
    status: SelectionStatus
    metric_ids: list[str]
    clarification_question: str | None = None

    @model_validator(mode="after")
    def consistent(self) -> Selection:
        if len(self.metric_ids) != len(set(self.metric_ids)):
            raise ValueError("Duplicate selected metric IDs")
        if (self.status == "resolved") != bool(self.metric_ids):
            raise ValueError("Invalid selection status/metric_ids combination")
        if self.status == "ambiguous" and not self.clarification_question:
            raise ValueError("Ambiguous selection requires a clarification question")
        # Unknown IDs are deliberately preserved to measure invalid_metric_rate.
        return self


class Usage(StrictModel):
    input_tokens: StrictInt = Field(ge=0)
    output_tokens: StrictInt = Field(ge=0)


class Execution(StrictModel):
    attempted: bool
    succeeded: bool
    safety_passed: bool | None = None
    query_fingerprint: str | None = None

    @model_validator(mode="after")
    def consistent(self) -> Execution:
        if self.succeeded and not self.attempted:
            raise ValueError("Execution cannot succeed without an attempt")
        return self


class StageError(StrictModel):
    stage: str
    code: str


class Prediction(StrictModel):
    id: str
    retrieved_metric_ids: list[str] | None = None
    selection: Selection | None = None
    plan: SemanticPlanDraft | None = None
    final_status: FinalStatus | None = None
    data_snapshot_id: str | None = None
    result: TableResult | None = None
    answer: str | None = None
    clarification_question: str | None = None
    warning_codes: list[str] = Field(default_factory=list)
    execution: Execution | None = None
    usage: Usage | None = None
    latency_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    stage_latency_ms: dict[str, float] = Field(default_factory=dict)
    selected_example_ids: list[str] = Field(default_factory=list)
    error: StageError | None = None

    @model_validator(mode="after")
    def consistent(self) -> Prediction:
        candidates = self.retrieved_metric_ids
        if candidates is not None and len(candidates) != len(set(candidates)):
            raise ValueError("Duplicate retrieved metric IDs")
        if any(not math.isfinite(v) or v < 0 for v in self.stage_latency_ms.values()):
            raise ValueError("Invalid stage latency")
        return self


class Judgment(StrictModel):
    """External review bound to exact prediction bytes, not a pipeline self-score."""

    id: str
    prediction_sha256: str
    judge_id: str = Field(min_length=1)
    judge_version: str = Field(min_length=1)
    numerical_correctness: StrictBool
    faithfulness: StrictBool
    answer_accuracy: StrictBool


def digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    def reject_constant(value: str) -> Any:
        raise ValueError(f"Non-finite JSON constant: {value}")

    def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise ValueError("Duplicate JSON object key")
            output[key] = value
        return output

    records = []
    with path.open(encoding="utf-8") as source:
        for number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(
                    line, parse_constant=reject_constant, object_pairs_hook=unique_keys
                )
            except ValueError as exc:
                raise ValueError(f"{path.name}:{number}: invalid JSON") from exc
            if not isinstance(record, dict):
                raise TypeError(f"{path.name}:{number}: expected a JSON object")
            records.append(record)
    if not records:
        raise ValueError(f"{path.name}: dataset/file is empty")
    return records


def load_cases(path: Path) -> list[BenchmarkCase]:
    cases = []
    ids: set[str] = set()
    queries: set[str] = set()
    for number, record in enumerate(read_jsonl(path), 1):
        try:
            case = BenchmarkCase.model_validate(record)
        except ValueError as exc:
            raise ValueError(f"{path.name}: record {number}: {exc}") from exc
        query_key = " ".join(case.user_query.casefold().split()).rstrip("?.! ")
        if case.id in ids or query_key in queries:
            raise ValueError(f"Duplicate ID or question: {case.id}")
        ids.add(case.id)
        queries.add(query_key)
        cases.append(case)
    if len({case.dataset_version for case in cases}) != 1:
        raise ValueError("Mixed dataset versions are not allowed")
    return cases


def load_predictions(path: Path, cases: list[BenchmarkCase]) -> dict[str, Prediction]:
    predictions: dict[str, Prediction] = {}
    allowed_ids = {case.id for case in cases}
    for record in read_jsonl(path):
        prediction = Prediction.model_validate(record)
        if prediction.id in predictions or prediction.id not in allowed_ids:
            raise ValueError(f"Duplicate or unexpected prediction ID: {prediction.id}")
        predictions[prediction.id] = prediction
    # Missing predictions are scored as failures, never dropped from denominators.
    return predictions


def load_example_manifest(path: Path, cases: list[BenchmarkCase]) -> set[str]:
    """Audit exact question overlap without invoking retrieval or an embedding model."""
    queries = {" ".join(case.user_query.casefold().split()).rstrip("?.! ") for case in cases}
    ids: set[str] = set()
    for record in read_jsonl(path):
        example_id = record.get("id", record.get("example_id"))
        question = record.get("question", record.get("user_query"))
        if not isinstance(example_id, str) or not isinstance(question, str) or not question.strip():
            raise ValueError("Example bank requires a string id/example_id and question/user_query")
        if example_id in ids:
            raise ValueError("Duplicate example-bank ID")
        if " ".join(question.casefold().split()).rstrip("?.! ") in queries:
            raise ValueError(f"Benchmark question appears in the few-shot bank: {example_id}")
        ids.add(example_id)
    return ids


def table_equal(
    expected: TableResult,
    actual: TableResult | None,
    *,
    ordered: bool,
    abs_tol: Decimal,
    rel_tol: Decimal,
) -> bool:
    if actual is None or expected.truncated != actual.truncated:
        return False
    exp_columns = {c.key: (c.type, c.unit) for c in expected.columns}
    act_columns = {c.key: (c.type, c.unit) for c in actual.columns}
    if exp_columns != act_columns or len(expected.rows) != len(actual.rows):
        return False

    def row_equal(left: dict[str, Scalar], right: dict[str, Scalar]) -> bool:
        for key, (kind, _) in exp_columns.items():
            a, b = left[key], right[key]
            if a is None or b is None:
                if a is not None or b is not None:
                    return False
            elif kind in {"decimal", "integer"}:
                a_dec, b_dec = Decimal(str(a)), Decimal(str(b))
                if abs(a_dec - b_dec) > max(abs_tol, rel_tol * abs(a_dec)):
                    return False
            elif type(a) is not type(b) or a != b:
                return False
        return True

    if ordered:
        return all(row_equal(a, b) for a, b in zip(expected.rows, actual.rows, strict=True))
    # Bipartite matching preserves duplicates and avoids greedy mismatches when
    # numeric tolerances allow a row to match more than one candidate.
    edges = [
        [j for j, other in enumerate(actual.rows) if row_equal(row, other)] for row in expected.rows
    ]
    matched: dict[int, int] = {}

    def assign(index: int, visited: set[int]) -> bool:
        for candidate in edges[index]:
            if candidate in visited:
                continue
            visited.add(candidate)
            if candidate not in matched or assign(matched[candidate], visited):
                matched[candidate] = index
                return True
        return False

    return all(assign(index, set()) for index in range(len(expected.rows)))


def plan_equal(expected: SemanticPlanDraft, actual: SemanticPlanDraft | None) -> bool:
    if actual is None:
        return False
    # Clarification wording may vary; unresolved slots and decisions must agree.
    left, right = expected.model_dump(mode="json"), actual.model_dump(mode="json")
    for value in (left, right):
        value.pop("question_for_user")
        for key in ("metric_ids", "dimensions", "unresolved_slots"):
            value[key] = sorted(value[key])
        for item in value["filters"]:
            if item["operator"] == "in":
                item["values"] = sorted(item["values"])
        value["filters"] = sorted(value["filters"], key=lambda f: json.dumps(f, sort_keys=True))
    return left == right


def score_case(
    case: BenchmarkCase,
    prediction: Prediction | None,
    mode: str,
    ks: list[int],
    abs_tol: Decimal,
    rel_tol: Decimal,
) -> dict[str, Any]:
    checks: dict[str, bool | None] = {}
    failures = []
    gold = set(case.expected_metric_ids)
    retrieval = None
    if gold and (
        mode == "retrieval" or (prediction and prediction.retrieved_metric_ids is not None)
    ):
        ranked = prediction.retrieved_metric_ids if prediction else None
        ranked = ranked or []
        ranks = [ranked.index(metric) + 1 for metric in gold if metric in ranked]
        retrieval = {
            "recall_at_k": {str(k): len(gold & set(ranked[:k])) / len(gold) for k in ks},
            "precision_at_k": {str(k): len(gold & set(ranked[:k])) / k for k in ks},
            "all_metrics_covered_at_k": {str(k): gold <= set(ranked[:k]) for k in ks},
            "reciprocal_rank": 1 / min(ranks) if ranks else 0.0,
        }
        if not gold.issubset(ranked):
            failures.append("retrieval_failure")
    selection = prediction.selection if prediction else None
    if mode == "selection" or selection is not None:
        checks["selection_exact_match"] = bool(
            selection
            and selection.status == case.expected_selection_status
            and set(selection.metric_ids) == gold
        )
        if not checks["selection_exact_match"]:
            failures.append("metric_selection_failure")
        if prediction and prediction.retrieved_metric_ids is not None and selection:
            checks["selection_within_candidates"] = set(selection.metric_ids) <= set(
                prediction.retrieved_metric_ids
            )
            if not checks["selection_within_candidates"]:
                failures.append("metric_selection_failure")
    if mode == "e2e":
        checks["final_status_match"] = bool(
            prediction and prediction.final_status == case.expected_final_status
        )
        checks["required_warnings_present"] = bool(
            prediction and set(case.expected_warning_codes) <= set(prediction.warning_codes)
        )
        if not checks["required_warnings_present"]:
            failures.append("missing_required_warning")
        if case.expected_final_status == "ready":
            checks["ready_response_complete"] = bool(
                prediction
                and prediction.result
                and prediction.result.row_count
                and prediction.answer
                and prediction.answer.strip()
            )
            if not checks["ready_response_complete"]:
                failures.append("incomplete_response")
        if case.expected_plan is not None:
            checks["plan_match"] = plan_equal(
                case.expected_plan, prediction.plan if prediction else None
            )
            if not checks["plan_match"]:
                failures.append("invalid_parameters")
        if case.expected_final_status == "needs_clarification":
            question = (
                (
                    prediction.clarification_question
                    or (prediction.plan.question_for_user if prediction.plan else None)
                    or (selection.clarification_question if selection else None)
                )
                if prediction
                else None
            )
            checks["clarification_present"] = bool(question and question.strip())
            if not checks["final_status_match"] or not checks["clarification_present"]:
                failures.append("ambiguous_query_handling_failure")
        if case.expected_result is not None:
            checks["snapshot_match"] = bool(
                prediction
                and case.result_reference
                and prediction.data_snapshot_id == case.result_reference.snapshot_id
            )
            checks["result_match"] = (
                table_equal(
                    case.expected_result,
                    prediction.result if prediction else None,
                    ordered=bool(
                        case.expected_plan
                        and case.expected_plan.operation in {"rank", "timeseries"}
                    ),
                    abs_tol=abs_tol,
                    rel_tol=rel_tol,
                )
                and checks["snapshot_match"]
            )
            if not checks["result_match"]:
                failures.append("sql_result_failure")
        if case.security_tags:
            execution = prediction.execution if prediction else None
            rejected = case.expected_final_status in {
                "forbidden",
                "unsupported",
                "needs_clarification",
            }
            checks["safety_pass"] = (
                bool(
                    prediction
                    and execution
                    and checks["final_status_match"]
                    and (not execution.attempted if rejected else execution.safety_passed is True)
                    and (prediction.result is None if rejected else True)
                )
                if execution is not None
                else None
            )
            if checks["safety_pass"] is False:
                failures.append("safety_failure")
        if not checks["final_status_match"]:
            failures.append("final_status_failure")
    if prediction is None or prediction.error:
        stage = prediction.error.stage if prediction and prediction.error else "prediction"
        failures.append(
            {
                "sql_generation": "sql_generation_failure",
                "sql_compilation": "sql_generation_failure",
                "sql_execution": "sql_execution_failure",
                "answer_validation": "answer_hallucination",
                "retrieval": "retrieval_failure",
                "metric_selection": "metric_selection_failure",
            }.get(stage, "runtime_failure")
        )
    return {
        "id": case.id,
        "case_category": case.case_category,
        "expected_metric_ids": case.expected_metric_ids,
        "predicted_metric_ids": selection.metric_ids if selection else None,
        "expected_final_status": case.expected_final_status,
        "predicted_final_status": prediction.final_status if prediction else None,
        "checks": checks,
        "retrieval": retrieval,
        "retrieval_observed": bool(prediction and prediction.retrieved_metric_ids is not None),
        "failure_categories": sorted(set(failures)),
        "prediction_sha256": digest(prediction.model_dump(mode="json")) if prediction else None,
    }


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lo, hi = math.floor(position), math.ceil(position)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def summarize(
    cases: list[BenchmarkCase],
    predictions: dict[str, Prediction],
    rows: list[dict[str, Any]],
    mode: str,
    ks: list[int],
    rates: tuple[Decimal | None, Decimal | None],
    judgments: dict[str, Judgment],
) -> dict[str, Any]:
    def check_metric(name: str, denominator: int | None = None) -> dict[str, Any]:
        values = [row["checks"][name] for row in rows if row["checks"].get(name) is not None]
        count = denominator if denominator is not None else len(values)
        return {
            "value": sum(values) / count if count else None,
            "scored": len(values),
            "eligible": count,
        }

    selected = [
        predictions[c.id].selection
        for c in cases
        if c.id in predictions and predictions[c.id].selection
    ]
    gold_sets = {case.id: set(case.expected_metric_ids) for case in cases}
    predicted_count = sum(len(selection.metric_ids) for selection in selected)
    true_positive = sum(
        len(set(p.selection.metric_ids) & gold_sets[c.id])
        for c in cases
        if (p := predictions.get(c.id)) and p.selection
    )
    gold_count = sum(len(ids) for ids in gold_sets.values())
    selection_measured = mode == "selection" or bool(selected)
    precision = true_positive / predicted_count if predicted_count else 0.0
    recall = true_positive / gold_count if gold_count else 0.0
    retrieval_rows = [row["retrieval"] for row in rows if row["retrieval"] is not None]
    retrieval_eligible = sum(bool(case.expected_metric_ids) for case in cases)
    retrieval_measured = mode == "retrieval" or bool(retrieval_rows)
    retrieval = {
        name: {
            str(k): sum(row[name][str(k)] for row in retrieval_rows) / retrieval_eligible
            if retrieval_measured and retrieval_eligible
            else None
            for k in ks
        }
        for name in ("recall_at_k", "precision_at_k", "all_metrics_covered_at_k")
    }
    retrieval["mrr"] = (
        sum(row["reciprocal_rank"] for row in retrieval_rows) / retrieval_eligible
        if retrieval_measured and retrieval_eligible
        else None
    )
    retrieval["coverage"] = {
        "scored": sum(
            row["retrieval_observed"] and bool(row["expected_metric_ids"]) for row in rows
        ),
        "eligible": retrieval_eligible,
    }
    unknown = sum(
        metric not in REGISTRY for selection in selected for metric in selection.metric_ids
    )
    selection_metrics = {
        "exact_match_accuracy": check_metric("selection_exact_match", len(cases))
        if selection_measured
        else None,
        "precision": precision if selection_measured else None,
        "recall": recall if selection_measured else None,
        "f1": (2 * precision * recall / (precision + recall) if precision + recall else 0.0)
        if selection_measured
        else None,
        "invalid_metric_rate": unknown / predicted_count
        if predicted_count
        else (0.0 if selected else None),
        "invalid_metric_count": unknown,
        "coverage": {"scored": len(selected), "eligible": len(cases)},
    }
    executions = [p.execution for c in cases if (p := predictions.get(c.id)) and p.execution]
    attempts = [execution for execution in executions if execution.attempted]
    result_eligible = sum(case.expected_result is not None for case in cases)
    security_eligible = sum(bool(case.security_tags) for case in cases)
    latencies = [
        p.latency_ms for c in cases if (p := predictions.get(c.id)) and p.latency_ms is not None
    ]
    usages = [p.usage for c in cases if (p := predictions.get(c.id)) and p.usage is not None]
    complete_usage = bool(usages) and len(usages) == len(cases)
    prices_known = all(rate is not None for rate in rates)
    cost = (
        sum(
            Decimal(u.input_tokens) * rates[0] + Decimal(u.output_tokens) * rates[1] for u in usages
        )
        / Decimal(1_000_000)
        if prices_known and complete_usage
        else None
    )
    reviewed = [judgments[c.id] for c in cases if c.id in judgments]
    return {
        "count": len(cases),
        "prediction_count": sum(c.id in predictions for c in cases),
        "retrieval": retrieval,
        "selection": selection_metrics,
        "planning": {"exact_match": check_metric("plan_match") if mode == "e2e" else None},
        "sql": {
            "execution_accuracy": check_metric("result_match", result_eligible)
            if mode == "e2e"
            else None,
            "execution_error_rate": mean([not execution.succeeded for execution in attempts]),
            "attempted": len(attempts),
            "execution_evidence_coverage": {"scored": len(executions), "eligible": len(cases)},
            "safety_test_pass_rate": check_metric("safety_pass", security_eligible)
            if mode == "e2e" and executions
            else None,
        },
        "answer": {
            key: {
                "value": mean([getattr(judgment, key) for judgment in reviewed]),
                "scored": len(reviewed),
                "eligible": len(cases),
            }
            for key in ("numerical_correctness", "faithfulness", "answer_accuracy")
        }
        | {"independently_reviewed": len(reviewed), "eligible": len(cases)},
        "e2e": {
            "status_accuracy": check_metric("final_status_match") if mode == "e2e" else None,
            "latency_p50_ms": percentile(latencies, 0.5),
            "latency_p95_ms": percentile(latencies, 0.95),
            "latency_samples": len(latencies),
            "average_tokens_observed": mean([u.input_tokens + u.output_tokens for u in usages]),
            "usage_samples": len(usages),
            "total_cost_usd": float(cost) if cost is not None else None,
            "cost_per_query_usd": float(cost / len(cases)) if cost is not None else None,
        },
        "failures": dict(Counter(failure for row in rows for failure in row["failure_categories"])),
        "gold_result_coverage": {"reviewed": result_eligible, "total": len(cases)},
    }


def flatten_metrics(value: dict[str, Any], prefix: str = "") -> dict[str, float]:
    output = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            output.update(flatten_metrics(item, path))
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            output[path] = item
    return output


def compare_baseline(report: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    if report["metadata"]["comparison_key"] != baseline.get("metadata", {}).get("comparison_key"):
        raise ValueError(
            "Baseline is not comparable: dataset, catalog, mode, filters or scoring settings differ"
        )
    current, previous = flatten_metrics(report["metrics"]), flatten_metrics(baseline["metrics"])
    return {
        "comparable": True,
        "deltas": {key: current[key] - previous[key] for key in current.keys() & previous.keys()},
        "lost_measurements": sorted(previous.keys() - current.keys()),
        "new_measurements": sorted(current.keys() - previous.keys()),
        "changed_run_metadata": {
            key: {"baseline": baseline["metadata"].get(key), "current": report["metadata"].get(key)}
            for key in ("model_version", "prompt_version", "config_sha256", "example_bank_sha256")
            if baseline["metadata"].get(key) != report["metadata"].get(key)
        },
    }


def quality_gates(metrics: dict[str, Any], thresholds: dict[str, Any]) -> list[dict[str, Any]]:
    flat = flatten_metrics(metrics)
    checks = []
    for path, bounds in thresholds.items():
        if not isinstance(bounds, dict) or not bounds or set(bounds) - {"min", "max"}:
            raise ValueError(f"Invalid threshold bounds for {path}")
        if any(
            not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v)
            for v in bounds.values()
        ):
            raise ValueError(f"Thresholds must be finite numbers: {path}")
        if "min" in bounds and "max" in bounds and bounds["min"] > bounds["max"]:
            raise ValueError(f"Threshold minimum exceeds maximum: {path}")
        value = flat.get(path)
        parent: Any = metrics
        for part in path.split(".")[:-1]:
            parent = parent.get(part, {}) if isinstance(parent, dict) else {}
        coverage = (
            parent if isinstance(parent, dict) and {"scored", "eligible"} <= parent.keys() else None
        )
        if coverage is None and path.startswith(("selection.", "retrieval.")):
            coverage = metrics.get(path.split(".")[0], {}).get("coverage")
        if path in {"e2e.latency_p50_ms", "e2e.latency_p95_ms", "e2e.average_tokens_observed"}:
            key = "usage_samples" if path.endswith("average_tokens_observed") else "latency_samples"
            coverage = {
                "scored": metrics.get("e2e", {}).get(key, 0),
                "eligible": metrics.get("count", 0),
            }
        complete = coverage is None or (
            coverage["eligible"] > 0 and coverage["scored"] == coverage["eligible"]
        )
        passed = (
            value is not None
            and all(
                value >= bound if op == "min" else value <= bound for op, bound in bounds.items()
            )
            and complete
        )
        checks.append(
            {
                "metric": path,
                "value": value,
                "bounds": bounds,
                "coverage_complete": complete,
                "passed": passed,
            }
        )
    return checks


async def collect_predictions(
    cases: list[BenchmarkCase],
    adapter: Adapter,
    seed: int,
    timeout_s: float,
) -> dict[str, Prediction]:
    predictions = {}
    for case in cases:
        started = time.perf_counter()
        try:
            raw = await asyncio.wait_for(adapter(case.adapter_input(seed)), timeout=timeout_s)
            prediction = Prediction.model_validate(raw)
            if prediction.id != case.id:
                raise ValueError("Adapter returned a different case ID")
            prediction.latency_ms = (time.perf_counter() - started) * 1000
        except Exception as exc:  # noqa: BLE001 -- arbitrary adapter failures must remain in denominators
            # Record a failure, retain it in all denominators; omit exception text
            # because provider/database messages may contain SQL or credentials.
            prediction = Prediction(
                id=case.id,
                final_status="temporarily_unavailable"
                if isinstance(exc, TimeoutError)
                else "error",
                error=StageError(stage="adapter", code=type(exc).__name__),
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        predictions[case.id] = prediction
    return predictions


def import_adapter(spec: str) -> Adapter:
    module_name, separator, name = spec.partition(":")
    if not separator or not module_name or not name:
        raise ValueError("Adapter must be module.path:async_predict_function")
    adapter = getattr(importlib.import_module(module_name), name)
    if not inspect.iscoroutinefunction(adapter):
        raise ValueError(
            "Adapter must be async; enforce database/provider limits inside the adapter"
        )
    return adapter


def git_state() -> dict[str, Any]:
    def git(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    commit, status = git("rev-parse", "HEAD"), git("status", "--porcelain")
    return {"commit": commit, "dirty": bool(status) if status is not None else None}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Check schemas only; no evaluation or report writes",
    )
    parser.add_argument("--mode", choices=("retrieval", "selection", "e2e"), default="e2e")
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--category", action="append", choices=sorted(CATEGORIES))
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--adapter", help="Async input-only adapter: module.path:predict")
    source.add_argument("--predictions", type=Path, help="Score previously recorded predictions")
    parser.add_argument(
        "--judgments", type=Path, help="Independent answer reviews bound to prediction hashes"
    )
    parser.add_argument(
        "--example-bank",
        type=Path,
        help="Versioned few-shot bank to audit overlap and selected IDs",
    )
    parser.add_argument("--config", type=Path, default=ROOT / "config/selection.yaml")
    parser.add_argument("--model-version", default="unreported")
    parser.add_argument("--prompt-version", default="unreported")
    parser.add_argument("--seed", type=int, default=20261101)
    parser.add_argument("--ks", type=int, nargs="+", default=[5, 10])
    parser.add_argument("--abs-tol", type=Decimal, default=Decimal(0))
    parser.add_argument("--rel-tol", type=Decimal, default=Decimal(0))
    parser.add_argument("--adapter-timeout-s", type=float, default=60.0)
    parser.add_argument("--input-usd-per-million", type=Decimal)
    parser.add_argument("--output-usd-per-million", type=Decimal)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument(
        "--thresholds", type=Path, help='JSON mapping metric paths to {"min": value, "max": value}'
    )
    parser.add_argument(
        "--output-dir", type=Path, help="New directory; existing directories are never overwritten"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if any(k < 1 for k in args.ks):
            raise ValueError("Every K must be positive")
        args.ks = sorted(set(args.ks))
        numbers = [
            args.abs_tol,
            args.rel_tol,
            args.input_usd_per_million,
            args.output_usd_per_million,
        ]
        if any(value is not None and (not value.is_finite() or value < 0) for value in numbers):
            raise ValueError("Tolerances and token prices must be finite and nonnegative")
        if not math.isfinite(args.adapter_timeout_s) or args.adapter_timeout_s <= 0:
            raise ValueError("Adapter timeout must be positive and finite")
        all_cases = load_cases(args.dataset)
        cases = [
            case
            for case in all_cases
            if case.split == args.split
            and (not args.category or case.case_category in args.category)
        ]
        if not cases:
            raise ValueError("No cases match the selected split/categories")
        example_ids = (
            load_example_manifest(args.example_bank, all_cases) if args.example_bank else None
        )
        if args.validate_only:
            if (
                args.adapter
                or args.predictions
                or args.judgments
                or args.baseline
                or args.thresholds
            ):
                raise ValueError("--validate-only cannot be combined with evaluation inputs")
            print(
                json.dumps(
                    {
                        "status": "validated_only",
                        "evaluation_executed": False,
                        "dataset_version": cases[0].dataset_version,
                        "total_records": len(all_cases),
                        "selected_records": len(cases),
                        "categories": dict(Counter(case.case_category for case in cases)),
                        "reviewed_results": sum(case.expected_result is not None for case in cases),
                        "example_bank_audited": args.example_bank is not None,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if not args.adapter and not args.predictions:
            raise ValueError("Choose --adapter or --predictions, or use --validate-only")
        if args.model_version == "unreported" or args.prompt_version == "unreported":
            raise ValueError(
                "Record --model-version and --prompt-version (use 'none' when not applicable)"
            )
        configuration = load_config(args.config).model_dump(mode="json")
        comparison = {
            "runner_version": RUNNER_VERSION,
            "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
            "catalog_sha256": digest({key: repr(value) for key, value in sorted(REGISTRY.items())}),
            "ids": [case.id for case in cases],
            "split": args.split,
            "mode": args.mode,
            "ks": args.ks,
            "abs_tol": str(args.abs_tol),
            "rel_tol": str(args.rel_tol),
            "seed": args.seed,
            "adapter_timeout_s": args.adapter_timeout_s,
            "input_price": str(args.input_usd_per_million),
            "output_price": str(args.output_usd_per_million),
        }
        metadata = {
            **comparison,
            "comparison_key": digest(comparison),
            "git": git_state(),
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "dataset_version": cases[0].dataset_version,
            "dataset_path": str(args.dataset.resolve()),
            "config_path": str(args.config.resolve()),
            "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
            "configuration": configuration,
            "model_version": args.model_version,
            "prompt_version": args.prompt_version,
            "seed": args.seed,
            "adapter": args.adapter,
            "prediction_source": "adapter" if args.adapter else str(args.predictions.resolve()),
            "predictions_sha256": hashlib.sha256(args.predictions.read_bytes()).hexdigest()
            if args.predictions
            else None,
            "judgments_sha256": hashlib.sha256(args.judgments.read_bytes()).hexdigest()
            if args.judgments
            else None,
            "example_bank_sha256": hashlib.sha256(args.example_bank.read_bytes()).hexdigest()
            if args.example_bank
            else None,
            "adapter_timeout_s": args.adapter_timeout_s,
        }
        baseline = json.loads(args.baseline.read_text()) if args.baseline else None
        if (
            baseline
            and baseline.get("metadata", {}).get("comparison_key") != metadata["comparison_key"]
        ):
            raise ValueError(
                "Baseline is incompatible; do not compare different datasets or scoring settings"
            )
        thresholds = json.loads(args.thresholds.read_text()) if args.thresholds else {}
        if not isinstance(thresholds, dict):
            raise TypeError("Threshold file must be a JSON object")
        quality_gates({}, thresholds)  # Validate settings before any adapter calls.
        target = args.output_dir or ROOT / "reports/eval" / datetime.now(UTC).strftime(
            "contract-%Y%m%dT%H%M%S%fZ"
        )
        if target.exists():
            raise ValueError("Output directory exists; choose a new directory")
        random.seed(args.seed)
        if args.adapter:
            predictions = asyncio.run(
                collect_predictions(
                    cases, import_adapter(args.adapter), args.seed, args.adapter_timeout_s
                )
            )
        else:
            predictions = load_predictions(args.predictions, all_cases)
        for prediction in predictions.values():
            if prediction.selected_example_ids and (
                example_ids is None or set(prediction.selected_example_ids) - example_ids
            ):
                raise ValueError("Selected few-shot IDs require a matching --example-bank manifest")
        rows = [
            score_case(
                case, predictions.get(case.id), args.mode, args.ks, args.abs_tol, args.rel_tol
            )
            for case in cases
        ]
        by_id = {row["id"]: row for row in rows}
        judgments: dict[str, Judgment] = {}
        if args.judgments:
            for record in read_jsonl(args.judgments):
                judgment = Judgment.model_validate(record)
                if judgment.id not in predictions or judgment.id in judgments:
                    raise ValueError("Unexpected or duplicate judgment ID")
                if (
                    digest(predictions[judgment.id].model_dump(mode="json"))
                    != judgment.prediction_sha256
                ):
                    raise ValueError(f"Judgment is bound to a different prediction: {judgment.id}")
                judgments[judgment.id] = judgment
                if judgment.id in by_id:
                    row = by_id[judgment.id]
                    for key in ("numerical_correctness", "faithfulness", "answer_accuracy"):
                        row["checks"][key] = getattr(judgment, key)
                    if not judgment.faithfulness:
                        row["failure_categories"].append("answer_hallucination")
                    if not judgment.numerical_correctness or not judgment.answer_accuracy:
                        row["failure_categories"].append("answer_incorrect")
                    row["failure_categories"] = sorted(set(row["failure_categories"]))
        rates = (args.input_usd_per_million, args.output_usd_per_million)
        metrics = summarize(cases, predictions, rows, args.mode, args.ks, rates, judgments)
        report = {
            "metadata": metadata,
            "metrics": metrics,
            "by_category": {
                category: summarize(
                    [c for c in cases if c.case_category == category],
                    predictions,
                    [r for r in rows if r["case_category"] == category],
                    args.mode,
                    args.ks,
                    rates,
                    judgments,
                )
                for category in sorted({case.case_category for case in cases})
            },
            "quality_gates": quality_gates(metrics, thresholds),
            "limitations": [
                "Draft semantic labels require domain review; they are development specifications.",
                "Null metrics are unmeasured, not passing scores.",
                "Numerical SQL accuracy requires independently reviewed expected_result and a matching database snapshot.",
                "Answer accuracy/faithfulness require independent judgments; status accuracy is not answer accuracy.",
                "Safety scores measure reported adapter execution evidence, not DB/RLS certification.",
                "Replay latency/tokens are recorded measurements, not timings of this scoring run.",
            ],
        }
        report["baseline_comparison"] = compare_baseline(report, baseline) if baseline else None
        target.mkdir(parents=True, exist_ok=False)
        (target / "summary.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        for name, records in (
            (
                "predictions.jsonl",
                [predictions[c.id].model_dump(mode="json") for c in cases if c.id in predictions],
            ),
            ("cases.jsonl", rows),
            ("failures.jsonl", [row for row in rows if row["failure_categories"]]),
        ):
            (target / name).write_text(
                "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
                encoding="utf-8",
            )
        print(
            json.dumps(
                {
                    "report": str(target.resolve() / "summary.json"),
                    "count": len(cases),
                    "metrics": metrics,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return (
            1
            if any(not gate["passed"] for gate in report["quality_gates"])
            or metrics["failures"].get("runtime_failure")
            else 0
        )
    except ConfigurationError:
        print(
            "Evaluation configuration error: selection config failed schema validation",
            file=sys.stderr,
        )
        return 2
    except (ValueError, TypeError, OSError, ImportError, AttributeError) as exc:
        print(f"Evaluation configuration/data error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
