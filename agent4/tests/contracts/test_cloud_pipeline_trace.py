"""Regression tests for Phase 1 cloud-query observability."""

from agent4.core.errors import ContractError
from agent4.metric_selection.recovery import SelectionTrace
from agent4.pipeline import PipelineTrace


def test_pipeline_trace_records_stage_success_and_contract_error() -> None:
    trace = PipelineTrace()

    with trace.measure("request_validation"):
        pass

    try:
        with trace.measure("sql_execution"):
            raise ContractError(
                "execution_timeout",
                "sql_execution",
                "Database query timed out.",
                retryable=True,
            )
    except ContractError:
        pass

    assert trace.stage_status == {
        "request_validation": "ok",
        "sql_execution": "error",
    }
    assert trace.stage_latency_ms["request_validation"] >= 0
    assert trace.stage_errors["sql_execution"] == {
        "code": "execution_timeout",
        "stage": "sql_execution",
        "retryable": True,
        "type": "ContractError",
    }


def test_selection_trace_keeps_public_contract_and_detailed_breakdown() -> None:
    trace = SelectionTrace()

    with trace.measure("retrieval_ms"):
        pass
    with trace.measure_detail("embedding"):
        pass

    assert trace.stage_latency_ms["retrieval_ms"] >= 0
    assert trace.stage_breakdown_ms["embedding"] >= 0
    assert trace.stage_status["retrieval_ms"] == "ok"
    assert trace.stage_breakdown_status["embedding"] == "ok"
