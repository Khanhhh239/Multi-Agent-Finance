"""Quantitative retrieval and end-to-end evaluation helpers."""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from .catalog import MetricCatalogAdapter
from .errors import MetricSelectionError
from .pipeline import MetricSelectionPipeline
from .schemas import (
    EvaluationCase,
    EvaluationSummary,
    MetricCandidate,
    MetricSelectionRequest,
)


def load_evaluation_cases(
    path: str | Path,
    catalog: MetricCatalogAdapter | None = None,
) -> list[EvaluationCase]:
    source = Path(path)
    cases = [
        EvaluationCase.model_validate_json(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Evaluation data contains duplicate IDs")
    if catalog:
        for case in cases:
            unknown = [item for item in case.gold_metric_ids if not catalog.contains(item)]
            if unknown:
                raise ValueError(f"Evaluation case {case.id} has unknown metrics: {unknown}")
    return cases


def evaluate_retrieval(
    cases: list[EvaluationCase],
    retrieve: Callable[[str], list[MetricCandidate]],
    ks: tuple[int, ...] = (5, 10),
) -> EvaluationSummary:
    resolved_cases = [case for case in cases if case.gold_metric_ids]
    if not resolved_cases:
        return EvaluationSummary(count=0)
    rows: list[tuple[EvaluationCase, list[str], float]] = []
    for case in resolved_cases:
        started = time.perf_counter()
        candidates = retrieve(case.question)
        ranked = [candidate.metric_id for candidate in candidates]
        rows.append((case, ranked, (time.perf_counter() - started) * 1000))

    def summarize(
        selected_rows: list[tuple[EvaluationCase, list[str], float]],
        include_categories: bool,
    ) -> EvaluationSummary:
        recall_sums = {k: 0.0 for k in ks}
        precision_sums = {k: 0.0 for k in ks}
        coverage_sums = {k: 0.0 for k in ks}
        reciprocal_ranks: list[float] = []
        counts: list[int] = []
        latencies: list[float] = []
        for case, ranked, latency in selected_rows:
            counts.append(len(ranked))
            latencies.append(latency)
            gold = set(case.gold_metric_ids)
            for k in ks:
                predicted = set(ranked[:k])
                hits = len(gold & predicted)
                recall_sums[k] += hits / len(gold)
                precision_sums[k] += hits / k
                coverage_sums[k] += float(gold.issubset(predicted))
            ranks = [ranked.index(item) + 1 for item in gold if item in ranked]
            reciprocal_ranks.append(1.0 / min(ranks) if ranks else 0.0)
        count = len(selected_rows)
        summary = EvaluationSummary(
            count=count,
            recall_at_k={k: recall_sums[k] / count for k in ks},
            precision_at_k={k: precision_sums[k] / count for k in ks},
            all_gold_covered_at_k={k: coverage_sums[k] / count for k in ks},
            mean_reciprocal_rank=sum(reciprocal_ranks) / count,
            average_candidate_count=sum(counts) / count,
            average_latency_ms=sum(latencies) / count,
        )
        if include_categories:
            categories = sorted({case.category for case, _, _ in selected_rows})
            summary.per_category = {
                category: summarize(
                    [row for row in selected_rows if row[0].category == category],
                    False,
                )
                for category in categories
            }
        return summary

    return summarize(rows, True)


async def evaluate_pipeline(
    cases: list[EvaluationCase],
    pipeline: MetricSelectionPipeline,
) -> EvaluationSummary:
    if not cases:
        return EvaluationSummary(count=0)
    rows = []
    for case in cases:
        started = time.perf_counter()
        result = None
        try:
            result = await pipeline.select(MetricSelectionRequest(question=case.question))
        except MetricSelectionError:
            pass
        finally:
            rows.append((case, result, (time.perf_counter() - started) * 1000))

    def summarize(selected_rows, include_categories: bool) -> EvaluationSummary:
        exact = true_positive = predicted_total = gold_total = valid = status_correct = 0
        latencies = []
        for case, result, latency in selected_rows:
            latencies.append(latency)
            gold = set(case.gold_metric_ids)
            gold_total += len(gold)
            if result is None:
                continue
            valid += 1
            predicted = set(result.metric_ids)
            exact += int(predicted == gold and result.status == case.gold_status)
            true_positive += len(predicted & gold)
            predicted_total += len(predicted)
            status_correct += int(result.status == case.gold_status)
        precision = true_positive / predicted_total if predicted_total else 0.0
        recall = true_positive / gold_total if gold_total else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        count = len(selected_rows)
        summary = EvaluationSummary(
            count=count,
            exact_set_match=exact / count,
            metric_precision=precision,
            metric_recall=recall,
            metric_f1=f1,
            valid_output_rate=valid / count,
            status_accuracy=status_correct / count,
            average_latency_ms=sum(latencies) / count,
        )
        if include_categories:
            categories = sorted({case.category for case, _, _ in selected_rows})
            summary.per_category = {
                category: summarize(
                    [row for row in selected_rows if row[0].category == category],
                    False,
                )
                for category in categories
            }
        return summary

    return summarize(rows, True)


def save_summary(summary: EvaluationSummary, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
