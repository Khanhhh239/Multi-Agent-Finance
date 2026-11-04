from datetime import date
from decimal import Decimal

from agent4.text2sql.compiler import SQLCompiler
from agent4.text2sql.execution import DuckDBReadOnlyExecutor
from agent4.text2sql.models import SemanticPlanDraft, TimeDraft
from agent4.text2sql.validation import SemanticValidator


def execute(catalog, auth, database, metric_id, time, *, view=None, dimensions=None, top_k=None):
    metric = catalog.get(metric_id)
    draft = SemanticPlanDraft(
        plan_version="1.0", status="ready", metric_ids=[metric_id],
        time=time, dimensions=dimensions or [],
        filters=[], view=view or metric.default_view,
        operation="rank" if top_k else ("breakdown" if dimensions else "aggregate"),
        sort=None, top_k=top_k, comparison=None, question_for_user=None,
        unresolved_slots=[], reason_code=None,
    )
    # Ranking handlers own their trusted sort and bounded SQL template.
    if top_k:
        draft = draft.model_copy(update={"operation": "aggregate"})
    plan = SemanticValidator(catalog).validate(draft, auth)
    bound = SQLCompiler(catalog).compile(plan)
    return DuckDBReadOnlyExecutor(database).execute(bound)[0]


def test_custom_ar_aging_and_overdue(catalog, auth, finance_db):
    as_of = TimeDraft.as_of_date(date(2026, 10, 31))
    aging = execute(catalog, auth, finance_db, "ar_aging", as_of)
    overdue = execute(catalog, auth, finance_db, "overdue_receivables", as_of)
    assert aging.rows == [{"aging_bucket": "31_60", "ar_aging": "55.00"}]
    assert Decimal(overdue.rows[0]["overdue_receivables"]) == Decimal(55)
    by_customer = execute(
        catalog, auth, finance_db, "ar_aging", as_of, dimensions=["customer"]
    )
    assert by_customer.rows == [
        {"customer_code": "C1", "aging_bucket": "31_60", "ar_aging": "55.00"}
    ]


def test_custom_dso_actual_and_ap_due(catalog, auth, finance_db):
    period = TimeDraft.range(date(2026, 10, 1), date(2026, 10, 31))
    dso = execute(catalog, auth, finance_db, "dso_actual", period)
    due = execute(catalog, auth, finance_db, "ap_due_soon", period)
    assert Decimal(dso.rows[0]["dso_actual"]) == Decimal(10)
    assert Decimal(due.rows[0]["ap_due_soon"]) == Decimal(200)


def test_custom_anomaly_sales_and_payroll(catalog, auth, finance_db):
    period = TimeDraft.range(date(2026, 10, 1), date(2026, 10, 31))
    journals = execute(catalog, auth, finance_db, "unbalanced_journals", period)
    sales = execute(catalog, auth, finance_db, "top_sales_transactions", period, top_k=1)
    payroll = execute(
        catalog, auth, finance_db, "payroll_summary", period, dimensions=["department"]
    )
    assert journals.rows[0]["unbalanced_journals"] == 1
    assert sales.truncated is False
    assert sales.rows[0]["top_sales_transactions"] == "100.00"
    assert payroll.rows == [{"department_code": "ADMIN", "payroll_summary": "115.00"}]


def test_custom_tax_handlers(catalog, auth, finance_db):
    october = TimeDraft.range(date(2026, 10, 1), date(2026, 10, 31))
    september = TimeDraft.range(date(2026, 9, 1), date(2026, 9, 30))
    cit = execute(catalog, auth, finance_db, "cit_estimate", october, view="tax")
    gap = execute(catalog, auth, finance_db, "mgmt_vs_tax_gap", september, view="tax")
    vat = execute(catalog, auth, finance_db, "vat_position", september, view="tax")
    assert Decimal(cit.rows[0]["cit_estimate"]) == Decimal(3)
    assert Decimal(gap.rows[0]["mgmt_vs_tax_gap"]) == Decimal(7)
    assert Decimal(vat.rows[0]["vat_position"]) == Decimal(3)
