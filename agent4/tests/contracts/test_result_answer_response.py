"""Tests for Contracts 21, 22, 23, 24, 25 of contracts.md:
- result.validation.v1
- answer.generation.v1
- answer.validation.v1
- query.response.v1
- observability.pipeline.v1
"""

from __future__ import annotations

import pytest

from tests.contract_harness import (
    FINAL_STATUSES,
    ContractError,
    MetricCatalog,
    build_final_response,
    build_observability_record,
    compile_sql,
    execute_safe_sql,
    generate_grounded_answer,
    validate_answer,
    validate_result,
    validate_semantic_plan_draft,
    validate_sql_safety,
)


def _make_validated_plan(
    catalog: MetricCatalog,
    auth: dict,
    metric_ids: list[str],
    start: str,
    end: str,
) -> dict:
    return validate_semantic_plan_draft(
        {
            "plan_version": "1.0",
            "status": "ready",
            "metric_ids": metric_ids,
            "time": {"mode": "range", "start": start, "end": end, "as_of": None, "grain": "month"},
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
        {"status": "validated", "metric_ids": metric_ids},
        catalog,
        auth,
    )


class TestResultValidationContract:
    """Contract 21: result.validation.v1."""

    def test_result_validation_rejects_nan_infinity_and_duplicate_columns(
        self, catalog: MetricCatalog, analyst_auth: dict
    ) -> None:
        v_plan = _make_validated_plan(catalog, analyst_auth, ["net_profit_margin"], "2026-08-01", "2026-08-31")

        # 1. NaN value in decimal column
        nan_result = {
            "columns": [{"key": "net_profit_margin", "type": "decimal", "unit": "%"}],
            "rows": [{"net_profit_margin": "NaN"}],
            "row_count": 1,
            "truncated": False,
            "data_watermark": "2026-10-14",
            "execution_ms": 10,
        }
        with pytest.raises(ContractError) as e_nan:
            validate_result(nan_result, v_plan, catalog)
        assert e_nan.value.code == "invalid_result"
        assert e_nan.value.details["checks"]["types_valid"] is False

        # 2. Duplicate columns
        dup_result = {
            "columns": [
                {"key": "net_profit_margin", "type": "decimal", "unit": "%"},
                {"key": "net_profit_margin", "type": "decimal", "unit": "%"},
            ],
            "rows": [{"net_profit_margin": "12.45"}],
            "row_count": 1,
            "truncated": False,
            "data_watermark": "2026-10-14",
            "execution_ms": 10,
        }
        with pytest.raises(ContractError) as e_dup:
            validate_result(dup_result, v_plan, catalog)
        assert e_dup.value.details["checks"]["schema_valid"] is False

        # 3. Wrong unit for metric
        bad_unit_result = {
            "columns": [{"key": "net_profit_margin", "type": "decimal", "unit": "VND"}],
            "rows": [{"net_profit_margin": "12.45"}],
            "row_count": 1,
            "truncated": False,
            "data_watermark": "2026-10-14",
            "execution_ms": 10,
        }
        with pytest.raises(ContractError) as e_unit:
            validate_result(bad_unit_result, v_plan, catalog)
        assert e_unit.value.details["checks"]["semantic_constraints_valid"] is False

    def test_ratio_zero_denominator_is_valid_with_warning(
        self, catalog: MetricCatalog, analyst_auth: dict, runtime_context: dict
    ) -> None:
        # Sunday 2026-08-16 has 0 revenue -> gross_margin denominator is 0 -> returns NULL
        v_plan = _make_validated_plan(catalog, analyst_auth, ["gross_margin"], "2026-08-16", "2026-08-16")
        bound = compile_sql(v_plan, catalog)
        safe = validate_sql_safety(bound, catalog, runtime_context)
        exec_res = execute_safe_sql(safe)

        val_res = validate_result(exec_res, v_plan, catalog)
        assert val_res["status"] == "valid"
        assert val_res["result"]["rows"][0]["gross_margin"] is None
        assert "ratio_undefined" in val_res["warnings"]

    def test_partial_data_watermark_and_no_data_detection(
        self, catalog: MetricCatalog, analyst_auth: dict, runtime_context: dict
    ) -> None:
        # 1. October 2026 query overlaps unclosed month and watermark 2026-10-14 -> status == 'partial'
        v_plan_oct = _make_validated_plan(catalog, analyst_auth, ["net_revenue"], "2026-10-01", "2026-10-31")
        bound_oct = compile_sql(v_plan_oct, catalog)
        safe_oct = validate_sql_safety(bound_oct, catalog, runtime_context)
        exec_oct = execute_safe_sql(safe_oct)
        val_oct = validate_result(exec_oct, v_plan_oct, catalog)
        assert val_oct["status"] == "partial"
        assert "partial_data_watermark" in val_oct["warnings"]

        # 2. Year 2022 query before data_start (2024-12-31) -> status == 'no_data'
        v_plan_old = _make_validated_plan(catalog, analyst_auth, ["net_revenue"], "2022-01-01", "2022-03-31")
        bound_old = compile_sql(v_plan_old, catalog)
        safe_old = validate_sql_safety(bound_old, catalog, runtime_context)
        exec_old = execute_safe_sql(safe_old)
        val_old = validate_result(exec_old, v_plan_old, catalog)
        assert val_old["status"] == "no_data"
        assert "no_data_for_period" in val_old["warnings"]


class TestAnswerGenerationAndValidationContracts:
    """Contracts 22 & 23: answer.generation.v1 & answer.validation.v1."""

    def test_grounded_answer_passes_validation(
        self, catalog: MetricCatalog, analyst_auth: dict
    ) -> None:
        v_plan = _make_validated_plan(catalog, analyst_auth, ["net_profit_margin"], "2026-08-01", "2026-08-31")
        val_res = {
            "status": "valid",
            "result": {
                "columns": [{"key": "net_profit_margin", "type": "decimal", "unit": "%"}],
                "rows": [{"net_profit_margin": "12.45"}],
                "row_count": 1,
                "truncated": False,
                "data_watermark": "2026-10-14",
                "execution_ms": 15,
            },
            "warnings": [],
        }
        draft = generate_grounded_answer(v_plan, val_res, catalog, locale="vi-VN")
        checked = validate_answer(draft, val_res, v_plan, catalog, locale="vi-VN", fallback_on_failure=False)
        assert checked["status"] == "valid"
        assert "12.45 %" in checked["answer"]
        assert checked["validated_claims"][0]["verified"] is True

    def test_answer_validator_rejects_hallucinations_and_falls_back(
        self, catalog: MetricCatalog, analyst_auth: dict
    ) -> None:
        v_plan = _make_validated_plan(catalog, analyst_auth, ["operating_expense"], "2026-09-01", "2026-09-30")
        val_res = {
            "status": "partial",
            "result": {
                "columns": [{"key": "operating_expense", "type": "decimal", "unit": "VND"}],
                "rows": [{"operating_expense": "1391237000.00"}],
                "row_count": 1,
                "truncated": False,
                "data_watermark": "2026-10-14",
                "execution_ms": 15,
            },
            "warnings": ["partial_data_watermark"],
        }

        # Case 1: Number in claim differs from result
        bad_num_draft = {
            "summary": "Chi phí hoạt động: 9999999999.00 VND.",
            "claims": [{"text": "Chi phí hoạt động: 9999999999.00 VND", "source_columns": ["operating_expense"], "source_rows": [0]}],
            "warnings": ["partial_data_watermark"],
            "table_caption": None,
        }
        with pytest.raises(ContractError):
            validate_answer(bad_num_draft, val_res, v_plan, catalog, fallback_on_failure=False)

        # With fallback_on_failure=True, it replaces the bad LLM draft with deterministic template
        fb_res = validate_answer(bad_num_draft, val_res, v_plan, catalog, fallback_on_failure=True)
        assert fb_res["status"] == "valid"
        assert fb_res["used_fallback"] is True
        assert "1391237000.00 VND" in fb_res["answer"]

        # Case 2: Causal speculation not in data ("sự kiện ra mắt")
        speculative_draft = {
            "summary": "Chi phí hoạt động: 1391237000.00 VND tăng đột biến do sự kiện ra mắt.",
            "claims": [{"text": "Chi phí hoạt động: 1391237000.00 VND", "source_columns": ["operating_expense"], "source_rows": [0]}],
            "warnings": ["partial_data_watermark"],
            "table_caption": None,
        }
        with pytest.raises(ContractError):
            validate_answer(speculative_draft, val_res, v_plan, catalog, fallback_on_failure=False)

        # Case 3: Omitting required partial warning
        missing_warn_draft = {
            "summary": "Chi phí hoạt động: 1391237000.00 VND.",
            "claims": [{"text": "Chi phí hoạt động: 1391237000.00 VND", "source_columns": ["operating_expense"], "source_rows": [0]}],
            "warnings": [],
            "table_caption": None,
        }
        with pytest.raises(ContractError):
            validate_answer(missing_warn_draft, val_res, v_plan, catalog, fallback_on_failure=False)


class TestFinalResponseAndObservabilityContracts:
    """Contracts 24 & 25: query.response.v1 & observability.pipeline.v1."""

    def test_final_response_supports_all_7_statuses_and_provenance(
        self, catalog: MetricCatalog, analyst_auth: dict, runtime_context: dict
    ) -> None:
        assert FINAL_STATUSES == {
            "ready",
            "needs_clarification",
            "unsupported",
            "forbidden",
            "no_data",
            "temporarily_unavailable",
            "error",
        }
        v_plan = _make_validated_plan(catalog, analyst_auth, ["net_revenue"], "2026-08-01", "2026-08-31")
        bound = compile_sql(v_plan, catalog)
        safe = validate_sql_safety(bound, catalog, runtime_context)
        exec_res = execute_safe_sql(safe)

        resp = build_final_response(
            request_id="req-001",
            status="ready",
            answer="Doanh thu thuần: 19339316000.00 VND.",
            execution_result=exec_res,
            validated_plan=v_plan,
            bound_query=bound,
            warnings=[],
            include_table=True,
        )
        assert resp["api_version"] == "v1"
        assert resp["status"] == "ready"
        assert resp["provenance"] == {
            "catalog_hash": catalog.get_catalog_hash(),
            "data_watermark": "2026-10-14",
            "source": "v_mgmt",
            "query_fingerprint": bound["fingerprint"],
        }

    def test_observability_record_redacts_sensitive_fields(self, catalog: MetricCatalog) -> None:
        obs = build_observability_record(
            request_id="req-001",
            trace_id="trace-001",
            stage_latencies_ms={"retrieval": 12, "execution": 45},
            catalog_hash=catalog.get_catalog_hash(),
            embedding_model="multilingual-embedding-v1",
            candidate_count=5,
            selected_metric_ids=["net_revenue"],
            fewshot_example_ids=["fs-rev-001"],
            token_usage=410,
            query_fingerprint="sha256:1234567890abcdef",
            row_count=1,
            truncated=False,
            data_watermark="2026-10-14",
            final_status="ready",
            error_code=None,
        )
        assert obs["contract_version"] == "observability.pipeline.v1"
        assert "sql" not in obs
        assert "rows" not in obs
        assert "chain_of_thought" not in obs
        assert "credentials" not in obs
