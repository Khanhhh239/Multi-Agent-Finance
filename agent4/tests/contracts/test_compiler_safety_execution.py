"""Tests for Contracts 18, 19, 20 of contracts.md against data/cfo_warehouse.duckdb:
- sql.compiler.v1
- sql.safety.v1
- sql.execution.v1
"""

from __future__ import annotations

from dataclasses import replace
from shutil import copyfile

import duckdb
import pytest

from agent4.core.catalog import MetricCatalog as GovernedCatalog
from agent4.core.context import build_runtime_context
from agent4.core.errors import ContractError as GovernedError
from agent4.planning.validator import ValidatedPlan
from agent4.planning.validator import validate_semantic_plan_draft as seal_plan
from agent4.sql.compiler import compile_sql as compile_governed_sql
from agent4.sql.executor import _connect_read_only, execute_safe_sql
from agent4.sql.safety import SafeBoundQuery
from agent4.sql.safety import validate_sql_safety as validate_governed_sql
from tests.contract_harness import DB_PATH


def _governed_plan(catalog: GovernedCatalog, auth: dict, *, row_cap=1000, **slots) -> ValidatedPlan:
    draft = {
        "plan_version": "1.0",
        "status": "ready",
        "metric_ids": ["net_revenue"],
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
        **slots,
    }
    plan = seal_plan(
        draft,
        {
            "status": "validated",
            "metric_ids": draft["metric_ids"],
            "catalog_hash": catalog.get_catalog_hash(),
        },
        catalog,
        auth,
        row_cap=row_cap,
    )
    assert isinstance(plan, ValidatedPlan)
    return plan


class TestSQLCompilerContract:
    """Contract 18: sql.compiler.v1."""

    @pytest.mark.parametrize(
        "unsealed",
        [
            "net revenue last month",
            {"plan_version": "1.0", "status": "ready", "metric_ids": ["net_revenue"]},
            {"contract_version": "validated-plan.v1", "status": "validated"},
        ],
    )
    def test_compiler_accepts_only_validated_plan(self, selection_catalog, unsealed) -> None:
        with pytest.raises(GovernedError) as exc_info:
            compile_governed_sql(unsealed, selection_catalog)
        assert exc_info.value.code == "invalid_request"

    def test_compiler_parameterized_and_row_cap(self, selection_catalog, analyst_auth) -> None:
        plan = _governed_plan(
            selection_catalog,
            analyst_auth,
            metric_ids=["net_revenue", "gross_profit"],
            dimensions=["branch_code", "product_line"],
            filters=[
                {"field": "branch_code", "op": "IN", "value": ["HN", "DN"]},
                {"field": "product_line", "op": "=", "value": "IT"},
            ],
            operation="ranking",
            sort={"metric_id": "gross_profit", "direction": "asc"},
            top_k=10,
            row_cap=8,
        )
        bound = compile_governed_sql(plan, selection_catalog)
        assert bound.contract_version == "bound-query.v1"
        assert bound.source == "v_mgmt"
        assert bound.row_cap == 8
        assert bound.fingerprint.startswith("sha256:")
        assert bound.catalog_hash == selection_catalog.get_catalog_hash()
        assert bound.units == {"net_revenue": "VND", "gross_profit": "VND"}
        assert bound.tenant_id == analyst_auth["tenant_id"]
        assert bound.policy_hash == analyst_auth["policy_hash"]
        assert bound.params == ("2026-08-01", "2026-08-31", "HN", "DN", "IT", 8)
        assert all(f"'{value}'" not in bound.sql for value in bound.params[:-1])
        assert 'ORDER BY "gross_profit" ASC NULLS LAST, "branch_code" ASC' in bound.sql
        assert '"product_line" ASC NULLS LAST LIMIT ?' in bound.sql
        assert bound == compile_governed_sql(plan, selection_catalog)
        assert compile_governed_sql(plan, selection_catalog, row_cap=4).row_cap == 4
        assert (
            compile_governed_sql(plan, selection_catalog, row_cap=4).fingerprint
            != bound.fingerprint
        )

    def test_different_filter_values_change_fingerprint(self, selection_catalog, analyst_auth):
        def compile_for_branch(branch):
            plan = _governed_plan(
                selection_catalog,
                analyst_auth,
                filters=[{"field": "branch_code", "op": "=", "value": branch}],
            )
            return compile_governed_sql(plan, selection_catalog)

        hn, dn = compile_for_branch("HN"), compile_for_branch("DN")
        assert hn.sql == dn.sql
        assert hn.params[-2:] == ("HN", 1000)
        assert dn.params[-2:] == ("DN", 1000)
        assert hn.fingerprint != dn.fingerprint

    @pytest.mark.parametrize("view,source", [("mgmt", "v_mgmt"), ("tax", "v_tax")])
    def test_flow_uses_approved_ledger_view(self, selection_catalog, cfo_auth, view, source):
        bound = compile_governed_sql(
            _governed_plan(selection_catalog, cfo_auth, view=view), selection_catalog
        )
        assert bound.source == source
        assert f" FROM {source} WHERE " in bound.sql
        assert "NOT is_closing" in bound.sql

    def test_budget_uses_month_keys_and_budget_dimensions(
        self, selection_catalog, analyst_auth, db_conn
    ):
        plan = _governed_plan(
            selection_catalog,
            analyst_auth,
            metric_ids=["budget_amount"],
            dimensions=["month", "branch_code"],
            operation="timeseries",
        )
        bound = compile_governed_sql(plan, selection_catalog)
        assert bound.source == "budget"
        assert "CAST(year_no AS INTEGER) * 100 + month_no" in bound.sql
        assert "PRINTF('%04d-%02d', year_no, month_no)" in bound.sql
        assert bound.params == (202608, 202608, 1000)
        assert db_conn.execute("EXPLAIN " + bound.sql, bound.params).fetchone() is not None

    def test_snapshot_binds_only_as_of_date(self, selection_catalog, analyst_auth):
        plan = _governed_plan(
            selection_catalog,
            analyst_auth,
            metric_ids=["cash_balance"],
            time={
                "mode": "as_of",
                "start": None,
                "end": None,
                "as_of": "2026-08-31",
                "grain": None,
            },
        )
        bound = compile_governed_sql(plan, selection_catalog)
        assert "posting_date <= CAST(? AS DATE)" in bound.sql
        assert "is_closing" not in bound.sql
        assert bound.params == ("2026-08-31", 1000)

    def test_mixed_warehouse_sources_fail_closed(self, selection_catalog, analyst_auth):
        plan = _governed_plan(
            selection_catalog, analyst_auth, metric_ids=["net_revenue", "budget_amount"]
        )
        with pytest.raises(GovernedError) as exc_info:
            compile_governed_sql(plan, selection_catalog)
        assert exc_info.value.code == "unsupported_data_source"

    def test_compiler_rejects_stale_catalog_and_unverified_binding(
        self, selection_catalog, analyst_auth
    ):
        original = _governed_plan(selection_catalog, analyst_auth)
        definition = selection_catalog.get("net_revenue")
        definition["sql_expr"] = "SUM(employee_code)"
        changed = GovernedCatalog([definition])
        with pytest.raises(GovernedError) as exc_info:
            compile_governed_sql(original, changed)
        assert exc_info.value.code == "invalid_request"
        with pytest.raises(GovernedError) as exc_info:
            compile_governed_sql(_governed_plan(changed, analyst_auth), changed)
        assert exc_info.value.code == "unsupported_data_source"


class TestSQLSafetyValidationContract:
    """Contract 19: sql.safety.v1."""

    @pytest.fixture
    def compiled_query(self, selection_catalog, analyst_auth):
        plan = _governed_plan(selection_catalog, analyst_auth)
        runtime = build_runtime_context(
            "request", "trace", analyst_auth, "vi-VN", "Asia/Ho_Chi_Minh", plan.catalog_hash
        )
        return compile_governed_sql(plan, selection_catalog), runtime

    def test_safety_gate_allows_valid_bound_query(self, selection_catalog, compiled_query) -> None:
        bound, runtime = compiled_query
        safe = validate_governed_sql(
            bound, selection_catalog, runtime, warehouse_tenant_id=runtime["tenant_id"]
        )
        assert safe["status"] == "allowed"
        assert safe["query_fingerprint"] == bound.fingerprint
        assert len(safe["checks"]) == 7
        assert all(safe["checks"].values())
        assert isinstance(safe["safe_bound_query"], SafeBoundQuery)
        assert safe["safe_bound_query"].query == bound
        with pytest.raises(TypeError, match="validate_sql_safety"):
            SafeBoundQuery(bound, _seal=None)

    @pytest.mark.parametrize(
        "mutation_fn,failed_check",
        [
            (
                lambda b: replace(b, sql="DELETE FROM v_mgmt WHERE posting_date >= ? LIMIT ?"),
                "read_only",
            ),
            (
                lambda b: replace(b, sql=b.sql + "; SELECT * FROM payroll"),
                "single_statement",
            ),
            (
                lambda b: replace(b, sql=b.sql.replace("FROM v_mgmt", "FROM duckdb_tables")),
                "approved_relations",
            ),
            (
                lambda b: replace(b, sql=b.sql.replace("SELECT ", "SELECT employee_code, ")),
                "approved_columns",
            ),
            (
                lambda b: replace(b, sql=b.sql.replace("WHERE ", "WHERE branch_code = 'HN' AND ")),
                "parameterized",
            ),
            (lambda b: replace(b, params=b.params[:-1]), "parameterized"),
            (lambda b: replace(b, params=("2025-01-01", *b.params[1:])), "parameterized"),
            (lambda b: replace(b, fingerprint="sha256:stale"), "parameterized"),
            (lambda b: replace(b, sql=b.sql.removesuffix(" LIMIT ?")), "row_cap_present"),
            (
                lambda b: replace(b, params=(*b.params[:-1], 1001), row_cap=1001),
                "row_cap_present",
            ),
            (lambda b: replace(b, tenant_id="wrong-tenant"), "tenant_scope_present"),
            (lambda b: replace(b, catalog_hash="catalog-tampered"), "tenant_scope_present"),
        ],
    )
    def test_safety_gate_rejects_unsafe_queries(
        self, selection_catalog, compiled_query, mutation_fn, failed_check: str
    ) -> None:
        bound, runtime = compiled_query
        tampered = mutation_fn(bound)
        with pytest.raises(GovernedError) as exc_info:
            validate_governed_sql(
                tampered, selection_catalog, runtime, warehouse_tenant_id=runtime["tenant_id"]
            )
        assert exc_info.value.code == "unsafe_sql_rejected"
        assert exc_info.value.details["checks"][failed_check] is False
        assert tampered.sql not in str(exc_info.value.to_dict())

    @pytest.mark.parametrize(
        "changes",
        [
            {"tenant_id": "another-tenant"},
            {"catalog_hash": "stale"},
            {"policy_hash": "stale"},
            {"allowed_views": ["tax"]},
        ],
    )
    def test_safety_gate_rejects_changed_runtime(self, selection_catalog, compiled_query, changes):
        bound, runtime = compiled_query
        with pytest.raises(GovernedError) as exc_info:
            validate_governed_sql(
                bound,
                selection_catalog,
                {**runtime, **changes},
                warehouse_tenant_id=runtime["tenant_id"],
            )
        assert exc_info.value.details["checks"]["tenant_scope_present"] is False

    @pytest.mark.parametrize("tenant", [None, "another-tenant"])
    def test_safety_gate_requires_trusted_warehouse_tenant(
        self, selection_catalog, compiled_query, tenant
    ):
        bound, runtime = compiled_query
        with pytest.raises(GovernedError) as exc_info:
            validate_governed_sql(bound, selection_catalog, runtime, warehouse_tenant_id=tenant)
        assert exc_info.value.details["checks"]["tenant_scope_present"] is False

    def test_safety_gate_rejects_sql_shaped_payload(self, selection_catalog, compiled_query):
        bound, runtime = compiled_query
        with pytest.raises(GovernedError) as exc_info:
            validate_governed_sql(
                {"sql": bound.sql, "params": bound.params},
                selection_catalog,
                runtime,
                warehouse_tenant_id=runtime["tenant_id"],
            )
        assert exc_info.value.code == "unsafe_sql_rejected"
        assert not any(exc_info.value.details["checks"].values())


class TestSQLExecutionOnDuckDBContract:
    """Contract 20: sql.execution.v1 against real data/cfo_warehouse.duckdb."""

    @pytest.fixture
    def warehouse(self, tmp_path):
        path = tmp_path / "warehouse.duckdb"
        copyfile(DB_PATH, path)
        return path

    def _authorize(self, catalog, auth, path, **slots):
        plan = _governed_plan(catalog, auth, **slots)
        runtime = build_runtime_context(
            "request", "trace", auth, "vi-VN", "Asia/Ho_Chi_Minh", plan.catalog_hash
        )
        return validate_governed_sql(
            compile_governed_sql(plan, catalog),
            catalog,
            runtime,
            warehouse_tenant_id=auth["tenant_id"],
            warehouse_path=path,
        )

    @pytest.mark.parametrize(
        "input", [{"status": "rejected"}, {"status": "allowed", "safe_bound_query": {}}]
    )
    def test_executor_rejects_unvalidated_query(self, input) -> None:
        with pytest.raises(GovernedError) as exc_info:
            execute_safe_sql(input)
        assert exc_info.value.code == "unsafe_sql_rejected"

    def test_duckdb_read_only_connection_blocks_writes(self, warehouse) -> None:
        with (
            _connect_read_only(warehouse) as connection,
            pytest.raises(duckdb.InvalidInputException, match="read-only"),
        ):
            connection.execute("CREATE TABLE forbidden_write (id INT)")

    def test_execute_mgmt_vs_tax_view_on_real_duckdb(
        self, selection_catalog, cfo_auth, warehouse
    ) -> None:
        res_mgmt = execute_safe_sql(
            self._authorize(
                selection_catalog, cfo_auth, warehouse, metric_ids=["operating_expense"]
            )
        )
        res_tax = execute_safe_sql(
            self._authorize(
                selection_catalog, cfo_auth, warehouse, metric_ids=["operating_expense"], view="tax"
            )
        )

        assert res_mgmt["data_watermark"] == "2026-10-14"
        assert res_mgmt["row_count"] == 1
        assert res_mgmt["truncated"] is False
        assert res_mgmt["rows"][0]["operating_expense"] == "3028615501.00"
        assert res_tax["rows"][0]["operating_expense"] == "2928697501.00"

    def test_database_outage_returns_temporarily_unavailable(
        self, selection_catalog, analyst_auth, tmp_path
    ) -> None:
        path = tmp_path / "missing.duckdb"
        safe = self._authorize(selection_catalog, analyst_auth, path)
        with pytest.raises(GovernedError) as exc_info:
            execute_safe_sql(safe)
        assert exc_info.value.code == "database_unavailable"
        assert exc_info.value.final_status == "temporarily_unavailable"
        assert exc_info.value.retryable is True
        assert str(path) not in str(exc_info.value.to_dict())
        copyfile(DB_PATH, path)
        assert execute_safe_sql(safe)["cache_hit"] is False

    def test_timeout_is_retryable(self, selection_catalog, analyst_auth, warehouse):
        safe = self._authorize(selection_catalog, analyst_auth, warehouse)
        with pytest.raises(GovernedError) as exc_info:
            execute_safe_sql(safe, timeout_ms=1)
        assert exc_info.value.code == "execution_timeout"
        assert exc_info.value.retryable
        assert not execute_safe_sql(safe)["cache_hit"]

    def test_cache_scope_watermark_and_copy(self, selection_catalog, analyst_auth, warehouse):
        safe = self._authorize(selection_catalog, analyst_auth, warehouse)
        cold = execute_safe_sql(safe)
        assert not cold["cache_hit"]
        cold["rows"][0]["net_revenue"] = "mutated"
        warm = execute_safe_sql(safe)
        assert warm["cache_hit"]
        assert warm["rows"][0]["net_revenue"] != "mutated"

        other_tenant = {**analyst_auth, "tenant_id": "other-tenant"}
        assert not execute_safe_sql(self._authorize(selection_catalog, other_tenant, warehouse))[
            "cache_hit"
        ]
        definition = selection_catalog.get("net_revenue")
        definition["label"] += " (new revision)"
        assert not execute_safe_sql(
            self._authorize(GovernedCatalog([definition]), analyst_auth, warehouse)
        )["cache_hit"]
        with duckdb.connect(str(warehouse)) as connection:
            connection.execute(
                "UPDATE company_info SET value = ? WHERE key = ?", ["2026-10-15", "as_of_date"]
            )
        changed = execute_safe_sql(safe)
        assert not changed["cache_hit"]
        assert changed["data_watermark"] == "2026-10-15"
