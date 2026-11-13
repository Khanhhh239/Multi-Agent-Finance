from __future__ import annotations

from datetime import date

import duckdb
import pytest

from agent4.text2sql.catalog import CatalogSnapshot
from agent4.text2sql.compiler import SQLCompiler
from agent4.text2sql.execution import DuckDBReadOnlyExecutor
from agent4.text2sql.models import AuthContext
from agent4.text2sql.selector import OfflineSemanticSelector
from agent4.text2sql.service import QueryService
from agent4.text2sql.validation import SemanticValidator


@pytest.fixture(scope="session")
def catalog():
    return CatalogSnapshot()


@pytest.fixture()
def auth():
    return AuthContext(
        user_id="reviewer",
        tenant_id="tenant_demo_A",
        roles=frozenset({"finance_analyst", "payroll_viewer"}),
        allowed_views=frozenset({"mgmt", "tax"}),
    )


@pytest.fixture()
def finance_db(tmp_path):
    path = tmp_path / "finance.duckdb"
    connection = duckdb.connect(str(path))
    connection.execute("""
        CREATE TABLE ledger(
          posting_date DATE, year_no INTEGER, quarter_no INTEGER,
          account_code VARCHAR, partner_code VARCHAR, item_code VARCHAR,
          product_line VARCHAR, cost_category VARCHAR, branch_code VARCHAR,
          department_code VARCHAR, debit_amount DECIMAL(18,2), credit_amount DECIMAL(18,2),
          source_document_type VARCHAR, is_closing BOOLEAN, tax_deductible BOOLEAN
        );
        CREATE VIEW v_mgmt AS SELECT * FROM ledger;
        CREATE VIEW v_tax AS SELECT * FROM ledger WHERE tax_deductible;
        CREATE TABLE company_info(key VARCHAR, value VARCHAR);
        INSERT INTO company_info VALUES ('as_of_date', '2026-10-31');
        CREATE TABLE ar_invoice(
          invoice_id INTEGER, einvoice_no VARCHAR, issue_date DATE, due_date DATE,
          customer_code VARCHAR, subtotal DECIMAL(18,2), total_amount DECIMAL(18,2),
          is_opening BOOLEAN
        );
        CREATE TABLE ar_receipt(
          invoice_id INTEGER, receipt_date DATE, amount DECIMAL(18,2)
        );
        CREATE TABLE ar_adjustment(
          invoice_id INTEGER, adjustment_date DATE, total_amount DECIMAL(18,2)
        );
        CREATE TABLE ap_bill(
          bill_id INTEGER, bill_date DATE, due_date DATE, total_amount DECIMAL(18,2)
        );
        CREATE TABLE ap_payment(
          bill_id INTEGER, payment_date DATE, amount DECIMAL(18,2)
        );
        CREATE TABLE payroll(
          year_month VARCHAR, branch_code VARCHAR, department_code VARCHAR,
          gross_salary DECIMAL(18,2), bonus DECIMAL(18,2),
          employer_contribution DECIMAL(18,2)
        );
        CREATE TABLE gl_entry(
          journal_id VARCHAR, posting_date DATE, debit_amount DECIMAL(18,2),
          credit_amount DECIMAL(18,2)
        );
        INSERT INTO ar_invoice VALUES (1, 'INV-1', '2026-10-01', '2026-09-01', 'C1', 100, 110, FALSE);
        INSERT INTO ar_receipt VALUES (1, '2026-10-11', 55);
        INSERT INTO ap_bill VALUES (1, '2026-10-01', '2026-10-20', 200);
        INSERT INTO ap_payment VALUES (1, '2026-10-10', 50);
        INSERT INTO payroll VALUES ('2026-10', 'HN', 'ADMIN', 100, 10, 5);
        INSERT INTO gl_entry VALUES
          ('BALANCED', '2026-10-01', 10, 0), ('BALANCED', '2026-10-01', 0, 10),
          ('UNBALANCED', '2026-10-02', 5, 0);
    """)
    rows = [
        (
            date(2026, 9, 30),
            2026,
            3,
            "111",
            None,
            None,
            None,
            None,
            "HN",
            None,
            1000,
            0,
            "OPENING",
            False,
            True,
        ),
        (
            date(2026, 10, 2),
            2026,
            4,
            "131",
            "C1",
            None,
            None,
            None,
            "HN",
            None,
            100,
            0,
            "SALES_INVOICE",
            False,
            True,
        ),
        (
            date(2026, 10, 2),
            2026,
            4,
            "511",
            "C1",
            None,
            None,
            None,
            "HN",
            None,
            0,
            100,
            "SALES_INVOICE",
            False,
            True,
        ),
        (
            date(2026, 10, 3),
            2026,
            4,
            "511",
            "C1",
            None,
            None,
            None,
            "HN",
            None,
            10,
            0,
            "SALES_RETURN",
            False,
            True,
        ),
        (
            date(2026, 10, 3),
            2026,
            4,
            "131",
            "C1",
            None,
            None,
            None,
            "HN",
            None,
            0,
            10,
            "SALES_RETURN",
            False,
            True,
        ),
        (
            date(2026, 10, 4),
            2026,
            4,
            "632",
            "C1",
            None,
            None,
            None,
            "HN",
            None,
            60,
            0,
            "GOODS_ISSUE",
            False,
            True,
        ),
        (
            date(2026, 10, 4),
            2026,
            4,
            "156",
            "C1",
            None,
            None,
            None,
            "HN",
            None,
            0,
            60,
            "GOODS_ISSUE",
            False,
            True,
        ),
        (
            date(2026, 10, 5),
            2026,
            4,
            "642",
            None,
            None,
            None,
            "KHAC",
            "HN",
            "ADMIN",
            15,
            0,
            "CASH_EXPENSE",
            False,
            True,
        ),
        (
            date(2026, 10, 5),
            2026,
            4,
            "111",
            None,
            None,
            None,
            None,
            "HN",
            None,
            0,
            15,
            "CASH_EXPENSE",
            False,
            True,
        ),
        (
            date(2026, 10, 6),
            2026,
            4,
            "821",
            None,
            None,
            None,
            None,
            "HN",
            None,
            4,
            0,
            "CIT",
            False,
            True,
        ),
        (
            date(2026, 10, 6),
            2026,
            4,
            "3334",
            None,
            None,
            None,
            None,
            "HN",
            None,
            0,
            4,
            "CIT",
            False,
            True,
        ),
        (
            date(2026, 10, 7),
            2026,
            4,
            "111",
            "C1",
            None,
            None,
            None,
            "HN",
            None,
            80,
            0,
            "RECEIPT",
            False,
            True,
        ),
        (
            date(2026, 10, 7),
            2026,
            4,
            "131",
            "C1",
            None,
            None,
            None,
            "HN",
            None,
            0,
            80,
            "RECEIPT",
            False,
            True,
        ),
        (
            date(2026, 10, 8),
            2026,
            4,
            "331",
            "V1",
            None,
            None,
            None,
            "HN",
            None,
            20,
            0,
            "PAYMENT",
            False,
            True,
        ),
        (
            date(2026, 10, 8),
            2026,
            4,
            "111",
            "V1",
            None,
            None,
            None,
            "HN",
            None,
            0,
            20,
            "PAYMENT",
            False,
            True,
        ),
        (
            date(2026, 10, 31),
            2026,
            4,
            "511",
            None,
            None,
            None,
            None,
            "HN",
            None,
            90,
            0,
            "CLOSING",
            True,
            True,
        ),
        (
            date(2026, 10, 31),
            2026,
            4,
            "911",
            None,
            None,
            None,
            None,
            "HN",
            None,
            0,
            90,
            "CLOSING",
            True,
            True,
        ),
        (
            date(2026, 10, 31),
            2026,
            4,
            "911",
            None,
            None,
            None,
            None,
            "HN",
            None,
            60,
            0,
            "CLOSING",
            True,
            True,
        ),
        (
            date(2026, 10, 31),
            2026,
            4,
            "632",
            None,
            None,
            None,
            None,
            "HN",
            None,
            0,
            60,
            "CLOSING",
            True,
            True,
        ),
        (
            date(2026, 9, 20),
            2026,
            3,
            "642",
            None,
            None,
            None,
            "KHAC",
            "HN",
            None,
            7,
            0,
            "EXPENSE",
            False,
            False,
        ),
        (
            date(2026, 9, 20),
            2026,
            3,
            "331",
            None,
            None,
            None,
            None,
            "HN",
            None,
            0,
            7,
            "EXPENSE",
            False,
            False,
        ),
        (
            date(2026, 9, 21),
            2026,
            3,
            "33311",
            None,
            None,
            None,
            None,
            "HN",
            None,
            0,
            8,
            "VAT",
            False,
            True,
        ),
        (
            date(2026, 9, 21),
            2026,
            3,
            "1331",
            None,
            None,
            None,
            None,
            "HN",
            None,
            5,
            0,
            "VAT",
            False,
            True,
        ),
    ]
    connection.executemany("INSERT INTO ledger VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    connection.close()
    return path


@pytest.fixture()
def finance_service(catalog, finance_db):
    return QueryService(
        catalog,
        OfflineSemanticSelector(catalog, today=date(2026, 10, 31)),
        SemanticValidator(catalog),
        SQLCompiler(catalog),
        DuckDBReadOnlyExecutor(finance_db),
    )
