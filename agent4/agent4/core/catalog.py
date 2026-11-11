"""Governed metric catalog and production visibility rules."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Collection
from typing import Any

from agent4.engine.metrics import REGISTRY, MetricDef, Term

from .errors import ContractError

CATALOG_VERSION = "2026.11.2"

LEGACY_METRIC_IDS = {
    "gross_margin": "gross_margin_pct",
    "operating_expense": "operating_expenses",
    "net_profit_margin": "net_margin_pct",
    "payroll_expense": "labor_cost",
    "cash_balance": "cash_and_equivalents",
    "loan_balance": "debt_balance",
}
CANONICAL_TO_LEGACY = {canonical: legacy for legacy, canonical in LEGACY_METRIC_IDS.items()}
_LEGACY_PERCENT_IDS = {"gross_margin", "net_profit_margin"}
_EXPENSE_DIMENSIONS = (
    "month",
    "quarter",
    "year",
    "branch_code",
    "department_code",
    "cost_category",
    "partner_code",
)
_PROFIT_DIMENSIONS = _EXPENSE_DIMENSIONS[:5]
_RATIO_DIMENSIONS = ("month", "quarter", "year", "branch_code")


def _ledger_sum(terms: tuple[Term, ...]) -> str:
    amounts = {
        "net_debit": "debit_amount - credit_amount",
        "net_credit": "credit_amount - debit_amount",
    }
    expressions = []
    for term in terms:
        accounts = " OR ".join(f"account_code LIKE '{prefix}%'" for prefix in term.prefixes)
        condition = f"({accounts}) AND {term.where}" if term.where else accounts
        amount = amounts[term.measure]
        if term.coef == -1:
            amount = f"-({amount})"
        elif term.coef != 1:
            raise ValueError("Unsupported ledger coefficient")
        expressions.append(f"CASE WHEN {condition} THEN {amount} ELSE 0 END")
    return f"COALESCE(SUM({' + '.join(expressions)}), 0)"


def _ratio(
    numerator: tuple[Term, ...], denominator: tuple[Term, ...], *, percent: bool = False
) -> str:
    # DuckDB decimal division returns a double. Divide integer cents and round
    # half away from zero before converting the result back to a fixed scale.
    scale, places = (10_000, 2) if percent else (1_000_000, 6)
    num = f"CAST({_ledger_sum(numerator)} * 100 AS HUGEINT)"
    den = f"CAST({_ledger_sum(denominator)} * 100 AS HUGEINT)"
    rounded = f"((ABS({num}) * {scale} + ABS({den}) // 2) // NULLIF(ABS({den}), 0))"
    return f"CAST(SIGN({num}) * SIGN({den}) * {rounded} * 0.{'0' * (places - 1)}1 AS DECIMAL(38, {places}))"


def metric_def_to_catalog_dict(
    metric: MetricDef, *, status: str = "approved", verified_handler: bool = False
) -> dict[str, Any]:
    operations = ["aggregate", "compare", "comparison"]
    if {"month", "quarter", "year"}.intersection(metric.group_bys):
        operations.append("timeseries")
    if metric.group_bys:
        operations.extend(("breakdown", "rank", "ranking"))
    return {
        "metric_id": metric.id,
        "label": metric.label,
        "description": metric.description,
        "aliases": list(metric.synonyms),
        "category": metric.category,
        "unit": metric.unit,
        "kind": metric.kind,
        "period_type": metric.period_type,
        "supported_views": list(metric.views),
        "supported_dimensions": list(metric.group_bys),
        "supported_operations": operations,
        "default_view": metric.default_view,
        "status": status,
        "verified_handler": verified_handler,
        "metadata_only": not verified_handler,
        "owner": "finance",
        "catalog_version": CATALOG_VERSION,
    }


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
        "null_on_divide_by_zero": kind == "ratio",
    }


def _amount(terms: tuple[Term, ...]) -> str:
    return f"ROUND({_ledger_sum(terms)}, 2)"


def _warehouse_metric(
    metric_id: str,
    label_en: str,
    description: str,
    dimensions: tuple[str, ...],
    sql_expr: str,
) -> dict[str, Any]:
    metric = REGISTRY[metric_id]
    operations = ("aggregate", "breakdown")
    if metric.period_type == "flow":
        operations += ("timeseries", "ranking", "comparison")
    return _definition(
        metric.id,
        metric.label,
        label_en,
        description,
        metric.synonyms,
        metric.unit,
        "ratio" if metric.kind == "ratio" else "amount",
        metric.period_type,
        metric.views,
        dimensions,
        operations,
        sql_expr,
    )


_OPERATING_PROFIT = (*REGISTRY["gross_profit"].terms, Term(("641", "642"), -1))
_PROFIT_BEFORE_TAX = (
    *_OPERATING_PROFIT,
    Term(("711",), measure="net_credit"),
    Term(("811", "635"), -1),
)
_INVENTORY = ("152", "155", "156")
_QUICK_ASSETS = ("111", "112", "131")
_CURRENT_LIABILITIES = (Term(("331", "333", "334", "34111"), measure="net_credit"),)
_TOTAL_LIABILITIES = (Term(("331", "333", "334", "341"), measure="net_credit"),)
_TOTAL_EQUITY = (
    Term(("411", "421"), measure="net_credit"),
    Term(
        ("511", "711"),
        measure="net_credit",
        where="NOT is_closing AND source_module IS DISTINCT FROM 'OPENING'",
    ),
    Term(
        ("521", "632", "641", "642", "635", "811", "821"),
        -1,
        where="NOT is_closing AND source_module IS DISTINCT FROM 'OPENING'",
    ),
)


_EXECUTABLE_DEFINITIONS = [
    _definition(
        "net_revenue",
        "Doanh thu thuần",
        "Net Revenue",
        "Doanh thu bán hàng và cung cấp dịch vụ thuần (TK 511 sau giảm trừ TK 521)",
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
        _amount(REGISTRY["net_revenue"].terms),
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
        _amount(REGISTRY["cogs"].terms),
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
        _amount(REGISTRY["gross_profit"].terms),
    ),
    _definition(
        "gross_margin_pct",
        "Biên lợi nhuận gộp",
        "Gross Profit Margin",
        "Tỷ lệ lợi nhuận gộp chia cho doanh thu thuần",
        (
            "biên lợi nhuận gộp",
            "biên lãi gộp",
            "tỷ suất lợi nhuận gộp",
            "gross margin",
            "gross profit margin",
        ),
        "ratio",
        "ratio",
        "flow",
        ("mgmt", "tax"),
        ("month", "quarter", "year", "branch_code", "product_line"),
        ("aggregate", "timeseries", "breakdown", "comparison"),
        _ratio(REGISTRY["gross_margin_pct"].num, REGISTRY["gross_margin_pct"].den),
    ),
    _definition(
        "operating_expenses",
        "Chi phí hoạt động",
        "Operating Expense",
        "Chi phí quản lý kinh doanh bao gồm chi phí bán hàng và quản lý doanh nghiệp (TK 641, 642)",
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
        _EXPENSE_DIMENSIONS,
        ("aggregate", "timeseries", "breakdown", "ranking", "comparison"),
        _amount(REGISTRY["operating_expenses"].terms),
    ),
    _definition(
        "net_profit",
        "Lợi nhuận ròng",
        "Net Profit",
        "Lợi nhuận sau thuế (TK 511, 515, 711 trừ TK 521, 632, 635, 641, 642, 811, 821)",
        ("lợi nhuận ròng", "lợi nhuận sau thuế", "lãi ròng", "net profit", "net income"),
        "VND",
        "amount",
        "flow",
        ("mgmt", "tax"),
        ("month", "quarter", "year", "branch_code"),
        ("aggregate", "timeseries", "breakdown", "comparison"),
        _amount(REGISTRY["net_profit"].terms),
    ),
    _definition(
        "net_margin_pct",
        "Biên lợi nhuận ròng",
        "Net Profit Margin",
        "Lợi nhuận ròng chia cho doanh thu thuần",
        ("biên lợi nhuận ròng", "tỷ suất lợi nhuận ròng", "net profit margin", "net margin"),
        "ratio",
        "ratio",
        "flow",
        ("mgmt", "tax"),
        ("month", "quarter", "year", "branch_code"),
        ("aggregate", "timeseries", "breakdown", "comparison"),
        _ratio(REGISTRY["net_margin_pct"].num, REGISTRY["net_margin_pct"].den),
    ),
    _definition(
        "labor_cost",
        "Chi phí lương và bảo hiểm",
        "Payroll and Insurance Expense",
        "Chi phí lương, thưởng và bảo hiểm trích theo lương trong kỳ",
        (
            "chi phí lương",
            "chi phí nhân sự",
            "quỹ lương",
            "payroll",
            "payroll expense",
            "labor cost",
        ),
        "VND",
        "amount",
        "flow",
        ("mgmt", "tax"),
        ("month", "quarter", "year", "branch_code", "department_code"),
        ("aggregate", "timeseries", "breakdown", "comparison"),
        _amount(REGISTRY["labor_cost"].terms),
    ),
    _definition(
        "cash_and_equivalents",
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
        _amount(REGISTRY["cash_and_equivalents"].terms),
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
        _amount(REGISTRY["ar_balance"].terms),
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
        _amount(REGISTRY["ap_balance"].terms),
    ),
    _definition(
        "debt_balance",
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
        _amount(REGISTRY["debt_balance"].terms),
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
        "ROUND(COALESCE(SUM(amount), 0), 2)",
        base_relation="budget",
    ),
]


_NEW_EXECUTABLE_DEFINITIONS = [
    _warehouse_metric(
        "admin_expenses",
        "Administrative Expenses",
        "Chi phí quản lý doanh nghiệp (TK 642)",
        _EXPENSE_DIMENSIONS,
        _amount((Term(("642",)),)),
    ),
    _warehouse_metric(
        "selling_expenses",
        "Selling Expenses",
        "Chi phí bán hàng (TK 641)",
        _EXPENSE_DIMENSIONS,
        _amount((Term(("641",)),)),
    ),
    _warehouse_metric(
        "salary_expense",
        "Salary Expense",
        "Chi phí lương (TK 641, 642, 154, khoản mục LUONG)",
        _EXPENSE_DIMENSIONS[:-1],
        _amount((Term(("641", "642", "154"), where="cost_category = 'LUONG'"),)),
    ),
    _warehouse_metric(
        "operating_profit",
        "Operating Profit",
        "Doanh thu thuần trừ giá vốn và chi phí hoạt động",
        _PROFIT_DIMENSIONS,
        _amount(_OPERATING_PROFIT),
    ),
    _warehouse_metric(
        "profit_before_tax",
        "Profit Before Tax",
        "Lợi nhuận hoạt động cộng thu nhập khác, trừ chi phí khác và chi phí tài chính",
        _PROFIT_DIMENSIONS,
        _amount(_PROFIT_BEFORE_TAX),
    ),
    _warehouse_metric(
        "income_tax_expense",
        "Income Tax Expense",
        "Chi phí thuế thu nhập doanh nghiệp (TK 821)",
        _PROFIT_DIMENSIONS,
        _amount(REGISTRY["income_tax_expense"].terms),
    ),
    _warehouse_metric(
        "current_ratio",
        "Current Ratio",
        "Tài sản ngắn hạn chia cho nợ ngắn hạn",
        _RATIO_DIMENSIONS,
        _ratio((Term((*_QUICK_ASSETS, *_INVENTORY)),), _CURRENT_LIABILITIES),
    ),
    _warehouse_metric(
        "quick_ratio",
        "Quick Ratio",
        "Tài sản ngắn hạn sau khi trừ hàng tồn kho chia cho nợ ngắn hạn",
        _RATIO_DIMENSIONS,
        _ratio((Term(_QUICK_ASSETS),), _CURRENT_LIABILITIES),
    ),
    _warehouse_metric(
        "debt_to_equity",
        "Debt to Equity",
        "Tổng nợ phải trả chia cho vốn chủ sở hữu",
        _RATIO_DIMENSIONS,
        _ratio(_TOTAL_LIABILITIES, _TOTAL_EQUITY),
    ),
]
_EXECUTABLE_BY_ID = {
    metric["metric_id"]: metric
    for metric in (*_EXECUTABLE_DEFINITIONS, *_NEW_EXECUTABLE_DEFINITIONS)
}

_PLACEHOLDER_DEFINITIONS = [
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
        verified_handler=False,
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


CANONICAL_METRIC_DEFINITIONS = [
    *(
        _EXECUTABLE_BY_ID.get(metric.id) or metric_def_to_catalog_dict(metric)
        for metric in REGISTRY.values()
    ),
    _EXECUTABLE_BY_ID["budget_amount"],
    *(
        metric_def_to_catalog_dict(MetricDef(metric_id, label, label, "custom", unit, category, ""))
        for metric_id, label, unit, category in (
            ("free_cash_flow", "Dòng tiền tự do", "VND", "cash flow"),
            ("altman_z_score", "Điểm Altman Z", "ratio", "ratio"),
        )
    ),
    *_PLACEHOLDER_DEFINITIONS,
]


def _legacy_definition(alias: str, metric: dict[str, Any]) -> dict[str, Any]:
    definition = {**metric, "metric_id": alias}
    if alias in _LEGACY_PERCENT_IDS:
        definition["unit"] = "%"
        if metric.get("sql_expr") == _EXECUTABLE_BY_ID[metric["metric_id"]]["sql_expr"]:
            canonical = REGISTRY[metric["metric_id"]]
            definition["sql_expr"] = _ratio(canonical.num, canonical.den, percent=True)
    return definition


DEFAULT_METRICS_DEFINITIONS = [
    *(
        _legacy_definition(CANONICAL_TO_LEGACY[metric["metric_id"]], metric)
        if metric["metric_id"] in CANONICAL_TO_LEGACY
        else metric
        for metric in _EXECUTABLE_DEFINITIONS
    ),
    *_PLACEHOLDER_DEFINITIONS,
]


class MetricCatalog:
    """Look up both built-in namespaces and enumerate the selected one by default.

    Pass canonical=True to enumerate canonical metrics. An explicit allowlist
    can include IDs from either namespace. Custom metric lists define their
    own catalog.
    """

    def __init__(
        self, metrics: list[dict[str, Any]] | None = None, *, canonical: bool = False
    ) -> None:
        primary = CANONICAL_METRIC_DEFINITIONS if canonical else DEFAULT_METRICS_DEFINITIONS
        raw_metrics = copy.deepcopy(primary if metrics is None else metrics)
        self._metrics = {metric["metric_id"]: metric for metric in raw_metrics}
        if metrics is None:
            supplemental = (
                DEFAULT_METRICS_DEFINITIONS if canonical else CANONICAL_METRIC_DEFINITIONS
            )
            self._additional = {
                metric["metric_id"]: copy.deepcopy(metric)
                for metric in supplemental
                if metric["metric_id"] not in self._metrics
            }
        else:
            self._additional = {
                alias: _legacy_definition(alias, self._metrics[canonical_id])
                for alias, canonical_id in LEGACY_METRIC_IDS.items()
                if alias not in self._metrics and canonical_id in self._metrics
            }
        blob = json.dumps([raw_metrics, self._additional], sort_keys=True, ensure_ascii=False)
        self._catalog_hash = "catalog-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]

    def _find(self, metric_id: str) -> dict[str, Any] | None:
        return self._metrics.get(metric_id) or self._additional.get(metric_id)

    def get(self, metric_id: str) -> dict[str, Any] | None:
        """Return an isolated metric definition, or ``None`` when unknown."""

        metric = self._find(metric_id)
        return copy.deepcopy(metric) if metric is not None else None

    def contains(self, metric_id: str) -> bool:
        return self._find(metric_id) is not None

    def has_verified_sql_handler(self, metric_id: str) -> bool:
        metric = self._find(metric_id)
        return bool(metric and metric["status"] == "approved" and metric["verified_handler"])

    def validate_access(self, metric_id: str, auth_context: dict[str, Any]) -> bool:
        """Check production visibility for an explicitly requested ID."""
        return self._is_visible(self._find(metric_id), auth_context)

    def list_metrics(
        self, *, approved_only: bool = False, allowed_metrics: Collection[str] | None = None
    ) -> list[dict[str, Any]]:
        metrics = self._metrics
        if allowed_metrics is not None:
            metrics = {**metrics, **self._additional}
        return [
            copy.deepcopy(metric)
            for metric_id, metric in metrics.items()
            if (allowed_metrics is None or metric_id in allowed_metrics)
            and (not approved_only or metric["status"] == "approved")
        ]

    def list_approved_metrics(self) -> list[dict[str, Any]]:
        """Return an isolated, ordered snapshot for offline document building."""
        return [
            copy.deepcopy(metric)
            for _, metric in sorted(self._metrics.items())
            if metric["status"] == "approved"
        ]

    def get_capability(self, metric_id: str) -> dict[str, Any]:
        """Return the governed capability surface for one metric."""

        metric = self._find(metric_id)
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
            "metadata_only": metric.get("metadata_only", False),
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

        return [
            metric
            for metric in self.list_metrics(
                approved_only=True, allowed_metrics=auth_context.get("allowed_metrics")
            )
            if self._is_visible(metric, auth_context)
        ]

    @staticmethod
    def _is_visible(metric: dict[str, Any] | None, auth_context: dict[str, Any]) -> bool:
        allowed_metrics = auth_context.get("allowed_metrics")
        return bool(
            metric
            and metric["status"] == "approved"
            and metric["verified_handler"] is True
            and (allowed_metrics is None or metric["metric_id"] in allowed_metrics)
            and set(auth_context.get("allowed_views") or ()).intersection(metric["supported_views"])
        )

    def get_catalog_hash(self) -> str:
        return self._catalog_hash
