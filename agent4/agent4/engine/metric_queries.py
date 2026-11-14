"""Trusted DuckDB templates for the metrics that need a query of their own."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricQuery:
    label_en: str
    sql: str
    dimensions: tuple[str, ...] = ()
    required_views: tuple[str, ...] = ()
    forecast: bool = False


# Each template sees a one-row period CTE with start_date and end_date. On a
# snapshot both fields are the same as-of date. Templates expose only declared
# dimensions and one numeric value. The compiler owns the final projection and limit.
_FLOW = """
    posting_date BETWEEN start_date AND end_date
    AND NOT is_closing AND source_module IS DISTINCT FROM 'OPENING'
"""
_CASH = "(starts_with(account_code, '111') OR starts_with(account_code, '112'))"
_STOCK = "left(account_code, 3) IN ('151','152','153','154','155','156','157')"
_EXPENSE = "left(account_code, 3) IN ('641','642')"
_AP_OPEN = """
    SELECT COALESCE(SUM(GREATEST(b.total_amount - COALESCE(p.paid, 0), 0)), 0)
    FROM ap_bill b LEFT JOIN (
        SELECT bill_id, SUM(amount) AS paid FROM ap_payment, period
        WHERE payment_date <= LEAST(start_date, watermark) GROUP BY bill_id
    ) p USING (bill_id), period
    WHERE b.bill_date <= LEAST(start_date, watermark) AND b.due_date <= end_date
"""


def _partner_balance(prefix: str, partner_type: str, sign: str) -> str:
    return f"""
        SELECT partner_code, SUM({sign}net_debit) AS value FROM v_mgmt, period
        WHERE posting_date <= end_date AND starts_with(account_code, '{prefix}')
          AND partner_type = '{partner_type}' AND partner_code IS NOT NULL
        GROUP BY partner_code
    """


def _turnover(stock: str, denominator: str, sign: str = "") -> str:
    return f"""
        SELECT (SUM(CASE WHEN posting_date < start_date THEN {sign}net_debit ELSE 0 END)
              + SUM({sign}net_debit)) / 2.0 * MAX(date_diff('day', start_date, end_date) + 1)
              / NULLIF(SUM(CASE WHEN {_FLOW} AND ({denominator})
                         THEN {"credit_amount" if sign else "debit_amount"} ELSE 0 END), 0) AS value
        FROM v_mgmt, period WHERE posting_date <= end_date AND ({stock} OR ({denominator}))
    """


# DIO needs COGS in the denominator but only inventory in both stock balances.
_DIO = f"""
    SELECT (SUM(CASE WHEN {_STOCK} AND posting_date < start_date THEN net_debit ELSE 0 END)
          + SUM(CASE WHEN {_STOCK} THEN net_debit ELSE 0 END)) / 2.0
          * MAX(date_diff('day', start_date, end_date) + 1)
          / NULLIF(SUM(CASE WHEN {_FLOW} AND starts_with(account_code, '632')
                     THEN net_debit ELSE 0 END), 0) AS value
    FROM v_mgmt, period WHERE posting_date <= end_date
"""
_DSO = _turnover(
    "starts_with(account_code, '131')",
    "starts_with(account_code, '131') AND source_document_type = 'SALES_INVOICE'",
)
_DPO = _turnover(
    "starts_with(account_code, '331')",
    "starts_with(account_code, '331') AND source_document_type IN ('PURCHASE_INVOICE','PURCHASE_SERVICE')",
    "-",
)

# Direct allocations reduce their invoices first. Unlinked credits and any
# excess allocated payments then cover the oldest open invoices of that customer.
_AR_OPEN = """
    WITH credits AS (
        SELECT invoice_id, customer_code, amount FROM ar_receipt, period WHERE receipt_date <= end_date
        UNION ALL
        SELECT invoice_id, customer_code, total_amount FROM ar_adjustment, period
        WHERE adjustment_date <= end_date
    ), allocated AS (
        SELECT invoice_id, SUM(amount) AS amount FROM credits WHERE invoice_id IS NOT NULL
        GROUP BY invoice_id
    ), invoices AS (
        SELECT i.invoice_id, i.customer_code, i.issue_date, i.due_date, end_date,
               i.total_amount - COALESCE(a.amount, 0) AS residual
        FROM ar_invoice i LEFT JOIN allocated a USING (invoice_id), period
        WHERE i.issue_date <= end_date
    ), pools AS (
        SELECT customer_code, SUM(amount) AS amount FROM (
            SELECT c.customer_code, c.amount FROM credits c LEFT JOIN invoices i USING (invoice_id)
            WHERE i.invoice_id IS NULL
            UNION ALL SELECT customer_code, -residual FROM invoices WHERE residual < 0
        ) amounts GROUP BY customer_code
    ), open AS (
        SELECT i.*, GREATEST(residual - GREATEST(COALESCE(p.amount, 0) - COALESCE(
            SUM(residual) OVER (PARTITION BY i.customer_code ORDER BY issue_date, invoice_id
                               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0), 0), 0) AS outstanding
        FROM invoices i LEFT JOIN pools p USING (customer_code) WHERE residual > 0
    )
"""


METRIC_QUERIES = {
    "ar_by_customer": MetricQuery(
        "Receivables by Customer", _partner_balance("131", "CUSTOMER", ""), ("partner_code",)
    ),
    "ap_by_vendor": MetricQuery(
        "Payables by Vendor", _partner_balance("331", "VENDOR", "-"), ("partner_code",)
    ),
    "ar_by_salesperson": MetricQuery(
        "Receivables by Salesperson",
        """
        SELECT COALESCE(p.salesperson_code, 'unassigned') AS salesperson_code, SUM(g.net_debit) AS value
        FROM v_mgmt g LEFT JOIN dim_partner p ON p.partner_code = g.partner_code
            AND p.partner_type = 'CUSTOMER', period
        WHERE g.posting_date <= end_date AND starts_with(g.account_code, '131')
            AND g.partner_type = 'CUSTOMER' AND g.partner_code IS NOT NULL
        GROUP BY 1
    """,
        ("salesperson_code",),
    ),
    "cash_flow_breakdown": MetricQuery(
        "Cash Flow Breakdown",
        f"""
        SELECT CASE
            WHEN source_document_type = 'RECEIPT' THEN 'customer_receipts'
            WHEN source_document_type = 'PAYMENT' THEN 'supplier_payments'
            WHEN source_document_type IN ('PAYROLL_PAYMENT', 'HR_REMITTANCE') THEN 'payroll'
            WHEN source_document_type IN ('VAT_PAYMENT','CIT_PAYMENT','TAX_PAYMENT') THEN 'tax'
            WHEN source_document_type IN ('LOAN_MOVEMENT','LOAN_INTEREST','INTEREST') THEN 'financing'
            WHEN source_document_type IN ('ASSET_PURCHASE','ASSET_ACQUISITION') THEN 'investing'
            ELSE 'other' END AS component, SUM(net_debit) AS value
        FROM v_mgmt, period WHERE {_FLOW} AND {_CASH} GROUP BY 1
    """,
        ("component",),
    ),
    "cash_coverage_days": MetricQuery(
        "Cash Coverage Days",
        f"""
        SELECT SUM(net_debit) * 90.0 / NULLIF(SUM(CASE
            WHEN posting_date > end_date - 90 AND NOT is_closing
             AND source_module IS DISTINCT FROM 'OPENING'
                AND COALESCE(source_document_type, '') NOT IN
                    ('LOAN_MOVEMENT','LOAN_PRINCIPAL','LOAN_REPAYMENT','LOAN_DISBURSEMENT','CASH_TRANSFER')
            THEN credit_amount ELSE 0 END), 0) AS value
        FROM v_mgmt, period WHERE posting_date <= end_date AND {_CASH}
    """,
    ),
    "ar_aging": MetricQuery(
        "Receivables Aging",
        _AR_OPEN
        + """
        SELECT CASE WHEN due_date >= end_date THEN '0_not_due'
                    WHEN due_date >= end_date - 30 THEN '1_01_30'
                    WHEN due_date >= end_date - 60 THEN '2_31_60'
                    WHEN due_date >= end_date - 90 THEN '3_61_90'
                    WHEN due_date < end_date - 90 THEN '4_over_90'
                    ELSE '5_unknown' END AS aging_bucket, SUM(outstanding) AS value
        FROM open WHERE outstanding > 0 GROUP BY 1
    """,
        ("aging_bucket",),
    ),
    "overdue_receivables": MetricQuery(
        "Overdue Receivables",
        _AR_OPEN
        + """
        SELECT COALESCE(SUM(outstanding), 0) AS value FROM open
        WHERE due_date < end_date - 30
    """,
    ),
    "dso": MetricQuery("Days Sales Outstanding", _DSO),
    "dso_actual": MetricQuery(
        "Actual Collection Days",
        """
        SELECT SUM(r.amount * date_diff('day', i.issue_date, r.receipt_date)) / NULLIF(SUM(r.amount), 0) AS value
        FROM ar_receipt r JOIN ar_invoice i USING (invoice_id), period
        WHERE r.receipt_date BETWEEN start_date AND end_date
            AND NOT i.is_opening AND r.receipt_date >= i.issue_date AND r.amount > 0
    """,
    ),
    "dpo": MetricQuery("Days Payable Outstanding", _DPO),
    "dio": MetricQuery("Days Inventory Outstanding", _DIO),
    "cash_conversion_cycle": MetricQuery(
        "Cash Conversion Cycle",
        f"""
        SELECT sales.value + inventory.value - payable.value AS value
        FROM ({_DSO}) sales CROSS JOIN ({_DIO}) inventory CROSS JOIN ({_DPO}) payable
    """,
    ),
    "ap_due_soon": MetricQuery("Payables Due Soon", f"SELECT ({_AP_OPEN}) AS value", forecast=True),
    "upcoming_obligations": MetricQuery(
        "Upcoming Payment Obligations",
        f"""
        SELECT ({_AP_OPEN}) + (
            SELECT COALESCE(SUM(GREATEST(balance, 0)), 0) FROM (
                SELECT left(account_code, 3), SUM(-net_debit) AS balance FROM v_mgmt, period
                WHERE posting_date <= LEAST(start_date, watermark)
                    AND left(account_code, 3) IN ('333','334','338') GROUP BY 1
            )
        ) + (SELECT COALESCE(SUM(principal), 0) FROM loan_schedule, period
             WHERE due_date BETWEEN start_date AND end_date) AS value
    """,
        forecast=True,
    ),
    "expense_spikes": MetricQuery(
        "Expense Spikes",
        f"""
        SELECT cost_category, SUM(CASE WHEN posting_date >= start_date THEN net_debit ELSE 0 END)
               - SUM(CASE WHEN posting_date < start_date THEN net_debit ELSE 0 END)
                 / 3.0 * MAX((date_diff('day', start_date, end_date) + 1.0)
                     / day(last_day(start_date))) AS value
        FROM v_mgmt, period
        WHERE posting_date >= date_trunc('month', start_date) - INTERVAL 3 MONTH
            AND posting_date <= end_date AND NOT is_closing
            AND source_module IS DISTINCT FROM 'OPENING' AND {_EXPENSE}
            AND cost_category IS NOT NULL AND date_trunc('month', start_date) = date_trunc('month', end_date)
            AND start_date = date_trunc('month', start_date)
            AND CAST((SELECT value FROM company_info WHERE key = 'data_start') AS DATE)
                <= date_trunc('month', start_date) - INTERVAL 3 MONTH
        GROUP BY 1 HAVING value > 0
    """,
        ("cost_category",),
    ),
    "unusual_account_movements": MetricQuery(
        "Unusual Account Movements",
        """
        WITH months AS (
            SELECT month_start::DATE AS month_start FROM period,
                generate_series(date_trunc('month', start_date) - INTERVAL 6 MONTH,
                    date_trunc('month', start_date), INTERVAL 1 MONTH) AS dates(month_start)
            WHERE start_date = date_trunc('month', start_date) AND end_date = last_day(start_date)
                AND end_date <= watermark
                AND CAST((SELECT value FROM company_info WHERE key = 'data_start') AS DATE)
                    <= date_trunc('month', start_date) - INTERVAL 6 MONTH
        ), movement AS (
            SELECT account_code, date_trunc('month', posting_date)::DATE AS month_start,
                SUM(debit_amount + credit_amount) AS amount
            FROM v_mgmt, period
            WHERE posting_date BETWEEN start_date - INTERVAL 6 MONTH AND end_date
                AND NOT is_closing AND source_module IS DISTINCT FROM 'OPENING' GROUP BY 1, 2
        ), stats AS (
            SELECT account_code, MAX(COALESCE(amount, 0)) FILTER (WHERE month_start = start_date) AS actual,
                   AVG(COALESCE(amount, 0)) FILTER (WHERE month_start < start_date) AS mean,
                   STDDEV_POP(COALESCE(amount, 0)) FILTER (WHERE month_start < start_date) AS sd
            FROM (SELECT DISTINCT account_code FROM movement) accounts CROSS JOIN months CROSS JOIN period
            LEFT JOIN movement USING (account_code, month_start) GROUP BY 1
        )
        SELECT COUNT(*) AS value FROM stats
        WHERE ABS(actual - mean) >= 50000000 AND (sd = 0 OR ABS(actual - mean) >= 2.5 * sd)
        HAVING EXISTS (SELECT 1 FROM months)
    """,
    ),
    "unbalanced_journals": MetricQuery(
        "Unbalanced Journals",
        """
        SELECT COUNT(*) AS value FROM (
            SELECT journal_id FROM v_mgmt, period
            WHERE posting_date BETWEEN start_date AND end_date
            GROUP BY journal_id HAVING SUM(debit_amount) <> SUM(credit_amount)
        )
    """,
    ),
    "top_sales_transactions": MetricQuery(
        "Top Sales Transactions",
        """
        SELECT CAST(invoice_id AS VARCHAR) AS transaction_id, subtotal AS value
        FROM ar_invoice, period WHERE issue_date BETWEEN start_date AND end_date AND NOT is_opening
    """,
        ("transaction_id",),
    ),
    "budget_vs_actual": MetricQuery(
        "Budget vs Actual",
        f"""
        SELECT component, SUM(amount) AS value FROM (
            SELECT 'actual_revenue' AS component, -net_debit AS amount FROM v_mgmt, period
            WHERE {_FLOW} AND left(account_code, 3) IN ('511','521')
            UNION ALL
            SELECT 'actual_expense', net_debit FROM v_mgmt, period WHERE {_FLOW} AND {_EXPENSE}
            UNION ALL
            SELECT 'budget_' || lower(b.line_type),
                b.amount * (date_diff('day', GREATEST(m, start_date), LEAST(last_day(m), end_date)) + 1.0)
                         / day(last_day(m))
            FROM budget b, period,
            LATERAL (SELECT make_date(b.year_no, b.month_no, 1) AS m)
            WHERE m <= end_date AND last_day(m) >= start_date AND b.line_type IN ('REVENUE','EXPENSE')
        ) amounts GROUP BY 1
    """,
        ("component",),
    ),
    "payroll_summary": MetricQuery(
        "Payroll Summary",
        """
        SELECT component, CASE WHEN component = 'headcount' THEN 'count' ELSE 'VND' END AS component_unit,
            amount AS value FROM (
            SELECT SUM(gross_salary) AS gross_salary, SUM(bonus) AS bonus,
                SUM(employer_contribution) AS employer_contribution, SUM(pit) AS personal_income_tax,
                COUNT(DISTINCT employee_code) AS headcount
            FROM payroll, period
            WHERE year_month BETWEEN strftime(start_date, '%Y-%m') AND strftime(end_date, '%Y-%m')
            HAVING COUNT(*) > 0
        ) UNPIVOT (amount FOR component IN (gross_salary, bonus, employer_contribution, personal_income_tax, headcount))
    """,
        ("component", "component_unit"),
    ),
    "mgmt_vs_tax_gap": MetricQuery(
        "Management vs Tax Gap",
        f"""
        SELECT COALESCE(tax_note, 'unspecified') AS component, SUM(net_debit) AS value
        FROM v_mgmt, period WHERE {_FLOW} AND tax_deductible IS FALSE
            AND left(account_code, 3) IN ('632','635','641','642','811') GROUP BY 1
    """,
        ("component",),
        required_views=("mgmt", "tax"),
    ),
    "vat_position": MetricQuery(
        "VAT Position",
        f"""
        SELECT component, amount AS value FROM (
            SELECT COALESCE(SUM(CASE WHEN starts_with(account_code, '33311')
                   THEN -net_debit ELSE 0 END), 0) AS output_vat,
                   COALESCE(SUM(CASE WHEN starts_with(account_code, '1331')
                   THEN net_debit ELSE 0 END), 0) AS input_vat, output_vat - input_vat AS net_vat
            FROM v_tax, period WHERE {_FLOW}
                AND COALESCE(source_document_type, '') NOT IN ('VAT_OFFSET','VAT_PAYMENT','TAX_PAYMENT')
        ) UNPIVOT (amount FOR component IN (output_vat, input_vat, net_vat))
    """,
        ("component",),
    ),
}
