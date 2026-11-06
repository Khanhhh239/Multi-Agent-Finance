"""Tests for Contracts 18, 19, 20 of contracts.md against data/cfo_warehouse.duckdb:
- sql.compiler.v1
- sql.safety.v1
- sql.execution.v1
"""

from __future__ import annotations

import copy
import duckdb
import pytest

from tests.contract_harness import (
    ContractError,
    MetricCatalog,
    compile_sql,
    execute_safe_sql,
    validate_semantic_plan_draft,
    validate_sql_safety,
)


def _build_validated_plan(
    catalog: MetricCatalog,
    auth_context: dict,
    metric_ids: list[str] = ["net_revenue"],
    start: str = "2026-08-01",
    end: str = "2026-08-31",
    view: str = "mgmt",
    dimensions: list[str] | None = None,
    filters: list[dict] | None = None,
    operation: str = "aggregate",
    top_k: int | None = None,
) -> dict:
    draft = {
        "plan_version": "1.0",
        "status": "ready",
        "metric_ids": metric_ids,
        "time": {"mode": "range", "start": start, "end": end, "as_of": None, "grain": "month"},
        "dimensions": dimensions or [],
        "filters": filters or [],
        "view": view,
        "operation": operation,
        "sort": "desc" if top_k else None,
        "top_k": top_k,
        "comparison": None,
        "question_for_user": None,
        "unresolved_slots": [],
        "reason_code": None,
    }
    return validate_semantic_plan_draft(
        draft,
        {"status": "validated", "metric_ids": metric_ids},
        catalog,
        auth_context,
    )


class TestSQLCompilerContract:
    """Contract 18: sql.compiler.v1."""

    def test_compiler_accepts_only_validated_plan(self, catalog: MetricCatalog) -> None:
        raw_plan_draft = {"plan_version": "1.0", "status": "ready", "metric_ids": ["net_revenue"]}
        with pytest.raises(ContractError) as exc_info:
            compile_sql(raw_plan_draft, catalog)
        assert exc_info.value.code == "invalid_request"

    def test_compiler_parameterized_and_row_cap(self, catalog: MetricCatalog, analyst_auth: dict) -> None:
        v_plan = _build_validated_plan(
            catalog,
            analyst_auth,
            metric_ids=["net_revenue", "cogs"],
            dimensions=["branch_code"],
            filters=[{"field": "branch_code", "op": "=", "value": "HN"}],
            operation="breakdown",
        )
        bound = compile_sql(v_plan, catalog)
        assert bound["contract_version"] == "bound-query.v1"
        assert bound["source"] == "v_mgmt"
        assert bound["row_cap"] == 1000
        assert bound["fingerprint"].startswith("sha256:")
        assert bound["catalog_hash"] == catalog.get_catalog_hash()
        assert "'HN'" not in bound["sql"]
        assert "HN" in bound["params"]
        assert bound["sql"].endswith("LIMIT ?")


class TestSQLSafetyValidationContract:
    """Contract 19: sql.safety.v1."""

    def test_safety_gate_allows_valid_bound_query(
        self, catalog: MetricCatalog, analyst_auth: dict, runtime_context: dict
    ) -> None:
        v_plan = _build_validated_plan(catalog, analyst_auth)
        bound = compile_sql(v_plan, catalog)
        safe = validate_sql_safety(bound, catalog, runtime_context)
        assert safe["status"] == "allowed"
        assert safe["query_fingerprint"] == bound["fingerprint"]
        assert all(safe["checks"].values()) is True

    @pytest.mark.parametrize(
        "mutation_fn,failed_check",
        [
            # 1. DML/DDL statement
            (lambda b: b.update({"sql": "DELETE FROM v_mgmt WHERE posting_date >= ? LIMIT ?"}), "read_only"),
            # 2. Multi-statement SQL
            (
                lambda b: b.update(
                    {
                        "sql": b["sql"].replace(
                            "LIMIT ?", "LIMIT ?; SELECT * FROM payroll"
                        )
                    }
                ),
                "single_statement",
            ),
            # 3. Relation outside allowlist
            (
                lambda b: b.update({"sql": b["sql"].replace("FROM v_mgmt", "FROM duckdb_tables")}),
                "approved_relations",
            ),
            # 4. Unparameterized user literal embedded in SQL
            (
                lambda b: b.update({"sql": b["sql"].replace("WHERE ", "WHERE branch_code = 'HN' AND ")}),
                "parameterized",
            ),
            # 5. Missing row cap
            (
                lambda b: b.update({"sql": b["sql"].replace(" LIMIT ?", ""), "row_cap": 0}),
                "row_cap_present",
            ),
            # 6. Missing tenant scope or catalog hash mismatch
            (
                lambda b: b.update({"tenant_id": "wrong-tenant"}),
                "tenant_scope_present",
            ),
            (
                lambda b: b.update({"catalog_hash": "catalog-tampered"}),
                "tenant_scope_present",
            ),
        ],
    )
    def test_safety_gate_rejects_unsafe_queries(
        self,
        catalog: MetricCatalog,
        analyst_auth: dict,
        runtime_context: dict,
        mutation_fn,
        failed_check: str,
    ) -> None:
        v_plan = _build_validated_plan(catalog, analyst_auth)
        bound = compile_sql(v_plan, catalog)
        tampered = copy.deepcopy(bound)
        mutation_fn(tampered)

        with pytest.raises(ContractError) as exc_info:
            validate_sql_safety(tampered, catalog, runtime_context)
        assert exc_info.value.code == "unsafe_sql_rejected"
        assert exc_info.value.details["checks"][failed_check] is False


class TestSQLExecutionOnDuckDBContract:
    """Contract 20: sql.execution.v1 against real data/cfo_warehouse.duckdb."""

    def test_executor_rejects_unvalidated_query(self) -> None:
        with pytest.raises(ContractError) as exc_info:
            execute_safe_sql({"status": "rejected"})
        assert exc_info.value.code == "unsafe_sql_rejected"

    def test_duckdb_read_only_connection_blocks_writes(self, db_conn: duckdb.DuckDBPyConnection) -> None:
        with pytest.raises(Exception):
            db_conn.execute("CREATE TABLE hacked_table (id INT)")

    def test_execute_mgmt_vs_tax_view_on_real_duckdb(
        self, catalog: MetricCatalog, cfo_auth: dict, runtime_context: dict
    ) -> None:
        # Execute operating_expense for 2026-08 on v_mgmt vs v_tax
        plan_mgmt = _build_validated_plan(
            catalog, cfo_auth, metric_ids=["operating_expense"], start="2026-08-01", end="2026-08-31", view="mgmt"
        )
        bound_mgmt = compile_sql(plan_mgmt, catalog)
        safe_mgmt = validate_sql_safety(bound_mgmt, catalog, runtime_context)
        res_mgmt = execute_safe_sql(safe_mgmt)

        plan_tax = _build_validated_plan(
            catalog, cfo_auth, metric_ids=["operating_expense"], start="2026-08-01", end="2026-08-31", view="tax"
        )
        bound_tax = compile_sql(plan_tax, catalog)
        safe_tax = validate_sql_safety(bound_tax, catalog, runtime_context)
        res_tax = execute_safe_sql(safe_tax)

        assert res_mgmt["data_watermark"] == "2026-10-14"
        assert res_mgmt["row_count"] == 1
        assert res_mgmt["truncated"] is False
        assert res_mgmt["rows"][0]["operating_expense"] == "3028615501.00"
        assert res_tax["rows"][0]["operating_expense"] == "2928697501.00"

    def test_database_outage_returns_temporarily_unavailable(
        self, catalog: MetricCatalog, analyst_auth: dict, runtime_context: dict
    ) -> None:
        v_plan = _build_validated_plan(catalog, analyst_auth)
        bound = compile_sql(v_plan, catalog)
        safe = validate_sql_safety(bound, catalog, runtime_context)

        with pytest.raises(ContractError) as exc_info:
            execute_safe_sql(safe, simulate_outage=True)
        assert exc_info.value.code == "database_unavailable"
        assert exc_info.value.final_status == "temporarily_unavailable"
        assert exc_info.value.retryable is True
