from __future__ import annotations

import hashlib
import re
from datetime import timedelta
from decimal import Decimal

from agent4.engine.metrics import MetricDef, Term

from .catalog import CatalogSnapshot
from .errors import PlanRejected, UnsafeQuery
from .models import BoundQuery, ValidatedPlan

DIMENSIONS: dict[str, tuple[str, str]] = {
    "month": ("strftime(posting_date, '%Y-%m')", "month"),
    "quarter": ("CAST(year_no AS VARCHAR) || '-Q' || CAST(quarter_no AS VARCHAR)", "quarter"),
    "year": ("CAST(year_no AS VARCHAR)", "year"),
    "branch": ("branch_code", "branch"),
    "product_line": ("product_line", "product_line"),
    "customer": ("partner_code", "customer"),
    "vendor": ("partner_code", "vendor"),
    "item": ("item_code", "item"),
    "cost_category": ("cost_category", "cost_category"),
    "department": ("department_code", "department"),
    "account": ("account_code", "account"),
}

WHERE_PREDICATES = {
    "source_document_type = 'DEPRECIATION'": ("source_document_type = ?", ("DEPRECIATION",)),
    "cost_category IN ('LUONG','THUONG')": (
        "cost_category IN (?, ?)", ("LUONG", "THUONG"),
    ),
    "cost_category IN ('LUONG','THUONG','BAOHIEM')": (
        "cost_category IN (?, ?, ?)", ("LUONG", "THUONG", "BAOHIEM"),
    ),
}
APPROVED_RELATIONS = frozenset({
    "v_mgmt", "v_tax", "ar_invoice", "ar_receipt", "ar_adjustment",
    "ap_bill", "ap_payment", "gl_entry", "payroll",
})


def assert_safe_select(sql: str) -> None:
    normalized = re.sub(r"\s+", " ", sql.strip()).upper()
    if not normalized.startswith(("SELECT ", "WITH ")):
        raise UnsafeQuery("compiler output is not a SELECT")
    if ";" in sql:
        raise UnsafeQuery("multiple statements are forbidden")
    for token in (
        " INSERT ", " UPDATE ", " DELETE ", " DROP ", " ALTER ", " COPY ",
        " ATTACH ", " PRAGMA ", " CREATE ", " REPLACE ", " MERGE ", " TRUNCATE ",
        " CALL ", " EXPORT ", " IMPORT ", " INSTALL ", " LOAD ",
    ):
        if token in f" {normalized} ":
            raise UnsafeQuery(f"forbidden SQL token: {token.strip()}")
    unsafe_functions = (
        "READ_CSV", "READ_JSON", "READ_PARQUET", "READ_TEXT", "READ_BLOB",
        "GLOB(", "HTTPFS", "SQLITE_SCAN", "POSTGRES_SCAN",
    )
    if any(function in normalized for function in unsafe_functions):
        raise UnsafeQuery("external-access SQL function is forbidden")
    ctes = {
        match.casefold()
        for match in re.findall(
            r"(?:WITH|,)\s*([A-Za-z_][A-Za-z0-9_]*)\s+AS\s*\(", sql, re.IGNORECASE
        )
    }
    relations = {
        match.casefold()
        for match in re.findall(
            r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", sql, re.IGNORECASE
        )
    }
    unexpected = relations.difference(APPROVED_RELATIONS, ctes)
    if unexpected:
        raise UnsafeQuery("query references a non-approved relation")


class SQLCompiler:
    def __init__(self, catalog: CatalogSnapshot, *, row_cap: int = 1000) -> None:
        self.catalog = catalog
        self.row_cap = row_cap

    @staticmethod
    def _predicate(term: Term) -> tuple[str, list[object]]:
        prefix_checks = " OR ".join("account_code LIKE ?" for _ in term.prefixes)
        params: list[object] = [f"{prefix}%" for prefix in term.prefixes]
        predicate = f"({prefix_checks})"
        if term.where:
            try:
                trusted, values = WHERE_PREDICATES[term.where]
            except KeyError as exc:
                raise UnsafeQuery(f"unapproved catalog predicate: {term.where}") from exc
            predicate = f"{predicate} AND {trusted}"
            params.extend(values)
        return predicate, params

    @classmethod
    def _term(cls, term: Term) -> tuple[str, list[object]]:
        predicate, params = cls._predicate(term)
        measures = {
            "net_debit": "debit_amount - credit_amount",
            "net_credit": "credit_amount - debit_amount",
            "debit": "debit_amount",
            "credit": "credit_amount",
        }
        try:
            measure = measures[term.measure]
        except KeyError as exc:
            raise UnsafeQuery(f"unapproved term measure: {term.measure}") from exc
        coef = Decimal(str(term.coef))
        return f"SUM(CASE WHEN {predicate} THEN ({measure}) * ? ELSE 0 END)", [*params, coef]

    @classmethod
    def _eligibility(cls, terms: tuple[Term, ...]) -> tuple[str, list[object]]:
        expressions: list[str] = []
        params: list[object] = []
        for term in terms:
            predicate, predicate_params = cls._predicate(term)
            expressions.append(f"SUM(CASE WHEN {predicate} THEN 1 ELSE 0 END)")
            params.extend(predicate_params)
        return " + ".join(expressions) or "0", params

    def _terms(self, terms: tuple[Term, ...]) -> tuple[str, list[object]]:
        expressions: list[str] = []
        params: list[object] = []
        for term in terms:
            expression, term_params = self._term(term)
            expressions.append(f"COALESCE({expression}, 0)")
            params.extend(term_params)
        return " + ".join(expressions) or "CAST(0 AS DECIMAL(38, 6))", params

    def _metric(self, metric: MetricDef) -> tuple[str, list[object]]:
        if metric.kind in {"flow", "snapshot"}:
            return self._terms(metric.terms)
        if metric.kind == "ratio":
            numerator, num_params = self._terms(metric.num)
            denominator, den_params = self._terms(metric.den)
            # Parameters occur once in the CTE; the final expression references aliases.
            expression = (
                f"CAST(CASE WHEN denominator = 0 THEN NULL "
                f"ELSE numerator / denominator * {Decimal(str(metric.scale))} "
                "END AS DECIMAL(38, 10))"
            )
            return f"RATIO::{numerator}::{denominator}::{expression}", [*num_params, *den_params]
        raise PlanRejected("unsupported_data_source", f"Custom metric {metric.id} needs a handler")

    def compile(self, plan: ValidatedPlan) -> BoundQuery:
        if plan.catalog_hash != self.catalog.hash:
            raise UnsafeQuery("catalog changed after validation")
        if len(plan.metric_ids) == 1 and self.catalog.get(plan.metric_ids[0]).kind == "custom":
            query = self._compile_custom(plan, plan.metric_ids[0])
        else:
            if any(self.catalog.get(metric_id).kind == "custom" for metric_id in plan.metric_ids):
                raise PlanRejected("incompatible_metrics", "Custom metric must execute in its own plan")
            query = self._compile_catalog(plan)
        assert_safe_select(query.sql)
        return query

    def _base_where(self, plan: ValidatedPlan) -> tuple[list[str], list[object]]:
        clauses: list[str] = []
        params: list[object] = []
        period_type = self.catalog.get(plan.metric_ids[0]).period_type
        if period_type == "flow":
            assert plan.time.start and plan.time.end
            clauses.extend([
                "posting_date >= ?", "posting_date < ?", "COALESCE(is_closing, FALSE) = FALSE",
                "source_document_type <> 'OPENING'",
            ])
            params.extend([plan.time.start, plan.time.end + timedelta(days=1)])
        else:
            assert plan.time.as_of
            clauses.append("posting_date <= ?")
            params.append(plan.time.as_of)
        field_columns = {name: DIMENSIONS[name][0] for name in DIMENSIONS if name not in {"month", "quarter", "year"}}
        for item in plan.filters:
            column = field_columns[item.field]
            if item.operator == "eq":
                clauses.append(f"{column} = ?")
                params.append(item.values[0])
            elif item.operator == "neq":
                clauses.append(f"{column} <> ?")
                params.append(item.values[0])
            elif item.operator == "in":
                clauses.append(f"{column} IN ({', '.join('?' for _ in item.values)})")
                params.extend(item.values)
            else:
                raise PlanRejected("unsupported_filter", "Filter operator is not compiler-approved")
        return clauses, params

    def _compile_catalog(self, plan: ValidatedPlan) -> BoundQuery:
        relation = {"mgmt": "v_mgmt", "tax": "v_tax"}[plan.view]
        dimension_selects = [f"{DIMENSIONS[d][0]} AS {DIMENSIONS[d][1]}" for d in plan.dimensions]
        dimension_aliases = [DIMENSIONS[d][1] for d in plan.dimensions]
        aggregates: list[str] = []
        final_metrics: list[str] = []
        expression_params: list[object] = []
        for metric_id in plan.metric_ids:
            metric = self.catalog.get(metric_id)
            compiled, params = self._metric(metric)
            eligibility_terms = metric.terms if metric.kind != "ratio" else metric.num + metric.den
            eligibility, eligibility_params = self._eligibility(eligibility_terms)
            if compiled.startswith("RATIO::"):
                _, numerator, denominator, expression = compiled.split("::", 3)
                aggregates.extend([
                    f"{numerator} AS {metric_id}__num",
                    f"{denominator} AS {metric_id}__den",
                    f"{eligibility} AS {metric_id}__rows",
                ])
                expression = expression.replace("numerator", f"{metric_id}__num").replace(
                    "denominator", f"{metric_id}__den"
                )
                final_metrics.append(
                    f"CASE WHEN {metric_id}__rows = 0 THEN NULL ELSE {expression} END AS {metric_id}"
                )
            else:
                aggregates.append(f"{compiled} AS {metric_id}")
                aggregates.append(f"{eligibility} AS {metric_id}__rows")
                final_metrics.append(
                    f"CASE WHEN {metric_id}__rows = 0 THEN NULL ELSE {metric_id} END AS {metric_id}"
                )
            expression_params.extend(params)
            expression_params.extend(eligibility_params)
        clauses, where_params = self._base_where(plan)
        selected = ", ".join([*dimension_selects, *aggregates])
        group_by = f" GROUP BY {', '.join(str(i + 1) for i in range(len(dimension_selects)))}" if dimension_selects else ""
        cte = f"SELECT {selected} FROM {relation} WHERE {' AND '.join(clauses)}{group_by}"
        final_select = ", ".join([*dimension_aliases, *final_metrics])
        ordering = ""
        if plan.sort:
            ordering = f" ORDER BY {plan.sort.metric_id} {plan.sort.direction.upper()}, {', '.join(dimension_aliases) or plan.sort.metric_id}"
        elif dimension_aliases:
            ordering = f" ORDER BY {', '.join(dimension_aliases)}"
        limit = min(plan.top_k or self.row_cap, self.row_cap)
        sql = f"WITH aggregated AS ({cte}) SELECT {final_select} FROM aggregated{ordering} LIMIT {limit + 1}"
        units = {metric_id: self.catalog.get(metric_id).unit for metric_id in plan.metric_ids}
        return self._bound(sql, [*expression_params, *where_params], plan, units, tuple(dimension_aliases))

    def _compile_custom(self, plan: ValidatedPlan, metric_id: str) -> BoundQuery:
        assert plan.time.as_of or plan.time.start
        params: list[object]
        dimensions: tuple[str, ...] = ()
        if metric_id == "ar_aging":
            assert plan.time.as_of
            customer_select = "customer_code, " if "customer" in plan.dimensions else ""
            group_by = "1, 2" if customer_select else "1"
            ordering = (
                "customer_code, CASE aging_bucket "
                if customer_select
                else "CASE aging_bucket "
            )
            sql = f"""
                WITH paid AS (
                  SELECT invoice_id, SUM(amount) AS paid FROM ar_receipt
                  WHERE receipt_date <= ? GROUP BY invoice_id
                ), adjusted AS (
                  SELECT invoice_id, SUM(total_amount) AS adjusted FROM ar_adjustment
                  WHERE adjustment_date <= ? GROUP BY invoice_id
                ), open_invoice AS (
                  SELECT i.customer_code,
                    CASE WHEN i.due_date >= ? THEN 'not_due'
                         WHEN date_diff('day', i.due_date, ?) <= 30 THEN '1_30'
                         WHEN date_diff('day', i.due_date, ?) <= 60 THEN '31_60'
                         WHEN date_diff('day', i.due_date, ?) <= 90 THEN '61_90'
                         ELSE 'over_90' END AS aging_bucket,
                    i.total_amount - COALESCE(p.paid, 0) - COALESCE(a.adjusted, 0) AS ar_aging
                  FROM ar_invoice i LEFT JOIN paid p USING(invoice_id) LEFT JOIN adjusted a USING(invoice_id)
                  WHERE i.issue_date <= ?
                )
                SELECT {customer_select}aging_bucket, SUM(ar_aging) AS ar_aging FROM open_invoice
                WHERE ar_aging > 0 GROUP BY {group_by} ORDER BY
                  {ordering}WHEN 'not_due' THEN 0 WHEN '1_30' THEN 1 WHEN '31_60' THEN 2 WHEN '61_90' THEN 3 ELSE 4 END
                LIMIT 1001
            """
            params = [plan.time.as_of] * 7
            dimensions = (("customer_code",) if customer_select else ()) + ("aging_bucket",)
        elif metric_id == "overdue_receivables":
            assert plan.time.as_of
            min_days = 30
            sql = """
                WITH paid AS (SELECT invoice_id, SUM(amount) paid FROM ar_receipt WHERE receipt_date <= ? GROUP BY 1),
                adjusted AS (SELECT invoice_id, SUM(total_amount) adjusted FROM ar_adjustment WHERE adjustment_date <= ? GROUP BY 1)
                SELECT SUM(i.total_amount - COALESCE(p.paid,0) - COALESCE(a.adjusted,0)) AS overdue_receivables
                FROM ar_invoice i LEFT JOIN paid p USING(invoice_id) LEFT JOIN adjusted a USING(invoice_id)
                WHERE i.issue_date <= ? AND i.due_date < ? - CAST(? AS INTEGER)
                  AND i.total_amount - COALESCE(p.paid,0) - COALESCE(a.adjusted,0) > 0 LIMIT 2
            """
            params = [plan.time.as_of, plan.time.as_of, plan.time.as_of, plan.time.as_of, min_days]
        elif metric_id == "dso_actual":
            assert plan.time.start and plan.time.end
            sql = """
                SELECT CASE WHEN SUM(r.amount)=0 THEN NULL ELSE
                  SUM(r.amount * date_diff('day', i.issue_date, r.receipt_date)) / SUM(r.amount) END AS dso_actual
                FROM ar_receipt r JOIN ar_invoice i USING(invoice_id)
                WHERE r.receipt_date >= ? AND r.receipt_date < ? LIMIT 2
            """
            params = [plan.time.start, plan.time.end + timedelta(days=1)]
        elif metric_id == "ap_due_soon":
            assert plan.time.start and plan.time.end
            sql = """
                WITH paid AS (SELECT bill_id, SUM(amount) paid FROM ap_payment WHERE payment_date <= ? GROUP BY 1)
                SELECT SUM(b.total_amount - COALESCE(p.paid,0)) AS ap_due_soon
                FROM ap_bill b LEFT JOIN paid p USING(bill_id)
                WHERE b.bill_date <= ? AND b.due_date <= ?
                  AND b.total_amount - COALESCE(p.paid,0) > 0 LIMIT 2
            """
            # Forward-looking obligation state is frozen at range start; the
            # range end is the due-date horizon and already-overdue items remain.
            params = [plan.time.start, plan.time.start, plan.time.end]
        elif metric_id == "unbalanced_journals":
            assert plan.time.start and plan.time.end
            sql = """
                SELECT COUNT(*) AS unbalanced_journals FROM (
                  SELECT journal_id FROM gl_entry WHERE posting_date >= ? AND posting_date < ?
                  GROUP BY journal_id HAVING SUM(debit_amount) <> SUM(credit_amount)
                ) imbalance LIMIT 2
            """
            params = [plan.time.start, plan.time.end + timedelta(days=1)]
        elif metric_id == "top_sales_transactions":
            assert plan.time.start and plan.time.end
            limit = min(plan.top_k or 10, 100)
            sql = f"""
                SELECT invoice_id, einvoice_no, customer_code, subtotal AS top_sales_transactions
                FROM ar_invoice WHERE issue_date >= ? AND issue_date < ? AND NOT is_opening
                ORDER BY subtotal DESC, invoice_id LIMIT {limit + 1}
            """
            params = [plan.time.start, plan.time.end + timedelta(days=1)]
            dimensions = ("invoice_id", "einvoice_no", "customer_code")
        elif metric_id == "payroll_summary":
            assert plan.time.start and plan.time.end
            mapped = {"branch": "branch_code", "department": "department_code"}
            columns = [mapped[d] for d in plan.dimensions]
            dims = ", ".join(columns)
            select_dims = f"{dims}, " if dims else ""
            group = f" GROUP BY {', '.join(str(i + 1) for i in range(len(columns)))}" if columns else ""
            sql = (
                f"SELECT {select_dims}SUM(gross_salary + bonus + employer_contribution) AS payroll_summary "
                f"FROM payroll WHERE year_month >= ? AND year_month <= ?{group} "
                f"ORDER BY {dims or 'payroll_summary'} LIMIT {self.row_cap + 1}"
            )
            params = [plan.time.start.strftime("%Y-%m"), plan.time.end.strftime("%Y-%m")]
            dimensions = tuple(plan.dimensions)
        elif metric_id == "cit_estimate":
            if plan.view != "tax":
                raise PlanRejected("unsupported_view", "Ước tính CIT chỉ dùng khung thuế")
            assert plan.time.start and plan.time.end
            taxable = self.catalog.get("taxable_income")
            expression, expression_params = self._terms(taxable.terms)
            eligibility, eligibility_params = self._eligibility(taxable.terms)
            sql = f"""
                SELECT CASE WHEN ({eligibility}) = 0 THEN NULL ELSE
                  GREATEST(COALESCE({expression},0),0) * CAST(0.20 AS DECIMAL(4,2)) END AS cit_estimate
                FROM v_tax WHERE posting_date >= ? AND posting_date < ?
                  AND COALESCE(is_closing,FALSE)=FALSE AND source_document_type <> 'OPENING' LIMIT 2
            """
            params = [
                *eligibility_params, *expression_params,
                plan.time.start, plan.time.end + timedelta(days=1),
            ]
        elif metric_id == "mgmt_vs_tax_gap":
            assert plan.time.start and plan.time.end
            sql = """
                SELECT SUM(CASE WHEN account_code LIKE '6%' OR account_code LIKE '8%'
                  THEN debit_amount-credit_amount ELSE 0 END) AS mgmt_vs_tax_gap
                FROM v_mgmt WHERE posting_date >= ? AND posting_date < ?
                  AND NOT tax_deductible AND COALESCE(is_closing,FALSE)=FALSE LIMIT 2
            """
            params = [plan.time.start, plan.time.end + timedelta(days=1)]
        elif metric_id == "vat_position":
            assert plan.time.start and plan.time.end
            sql = """
                SELECT CASE WHEN SUM(CASE WHEN account_code LIKE '33311%' OR account_code LIKE '1331%'
                                          THEN 1 ELSE 0 END)=0 THEN NULL ELSE
                  SUM(CASE WHEN account_code LIKE '33311%' THEN credit_amount-debit_amount
                           WHEN account_code LIKE '1331%' THEN -(debit_amount-credit_amount) ELSE 0 END)
                  END AS vat_position
                FROM v_tax WHERE posting_date >= ? AND posting_date < ?
                  AND COALESCE(is_closing,FALSE)=FALSE AND source_document_type <> 'OPENING' LIMIT 2
            """
            params = [plan.time.start, plan.time.end + timedelta(days=1)]
        else:
            raise PlanRejected("unsupported_data_source", f"No approved synthetic handler for {metric_id}")
        units = {metric_id: self.catalog.get(metric_id).unit}
        return self._bound(sql, params, plan, units, dimensions)

    def _bound(
        self,
        sql: str,
        params: list[object],
        plan: ValidatedPlan,
        units: dict[str, str],
        dimensions: tuple[str, ...],
    ) -> BoundQuery:
        normalized = re.sub(r"\s+", " ", sql.strip())
        fingerprint = hashlib.sha256(normalized.encode()).hexdigest()[:24]
        return BoundQuery(
            sql=normalized, params=tuple(params), metric_ids=plan.metric_ids,
            dimensions=dimensions, units=units,
            row_cap=min(plan.top_k or self.row_cap, self.row_cap),
            fingerprint=fingerprint, source="synthetic_duckdb",
            catalog_hash=plan.catalog_hash,
        )
