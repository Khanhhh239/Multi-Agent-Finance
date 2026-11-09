"""Governed metric catalog and production visibility rules."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from .errors import ContractError

CATALOG_VERSION = "2026.11.1"


def _definition(
    metric_id: str,
    label: str,
    label_en: str,
    description: str,
    aliases: tuple[str, ...],
    unit: str,
    kind: str,
    period_type: str,
    supported_views: tuple[str, ...],
    supported_dimensions: tuple[str, ...],
    supported_operations: tuple[str, ...],
    sql_expr: str,
    *,
    base_relation: str = "view",
    status: str = "approved",
    verified_handler: bool = True,
) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "label": label,
        "label_en": label_en,
        "description": description,
        "aliases": list(aliases),
        "unit": unit,
        "kind": kind,
        "period_type": period_type,
        "supported_views": list(supported_views),
        "supported_dimensions": list(supported_dimensions),
        "supported_operations": list(supported_operations),
        "default_view": "mgmt",
        "status": status,
        "owner": "finance",
        "catalog_version": CATALOG_VERSION,
        "verified_handler": verified_handler,
        "sql_expr": sql_expr,
        "base_relation": base_relation,
    }


DEFAULT_METRICS_DEFINITIONS: list[dict[str, Any]] = [
    _definition(
        "net_revenue",
        "Doanh thu thuần",
        "Net Revenue",
        "Tổng doanh thu bán hàng và cung cấp dịch vụ thuần (TK 511)",
        (
            "doanh thu",
            "doanh thu thuần",
            "doanh số",
            "net revenue",
            "revenue",
            "sales",
            "total revenue",
        ),
        "VND",
        "amount",
        "flow",
        ("mgmt", "tax", "gl"),
        ("month", "quarter", "year", "branch_code", "product_line", "partner_code", "segment"),
        ("aggregate", "timeseries", "breakdown", "ranking", "comparison"),
        "COALESCE(SUM(CASE WHEN account_code LIKE '511%' THEN credit_amount - debit_amount ELSE 0 END), 0)",
    ),
    _definition(
        "cogs",
        "Giá vốn hàng bán",
        "Cost of Goods Sold",
        "Tổng giá vốn hàng bán trong kỳ (TK 632)",
        ("giá vốn", "giá vốn hàng bán", "cogs", "cost of goods sold", "cost of sales"),
        "VND",
        "amount",
        "flow",
        ("mgmt", "tax", "gl"),
        ("month", "quarter", "year", "branch_code", "product_line"),
        ("aggregate", "timeseries", "breakdown", "comparison"),
        "COALESCE(SUM(CASE WHEN account_code LIKE '632%' THEN debit_amount - credit_amount ELSE 0 END), 0)",
    ),
    _definition(
        "gross_profit",
        "Lợi nhuận gộp",
        "Gross Profit",
        "Doanh thu thuần trừ giá vốn hàng bán (TK 511 - TK 632)",
        ("lợi nhuận gộp", "lãi gộp", "gross profit"),
        "VND",
        "amount",
        "flow",
        ("mgmt", "tax", "gl"),
        ("month", "quarter", "year", "branch_code", "product_line"),
        ("aggregate", "timeseries", "breakdown", "ranking", "comparison"),
        "COALESCE(SUM(CASE WHEN account_code LIKE '511%' THEN credit_amount - debit_amount WHEN account_code LIKE '632%' THEN -(debit_amount - credit_amount) ELSE 0 END), 0)",
    ),
    _definition(
        "gross_margin",
        "Biên lợi nhuận gộp",
        "Gross Profit Margin",
        "Tỷ lệ lợi nhuận gộp chia cho doanh thu thuần (%)",
        (
            "biên lợi nhuận gộp",
            "biên lãi gộp",
            "tỷ suất lợi nhuận gộp",
            "gross margin",
            "gross profit margin",
        ),
        "%",
        "ratio",
        "flow",
        ("mgmt", "tax"),
        ("month", "quarter", "year", "branch_code", "product_line"),
        ("aggregate", "timeseries", "breakdown", "comparison"),
        "CASE WHEN SUM(CASE WHEN account_code LIKE '511%' THEN credit_amount - debit_amount ELSE 0 END) = 0 THEN NULL ELSE ROUND((SUM(CASE WHEN account_code LIKE '511%' THEN credit_amount - debit_amount WHEN account_code LIKE '632%' THEN -(debit_amount - credit_amount) ELSE 0 END) * 100.0) / NULLIF(SUM(CASE WHEN account_code LIKE '511%' THEN credit_amount - debit_amount ELSE 0 END), 0), 2) END",
    ),
    _definition(
        "operating_expense",
        "Chi phí hoạt động",
        "Operating Expense",
        "Chi phí quản lý kinh doanh bao gồm chi phí bán hàng và quản lý doanh nghiệp (TK 642)",
        (
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
        ),
        "VND",
        "amount",
        "flow",
        ("mgmt", "tax", "gl"),
        ("month", "quarter", "year", "branch_code", "department_code", "cost_category"),
        ("aggregate", "timeseries", "breakdown", "ranking", "comparison"),
        "COALESCE(SUM(CASE WHEN account_code LIKE '642%' THEN debit_amount - credit_amount ELSE 0 END), 0)",
    ),
    _definition(
        "net_profit",
        "Lợi nhuận ròng",
        "Net Profit",
        "Lợi nhuận sau thuế thu nhập doanh nghiệp (Doanh thu 511, 515, 711 trừ Chi phí 632, 635, 642, 811, 821)",
        ("lợi nhuận ròng", "lợi nhuận sau thuế", "lãi ròng", "net profit", "net income"),
        "VND",
        "amount",
        "flow",
        ("mgmt", "tax"),
        ("month", "quarter", "year", "branch_code"),
        ("aggregate", "timeseries", "breakdown", "comparison"),
        "COALESCE(SUM(CASE WHEN account_type = 'REVENUE' THEN credit_amount - debit_amount WHEN account_type = 'EXPENSE' THEN -(debit_amount - credit_amount) ELSE 0 END), 0)",
    ),
    _definition(
        "net_profit_margin",
        "Biên lợi nhuận ròng",
        "Net Profit Margin",
        "Lợi nhuận ròng chia cho doanh thu thuần (%)",
        ("biên lợi nhuận ròng", "tỷ suất lợi nhuận ròng", "net profit margin", "net margin"),
        "%",
        "ratio",
        "flow",
        ("mgmt", "tax"),
        ("month", "quarter", "year", "branch_code"),
        ("aggregate", "timeseries", "breakdown", "comparison"),
        "CASE WHEN SUM(CASE WHEN account_code LIKE '511%' THEN credit_amount - debit_amount ELSE 0 END) = 0 THEN NULL ELSE ROUND((SUM(CASE WHEN account_type = 'REVENUE' THEN credit_amount - debit_amount WHEN account_type = 'EXPENSE' THEN -(debit_amount - credit_amount) ELSE 0 END) * 100.0) / NULLIF(SUM(CASE WHEN account_code LIKE '511%' THEN credit_amount - debit_amount ELSE 0 END), 0), 2) END",
    ),
    _definition(
        "payroll_expense",
        "Chi phí lương và bảo hiểm",
        "Payroll and Insurance Expense",
        "Chi phí lương, thưởng và bảo hiểm trích theo lương trong kỳ",
        (
            "chi phí lương",
            "chi phí nhân sự",
            "quỹ lương",
            "payroll",
            "payroll expense",
            "salary expense",
        ),
        "VND",
        "amount",
        "flow",
        ("mgmt", "tax"),
        ("month", "quarter", "year", "branch_code", "department_code"),
        ("aggregate", "timeseries", "breakdown", "comparison"),
        "COALESCE(SUM(CASE WHEN cost_category IN ('LUONG', 'BAOHIEM', 'THUONG') AND account_code LIKE '642%' THEN debit_amount - credit_amount ELSE 0 END), 0)",
    ),
    _definition(
        "cash_balance",
        "Số dư tiền và tương đương tiền",
        "Cash and Bank Balance",
        "Số dư tiền mặt (TK 111) và tiền gửi ngân hàng (TK 112) tại thời điểm as_of",
        (
            "số dư tiền",
            "số dư tiền mặt",
            "tiền gửi ngân hàng",
            "cash balance",
            "cash and bank balance",
        ),
        "VND",
        "amount",
        "snapshot",
        ("mgmt", "gl"),
        ("branch_code",),
        ("aggregate", "breakdown"),
        "COALESCE(SUM(CASE WHEN account_code LIKE '111%' OR account_code LIKE '112%' THEN debit_amount - credit_amount ELSE 0 END), 0)",
    ),
    _definition(
        "ar_balance",
        "Số dư nợ phải thu khách hàng",
        "Accounts Receivable Balance",
        "Tổng dư nợ phải thu khách hàng (TK 131) tại thời điểm as_of",
        (
            "nợ phải thu",
            "phải thu khách hàng",
            "số dư phải thu",
            "accounts receivable",
            "ar balance",
            "receivables",
        ),
        "VND",
        "amount",
        "snapshot",
        ("mgmt", "gl"),
        ("branch_code", "partner_code", "segment"),
        ("aggregate", "breakdown", "ranking"),
        "COALESCE(SUM(CASE WHEN account_code LIKE '131%' THEN debit_amount - credit_amount ELSE 0 END), 0)",
    ),
    _definition(
        "ap_balance",
        "Số dư nợ phải trả nhà cung cấp",
        "Accounts Payable Balance",
        "Tổng dư nợ phải trả người bán (TK 331) tại thời điểm as_of",
        (
            "nợ phải trả",
            "phải trả nhà cung cấp",
            "phải trả người bán",
            "accounts payable",
            "ap balance",
            "payables",
        ),
        "VND",
        "amount",
        "snapshot",
        ("mgmt", "gl"),
        ("branch_code", "partner_code"),
        ("aggregate", "breakdown", "ranking"),
        "COALESCE(SUM(CASE WHEN account_code LIKE '331%' THEN credit_amount - debit_amount ELSE 0 END), 0)",
    ),
    _definition(
        "loan_balance",
        "Tổng dư nợ vay",
        "Total Loan Balance",
        "Tổng dư nợ vay ngắn hạn và dài hạn (TK 341) tại thời điểm as_of",
        (
            "dư nợ vay",
            "nợ vay ngân hàng",
            "vay ngân hàng",
            "loan balance",
            "total debt",
            "bank loan",
        ),
        "VND",
        "amount",
        "snapshot",
        ("mgmt", "gl"),
        ("branch_code",),
        ("aggregate", "breakdown"),
        "COALESCE(SUM(CASE WHEN account_code LIKE '341%' THEN credit_amount - debit_amount ELSE 0 END), 0)",
    ),
    _definition(
        "budget_amount",
        "Ngân sách kế hoạch",
        "Budget Amount",
        "Ngân sách chi phí/doanh thu được duyệt theo kỳ và chi nhánh",
        ("ngân sách", "dự toán", "kế hoạch ngân sách", "budget", "budget amount"),
        "VND",
        "amount",
        "flow",
        ("mgmt",),
        ("month", "year", "branch_code", "cost_category"),
        ("aggregate", "breakdown", "timeseries"),
        "COALESCE(SUM(amount), 0)",
        base_relation="budget",
    ),
    _definition(
        "experimental_cash_burn",
        "Tốc độ đốt tiền thử nghiệm",
        "Experimental Cash Burn Rate",
        "Metric thử nghiệm chưa được CFO phê duyệt",
        ("cash burn", "tốc độ đốt tiền"),
        "VND",
        "amount",
        "flow",
        ("mgmt",),
        ("month",),
        ("aggregate",),
        "0",
        status="draft",
    ),
    _definition(
        "unverified_custom_kpi",
        "KPI tùy chỉnh chưa kiểm chứng nguồn",
        "Unverified Custom KPI",
        "Metric có status approved nhưng handler chưa được verify",
        ("unverified kpi",),
        "VND",
        "amount",
        "flow",
        ("mgmt",),
        ("month",),
        ("aggregate",),
        "0",
        base_relation="unknown_table",
        verified_handler=False,
    ),
]


class MetricCatalog:
    """Source of truth for metric definitions and production visibility."""

    def __init__(self, metrics: list[dict[str, Any]] | None = None) -> None:
        raw_metrics = copy.deepcopy(DEFAULT_METRICS_DEFINITIONS if metrics is None else metrics)
        self._metrics = {metric["metric_id"]: metric for metric in raw_metrics}
        blob = json.dumps(raw_metrics, sort_keys=True, ensure_ascii=False)
        self._catalog_hash = "catalog-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]

    def get(self, metric_id: str) -> dict[str, Any] | None:
        """Return an isolated metric definition, or ``None`` when unknown."""

        metric = self._metrics.get(metric_id)
        return copy.deepcopy(metric) if metric is not None else None

    def contains(self, metric_id: str) -> bool:
        return metric_id in self._metrics

    def list_approved_metrics(self) -> list[dict[str, Any]]:
        """Return an isolated, ordered snapshot for offline document building."""
        return [
            copy.deepcopy(metric)
            for _, metric in sorted(self._metrics.items())
            if metric["status"] == "approved"
        ]

    def get_capability(self, metric_id: str) -> dict[str, Any]:
        """Return the governed capability surface for one metric."""

        metric = self._metrics.get(metric_id)
        if metric is None:
            raise ContractError(
                "unknown_metric",
                "metric_catalog",
                f"Metric '{metric_id}' not found.",
            )
        return {
            "metric_id": metric["metric_id"],
            "unit": metric["unit"],
            "kind": metric["kind"],
            "period_type": metric["period_type"],
            "supported_views": copy.deepcopy(metric["supported_views"]),
            "supported_dimensions": copy.deepcopy(metric["supported_dimensions"]),
            "supported_operations": copy.deepcopy(metric["supported_operations"]),
            "default_view": metric["default_view"],
            "status": metric["status"],
            "verified_handler": metric["verified_handler"],
        }

    def list_visible_metrics(self, auth_context: dict[str, Any]) -> list[dict[str, Any]]:
        """List approved, verified metrics authorized for at least one view."""

        allowed_views = set(auth_context.get("allowed_views") or [])
        allowed_metrics_value = auth_context.get("allowed_metrics")
        allowed_metrics = set(allowed_metrics_value) if allowed_metrics_value is not None else None
        visible: list[dict[str, Any]] = []
        for metric in self._metrics.values():
            if metric["status"] != "approved":
                continue
            if metric.get("verified_handler") is not True:
                continue
            if allowed_metrics is not None and metric["metric_id"] not in allowed_metrics:
                continue
            if not allowed_views.intersection(metric["supported_views"]):
                continue
            visible.append(copy.deepcopy(metric))
        return visible

    def get_catalog_hash(self) -> str:
        return self._catalog_hash
