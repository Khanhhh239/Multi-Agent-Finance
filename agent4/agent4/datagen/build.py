"""Materialise the simulated company into a DuckDB warehouse.

Run::

    python -m agent4.datagen.build --out data/cfo_warehouse.duckdb

The warehouse is a star schema (``gl_entry`` fact + dimensions) extended with
the sub-ledgers a real ERP has (AR invoices/receipts, AP bills/payments,
inventory movements, payroll, fixed assets, loans, budgets) and two governed
views — ``v_mgmt`` (management: every transaction) and ``v_tax`` (tax: only
CIT-deductible lines) — that the semantic metric layer reads from.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from ..config import get_settings
from . import company as C
from .simulator import Simulator, add_months, is_business_day

SCHEMA_SQL = """
CREATE TABLE dim_account(
  account_key INTEGER PRIMARY KEY, account_code VARCHAR UNIQUE NOT NULL, account_name VARCHAR NOT NULL,
  account_type VARCHAR NOT NULL, normal_balance VARCHAR NOT NULL, parent_account_code VARCHAR, level SMALLINT,
  is_postable BOOLEAN, effective_from DATE, effective_to DATE);
CREATE TABLE dim_branch(branch_key INTEGER PRIMARY KEY, branch_code VARCHAR UNIQUE, branch_name VARCHAR, region VARCHAR);
CREATE TABLE dim_department(department_key INTEGER PRIMARY KEY, department_code VARCHAR UNIQUE, department_name VARCHAR,
  expense_account VARCHAR);
CREATE TABLE dim_employee(employee_key INTEGER PRIMARY KEY, employee_code VARCHAR UNIQUE, employee_name VARCHAR, title VARCHAR,
  department_code VARCHAR, branch_code VARCHAR, hire_date DATE, leave_date DATE, base_salary DECIMAL(18,2));
CREATE TABLE dim_partner(partner_key INTEGER PRIMARY KEY, partner_code VARCHAR UNIQUE, partner_name VARCHAR, partner_type VARCHAR,
  tax_id VARCHAR, segment VARCHAR, vendor_category VARCHAR, branch_code VARCHAR, province VARCHAR, payment_terms_days INTEGER,
  credit_limit DECIMAL(18,2), salesperson_code VARCHAR, is_active BOOLEAN);
CREATE TABLE dim_item(item_key INTEGER PRIMARY KEY, item_code VARCHAR UNIQUE, item_name VARCHAR, item_type VARCHAR, product_line VARCHAR,
  unit VARCHAR, list_price DECIMAL(18,2), standard_cost DECIMAL(18,2), default_vendor VARCHAR, is_active BOOLEAN);
CREATE TABLE dim_product_line(product_line VARCHAR PRIMARY KEY, product_line_name VARCHAR);
CREATE TABLE dim_cost_category(cost_category VARCHAR PRIMARY KEY, cost_category_name VARCHAR);
CREATE TABLE dim_period(period_key INTEGER PRIMARY KEY, calendar_date DATE UNIQUE, day_of_month SMALLINT, day_of_week SMALLINT,
  is_business_day BOOLEAN, week_of_year SMALLINT, month_no SMALLINT, quarter_no SMALLINT, year_no SMALLINT, year_month VARCHAR,
  month_start_date DATE, month_end_date DATE, is_month_closed BOOLEAN);
CREATE TABLE period_close(year_month VARCHAR PRIMARY KEY, status VARCHAR, closed_at TIMESTAMP);
CREATE TABLE gl_journal(journal_id VARCHAR PRIMARY KEY, posting_date DATE, doc_type VARCHAR, doc_no VARCHAR, description VARCHAR,
  source_module VARCHAR, is_closing BOOLEAN, created_by VARCHAR, created_at TIMESTAMP);
CREATE TABLE gl_entry(
  entry_id BIGINT PRIMARY KEY, journal_id VARCHAR NOT NULL, entry_no INTEGER, posting_date DATE NOT NULL, period_key INTEGER,
  account_key INTEGER NOT NULL, partner_key INTEGER, item_key INTEGER, branch_key INTEGER, department_key INTEGER, employee_key INTEGER,
  product_line VARCHAR, cost_category VARCHAR, description VARCHAR,
  debit_amount DECIMAL(18,2) NOT NULL, credit_amount DECIMAL(18,2) NOT NULL, currency_code VARCHAR DEFAULT 'VND',
  source_document_type VARCHAR, source_document_no VARCHAR, source_module VARCHAR, is_closing BOOLEAN,
  tax_deductible BOOLEAN, tax_note VARCHAR, created_by VARCHAR, created_at TIMESTAMP,
  CHECK (debit_amount >= 0 AND credit_amount >= 0),
  CHECK ((debit_amount > 0 AND credit_amount = 0) OR (debit_amount = 0 AND credit_amount > 0)));
CREATE TABLE ar_invoice(invoice_id INTEGER PRIMARY KEY, journal_id VARCHAR, einvoice_no VARCHAR, issue_date DATE, due_date DATE,
  customer_code VARCHAR, branch_code VARCHAR, salesperson_code VARCHAR, subtotal DECIMAL(18,2), vat_amount DECIMAL(18,2),
  total_amount DECIMAL(18,2), payment_terms_days INTEGER, description VARCHAR, is_opening BOOLEAN);
CREATE TABLE ar_invoice_line(invoice_id INTEGER, item_code VARCHAR, quantity INTEGER, unit_price DECIMAL(18,2), net_amount DECIMAL(18,2),
  vat_amount DECIMAL(18,2), cost_amount DECIMAL(18,2));
CREATE TABLE ar_receipt(receipt_id INTEGER PRIMARY KEY, journal_id VARCHAR, receipt_date DATE, bank_txn_date DATE, customer_code VARCHAR,
  invoice_id INTEGER, amount DECIMAL(18,2), method VARCHAR, cash_account VARCHAR);
CREATE TABLE ar_adjustment(adjustment_id INTEGER PRIMARY KEY, journal_id VARCHAR, adjustment_date DATE, customer_code VARCHAR,
  invoice_id INTEGER, adjustment_type VARCHAR, net_amount DECIMAL(18,2), vat_amount DECIMAL(18,2), total_amount DECIMAL(18,2));
CREATE TABLE ap_bill(bill_id INTEGER PRIMARY KEY, journal_id VARCHAR, vendor_invoice_no VARCHAR, bill_date DATE, due_date DATE,
  vendor_code VARCHAR, branch_code VARCHAR, category VARCHAR, subtotal DECIMAL(18,2), vat_amount DECIMAL(18,2), total_amount DECIMAL(18,2),
  description VARCHAR, tax_deductible BOOLEAN, is_opening BOOLEAN);
CREATE TABLE ap_payment(payment_id INTEGER PRIMARY KEY, journal_id VARCHAR, payment_date DATE, vendor_code VARCHAR, bill_id INTEGER,
  amount DECIMAL(18,2), method VARCHAR, cash_account VARCHAR);
CREATE TABLE inventory_txn(txn_id INTEGER PRIMARY KEY, journal_id VARCHAR, txn_date DATE, item_code VARCHAR, txn_type VARCHAR,
  quantity INTEGER, unit_cost DECIMAL(18,4), value DECIMAL(18,2));
CREATE TABLE payroll(year_month VARCHAR, employee_code VARCHAR, branch_code VARCHAR, department_code VARCHAR, gross_salary DECIMAL(18,2),
  bonus DECIMAL(18,2), insurance_base DECIMAL(18,2), employer_contribution DECIMAL(18,2), employee_contribution DECIMAL(18,2),
  pit DECIMAL(18,2), net_pay DECIMAL(18,2));
CREATE TABLE fixed_asset(asset_code VARCHAR PRIMARY KEY, asset_name VARCHAR, branch_code VARCHAR, department_code VARCHAR,
  acquisition_date DATE, cost DECIMAL(18,2), useful_life_months INTEGER, monthly_depreciation DECIMAL(18,2));
CREATE TABLE loan(loan_id VARCHAR PRIMARY KEY, lender VARCHAR, loan_type VARCHAR, start_date DATE, principal DECIMAL(18,2),
  annual_rate DOUBLE, maturity_date DATE);
CREATE TABLE loan_schedule(loan_id VARCHAR, due_date DATE, principal DECIMAL(18,2));
CREATE TABLE service_contract(contract_no VARCHAR PRIMARY KEY, customer_code VARCHAR, item_code VARCHAR, start_date DATE, end_date DATE);
CREATE TABLE budget(year_no SMALLINT, month_no SMALLINT, branch_code VARCHAR, line_type VARCHAR, cost_category VARCHAR, amount DECIMAL(18,2));
CREATE TABLE company_info(key VARCHAR PRIMARY KEY, value VARCHAR);
"""

VIEWS_SQL = """
CREATE OR REPLACE TABLE gl_wide AS
SELECT g.entry_id, g.journal_id, g.entry_no, g.posting_date, g.period_key, p.year_month, p.year_no, p.quarter_no, p.month_no,
       a.account_code, a.account_name, a.account_type,
       pa.partner_code, pa.partner_name, pa.partner_type, pa.segment,
       i.item_code, i.item_name, g.product_line, g.cost_category,
       b.branch_code, d.department_code, e.employee_code, e.employee_name,
       g.description, g.debit_amount, g.credit_amount, g.debit_amount - g.credit_amount AS net_debit,
       g.source_document_type, g.source_document_no, g.source_module, g.is_closing, g.tax_deductible, g.tax_note,
       g.created_by, g.created_at
FROM gl_entry g
JOIN dim_account a USING (account_key)
LEFT JOIN dim_period p USING (period_key)
LEFT JOIN dim_partner pa USING (partner_key)
LEFT JOIN dim_item i USING (item_key)
LEFT JOIN dim_branch b USING (branch_key)
LEFT JOIN dim_department d USING (department_key)
LEFT JOIN dim_employee e USING (employee_key)
ORDER BY g.posting_date, g.entry_id;
-- Denormalised GL (materialised for speed; rebuilt by the loader).
CREATE OR REPLACE VIEW v_gl AS SELECT * FROM gl_wide;
-- Management view: 100% of real transactions (closing entries flagged, not removed).
CREATE OR REPLACE VIEW v_mgmt AS SELECT * FROM v_gl;
-- Tax view: only CIT-deductible lines (non-deductible expenses removed).
CREATE OR REPLACE VIEW v_tax AS SELECT * FROM v_gl WHERE tax_deductible;
"""


def _df(rows, cols):
    return pd.DataFrame(rows, columns=cols)


def build(out: Path, seed: int = 20251, as_of: date | None = None, last_closed: str | None = None, quiet: bool = False) -> dict:
    settings = get_settings()
    as_of = as_of or settings.as_of
    last_closed = last_closed or settings.last_closed_month
    t0 = time.time()
    sim = Simulator(seed=seed, as_of=as_of, last_closed_month=last_closed)
    sim.run()
    t_sim = time.time() - t0
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    con = duckdb.connect(str(out))
    con.execute(SCHEMA_SQL)

    # ---- dimensions
    acc_rows = []
    for k, (code, name, typ, nb, parent) in enumerate(C.ACCOUNTS, start=1):
        has_child = any(a[4] == code for a in C.ACCOUNTS)
        acc_rows.append((k, code, name, typ, nb, parent, 1 if parent is None else 2, not has_child, date(2017, 1, 1), None))
    acc = _df(acc_rows, ["account_key", "account_code", "account_name", "account_type", "normal_balance", "parent_account_code", "level",
                         "is_postable", "effective_from", "effective_to"])
    con.execute("INSERT INTO dim_account SELECT * FROM acc")
    acc_key = dict(zip(acc.account_code, acc.account_key))
    br = _df([(k, b[0], b[1], b[2]) for k, b in enumerate(C.BRANCHES, 1)], ["branch_key", "branch_code", "branch_name", "region"])
    con.execute("INSERT INTO dim_branch SELECT * FROM br")
    br_key = dict(zip(br.branch_code, br.branch_key))
    dp = _df([(k, d[0], d[1], d[2]) for k, d in enumerate(C.DEPARTMENTS, 1)], ["department_key", "department_code", "department_name", "expense_account"])
    con.execute("INSERT INTO dim_department SELECT * FROM dp")
    dp_key = dict(zip(dp.department_code, dp.department_key))
    em = _df([(k, e["code"], e["name"], e["title"], e["dept"], e["branch"], e["hire"], e["leave"], e["salary"]) for k, e in enumerate(sim.employees, 1)],
             ["employee_key", "employee_code", "employee_name", "title", "department_code", "branch_code", "hire_date", "leave_date", "base_salary"])
    con.execute("INSERT INTO dim_employee SELECT * FROM em")
    em_key = dict(zip(em.employee_code, em.employee_key))
    partners = list(sim.customers.values()) + list(sim.vendors.values())
    pa = _df([(k, p.code, p.name, p.ptype, p.tax_id, p.segment, p.category, p.branch, p.province, p.terms, p.credit_limit, p.salesperson, True)
              for k, p in enumerate(partners, 1)],
             ["partner_key", "partner_code", "partner_name", "partner_type", "tax_id", "segment", "vendor_category", "branch_code", "province",
              "payment_terms_days", "credit_limit", "salesperson_code", "is_active"])
    con.execute("INSERT INTO dim_partner SELECT * FROM pa")
    pa_key = dict(zip(pa.partner_code, pa.partner_key))
    it = _df([(k, i.spec.code, i.spec.name, "SERVICE" if i.spec.is_service else "PRODUCT", i.spec.line, i.spec.unit, i.spec.list_price,
               round(i.spec.list_price * i.spec.cost_ratio, -3), i.vendor or None, True) for k, i in enumerate(sim.items.values(), 1)],
             ["item_key", "item_code", "item_name", "item_type", "product_line", "unit", "list_price", "standard_cost", "default_vendor", "is_active"])
    con.execute("INSERT INTO dim_item SELECT * FROM it")
    it_key = dict(zip(it.item_code, it.item_key))
    con.executemany("INSERT INTO dim_product_line VALUES (?, ?)", C.PRODUCT_LINES)
    con.executemany("INSERT INTO dim_cost_category VALUES (?, ?)", C.COST_CATEGORIES)
    # periods
    d = date(2024, 12, 1)
    rows = []
    while d <= date(2026, 12, 31):
        ym = f"{d:%Y-%m}"
        me = add_months(d.replace(day=1), 1) - timedelta(days=1)
        rows.append((int(f"{d:%Y%m%d}"), d, d.day, d.isoweekday(), is_business_day(d), d.isocalendar()[1], d.month, (d.month - 1) // 3 + 1,
                     d.year, ym, d.replace(day=1), me, ym <= last_closed))
        d += timedelta(days=1)
    per = _df(rows, ["period_key", "calendar_date", "day_of_month", "day_of_week", "is_business_day", "week_of_year", "month_no", "quarter_no",
                     "year_no", "year_month", "month_start_date", "month_end_date", "is_month_closed"])
    con.execute("INSERT INTO dim_period SELECT * FROM per")
    pc = []
    m = date(2025, 1, 1)
    while m <= as_of:
        ym = f"{m:%Y-%m}"
        closed = ym <= last_closed
        closed_at = pd.Timestamp(add_months(m, 1) + timedelta(days=6)) if closed else None
        pc.append((ym, "CLOSED" if closed else "OPEN", closed_at))
        m = add_months(m, 1)
    pcd = _df(pc, ["year_month", "status", "closed_at"])
    con.execute("INSERT INTO period_close SELECT * FROM pcd")

    # ---- facts
    jr = _df(sim.L.journals, ["journal_id", "posting_date", "doc_type", "doc_no", "description", "source_module", "is_closing", "created_by", "created_at"])
    con.execute("INSERT INTO gl_journal SELECT * FROM jr")
    gl = _df(sim.L.rows, ["entry_id", "journal_id", "entry_no", "posting_date", "account", "partner", "item", "branch", "department", "employee",
                          "product_line", "cost_category", "description", "debit_amount", "credit_amount", "source_document_type",
                          "source_document_no", "source_module", "is_closing", "tax_deductible", "tax_note", "created_by", "created_at"])
    gl["period_key"] = pd.to_datetime(gl.posting_date).dt.strftime("%Y%m%d").astype(int)
    gl["account_key"] = gl.account.map(acc_key)
    if gl.account_key.isna().any():
        raise RuntimeError(f"unknown accounts: {set(gl.account[gl.account_key.isna()])}")
    gl["partner_key"] = gl.partner.map(pa_key).astype("Int64")
    gl["item_key"] = gl["item"].map(it_key).astype("Int64")
    gl["branch_key"] = gl.branch.map(br_key).astype("Int64")
    gl["department_key"] = gl.department.map(dp_key).astype("Int64")
    gl["employee_key"] = gl.employee.map(em_key).astype("Int64")
    gl["currency_code"] = "VND"
    gl = gl[["entry_id", "journal_id", "entry_no", "posting_date", "period_key", "account_key", "partner_key", "item_key", "branch_key",
             "department_key", "employee_key", "product_line", "cost_category", "description", "debit_amount", "credit_amount", "currency_code",
             "source_document_type", "source_document_no", "source_module", "is_closing", "tax_deductible", "tax_note", "created_by", "created_at"]]
    con.execute("INSERT INTO gl_entry SELECT * FROM gl")
    tables = {
        "ar_invoice": (sim.ar_invoice_rows, ["invoice_id", "journal_id", "einvoice_no", "issue_date", "due_date", "customer_code", "branch_code",
                                             "salesperson_code", "subtotal", "vat_amount", "total_amount", "payment_terms_days", "description", "is_opening"]),
        "ar_invoice_line": (sim.ar_line_rows, ["invoice_id", "item_code", "quantity", "unit_price", "net_amount", "vat_amount", "cost_amount"]),
        "ar_receipt": (sim.ar_receipt_rows, ["receipt_id", "journal_id", "receipt_date", "bank_txn_date", "customer_code", "invoice_id", "amount",
                                             "method", "cash_account"]),
        "ar_adjustment": (sim.ar_adj_rows, ["adjustment_id", "journal_id", "adjustment_date", "customer_code", "invoice_id", "adjustment_type",
                                            "net_amount", "vat_amount", "total_amount"]),
        "ap_bill": (sim.ap_bill_rows, ["bill_id", "journal_id", "vendor_invoice_no", "bill_date", "due_date", "vendor_code", "branch_code", "category",
                                       "subtotal", "vat_amount", "total_amount", "description", "tax_deductible", "is_opening"]),
        "ap_payment": (sim.ap_payment_rows, ["payment_id", "journal_id", "payment_date", "vendor_code", "bill_id", "amount", "method", "cash_account"]),
        "inventory_txn": (sim.inv_rows, ["txn_id", "journal_id", "txn_date", "item_code", "txn_type", "quantity", "unit_cost", "value"]),
        "payroll": (sim.payroll_rows, ["year_month", "employee_code", "branch_code", "department_code", "gross_salary", "bonus", "insurance_base",
                                       "employer_contribution", "employee_contribution", "pit", "net_pay"]),
        "fixed_asset": (sim.asset_rows, ["asset_code", "asset_name", "branch_code", "department_code", "acquisition_date", "cost",
                                         "useful_life_months", "monthly_depreciation"]),
        "loan": (sim.loan_rows, ["loan_id", "lender", "loan_type", "start_date", "principal", "annual_rate", "maturity_date"]),
        "service_contract": (sim.contract_rows, ["contract_no", "customer_code", "item_code", "start_date", "end_date"]),
    }
    for name, (rows, cols) in tables.items():
        frame = _df(rows, cols)
        con.register("frame", frame)
        con.execute(f"INSERT INTO {name} SELECT * FROM frame")
        con.unregister("frame")
    sched = []
    for lid, ln in sim.loans.items():
        bal, d = ln["balance"], as_of
        if ln.get("freq") in ("Q", "M") and bal > 0:
            y, m = as_of.year, as_of.month
            while bal > 0 and y <= as_of.year + 3:
                me = add_months(date(y, m, 1), 1) - timedelta(days=1)
                if me > as_of and (ln["freq"] == "M" or m in (3, 6, 9, 12)):
                    amt = min(ln["repay"], bal)
                    sched.append((lid, me, amt))
                    bal -= amt
                y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    con.executemany("INSERT INTO loan_schedule VALUES (?, ?, ?)", sched)
    con.execute(VIEWS_SQL)
    _build_budget(con)
    info = {**C.COMPANY, "as_of_date": as_of.isoformat(), "last_closed_month": last_closed, "data_start": "2025-01-01", "seed": str(seed),
            "generator": "agent4.datagen v2 (event-driven simulation)"}
    con.executemany("INSERT INTO company_info VALUES (?, ?)", [(k, str(v)) for k, v in info.items()])
    con.execute("CREATE TABLE ground_truth AS SELECT * FROM read_json_auto(?)", [_write_gt(out, sim.ground_truth)])
    stats = _validate(con, quiet=quiet)
    stats["simulation_seconds"] = round(t_sim, 1)
    con.close()
    return stats


def _write_gt(out: Path, gt: list[dict]) -> str:
    path = out.with_name(out.stem + "_ground_truth.json")
    rows = [{"id": g["id"], "type": g["type"], "detail": g["detail"], "payload": json.dumps(g, ensure_ascii=False)} for g in gt]
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return str(path)


def _build_budget(con: duckdb.DuckDBPyConnection) -> None:
    """Budgets are set the way a real FP&A team does it: 2025 ≈ prior-year plan
    (±5% noise around actuals), 2026 = 2025 actuals × growth targets."""
    con.execute("""
    CREATE TEMP TABLE actual AS
    SELECT year_no, month_no, branch_code, cost_category,
           SUM(CASE WHEN account_code LIKE '511%' THEN credit_amount - debit_amount ELSE 0 END) AS revenue,
           SUM(CASE WHEN account_code LIKE '642%' THEN debit_amount - credit_amount ELSE 0 END) AS opex
    FROM v_gl WHERE NOT is_closing AND year_no = 2025 GROUP BY ALL""")
    con.execute("SELECT setseed(0.42)")
    con.execute("""
    INSERT INTO budget
    SELECT year_no, month_no, branch_code, 'REVENUE', NULL, ROUND(SUM(revenue) * ANY_VALUE(0.97 + 0.06 * random()), -6)
    FROM actual WHERE branch_code IS NOT NULL GROUP BY year_no, month_no, branch_code HAVING SUM(revenue) > 0
    UNION ALL
    SELECT 2026, month_no, branch_code, 'REVENUE', NULL, ROUND(SUM(revenue) * 1.20, -6)
    FROM actual WHERE branch_code IS NOT NULL GROUP BY month_no, branch_code HAVING SUM(revenue) > 0
    UNION ALL
    SELECT year_no, month_no, COALESCE(branch_code, 'HN'), 'EXPENSE', cost_category, ROUND(SUM(opex) * ANY_VALUE(0.96 + 0.08 * random()), -5)
    FROM actual WHERE cost_category IS NOT NULL GROUP BY year_no, month_no, COALESCE(branch_code, 'HN'), cost_category HAVING SUM(opex) > 0
    UNION ALL
    SELECT 2026, month_no, COALESCE(branch_code, 'HN'), 'EXPENSE', cost_category,
           ROUND(SUM(opex) * CASE cost_category WHEN 'MARKETING' THEN 1.15 WHEN 'LUONG' THEN 1.07 ELSE 1.05 END, -5)
    FROM actual WHERE cost_category IS NOT NULL GROUP BY month_no, COALESCE(branch_code, 'HN'), cost_category HAVING SUM(opex) > 0""")


def _validate(con: duckdb.DuckDBPyConnection, quiet: bool = False) -> dict:
    q = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    stats = {
        "gl_lines": q("SELECT COUNT(*) FROM gl_entry"),
        "journals": q("SELECT COUNT(*) FROM gl_journal"),
        "ar_invoices": q("SELECT COUNT(*) FROM ar_invoice"),
        "ap_bills": q("SELECT COUNT(*) FROM ap_bill"),
        "unbalanced_journals": q("SELECT COUNT(*) FROM (SELECT journal_id FROM gl_entry GROUP BY 1 HAVING SUM(debit_amount) <> SUM(credit_amount))"),
        "revenue_2025": float(q("SELECT SUM(credit_amount-debit_amount) FROM v_gl WHERE account_code LIKE '511%' AND NOT is_closing AND year_no=2025")),
        "net_profit_2025": float(q("""SELECT -SUM(net_debit) FROM v_gl WHERE NOT is_closing AND year_no=2025
                                      AND regexp_matches(account_code, '^[5-8]')""")),
        "ar_gl_vs_subledger_gap": float(q("""SELECT (SELECT SUM(net_debit) FROM v_gl WHERE account_code='131')
            - ((SELECT SUM(total_amount) FROM ar_invoice) - (SELECT SUM(amount) FROM ar_receipt) - (SELECT SUM(total_amount) FROM ar_adjustment))""")),
        "ap_gl_vs_subledger_gap": float(q("""SELECT (SELECT -SUM(net_debit) FROM v_gl WHERE account_code='331')
            - ((SELECT SUM(total_amount) FROM ap_bill) - (SELECT SUM(amount) FROM ap_payment))""")),
        "inventory_gl_vs_subledger_gap": float(q("""SELECT (SELECT SUM(net_debit) FROM v_gl WHERE account_code LIKE '156%')
            - (SELECT SUM(value) FROM inventory_txn)""")),
        "min_bank_balance": float(q("""SELECT MIN(bal) FROM (SELECT posting_date, SUM(SUM(net_debit)) OVER (ORDER BY posting_date) bal
            FROM v_gl WHERE account_code LIKE '112%' GROUP BY 1)""")),
    }
    if not quiet:
        for k, v in stats.items():
            print(f"  {k:32s} {v:,.0f}" if isinstance(v, (int, float)) else f"  {k:32s} {v}")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=get_settings().warehouse_path)
    ap.add_argument("--seed", type=int, default=20251)
    args = ap.parse_args()
    print(f"Simulating Minh Phát books → {args.out}")
    stats = build(args.out, seed=args.seed)
    print(f"done in {stats['simulation_seconds']}s simulation")


if __name__ == "__main__":
    main()
