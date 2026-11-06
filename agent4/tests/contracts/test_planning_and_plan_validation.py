"""Tests for Contracts 16 and 17 of contracts.md:
- query.planning.v1
- query.plan-validation.v1
"""

from __future__ import annotations

import pytest

from tests.contract_harness import (
    ContractError,
    MetricCatalog,
    validate_semantic_plan_draft,
)


def _make_base_plan(**overrides: object) -> dict:
    base = {
        "plan_version": "1.0",
        "status": "ready",
        "metric_ids": ["net_profit_margin"],
        "time": {
            "mode": "range",
            "start": "2026-09-01",
            "end": "2026-09-30",
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
    }
    base.update(overrides)
    return base


class TestQueryPlanningAndPlanValidationContracts:
    """Contracts 16 & 17: query.planning.v1 & query.plan-validation.v1."""

    def test_validated_plan_trust_boundary_and_hashes(
        self, catalog: MetricCatalog, analyst_auth: dict
    ) -> None:
        validated_metrics = {
            "status": "validated",
            "metric_ids": ["net_profit_margin"],
            "catalog_hash": catalog.get_catalog_hash(),
        }
        plan_draft = _make_base_plan(operation=None)
        v_plan = validate_semantic_plan_draft(plan_draft, validated_metrics, catalog, analyst_auth)
        assert v_plan["contract_version"] == "validated-plan.v1"
        assert v_plan["status"] == "validated"
        assert v_plan["tenant_id"] == analyst_auth["tenant_id"]
        assert v_plan["catalog_hash"] == catalog.get_catalog_hash()
        assert v_plan["policy_hash"] == analyst_auth["policy_hash"]
        assert v_plan["operation"] == "aggregate"
        assert "operation=aggregate" in v_plan["applied_defaults"]

    def test_semantic_plan_draft_rejects_sql_or_physical_tables(
        self, catalog: MetricCatalog, analyst_auth: dict
    ) -> None:
        validated_metrics = {"status": "validated", "metric_ids": ["net_revenue"]}
        bad_draft = _make_base_plan(
            metric_ids=["net_revenue"],
            reason_code="SELECT * FROM gl_wide",
        )
        with pytest.raises(ContractError) as exc_info:
            validate_semantic_plan_draft(bad_draft, validated_metrics, catalog, analyst_auth)
        assert exc_info.value.code == "invalid_request"

    def test_planner_needs_clarification_path(
        self, catalog: MetricCatalog, analyst_auth: dict
    ) -> None:
        validated_metrics = {"status": "validated", "metric_ids": ["net_revenue"]}
        clarify_draft = _make_base_plan(
            status="needs_clarification",
            metric_ids=["net_revenue"],
            time={"mode": "range", "start": None, "end": None, "as_of": None, "grain": None},
            question_for_user="Bạn muốn xem doanh thu của chi nhánh Đà Nẵng trong khoảng thời gian nào?",
            unresolved_slots=["time"],
        )
        v_plan = validate_semantic_plan_draft(clarify_draft, validated_metrics, catalog, analyst_auth)
        assert v_plan["status"] == "needs_clarification"
        assert v_plan["unresolved_slots"] == ["time"]
        assert "Đà Nẵng" in v_plan["question_for_user"]

    def test_snapshot_metric_rejects_invalid_range_mode(
        self, catalog: MetricCatalog, analyst_auth: dict
    ) -> None:
        validated_metrics = {"status": "validated", "metric_ids": ["cash_balance"]}
        # 'cash_balance' has period_type='snapshot', so mode='range' must be rejected
        bad_snapshot_plan = _make_base_plan(
            metric_ids=["cash_balance"],
            time={"mode": "range", "start": "2026-08-01", "end": "2026-08-31", "as_of": None, "grain": "month"},
        )
        with pytest.raises(ContractError) as exc_info:
            validate_semantic_plan_draft(bad_snapshot_plan, validated_metrics, catalog, analyst_auth)
        assert exc_info.value.code == "invalid_request"
        assert exc_info.value.final_status == "unsupported"

        # Valid snapshot plan with mode='as_of' succeeds
        good_snapshot_plan = _make_base_plan(
            metric_ids=["cash_balance"],
            time={"mode": "as_of", "start": None, "end": None, "as_of": "2026-08-31", "grain": None},
        )
        v_plan = validate_semantic_plan_draft(good_snapshot_plan, validated_metrics, catalog, analyst_auth)
        assert v_plan["status"] == "validated"

    def test_dimension_and_filter_allowlist_and_limits(
        self, catalog: MetricCatalog, analyst_auth: dict
    ) -> None:
        validated_metrics = {"status": "validated", "metric_ids": ["net_profit_margin"]}

        # 1. Dimension not supported by net_profit_margin (e.g. cost_category)
        with pytest.raises(ContractError) as e_dim:
            validate_semantic_plan_draft(
                _make_base_plan(dimensions=["cost_category"]),
                validated_metrics,
                catalog,
                analyst_auth,
            )
        assert e_dim.value.code == "unsupported_metric"

        # 2. Invalid date range (start > end)
        with pytest.raises(ContractError) as e_date:
            validate_semantic_plan_draft(
                _make_base_plan(
                    time={"mode": "range", "start": "2026-09-30", "end": "2026-09-01", "as_of": None, "grain": "month"}
                ),
                validated_metrics,
                catalog,
                analyst_auth,
            )
        assert e_date.value.code == "invalid_request"

        # 3. Date range exceeding max_days (750 days)
        with pytest.raises(ContractError) as e_max_days:
            validate_semantic_plan_draft(
                _make_base_plan(
                    time={"mode": "range", "start": "2020-01-01", "end": "2026-09-30", "as_of": None, "grain": "year"}
                ),
                validated_metrics,
                catalog,
                analyst_auth,
            )
        assert e_max_days.value.code == "invalid_request"

        # 4. Out-of-bounds top_k
        with pytest.raises(ContractError) as e_topk:
            validate_semantic_plan_draft(
                _make_base_plan(top_k=500),
                validated_metrics,
                catalog,
                analyst_auth,
            )
        assert e_topk.value.code == "invalid_request"
