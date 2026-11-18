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
    "account_code = '642'": ("account_code = ?", ("642",)),
    "source_document_type = 'DEPRECIATION'": ("source_document_type = ?", ("DEPRECIATION",)),
    "COALESCE(source_document_type, 'INTEREST') IN ('INTEREST', 'LOAN_INTEREST')": (
        "COALESCE(source_document_type, ?) IN (?, ?)",
        ("INTEREST", "INTEREST", "LOAN_INTEREST"),
    ),
    "cost_category IN ('LUONG','THUONG')": (
        "cost_category IN (?, ?)",
        ("LUONG", "THUONG"),
    ),
    "cost_category IN ('LUONG','THUONG','BAOHIEM')": (
        "cost_category IN (?, ?, ?)",
        ("LUONG", "THUONG", "BAOHIEM"),
    ),
}
_BILATERAL_SNAPSHOT_METRICS = frozenset(
    {"ar_balance", "ap_balance", "current_ratio", "quick_ratio", "working_capital"}
)
APPROVED_RELATIONS = frozenset(
    {
        "v_mgmt",
        "v_tax",
        "ar_invoice",
        "ar_receipt",
        "ar_adjustment",
        "ap_bill",
        "ap_payment",
        "gl_entry",
        "payroll",
    }
)

_SQL_TOKEN_RE = re.compile(r'"(?:""|[^"])*"|`[^`]*`|\[[^\]]*\]|[A-Za-z_][A-Za-z0-9_$]*|[(),.]|\S')
_CLAUSE_BOUNDARIES = frozenset(
    {
        "WHERE",
        "GROUP",
        "HAVING",
        "ORDER",
        "LIMIT",
        "UNION",
        "EXCEPT",
        "INTERSECT",
        "WINDOW",
        "QUALIFY",
        "FETCH",
        "OFFSET",
    }
)
_UNSAFE_FUNC_RE = re.compile(
    r"\b(?:READ_\w+|CSV_SCAN|PARQUET_\w+|JSON_SCAN|ICEBERG_\w+|DELTA_SCAN|"
    r"SQLITE_\w+|POSTGRES_\w+|MYSQL_\w+|EXCEL\w*|ST_READ\w*|GLOB|"
    r"PRAGMA_\w*|DUCKDB_\w*|CURRENT_SETTING)\s*\(",
    re.IGNORECASE,
)


def _unquote_ident(token: str) -> tuple[str, bool]:
    if token.startswith('"') and token.endswith('"') and len(token) >= 2:
        return token[1:-1].replace('""', '"'), True
    if token.startswith("`") and token.endswith("`") and len(token) >= 2:
        return token[1:-1], True
    if token.startswith("[") and token.endswith("]") and len(token) >= 2:
        return token[1:-1], True
    return token, False


def _is_ident_token(token: str) -> bool:
    if token.startswith(('"', "`", "[")):
        name, _ = _unquote_ident(token)
        return bool(name.strip())
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", token))


def _inspect_tokens(tokens: list[str], ctes: set[str]) -> None:
    depth = 0
    idx = 0
    total = len(tokens)
    while idx < total:
        tok = tokens[idx]
        upper = tok.upper()
        if tok == "(":
            depth += 1
            idx += 1
            continue
        if tok == ")":
            depth -= 1
            if depth < 0:
                raise UnsafeQuery("unbalanced parentheses in SQL")
            idx += 1
            continue
        prev_upper = tokens[idx - 1].upper() if idx > 0 else ""
        if upper in ("FROM", "JOIN") and prev_upper != "DISTINCT":
            is_from = upper == "FROM"
            from_depth = depth
            idx += 1
            if idx >= total:
                raise UnsafeQuery("incomplete FROM/JOIN clause")
            target = tokens[idx]
            if target == "(":
                sub_start = idx + 1
                sub_depth = 1
                idx += 1
                while idx < total and sub_depth > 0:
                    if tokens[idx] == "(":
                        sub_depth += 1
                    elif tokens[idx] == ")":
                        sub_depth -= 1
                    idx += 1
                if sub_depth != 0:
                    raise UnsafeQuery("unclosed subquery in FROM/JOIN")
                _inspect_tokens(tokens[sub_start : idx - 1], ctes)
            else:
                if not _is_ident_token(target):
                    raise UnsafeQuery("invalid relation in FROM/JOIN")
                next_tok = tokens[idx + 1] if idx + 1 < total else ""
                if next_tok == ".":
                    raise UnsafeQuery("schema-qualified relations are forbidden")
                if next_tok == "(":
                    raise UnsafeQuery("table-valued functions in FROM/JOIN are forbidden")
                rel_name, was_quoted = _unquote_ident(target)
                folded = rel_name.casefold()
                if was_quoted or (folded not in APPROVED_RELATIONS and folded not in ctes):
                    raise UnsafeQuery("query references a non-approved relation")
                idx += 1
            if is_from:
                scan_idx = idx
                scan_depth = from_depth
                while scan_idx < total:
                    st = tokens[scan_idx]
                    st_up = st.upper()
                    if st == "(":
                        scan_depth += 1
                    elif st == ")":
                        if scan_depth == from_depth:
                            break
                        scan_depth -= 1
                    elif scan_depth == from_depth:
                        if st == ",":
                            raise UnsafeQuery("comma-joins are forbidden")
                        if st_up in _CLAUSE_BOUNDARIES:
                            break
                    scan_idx += 1
            continue
        idx += 1
    if depth != 0:
        raise UnsafeQuery("unbalanced parentheses in SQL")


def _inspect_relations(unquoted_sql: str, ctes: set[str]) -> None:
    _inspect_tokens(_SQL_TOKEN_RE.findall(unquoted_sql), ctes)


def assert_safe_select(sql: str) -> None:
    if not isinstance(sql, str) or not sql.strip():
        raise UnsafeQuery("compiler output is empty")
    if ";" in sql:
        raise UnsafeQuery("multiple statements are forbidden")
    unquoted = re.sub(r"'(?:''|[^'])*'", "'__STR__'", sql)
    if "--" in unquoted or "/*" in unquoted or "*/" in unquoted:
        raise UnsafeQuery("SQL comments are forbidden")
    normalized = re.sub(r"\s+", " ", unquoted.strip()).upper()
    if not normalized.startswith(("SELECT ", "WITH ")):
        raise UnsafeQuery("compiler output is not a SELECT")
    for token in (
        " INSERT ",
        " UPDATE ",
        " DELETE ",
        " DROP ",
        " ALTER ",
        " COPY ",
        " ATTACH ",
        " DETACH ",
        " PRAGMA ",
        " CREATE ",
        " REPLACE ",
        " MERGE ",
        " TRUNCATE ",
        " CALL ",
        " EXPORT ",
        " IMPORT ",
        " INSTALL ",
        " LOAD ",
        " GRANT ",
        " REVOKE ",
        " VACUUM ",
        " EXECUTE ",
        " PREPARE ",
    ):
        if token in f" {normalized} ":
            raise UnsafeQuery(f"forbidden SQL token: {token.strip()}")
    if _UNSAFE_FUNC_RE.search(unquoted) or any(
        forbidden in normalized
        for forbidden in (
            "HTTPFS",
            "INFORMATION_SCHEMA",
            "PG_CATALOG",
            "SQLITE_MASTER",
            "SQLITE_SCHEMA",
            "DUCKDB_",
            "PRAGMA_",
        )
    ):
        raise UnsafeQuery("external-access or system catalog SQL function is forbidden")
    if re.search(r"\b(?:CROSS|NATURAL|POSITIONAL|ASOF)\s+JOIN\b|\bLATERAL\b", normalized):
        raise UnsafeQuery("unauthorized JOIN type is forbidden")
    ctes = {
        match.casefold()
        for match in re.findall(
            r"(?:WITH|,)\s*([A-Za-z_][A-Za-z0-9_]*)\s+AS\s*\(", unquoted, re.IGNORECASE
        )
    }
    allowed_ctes = {
        "aggregated",
        "paid",
        "adjusted",
        "open_invoice",
        "bilateral_base",
        "ledger_source",
    }
    if (ctes - allowed_ctes) and any(
        name not in APPROVED_RELATIONS and name in {"ground_truth", "company_info"} for name in ctes
    ):
        raise UnsafeQuery("unauthorized CTE name")
    _inspect_relations(unquoted, ctes)


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
                raise PlanRejected(
                    "incompatible_metrics", "Custom metric must execute in its own plan"
                )
            query = self._compile_catalog(plan)
        assert_safe_select(query.sql)
        return query

    def _base_where(self, plan: ValidatedPlan) -> tuple[list[str], list[object]]:
        clauses: list[str] = []
        params: list[object] = []
        period_type = self.catalog.get(plan.metric_ids[0]).period_type
        if period_type == "flow":
            assert plan.time.start and plan.time.end
            clauses.extend(
                [
                    "posting_date >= ?",
                    "posting_date < ?",
                    "COALESCE(is_closing, FALSE) = FALSE",
                    "source_document_type <> 'OPENING'",
                ]
            )
            params.extend([plan.time.start, plan.time.end + timedelta(days=1)])
        else:
            assert plan.time.as_of
            clauses.append("posting_date <= ?")
            params.append(plan.time.as_of)
        field_columns = {
            name: DIMENSIONS[name][0]
            for name in DIMENSIONS
            if name not in {"month", "quarter", "year"}
        }
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
                aggregates.extend(
                    [
                        f"{numerator} AS {metric_id}__num",
                        f"{denominator} AS {metric_id}__den",
                        f"{eligibility} AS {metric_id}__rows",
                    ]
                )
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
        group_by = (
            f" GROUP BY {', '.join(str(i + 1) for i in range(len(dimension_selects)))}"
            if dimension_selects
            else ""
        )
        period_type = self.catalog.get(plan.metric_ids[0]).period_type
        use_bilateral = period_type == "snapshot" and bool(
            _BILATERAL_SNAPSHOT_METRICS.intersection(plan.metric_ids)
        )
        if use_bilateral:
            dim_cols = [DIMENSIONS[d][0] for d in plan.dimensions]
            group_select = "".join(f"{col}, " for col in dim_cols)
            partner_group = ", ".join(
                dim_cols
                if "partner_code" in dim_cols
                else [*dim_cols, "COALESCE(partner_code, '__UNASSIGNED__')"]
            )
            bilateral_prefix = (
                f"WITH bilateral_base AS (SELECT * FROM {relation} WHERE {' AND '.join(clauses)}), "
                f"ledger_source AS ("
                f"SELECT {group_select}account_code, debit_amount, credit_amount "
                f"FROM bilateral_base "
                f"WHERE NOT starts_with(account_code, '131') AND NOT starts_with(account_code, '331') "
                f"UNION ALL "
                f"SELECT {group_select}"
                f"CASE WHEN bal >= 0 THEN '131' ELSE '3387_ADV' END AS account_code, "
                f"GREATEST(bal, 0) AS debit_amount, GREATEST(-bal, 0) AS credit_amount "
                f"FROM (SELECT {group_select}SUM(debit_amount - credit_amount) AS bal "
                f"FROM bilateral_base WHERE starts_with(account_code, '131') "
                f"GROUP BY {partner_group}) ar_partners "
                f"UNION ALL "
                f"SELECT {group_select}"
                f"CASE WHEN bal >= 0 THEN '331' ELSE '1388_ADV' END AS account_code, "
                f"GREATEST(-bal, 0) AS debit_amount, GREATEST(bal, 0) AS credit_amount "
                f"FROM (SELECT {group_select}SUM(credit_amount - debit_amount) AS bal "
                f"FROM bilateral_base WHERE starts_with(account_code, '331') "
                f"GROUP BY {partner_group}) ap_partners), "
                f"aggregated AS (SELECT {selected} FROM ledger_source{group_by})"
            )
            bound_params = [*where_params, *expression_params]
        else:
            bilateral_prefix = (
                f"WITH aggregated AS (SELECT {selected} FROM {relation} "
                f"WHERE {' AND '.join(clauses)}{group_by})"
            )
            bound_params = [*expression_params, *where_params]
        final_select = ", ".join([*dimension_aliases, *final_metrics])
        ordering = ""
        if plan.sort:
            ordering = f" ORDER BY {plan.sort.metric_id} {plan.sort.direction.upper()}, {', '.join(dimension_aliases) or plan.sort.metric_id}"
        elif dimension_aliases:
            ordering = f" ORDER BY {', '.join(dimension_aliases)}"
        limit = min(plan.top_k or self.row_cap, self.row_cap)
        sql = (
            f"{bilateral_prefix} SELECT {final_select} FROM aggregated{ordering} LIMIT {limit + 1}"
        )
        units = {metric_id: self.catalog.get(metric_id).unit for metric_id in plan.metric_ids}
        return self._bound(sql, bound_params, plan, units, tuple(dimension_aliases))

    @staticmethod
    def _custom_filter_clauses(
        plan: ValidatedPlan, mapping: dict[str, str]
    ) -> tuple[str, list[object]]:
        if not plan.filters:
            return "", []
        clauses: list[str] = []
        params: list[object] = []
        for item in plan.filters:
            if item.field not in mapping:
                raise PlanRejected(
                    "unsupported_filter", f"Filter {item.field} is not supported here"
                )
            col = mapping[item.field]
            if item.operator == "eq":
                clauses.append(f"{col} = ?")
                params.append(item.values[0])
            elif item.operator == "neq":
                clauses.append(f"{col} <> ?")
                params.append(item.values[0])
            elif item.operator == "in":
                clauses.append(f"{col} IN ({', '.join('?' for _ in item.values)})")
                params.extend(item.values)
            else:
                raise PlanRejected("unsupported_filter", "Filter operator is not compiler-approved")
        return " AND " + " AND ".join(clauses), params

    def _compile_custom(self, plan: ValidatedPlan, metric_id: str) -> BoundQuery:
        assert plan.time.as_of or plan.time.start
        params: list[object]
        dimensions: tuple[str, ...] = ()
        if metric_id == "ar_aging":
            assert plan.time.as_of
            flt_sql, flt_params = self._custom_filter_clauses(plan, {"customer": "i.customer_code"})
            customer_select = "customer_code, " if "customer" in plan.dimensions else ""
            group_by = "1, 2" if customer_select else "1"
            ordering = (
                "customer_code, CASE aging_bucket " if customer_select else "CASE aging_bucket "
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
                  WHERE i.issue_date <= ?{flt_sql}
                )
                SELECT {customer_select}aging_bucket, SUM(ar_aging) AS ar_aging FROM open_invoice
                WHERE ar_aging > 0 GROUP BY {group_by} ORDER BY
                  {ordering}WHEN 'not_due' THEN 0 WHEN '1_30' THEN 1 WHEN '31_60' THEN 2 WHEN '61_90' THEN 3 ELSE 4 END
                LIMIT 1001
            """
            params = [*([plan.time.as_of] * 7), *flt_params]
            dimensions = (("customer_code",) if customer_select else ()) + ("aging_bucket",)
        elif metric_id == "overdue_receivables":
            assert plan.time.as_of
            min_days = 30
            flt_sql, flt_params = self._custom_filter_clauses(plan, {"customer": "i.customer_code"})
            sql = f"""
                WITH paid AS (SELECT invoice_id, SUM(amount) paid FROM ar_receipt WHERE receipt_date <= ? GROUP BY 1),
                adjusted AS (SELECT invoice_id, SUM(total_amount) adjusted FROM ar_adjustment WHERE adjustment_date <= ? GROUP BY 1)
                SELECT SUM(i.total_amount - COALESCE(p.paid,0) - COALESCE(a.adjusted,0)) AS overdue_receivables
                FROM ar_invoice i LEFT JOIN paid p USING(invoice_id) LEFT JOIN adjusted a USING(invoice_id)
                WHERE i.issue_date <= ? AND i.due_date < ? - CAST(? AS INTEGER){flt_sql}
                  AND i.total_amount - COALESCE(p.paid,0) - COALESCE(a.adjusted,0) > 0 LIMIT 2
            """
            params = [
                plan.time.as_of,
                plan.time.as_of,
                plan.time.as_of,
                plan.time.as_of,
                min_days,
                *flt_params,
            ]
        elif metric_id == "dso_actual":
            self._custom_filter_clauses(plan, {})
            assert plan.time.start and plan.time.end
            sql = """
                SELECT CASE WHEN SUM(r.amount)=0 THEN NULL ELSE
                  SUM(r.amount * date_diff('day', i.issue_date, r.receipt_date)) / SUM(r.amount) END AS dso_actual
                FROM ar_receipt r JOIN ar_invoice i USING(invoice_id)
                WHERE r.receipt_date >= ? AND r.receipt_date < ? LIMIT 2
            """
            params = [plan.time.start, plan.time.end + timedelta(days=1)]
        elif metric_id == "ap_due_soon":
            self._custom_filter_clauses(plan, {})
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
            self._custom_filter_clauses(plan, {})
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
            flt_sql, flt_params = self._custom_filter_clauses(plan, {"customer": "customer_code"})
            limit = min(plan.top_k or 10, 100)
            sql = f"""
                SELECT invoice_id, einvoice_no, customer_code, subtotal AS top_sales_transactions
                FROM ar_invoice WHERE issue_date >= ? AND issue_date < ? AND NOT is_opening{flt_sql}
                ORDER BY subtotal DESC, invoice_id LIMIT {limit + 1}
            """
            params = [plan.time.start, plan.time.end + timedelta(days=1), *flt_params]
            dimensions = ("invoice_id", "einvoice_no", "customer_code")
        elif metric_id == "payroll_summary":
            assert plan.time.start and plan.time.end
            mapped = {"branch": "branch_code", "department": "department_code"}
            flt_sql, flt_params = self._custom_filter_clauses(plan, mapped)
            columns = [mapped[d] for d in plan.dimensions]
            dims = ", ".join(columns)
            select_dims = f"{dims}, " if dims else ""
            group = (
                f" GROUP BY {', '.join(str(i + 1) for i in range(len(columns)))}" if columns else ""
            )
            sql = (
                f"SELECT {select_dims}SUM(gross_salary + bonus + employer_contribution) AS payroll_summary "
                f"FROM payroll WHERE year_month >= ? AND year_month <= ?{flt_sql}{group} "
                f"ORDER BY {dims or 'payroll_summary'} LIMIT {self.row_cap + 1}"
            )
            params = [
                plan.time.start.strftime("%Y-%m"),
                plan.time.end.strftime("%Y-%m"),
                *flt_params,
            ]
            dimensions = tuple(plan.dimensions)
        elif metric_id == "cit_estimate":
            self._custom_filter_clauses(plan, {})
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
                *eligibility_params,
                *expression_params,
                plan.time.start,
                plan.time.end + timedelta(days=1),
            ]
        elif metric_id == "mgmt_vs_tax_gap":
            self._custom_filter_clauses(plan, {})
            assert plan.time.start and plan.time.end
            sql = """
                SELECT SUM(CASE WHEN account_code LIKE '6%' OR account_code LIKE '8%'
                  THEN debit_amount-credit_amount ELSE 0 END) AS mgmt_vs_tax_gap
                FROM v_mgmt WHERE posting_date >= ? AND posting_date < ?
                  AND NOT tax_deductible AND COALESCE(is_closing,FALSE)=FALSE LIMIT 2
            """
            params = [plan.time.start, plan.time.end + timedelta(days=1)]
        elif metric_id == "vat_position":
            self._custom_filter_clauses(plan, {})
            assert plan.time.start and plan.time.end
            sql = """
                SELECT CASE WHEN SUM(CASE WHEN account_code LIKE '33311%' OR account_code LIKE '1331%'
                                          THEN 1 ELSE 0 END)=0 THEN NULL ELSE
                  SUM(CASE WHEN account_code LIKE '33311%' THEN credit_amount-debit_amount
                           WHEN account_code LIKE '1331%' THEN -(debit_amount-credit_amount) ELSE 0 END)
                  END AS vat_position
                FROM v_tax WHERE posting_date >= ? AND posting_date < ?
                  AND COALESCE(is_closing,FALSE)=FALSE
                  AND COALESCE(source_document_type, '') NOT IN ('OPENING', 'VAT_OFFSET', 'VAT_PAYMENT', 'TAX_PAYMENT')
                LIMIT 2
            """
            params = [plan.time.start, plan.time.end + timedelta(days=1)]
        else:
            raise PlanRejected(
                "unsupported_data_source", f"No approved synthetic handler for {metric_id}"
            )
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
            sql=normalized,
            params=tuple(params),
            metric_ids=plan.metric_ids,
            dimensions=dimensions,
            units=units,
            row_cap=min(plan.top_k or self.row_cap, self.row_cap),
            fingerprint=fingerprint,
            source="synthetic_duckdb",
            catalog_hash=plan.catalog_hash,
        )
