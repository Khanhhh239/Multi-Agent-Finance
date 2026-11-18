"""Comprehensive regression suite for Agent 4 audit fixes (Prompts 1–4 + Expert Findings).

Covers:
1. VAS / TT133 / TT200 semantic accounting formulas, TK 515 financial income, 335/338 liabilities,
   closed-vs-open equity parity without double counting, 'THUONG' salary bonus, partner-level
   bilateral 131/331 aggregation, and VAS 24 cash_flow_breakdown.
2. OfflineSemanticSelector dimensional filters & comparison guard, vat_position settlement exclusion,
   hardened assert_safe_select SQL tokenizer, and DuckDB read-only / no-external-access sandbox.
3. All 7 MPX10 branches, 11 departments, C/V partner codes, refined _UNSAFE_OUTPUT sanitizer,
   and deterministic reference_date-anchored Vietnamese relative time resolution.
4. Non-blocking asyncio.to_thread OpenAI retrieval, offline Ollama GovernedLexicalSelector fallback,
   safe_display_text normalization, answer numeric & sign consistency validator, and 100% local-first
   selection.yaml + selection_cloud.yaml + dual env-var support.
"""

from __future__ import annotations

import asyncio
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import duckdb
import httpx
import pytest
import yaml

from agent4.answer.result_validator import safe_display_text
from agent4.answer.validator import validate_answer
from agent4.core.catalog import MetricCatalog
from agent4.core.config import AppConfig
from agent4.core.context import build_auth_context, build_runtime_context, query_intake
from agent4.core.errors import ContractError
from agent4.engine.metric_queries import METRIC_QUERIES
from agent4.metric_selection.config import (
    DEFAULT_CONFIG_PATH,
    PROJECT_DIR,
    EmbeddingConfig,
    LLMSelectionConfig,
    MetricSelectionConfig,
    RetrievalConfig,
    load_config,
)
from agent4.metric_selection.embedding import EmbeddingProvider
from agent4.metric_selection.llm_selector import LLMMetricSelector, validate_llm_selection_draft
from agent4.metric_selection.recovery import select_metrics_with_recovery
from agent4.planning._time import parse_time_slot
from agent4.planning.planner import build_semantic_plan_draft
from agent4.planning.validator import validate_semantic_plan_draft
from agent4.sql.compiler import compile_sql
from agent4.sql.safety import validate_sql_safety
from agent4.text2sql.catalog import CatalogSnapshot
from agent4.text2sql.compiler import SQLCompiler, assert_safe_select
from agent4.text2sql.errors import PlanRejected, UnsafeQuery
from agent4.text2sql.execution import DuckDBReadOnlyExecutor, _connect_read_only
from agent4.text2sql.models import (
    AuthContext as T2SAuthContext,
)
from agent4.text2sql.models import (
    BoundQuery,
    FilterDraft,
    SemanticPlanDraft,
    TimeDraft,
)
from agent4.text2sql.models import (
    ValidatedPlan as T2SValidatedPlan,
)
from agent4.text2sql.selector import OfflineSemanticSelector
from agent4.text2sql.validation import SemanticValidator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CFO_CLAIMS = {"user_id": "cfo-audit", "tenant_id": "minh-phat", "roles": ["cfo"]}
_CFO_POLICY = {
    "policy_version": "audit-v1",
    "allowed_views": ["mgmt", "tax"],
    "allowed_metrics": None,
}


def _cfo_auth() -> dict:
    return build_auth_context(_CFO_CLAIMS, _CFO_POLICY)


def _compile_governed_metric(
    metric_id: str,
    question: str,
    *,
    view: str = "mgmt",
    reference_date: str | None = None,
) -> tuple[str, tuple]:
    catalog = MetricCatalog()
    auth = _cfo_auth()
    selection = {
        "status": "validated",
        "metric_ids": [metric_id],
        "catalog_hash": catalog.get_catalog_hash(),
        "validated_capabilities": {metric_id: catalog.get_capability(metric_id)},
    }
    intake = query_intake({"api_version": "v1", "locale": "vi-VN", "question": question})
    qctx = {"requested_view": view}
    if reference_date is not None:
        qctx["reference_date"] = reference_date
    draft = build_semantic_plan_draft(intake, selection, qctx)
    assert draft["status"] == "ready", f"Expected ready plan, got: {draft}"
    plan = validate_semantic_plan_draft(draft, selection, catalog, auth)
    bound = compile_sql(plan, catalog)
    runtime = build_runtime_context(
        request_id="audit-req-1",
        trace_id="audit-trace-1",
        auth_context=auth,
        locale="vi-VN",
        timezone="Asia/Ho_Chi_Minh",
        catalog_hash=catalog.get_catalog_hash(),
    )
    safe = validate_sql_safety(bound, catalog, runtime, warehouse_tenant_id="minh-phat")[
        "safe_bound_query"
    ]
    return safe.query.sql, safe.query.params


def _compile_t2s_metric(
    metric_id: str,
    *,
    view: str = "mgmt",
    mode: str = "range",
    start: date | None = date(2026, 8, 1),
    end: date | None = date(2026, 8, 31),
    as_of: date | None = None,
    filters: list[FilterDraft] | None = None,
    group_by: list[str] | None = None,
) -> BoundQuery:
    snap = CatalogSnapshot()
    time_draft = (
        TimeDraft.as_of_date(as_of)
        if mode == "as_of" and as_of is not None
        else TimeDraft.range(start or date(2026, 8, 1), end or date(2026, 8, 31))
    )
    validated = T2SValidatedPlan(
        metric_ids=(metric_id,),
        time=time_draft,
        dimensions=tuple(group_by or ()),
        filters=tuple(filters or ()),
        view=view,  # type: ignore[arg-type]
        operation="timeseries" if group_by else "aggregate",
        sort=None,
        top_k=None,
        comparison=None,
        tenant_id="minh-phat",
        catalog_hash=snap.hash,
        policy_hash="audit-policy",
    )
    return SQLCompiler(snap).compile(validated)


def _create_ledger_table(con: duckdb.DuckDBPyConnection, view_name: str = "v_mgmt") -> None:
    con.execute(
        f"""
        CREATE TABLE {view_name} (
            journal_id VARCHAR,
            posting_date DATE,
            year_no INTEGER,
            quarter_no INTEGER,
            month_no INTEGER,
            year_month VARCHAR,
            account_code VARCHAR,
            account_type VARCHAR,
            partner_code VARCHAR,
            branch_code VARCHAR,
            department_code VARCHAR,
            product_line VARCHAR,
            cost_category VARCHAR,
            debit_amount DECIMAL(18,2),
            credit_amount DECIMAL(18,2),
            net_debit DECIMAL(18,2),
            source_document_type VARCHAR,
            source_module VARCHAR,
            is_closing BOOLEAN
        )
        """
    )


# ===========================================================================
# Prompt 1 + Subagent #1 — VAS / TT133 Semantic Accounting Formulas
# ===========================================================================


def test_selling_and_admin_expenses_tt133_tt200_no_double_count() -> None:
    with duckdb.connect() as con:
        _create_ledger_table(con)
        rows = [
            # TT200 selling 6411 = 100
            (
                "J1",
                "2026-08-10",
                2026,
                3,
                8,
                "2026-08",
                "6411",
                "EXPENSE",
                "V000001",
                "HN",
                "KD",
                None,
                "MARKETING",
                Decimal("100.00"),
                Decimal("0.00"),
                Decimal("100.00"),
                "BILL",
                "AP",
                False,
            ),
            # TT133 selling 6421 = 200
            (
                "J2",
                "2026-08-11",
                2026,
                3,
                8,
                "2026-08",
                "6421",
                "EXPENSE",
                "V000002",
                "HN",
                "KD",
                None,
                "VANCHUYEN",
                Decimal("200.00"),
                Decimal("0.00"),
                Decimal("200.00"),
                "BILL",
                "AP",
                False,
            ),
            # TT133 admin 6422 = 300
            (
                "J3",
                "2026-08-12",
                2026,
                3,
                8,
                "2026-08",
                "6422",
                "EXPENSE",
                "V000003",
                "HN",
                "HCNS",
                None,
                "THUE_MB",
                Decimal("300.00"),
                Decimal("0.00"),
                Decimal("300.00"),
                "BILL",
                "AP",
                False,
            ),
            # Direct parent 642 = 50
            (
                "J4",
                "2026-08-13",
                2026,
                3,
                8,
                "2026-08",
                "642",
                "EXPENSE",
                "V000004",
                "HN",
                "TCKT",
                None,
                "VPP",
                Decimal("50.00"),
                Decimal("0.00"),
                Decimal("50.00"),
                "BILL",
                "AP",
                False,
            ),
        ]
        con.executemany(
            "INSERT INTO v_mgmt VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

        # Governed SQL compiler (core/catalog.py)
        for metric_id, expected in (
            ("selling_expenses", Decimal("300.00")),
            ("admin_expenses", Decimal("350.00")),
            ("operating_expenses", Decimal("650.00")),
        ):
            sql, params = _compile_governed_metric(metric_id, f"{metric_id} tháng 08/2026?")
            actual = con.execute(sql, params).fetchone()[0]
            assert actual == expected, f"Governed {metric_id}: {actual} != {expected}"

        # Text2SQL compiler (engine/metrics.py + text2sql/compiler.py)
        for metric_id, expected in (
            ("selling_expenses", Decimal("300.00")),
            ("admin_expenses", Decimal("350.00")),
            ("operating_expenses", Decimal("650.00")),
        ):
            bound = _compile_t2s_metric(metric_id)
            actual = con.execute(bound.sql, list(bound.params)).fetchone()[0]
            assert actual == expected, f"Text2SQL {metric_id}: {actual} != {expected}"


def test_financial_income_515_liabilities_335_338_and_closed_open_equity_parity() -> None:
    with duckdb.connect() as con:
        _create_ledger_table(con)
        # Balanced multi-month ledger:
        # 2025-01-01 OPENING: Dr 11211 = 1000, Cr 4111 = 1000
        # 2026-08 (CLOSED):
        #   Sales: Dr 11211 = 500, Cr 5111 = 500
        #   Bank interest income (515): Dr 11211 = 25, Cr 515 = 25
        #   COGS: Dr 632 = 200, Cr 1561 = 200 (after buying inventory Dr 1561 = 250, Cr 11211 = 250)
        #   Loan interest (635 INTEREST): Dr 635 = 10, Cr 11211 = 10
        #   Bank fee (635 BANK_FEE): Dr 635 = 3, Cr 11211 = 3
        #   Accrued bonus (335): Dr 6421 = 40, Cr 335 = 40
        #   Social insurance payable (338): Dr 6422 = 30, Cr 338 = 30
        #   Depreciation (214): Dr 6422 = 15, Cr 2141 = 15 (after buying asset Dr 2111 = 100, Cr 11211 = 100)
        #   CIT tax (8211): Dr 8211 = 45, Cr 3334 = 45
        #   Net profit 2026-08 = 500 + 25 - 200 - 13 - 40 - 45 - 45 = 182
        #   Closing entry (is_closing=True): Dr 5111=500, Dr 515=25, Cr 632=200, Cr 635=13, Cr 6421=40, Cr 6422=45, Cr 8211=45, Cr 4212=182
        # 2026-09 (OPEN, NOT closed):
        #   Sales: Dr 11211 = 300, Cr 5111 = 300
        #   Interest income (515): Dr 11211 = 12, Cr 515 = 12
        #   Admin expense: Dr 6422 = 20, Cr 11211 = 20
        #   B4 equity adjustment on 4219: Dr 4219 = 8, Cr 11211 = 8
        entries = [
            (
                "J-OP",
                "2025-01-01",
                2025,
                1,
                1,
                "2025-01",
                "11211",
                "ASSET",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(1000),
                Decimal(0),
                Decimal(1000),
                "OPENING",
                "OPENING",
                False,
            ),
            (
                "J-OP",
                "2025-01-01",
                2025,
                1,
                1,
                "2025-01",
                "4111",
                "EQUITY",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(0),
                Decimal(1000),
                Decimal(-1000),
                "OPENING",
                "OPENING",
                False,
            ),
            (
                "J-INV",
                "2026-08-02",
                2026,
                3,
                8,
                "2026-08",
                "1561",
                "ASSET",
                "V000001",
                "HN",
                "MH",
                "IT",
                None,
                Decimal(250),
                Decimal(0),
                Decimal(250),
                "BILL",
                "AP",
                False,
            ),
            (
                "J-INV",
                "2026-08-02",
                2026,
                3,
                8,
                "2026-08",
                "11211",
                "ASSET",
                "V000001",
                "HN",
                "MH",
                "IT",
                None,
                Decimal(0),
                Decimal(250),
                Decimal(-250),
                "BILL",
                "AP",
                False,
            ),
            (
                "J-FA",
                "2026-08-03",
                2026,
                3,
                8,
                "2026-08",
                "2111",
                "ASSET",
                "V000002",
                "HN",
                "IT",
                None,
                None,
                Decimal(100),
                Decimal(0),
                Decimal(100),
                "BILL",
                "FA",
                False,
            ),
            (
                "J-FA",
                "2026-08-03",
                2026,
                3,
                8,
                "2026-08",
                "11211",
                "ASSET",
                "V000002",
                "HN",
                "IT",
                None,
                None,
                Decimal(0),
                Decimal(100),
                Decimal(-100),
                "BILL",
                "FA",
                False,
            ),
            (
                "J-REV8",
                "2026-08-10",
                2026,
                3,
                8,
                "2026-08",
                "11211",
                "ASSET",
                "C000001",
                "HN",
                "KD",
                "IT",
                None,
                Decimal(500),
                Decimal(0),
                Decimal(500),
                "INVOICE",
                "AR",
                False,
            ),
            (
                "J-REV8",
                "2026-08-10",
                2026,
                3,
                8,
                "2026-08",
                "5111",
                "REVENUE",
                "C000001",
                "HN",
                "KD",
                "IT",
                None,
                Decimal(0),
                Decimal(500),
                Decimal(-500),
                "INVOICE",
                "AR",
                False,
            ),
            (
                "J-515-8",
                "2026-08-15",
                2026,
                3,
                8,
                "2026-08",
                "11211",
                "ASSET",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(25),
                Decimal(0),
                Decimal(25),
                "INTEREST_INCOME",
                "CASH",
                False,
            ),
            (
                "J-515-8",
                "2026-08-15",
                2026,
                3,
                8,
                "2026-08",
                "515",
                "REVENUE",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(0),
                Decimal(25),
                Decimal(-25),
                "INTEREST_INCOME",
                "CASH",
                False,
            ),
            (
                "J-COGS8",
                "2026-08-10",
                2026,
                3,
                8,
                "2026-08",
                "632",
                "EXPENSE",
                None,
                "HN",
                "KHO",
                "IT",
                None,
                Decimal(200),
                Decimal(0),
                Decimal(200),
                "ISSUE",
                "INV",
                False,
            ),
            (
                "J-COGS8",
                "2026-08-10",
                2026,
                3,
                8,
                "2026-08",
                "1561",
                "ASSET",
                None,
                "HN",
                "KHO",
                "IT",
                None,
                Decimal(0),
                Decimal(200),
                Decimal(-200),
                "ISSUE",
                "INV",
                False,
            ),
            (
                "J-INT8",
                "2026-08-20",
                2026,
                3,
                8,
                "2026-08",
                "635",
                "EXPENSE",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(10),
                Decimal(0),
                Decimal(10),
                "LOAN_INTEREST",
                "LOAN",
                False,
            ),
            (
                "J-INT8",
                "2026-08-20",
                2026,
                3,
                8,
                "2026-08",
                "11211",
                "ASSET",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(0),
                Decimal(10),
                Decimal(-10),
                "LOAN_INTEREST",
                "LOAN",
                False,
            ),
            (
                "J-FEE8",
                "2026-08-21",
                2026,
                3,
                8,
                "2026-08",
                "635",
                "EXPENSE",
                None,
                "HN",
                "TCKT",
                None,
                "PHI_NH",
                Decimal(3),
                Decimal(0),
                Decimal(3),
                "BANK_FEE",
                "CASH",
                False,
            ),
            (
                "J-FEE8",
                "2026-08-21",
                2026,
                3,
                8,
                "2026-08",
                "11211",
                "ASSET",
                None,
                "HN",
                "TCKT",
                None,
                "PHI_NH",
                Decimal(0),
                Decimal(3),
                Decimal(-3),
                "BANK_FEE",
                "CASH",
                False,
            ),
            (
                "J-335",
                "2026-08-25",
                2026,
                3,
                8,
                "2026-08",
                "6421",
                "EXPENSE",
                None,
                "HN",
                "KD",
                None,
                "THUONG",
                Decimal(40),
                Decimal(0),
                Decimal(40),
                "PAYROLL",
                "HR",
                False,
            ),
            (
                "J-335",
                "2026-08-25",
                2026,
                3,
                8,
                "2026-08",
                "335",
                "LIABILITY",
                None,
                "HN",
                "KD",
                None,
                "THUONG",
                Decimal(0),
                Decimal(40),
                Decimal(-40),
                "PAYROLL",
                "HR",
                False,
            ),
            (
                "J-338",
                "2026-08-25",
                2026,
                3,
                8,
                "2026-08",
                "6422",
                "EXPENSE",
                None,
                "HN",
                "HCNS",
                None,
                "BAOHIEM",
                Decimal(30),
                Decimal(0),
                Decimal(30),
                "PAYROLL",
                "HR",
                False,
            ),
            (
                "J-338",
                "2026-08-25",
                2026,
                3,
                8,
                "2026-08",
                "338",
                "LIABILITY",
                None,
                "HN",
                "HCNS",
                None,
                "BAOHIEM",
                Decimal(0),
                Decimal(30),
                Decimal(-30),
                "PAYROLL",
                "HR",
                False,
            ),
            (
                "J-DEP8",
                "2026-08-31",
                2026,
                3,
                8,
                "2026-08",
                "6422",
                "EXPENSE",
                None,
                "HN",
                "IT",
                None,
                "KHAUHAO",
                Decimal(15),
                Decimal(0),
                Decimal(15),
                "DEPRECIATION",
                "FA",
                False,
            ),
            (
                "J-DEP8",
                "2026-08-31",
                2026,
                3,
                8,
                "2026-08",
                "2141",
                "ASSET",
                None,
                "HN",
                "IT",
                None,
                "KHAUHAO",
                Decimal(0),
                Decimal(15),
                Decimal(-15),
                "DEPRECIATION",
                "FA",
                False,
            ),
            (
                "J-CIT8",
                "2026-08-31",
                2026,
                3,
                8,
                "2026-08",
                "8211",
                "EXPENSE",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(45),
                Decimal(0),
                Decimal(45),
                "CIT",
                "TAX",
                False,
            ),
            (
                "J-CIT8",
                "2026-08-31",
                2026,
                3,
                8,
                "2026-08",
                "3334",
                "LIABILITY",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(0),
                Decimal(45),
                Decimal(-45),
                "CIT",
                "TAX",
                False,
            ),
            # Closing entry for 2026-08
            (
                "J-KC8",
                "2026-08-31",
                2026,
                3,
                8,
                "2026-08",
                "5111",
                "REVENUE",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(500),
                Decimal(0),
                Decimal(500),
                "CLOSING",
                "CLOSING",
                True,
            ),
            (
                "J-KC8",
                "2026-08-31",
                2026,
                3,
                8,
                "2026-08",
                "515",
                "REVENUE",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(25),
                Decimal(0),
                Decimal(25),
                "CLOSING",
                "CLOSING",
                True,
            ),
            (
                "J-KC8",
                "2026-08-31",
                2026,
                3,
                8,
                "2026-08",
                "632",
                "EXPENSE",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(0),
                Decimal(200),
                Decimal(-200),
                "CLOSING",
                "CLOSING",
                True,
            ),
            (
                "J-KC8",
                "2026-08-31",
                2026,
                3,
                8,
                "2026-08",
                "635",
                "EXPENSE",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(0),
                Decimal(13),
                Decimal(-13),
                "CLOSING",
                "CLOSING",
                True,
            ),
            (
                "J-KC8",
                "2026-08-31",
                2026,
                3,
                8,
                "2026-08",
                "6421",
                "EXPENSE",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(0),
                Decimal(40),
                Decimal(-40),
                "CLOSING",
                "CLOSING",
                True,
            ),
            (
                "J-KC8",
                "2026-08-31",
                2026,
                3,
                8,
                "2026-08",
                "6422",
                "EXPENSE",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(0),
                Decimal(45),
                Decimal(-45),
                "CLOSING",
                "CLOSING",
                True,
            ),
            (
                "J-KC8",
                "2026-08-31",
                2026,
                3,
                8,
                "2026-08",
                "8211",
                "EXPENSE",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(0),
                Decimal(45),
                Decimal(-45),
                "CLOSING",
                "CLOSING",
                True,
            ),
            (
                "J-KC8",
                "2026-08-31",
                2026,
                3,
                8,
                "2026-08",
                "4212",
                "EQUITY",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(0),
                Decimal(182),
                Decimal(-182),
                "CLOSING",
                "CLOSING",
                True,
            ),
            # Open month 2026-09
            (
                "J-REV9",
                "2026-09-10",
                2026,
                3,
                9,
                "2026-09",
                "11211",
                "ASSET",
                "C000002",
                "HN",
                "KD",
                "IT",
                None,
                Decimal(300),
                Decimal(0),
                Decimal(300),
                "INVOICE",
                "AR",
                False,
            ),
            (
                "J-REV9",
                "2026-09-10",
                2026,
                3,
                9,
                "2026-09",
                "5111",
                "REVENUE",
                "C000002",
                "HN",
                "KD",
                "IT",
                None,
                Decimal(0),
                Decimal(300),
                Decimal(-300),
                "INVOICE",
                "AR",
                False,
            ),
            (
                "J-515-9",
                "2026-09-15",
                2026,
                3,
                9,
                "2026-09",
                "11211",
                "ASSET",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(12),
                Decimal(0),
                Decimal(12),
                "INTEREST_INCOME",
                "CASH",
                False,
            ),
            (
                "J-515-9",
                "2026-09-15",
                2026,
                3,
                9,
                "2026-09",
                "515",
                "REVENUE",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(0),
                Decimal(12),
                Decimal(-12),
                "INTEREST_INCOME",
                "CASH",
                False,
            ),
            (
                "J-ADM9",
                "2026-09-18",
                2026,
                3,
                9,
                "2026-09",
                "6422",
                "EXPENSE",
                None,
                "HN",
                "HCNS",
                None,
                "VPP",
                Decimal(20),
                Decimal(0),
                Decimal(20),
                "BILL",
                "AP",
                False,
            ),
            (
                "J-ADM9",
                "2026-09-18",
                2026,
                3,
                9,
                "2026-09",
                "11211",
                "ASSET",
                None,
                "HN",
                "HCNS",
                None,
                "VPP",
                Decimal(0),
                Decimal(20),
                Decimal(-20),
                "BILL",
                "AP",
                False,
            ),
            (
                "J-B4-9",
                "2026-09-20",
                2026,
                3,
                9,
                "2026-09",
                "4219",
                "EQUITY",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(8),
                Decimal(0),
                Decimal(8),
                "PENALTY",
                "GL",
                False,
            ),
            (
                "J-B4-9",
                "2026-09-20",
                2026,
                3,
                9,
                "2026-09",
                "11211",
                "ASSET",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(0),
                Decimal(8),
                Decimal(-8),
                "PENALTY",
                "GL",
                False,
            ),
        ]
        con.executemany(
            "INSERT INTO v_mgmt VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            entries,
        )

        # P&L identities in 2026-08 (includes TK 515 = 25):
        # gross_profit = 500 - 200 = 300
        # operating_profit (VAS B02-DNN CT30) = 300 + 25 - 13 - 40 - 45 = 227
        # profit_before_tax = 227
        # ebitda = 227 + 10 (LOAN_INTEREST, excluding 3 BANK_FEE) + 15 (DEPRECIATION) = 252
        # net_profit = 227 - 45 = 182
        expected_aug = {
            "finance_income": Decimal("25.00"),
            "operating_profit": Decimal("227.00"),
            "profit_before_tax": Decimal("227.00"),
            "ebitda": Decimal("252.00"),
            "income_tax_expense": Decimal("45.00"),
            "net_profit": Decimal("182.00"),
        }
        for mid, exp in expected_aug.items():
            sql_g, params_g = _compile_governed_metric(mid, f"{mid} tháng 08/2026?")
            assert con.execute(sql_g, params_g).fetchone()[0] == exp, f"Governed {mid}"
            bound_t = _compile_t2s_metric(mid)
            assert con.execute(bound_t.sql, list(bound_t.params)).fetchone()[0] == exp, f"T2S {mid}"

        # Balance Sheet accounting equation on CLOSED month (2026-08-31) and OPEN month (2026-09-30):
        # 2026-08-31: Equity = 1000 + 182 = 1182 (ZERO closed-month double counting!), Liabilities = 40(335) + 30(338) + 45(3334) = 115, Assets = 1297
        # 2026-09-30: Equity = 1182 + 300 + 12 - 20 - 8 = 1466, Liabilities = 115, Assets = 1581
        for as_of_str, as_of_dt, exp_assets, exp_liab, exp_eq in (
            (
                "31/08/2026",
                date(2026, 8, 31),
                Decimal("1297.00"),
                Decimal("115.00"),
                Decimal("1182.00"),
            ),
            (
                "30/09/2026",
                date(2026, 9, 30),
                Decimal("1581.00"),
                Decimal("115.00"),
                Decimal("1466.00"),
            ),
        ):
            # Text2SQL snapshot metrics
            b_assets = _compile_t2s_metric(
                "total_assets", mode="as_of", start=None, end=None, as_of=as_of_dt
            )
            b_liab = _compile_t2s_metric(
                "total_liabilities", mode="as_of", start=None, end=None, as_of=as_of_dt
            )
            b_eq = _compile_t2s_metric("equity", mode="as_of", start=None, end=None, as_of=as_of_dt)
            t_assets = con.execute(b_assets.sql, list(b_assets.params)).fetchone()[0]
            t_liab = con.execute(b_liab.sql, list(b_liab.params)).fetchone()[0]
            t_eq = con.execute(b_eq.sql, list(b_eq.params)).fetchone()[0]
            assert (t_assets, t_liab, t_eq) == (exp_assets, exp_liab, exp_eq)
            assert t_assets == t_liab + t_eq

            # Governed catalog debt_to_equity = total_liabilities / equity
            sql_dte, params_dte = _compile_governed_metric(
                "debt_to_equity", f"debt_to_equity tính đến {as_of_str}?"
            )
            dte = con.execute(sql_dte, params_dte).fetchone()[0]
            assert abs(dte - (exp_liab / exp_eq)) <= Decimal("0.000001")


def test_salary_expense_includes_thuong_bonus() -> None:
    with duckdb.connect() as con:
        _create_ledger_table(con)
        rows = [
            (
                "J1",
                "2026-08-25",
                2026,
                3,
                8,
                "2026-08",
                "6421",
                "EXPENSE",
                None,
                "HN",
                "KD",
                None,
                "LUONG",
                Decimal(100000000),
                Decimal(0),
                Decimal(100000000),
                "PAYROLL",
                "HR",
                False,
            ),
            (
                "J2",
                "2026-08-25",
                2026,
                3,
                8,
                "2026-08",
                "6421",
                "EXPENSE",
                None,
                "HN",
                "KD",
                None,
                "THUONG",
                Decimal(40000000),
                Decimal(0),
                Decimal(40000000),
                "PAYROLL",
                "HR",
                False,
            ),
            (
                "J3",
                "2026-08-25",
                2026,
                3,
                8,
                "2026-08",
                "6422",
                "EXPENSE",
                None,
                "HN",
                "HCNS",
                None,
                "BAOHIEM",
                Decimal(22000000),
                Decimal(0),
                Decimal(22000000),
                "PAYROLL",
                "HR",
                False,
            ),
        ]
        con.executemany(
            "INSERT INTO v_mgmt VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

        sql_sal, params_sal = _compile_governed_metric(
            "salary_expense", "Chi phí lương tháng 08/2026?"
        )
        assert con.execute(sql_sal, params_sal).fetchone()[0] == Decimal("140000000.00")

        bound_sal = _compile_t2s_metric("salary_expense")
        assert con.execute(bound_sal.sql, list(bound_sal.params)).fetchone()[0] == Decimal(
            "140000000.00"
        )

        bound_total = _compile_t2s_metric("labor_cost")
        assert con.execute(bound_total.sql, list(bound_total.params)).fetchone()[0] == Decimal(
            "162000000.00"
        )


def test_partner_level_bilateral_ar_131_and_ap_331_no_cross_partner_netting() -> None:
    with duckdb.connect() as con:
        _create_ledger_table(con)
        # Balanced ledger as of 2026-08-31:
        # C000001 owes +100M on 131; C000002 paid customer advance -30M (credit 131)
        # V000001 owed +80M on 331; V000002 received supplier prepayment -20M (debit 331)
        # Bank 11211 = +100M; Capital 4111 = +110M (Dr: 100+20+100=220, Cr: 30+80+110=220)
        rows = [
            (
                "J1",
                "2026-08-05",
                2026,
                3,
                8,
                "2026-08",
                "131",
                "ASSET",
                "C000001",
                "HN",
                "KD",
                "IT",
                None,
                Decimal(100000000),
                Decimal(0),
                Decimal(100000000),
                "INVOICE",
                "AR",
                False,
            ),
            (
                "J2",
                "2026-08-06",
                2026,
                3,
                8,
                "2026-08",
                "131",
                "ASSET",
                "C000002",
                "HN",
                "KD",
                "IT",
                None,
                Decimal(0),
                Decimal(30000000),
                Decimal(-30000000),
                "CUSTOMER_ADVANCE",
                "AR",
                False,
            ),
            (
                "J3",
                "2026-08-07",
                2026,
                3,
                8,
                "2026-08",
                "331",
                "LIABILITY",
                "V000001",
                "HN",
                "MH",
                "IT",
                None,
                Decimal(0),
                Decimal(80000000),
                Decimal(-80000000),
                "BILL",
                "AP",
                False,
            ),
            (
                "J4",
                "2026-08-08",
                2026,
                3,
                8,
                "2026-08",
                "331",
                "LIABILITY",
                "V000002",
                "HN",
                "MH",
                "IT",
                None,
                Decimal(20000000),
                Decimal(0),
                Decimal(20000000),
                "PREPAYMENT",
                "AP",
                False,
            ),
            (
                "J5",
                "2026-08-01",
                2026,
                3,
                8,
                "2026-08",
                "11211",
                "ASSET",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(100000000),
                Decimal(0),
                Decimal(100000000),
                "OPENING",
                "OPENING",
                False,
            ),
            (
                "J5",
                "2026-08-01",
                2026,
                3,
                8,
                "2026-08",
                "4111",
                "EQUITY",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(0),
                Decimal(110000000),
                Decimal(-110000000),
                "OPENING",
                "OPENING",
                False,
            ),
        ]
        con.executemany(
            "INSERT INTO v_mgmt VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

        # Governed compiler (sql/compiler.py)
        ar_sql, ar_params = _compile_governed_metric(
            "ar_balance", "Công nợ phải thu khách hàng tính đến 31/08/2026?"
        )
        ap_sql, ap_params = _compile_governed_metric(
            "ap_balance", "Công nợ phải trả nhà cung cấp tính đến 31/08/2026?"
        )
        wc_sql, wc_params = _compile_governed_metric(
            "working_capital", "Vốn lưu động tính đến 31/08/2026?"
        )
        cr_sql, cr_params = _compile_governed_metric(
            "current_ratio", "Hệ số thanh toán hiện hành tính đến 31/08/2026?"
        )

        assert con.execute(ar_sql, ar_params).fetchone()[0] == Decimal("100000000.00")
        assert con.execute(ap_sql, ap_params).fetchone()[0] == Decimal("80000000.00")
        assert con.execute(wc_sql, wc_params).fetchone()[0] == Decimal("110000000.00")
        assert con.execute(cr_sql, cr_params).fetchone()[0] == Decimal("2.000000")

        # Text2SQL compiler (text2sql/compiler.py)
        as_of_dt = date(2026, 8, 31)
        b_ar = _compile_t2s_metric("ar_balance", mode="as_of", start=None, end=None, as_of=as_of_dt)
        b_ap = _compile_t2s_metric("ap_balance", mode="as_of", start=None, end=None, as_of=as_of_dt)
        b_cr = _compile_t2s_metric(
            "current_ratio", mode="as_of", start=None, end=None, as_of=as_of_dt
        )
        assert con.execute(b_ar.sql, list(b_ar.params)).fetchone()[0] == Decimal("100000000.00")
        assert con.execute(b_ap.sql, list(b_ap.params)).fetchone()[0] == Decimal("80000000.00")
        assert con.execute(b_cr.sql, list(b_cr.params)).fetchone()[0] == Decimal("2.000000")


def test_cash_flow_breakdown_vas24_categories_and_internal_transfer_exclusion() -> None:
    with duckdb.connect() as con:
        _create_ledger_table(con)
        rows = [
            # Customer advance: +50M bank -> customer_receipts
            (
                "J1",
                "2026-08-05",
                2026,
                3,
                8,
                "2026-08",
                "11211",
                "ASSET",
                "C000001",
                "HN",
                "KD",
                None,
                None,
                Decimal(50000000),
                Decimal(0),
                Decimal(50000000),
                "CUSTOMER_ADVANCE",
                "AR",
                False,
            ),
            # Loan drawdown: +200M bank -> financing
            (
                "J2",
                "2026-08-06",
                2026,
                3,
                8,
                "2026-08",
                "11211",
                "ASSET",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(200000000),
                Decimal(0),
                Decimal(200000000),
                "LOAN_DRAWDOWN",
                "LOAN",
                False,
            ),
            # Loan repayment: -80M bank -> financing
            (
                "J3",
                "2026-08-20",
                2026,
                3,
                8,
                "2026-08",
                "11211",
                "ASSET",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(0),
                Decimal(80000000),
                Decimal(-80000000),
                "LOAN_REPAYMENT",
                "LOAN",
                False,
            ),
            # Internal cash transfer 111 <-> 112: must be excluded per VAS 24!
            (
                "J4",
                "2026-08-22",
                2026,
                3,
                8,
                "2026-08",
                "1111",
                "ASSET",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(30000000),
                Decimal(0),
                Decimal(30000000),
                "CASH_TRANSFER",
                "CASH",
                False,
            ),
            (
                "J4",
                "2026-08-22",
                2026,
                3,
                8,
                "2026-08",
                "11211",
                "ASSET",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(0),
                Decimal(30000000),
                Decimal(-30000000),
                "CASH_TRANSFER",
                "CASH",
                False,
            ),
        ]
        con.executemany(
            "INSERT INTO v_mgmt VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

        sql = (
            "WITH period AS (SELECT ?::DATE AS start_date, ?::DATE AS end_date) "
            + METRIC_QUERIES["cash_flow_breakdown"].sql
        )
        by_cat = dict(con.execute(sql, [date(2026, 8, 1), date(2026, 8, 31)]).fetchall())
        assert by_cat == {
            "financing": Decimal("120000000.00"),
            "customer_receipts": Decimal("50000000.00"),
        }
        assert "other" not in by_cat

        net_cf_bound = _compile_t2s_metric("net_cash_flow")
        net_cf = con.execute(net_cf_bound.sql, list(net_cf_bound.params)).fetchone()[0]
        assert sum(by_cat.values(), Decimal("0.00")) == net_cf == Decimal("170000000.00")


# ===========================================================================
# Prompt 2 + Subagent #1 — Text2SQL Selector, vat_position, & DuckDB Sandbox
# ===========================================================================


def test_offline_semantic_selector_filters_clarifications_and_comparison_guard() -> None:
    snap = CatalogSnapshot()
    selector = OfflineSemanticSelector(snap)
    t2s_auth = T2SAuthContext(
        user_id="cfo-1",
        tenant_id="minh-phat",
        roles=frozenset({"cfo", "finance_analyst"}),
        allowed_views=frozenset({"mgmt", "tax"}),
    )

    # Multi-filter extraction (MPX10 branch NA + customer C000042)
    d1 = selector.select("Doanh thu thuần chi nhánh NA của khách hàng C000042 tháng 08/2026?")
    assert d1.status == "ready"
    assert d1.metric_ids == ["net_revenue"]
    assert {(f.field, tuple(f.values)) for f in d1.filters} == {
        ("branch", ("NA",)),
        ("customer", ("C000042",)),
    }

    # Department IT vs Product line IT disambiguation
    d_dept = selector.select("Chi phí hoạt động phòng IT tháng 08/2026?")
    assert d_dept.status == "ready"
    assert [(f.field, f.values) for f in d_dept.filters] == [("department", ["IT"])]

    d_prod = selector.select("Doanh thu dòng sản phẩm thiết bị CNTT tháng 08/2026?")
    assert d_prod.status == "ready"
    assert [(f.field, f.values) for f in d_prod.filters] == [("product_line", ["IT"])]

    # Unknown branch fails closed to needs_clarification (never drops filter!)
    d_unknown = selector.select("Doanh thu thuần chi nhánh Hải Dương tháng 08/2026?")
    assert d_unknown.status == "needs_clarification"

    # Period-over-period comparison rejected as unsupported_comparison
    for q in (
        "Doanh thu thuần tháng 09/2026 so với tháng 08/2026?",
        "Tăng trưởng lãi gộp quý 3/2026 cùng kỳ năm trước?",
        "Compare net revenue Q3 2026 vs Q2 2026?",
    ):
        d_cmp = selector.select(q)
        assert d_cmp.status == "unsupported"
        assert d_cmp.reason_code == "unsupported_comparison"

    # Incompatible filter on a metric that does not support that dimension fails closed in SemanticValidator
    incompatible = SemanticPlanDraft(
        plan_version="1.0",
        status="ready",
        metric_ids=["cash_and_equivalents"],
        time=TimeDraft.as_of_date(date(2026, 8, 31)),
        dimensions=[],
        filters=[FilterDraft(field="cost_category", operator="eq", values=["LUONG"])],
        view="mgmt",
        operation="aggregate",
        sort=None,
        top_k=None,
        comparison=None,
        question_for_user=None,
        unresolved_slots=[],
        reason_code=None,
    )
    with pytest.raises(PlanRejected) as exc_info:
        SemanticValidator(snap).validate(incompatible, t2s_auth)
    assert exc_info.value.code == "unsupported_filter"


def test_vat_position_excludes_settlement_and_payment_journals_while_preserving_b4() -> None:
    with duckdb.connect() as con:
        _create_ledger_table(con, "v_tax")
        rows = [
            # Output VAT on sales invoice: 33311 credit 50M
            (
                "J1",
                "2026-09-10",
                2026,
                3,
                9,
                "2026-09",
                "33311",
                "LIABILITY",
                "C000001",
                "HN",
                "KD",
                None,
                None,
                Decimal(0),
                Decimal(50000000),
                Decimal(-50000000),
                "INVOICE",
                "AR",
                False,
            ),
            # Deductible input VAT on purchase bill: 1331 debit 20M
            (
                "J2",
                "2026-09-12",
                2026,
                3,
                9,
                "2026-09",
                "1331",
                "ASSET",
                "V000001",
                "HN",
                "MH",
                None,
                None,
                Decimal(20000000),
                Decimal(0),
                Decimal(20000000),
                "BILL",
                "AP",
                False,
            ),
            # VAT offset & payment journals in period: MUST NOT zero out period VAT generated!
            (
                "J3",
                "2026-09-30",
                2026,
                3,
                9,
                "2026-09",
                "33311",
                "LIABILITY",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(20000000),
                Decimal(0),
                Decimal(20000000),
                "VAT_OFFSET",
                "TAX",
                False,
            ),
            (
                "J3",
                "2026-09-30",
                2026,
                3,
                9,
                "2026-09",
                "1331",
                "ASSET",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(0),
                Decimal(20000000),
                Decimal(-20000000),
                "VAT_OFFSET",
                "TAX",
                False,
            ),
            (
                "J4",
                "2026-09-30",
                2026,
                3,
                9,
                "2026-09",
                "33311",
                "LIABILITY",
                None,
                "HN",
                "TCKT",
                None,
                None,
                Decimal(30000000),
                Decimal(0),
                Decimal(30000000),
                "VAT_PAYMENT",
                "TAX",
                False,
            ),
        ]
        con.executemany(
            "INSERT INTO v_tax VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

        bound = _compile_t2s_metric(
            "vat_position",
            view="tax",
            start=date(2026, 9, 1),
            end=date(2026, 9, 30),
        )
        net_vat_scalar = con.execute(bound.sql, list(bound.params)).fetchone()[0]
        assert net_vat_scalar == Decimal("30000000.00")

        mq_sql = (
            "WITH period AS (SELECT ?::DATE AS start_date, ?::DATE AS end_date) "
            + METRIC_QUERIES["vat_position"].sql
        )
        mq_rows = dict(con.execute(mq_sql, [date(2026, 9, 1), date(2026, 9, 30)]).fetchall())
        assert mq_rows == {
            "output_vat": Decimal("50000000.00"),
            "input_vat": Decimal("20000000.00"),
            "net_vat": Decimal("30000000.00"),
        }


@pytest.mark.parametrize(
    "malicious_sql",
    [
        "SELECT * FROM v_mgmt, ground_truth",
        "SELECT a.debit_amount FROM (SELECT * FROM v_mgmt) a, secret_table b",
        'SELECT * FROM "ground_truth"',
        "SELECT * FROM main.ground_truth",
        "SELECT * FROM memory.v_mgmt",
        "SELECT * FROM read_csv('C:/Windows/win.ini')",
        "SELECT * FROM read_csv_auto('secret.csv')",
        "SELECT * FROM read_parquet('dump.parquet')",
        "SELECT * FROM parquet_scan('dump.parquet')",
        "SELECT * FROM read_json('dump.json')",
        "SELECT * FROM iceberg_scan('tbl')",
        "SELECT * FROM sqlite_scan('db.sqlite', 'users')",
        "SELECT * FROM glob('*')",
        "SELECT * FROM pragma_database_list()",
        "SELECT * FROM duckdb_tables()",
        "SELECT /* hidden */ 1 FROM v_mgmt",
        "SELECT 1 FROM v_mgmt -- trailing comment",
        "SELECT 1 FROM v_mgmt; SELECT 2 FROM v_mgmt",
        "SELECT * FROM v_mgmt CROSS JOIN ar_invoice",
        "SELECT * FROM v_mgmt NATURAL JOIN ar_invoice",
    ],
)
def test_assert_safe_select_blocks_injection_comma_joins_and_file_scans(malicious_sql: str) -> None:
    with pytest.raises(UnsafeQuery):
        assert_safe_select(malicious_sql)


def test_duckdb_read_only_executor_disables_writes_and_external_access(tmp_path: Path) -> None:
    db_file = tmp_path / "sandbox.duckdb"
    csv_file = tmp_path / "leak.csv"
    csv_file.write_text("col\nsecret\n", encoding="utf-8")
    with duckdb.connect(str(db_file)) as setup_con:
        setup_con.execute("CREATE TABLE v_mgmt (x INTEGER)")
        setup_con.execute("INSERT INTO v_mgmt VALUES (42)")
        setup_con.execute("CREATE TABLE company_info (key VARCHAR, value VARCHAR)")
        setup_con.execute("INSERT INTO company_info VALUES ('as_of_date', '2026-10-14')")

    with _connect_read_only(db_file) as ro_con:
        with pytest.raises(duckdb.Error):
            ro_con.execute("INSERT INTO v_mgmt VALUES (99)")
        with pytest.raises(duckdb.Error):
            ro_con.execute(f"SELECT * FROM read_csv_auto('{csv_file.as_posix()}')")

    executor = DuckDBReadOnlyExecutor(db_file)
    assert executor.ready() is True


# ===========================================================================
# Prompt 3 — MPX10 Entities, _UNSAFE_OUTPUT Sanitizer, & Relative VN Time
# ===========================================================================


@pytest.mark.parametrize("branch_code", ["HN", "HCM", "DN", "HP", "BD", "CT", "NA"])
def test_mpx10_all_seven_branches_accepted_by_planner_and_validator(branch_code: str) -> None:
    catalog = MetricCatalog()
    auth = _cfo_auth()
    selection = {
        "status": "validated",
        "metric_ids": ["net_revenue"],
        "catalog_hash": catalog.get_catalog_hash(),
        "validated_capabilities": {"net_revenue": catalog.get_capability("net_revenue")},
    }
    intake = query_intake(
        {
            "api_version": "v1",
            "locale": "vi-VN",
            "question": f"Doanh thu thuần của chi nhánh {branch_code} tháng 08/2026?",
        }
    )
    draft = build_semantic_plan_draft(intake, selection, {})
    assert draft["status"] == "ready"
    plan = validate_semantic_plan_draft(draft, selection, catalog, auth)
    assert [(f.field, f.op, f.value) for f in plan.filters] == [("branch_code", "=", branch_code)]


@pytest.mark.parametrize(
    "dept_code",
    ["BGD", "KD", "MKT", "KT", "KHO", "TCKT", "HCNS", "IT", "CSKH", "MH", "KSNB"],
)
def test_mpx10_all_eleven_departments_accepted_by_planner_and_validator(dept_code: str) -> None:
    catalog = MetricCatalog()
    auth = _cfo_auth()
    selection = {
        "status": "validated",
        "metric_ids": ["operating_expenses"],
        "catalog_hash": catalog.get_catalog_hash(),
        "validated_capabilities": {
            "operating_expenses": catalog.get_capability("operating_expenses")
        },
    }
    intake = query_intake(
        {
            "api_version": "v1",
            "locale": "vi-VN",
            "question": f"Chi phí hoạt động của phòng {dept_code} tháng 08/2026?",
        }
    )
    draft = build_semantic_plan_draft(intake, selection, {})
    assert draft["status"] == "ready"
    plan = validate_semantic_plan_draft(draft, selection, catalog, auth)
    assert [(f.field, f.op, f.value) for f in plan.filters] == [("department_code", "=", dept_code)]


def test_mpx10_partner_codes_and_hp_it_disambiguation() -> None:
    catalog = MetricCatalog()
    auth = _cfo_auth()
    sel_rev = {
        "status": "validated",
        "metric_ids": ["net_revenue"],
        "catalog_hash": catalog.get_catalog_hash(),
        "validated_capabilities": {"net_revenue": catalog.get_capability("net_revenue")},
    }
    # Customer C000123
    q_cust = query_intake(
        {
            "api_version": "v1",
            "locale": "vi-VN",
            "question": "Doanh thu thuần khách hàng C000123 tháng 08/2026?",
        }
    )
    plan_cust = validate_semantic_plan_draft(
        build_semantic_plan_draft(q_cust, sel_rev, {}), sel_rev, catalog, auth
    )
    assert [(f.field, f.op, f.value) for f in plan_cust.filters] == [
        ("partner_code", "=", "C000123")
    ]

    # Vendor V000045
    sel_ap = {
        "status": "validated",
        "metric_ids": ["ap_balance"],
        "catalog_hash": catalog.get_catalog_hash(),
        "validated_capabilities": {"ap_balance": catalog.get_capability("ap_balance")},
    }
    q_vend = query_intake(
        {
            "api_version": "v1",
            "locale": "vi-VN",
            "question": "Công nợ phải trả nhà cung cấp V000045 tính đến 31/08/2026?",
        }
    )
    plan_vend = validate_semantic_plan_draft(
        build_semantic_plan_draft(q_vend, sel_ap, {}), sel_ap, catalog, auth
    )
    assert [(f.field, f.op, f.value) for f in plan_vend.filters] == [
        ("partner_code", "=", "V000045")
    ]

    # "Laptop HP" must NOT falsely trigger branch_code = "HP"
    q_laptop = query_intake(
        {
            "api_version": "v1",
            "locale": "vi-VN",
            "question": "Doanh thu bán Laptop HP tháng 08/2026?",
        }
    )
    draft_laptop = build_semantic_plan_draft(q_laptop, sel_rev, {})
    assert draft_laptop["filters"] == []


def test_llm_selector_sanitizer_allows_vietnamese_finance_phrases_and_blocks_unsafe_tokens() -> (
    None
):
    for safe_clarification in (
        "Bạn muốn tra cứu kỳ 10-2026 hay Q3/2026?",
        "Bạn cần số liệu theo sổ quản trị - thuế nào?",
        "Bạn muốn xem tổng thu / chi hay dòng tiền ròng giai đoạn 2025-2026?",
    ):
        checked = validate_llm_selection_draft(
            {
                "status": "ambiguous",
                "metric_ids": [],
                "clarification_question": safe_clarification,
                "unsupported_reason": None,
            }
        )
        assert checked["clarification_question"] == safe_clarification

    for unsafe_text in (
        "Tính bằng 511-521",
        "Lấy net_revenue / cogs",
        "SELECT * FROM v_mgmt",
        "Dùng hàm SUM(credit_amount)",
        "Tra cứu TK 511",
    ):
        with pytest.raises(ContractError):
            validate_llm_selection_draft(
                {
                    "status": "ambiguous",
                    "metric_ids": [],
                    "clarification_question": unsafe_text,
                    "unsupported_reason": None,
                }
            )


@pytest.mark.parametrize(
    ("phrase", "ref_date", "period_type", "expected"),
    [
        (
            "Doanh thu tháng này?",
            "2026-10-14",
            "flow",
            ("range", "month", "2026-10-01", "2026-10-31", None),
        ),
        (
            "Số dư tiền tháng này?",
            "2026-10-14",
            "snapshot",
            ("as_of", None, None, None, "2026-10-14"),
        ),
        (
            "Doanh thu tháng trước?",
            "2026-10-14",
            "flow",
            ("range", "month", "2026-09-01", "2026-09-30", None),
        ),
        (
            "Doanh thu tháng trước?",
            "2026-01-15",
            "flow",
            ("range", "month", "2025-12-01", "2025-12-31", None),
        ),
        (
            "Doanh thu quý này?",
            "2026-10-14",
            "flow",
            ("range", "quarter", "2026-10-01", "2026-12-31", None),
        ),
        (
            "Doanh thu quý trước?",
            "2026-10-14",
            "flow",
            ("range", "quarter", "2026-07-01", "2026-09-30", None),
        ),
        (
            "Doanh thu quý trước?",
            "2026-02-10",
            "flow",
            ("range", "quarter", "2025-10-01", "2025-12-31", None),
        ),
        (
            "Doanh thu năm nay?",
            "2026-10-14",
            "flow",
            ("range", "year", "2026-01-01", "2026-12-31", None),
        ),
        (
            "Doanh thu năm ngoái?",
            "2026-10-14",
            "flow",
            ("range", "year", "2025-01-01", "2025-12-31", None),
        ),
        (
            "Doanh thu cùng kỳ?",
            "2026-10-14",
            "flow",
            ("range", "month", "2025-10-01", "2025-10-31", None),
        ),
        (
            "Doanh thu 6 tháng đầu năm?",
            "2026-10-14",
            "flow",
            ("range", "month", "2026-01-01", "2026-06-30", None),
        ),
        (
            "Doanh thu từ đầu năm đến nay?",
            "2026-10-14",
            "flow",
            ("range", "month", "2026-01-01", "2026-10-14", None),
        ),
    ],
)
def test_deterministic_reference_date_anchored_vietnamese_relative_time(
    phrase: str,
    ref_date: str,
    period_type: str,
    expected: tuple[str, str, str | None, str | None, str | None],
) -> None:
    slot = parse_time_slot(phrase, period_type=period_type, reference_date=ref_date)
    assert (slot["mode"], slot["grain"], slot["start"], slot["end"], slot["as_of"]) == expected

    # Without reference_date, relative periods must NEVER call wall-clock date.today()
    no_ref = parse_time_slot(phrase, period_type=period_type, reference_date=None)
    assert no_ref["mode"] == "none"


# ===========================================================================
# Prompt 4 + Subagent #3 — Async Safety, Answer Grounding, Offline & Config
# ===========================================================================


@pytest.mark.asyncio
async def test_openai_embedding_runs_in_worker_thread_without_blocking_event_loop(
    tmp_path: Path,
) -> None:
    catalog = MetricCatalog()
    auth = _cfo_auth()

    def slow_embed(request: httpx.Request) -> httpx.Response:
        time.sleep(0.15)
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [0.125] * 64}]},
        )

    emb_cfg = EmbeddingConfig(
        provider="openai",
        base_url="http://localhost:11434/v1",
        model="local-embed",
        dimensions=64,
        cache_enabled=False,
        cache_path=tmp_path / "idx.npz",
    )
    provider = EmbeddingProvider(emb_cfg, transport=httpx.MockTransport(slow_embed))
    # Pre-build index quickly with mock non-sleeping transport
    fast_provider = EmbeddingProvider(
        emb_cfg,
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={
                    "data": [
                        {"index": i, "embedding": [0.125] * 64}
                        for i in range(len(catalog.list_approved_metrics()))
                    ]
                },
            )
        ),
    )
    from agent4.metric_selection.index import build_index

    index = build_index(catalog, fast_provider, tmp_path / "idx.npz")

    cfg = MetricSelectionConfig(
        embedding=emb_cfg,
        retrieval=RetrievalConfig(mode="hybrid", dense_enabled=True, lexical_enabled=True),
        llm=LLMSelectionConfig(provider="mock"),
    )
    ticks = 0
    running = True

    async def heartbeat() -> None:
        nonlocal ticks
        while running:
            await asyncio.sleep(0.015)
            ticks += 1

    hb_task = asyncio.create_task(heartbeat())
    try:
        res = await select_metrics_with_recovery(
            query_intake(
                {
                    "api_version": "v1",
                    "locale": "vi-VN",
                    "question": "Doanh thu thuần tháng 08/2026?",
                }
            ),
            catalog,
            auth_context=auth,
            config=cfg,
            embedding_provider=provider,
            index=index,
        )
    finally:
        running = False
        await hb_task

    assert res["status"] == "validated"
    # Event loop ticked multiple times during the 150ms synchronous embedding call
    assert ticks >= 3


@pytest.mark.asyncio
async def test_offline_ollama_falls_back_to_governed_lexical_selector_preserving_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = MetricCatalog()
    auth = _cfo_auth()

    def raise_connect_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    orig_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: orig_async_client(transport=httpx.MockTransport(raise_connect_error), **kw),
    )

    cfg = load_config()
    assert cfg.recovery.degraded_lexical_fallback is True
    assert cfg.recovery.llm_lexical_fallback is True

    question = "Doanh thu thuần chi nhánh NA của khách hàng C000012 tháng 08/2026?"
    intake = query_intake({"api_version": "v1", "locale": "vi-VN", "question": question})
    selected = await select_metrics_with_recovery(
        intake,
        catalog,
        auth_context=auth,
        config=cfg,
        selector=LLMMetricSelector(cfg.llm),
    )
    assert selected["status"] == "validated"
    assert selected["metric_ids"] == ["net_revenue"]
    assert selected["recovery_triggered"] is True
    assert selected["recovery_reason"] == "llm_unavailable"

    # Full M2 planner preserves branch NA and partner C000012 filters!
    draft = build_semantic_plan_draft(intake, selected, {})
    sealed = validate_semantic_plan_draft(draft, selected, catalog, auth)
    assert [(f.field, f.op, f.value) for f in sealed.filters] == [
        ("branch_code", "=", "NA"),
        ("partner_code", "=", "C000012"),
    ]

    # Ambiguous bare query ("Lợi nhuận?") degrades cleanly to ambiguous -> needs_clarification
    ambig_intake = query_intake({"api_version": "v1", "locale": "vi-VN", "question": "Lợi nhuận?"})
    ambig_sel = await select_metrics_with_recovery(
        ambig_intake,
        catalog,
        auth_context=auth,
        config=cfg,
        selector=LLMMetricSelector(cfg.llm),
    )
    assert ambig_sel["status"] == "needs_clarification"


def test_safe_display_text_returns_nfkc_normalized_and_strips_zero_width_cf() -> None:
    raw = "Ｃông\u200b ty\ufeff Minh\u200d Phát\u202e"
    assert safe_display_text(raw) == "Công ty Minh Phát"


def test_answer_validator_enforces_numeric_accuracy_and_strict_sign_consistency() -> None:
    catalog = MetricCatalog()
    auth = _cfo_auth()
    selection = {
        "status": "validated",
        "metric_ids": ["net_profit"],
        "catalog_hash": catalog.get_catalog_hash(),
        "validated_capabilities": {"net_profit": catalog.get_capability("net_profit")},
    }
    intake = query_intake(
        {"api_version": "v1", "locale": "vi-VN", "question": "Lợi nhuận ròng tháng 08/2026?"}
    )
    plan = validate_semantic_plan_draft(
        build_semantic_plan_draft(intake, selection, {}), selection, catalog, auth
    )
    validated_result = {
        "status": "ok",
        "warnings": [],
        "result": {
            "columns": [{"key": "net_profit", "type": "decimal", "unit": "VND"}],
            "rows": [{"net_profit": "-666387909.00"}],
            "row_count": 1,
            "truncated": False,
            "data_watermark": "2026-10-14",
        },
    }

    # 1. Valid custom grounded negative prose is accepted WITHOUT fallback!
    good_draft = {
        "summary": "Lợi nhuận ròng kỳ 08/2026 ghi nhận âm 666.387.909 đồng (lỗ khoảng 666,4 triệu đồng).",
        "claims": [
            {
                "text": "Lợi nhuận ròng: -666.387.909 đồng",
                "source_columns": ["net_profit"],
                "source_rows": [0],
            }
        ],
        "warnings": [],
        "table_caption": None,
    }
    checked_good = validate_answer(good_draft, validated_result, plan, catalog, locale="vi-VN")
    assert checked_good["used_fallback"] is False
    assert "-666.387.909" in checked_good["answer"] or "âm 666.387.909" in checked_good["answer"]

    # 2. Sign-flip bug ("-666.387.909 đồng (khoảng 666,4 triệu đồng)" — positive parenthetical!) MUST fail!
    sign_flipped_parenthetical = {
        "summary": "Lợi nhuận ròng kỳ 08/2026 là -666.387.909 đồng (khoảng 666,4 triệu đồng).",
        "claims": [
            {
                "text": "Lợi nhuận ròng: -666.387.909 đồng",
                "source_columns": ["net_profit"],
                "source_rows": [0],
            }
        ],
        "warnings": [],
        "table_caption": None,
    }
    with pytest.raises(ContractError) as exc_flip:
        validate_answer(
            sign_flipped_parenthetical,
            validated_result,
            plan,
            catalog,
            locale="vi-VN",
            fallback_on_failure=False,
        )
    assert exc_flip.value.code == "ungrounded_answer"

    fallback_res = validate_answer(
        sign_flipped_parenthetical, validated_result, plan, catalog, locale="vi-VN"
    )
    assert fallback_res["used_fallback"] is True

    # 3. Hallucinated magnitude MUST fail!
    hallucinated = {
        "summary": "Lợi nhuận ròng kỳ 08/2026 là -500.000.000 đồng.",
        "claims": [
            {
                "text": "Lợi nhuận ròng: -500.000.000 đồng",
                "source_columns": ["net_profit"],
                "source_rows": [0],
            }
        ],
        "warnings": [],
        "table_caption": None,
    }
    with pytest.raises(ContractError):
        validate_answer(
            hallucinated,
            validated_result,
            plan,
            catalog,
            locale="vi-VN",
            fallback_on_failure=False,
        )


def test_local_first_selection_yaml_cloud_separation_and_dual_env_vars(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for key in (
        "AGENT4_SELECTION_CONFIG",
        "AGENT4_METRIC_SELECTION_CONFIG",
        "AGENT4_LLM_BASE_URL",
        "AGENT4_EMBED_BASE_URL",
        "AGENT4_LLM_PROVIDER",
        "AGENT4_EMBED_PROVIDER",
    ):
        monkeypatch.delenv(key, raising=False)

    default_cfg = load_config(DEFAULT_CONFIG_PATH)
    assert urlparse(default_cfg.embedding.base_url).hostname in ("localhost", "127.0.0.1")
    assert urlparse(default_cfg.llm.base_url).hostname in ("localhost", "127.0.0.1")
    assert default_cfg.llm.provider == "ollama"
    assert default_cfg.recovery.degraded_lexical_fallback is True
    assert default_cfg.recovery.llm_lexical_fallback is True

    cloud_path = PROJECT_DIR / "config" / "selection_cloud.yaml"
    assert cloud_path.is_file()
    cloud_cfg = load_config(cloud_path)
    assert cloud_cfg.llm.provider == "openai"

    custom_cfg_path = tmp_path / "custom_selection.yaml"
    custom_cfg_path.write_text(
        yaml.safe_dump({"llm": {"provider": "mock", "model": "local-mock"}}),
        encoding="utf-8",
    )

    monkeypatch.setenv("AGENT4_SELECTION_CONFIG", str(custom_cfg_path))
    assert AppConfig().selection_config_path == custom_cfg_path
    assert load_config().llm.model == "local-mock"

    monkeypatch.delenv("AGENT4_SELECTION_CONFIG")
    monkeypatch.setenv("AGENT4_METRIC_SELECTION_CONFIG", str(custom_cfg_path))
    assert AppConfig().selection_config_path == custom_cfg_path
    assert load_config().llm.model == "local-mock"


@pytest.mark.asyncio
async def test_governed_pipeline_offline_ollama_and_relative_vietnamese_time_e2e(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from agent4.pipeline import run_governed_pipeline

    db_path = tmp_path / "e2e_offline.duckdb"
    with duckdb.connect(str(db_path)) as con:
        _create_ledger_table(con)
        con.execute("CREATE TABLE company_info (key VARCHAR, value VARCHAR)")
        con.execute(
            "INSERT INTO company_info VALUES ('as_of_date', '2026-10-14'), ('last_closed_month', '2026-08')"
        )
        con.execute(
            "INSERT INTO v_mgmt VALUES "
            "('J1', DATE '2026-09-15', 2026, 3, 9, '2026-09', '5111', 'REVENUE', 'C000088', 'NA', 'KD', 'IT', NULL, 0, 75000000, -75000000, 'INVOICE', 'AR', FALSE), "
            "('J1', DATE '2026-09-15', 2026, 3, 9, '2026-09', '131', 'ASSET', 'C000088', 'NA', 'KD', 'IT', NULL, 75000000, 0, 75000000, 'INVOICE', 'AR', FALSE)"
        )

    def raise_connect_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Ollama offline", request=request)

    orig_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: orig_async_client(transport=httpx.MockTransport(raise_connect_error), **kw),
    )

    resp = await run_governed_pipeline(
        {
            "api_version": "v1",
            "locale": "vi-VN",
            "question": "Doanh thu thuần chi nhánh NA của khách hàng C000088 tháng trước?",
        },
        _CFO_CLAIMS,
        _CFO_POLICY,
        warehouses={"minh-phat": db_path},
        selection_config=load_config(DEFAULT_CONFIG_PATH),
    )
    assert resp["status"] == "ready", resp
    assert resp["data"]["rows"] == [{"net_revenue": "75000000.00"}]
    assert resp["interpretation"]["time"] == {
        "mode": "range",
        "grain": "month",
        "start": "2026-09-01",
        "end": "2026-09-30",
        "as_of": None,
    }
