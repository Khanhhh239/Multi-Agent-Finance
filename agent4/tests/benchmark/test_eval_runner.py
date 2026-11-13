"""Runner unit/structure checks; no benchmark execution, model calls or database access."""

from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from vals import run_eval
from vals.run_eval import (
    BenchmarkCase,
    Prediction,
    Selection,
    TableResult,
    compare_baseline,
    load_cases,
    load_example_manifest,
    load_predictions,
    quality_gates,
    read_jsonl,
    score_case,
    summarize,
    table_equal,
)


def make_case(case_id: str = "BM-001", *, multi: bool = False) -> BenchmarkCase:
    ids = ["net_revenue", "cogs"] if multi else ["net_revenue"]
    return BenchmarkCase.model_validate(
        {
            "schema_version": "benchmark-case.v2",
            "dataset_version": "unit-fixture-v1",
            "id": case_id,
            "split": "dev",
            "case_category": "multi_metrics" if multi else "single_metric_aggregate",
            "locale": "vi-VN",
            "user_query": f"Câu hỏi fixture {case_id}",
            "auth_context": {
                "user_id": "unit-user",
                "tenant_id": "unit-tenant",
                "roles": ["finance_analyst"],
                "allowed_views": ["mgmt"],
                "allowed_metrics": None,
            },
            "query_context": {"reference_date": "2026-10-14", "timezone": "Asia/Ho_Chi_Minh"},
            "expected_selection_status": "resolved",
            "expected_metric_ids": ids,
            "expected_dimensions": [],
            "expected_filters": [],
            "expected_plan": {
                "plan_version": "1.0",
                "status": "ready",
                "metric_ids": ids,
                "time": {
                    "mode": "range",
                    "start": "2026-08-01",
                    "end": "2026-08-31",
                    "as_of": None,
                    "grain": "month",
                },
                "dimensions": [],
                "filters": [],
                "view": "mgmt",
                "operation": "aggregate",
                "sort": None,
                "top_k": None,
                "comparison": None,
                "question_for_user": None,
                "unresolved_slots": [],
                "reason_code": None,
            },
            "expected_result": None,
            "expected_final_status": "ready",
            "expected_warning_codes": [],
            "security_tags": [],
            "fixture_requirements": [],
            "review_status": "draft",
            "notes": "Unit fixture only, not a benchmark prediction.",
        }
    )


def table(values: list[str | None]) -> TableResult:
    return TableResult(
        columns=[{"key": "net_revenue", "type": "decimal", "unit": "VND"}],
        rows=[{"net_revenue": value} for value in values],
        row_count=len(values),
        truncated=False,
    )


def scores(case: BenchmarkCase, prediction: Prediction | None, mode: str = "selection"):
    return score_case(case, prediction, mode, [1, 5], Decimal(0), Decimal(0))


def test_expected_policy_rejection_is_safety_evidence_not_runtime_error():
    case = make_case().model_copy(
        update={"expected_final_status": "forbidden", "security_tags": ["policy"]}
    )
    prediction = Prediction.model_validate(
        {
            "id": case.id,
            "final_status": "forbidden",
            "execution": {"attempted": False, "succeeded": False},
            "error": {"stage": "metrics_validation", "code": "forbidden_metric"},
        }
    )
    result = scores(case, prediction, "e2e")
    assert result["checks"]["safety_pass"] is True
    assert "runtime_failure" not in result["failure_categories"]
    attempted = prediction.execution.model_copy(update={"attempted": True})
    result = scores(case, prediction.model_copy(update={"execution": attempted}), "e2e")
    assert result["checks"]["safety_pass"] is False
    assert "runtime_failure" in result["failure_categories"]


def test_dataset_structure_only_has_separate_multi_metric_coverage() -> None:
    cases = load_cases(run_eval.DEFAULT_DATASET)
    assert len(cases) == 140
    assert Counter(case.case_category for case in cases) == {
        "single_metric_aggregate": 20,
        "timeseries_and_comparison": 20,
        "dimensional_breakdown_filter_topk": 20,
        "business_views": 15,
        "ambiguous_needs_clarification": 15,
        "unsupported_out_of_catalog": 12,
        "no_data_and_edge_cases": 8,
        "authorization_and_security": 10,
        "multi_metrics": 20,
    }
    assert all(case.expected_result is None and case.split == "dev" for case in cases)


def test_adapter_payload_contains_only_inputs() -> None:
    payload = make_case(multi=True).adapter_input(123)
    assert set(payload) == {
        "contract_version",
        "id",
        "user_query",
        "locale",
        "auth_context",
        "query_context",
        "options",
        "seed",
    }
    assert not any(key.startswith("expected_") for key in payload)
    assert "notes" not in payload and "fixture_requirements" not in payload


@pytest.mark.parametrize("contents", ['{"id":"x","id":"y"}', '{"value":NaN}', "[]"])
def test_jsonl_rejects_ambiguous_or_nonfinite_json(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "invalid.jsonl"
    path.write_text(contents + "\n", encoding="utf-8")
    with pytest.raises((ValueError, TypeError)):
        read_jsonl(path)


def test_numerical_gold_and_test_split_require_review() -> None:
    raw = make_case().model_dump(mode="json")
    raw["expected_result"] = table(["42"]).model_dump(mode="json")
    with pytest.raises(ValidationError, match="independent review"):
        BenchmarkCase.model_validate(raw)
    raw["expected_result"] = None
    raw["split"] = "test"
    with pytest.raises(ValidationError, match="reviewed"):
        BenchmarkCase.model_validate(raw)


def test_multi_metric_exact_match_requires_the_whole_set() -> None:
    case = make_case(multi=True)
    incomplete = Prediction(
        id=case.id, selection=Selection(status="resolved", metric_ids=["net_revenue"])
    )
    assert scores(case, incomplete)["checks"]["selection_exact_match"] is False
    complete = Prediction(
        id=case.id, selection=Selection(status="resolved", metric_ids=["cogs", "net_revenue"])
    )
    assert scores(case, complete)["checks"]["selection_exact_match"] is True


def test_catalog_valid_metric_outside_candidates_is_a_failure() -> None:
    case = make_case()
    prediction = Prediction(
        id=case.id,
        retrieved_metric_ids=["cogs"],
        selection=Selection(status="resolved", metric_ids=["net_revenue"]),
    )
    assert scores(case, prediction)["checks"]["selection_within_candidates"] is False


def test_missing_predictions_stay_in_denominators_and_unmeasured_scores_stay_null() -> None:
    cases = [make_case(), make_case("BM-002")]
    first = Prediction(
        id=cases[0].id, selection=Selection(status="resolved", metric_ids=["net_revenue"])
    )
    predictions = {first.id: first}
    rows = [scores(case, predictions.get(case.id)) for case in cases]
    summary = summarize(cases, predictions, rows, "selection", [1, 5], (None, None), {})
    assert summary["selection"]["exact_match_accuracy"]["value"] == 0.5
    assert summary["selection"]["recall"] == 0.5
    assert summary["sql"]["execution_accuracy"] is None
    assert summary["answer"]["faithfulness"]["value"] is None
    assert summary["e2e"]["cost_per_query_usd"] is None


def test_retrieval_reports_multi_metric_all_covered_separately_from_mrr() -> None:
    case = make_case(multi=True)
    prediction = Prediction(id=case.id, retrieved_metric_ids=["net_revenue"])
    result = scores(case, prediction, "retrieval")["retrieval"]
    assert result["recall_at_k"]["5"] == 0.5
    assert result["precision_at_k"]["5"] == 0.2
    assert result["reciprocal_rank"] == 1.0
    assert result["all_metrics_covered_at_k"]["5"] is False


def test_result_comparison_preserves_nulls_units_order_and_duplicate_counts() -> None:
    assert table_equal(
        table(["1.00", "2"]),
        table(["2.0", "1"]),
        ordered=False,
        abs_tol=Decimal(0),
        rel_tol=Decimal(0),
    )
    assert not table_equal(
        table(["1", "2"]), table(["2", "1"]), ordered=True, abs_tol=Decimal(0), rel_tol=Decimal(0)
    )
    assert not table_equal(
        table([None]), table(["0"]), ordered=False, abs_tol=Decimal(0), rel_tol=Decimal(0)
    )
    assert not table_equal(
        table(["1", "1"]), table(["1", "2"]), ordered=False, abs_tol=Decimal(0), rel_tol=Decimal(0)
    )


def test_tolerant_unordered_results_use_complete_matching() -> None:
    assert table_equal(
        table(["0", "2"]), table(["1", "-1"]), ordered=False, abs_tol=Decimal(1), rel_tol=Decimal(0)
    )


def test_snapshot_mismatch_cannot_pass_numerical_comparison() -> None:
    raw = make_case().model_dump(mode="json")
    raw.update(
        {
            "review_status": "approved",
            "expected_result": table(["42"]).model_dump(mode="json"),
            "result_reference": {
                "snapshot_id": "reviewed-db",
                "method": "independent_sql",
                "reviewer": "owner",
                "version": "v1",
            },
        }
    )
    case = BenchmarkCase.model_validate(raw)
    prediction = Prediction(
        id=case.id, final_status="ready", result=table(["42"]), data_snapshot_id="other-db"
    )
    assert scores(case, prediction, "e2e")["checks"]["result_match"] is False


def test_incomplete_review_or_missing_measurement_cannot_pass_a_quality_gate() -> None:
    metrics = {"answer": {"faithfulness": {"value": 1.0, "scored": 1, "eligible": 140}}}
    gate = quality_gates(metrics, {"answer.faithfulness.value": {"min": 0.9}})[0]
    assert gate["passed"] is False
    assert gate["coverage_complete"] is False
    assert quality_gates({}, {"sql.execution_accuracy.value": {"min": 0.9}})[0]["passed"] is False


def test_baseline_rejects_changed_dataset_and_reports_lost_measurements() -> None:
    baseline = {"metadata": {"comparison_key": "same"}, "metrics": {"score": 0.9}}
    current = {"metadata": {"comparison_key": "same"}, "metrics": {"score": None}}
    assert compare_baseline(current, baseline)["lost_measurements"] == ["score"]
    current["metadata"]["comparison_key"] = "different"
    with pytest.raises(ValueError, match="not comparable"):
        compare_baseline(current, baseline)


def test_prediction_loading_matches_by_id_and_rejects_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "predictions.jsonl"
    path.write_text('{"id":"BM-002"}\n', encoding="utf-8")
    cases = [make_case(), make_case("BM-002")]
    assert list(load_predictions(path, cases)) == ["BM-002"]
    path.write_text('{"id":"BM-002"}\n{"id":"BM-002"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        load_predictions(path, cases)


def test_example_manifest_rejects_exact_benchmark_leakage(tmp_path: Path) -> None:
    path = tmp_path / "examples.jsonl"
    path.write_text(
        json.dumps({"id": "ex-1", "question": make_case().user_query.upper() + "?"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="appears in the few-shot bank"):
        load_example_manifest(path, [make_case()])


def test_validate_only_never_imports_an_adapter_or_writes_reports(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    def forbidden_import(_):
        pytest.fail("Validation must not import an adapter")

    monkeypatch.setattr(run_eval, "import_adapter", forbidden_import)
    target = tmp_path / "report"
    assert run_eval.main(["--validate-only", "--output-dir", str(target)]) == 0
    assert json.loads(capsys.readouterr().out)["evaluation_executed"] is False
    assert not target.exists()
