"""Regression coverage for M1-P0-2 time and benchmark contracts."""

import pytest

from agent4.core.catalog import MetricCatalog
from agent4.core.context import query_intake
from agent4.eval_adapter import predict
from agent4.planning.planner import build_semantic_plan_draft, parse_time_slot
from agent4.planning.validator import validate_semantic_plan_draft


@pytest.mark.parametrize(
    ("question", "locale", "start", "end", "grain"),
    [
        ("từ tháng 01/2026 đến tháng 08/2026", "vi-VN", "2026-01-01", "2026-08-31", "month"),
        ("from Q1 2025 to Q3 2026", "en-US", "2025-01-01", "2026-09-30", "quarter"),
        ("giữa tháng 08/2026 và tháng 09/2026", "vi-VN", "2026-08-01", "2026-09-30", "month"),
        ("so sánh tháng 09/2026 và tháng 08/2026", "vi-VN", "2026-08-01", "2026-09-30", "month"),
        ("between May 2026 and July 2026", "en-US", "2026-05-01", "2026-07-31", "month"),
        ("từ đầu năm 2026 đến hết tháng 10/2026", "vi-VN", "2026-01-01", "2026-10-31", "month"),
        ("beginning of 2026 through September 2026", "en-US", "2026-01-01", "2026-09-30", "month"),
        ("trong Quý 2 năm 2026", "vi-VN", "2026-04-01", "2026-06-30", "quarter"),
        ("trong Quý 3/2026 (tháng 7, 8, 9)", "vi-VN", "2026-07-01", "2026-09-30", "month"),
        ("from January through August 2026", "en-US", "2026-01-01", "2026-08-31", "month"),
        ("từ T1/2026 đến T8/2026", "vi-VN", "2026-01-01", "2026-08-31", "month"),
        ("cả năm 2025 và tám tháng đầu năm 2026", "vi-VN", "2025-01-01", "2026-08-31", "month"),
        ("in FY 2026 (up to September 2026)", "en-US", "2026-01-01", "2026-09-30", "month"),
        ("for Q4 2026 up to October 2026", "en-US", "2026-10-01", "2026-10-31", "month"),
        ("Revenue in August 2026 (08/2026)", "en-US", "2026-08-01", "2026-08-31", "month"),
        ("in FY 2025", "en-US", "2025-01-01", "2025-12-31", "year"),
        ("FY 2025 starting in January", "en-US", "2025-01-01", "2025-12-31", "year"),
        ("năm 2026 (đến hết tháng 10/2026)", "vi-VN", "2026-01-01", "2026-10-31", "month"),
        ("in fiscal year 2025", "en-US", "2025-01-01", "2025-12-31", "year"),
        ("trong năm tài chính 2025", "vi-VN", "2025-01-01", "2025-12-31", "year"),
        ("ngày 16/08/2026", "vi-VN", "2026-08-16", "2026-08-16", "day"),
        ("on August 16, 2026", "en-US", "2026-08-16", "2026-08-16", "day"),
    ],
)
def test_explicit_flow_time(question, locale, start, end, grain):
    assert parse_time_slot(question, locale=locale, period_type="flow") == {
        "mode": "range",
        "start": start,
        "end": end,
        "as_of": None,
        "grain": grain,
    }


@pytest.mark.parametrize(
    ("question", "locale", "date"),
    [
        ("Số dư tính đến cuối năm 2025 (31/12/2025)", "vi-VN", "2025-12-31"),
        ("Số dư cuối năm 2025", "vi-VN", "2025-12-31"),
        ("Số dư cuối quý 2/2026", "vi-VN", "2026-06-30"),
        ("Balance at the end of 2025", "en-US", "2025-12-31"),
        ("Balance as of the end of Q1 2026", "en-US", "2026-03-31"),
    ],
)
def test_explicit_snapshot_time(question, locale, date):
    assert parse_time_slot(question, locale=locale, period_type="snapshot")["as_of"] == date


@pytest.mark.parametrize(
    ("question", "period_type"),
    [
        ("FY 2025 non-calendar", "flow"),
        ("năm tài chính 2025 bắt đầu từ tháng 4", "flow"),
        ("fiscal year 2025 starting in April", "flow"),
        ("Revenue January 2026 or March 2026", "flow"),
        ("Revenue January 2026 and March 2026", "flow"),
        ("from May 2026 to March 2026", "flow"),
        ("for Q4 2026 up to August 2026", "flow"),
        ("Quý 3/2026 (tháng 7, 9)", "flow"),
        ("Balance at the end of 2025 (09/30/2025)", "snapshot"),
    ],
)
def test_unresolved_time_stays_non_executable(question, period_type):
    assert parse_time_slot(question, locale="en-US", period_type=period_type)["mode"] == "none"


def _plan(question, locale, metric):
    catalog = MetricCatalog(canonical=True)
    metrics = {
        "status": "validated",
        "metric_ids": [metric],
        "catalog_hash": catalog.get_catalog_hash(),
        "validated_capabilities": {metric: catalog.get_capability(metric)},
    }
    query = query_intake({"api_version": "v1", "question": question, "locale": locale})
    draft = build_semantic_plan_draft(query, metrics, {})
    return draft, metrics, catalog


@pytest.mark.parametrize(
    ("question", "locale", "metric", "view", "grain"),
    [
        ("Biên lợi nhuận gộp ngày 16/08/2026?", "vi-VN", "gross_margin_pct", "mgmt", "day"),
        ("Gross margin on August 16, 2026?", "en-US", "gross_margin_pct", "mgmt", "day"),
        ("What was the net profit margin in FY 2025?", "en-US", "net_margin_pct", "mgmt", "year"),
        (
            "Chi phí theo view quản trị trong quý 2/2026?",
            "vi-VN",
            "operating_expenses",
            "mgmt",
            "quarter",
        ),
        ("Doanh thu theo khung thuế trong quý 2/2026?", "vi-VN", "net_revenue", "tax", "quarter"),
        ("Doanh thu theo từng khách hàng quý 2/2026?", "vi-VN", "net_revenue", "mgmt", "month"),
        (
            "So sánh doanh thu giữa tháng 08/2026 và tháng 09/2026 theo từng tháng.",
            "vi-VN",
            "net_revenue",
            "mgmt",
            "month",
        ),
    ],
)
def test_explicit_planner_slots_pass_validation(question, locale, metric, view, grain, cfo_auth):
    draft, metrics, catalog = _plan(question, locale, metric)
    assert draft["status"] == "ready"
    sealed = validate_semantic_plan_draft(draft, metrics, catalog, cfo_auth)
    assert sealed.time.grain == grain
    assert sealed.view == view


def test_bare_margin_requires_clarification():
    draft, _, _ = _plan("What was our margin in FY 2025?", "en-US", "net_margin_pct")
    assert draft["unresolved_slots"] == ["metric"]


def test_explicit_comparison_still_requires_comparison_support():
    draft, _, _ = _plan(
        "Compare gross profit in Q3 2026 with Q2 2026, including the absolute change.",
        "en-US",
        "gross_profit",
    )
    assert draft["status"] == "unsupported"
    assert draft["reason_code"] == "unsupported_comparison"


@pytest.mark.asyncio
async def test_warning_aliases_are_applied_at_benchmark_boundary(monkeypatch):
    warnings = ["partial_data_watermark", "ratio_undefined", "other_warning"]

    async def query(*args, **kwargs):
        return {
            "status": "ready",
            "error": None,
            "data": None,
            "answer": None,
            "warnings": warnings,
        }

    monkeypatch.setattr("agent4.eval_adapter.run_governed_pipeline", query)
    result = await predict(
        {
            "id": "warning-alias",
            "auth_context": {
                "user_id": "u",
                "tenant_id": "t",
                "roles": ["cfo"],
                "allowed_views": ["mgmt"],
            },
            "user_query": "gross margin",
            "locale": "en-US",
            "options": {},
            "seed": 20261101,
        }
    )
    assert result["warning_codes"] == ["partial_data", "undefined_ratio", "other_warning"]
    assert warnings == ["partial_data_watermark", "ratio_undefined", "other_warning"]
