"""Small, hand-calculated fixtures for the new custom metric definitions."""

from decimal import Decimal

import duckdb
import pytest

from agent4.engine.metric_queries import METRIC_QUERIES


def _rows(db, metric, start="2026-08-01", end="2026-08-31"):
    return db.execute(
        f"""WITH period AS (
            SELECT CAST(? AS DATE) start_date, CAST(? AS DATE) end_date,
                DATE '2026-08-31' AS watermark
        ) SELECT * FROM ({METRIC_QUERIES[metric].sql}) metric_rows""",
        [start, end],
    ).fetchall()


def test_receivable_aging_applies_credits_once_and_excludes_future_receipts():
    with duckdb.connect() as db:
        db.execute("""
            CREATE TABLE ar_invoice (
                invoice_id INTEGER, customer_code VARCHAR, issue_date DATE,
                due_date DATE, total_amount DECIMAL(18,2)
            );
            INSERT INTO ar_invoice VALUES
                (1,'C','2026-06-01','2026-07-01',100),
                (2,'C','2026-07-01','2026-09-01',80),
                (3,'C','2026-09-01','2026-10-01',300);
            CREATE TABLE ar_receipt (
                invoice_id INTEGER, customer_code VARCHAR, receipt_date DATE,
                amount DECIMAL(18,2)
            );
            INSERT INTO ar_receipt VALUES
                (1,'C','2026-08-02',20), (NULL,'C','2026-08-03',25),
                (1,'C','2026-09-02',50);
            CREATE TABLE ar_adjustment (
                invoice_id INTEGER, customer_code VARCHAR, adjustment_date DATE,
                total_amount DECIMAL(18,2)
            );
            INSERT INTO ar_adjustment VALUES (1,'C','2026-08-04',5);
        """)
        assert dict(_rows(db, "ar_aging")) == {
            "0_not_due": Decimal(80),
            "3_61_90": Decimal(50),
        }
        assert _rows(db, "overdue_receivables") == [(Decimal(50),)]


@pytest.mark.parametrize(
    "metric_id", ["dso", "dpo", "dio", "cash_conversion_cycle", "cash_coverage_days"]
)
def test_days_metric_returns_undefined_when_denominator_is_zero(metric_id):
    with duckdb.connect() as db:
        db.execute("""
            CREATE TABLE v_mgmt (
                posting_date DATE, account_code VARCHAR, debit_amount DECIMAL(18,2),
                credit_amount DECIMAL(18,2), net_debit DECIMAL(18,2),
                is_closing BOOLEAN, source_module VARCHAR, source_document_type VARCHAR
            );
            INSERT INTO v_mgmt VALUES ('2026-07-31','112',100,0,100,false,'OPENING','OPENING');
        """)
        assert _rows(db, metric_id) == [(None,)]


def test_payroll_counts_distinct_people_and_retains_currency_by_component():
    with duckdb.connect() as db:
        db.execute("""
            CREATE TABLE payroll (
                year_month VARCHAR, employee_code VARCHAR, gross_salary DECIMAL(18,2),
                bonus DECIMAL(18,2), employer_contribution DECIMAL(18,2), pit DECIMAL(18,2)
            );
            INSERT INTO payroll VALUES
                ('2026-07','E1',100,2,3,4), ('2026-08','E1',110,4,5,6),
                ('2026-08','E2',80,8,6,4), ('2026-09','E3',90,9,9,9);
        """)
        assert set(_rows(db, "payroll_summary", start="2026-07-01")) == {
            ("gross_salary", "VND", Decimal(290)),
            ("bonus", "VND", Decimal(14)),
            ("employer_contribution", "VND", Decimal(14)),
            ("personal_income_tax", "VND", Decimal(14)),
            ("headcount", "count", Decimal(2)),
        }


def test_vat_position_uses_invoice_movements_and_excludes_settlement():
    with duckdb.connect() as db:
        db.execute("""
            CREATE TABLE v_tax (
                posting_date DATE, account_code VARCHAR, net_debit DECIMAL(18,2),
                is_closing BOOLEAN, source_module VARCHAR, source_document_type VARCHAR
            );
            INSERT INTO v_tax VALUES
                ('2026-08-01','33311',-100,false,'AR','SALES_INVOICE'),
                ('2026-08-02','33311',10,false,'AR','SALES_RETURN'),
                ('2026-08-02','1331',45,false,'AP','PURCHASE_INVOICE'),
                ('2026-08-30','33311',30,false,'GL','VAT_PAYMENT'),
                ('2026-08-31','1331',-45,false,'GL','VAT_OFFSET');
        """)
        assert dict(_rows(db, "vat_position")) == {
            "output_vat": Decimal(90),
            "input_vat": Decimal(45),
            "net_vat": Decimal(45),
        }


def test_payables_due_soon_freezes_payments_at_the_start_of_the_horizon():
    with duckdb.connect() as db:
        db.execute("""
            CREATE TABLE ap_bill (
                bill_id INTEGER, bill_date DATE, due_date DATE, total_amount DECIMAL(18,2)
            );
            INSERT INTO ap_bill VALUES
                (1,'2026-07-01','2026-07-31',100),
                (2,'2026-07-15','2026-08-31',150),
                (3,'2026-07-15','2026-09-01',999),
                (4,'2026-08-02','2026-08-31',999);
            CREATE TABLE ap_payment (bill_id INTEGER, payment_date DATE, amount DECIMAL(18,2));
            INSERT INTO ap_payment VALUES (1,'2026-08-01',40), (2,'2026-08-02',70);
        """)
        assert _rows(db, "ap_due_soon") == [(Decimal(210),)]


def test_budget_comparison_prorates_partial_months_without_double_counting_actuals():
    with duckdb.connect() as db:
        db.execute("""
            CREATE TABLE budget (year_no INT, month_no INT, line_type VARCHAR, amount DECIMAL(18,2));
            INSERT INTO budget VALUES (2026,8,'REVENUE',310), (2026,8,'EXPENSE',155);
            CREATE TABLE v_mgmt (
                posting_date DATE, account_code VARCHAR, net_debit DECIMAL(18,2),
                is_closing BOOLEAN, source_module VARCHAR
            );
            INSERT INTO v_mgmt VALUES
                ('2026-08-01','5111',-90,false,'AR'), ('2026-08-02','5111',10,false,'AR'),
                ('2026-08-02','6422',25,false,'AP'), ('2026-08-11','6422',100,false,'AP'),
                ('2026-08-10','5111',999,true,'GL');
        """)
        assert dict(_rows(db, "budget_vs_actual", end="2026-08-10")) == {
            "actual_revenue": Decimal(80),
            "actual_expense": Decimal(25),
            "budget_revenue": Decimal(100),
            "budget_expense": Decimal(50),
        }
