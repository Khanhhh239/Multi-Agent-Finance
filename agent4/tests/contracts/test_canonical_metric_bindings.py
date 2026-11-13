"""Governed catalog and warehouse bindings for M1-P0-1."""

import json
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from agent4.core.catalog import LEGACY_METRIC_IDS, MetricCatalog
from agent4.core.context import build_runtime_context, query_intake
from agent4.core.errors import ContractError
from agent4.engine.metrics import REGISTRY
from agent4.metric_selection.validator import validate_metrics
from agent4.planning.planner import build_semantic_plan_draft
from agent4.planning.validator import validate_semantic_plan_draft
from agent4.sql.compiler import compile_sql
from agent4.sql.safety import validate_sql_safety

_BENCHMARK = Path(__file__).resolve().parents[2] / "data/eval/contract_benchmark_questions.jsonl"


def test_canonical_catalog_has_all_registry_ids_and_only_22_visible_metrics(analyst_auth):
    catalog = MetricCatalog(canonical=True)
    assert all(catalog.contains(metric_id) for metric_id in REGISTRY)
    assert not catalog.get("experimental_cash_burn")["verified_handler"]
    visible = {metric["metric_id"] for metric in catalog.list_visible_metrics(analyst_auth)}
    assert len(visible) == 22
    assert visible.isdisjoint(LEGACY_METRIC_IDS)
    for alias, canonical in LEGACY_METRIC_IDS.items():
        auth = {**analyst_auth, "allowed_metrics": [alias]}
        assert catalog.has_verified_sql_handler(alias)
        assert catalog.validate_access(alias, auth)
        assert not catalog.validate_access(canonical, auth)
        assert [metric["metric_id"] for metric in catalog.list_visible_metrics(auth)] == [alias]


def test_legacy_catalog_can_explicitly_select_canonical_metrics(analyst_auth):
    catalog = MetricCatalog()
    assert all(catalog.contains(metric_id) for metric_id in REGISTRY)
    assert len(catalog.list_visible_metrics(analyst_auth)) == 13
    assert catalog.get_catalog_hash() != MetricCatalog(canonical=True).get_catalog_hash()
    auth = {**analyst_auth, "allowed_metrics": ["operating_expenses", "admin_expenses"]}
    visible = catalog.list_visible_metrics(auth)
    assert {metric["metric_id"] for metric in visible} == set(auth["allowed_metrics"])
    assert catalog.validate_access("operating_expenses", auth)
    assert not catalog.validate_access("operating_expense", auth)


@pytest.mark.parametrize("metric_id", ["gross_revenue", "free_cash_flow", "altman_z_score"])
def test_registered_metadata_is_rejected_before_sql(metric_id, analyst_auth):
    with pytest.raises(ContractError) as error:
        validate_metrics(
            {
                "status": "resolved",
                "metric_ids": [metric_id],
                "clarification_question": None,
                "unsupported_reason": None,
            },
            {"candidates": []},
            MetricCatalog(),
            analyst_auth,
        )
    assert error.value.final_status == "unsupported"
    assert error.value.code == "unsupported_metric"


@pytest.mark.parametrize("case_id", ["BM-119", "BM-120"])
@pytest.mark.parametrize("metric_id", ["operating_expenses", "operating_expense"])
def test_vendor_expense_cases_compile_and_execute(case_id, metric_id, analyst_auth):
    with _BENCHMARK.open(encoding="utf-8") as source:
        case = next(case for line in source if (case := json.loads(line))["id"] == case_id)
    catalog = MetricCatalog()
    selection = {
        "status": "validated",
        "metric_ids": [metric_id],
        "catalog_hash": catalog.get_catalog_hash(),
        "validated_capabilities": {metric_id: catalog.get_capability(metric_id)},
    }
    query = query_intake(
        {"api_version": "v1", "question": case["user_query"], "locale": case["locale"]}
    )
    draft = build_semantic_plan_draft(query, selection, case["query_context"])
    assert draft["status"] == "ready"
    plan = validate_semantic_plan_draft(draft, selection, catalog, analyst_auth)
    bound = compile_sql(plan, catalog)
    assert "NCC-MK-DG" not in bound.sql
    assert bound.params[-2] == "NCC-MK-DG"
    runtime = build_runtime_context(
        request_id="m1-p0-1",
        trace_id="vendor",
        auth_context=analyst_auth,
        locale=case["locale"],
        timezone="Asia/Ho_Chi_Minh",
        catalog_hash=catalog.get_catalog_hash(),
    )
    safe = validate_sql_safety(bound, catalog, runtime, warehouse_tenant_id="minh-phat")[
        "safe_bound_query"
    ]
    with duckdb.connect() as db:
        db.execute(
            """CREATE TABLE v_mgmt (
                posting_date DATE, is_closing BOOLEAN, source_module VARCHAR,
                account_code VARCHAR, partner_code VARCHAR,
                debit_amount DECIMAL(18,2), credit_amount DECIMAL(18,2)
            )"""
        )
        db.execute(
            """INSERT INTO v_mgmt VALUES
            ('2026-09-01', false, 'AP', '6411', 'NCC-MK-DG', 100.11, 0),
            ('2026-09-01', false, 'AP', '6421', 'NCC-MK-DG', 70.12, 10.03),
            ('2026-09-01', false, 'AP', '6421', 'NCC-OTHER', 800, 0),
            ('2026-09-01', false, 'OPENING', '6421', 'NCC-MK-DG', 800, 0),
            ('2026-09-01', true, 'GL', '6421', 'NCC-MK-DG', 800, 0)"""
        )
        assert db.execute(safe.query.sql, safe.query.params).fetchone() == (Decimal("160.20"),)


def test_snapshot_ratios_exclude_long_term_debt_from_current_liabilities():
    catalog = MetricCatalog()
    metrics = ["current_ratio", "quick_ratio", "debt_to_equity"]
    expressions = ", ".join(catalog.get(metric)["sql_expr"] for metric in metrics)
    with duckdb.connect() as db:
        result = db.execute(
            f"""SELECT {expressions}
            FROM (VALUES
                ('111', 80, 0, false, 'OPENING'),
                ('152', 20, 0, false, 'OPENING'),
                ('331', 0, 24, false, 'AP'),
                ('34111', 0, 6, false, 'BANK'),
                ('34112', 0, 10, false, 'BANK'),
                ('411', 0, 45, false, 'OPENING'),
                ('511', 0, 20, false, 'SALES'),
                ('641', 5, 0, false, 'AP'),
                ('511', 10, 0, true, 'GL')
            ) AS ledger(account_code, debit_amount, credit_amount, is_closing, source_module)"""
        ).fetchone()
        assert result == (Decimal("3.333333"), Decimal("2.666667"), Decimal("0.666667"))
        assert db.execute(
            f"""SELECT {expressions}
            FROM (VALUES ('111', 80, 0, false, 'OPENING'))
            AS ledger(account_code, debit_amount, credit_amount, is_closing, source_module)"""
        ).fetchone() == (None, None, None)
