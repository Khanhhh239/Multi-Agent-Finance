"""Tests for Contracts 16 and 17 of contracts.md:
- query.planning.v1
- query.plan-validation.v1
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, replace
from datetime import date, timedelta

import pytest

from agent4.core.catalog import MetricCatalog as ProductionCatalog
from agent4.core.context import build_auth_context, query_intake
from agent4.core.errors import ContractError as ProductionContractError
from agent4.metric_selection.catalog_adapter import (
    build_canonical_catalog,
    build_full_catalog_retrieval_result,
)
from agent4.metric_selection.validator import validate_metrics
from agent4.planning.eval_adapter import predict, predict_baseline, predict_validated
from agent4.planning.planner import build_semantic_plan_draft, parse_time_slot
from agent4.planning.validator import PlanClarification, ValidatedPlan
from agent4.planning.validator import validate_semantic_plan_draft as seal_plan
from tests.contract_harness import (
    ContractError,
    MetricCatalog,
    validate_semantic_plan_draft,
)
from vals.run_eval import Prediction


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
        v_plan = validate_semantic_plan_draft(
            clarify_draft, validated_metrics, catalog, analyst_auth
        )
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
            time={
                "mode": "range",
                "start": "2026-08-01",
                "end": "2026-08-31",
                "as_of": None,
                "grain": "month",
            },
        )
        with pytest.raises(ContractError) as exc_info:
            validate_semantic_plan_draft(
                bad_snapshot_plan, validated_metrics, catalog, analyst_auth
            )
        assert exc_info.value.code == "invalid_request"
        assert exc_info.value.final_status == "unsupported"

        # Valid snapshot plan with mode='as_of' succeeds
        good_snapshot_plan = _make_base_plan(
            metric_ids=["cash_balance"],
            time={
                "mode": "as_of",
                "start": None,
                "end": None,
                "as_of": "2026-08-31",
                "grain": None,
            },
        )
        v_plan = validate_semantic_plan_draft(
            good_snapshot_plan, validated_metrics, catalog, analyst_auth
        )
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
                    time={
                        "mode": "range",
                        "start": "2026-09-30",
                        "end": "2026-09-01",
                        "as_of": None,
                        "grain": "month",
                    }
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
                    time={
                        "mode": "range",
                        "start": "2020-01-01",
                        "end": "2026-09-30",
                        "as_of": None,
                        "grain": "year",
                    }
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


class TestProductionSemanticPlanner:
    """Exercise M1 validation and the production query.planning.v1 entry point."""

    @pytest.mark.parametrize(
        ("locale", "question", "start", "end", "grain"),
        [
            ("vi-VN", "Doanh thu tháng 02/2024?", "2024-02-01", "2024-02-29", "month"),
            ("en-US", "Revenue for Sep. 2025?", "2025-09-01", "2025-09-30", "month"),
            ("vi-VN", "Doanh thu quý 2/2026?", "2026-04-01", "2026-06-30", "quarter"),
            ("en-US", "Revenue in Q4 2025?", "2025-10-01", "2025-12-31", "quarter"),
            ("en-US", "Revenue in the 2nd quarter of 2026?", "2026-04-01", "2026-06-30", "quarter"),
            ("vi-VN", "Doanh thu 6 tháng đầu năm 2026?", "2026-01-01", "2026-06-30", "month"),
            ("vi-VN", "Doanh thu sáu tháng cuối năm 2026?", "2026-07-01", "2026-12-31", "month"),
            ("en-US", "Revenue for H2 2026?", "2026-07-01", "2026-12-31", "month"),
            ("en-US", "Revenue in the first half of 2026?", "2026-01-01", "2026-06-30", "month"),
            ("vi-VN", "Doanh thu năm 2025?", "2025-01-01", "2025-12-31", "year"),
            ("en-US", "Revenue in 2025?", "2025-01-01", "2025-12-31", "year"),
            ("en-US", "Revenue in 09/2025?", "2025-09-01", "2025-09-30", "month"),
        ],
    )
    def test_supported_flow_periods(self, locale, question, start, end, grain):
        assert parse_time_slot(question, locale=locale, period_type="flow") == {
            "mode": "range",
            "start": start,
            "end": end,
            "as_of": None,
            "grain": grain,
        }

    @pytest.mark.parametrize(
        ("locale", "question", "expected"),
        [
            ("vi-VN", "Số dư tính đến 31/08/2026?", "2026-08-31"),
            ("en-US", "Balance as of 08/31/2026?", "2026-08-31"),
            ("en-US", "Balance as of 08/09/2026?", "2026-08-09"),
            ("vi-VN", "Số dư tại ngày 08/09/2026?", "2026-09-08"),
            ("en-US", "Balance as of August 31, 2026?", "2026-08-31"),
            ("en-US", "Balance as at 31 Aug 2026?", "2026-08-31"),
            ("vi-VN", "Số dư ngày 2024-02-29?", "2024-02-29"),
        ],
    )
    def test_supported_as_of_dates(self, locale, question, expected):
        assert parse_time_slot(question, locale=locale, period_type="snapshot") == {
            "mode": "as_of",
            "start": None,
            "end": None,
            "as_of": expected,
            "grain": None,
        }

    @pytest.mark.parametrize(
        ("period_type", "question"),
        [
            ("flow", "Revenue this month?"),
            ("flow", "Doanh thu tháng 8?"),
            ("flow", "Revenue in August or September 2026?"),
            ("flow", "Revenue in 2025 or 2026?"),
            ("flow", "Doanh thu quý 2/2026 hay quý 3/2026?"),
            ("flow", "Doanh thu quý 5/2026?"),
            ("flow", "Doanh thu tháng 13/2026?"),
            ("flow", "Revenue as of 2026-08-31?"),
            ("snapshot", "Số dư tháng 08/2026?"),
            ("snapshot", "Balance as of 2026-02-29?"),
            ("snapshot", "Balance as of 31/02/2026?"),
            ("snapshot", "What is the current balance?"),
            ("snapshot", "Balance on Aug 30, 2026 or Aug 31, 2026?"),
        ],
    )
    def test_unresolved_time(self, period_type, question):
        assert parse_time_slot(question, period_type=period_type)["mode"] == "none"

    def test_ranking_filters_and_view(self, production_plan):
        draft = production_plan(
            "Bottom 5 customers by net revenue for branches HN and HCM in Q2 2026 under the tax view",
            ["net_revenue"],
            locale="en-US",
        )
        assert draft == _make_base_plan(
            metric_ids=["net_revenue"],
            time={
                "mode": "range",
                "start": "2026-04-01",
                "end": "2026-06-30",
                "as_of": None,
                "grain": "quarter",
            },
            dimensions=["partner_code"],
            filters=[{"field": "branch_code", "op": "IN", "value": ["HN", "HCM"]}],
            view="tax",
            operation="ranking",
            sort={"metric_id": "net_revenue", "direction": "asc"},
            top_k=5,
        )

    @pytest.mark.parametrize(
        ("question", "metric_id", "field", "value"),
        [
            ("Doanh thu của dòng sản phẩm IT tháng 08/2026?", "net_revenue", "product_line", "IT"),
            (
                "Chi phí hoạt động của phòng Kinh doanh tháng 08/2026?",
                "operating_expenses",
                "department_code",
                "KD",
            ),
            (
                "Chi phí hoạt động khoản mục tiền điện nước tháng 08/2026?",
                "operating_expenses",
                "cost_category",
                "DIEN_NUOC",
            ),
            (
                "Chi phí hoạt động khoản mục bảo hiểm tài sản tháng 08/2026?",
                "operating_expenses",
                "cost_category",
                "BAOHIEM_TS",
            ),
            (
                "Doanh thu của khách hàng KH0082 tháng 08/2026?",
                "net_revenue",
                "partner_code",
                "KH0082",
            ),
            (
                "Công nợ phải trả NCC-PP-TN tính đến 31/08/2026?",
                "ap_balance",
                "partner_code",
                "NCC-PP-TN",
            ),
        ],
    )
    def test_named_filter(self, production_plan, question, metric_id, field, value):
        draft = production_plan(question, [metric_id])
        assert draft["status"] == "ready"
        assert draft["filters"] == [{"field": field, "op": "=", "value": value}]

    def test_timeseries_breakdown_and_sort(self, production_plan):
        draft = production_plan(
            "Doanh thu theo tháng và chi nhánh trong năm 2026, sắp xếp giảm dần",
            ["net_revenue"],
        )
        assert draft["status"] == "ready"
        assert draft["dimensions"] == ["month", "branch_code"]
        assert draft["operation"] == "timeseries"
        assert draft["time"]["grain"] == "month"
        assert draft["sort"] == {"metric_id": "net_revenue", "direction": "desc"}

    def test_preserve_slots_during_metric_clarification(self, production_plan):
        draft = production_plan("Công nợ tại ngày 31/08/2026?", [])
        assert draft["status"] == "needs_clarification"
        assert draft["unresolved_slots"] == ["metric"]
        assert draft["time"]["as_of"] == "2026-08-31"
        assert "phải thu" in draft["question_for_user"] and "phải trả" in draft["question_for_user"]

    def test_missing_time_and_business_intent(self, production_plan):
        draft = production_plan(
            "What is our profit margin by branch?", ["gross_margin_pct"], locale="en-US"
        )
        assert draft["status"] == "needs_clarification"
        assert draft["unresolved_slots"] == ["metric", "time"]
        assert draft["metric_ids"] == []
        assert draft["dimensions"] == ["branch_code"]
        assert draft["time"]["mode"] == "none"
        assert "gross margin or net profit margin" in draft["question_for_user"]
        assert "time period" in draft["question_for_user"]

    def test_snapshot_missing_date(self, production_plan):
        draft = production_plan("What is the total loan balance?", ["debt_balance"], locale="en-US")
        assert draft["unresolved_slots"] == ["time"]
        assert "as-of date" in draft["question_for_user"]

    @pytest.mark.parametrize(
        ("question", "slot"),
        [
            ("Doanh thu quản trị hay sổ thuế trong năm 2026?", "view"),
            ("Top 500 khách hàng có doanh thu cao nhất trong năm 2026?", "top_k"),
            ("Doanh thu của chi nhánh UNKNOWN trong năm 2026?", "filters"),
            ("Doanh thu theo kênh bán hàng trong năm 2026?", "dimensions"),
            ("Doanh thu chi nhánh HN trừ HCM trong năm 2026?", "filters"),
            ("Revenue for branch HN or product line SVC in 2026?", "filters"),
            ("Top 5 doanh thu trong năm 2026?", "dimensions"),
        ],
    )
    def test_missing_or_conflicting_business_slots(self, production_plan, question, slot):
        draft = production_plan(question, ["net_revenue"])
        assert draft["status"] == "needs_clarification"
        assert draft["unresolved_slots"] == [slot]
        assert draft["question_for_user"]

    def test_incompatible_business_dimension_is_not_dropped(self, production_plan):
        draft = production_plan(
            "Tỷ suất lợi nhuận ròng theo chi nhánh tháng 08/2026?", ["net_margin_pct"]
        )
        assert draft["status"] == "unsupported"
        assert draft["reason_code"] == "incompatible_plan"
        assert draft["dimensions"] == ["branch_code"]

    @pytest.mark.parametrize(
        "content",
        [
            "SELECT * FROM payroll",
            "gl_wide",
            "ar_invoice_line",
            "dim_partner",
            "payroll table",
            "HN' OR 1=1 --",
        ],
    )
    def test_query_sql_and_physical_identifiers_rejected(self, production_plan, content):
        with pytest.raises(ProductionContractError) as exc_info:
            production_plan(f"Doanh thu tháng 08/2026 {content}", ["net_revenue"])
        assert exc_info.value.code == "invalid_request"
        assert exc_info.value.stage == "query_planning"
        assert content not in str(exc_info.value)

    def test_clarification_text_from_selector_is_never_echoed(self):
        draft = build_semantic_plan_draft(
            query_intake({"api_version": "v1", "question": "Which profit?", "locale": "en-US"}),
            {
                "status": "needs_clarification",
                "metric_ids": [],
                "validated_capabilities": {},
                "clarification_question": "SELECT * FROM gl_wide",
            },
            {},
        )
        assert draft["status"] == "needs_clarification"
        assert "SELECT" not in str(draft)
        assert "gl_wide" not in str(draft)

    @pytest.mark.asyncio
    async def test_benchmark_adapter_serializes_ambiguous_selection(self, cfo_auth):
        request = {
            "id": "adapter-regression",
            "user_query": "Which profit margin should we look at in Q3 2025?",
            "locale": "en-US",
            "auth_context": cfo_auth,
            "query_context": {},
        }
        baseline = Prediction.model_validate(await predict_baseline(request))
        result = Prediction.model_validate(await predict(request))
        assert result.selection == baseline.selection
        assert result.selection.status == "ambiguous"
        assert baseline.plan is None
        assert result.plan.unresolved_slots == ["metric"]
        assert result.plan.time.start.isoformat() == "2025-07-01"


@pytest.fixture
def production_plan(cfo_auth):
    catalog = build_canonical_catalog()

    def plan(question, metric_ids, *, locale="vi-VN", context=None):
        query = query_intake({"api_version": "v1", "question": question, "locale": locale})
        context = context or {"reference_date": "2026-10-14", "timezone": "Asia/Ho_Chi_Minh"}
        candidates = build_full_catalog_retrieval_result(question, catalog, cfo_auth)
        metrics = validate_metrics(
            {
                "status": "resolved" if metric_ids else "ambiguous",
                "metric_ids": metric_ids,
                "clarification_question": None,
                "unsupported_reason": None,
            },
            candidates,
            catalog,
            cfo_auth,
            context,
        )
        return build_semantic_plan_draft(query, metrics, context)

    return plan


@pytest.fixture
def plan_gate(cfo_auth):
    catalog = build_canonical_catalog()
    metrics = validate_metrics(
        {
            "status": "resolved",
            "metric_ids": ["net_revenue"],
            "clarification_question": None,
            "unsupported_reason": None,
        },
        build_full_catalog_retrieval_result("Doanh thu", catalog, cfo_auth),
        catalog,
        cfo_auth,
        {},
    )
    return catalog, metrics


class TestProductionPlanValidation:
    def test_plan_gate_preserves_and_seals_planner_output(self, plan_gate, cfo_auth):
        catalog, metrics = plan_gate
        question = "Bottom 5 customers by net revenue for branches HN and HCM in Q2 2026"
        query = query_intake({"api_version": "v1", "question": question, "locale": "en-US"})
        draft = build_semantic_plan_draft(query, metrics, {})
        plan = seal_plan(draft, metrics, catalog, cfo_auth, row_cap=80)
        assert isinstance(plan, ValidatedPlan)
        assert (plan.status, plan.contract_version) == ("validated", "validated-plan.v1")
        assert (plan.tenant_id, plan.policy_hash, plan.catalog_hash) == (
            cfo_auth["tenant_id"],
            cfo_auth["policy_hash"],
            catalog.get_catalog_hash(),
        )
        assert (plan.dimensions, plan.operation, plan.top_k, plan.row_cap) == (
            ("partner_code",),
            "ranking",
            5,
            80,
        )
        draft["time"]["start"] = "2026-04-02"
        draft["filters"][0]["value"].append("DN")
        draft["sort"]["direction"] = "desc"
        draft["metric_ids"].clear()
        assert plan.time.start == date(2026, 4, 1)
        assert plan.filters[0].value == ("HN", "HCM")
        assert plan.sort.direction == "asc"
        assert plan.metric_ids == ("net_revenue",)
        for target, attribute in (
            (plan, "row_cap"),
            (plan.time, "start"),
            (plan.filters[0], "value"),
            (plan.sort, "direction"),
        ):
            with pytest.raises(FrozenInstanceError):
                setattr(target, attribute, None)
        with pytest.raises(TypeError, match="Use validate_semantic_plan_draft"):
            replace(plan, _seal=object(), row_cap=9999)

    def test_plan_gate_defaults_and_catalog_capabilities(self, plan_gate, cfo_auth):
        catalog, metrics = plan_gate
        metrics["validated_capabilities"]["net_revenue"]["supported_dimensions"] = ["cost_category"]
        draft = _make_base_plan(
            metric_ids=["net_revenue"], operation=None, dimensions=["branch_code"]
        )
        plan = seal_plan(draft, metrics, catalog, cfo_auth)
        assert plan.operation == "aggregate"
        assert plan.applied_defaults == ("operation=aggregate",)
        draft["dimensions"] = ["cost_category"]
        with pytest.raises(ProductionContractError) as error:
            seal_plan(draft, metrics, catalog, cfo_auth)
        assert error.value.code == "unsupported_metric"

    def test_plan_gate_clarification_has_no_executable_fields(self, plan_gate, cfo_auth):
        catalog, metrics = plan_gate
        query = query_intake(
            {"api_version": "v1", "question": "What is our net revenue?", "locale": "en-US"}
        )
        draft = build_semantic_plan_draft(query, metrics, {})
        decision = seal_plan(draft, metrics, catalog, cfo_auth)
        assert isinstance(decision, PlanClarification)
        assert asdict(decision) == {
            "status": "needs_clarification",
            "question_for_user": draft["question_for_user"],
            "unresolved_slots": ("time",),
        }
        with pytest.raises(ProductionContractError) as error:
            seal_plan(asdict(decision), metrics, catalog, cfo_auth)
        assert error.value.code == "invalid_request"
        draft["question_for_user"] = "Which month from the previous year would you like to see?"
        assert (
            seal_plan(draft, metrics, catalog, cfo_auth).question_for_user
            == draft["question_for_user"]
        )

    @pytest.mark.parametrize(
        "update",
        [
            {"tenant_id": "forged"},
            {"catalog_hash": "forged"},
            {"policy_hash": "forged"},
            {"row_cap": 10000},
            {"plan_version": "1.1"},
            {"status": "validated"},
            {"time": {"mode": "none", "start": None, "end": None, "as_of": None}},
            {"dimensions": ["branch_code", "branch_code"]},
            {"metric_ids": ["net_revenue", "net_revenue"]},
            {"filters": [{"field": "branch_code", "op": "=", "value": ["HN"]}]},
            {"filters": [{"field": "branch_code", "op": "IN", "value": "HN"}]},
            {"filters": [{"field": "branch_code", "op": "IN", "value": []}]},
            {"filters": [{"field": "branch_code", "op": "!=", "value": "HN"}]},
            {"filters": [{"field": "branch_code", "op": "=", "value": "unknown"}]},
            {"filters": [{"field": "partner_code", "op": "=", "value": "KH１２３４"}]},
            {"top_k": 0},
            {"top_k": 101},
            {"top_k": True},
            {"top_k": "5"},
            {"sort": {"metric_id": "cogs", "direction": "asc"}},
            {"sort": {"metric_id": "net_revenue", "direction": "sideways"}},
            {"operation": "ranking", "sort": None},
            {"operation": "timeseries", "dimensions": ["year"]},
        ],
    )
    def test_plan_gate_rejects_invalid_schema_and_slots(self, update, plan_gate, cfo_auth):
        catalog, metrics = plan_gate
        draft = _make_base_plan(metric_ids=["net_revenue"])
        draft.update(update)
        with pytest.raises(ProductionContractError) as error:
            seal_plan(draft, metrics, catalog, cfo_auth)
        assert (error.value.code, error.value.stage) == (
            "invalid_request",
            "semantic_plan_validation",
        )

    @pytest.mark.parametrize(
        ("start", "end", "status"),
        [
            ("2026-09-31", "2026-10-01", "error"),
            ("20260901", "2026-10-01", "error"),
            ("2026-09-30", "2026-09-01", "error"),
            ("2020-01-01", "2026-10-01", "unsupported"),
            (0, "2026-10-01", "error"),
        ],
    )
    def test_plan_gate_date_errors(self, start, end, status, plan_gate, cfo_auth):
        catalog, metrics = plan_gate
        draft = _make_base_plan(metric_ids=["net_revenue"])
        draft["time"].update(start=start, end=end)
        with pytest.raises(ProductionContractError) as error:
            seal_plan(draft, metrics, catalog, cfo_auth)
        assert (error.value.code, error.value.final_status) == ("invalid_request", status)

    def test_plan_gate_hard_and_policy_limits(self, plan_gate, cfo_auth):
        catalog, metrics = plan_gate
        draft = _make_base_plan(
            metric_ids=["net_revenue"],
            sort={"metric_id": "net_revenue", "direction": "desc"},
            top_k=100,
        )
        start = date.fromisoformat(draft["time"]["start"])
        draft["time"]["end"] = (start + timedelta(days=750)).isoformat()
        assert seal_plan(draft, metrics, catalog, cfo_auth).top_k == 100
        for limits in (
            {"max_days": 749},
            {"max_days": 751},
            {"max_top_k": 99},
            {"max_top_k": 101},
            {"row_cap": 1001},
            {"row_cap": False},
        ):
            with pytest.raises(ProductionContractError) as error:
                seal_plan(draft, metrics, catalog, cfo_auth, **limits)
            assert error.value.code == "invalid_request"

    def test_plan_gate_snapshot_and_flow_modes(self, plan_gate, cfo_auth):
        catalog, flow = plan_gate
        snapshot = {**flow, "metric_ids": ["cash_and_equivalents"]}
        draft = _make_base_plan(metric_ids=["cash_and_equivalents"])
        with pytest.raises(ProductionContractError) as error:
            seal_plan(draft, snapshot, catalog, cfo_auth)
        assert (error.value.code, error.value.final_status) == ("invalid_request", "unsupported")
        draft["time"].update(mode="as_of", as_of="2026-09-30", start=None, end=None, grain=None)
        assert seal_plan(draft, snapshot, catalog, cfo_auth).time.as_of == date(2026, 9, 30)
        draft["metric_ids"] = ["net_revenue"]
        with pytest.raises(ProductionContractError) as error:
            seal_plan(draft, flow, catalog, cfo_auth)
        assert (error.value.code, error.value.final_status) == ("invalid_request", "unsupported")

    def test_plan_gate_rechecks_auth_and_upstream_selection(
        self, plan_gate, cfo_auth, analyst_auth
    ):
        catalog, metrics = plan_gate
        draft = _make_base_plan(metric_ids=["net_revenue"], view="tax")
        restricted = build_auth_context(
            {"user_id": "restricted", "tenant_id": "minh-phat", "roles": ["cfo"]},
            {"allowed_views": ["mgmt", "tax"], "allowed_metrics": ["cogs"], "policy_version": "v2"},
        )
        for auth in (analyst_auth, restricted, {"allowed_views": ["tax"]}):
            with pytest.raises(ProductionContractError) as error:
                seal_plan(draft, metrics, catalog, auth)
            assert (error.value.code, error.value.final_status) == ("forbidden_metric", "forbidden")
        with pytest.raises(ProductionContractError) as error:
            seal_plan(draft, {**metrics, "catalog_hash": "stale"}, catalog, cfo_auth)
        assert error.value.code == "invalid_request"
        draft["metric_ids"] = ["cogs"]
        with pytest.raises(ProductionContractError) as error:
            seal_plan(draft, metrics, catalog, cfo_auth)
        assert error.value.code == "metric_outside_candidates"

    @pytest.mark.parametrize(
        ("ids", "update", "expected_code"),
        [
            (["net_revenue", "cash_and_equivalents"], {}, "incompatible_metrics"),
            (
                ["net_revenue", "net_margin_pct"],
                {"dimensions": ["branch_code"]},
                "unsupported_metric",
            ),
            (
                ["net_revenue"],
                {"filters": [{"field": "department_code", "op": "=", "value": "KD"}]},
                "unsupported_metric",
            ),
            (
                ["net_revenue"],
                {"filters": [{"field": "partner_code", "op": "=", "value": "NCC-PP-TN"}]},
                "unsupported_metric",
            ),
            (["cash_and_equivalents"], {"view": "tax"}, "unsupported_view"),
            (["missing_metric"], {}, "unknown_metric"),
        ],
    )
    def test_plan_gate_catalog_and_metric_compatibility(
        self, ids, update, expected_code, plan_gate, cfo_auth
    ):
        catalog, metrics = plan_gate
        draft = _make_base_plan(metric_ids=ids, **update)
        if ids == ["cash_and_equivalents"]:
            draft["time"].update(mode="as_of", start=None, end=None, as_of="2026-09-30", grain=None)
        with pytest.raises(ProductionContractError) as error:
            seal_plan(draft, {**metrics, "metric_ids": ids}, catalog, cfo_auth)
        assert error.value.code == expected_code

    @pytest.mark.asyncio
    async def test_plan_gate_benchmark_adapter_records_validation(self, cfo_auth):
        request = {
            "id": "plan-gate-regression",
            "user_query": "What is the profit margin by branch?",
            "locale": "en-US",
            "auth_context": cfo_auth,
            "query_context": {},
        }
        baseline = Prediction.model_validate(await predict(request))
        result = Prediction.model_validate(await predict_validated(request))
        assert result.plan == baseline.plan
        assert result.final_status == "needs_clarification"
        assert result.stage_latency_ms["plan_validation_ms"] >= 0
        assert result.execution is None

    @pytest.mark.parametrize(
        ("status", "verified", "expected"),
        [("draft", True, "unsupported_metric"), ("approved", False, "unsupported_data_source")],
    )
    def test_plan_gate_rechecks_current_metric_governance(
        self, status, verified, expected, plan_gate, cfo_auth
    ):
        catalog, metrics = plan_gate
        definition = catalog.get("net_revenue")
        definition.update(status=status, verified_handler=verified)
        current = ProductionCatalog([definition])
        with pytest.raises(ProductionContractError) as error:
            seal_plan(
                _make_base_plan(metric_ids=["net_revenue"]),
                {**metrics, "catalog_hash": current.get_catalog_hash()},
                current,
                cfo_auth,
            )
        assert error.value.code == expected

    @pytest.mark.asyncio
    async def test_plan_gate_benchmark_adapter_projects_sealed_fields(self, cfo_auth):
        result = Prediction.model_validate(
            await predict_validated(
                {
                    "id": "sealed-regression",
                    "user_query": "Net revenue for branch HN and HCM in Q2 2026?",
                    "locale": "en-US",
                    "auth_context": cfo_auth,
                    "query_context": {},
                }
            )
        )
        assert result.final_status == "ready"
        assert result.plan.time.start == date(2026, 4, 1)
        assert result.plan.filters[0].values == ["HN", "HCM"]
        assert result.stage_latency_ms["plan_validation_ms"] >= 0
