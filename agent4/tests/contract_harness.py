"""Contract-first reference harness implementing the 25 Module Contracts from contracts.md
and the product workflow from scope.md, backed by data/cfo_warehouse.duckdb.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import math
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "cfo_warehouse.duckdb"
GROUND_TRUTH_PATH = REPO_ROOT / "data" / "cfo_warehouse_ground_truth.json"

SUPPORTED_LOCALES = {"vi-VN", "en-US"}
COMMON_STATUSES = {"ok", "needs_clarification", "unsupported", "forbidden", "rejected", "unavailable"}
FINAL_STATUSES = {
    "ready",
    "needs_clarification",
    "unsupported",
    "forbidden",
    "no_data",
    "temporarily_unavailable",
    "error",
}
ALLOWED_RELATIONS = {
    "v_mgmt",
    "v_tax",
    "v_gl",
    "ar_invoice",
    "ar_receipt",
    "ap_bill",
    "ap_payment",
    "budget",
    "payroll",
    "loan",
    "fixed_asset",
    "inventory_txn",
    "period_close",
    "dim_partner",
    "dim_branch",
    "dim_product_line",
    "dim_department",
    "dim_cost_category",
}
ALLOWED_DIMENSIONS = {
    "month",
    "quarter",
    "year",
    "branch_code",
    "product_line",
    "department_code",
    "cost_category",
    "partner_code",
    "segment",
}
ALLOWED_FILTER_FIELDS = {
    "branch_code": {"HN", "HCM", "DN"},
    "product_line": {"IT", "OFF", "CON", "SVC"},
    "department_code": {"BGD", "KD", "MKT", "KT", "KHO", "TCKT", "HCNS"},
    "cost_category": {
        "LUONG",
        "BAOHIEM",
        "THUONG",
        "THUE_MB",
        "DIEN_NUOC",
        "VIENTHONG",
        "MARKETING",
        "VANCHUYEN",
        "CONGTAC",
        "TIEPKHACH",
        "KHAUHAO",
        "PHANMEM",
        "VPP",
        "BAOHIEM_TS",
        "PHI_NH",
        "DUPHONG",
        "VATTU_DV",
        "THUE_PHI",
        "KHAC",
    },
    "segment": {"GOV", "SME", "DLR", "RET", "ENT"},
    "partner_code": None,  # Validated against alphanumeric pattern
}
ALLOWED_OPERATORS = {"=", "IN"}
FORBIDDEN_SQL_PATTERNS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|COPY|ATTACH|DETACH|PRAGMA|CREATE|REPLACE|TRUNCATE|GRANT|REVOKE|CALL|EXPORT|IMPORT|LOAD|INSTALL)\b",
    re.IGNORECASE,
)
CAUSAL_SPECULATION_PATTERNS = re.compile(
    r"\b(nắng nóng|sự kiện ra mắt|chiến dịch bổ sung|tăng giá|do thời tiết|because of weather|due to launch event)\b",
    re.IGNORECASE,
)
INJECTION_PATTERNS = re.compile(
    r"(ignore\s+(all\s+)?previous\s+instructions|system\s+note\s+to\s+ai|bỏ\s+qua\s+mọi\s+quy\s+tắc|drop\s+table|select\s+\*\s+from\s+payroll)",
    re.IGNORECASE,
)


class ContractError(Exception):
    """Structured contract error adhering to Section 1.3 of contracts.md."""

    def __init__(
        self,
        code: str,
        stage: str,
        message: str,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
        final_status: str = "error",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.message = self._sanitize_message(message)
        self.retryable = bool(retryable)
        self.details = self._sanitize_details(details or {})
        self.final_status = final_status if final_status in FINAL_STATUSES else "error"

    @staticmethod
    def _sanitize_message(msg: str) -> str:
        # Section 1.1: Public error must not contain raw SQL, stack trace, credentials, or raw financial rows.
        sanitized = re.sub(r"(SELECT|WITH|INSERT|UPDATE|DELETE|DROP)\s+.*", "[REDACTED]", msg, flags=re.IGNORECASE)
        sanitized = re.sub(r"Traceback \(most recent call last\).*", "[REDACTED]", sanitized, flags=re.DOTALL)
        sanitized = re.sub(r"(password|secret|token|api_key)\s*=\s*\S+", "[REDACTED]", sanitized, flags=re.IGNORECASE)
        return sanitized

    @classmethod
    def _sanitize_details(cls, details: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        forbidden_keys = {"sql", "raw_sql", "stack_trace", "traceback", "credentials", "password", "rows", "raw_rows"}
        for k, v in details.items():
            if k.lower() in forbidden_keys:
                continue
            if isinstance(v, str):
                clean[k] = cls._sanitize_message(v)
            else:
                clean[k] = v
        return clean

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "stage": self.stage,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }


def enforce_exact_keys(
    obj: dict[str, Any],
    required_keys: set[str],
    optional_keys: set[str] | None = None,
    stage: str = "boundary",
) -> None:
    """Section 1.1: Unknown field must be rejected at module boundaries."""
    if not isinstance(obj, dict):
        raise ContractError("invalid_request", stage, "Input payload must be a JSON object.", final_status="error")
    allowed = required_keys | (optional_keys or set())
    unknown = set(obj.keys()) - allowed
    if unknown:
        raise ContractError(
            "invalid_request",
            stage,
            f"Unknown fields rejected at boundary: {sorted(unknown)}",
            details={"unknown_fields": sorted(unknown)},
            final_status="error",
        )
    missing = required_keys - set(obj.keys())
    if missing:
        raise ContractError(
            "invalid_request",
            stage,
            f"Missing required fields at boundary: {sorted(missing)}",
            details={"missing_fields": sorted   (missing)},
            final_status="error",
        )


# =====================================================================
# Contract 2: Query Intake (query.intake.v1)
# =====================================================================
def query_intake(payload: dict[str, Any], max_question_length: int = 500) -> dict[str, Any]:
    stage = "query_intake"
    enforce_exact_keys(
        payload,
        required_keys={"api_version", "question", "locale"},
        optional_keys={"session_id", "options"},
        stage=stage,
    )
    if payload["api_version"] != "v1":
        raise ContractError("invalid_request", stage, "Unsupported api_version.", final_status="error")

    question = payload["question"]
    if not isinstance(question, str) or not question.strip():
        raise ContractError("invalid_request", stage, "Question must be a non-empty string.", final_status="error")
    if len(question) > max_question_length:
        raise ContractError(
            "question_too_long",
            stage,
            f"Question exceeds maximum length of {max_question_length} characters.",
            final_status="error",
        )

    locale = payload["locale"]
    if locale not in SUPPORTED_LOCALES:
        raise ContractError(
            "unsupported_locale",
            stage,
            f"Locale '{locale}' is not supported.",
            details={"locale": locale},
            final_status="unsupported",
        )

    options_in = payload.get("options") or {"include_table": True, "explain_metrics": True}
    enforce_exact_keys(
        options_in,
        required_keys=set(),
        optional_keys={"include_table", "explain_metrics"},
        stage=stage,
    )
    options = {
        "include_table": bool(options_in.get("include_table", True)),
        "explain_metrics": bool(options_in.get("explain_metrics", True)),
    }

    normalized_q = re.sub(r"\s+", " ", question.strip()).lower()
    normalized_q = re.sub(r"[?!.]+$", "", normalized_q).strip()

    return {
        "contract_version": "normalized-query.v1",
        "question": question,
        "normalized_question": normalized_q,
        "locale": locale,
        "options": options,
    }


# =====================================================================
# Contract 3: Auth and Policy Context (auth.policy-context.v1)
# =====================================================================
def build_auth_context(
    idp_claims: dict[str, Any] | None,
    server_policy: dict[str, Any] | None,
    request_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Builds AuthContext strictly from server/IdP claims, ignoring request_body."""
    stage = "auth_policy_context"
    if not idp_claims or not server_policy:
        raise ContractError("forbidden", stage, "Missing authentication or policy claims.", final_status="forbidden")

    enforce_exact_keys(
        idp_claims,
        required_keys={"user_id", "tenant_id", "roles"},
        optional_keys=set(),
        stage=stage,
    )
    enforce_exact_keys(
        server_policy,
        required_keys={"allowed_views", "policy_version"},
        optional_keys={"allowed_metrics"},
        stage=stage,
    )

    user_id = idp_claims["user_id"]
    tenant_id = idp_claims["tenant_id"]
    roles = list(idp_claims["roles"])
    allowed_views = list(server_policy["allowed_views"])
    allowed_metrics = (
        list(server_policy["allowed_metrics"]) if server_policy.get("allowed_metrics") is not None else None
    )

    if not user_id or not tenant_id or not roles or not allowed_views:
        raise ContractError("forbidden", stage, "Incomplete authorization context.", final_status="forbidden")

    policy_blob = json.dumps(
        {
            "tenant_id": tenant_id,
            "roles": sorted(roles),
            "allowed_views": sorted(allowed_views),
            "allowed_metrics": sorted(allowed_metrics) if allowed_metrics else None,
            "policy_version": server_policy["policy_version"],
        },
        sort_keys=True,
    )
    policy_hash = "policy-" + hashlib.sha256(policy_blob.encode("utf-8")).hexdigest()[:12]

    return {
        "contract_version": "auth-context.v1",
        "user_id": user_id,
        "tenant_id": tenant_id,
        "roles": roles,
        "allowed_views": allowed_views,
        "allowed_metrics": allowed_metrics,
        "policy_hash": policy_hash,
    }


# =====================================================================
# Contract 4: Metric Catalog (metric.catalog.v1)
# =====================================================================
DEFAULT_METRICS_DEFINITIONS: list[dict[str, Any]] = [
    {
        "metric_id": "net_revenue",
        "label": "Doanh thu thuần",
        "label_en": "Net Revenue",
        "description": "Tổng doanh thu bán hàng và cung cấp dịch vụ thuần (TK 511)",
        "aliases": ["doanh thu", "doanh thu thuần", "doanh số", "net revenue", "revenue", "sales", "total revenue"],
        "unit": "VND",
        "kind": "amount",
        "period_type": "flow",
        "supported_views": ["mgmt", "tax", "gl"],
        "supported_dimensions": ["month", "quarter", "year", "branch_code", "product_line", "partner_code", "segment"],
        "supported_operations": ["aggregate", "timeseries", "breakdown", "ranking", "comparison"],
        "default_view": "mgmt",
        "status": "approved",
        "owner": "finance",
        "catalog_version": "2026.11.1",
        "verified_handler": True,
        "sql_expr": "COALESCE(SUM(CASE WHEN account_code LIKE '511%' THEN credit_amount - debit_amount ELSE 0 END), 0)",
        "base_relation": "view",
    },
    {
        "metric_id": "cogs",
        "label": "Giá vốn hàng bán",
        "label_en": "Cost of Goods Sold",
        "description": "Tổng giá vốn hàng bán trong kỳ (TK 632)",
        "aliases": ["giá vốn", "giá vốn hàng bán", "cogs", "cost of goods sold", "cost of sales"],
        "unit": "VND",
        "kind": "amount",
        "period_type": "flow",
        "supported_views": ["mgmt", "tax", "gl"],
        "supported_dimensions": ["month", "quarter", "year", "branch_code", "product_line"],
        "supported_operations": ["aggregate", "timeseries", "breakdown", "comparison"],
        "default_view": "mgmt",
        "status": "approved",
        "owner": "finance",
        "catalog_version": "2026.11.1",
        "verified_handler": True,
        "sql_expr": "COALESCE(SUM(CASE WHEN account_code LIKE '632%' THEN debit_amount - credit_amount ELSE 0 END), 0)",
        "base_relation": "view",
    },
    {
        "metric_id": "gross_profit",
        "label": "Lợi nhuận gộp",
        "label_en": "Gross Profit",
        "description": "Doanh thu thuần trừ giá vốn hàng bán (TK 511 - TK 632)",
        "aliases": ["lợi nhuận gộp", "lãi gộp", "gross profit"],
        "unit": "VND",
        "kind": "amount",
        "period_type": "flow",
        "supported_views": ["mgmt", "tax", "gl"],
        "supported_dimensions": ["month", "quarter", "year", "branch_code", "product_line"],
        "supported_operations": ["aggregate", "timeseries", "breakdown", "ranking", "comparison"],
        "default_view": "mgmt",
        "status": "approved",
        "owner": "finance",
        "catalog_version": "2026.11.1",
        "verified_handler": True,
        "sql_expr": "COALESCE(SUM(CASE WHEN account_code LIKE '511%' THEN credit_amount - debit_amount WHEN account_code LIKE '632%' THEN -(debit_amount - credit_amount) ELSE 0 END), 0)",
        "base_relation": "view",
    },
    {
        "metric_id": "gross_margin",
        "label": "Biên lợi nhuận gộp",
        "label_en": "Gross Profit Margin",
        "description": "Tỷ lệ lợi nhuận gộp chia cho doanh thu thuần (%)",
        "aliases": ["biên lợi nhuận gộp", "biên lãi gộp", "tỷ suất lợi nhuận gộp", "gross margin", "gross profit margin"],
        "unit": "%",
        "kind": "ratio",
        "period_type": "flow",
        "supported_views": ["mgmt", "tax"],
        "supported_dimensions": ["month", "quarter", "year", "branch_code", "product_line"],
        "supported_operations": ["aggregate", "timeseries", "breakdown", "comparison"],
        "default_view": "mgmt",
        "status": "approved",
        "owner": "finance",
        "catalog_version": "2026.11.1",
        "verified_handler": True,
        "sql_expr": "CASE WHEN SUM(CASE WHEN account_code LIKE '511%' THEN credit_amount - debit_amount ELSE 0 END) = 0 THEN NULL ELSE ROUND((SUM(CASE WHEN account_code LIKE '511%' THEN credit_amount - debit_amount WHEN account_code LIKE '632%' THEN -(debit_amount - credit_amount) ELSE 0 END) * 100.0) / NULLIF(SUM(CASE WHEN account_code LIKE '511%' THEN credit_amount - debit_amount ELSE 0 END), 0), 2) END",
        "base_relation": "view",
    },
    {
        "metric_id": "operating_expense",
        "label": "Chi phí hoạt động",
        "label_en": "Operating Expense",
        "description": "Chi phí quản lý kinh doanh bao gồm chi phí bán hàng và quản lý doanh nghiệp (TK 642)",
        "aliases": [
            "chi phí hoạt động",
            "chi phí quản lý kinh doanh",
            "chi phí vận hành",
            "opex",
            "operating expense",
            "operating expenses",
            "chi phí",
            "chi phí marketing",
            "chi phí điện nước",
            "chi phí được trừ",
        ],
        "unit": "VND",
        "kind": "amount",
        "period_type": "flow",
        "supported_views": ["mgmt", "tax", "gl"],
        "supported_dimensions": ["month", "quarter", "year", "branch_code", "department_code", "cost_category"],
        "supported_operations": ["aggregate", "timeseries", "breakdown", "ranking", "comparison"],
        "default_view": "mgmt",
        "status": "approved",
        "owner": "finance",
        "catalog_version": "2026.11.1",
        "verified_handler": True,
        "sql_expr": "COALESCE(SUM(CASE WHEN account_code LIKE '642%' THEN debit_amount - credit_amount ELSE 0 END), 0)",
        "base_relation": "view",
    },
    {
        "metric_id": "net_profit",
        "label": "Lợi nhuận ròng",
        "label_en": "Net Profit",
        "description": "Lợi nhuận sau thuế thu nhập doanh nghiệp (Doanh thu 511, 515, 711 trừ Chi phí 632, 635, 642, 811, 821)",
        "aliases": ["lợi nhuận ròng", "lợi nhuận sau thuế", "lãi ròng", "net profit", "net income"],
        "unit": "VND",
        "kind": "amount",
        "period_type": "flow",
        "supported_views": ["mgmt", "tax"],
        "supported_dimensions": ["month", "quarter", "year", "branch_code"],
        "supported_operations": ["aggregate", "timeseries", "breakdown", "comparison"],
        "default_view": "mgmt",
        "status": "approved",
        "owner": "finance",
        "catalog_version": "2026.11.1",
        "verified_handler": True,
        "sql_expr": "COALESCE(SUM(CASE WHEN account_type = 'REVENUE' THEN credit_amount - debit_amount WHEN account_type = 'EXPENSE' THEN -(debit_amount - credit_amount) ELSE 0 END), 0)",
        "base_relation": "view",
    },
    {
        "metric_id": "net_profit_margin",
        "label": "Biên lợi nhuận ròng",
        "label_en": "Net Profit Margin",
        "description": "Lợi nhuận ròng chia cho doanh thu thuần (%)",
        "aliases": ["biên lợi nhuận ròng", "tỷ suất lợi nhuận ròng", "net profit margin", "net margin"],
        "unit": "%",
        "kind": "ratio",
        "period_type": "flow",
        "supported_views": ["mgmt", "tax"],
        "supported_dimensions": ["month", "quarter", "year", "branch_code"],
        "supported_operations": ["aggregate", "timeseries", "breakdown", "comparison"],
        "default_view": "mgmt",
        "status": "approved",
        "owner": "finance",
        "catalog_version": "2026.11.1",
        "verified_handler": True,
        "sql_expr": "CASE WHEN SUM(CASE WHEN account_code LIKE '511%' THEN credit_amount - debit_amount ELSE 0 END) = 0 THEN NULL ELSE ROUND((SUM(CASE WHEN account_type = 'REVENUE' THEN credit_amount - debit_amount WHEN account_type = 'EXPENSE' THEN -(debit_amount - credit_amount) ELSE 0 END) * 100.0) / NULLIF(SUM(CASE WHEN account_code LIKE '511%' THEN credit_amount - debit_amount ELSE 0 END), 0), 2) END",
        "base_relation": "view",
    },
    {
        "metric_id": "payroll_expense",
        "label": "Chi phí lương và bảo hiểm",
        "label_en": "Payroll and Insurance Expense",
        "description": "Chi phí lương, thưởng và bảo hiểm trích theo lương trong kỳ",
        "aliases": ["chi phí lương", "chi phí nhân sự", "quỹ lương", "payroll", "payroll expense", "salary expense"],
        "unit": "VND",
        "kind": "amount",
        "period_type": "flow",
        "supported_views": ["mgmt", "tax"],
        "supported_dimensions": ["month", "quarter", "year", "branch_code", "department_code"],
        "supported_operations": ["aggregate", "timeseries", "breakdown", "comparison"],
        "default_view": "mgmt",
        "status": "approved",
        "owner": "finance",
        "catalog_version": "2026.11.1",
        "verified_handler": True,
        "sql_expr": "COALESCE(SUM(CASE WHEN cost_category IN ('LUONG', 'BAOHIEM', 'THUONG') AND account_code LIKE '642%' THEN debit_amount - credit_amount ELSE 0 END), 0)",
        "base_relation": "view",
    },
    {
        "metric_id": "cash_balance",
        "label": "Số dư tiền và tương đương tiền",
        "label_en": "Cash and Bank Balance",
        "description": "Số dư tiền mặt (TK 111) và tiền gửi ngân hàng (TK 112) tại thời điểm as_of",
        "aliases": ["số dư tiền", "số dư tiền mặt", "tiền gửi ngân hàng", "cash balance", "cash and bank balance"],
        "unit": "VND",
        "kind": "amount",
        "period_type": "snapshot",
        "supported_views": ["mgmt", "gl"],
        "supported_dimensions": ["branch_code"],
        "supported_operations": ["aggregate", "breakdown"],
        "default_view": "mgmt",
        "status": "approved",
        "owner": "finance",
        "catalog_version": "2026.11.1",
        "verified_handler": True,
        "sql_expr": "COALESCE(SUM(CASE WHEN account_code LIKE '111%' OR account_code LIKE '112%' THEN debit_amount - credit_amount ELSE 0 END), 0)",
        "base_relation": "view",
    },
    {
        "metric_id": "ar_balance",
        "label": "Số dư nợ phải thu khách hàng",
        "label_en": "Accounts Receivable Balance",
        "description": "Tổng dư nợ phải thu khách hàng (TK 131) tại thời điểm as_of",
        "aliases": [
            "nợ phải thu",
            "phải thu khách hàng",
            "số dư phải thu",
            "accounts receivable",
            "ar balance",
            "receivables",
        ],
        "unit": "VND",
        "kind": "amount",
        "period_type": "snapshot",
        "supported_views": ["mgmt", "gl"],
        "supported_dimensions": ["branch_code", "partner_code", "segment"],
        "supported_operations": ["aggregate", "breakdown", "ranking"],
        "default_view": "mgmt",
        "status": "approved",
        "owner": "finance",
        "catalog_version": "2026.11.1",
        "verified_handler": True,
        "sql_expr": "COALESCE(SUM(CASE WHEN account_code LIKE '131%' THEN debit_amount - credit_amount ELSE 0 END), 0)",
        "base_relation": "view",
    },
    {
        "metric_id": "ap_balance",
        "label": "Số dư nợ phải trả nhà cung cấp",
        "label_en": "Accounts Payable Balance",
        "description": "Tổng dư nợ phải trả người bán (TK 331) tại thời điểm as_of",
        "aliases": [
            "nợ phải trả",
            "phải trả nhà cung cấp",
            "phải trả người bán",
            "accounts payable",
            "ap balance",
            "payables",
        ],
        "unit": "VND",
        "kind": "amount",
        "period_type": "snapshot",
        "supported_views": ["mgmt", "gl"],
        "supported_dimensions": ["branch_code", "partner_code"],
        "supported_operations": ["aggregate", "breakdown", "ranking"],
        "default_view": "mgmt",
        "status": "approved",
        "owner": "finance",
        "catalog_version": "2026.11.1",
        "verified_handler": True,
        "sql_expr": "COALESCE(SUM(CASE WHEN account_code LIKE '331%' THEN credit_amount - debit_amount ELSE 0 END), 0)",
        "base_relation": "view",
    },
    {
        "metric_id": "loan_balance",
        "label": "Tổng dư nợ vay",
        "label_en": "Total Loan Balance",
        "description": "Tổng dư nợ vay ngắn hạn và dài hạn (TK 341) tại thời điểm as_of",
        "aliases": ["dư nợ vay", "nợ vay ngân hàng", "vay ngân hàng", "loan balance", "total debt", "bank loan"],
        "unit": "VND",
        "kind": "amount",
        "period_type": "snapshot",
        "supported_views": ["mgmt", "gl"],
        "supported_dimensions": ["branch_code"],
        "supported_operations": ["aggregate", "breakdown"],
        "default_view": "mgmt",
        "status": "approved",
        "owner": "finance",
        "catalog_version": "2026.11.1",
        "verified_handler": True,
        "sql_expr": "COALESCE(SUM(CASE WHEN account_code LIKE '341%' THEN credit_amount - debit_amount ELSE 0 END), 0)",
        "base_relation": "view",
    },
    {
        "metric_id": "budget_amount",
        "label": "Ngân sách kế hoạch",
        "label_en": "Budget Amount",
        "description": "Ngân sách chi phí/doanh thu được duyệt theo kỳ và chi nhánh",
        "aliases": ["ngân sách", "dự toán", "kế hoạch ngân sách", "budget", "budget amount"],
        "unit": "VND",
        "kind": "amount",
        "period_type": "flow",
        "supported_views": ["mgmt"],
        "supported_dimensions": ["month", "year", "branch_code", "cost_category"],
        "supported_operations": ["aggregate", "breakdown", "timeseries"],
        "default_view": "mgmt",
        "status": "approved",
        "owner": "finance",
        "catalog_version": "2026.11.1",
        "verified_handler": True,
        "sql_expr": "COALESCE(SUM(amount), 0)",
        "base_relation": "budget",
    },
    # Unapproved draft metric for testing Rule 4.2 & Contract 4 / Contract 15
    {
        "metric_id": "experimental_cash_burn",
        "label": "Tốc độ đốt tiền thử nghiệm",
        "label_en": "Experimental Cash Burn Rate",
        "description": "Metric thử nghiệm chưa được CFO phê duyệt",
        "aliases": ["cash burn", "tốc độ đốt tiền"],
        "unit": "VND",
        "kind": "amount",
        "period_type": "flow",
        "supported_views": ["mgmt"],
        "supported_dimensions": ["month"],
        "supported_operations": ["aggregate"],
        "default_view": "mgmt",
        "status": "draft",
        "owner": "finance",
        "catalog_version": "2026.11.1",
        "verified_handler": True,
        "sql_expr": "0",
        "base_relation": "view",
    },
    # Approved metric with unverified handler for testing Contract 15 unsupported_data_source
    {
        "metric_id": "unverified_custom_kpi",
        "label": "KPI tùy chỉnh chưa kiểm chứng nguồn",
        "label_en": "Unverified Custom KPI",
        "description": "Metric có status approved nhưng handler chưa được verify",
        "aliases": ["unverified kpi"],
        "unit": "VND",
        "kind": "amount",
        "period_type": "flow",
        "supported_views": ["mgmt"],
        "supported_dimensions": ["month"],
        "supported_operations": ["aggregate"],
        "default_view": "mgmt",
        "status": "approved",
        "owner": "finance",
        "catalog_version": "2026.11.1",
        "verified_handler": False,
        "sql_expr": "0",
        "base_relation": "unknown_table",
    },
]


class MetricCatalog:
    """Implements Contract 4: metric.catalog.v1."""

    def __init__(self, metrics: list[dict[str, Any]] | None = None) -> None:
        raw_list = copy.deepcopy(metrics if metrics is not None else DEFAULT_METRICS_DEFINITIONS)
        self._metrics: dict[str, dict[str, Any]] = {m["metric_id"]: m for m in raw_list}
        blob = json.dumps(raw_list, sort_keys=True, ensure_ascii=False)
        self._catalog_hash = "catalog-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]

    def get(self, metric_id: str) -> dict[str, Any] | None:
        m = self._metrics.get(metric_id)
        return copy.deepcopy(m) if m else None

    def contains(self, metric_id: str) -> bool:
        return metric_id in self._metrics

    def get_capability(self, metric_id: str) -> dict[str, Any]:
        m = self._metrics.get(metric_id)
        if not m:
            raise ContractError("unknown_metric", "metric_catalog", f"Metric '{metric_id}' not found.")
        return {
            "metric_id": m["metric_id"],
            "unit": m["unit"],
            "kind": m["kind"],
            "period_type": m["period_type"],
            "supported_views": list(m["supported_views"]),
            "supported_dimensions": list(m["supported_dimensions"]),
            "supported_operations": list(m["supported_operations"]),
            "default_view": m["default_view"],
            "status": m["status"],
            "verified_handler": bool(m.get("verified_handler", True)),
        }

    def list_visible_metrics(self, auth_context: dict[str, Any]) -> list[dict[str, Any]]:
        allowed_views = set(auth_context.get("allowed_views") or [])
        allowed_metrics = (
            set(auth_context["allowed_metrics"]) if auth_context.get("allowed_metrics") is not None else None
        )
        visible: list[dict[str, Any]] = []
        for m in self._metrics.values():
            if m["status"] != "approved":
                continue
            if not m.get("verified_handler", True):
                continue
            if allowed_metrics is not None and m["metric_id"] not in allowed_metrics:
                continue
            if not (set(m["supported_views"]) & allowed_views):
                continue
            visible.append(copy.deepcopy(m))
        return visible

    def get_catalog_hash(self) -> str:
        return self._catalog_hash


# =====================================================================
# Contract 5 & 6: Embedding Provider & Metric Document Builder
# =====================================================================
class EmbeddingProvider:
    """Implements Contract 5: metric.embedding-provider.v1."""

    def __init__(
        self,
        model_id: str = "multilingual-embedding-v1",
        model_version: str = "2026.10",
        dimension: int = 16,
        available: bool = True,
        max_batch_size: int = 32,
        max_text_length: int = 1000,
    ) -> None:
        self.model_id = model_id
        self.model_version = model_version
        self.dimension = dimension
        self.available = available
        self.max_batch_size = max_batch_size
        self.max_text_length = max_text_length

    def embed(self, request: dict[str, Any]) -> dict[str, Any]:
        stage = "embedding_provider"
        enforce_exact_keys(
            request,
            required_keys={"texts", "model_id", "model_version", "normalize"},
            stage=stage,
        )
        if not self.available:
            raise ContractError(
                "retrieval_unavailable",
                stage,
                "Embedding provider is temporarily unavailable.",
                retryable=True,
                final_status="temporarily_unavailable",
            )
        if request["model_id"] != self.model_id or request["model_version"] != self.model_version:
            raise ContractError(
                "invalid_request",
                stage,
                "Embedding model/version mismatch.",
                final_status="error",
            )
        texts = request["texts"]
        if not isinstance(texts, list) or not texts or len(texts) > self.max_batch_size:
            raise ContractError("invalid_request", stage, "Invalid batch size for embedding.", final_status="error")

        vectors: list[dict[str, Any]] = []
        for text in texts:
            if not isinstance(text, str) or len(text) > self.max_text_length:
                raise ContractError("invalid_request", stage, "Invalid text length in embedding request.")
            digest = hashlib.sha256(text.lower().encode("utf-8")).digest()
            raw_vals = [((b / 127.5) - 1.0) for b in digest[: self.dimension]]
            if request["normalize"]:
                norm = math.sqrt(sum(v * v for v in raw_vals)) or 1.0
                vals = [round(v / norm, 6) for v in raw_vals]
            else:
                vals = [round(v, 6) for v in raw_vals]
            vectors.append(
                {
                    "values": vals,
                    "dimension": self.dimension,
                    "normalized": bool(request["normalize"]),
                }
            )
        return {
            "vectors": vectors,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "dimension": self.dimension,
        }


def build_metric_documents(catalog: MetricCatalog, locale: str = "vi-VN") -> list[dict[str, Any]]:
    """Implements Contract 6: metric.document-builder.v1."""
    if locale not in SUPPORTED_LOCALES:
        raise ContractError("unsupported_locale", "document_builder", f"Unsupported locale: {locale}")
    docs: list[dict[str, Any]] = []
    catalog_hash = catalog.get_catalog_hash()
    for m_id in sorted(catalog._metrics.keys()):
        m = catalog.get(m_id)
        if not m or m["status"] != "approved":
            continue
        dims = ", ".join(m["supported_dimensions"])
        if locale == "vi-VN":
            doc_text = f"{m['label']}. {m['description']}. Đơn vị {m['unit']}. Hỗ trợ theo {dims}."
        else:
            doc_text = f"{m.get('label_en', m['label'])}. {m['description']}. Unit {m['unit']}. Supports {dims}."
        docs.append(
            {
                "metric_id": m["metric_id"],
                "document_text": doc_text,
                "locale": locale,
                "catalog_hash": catalog_hash,
                "document_version": "metric-doc-v2",
            }
        )
    return docs


# =====================================================================
# Contracts 7, 8, 9, 10, 11: Retrieval Pipeline
# =====================================================================
def dense_retrieve(request: dict[str, Any], catalog: MetricCatalog, expected_dim: int = 16) -> dict[str, Any]:
    """Implements Contract 7: metric.retrieval.dense.v1."""
    stage = "dense_retrieval"
    enforce_exact_keys(
        request,
        required_keys={"query", "query_embedding", "top_k", "catalog_hash", "index_version"},
        stage=stage,
    )
    emb = request["query_embedding"]
    enforce_exact_keys(emb, required_keys={"values", "dimension", "normalized"}, stage=stage)
    if emb["dimension"] != expected_dim or len(emb["values"]) != expected_dim or not emb["normalized"]:
        raise ContractError("invalid_request", stage, "Query embedding dimension or normalization mismatch.")
    if request["catalog_hash"] != catalog.get_catalog_hash():
        raise ContractError("invalid_request", stage, "Catalog hash mismatch in dense retriever.")

    q_lower = request["query"].lower()
    scored: list[tuple[float, str]] = []
    for m_id, m in catalog._metrics.items():
        if m["status"] != "approved":
            continue
        score = 0.1
        for alias in m.get("aliases", []):
            if alias in q_lower:
                score = max(score, 0.85 + min(len(alias) * 0.005, 0.14))
        for token in re.findall(r"\w+", q_lower):
            if len(token) > 2 and token in (m["label"].lower() + " " + m.get("label_en", "").lower()):
                score = max(score, 0.55)
        if score > 0.2:
            scored.append((round(min(score, 0.99), 4), m_id))

    scored.sort(key=lambda x: (-x[0], x[1]))
    top_k = max(1, int(request["top_k"]))
    hits = [
        {
            "metric_id": m_id,
            "rank": idx + 1,
            "score": sc,
            "index_version": request["index_version"],
        }
        for idx, (sc, m_id) in enumerate(scored[:top_k])
    ]
    return {"source": "dense", "hits": hits}


def lexical_retrieve(request: dict[str, Any], catalog: MetricCatalog) -> dict[str, Any]:
    """Implements Contract 8: metric.retrieval.lexical.v1."""
    stage = "lexical_retrieval"
    enforce_exact_keys(
        request,
        required_keys={"query", "top_k", "index_version"},
        stage=stage,
    )
    q_lower = request["query"].lower()
    scored: list[tuple[float, str, list[str]]] = []
    for m_id, m in catalog._metrics.items():
        if m["status"] != "approved":
            continue
        matched: list[str] = []
        score = 0.0
        for alias in m.get("aliases", []):
            if alias in q_lower:
                matched.append(alias)
                score += 4.5 + len(alias.split()) * 1.2
        if matched:
            scored.append((round(score, 2), m_id, matched))

    scored.sort(key=lambda x: (-x[0], x[1]))
    top_k = max(1, int(request["top_k"]))
    hits = [
        {
            "metric_id": m_id,
            "rank": idx + 1,
            "score": sc,
            "matched_terms": matched,
        }
        for idx, (sc, m_id, matched) in enumerate(scored[:top_k])
    ]
    return {"source": "lexical", "hits": hits}


def fuse_candidates(
    dense_out: dict[str, Any],
    lexical_out: dict[str, Any],
    rrf_k: int = 60,
) -> dict[str, Any]:
    """Implements Contract 9: metric.retrieval.fusion.v1."""
    by_metric: dict[str, dict[str, Any]] = {}
    for hit in dense_out.get("hits", []):
        m_id = hit["metric_id"]
        entry = by_metric.setdefault(
            m_id,
            {
                "metric_id": m_id,
                "retrieval_sources": [],
                "dense_score": None,
                "lexical_score": None,
                "fusion_score": 0.0,
            },
        )
        if "dense" not in entry["retrieval_sources"]:
            entry["retrieval_sources"].append("dense")
        entry["dense_score"] = hit["score"]
        entry["fusion_score"] += 1.0 / (rrf_k + hit["rank"])

    for hit in lexical_out.get("hits", []):
        m_id = hit["metric_id"]
        entry = by_metric.setdefault(
            m_id,
            {
                "metric_id": m_id,
                "retrieval_sources": [],
                "dense_score": None,
                "lexical_score": None,
                "fusion_score": 0.0,
            },
        )
        if "lexical" not in entry["retrieval_sources"]:
            entry["retrieval_sources"].append("lexical")
        entry["lexical_score"] = hit["score"]
        entry["fusion_score"] += 1.0 / (rrf_k + hit["rank"])

    if not by_metric:
        return {
            "status": "empty_candidates",
            "candidates": [],
            "fusion_method": "rrf",
            "fusion_version": "rrf-v1",
        }

    sorted_items = sorted(by_metric.values(), key=lambda x: (-x["fusion_score"], x["metric_id"]))
    candidates = []
    for idx, item in enumerate(sorted_items):
        candidates.append(
            {
                "metric_id": item["metric_id"],
                "rank": idx + 1,
                "retrieval_sources": list(item["retrieval_sources"]),
                "dense_score": item["dense_score"],
                "lexical_score": item["lexical_score"],
                "fusion_score": round(item["fusion_score"], 6),
            }
        )
    return {
        "status": "candidates_found",
        "candidates": candidates,
        "fusion_method": "rrf",
        "fusion_version": "rrf-v1",
    }


def rerank_candidates(
    normalized_query: dict[str, Any],
    fusion_result: dict[str, Any],
    catalog: MetricCatalog,
    requested_view: str = "mgmt",
) -> dict[str, Any]:
    """Implements Contract 10: metric.retrieval.rerank.v1."""
    stage = "metric_rerank"
    q_text = normalized_query["normalized_question"]
    ranked: list[dict[str, Any]] = []
    for cand in fusion_result.get("candidates", []):
        m_id = cand["metric_id"]
        if not catalog.contains(m_id):
            raise ContractError("unknown_metric", stage, f"Reranker received unknown metric '{m_id}'.")
        m = catalog.get(m_id)
        assert m is not None
        label_match = 0.95 if any(a in q_text for a in m.get("aliases", [])) else 0.5
        view_compat = 1.0 if requested_view in m["supported_views"] else 0.2
        lang_match = 1.0
        rerank_score = round(0.6 * label_match + 0.25 * view_compat + 0.15 * lang_match, 4)
        ranked.append(
            {
                "metric_id": m_id,
                "rank": 0,
                "rerank_score": rerank_score,
                "score_components": {
                    "label_match": label_match,
                    "view_compatibility": view_compat,
                    "language_match": lang_match,
                },
                "retrieval_sources": list(cand["retrieval_sources"]),
                "_dense_score": cand["dense_score"],
                "_lexical_score": cand["lexical_score"],
                "_fusion_score": cand["fusion_score"],
            }
        )

    ranked.sort(key=lambda x: (-x["rerank_score"], -x["_fusion_score"], x["metric_id"]))
    clean_ranked = []
    for idx, item in enumerate(ranked):
        clean_ranked.append(
            {
                "metric_id": item["metric_id"],
                "rank": idx + 1,
                "rerank_score": item["rerank_score"],
                "score_components": item["score_components"],
                "retrieval_sources": item["retrieval_sources"],
            }
        )
    return {
        "ranked_candidates": clean_ranked,
        "reranker_version": "metadata-reranker-v2",
    }


def orchestrate_retrieval(
    normalized_query: dict[str, Any],
    catalog: MetricCatalog,
    embedding_provider: EmbeddingProvider,
    top_k: int = 15,
    requested_view: str = "mgmt",
) -> dict[str, Any]:
    """Implements Contract 11: metric.retrieval.orchestrator.v1."""
    try:
        emb_res = embedding_provider.embed(
            {
                "texts": [normalized_query["normalized_question"]],
                "model_id": embedding_provider.model_id,
                "model_version": embedding_provider.model_version,
                "normalize": True,
            }
        )
    except ContractError as exc:
        if exc.code == "retrieval_unavailable":
            return {
                "status": "retrieval_unavailable",
                "query": normalized_query["question"],
                "candidates": [],
                "catalog_hash": catalog.get_catalog_hash(),
                "embedding_model": embedding_provider.model_id,
                "dense_index_version": "metric-dense-index-v3",
                "lexical_index_version": "metric-lexical-index-v2",
                "reranker_version": "metadata-reranker-v2",
            }
        raise

    dense_out = dense_retrieve(
        {
            "query": normalized_query["question"],
            "query_embedding": emb_res["vectors"][0],
            "top_k": top_k,
            "catalog_hash": catalog.get_catalog_hash(),
            "index_version": "metric-dense-index-v3",
        },
        catalog=catalog,
        expected_dim=embedding_provider.dimension,
    )
    lex_out = lexical_retrieve(
        {
            "query": normalized_query["normalized_question"],
            "top_k": top_k,
            "index_version": "metric-lexical-index-v2",
        },
        catalog=catalog,
    )
    fused = fuse_candidates(dense_out, lex_out)
    if fused["status"] == "empty_candidates":
        return {
            "status": "empty_candidates",
            "query": normalized_query["question"],
            "candidates": [],
            "catalog_hash": catalog.get_catalog_hash(),
            "embedding_model": embedding_provider.model_id,
            "dense_index_version": "metric-dense-index-v3",
            "lexical_index_version": "metric-lexical-index-v2",
            "reranker_version": "metadata-reranker-v2",
        }

    reranked = rerank_candidates(normalized_query, fused, catalog, requested_view=requested_view)
    fusion_lookup = {c["metric_id"]: c for c in fused["candidates"]}
    final_candidates = []
    for rc in reranked["ranked_candidates"]:
        fc = fusion_lookup[rc["metric_id"]]
        final_candidates.append(
            {
                "metric_id": rc["metric_id"],
                "rank": rc["rank"],
                "retrieval_sources": rc["retrieval_sources"],
                "dense_score": fc["dense_score"],
                "lexical_score": fc["lexical_score"],
                "fusion_score": fc["fusion_score"],
                "rerank_score": rc["rerank_score"],
            }
        )
    return {
        "status": "candidates_found",
        "query": normalized_query["question"],
        "candidates": final_candidates,
        "catalog_hash": catalog.get_catalog_hash(),
        "embedding_model": embedding_provider.model_id,
        "dense_index_version": "metric-dense-index-v3",
        "lexical_index_version": "metric-lexical-index-v2",
        "reranker_version": "metadata-reranker-v2",
    }


# =====================================================================
# Contracts 12 & 13: Dynamic Few-shot Example Bank & Retrieval
# =====================================================================
DEFAULT_FEWSHOT_BANK: list[dict[str, Any]] = [
    {
        "example_id": "fs-margin-001",
        "question": "Tỷ suất lợi nhuận ròng quý trước là bao nhiêu?",
        "locale": "vi-VN",
        "intent": "metric_selection",
        "expected_selection": {"status": "resolved", "metric_ids": ["net_profit_margin"]},
        "context_constraints": {"supported_views": ["mgmt"], "required_dimensions": [], "required_time_modes": ["range"]},
        "quality_status": "approved",
        "source": "human_reviewed",
        "example_version": "fewshot-v4",
        "token_count": 185,
    },
    {
        "example_id": "fs-rev-001",
        "question": "Doanh thu thuần tháng 7/2026 là bao nhiêu?",
        "locale": "vi-VN",
        "intent": "metric_selection",
        "expected_selection": {"status": "resolved", "metric_ids": ["net_revenue"]},
        "context_constraints": {"supported_views": ["mgmt", "tax"], "required_dimensions": [], "required_time_modes": ["range"]},
        "quality_status": "approved",
        "source": "human_reviewed",
        "example_version": "fewshot-v4",
        "token_count": 160,
    },
    {
        "example_id": "fs-opex-001",
        "question": "Tổng chi phí hoạt động trong quý 1/2026 là bao nhiêu?",
        "locale": "vi-VN",
        "intent": "metric_selection",
        "expected_selection": {"status": "resolved", "metric_ids": ["operating_expense"]},
        "context_constraints": {"supported_views": ["mgmt", "tax"], "required_dimensions": [], "required_time_modes": ["range"]},
        "quality_status": "approved",
        "source": "human_reviewed",
        "example_version": "fewshot-v4",
        "token_count": 175,
    },
    {
        "example_id": "fs-unapproved-999",
        "question": "Ví dụ chưa được duyệt",
        "locale": "vi-VN",
        "intent": "metric_selection",
        "expected_selection": {"status": "resolved", "metric_ids": ["net_revenue"]},
        "context_constraints": {"supported_views": ["mgmt"], "required_dimensions": [], "required_time_modes": ["range"]},
        "quality_status": "draft",
        "source": "synthetic_unreviewed",
        "example_version": "fewshot-v4",
        "token_count": 120,
    },
]


def retrieve_dynamic_fewshot(
    request: dict[str, Any],
    example_bank: list[dict[str, Any]] | None = None,
    available: bool = True,
) -> dict[str, Any]:
    """Implements Contracts 12 & 13: fewshot.example-bank.v1 & fewshot.retrieval.dynamic.v1."""
    stage = "fewshot_retrieval"
    enforce_exact_keys(
        request,
        required_keys={
            "question",
            "locale",
            "candidate_metric_ids",
            "context",
            "max_examples",
            "token_budget",
            "selection_strategy",
            "example_bank_version",
            "compatible_only",
        },
        stage=stage,
    )
    if not available:
        return {
            "status": "fewshot_unavailable",
            "examples": [],
            "total_token_count": 0,
            "example_bank_version": request["example_bank_version"],
            "selection_strategy": request["selection_strategy"],
        }

    bank = example_bank if example_bank is not None else DEFAULT_FEWSHOT_BANK
    candidate_set = set(request["candidate_metric_ids"])
    q_norm = request["question"].strip().lower()
    req_view = (request.get("context") or {}).get("view", "mgmt")
    max_examples = int(request["max_examples"])
    token_budget = int(request["token_budget"])
    compatible_only = bool(request["compatible_only"])

    selected: list[dict[str, Any]] = []
    total_tokens = 0

    for ex in bank:
        # Rule 12: Only approved examples without prompt injection
        if ex.get("quality_status") != "approved":
            continue
        if INJECTION_PATTERNS.search(ex.get("question", "")):
            continue
        # Rule 13: Never select the exact current question
        if ex["question"].strip().lower() == q_norm:
            continue
        ex_metrics = set(ex["expected_selection"]["metric_ids"])
        # Rule 13: compatible_only enforces example.expected_selection.metric_ids <= candidate_metric_ids
        if compatible_only and not ex_metrics.issubset(candidate_set):
            continue
        supported_views = ex.get("context_constraints", {}).get("supported_views", ["mgmt"])
        if req_view not in supported_views:
            continue

        ex_tokens = int(ex.get("token_count", 180))
        if total_tokens + ex_tokens > token_budget:
            continue
        if len(selected) >= max_examples:
            break

        matched_ids = sorted(ex_metrics & candidate_set)
        selected.append(
            {
                "example_id": ex["example_id"],
                "question": ex["question"],
                "expected_selection": copy.deepcopy(ex["expected_selection"]),
                "matched_metric_ids": matched_ids,
                "similarity_score": 0.91,
                "compatibility_score": 1.0 if ex_metrics.issubset(candidate_set) else 0.5,
                "rank": len(selected) + 1,
                "token_count": ex_tokens,
            }
        )
        total_tokens += ex_tokens

    status = "examples_found" if selected else "no_compatible_examples"
    return {
        "status": status,
        "examples": selected,
        "total_token_count": total_tokens,
        "example_bank_version": request["example_bank_version"],
        "selection_strategy": request["selection_strategy"],
    }


# =====================================================================
# Contracts 14 & 15: LLM Metric Selection & Metrics Validation
# =====================================================================
def validate_llm_selection_draft(draft: dict[str, Any]) -> dict[str, Any]:
    """Validates schema & safety rules of Contract 14: metric.selection.llm.v1."""
    stage = "llm_metric_selection"
    enforce_exact_keys(
        draft,
        required_keys={"status", "metric_ids", "clarification_question", "unsupported_reason"},
        stage=stage,
    )
    if draft["status"] not in {"resolved", "ambiguous", "unsupported"}:
        raise ContractError("invalid_request", stage, f"Invalid LLM selection status: {draft['status']}")
    if not isinstance(draft["metric_ids"], list):
        raise ContractError("invalid_request", stage, "metric_ids must be a list.")

    # Rule 14: No SQL, formula, table name, or column name in LLM selection output
    serialized = json.dumps(draft, ensure_ascii=False)
    if FORBIDDEN_SQL_PATTERNS.search(serialized) or re.search(
        r"\b(SELECT\s+|FROM\s+v_mgmt|FROM\s+gl_wide|SUM\(|credit_amount|debit_amount)\b",
        serialized,
        re.IGNORECASE,
    ):
        raise ContractError(
            "invalid_request",
            stage,
            "LLM selection output must not contain SQL, formulas, table names, or column names.",
        )
    return copy.deepcopy(draft)


def validate_metrics(
    llm_selection: dict[str, Any],
    retrieval_result: dict[str, Any],
    catalog: MetricCatalog,
    auth_context: dict[str, Any],
    query_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Implements Contract 15: metric.validation.v1 (Ultimate authority for metrics)."""
    stage = "metrics_validation"
    checked_llm = validate_llm_selection_draft(llm_selection)
    q_ctx = query_context or {}

    if checked_llm["status"] == "ambiguous":
        return {
            "status": "needs_clarification",
            "metric_ids": [],
            "catalog_hash": catalog.get_catalog_hash(),
            "validated_capabilities": {},
            "warnings": [],
            "clarification_question": checked_llm.get("clarification_question")
            or "Bạn vui lòng làm rõ chỉ tiêu tài chính cần truy vấn?",
        }

    if checked_llm["status"] == "unsupported":
        raise ContractError(
            "unsupported_metric",
            stage,
            checked_llm.get("unsupported_reason") or "Metric hoặc yêu cầu chưa được hỗ trợ.",
            final_status="unsupported",
        )

    selected_ids = list(checked_llm["metric_ids"])
    if not selected_ids:
        raise ContractError("unsupported_metric", stage, "No metrics selected.", final_status="unsupported")

    candidate_ids = {c["metric_id"] for c in retrieval_result.get("candidates", [])}
    allowed_views = set(auth_context.get("allowed_views") or [])
    allowed_metrics = (
        set(auth_context["allowed_metrics"]) if auth_context.get("allowed_metrics") is not None else None
    )
    requested_view = q_ctx.get("requested_view") or "mgmt"
    requested_dimensions = list(q_ctx.get("requested_dimensions") or [])
    requested_operation = q_ctx.get("requested_operation") or "aggregate"

    if requested_view not in allowed_views:
        raise ContractError(
            "forbidden_metric",
            stage,
            f"User is not authorized to access view '{requested_view}'.",
            details={"requested_view": requested_view},
            final_status="forbidden",
        )

    validated_capabilities: dict[str, Any] = {}
    period_types: set[str] = set()

    for m_id in selected_ids:
        # Check 1: Exists in catalog
        if not catalog.contains(m_id):
            raise ContractError(
                "unknown_metric",
                stage,
                f"Metric '{m_id}' does not exist in Metric Catalog.",
                details={"metric_id": m_id},
                final_status="unsupported",
            )
        # Check 2: selected_metric_ids <= retrieved_candidate_metric_ids
        if m_id not in candidate_ids:
            raise ContractError(
                "metric_outside_candidates",
                stage,
                f"Metric '{m_id}' was not in retrieved candidate set.",
                details={"metric_id": m_id},
                final_status="unsupported",
            )
        cap = catalog.get_capability(m_id)
        # Check 3: Approved status
        if cap["status"] != "approved":
            raise ContractError(
                "unsupported_metric",
                stage,
                f"Metric '{m_id}' is not approved for production use.",
                details={"metric_id": m_id},
                final_status="unsupported",
            )
        # Check 4: Verified handler/source
        if not cap.get("verified_handler", True):
            raise ContractError(
                "unsupported_data_source",
                stage,
                f"Metric '{m_id}' does not have a verified data handler.",
                details={"metric_id": m_id},
                final_status="unsupported",
            )
        # Check 5: User permission on metric
        if allowed_metrics is not None and m_id not in allowed_metrics:
            raise ContractError(
                "forbidden_metric",
                stage,
                f"User is not permitted to access metric '{m_id}'.",
                details={"metric_id": m_id},
                final_status="forbidden",
            )
        # Check 6: View compatibility
        if requested_view not in cap["supported_views"]:
            raise ContractError(
                "unsupported_view",
                stage,
                f"Metric '{m_id}' does not support view '{requested_view}'.",
                details={"metric_id": m_id, "view": requested_view},
                final_status="unsupported",
            )
        # Check 7: Dimension & operation capabilities
        for dim in requested_dimensions:
            if dim not in cap["supported_dimensions"]:
                raise ContractError(
                    "unsupported_metric",
                    stage,
                    f"Metric '{m_id}' does not support dimension '{dim}'.",
                    details={"metric_id": m_id, "dimension": dim},
                    final_status="unsupported",
                )
        if requested_operation not in cap["supported_operations"]:
            raise ContractError(
                "unsupported_metric",
                stage,
                f"Metric '{m_id}' does not support operation '{requested_operation}'.",
                details={"metric_id": m_id, "operation": requested_operation},
                final_status="unsupported",
            )

        period_types.add(cap["period_type"])
        validated_capabilities[m_id] = {
            "period_type": cap["period_type"],
            "supported_views": cap["supported_views"],
            "supported_dimensions": cap["supported_dimensions"],
            "supported_operations": cap["supported_operations"],
        }

    # Check 8: Period type compatibility across multiple metrics
    if len(period_types) > 1:
        raise ContractError(
            "incompatible_metrics",
            stage,
            "Cannot combine 'flow' and 'snapshot' metrics in the same query.",
            details={"period_types": sorted(period_types)},
            final_status="unsupported",
        )

    return {
        "status": "validated",
        "metric_ids": selected_ids,
        "catalog_hash": catalog.get_catalog_hash(),
        "validated_capabilities": validated_capabilities,
        "warnings": [],
    }


# =====================================================================
# Contracts 16 & 17: Query Planning & Semantic Plan Validation
# =====================================================================
def validate_semantic_plan_draft(
    plan_draft: dict[str, Any],
    validated_metrics: dict[str, Any],
    catalog: MetricCatalog,
    auth_context: dict[str, Any],
    max_days: int = 750,
    max_top_k: int = 100,
) -> dict[str, Any]:
    """Implements Contracts 16 & 17: query.planning.v1 & query.plan-validation.v1."""
    stage = "semantic_plan_validation"
    enforce_exact_keys(
        plan_draft,
        required_keys={
            "plan_version",
            "status",
            "metric_ids",
            "time",
            "dimensions",
            "filters",
            "view",
            "operation",
            "sort",
            "top_k",
            "comparison",
            "question_for_user",
            "unresolved_slots",
            "reason_code",
        },
        stage=stage,
    )
    if plan_draft["plan_version"] != "1.0":
        raise ContractError("invalid_request", stage, "Unsupported plan_version.")

    # Rule 16: No SQL or physical table names inside SemanticPlanDraft
    serialized = json.dumps(plan_draft, ensure_ascii=False)
    if FORBIDDEN_SQL_PATTERNS.search(serialized) or re.search(
        r"\b(SELECT\s+|FROM\s+|gl_wide|gl_entry|ar_invoice_line|duckdb_tables)\b",
        serialized,
        re.IGNORECASE,
    ):
        raise ContractError("invalid_request", stage, "SemanticPlanDraft must not contain SQL or physical tables.")

    if plan_draft["status"] == "needs_clarification":
        return {
            "contract_version": "validated-plan.v1",
            "status": "needs_clarification",
            "question_for_user": plan_draft.get("question_for_user")
            or "Vui lòng cho biết khoảng thời gian hoặc tiêu chí cụ thể.",
            "unresolved_slots": list(plan_draft.get("unresolved_slots") or ["time"]),
            "tenant_id": auth_context["tenant_id"],
            "catalog_hash": catalog.get_catalog_hash(),
            "policy_hash": auth_context["policy_hash"],
        }

    if plan_draft["status"] == "unsupported":
        raise ContractError(
            "unsupported_metric",
            stage,
            plan_draft.get("reason_code") or "Unsupported query plan.",
            final_status="unsupported",
        )

    if plan_draft["status"] != "ready":
        raise ContractError("invalid_request", stage, f"Invalid plan status: {plan_draft['status']}")

    # Only use metrics in ValidatedMetricSet
    validated_ids = set(validated_metrics["metric_ids"])
    plan_ids = list(plan_draft["metric_ids"])
    if not plan_ids or not set(plan_ids).issubset(validated_ids):
        raise ContractError(
            "metric_outside_candidates",
            stage,
            "Plan contains metrics not in ValidatedMetricSet.",
            final_status="unsupported",
        )

    view = plan_draft["view"]
    if view not in set(auth_context.get("allowed_views") or []):
        raise ContractError(
            "forbidden_metric",
            stage,
            f"View '{view}' is not allowed by AuthContext.",
            final_status="forbidden",
        )

    # Check period_type vs time mode
    caps = [catalog.get_capability(m_id) for m_id in plan_ids]
    period_types = {c["period_type"] for c in caps}
    if len(period_types) > 1:
        raise ContractError(
            "incompatible_metrics",
            stage,
            "Incompatible period types in plan.",
            final_status="unsupported",
        )
    period_type = next(iter(period_types))

    time_spec = plan_draft["time"]
    if not isinstance(time_spec, dict) or "mode" not in time_spec:
        raise ContractError("invalid_request", stage, "Invalid time specification in plan.")

    if period_type == "snapshot":
        if time_spec["mode"] != "as_of" or not time_spec.get("as_of"):
            raise ContractError(
                "invalid_request",
                stage,
                "Snapshot metrics require time.mode == 'as_of' and a valid 'as_of' date.",
                final_status="unsupported",
            )
        datetime.date.fromisoformat(time_spec["as_of"])
    else:
        if time_spec["mode"] != "range" or not time_spec.get("start") or not time_spec.get("end"):
            raise ContractError(
                "invalid_request",
                stage,
                "Flow metrics require time.mode == 'range' with 'start' and 'end' dates.",
                final_status="unsupported",
            )
        start_d = datetime.date.fromisoformat(time_spec["start"])
        end_d = datetime.date.fromisoformat(time_spec["end"])
        if start_d > end_d:
            raise ContractError("invalid_request", stage, "start date must be <= end date.")
        if (end_d - start_d).days > max_days:
            raise ContractError(
                "invalid_request",
                stage,
                f"Date range exceeds maximum allowed days ({max_days}).",
                final_status="unsupported",
            )

    # Validate dimensions
    dimensions = list(plan_draft.get("dimensions") or [])
    for dim in dimensions:
        if dim not in ALLOWED_DIMENSIONS:
            raise ContractError("unsupported_metric", stage, f"Dimension '{dim}' is not in allowlist.", final_status="unsupported")
        for cap in caps:
            if dim not in cap["supported_dimensions"]:
                raise ContractError(
                    "unsupported_metric",
                    stage,
                    f"Metric '{cap['metric_id']}' does not support dimension '{dim}'.",
                    final_status="unsupported",
                )

    # Validate filters
    filters = list(plan_draft.get("filters") or [])
    for flt in filters:
        enforce_exact_keys(flt, required_keys={"field", "op", "value"}, stage=stage)
        fld = flt["field"]
        op = flt["op"]
        val = flt["value"]
        if fld not in ALLOWED_FILTER_FIELDS:
            raise ContractError("invalid_request", stage, f"Filter field '{fld}' is not allowlisted.", final_status="unsupported")
        if op not in ALLOWED_OPERATORS:
            raise ContractError("invalid_request", stage, f"Filter operator '{op}' is not allowlisted.", final_status="unsupported")
        allowed_vals = ALLOWED_FILTER_FIELDS[fld]
        vals_to_check = val if isinstance(val, list) else [val]
        for v in vals_to_check:
            if not isinstance(v, str) or INJECTION_PATTERNS.search(v) or ";" in v or "--" in v or "'" in v:
                raise ContractError("invalid_request", stage, f"Invalid filter value '{v}'.", final_status="unsupported")
            if allowed_vals is not None and v not in allowed_vals:
                raise ContractError("invalid_request", stage, f"Value '{v}' not in allowlist for '{fld}'.", final_status="unsupported")

    # Validate top_k
    top_k = plan_draft.get("top_k")
    if top_k is not None:
        if not isinstance(top_k, int) or top_k < 1 or top_k > max_top_k:
            raise ContractError("invalid_request", stage, f"top_k must be between 1 and {max_top_k}.")

    applied_defaults: list[str] = []
    operation = plan_draft.get("operation") or "aggregate"
    if not plan_draft.get("operation"):
        applied_defaults.append("operation=aggregate")

    return {
        "contract_version": "validated-plan.v1",
        "status": "validated",
        "metric_ids": plan_ids,
        "time": copy.deepcopy(time_spec),
        "dimensions": dimensions,
        "filters": copy.deepcopy(filters),
        "view": view,
        "operation": operation,
        "sort": plan_draft.get("sort"),
        "top_k": top_k,
        "comparison": plan_draft.get("comparison"),
        "tenant_id": auth_context["tenant_id"],
        "catalog_hash": catalog.get_catalog_hash(),
        "policy_hash": auth_context["policy_hash"],
        "applied_defaults": applied_defaults,
    }


# =====================================================================
# Contracts 18, 19, 20: SQL Compiler, Safety Gate & Execution
# =====================================================================
DIMENSION_TO_SQL_COL = {
    "month": "year_month",
    "quarter": "CAST(year_no AS VARCHAR) || '-Q' || CAST(quarter_no AS VARCHAR)",
    "year": "CAST(year_no AS VARCHAR)",
    "branch_code": "branch_code",
    "product_line": "product_line",
    "department_code": "department_code",
    "cost_category": "cost_category",
    "partner_code": "partner_code",
    "segment": "segment",
}


def compile_sql(
    validated_plan: dict[str, Any],
    catalog: MetricCatalog,
    row_cap: int = 1000,
) -> dict[str, Any]:
    """Implements Contract 18: sql.compiler.v1. Accepts ONLY ValidatedPlan."""
    stage = "sql_compiler"
    if not isinstance(validated_plan, dict) or validated_plan.get("contract_version") != "validated-plan.v1":
        raise ContractError(
            "invalid_request",
            stage,
            "SQL Compiler only accepts a trusted ValidatedPlan object.",
        )
    if validated_plan.get("status") != "validated":
        raise ContractError("invalid_request", stage, "ValidatedPlan status must be 'validated'.")
    if validated_plan.get("catalog_hash") != catalog.get_catalog_hash():
        raise ContractError("invalid_request", stage, "Catalog hash mismatch between ValidatedPlan and CatalogSnapshot.")

    metric_ids = validated_plan["metric_ids"]
    metrics = [catalog.get(m_id) for m_id in metric_ids]
    assert all(m is not None for m in metrics)

    view_map = {"mgmt": "v_mgmt", "tax": "v_tax", "gl": "v_gl"}
    first_metric = metrics[0]
    assert first_metric is not None
    if first_metric.get("base_relation") == "budget":
        source_relation = "budget"
    else:
        source_relation = view_map.get(validated_plan["view"], "v_mgmt")

    select_parts: list[str] = []
    group_by_parts: list[str] = []
    dimensions = list(validated_plan.get("dimensions") or [])
    time_spec = validated_plan["time"]
    grain = time_spec.get("grain")

    if validated_plan["operation"] == "timeseries" and grain in {"month", "quarter", "year"} and grain not in dimensions:
        dimensions = [grain] + dimensions

    for dim in dimensions:
        if source_relation == "budget" and dim == "month":
            col_expr = "PRINTF('%04d-%02d', year_no, month_no)"
        else:
            col_expr = DIMENSION_TO_SQL_COL[dim]
        select_parts.append(f"{col_expr} AS {dim}")
        group_by_parts.append(col_expr)

    units: dict[str, str] = {}
    for m in metrics:
        assert m is not None
        select_parts.append(f"{m['sql_expr']} AS {m['metric_id']}")
        units[m["metric_id"]] = m["unit"]

    where_clauses: list[str] = []
    params: list[Any] = []

    if source_relation == "budget":
        start_d = datetime.date.fromisoformat(time_spec["start"])
        end_d = datetime.date.fromisoformat(time_spec["end"])
        start_ym = start_d.year * 100 + start_d.month
        end_ym = end_d.year * 100 + end_d.month
        where_clauses.append("(CAST(year_no AS INTEGER) * 100 + month_no) BETWEEN ? AND ?")
        params.extend([start_ym, end_ym])
    else:
        if time_spec["mode"] == "as_of":
            where_clauses.append("posting_date <= CAST(? AS DATE)")
            params.append(time_spec["as_of"])
        else:
            where_clauses.append("posting_date >= CAST(? AS DATE) AND posting_date <= CAST(? AS DATE)")
            params.extend([time_spec["start"], time_spec["end"]])
            where_clauses.append("NOT is_closing")

    for flt in validated_plan.get("filters") or []:
        fld = flt["field"]
        op = flt["op"]
        val = flt["value"]
        if op == "=":
            where_clauses.append(f"{fld} = ?")
            params.append(val)
        elif op == "IN" and isinstance(val, list):
            placeholders = ", ".join(["?"] * len(val))
            where_clauses.append(f"{fld} IN ({placeholders})")
            params.extend(val)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    group_sql = f" GROUP BY {', '.join(group_by_parts)}" if group_by_parts else ""

    order_sql = ""
    if validated_plan.get("top_k") or validated_plan.get("operation") == "ranking":
        primary_metric = metric_ids[0]
        direction = "ASC" if validated_plan.get("sort") == "asc" else "DESC"
        order_sql = f" ORDER BY {primary_metric} {direction}"
    elif group_by_parts:
        order_sql = f" ORDER BY {', '.join(dimensions)} ASC"

    effective_cap = min(int(validated_plan["top_k"]), row_cap) if validated_plan.get("top_k") else row_cap
    params.append(effective_cap)

    sql = (
        f"WITH tenant_scoped AS ("
        f"SELECT * FROM {source_relation} /* tenant:{validated_plan['tenant_id']} */ "
        f"WHERE {where_sql}"
        f") "
        f"SELECT {', '.join(select_parts)} FROM tenant_scoped{group_sql}{order_sql} LIMIT ?"
    )
    fingerprint = "sha256:" + hashlib.sha256((sql + json.dumps(params, default=str)).encode("utf-8")).hexdigest()[:16]

    return {
        "contract_version": "bound-query.v1",
        "sql": sql,
        "params": params,
        "metric_ids": metric_ids,
        "dimensions": dimensions,
        "units": units,
        "row_cap": effective_cap,
        "fingerprint": fingerprint,
        "source": source_relation,
        "catalog_hash": catalog.get_catalog_hash(),
        "tenant_id": validated_plan["tenant_id"],
    }


def validate_sql_safety(
    bound_query: dict[str, Any],
    catalog: MetricCatalog,
    runtime_context: dict[str, Any],
) -> dict[str, Any]:
    """Implements Contract 19: sql.safety.v1."""
    stage = "sql_safety"
    sql = bound_query.get("sql", "")
    params = bound_query.get("params", [])

    # Strip comments before statement checks
    sql_no_comments = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL).strip()
    has_dml_ddl = bool(FORBIDDEN_SQL_PATTERNS.search(sql_no_comments))
    starts_valid = bool(re.match(r"^(SELECT|WITH)\b", sql_no_comments, re.IGNORECASE))
    read_only = starts_valid and not has_dml_ddl

    # Single statement check (no semicolons)
    single_statement = ";" not in sql_no_comments

    # Approved relations check
    from_matches = re.findall(r"\bFROM\s+([a-zA-Z0-9_]+)", sql_no_comments, re.IGNORECASE)
    cte_names = set(re.findall(r"\bWITH\s+([a-zA-Z0-9_]+)\s+AS", sql_no_comments, re.IGNORECASE))
    approved_relations = all((rel in ALLOWED_RELATIONS or rel in cte_names) for rel in from_matches) and bool(from_matches)

    # No literal user-controlled strings embedded in WHERE (excluding account_code LIKE '511%' and cost_category IN ('LUONG', ...))
    sql_without_known_literals = re.sub(r"account_code\s+LIKE\s+'[0-9]+%'", "", sql_no_comments)
    sql_without_known_literals = re.sub(r"account_type\s*=\s*'(REVENUE|EXPENSE)'", "", sql_without_known_literals)
    sql_without_known_literals = re.sub(
        r"cost_category\s+IN\s*\('LUONG',\s*'BAOHIEM',\s*'THUONG'\)", "", sql_without_known_literals
    )
    sql_without_known_literals = re.sub(r"PRINTF\('%04d-%02d'", "", sql_without_known_literals)
    sql_without_known_literals = re.sub(r"\|\|\s*'-Q'\s*\|\|", "", sql_without_known_literals)
    has_unparameterized_quotes = "'" in sql_without_known_literals
    parameterized = (not has_unparameterized_quotes) and (sql_no_comments.count("?") == len(params)) and len(params) > 0

    # Row cap check
    row_cap_present = bool(re.search(r"\bLIMIT\s+(\?|\d+)\s*$", sql_no_comments, re.IGNORECASE)) and (
        0 < int(bound_query.get("row_cap", 0)) <= 1000
    )

    # Tenant scope & hash check
    expected_tenant = runtime_context.get("tenant_id")
    tenant_scope_present = (
        bool(expected_tenant)
        and bound_query.get("tenant_id") == expected_tenant
        and f"tenant:{expected_tenant}" in sql
    )
    hash_matches = bound_query.get("catalog_hash") == catalog.get_catalog_hash()
    approved_columns = not bool(re.search(r"\b(password|secret|tax_id|credit_limit)\b", sql_no_comments, re.IGNORECASE))

    checks = {
        "read_only": read_only,
        "single_statement": single_statement,
        "approved_relations": approved_relations,
        "approved_columns": approved_columns,
        "parameterized": parameterized,
        "row_cap_present": row_cap_present,
        "tenant_scope_present": tenant_scope_present and hash_matches,
    }

    if not all(checks.values()):
        raise ContractError(
            "unsafe_sql_rejected",
            stage,
            "Query rejected by SQL Safety Validation gate.",
            details={"checks": checks},
            final_status="error",
        )

    return {
        "status": "allowed",
        "query_fingerprint": bound_query["fingerprint"],
        "checks": checks,
        "safe_bound_query": copy.deepcopy(bound_query),
    }


def execute_safe_sql(
    safety_result: dict[str, Any],
    db_path: Path = DB_PATH,
    timeout_ms: int = 5000,
    simulate_outage: bool = False,
) -> dict[str, Any]:
    """Implements Contract 20: sql.execution.v1 on read-only DuckDB."""
    stage = "sql_execution"
    if not isinstance(safety_result, dict) or safety_result.get("status") != "allowed" or "safe_bound_query" not in safety_result:
        raise ContractError(
            "unsafe_sql_rejected",
            stage,
            "SQL Executor only accepts queries that passed SQL Safety Validation.",
        )
    if simulate_outage:
        raise ContractError(
            "database_unavailable",
            stage,
            "Database is temporarily unavailable.",
            retryable=True,
            final_status="temporarily_unavailable",
        )

    bound = safety_result["safe_bound_query"]
    t0 = time.perf_counter()
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        wm_row = con.execute("SELECT value FROM company_info WHERE key = 'as_of_date'").fetchone()
        data_watermark = wm_row[0] if wm_row else "2026-10-14"

        cur = con.execute(bound["sql"], bound["params"])
        col_names = [desc[0] for desc in cur.description]
        raw_rows = cur.fetchall()
    except Exception as exc:
        raise ContractError("execution_failed", stage, f"Database execution error: {type(exc).__name__}") from exc
    finally:
        con.close()

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    if elapsed_ms > timeout_ms:
        raise ContractError(
            "execution_timeout",
            stage,
            "Database query timed out.",
            retryable=True,
            final_status="temporarily_unavailable",
        )

    units = bound.get("units", {})
    dims = set(bound.get("dimensions", []))
    columns = []
    for c_name in col_names:
        if c_name in dims:
            columns.append({"key": c_name, "type": "string", "unit": None})
        else:
            columns.append({"key": c_name, "type": "decimal", "unit": units.get(c_name, "VND")})

    formatted_rows: list[dict[str, Any]] = []
    for r in raw_rows:
        row_dict: dict[str, Any] = {}
        for c_name, val in zip(col_names, r):
            if val is None:
                row_dict[c_name] = None
            elif isinstance(val, (Decimal, float, int)) and c_name not in dims:
                row_dict[c_name] = f"{Decimal(str(val)):.2f}"
            else:
                row_dict[c_name] = str(val)
        formatted_rows.append(row_dict)

    row_cap = int(bound["row_cap"])
    return {
        "columns": columns,
        "rows": formatted_rows,
        "row_count": len(formatted_rows),
        "truncated": len(formatted_rows) >= row_cap and row_cap == 1000,
        "data_watermark": data_watermark,
        "execution_ms": max(1, elapsed_ms),
    }


# =====================================================================
# Contracts 21, 22, 23, 24, 25: Result Validation, Grounded Answer & Final Response
# =====================================================================
def validate_result(
    execution_result: dict[str, Any],
    validated_plan: dict[str, Any],
    catalog: MetricCatalog,
    last_closed_month: str = "2026-08",
) -> dict[str, Any]:
    """Implements Contract 21: result.validation.v1."""
    stage = "result_validation"
    cols = execution_result.get("columns", [])
    rows = execution_result.get("rows", [])
    col_keys = [c["key"] for c in cols]

    # Check duplicate columns & expected columns
    no_duplicates = len(col_keys) == len(set(col_keys))
    expected_keys = list(validated_plan.get("dimensions") or []) + list(validated_plan["metric_ids"])
    columns_expected = col_keys == expected_keys and no_duplicates

    types_valid = True
    semantic_valid = True
    warnings: list[str] = []

    for c in cols:
        m_id = c["key"]
        if catalog.contains(m_id):
            cap = catalog.get_capability(m_id)
            if c.get("unit") != cap["unit"]:
                semantic_valid = False

    for row in rows:
        for c in cols:
            key = c["key"]
            val = row.get(key)
            if c["type"] == "decimal":
                if val is None:
                    if catalog.contains(key) and catalog.get_capability(key)["kind"] == "ratio":
                        if "ratio_undefined" not in warnings:
                            warnings.append("ratio_undefined")
                    else:
                        types_valid = False
                else:
                    try:
                        d_val = Decimal(str(val))
                        if d_val.is_nan() or d_val.is_infinite():
                            types_valid = False
                    except (InvalidOperation, ValueError):
                        types_valid = False

    row_count_valid = len(rows) == execution_result.get("row_count", -1)
    checks = {
        "schema_valid": no_duplicates,
        "types_valid": types_valid,
        "columns_expected": columns_expected,
        "row_count_valid": row_count_valid,
        "semantic_constraints_valid": semantic_valid,
    }

    if not all(checks.values()):
        raise ContractError(
            "invalid_result",
            stage,
            "ExecutionResult failed Result Validation checks.",
            details={"checks": checks},
            final_status="error",
        )

    # Check if result has no data (0 rows or single aggregate row where all metrics are 0/None outside data range)
    time_spec = validated_plan["time"]
    watermark = execution_result.get("data_watermark", "2026-10-14")
    wm_date = datetime.date.fromisoformat(watermark)
    data_start_date = datetime.date(2024, 12, 31)

    if time_spec["mode"] == "range":
        start_d = datetime.date.fromisoformat(time_spec["start"])
        end_d = datetime.date.fromisoformat(time_spec["end"])
        if end_d < data_start_date or start_d > wm_date:
            return {
                "status": "no_data",
                "result": copy.deepcopy(execution_result),
                "warnings": ["no_data_for_period"],
                "checks": checks,
            }
        # Detect partial data per watermark / unclosed month
        if end_d > wm_date or end_d.strftime("%Y-%m") > last_closed_month:
            if "partial_data_watermark" not in warnings:
                warnings.append("partial_data_watermark")
    elif time_spec["mode"] == "as_of":
        as_of_d = datetime.date.fromisoformat(time_spec["as_of"])
        if as_of_d < data_start_date:
            return {
                "status": "no_data",
                "result": copy.deepcopy(execution_result),
                "warnings": ["no_data_for_period"],
                "checks": checks,
            }
        if as_of_d > wm_date:
            warnings.append("partial_data_watermark")

    if len(rows) == 0:
        return {
            "status": "no_data",
            "result": copy.deepcopy(execution_result),
            "warnings": warnings + ["no_data_found"],
            "checks": checks,
        }

    status = "partial" if "partial_data_watermark" in warnings else "valid"
    return {
        "status": status,
        "result": copy.deepcopy(execution_result),
        "warnings": warnings,
        "checks": checks,
    }


def generate_grounded_answer(
    validated_plan: dict[str, Any],
    validated_result: dict[str, Any],
    catalog: MetricCatalog,
    locale: str = "vi-VN",
) -> dict[str, Any]:
    """Implements Contract 22: answer.generation.v1 using deterministic grounded templates."""
    res = validated_result["result"]
    rows = res.get("rows", [])
    warnings = list(validated_result.get("warnings", []))
    metric_ids = validated_plan["metric_ids"]

    if validated_result["status"] == "no_data" or not rows:
        msg = (
            "Không có dữ liệu phù hợp cho kỳ truy vấn."
            if locale == "vi-VN"
            else "No matching financial data found for the requested period."
        )
        return {
            "summary": msg,
            "claims": [],
            "warnings": warnings,
            "table_caption": None,
        }

    first_row = rows[0]
    parts: list[str] = []
    claims: list[dict[str, Any]] = []
    for m_id in metric_ids:
        m = catalog.get(m_id)
        assert m is not None
        label = m["label"] if locale == "vi-VN" else m.get("label_en", m["label"])
        val = first_row.get(m_id)
        val_str = "N/A" if val is None else f"{val} {m['unit']}"
        claim_text = f"{label}: {val_str}"
        parts.append(claim_text)
        claims.append(
            {
                "text": claim_text,
                "source_columns": [m_id],
                "source_rows": [0],
            }
        )

    summary = "; ".join(parts) + "."
    if "partial_data_watermark" in warnings:
        wm = res.get("data_watermark", "2026-10-14")
        note = (
            f" Lưu ý: Dữ liệu đang ở trạng thái partial (cập nhật đến {wm})."
            if locale == "vi-VN"
            else f" Note: Data is partial (updated through {wm})."
        )
        summary += note

    return {
        "summary": summary,
        "claims": claims,
        "warnings": warnings,
        "table_caption": f"Result ({len(rows)} rows)",
    }


def validate_answer(
    answer_draft: dict[str, Any],
    validated_result: dict[str, Any],
    validated_plan: dict[str, Any],
    catalog: MetricCatalog,
    locale: str = "vi-VN",
    fallback_on_failure: bool = True,
) -> dict[str, Any]:
    """Implements Contract 23: answer.validation.v1."""
    stage = "answer_validation"
    summary = answer_draft.get("summary", "")
    claims = answer_draft.get("claims", [])
    draft_warnings = list(answer_draft.get("warnings") or [])
    required_warnings = list(validated_result.get("warnings") or [])
    rows = validated_result["result"].get("rows", [])
    plan_metrics = set(validated_plan["metric_ids"])

    def _fail_or_fallback(reason: str) -> dict[str, Any]:
        if fallback_on_failure:
            safe_draft = generate_grounded_answer(validated_plan, validated_result, catalog, locale=locale)
            return {
                "status": "valid",
                "answer": safe_draft["summary"],
                "validated_claims": [
                    {
                        "source_columns": c["source_columns"],
                        "source_rows": c["source_rows"],
                        "verified": True,
                    }
                    for c in safe_draft["claims"]
                ],
                "warnings": safe_draft["warnings"],
                "used_fallback": True,
                "rejection_reason": reason,
            }
        raise ContractError("ungrounded_answer", stage, reason, final_status="error")

    # 1. Reject SQL or prompt injection leak in answer
    if FORBIDDEN_SQL_PATTERNS.search(summary) or INJECTION_PATTERNS.search(summary):
        return _fail_or_fallback("Answer contains SQL or prompt injection content.")

    # 2. Reject causal speculation not grounded in data
    if CAUSAL_SPECULATION_PATTERNS.search(summary):
        return _fail_or_fallback("Answer contains unverified causal speculation.")

    # 3. Reject if required partial/no-data warning was dropped
    for req_w in required_warnings:
        if req_w not in draft_warnings:
            return _fail_or_fallback(f"Answer omitted required warning '{req_w}'.")

    # 4. Reject if answer mentions unrequested catalog metrics
    summary_masked = summary.lower()
    for pm_id in plan_metrics:
        pm = catalog.get(pm_id)
        if pm:
            summary_masked = summary_masked.replace(pm["label"].lower(), "")
            if pm.get("label_en"):
                summary_masked = summary_masked.replace(pm["label_en"].lower(), "")
    for m_id, m in catalog._metrics.items():
        if m_id not in plan_metrics:
            if m["label"].lower() in summary_masked or (
                m.get("label_en") and m["label_en"].lower() in summary_masked
            ):
                return _fail_or_fallback(f"Answer mentions metric '{m_id}' outside ValidatedPlan.")

    # 5. Verify every claim maps to result rows and numbers match
    validated_claims: list[dict[str, Any]] = []
    for cl in claims:
        src_cols = cl.get("source_columns") or []
        src_rows = cl.get("source_rows") or []
        text = cl.get("text", "")
        if not src_cols or not src_rows:
            return _fail_or_fallback("Claim does not map to source_columns and source_rows.")
        if not set(src_cols).issubset(plan_metrics):
            return _fail_or_fallback("Claim references column outside ValidatedPlan.")
        for r_idx in src_rows:
            if not isinstance(r_idx, int) or r_idx < 0 or r_idx >= len(rows):
                return _fail_or_fallback("Claim references out-of-range row index.")
            row_data = rows[r_idx]
            for col in src_cols:
                expected_val = row_data.get(col)
                if expected_val is not None and str(expected_val) not in text:
                    return _fail_or_fallback(
                        f"Number mismatch in claim: expected '{expected_val}' in '{text}'."
                    )
        validated_claims.append(
            {
                "source_columns": list(src_cols),
                "source_rows": list(src_rows),
                "verified": True,
            }
        )

    return {
        "status": "valid",
        "answer": summary,
        "validated_claims": validated_claims,
        "warnings": draft_warnings,
        "used_fallback": False,
    }


def build_final_response(
    request_id: str,
    status: str,
    error: dict[str, Any] | None = None,
    answer: str | None = None,
    execution_result: dict[str, Any] | None = None,
    validated_plan: dict[str, Any] | None = None,
    bound_query: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    include_table: bool = True,
) -> dict[str, Any]:
    """Implements Contract 24: query.response.v1."""
    if status not in FINAL_STATUSES:
        raise ContractError("invalid_request", "final_response", f"Invalid final status '{status}'.")

    data_block = None
    if execution_result is not None and status in {"ready", "no_data"}:
        data_block = {
            "columns": execution_result["columns"] if include_table else [],
            "rows": execution_result["rows"] if include_table else [],
            "row_count": execution_result["row_count"],
            "truncated": execution_result["truncated"],
        }

    interpretation = None
    if validated_plan is not None and validated_plan.get("status") == "validated":
        interpretation = {
            "metric_ids": validated_plan["metric_ids"],
            "dimensions": validated_plan["dimensions"],
            "view": validated_plan["view"],
            "time": validated_plan["time"],
        }

    provenance = None
    if bound_query is not None and execution_result is not None:
        provenance = {
            "catalog_hash": bound_query["catalog_hash"],
            "data_watermark": execution_result["data_watermark"],
            "source": bound_query["source"],
            "query_fingerprint": bound_query["fingerprint"],
        }

    return {
        "api_version": "v1",
        "request_id": request_id,
        "status": status,
        "error": error,
        "answer": answer,
        "data": data_block,
        "interpretation": interpretation,
        "provenance": provenance,
        "warnings": list(warnings or []),
    }


def build_observability_record(
    request_id: str,
    trace_id: str,
    stage_latencies_ms: dict[str, int],
    catalog_hash: str,
    embedding_model: str,
    candidate_count: int,
    selected_metric_ids: list[str],
    fewshot_example_ids: list[str],
    token_usage: int,
    query_fingerprint: str | None,
    row_count: int,
    truncated: bool,
    data_watermark: str | None,
    final_status: str,
    error_code: str | None = None,
) -> dict[str, Any]:
    """Implements Contract 25: observability.pipeline.v1."""
    return {
        "contract_version": "observability.pipeline.v1",
        "request_id": request_id,
        "trace_id": trace_id,
        "stage_latencies_ms": dict(stage_latencies_ms),
        "catalog_hash": catalog_hash,
        "embedding_model": embedding_model,
        "candidate_count": int(candidate_count),
        "selected_metric_ids": list(selected_metric_ids),
        "fewshot_example_ids": list(fewshot_example_ids),
        "token_usage": int(token_usage),
        "query_fingerprint": query_fingerprint,
        "row_count": int(row_count),
        "truncated": bool(truncated),
        "data_watermark": data_watermark,
        "final_status": final_status,
        "error_code": error_code,
    }
