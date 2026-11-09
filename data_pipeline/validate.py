"""Independent accounting/foreign-key checks and a new metric baseline."""
import argparse
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

import duckdb


def serial(value):
    return str(value) if isinstance(value,Decimal) else value.isoformat() if hasattr(value,'isoformat') else str(value)


def validate(folder):
    folder=Path(folder)
    c=duckdb.connect(str(folder/'warehouse.duckdb'),read_only=True)
    c.execute("SET memory_limit='1200MB'; SET threads=2; SET preserve_insertion_order=false")
    checks={}
    def check(name,sql,expected=0):
        value=c.execute(sql).fetchone()[0]
        checks[name]={'actual':value,'expected':expected,'pass':value==expected}
        print(f'{name}: {value} (expected {expected})',flush=True)
    tables=[r[0] for r in c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main' AND table_type='BASE TABLE' ORDER BY table_name").fetchall()]
    counts={t:c.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables}
    check('unlabelled_unbalanced_journals',"SELECT count(*) FROM (SELECT journal_id FROM gl_entry WHERE journal_id<>'TEST-UNBALANCED' GROUP BY journal_id HAVING sum(debit_amount)<>sum(credit_amount))")
    check('labelled_imbalance_vnd',"SELECT sum(debit_amount-credit_amount) FROM gl_entry WHERE journal_id='TEST-UNBALANCED'",1000)
    check('ar_reconciliation_vnd',"SELECT (SELECT sum(net_debit) FROM v_gl WHERE account_code='131')-(SELECT sum(total_amount) FROM ar_invoice)+(SELECT sum(amount) FROM ar_receipt)+(SELECT sum(total_amount) FROM ar_adjustment)")
    check('ap_reconciliation_vnd',"SELECT (SELECT -sum(net_debit) FROM v_gl WHERE account_code='331')-(SELECT sum(total_amount) FROM ap_bill)+(SELECT sum(amount) FROM ap_payment)")
    check('inventory_reconciliation_vnd',"SELECT (SELECT sum(net_debit) FROM v_gl WHERE account_code LIKE '156%')-(SELECT sum(value) FROM inventory_txn)")
    check('invoice_lines_net_vnd',"SELECT sum(abs(i.subtotal-l.net)) FROM ar_invoice i JOIN (SELECT invoice_id,sum(net_amount) net FROM ar_invoice_line GROUP BY invoice_id) l USING(invoice_id)")
    check('invoice_lines_vat_vnd',"SELECT sum(abs(i.vat_amount-l.vat)) FROM ar_invoice i JOIN (SELECT invoice_id,sum(vat_amount) vat FROM ar_invoice_line GROUP BY invoice_id) l USING(invoice_id)")
    check('invoice_total_vnd',"SELECT sum(abs(total_amount-subtotal-vat_amount)) FROM ar_invoice")
    for table,key,dimension,dkey in [
        ('gl_entry','journal_id','gl_journal','journal_id'),('gl_entry','account_key','dim_account','account_key'),
        ('gl_entry','partner_key','dim_partner','partner_key'),('gl_entry','item_key','dim_item','item_key'),
        ('gl_entry','employee_key','dim_employee','employee_key'),('gl_entry','branch_key','dim_branch','branch_key'),
        ('gl_entry','department_key','dim_department','department_key'),('gl_entry','period_key','dim_period','period_key'),
        ('ar_invoice','customer_code','dim_partner','partner_code'),('ar_invoice','salesperson_code','dim_employee','employee_code'),
        ('ar_invoice_line','invoice_id','ar_invoice','invoice_id'),('ar_invoice_line','item_code','dim_item','item_code'),
        ('ar_receipt','invoice_id','ar_invoice','invoice_id'),('ar_receipt','journal_id','gl_journal','journal_id'),
        ('ap_bill','vendor_code','dim_partner','partner_code'),('ap_payment','bill_id','ap_bill','bill_id'),
        ('inventory_txn','journal_id','gl_journal','journal_id'),('payroll','employee_code','dim_employee','employee_code')]:
        check(f'fk_{table}_{key}',f'SELECT count(*) FROM {table} t LEFT JOIN {dimension} d ON t.{key}=d.{dkey} WHERE t.{key} IS NOT NULL AND d.{dkey} IS NULL')
    check('overpaid_ar_invoices',"""SELECT count(*) FROM ar_invoice i LEFT JOIN (SELECT invoice_id,sum(amount) paid FROM ar_receipt GROUP BY invoice_id) r USING(invoice_id)
        LEFT JOIN (SELECT invoice_id,sum(total_amount) adj FROM ar_adjustment GROUP BY invoice_id) a USING(invoice_id)
        WHERE coalesce(r.paid,0)+coalesce(a.adj,0)>i.total_amount""")
    check('negative_daily_inventory_quantity',"""SELECT count(*) FROM (SELECT item_code,txn_date,
        sum(sum(quantity)) OVER(PARTITION BY item_code ORDER BY txn_date) qty FROM inventory_txn GROUP BY item_code,txn_date) WHERE qty<0""")
    check('negative_daily_inventory_value',"""SELECT count(*) FROM (SELECT item_code,txn_date,
        sum(sum(value)) OVER(PARTITION BY item_code ORDER BY txn_date) val FROM inventory_txn GROUP BY item_code,txn_date) WHERE val<0""")
    check('negative_daily_bank_balance',"""SELECT count(*) FROM (SELECT account_code,posting_date,
        sum(sum(net_debit)) OVER(PARTITION BY account_code ORDER BY posting_date) bal FROM v_gl WHERE account_code LIKE '112%' GROUP BY account_code,posting_date) WHERE bal<0""")
    check('closed_period_unclosed_pnl',"""SELECT count(*) FROM (SELECT year_month,account_code,sum(net_debit) bal FROM v_gl
        WHERE year_month BETWEEN '2023-01' AND '2026-08' AND regexp_matches(account_code,'^[5-8]') GROUP BY ALL HAVING bal<>0)""")
    check('monthly_accounting_equation',"""SELECT count(*) FROM (SELECT year_month,sum(sum(net_debit)) OVER(ORDER BY year_month) balance FROM v_gl GROUP BY year_month)
        WHERE balance<>CASE WHEN year_month>='2026-09' THEN 1000 ELSE 0 END""")
    def rows(sql):
        cur=c.execute(sql); cols=[d[0] for d in cur.description]
        return [dict(zip(cols,r)) for r in cur.fetchall()]
    yearly=rows("""SELECT year_no,sum(CASE WHEN account_code LIKE '511%' THEN -net_debit ELSE 0 END) revenue,
        sum(CASE WHEN account_code='632' THEN net_debit ELSE 0 END) cogs,
        -sum(CASE WHEN regexp_matches(account_code,'^[5-8]') THEN net_debit ELSE 0 END) net_profit
        FROM v_gl WHERE NOT is_closing AND year_no>=2023 GROUP BY year_no ORDER BY year_no""")
    for row in yearly:
        row['gross_margin_pct']=round((row['revenue']-row['cogs'])/row['revenue']*100,3)
        row['net_margin_pct']=round(row['net_profit']/row['revenue']*100,3)
    concentration=c.execute("SELECT sum(CASE WHEN customer_code<='C000010' THEN subtotal ELSE 0 END)/sum(subtotal)*100 FROM ar_invoice").fetchone()[0]
    summary={'checks':checks,'all_pass':all(x['pass'] for x in checks.values()),'counts':counts,'annual_financials':yearly,
      'top10_customer_revenue_pct':concentration,
      'branch_revenue':rows("SELECT year(issue_date) AS year,branch_code,sum(subtotal) revenue FROM ar_invoice GROUP BY ALL ORDER BY ALL"),
      'product_revenue':rows("SELECT year_no,product_line,sum(-net_debit) revenue FROM v_gl WHERE account_code LIKE '511%' AND NOT is_closing GROUP BY ALL ORDER BY ALL"),
      'closing_balances':rows("SELECT account_code,sum(net_debit) debit_balance FROM v_gl GROUP BY account_code ORDER BY account_code"),
      'debt_aging':rows("""SELECT CASE WHEN date_diff('day',i.due_date,DATE '2026-10-14')<=0 THEN 'not_due'
         WHEN date_diff('day',i.due_date,DATE '2026-10-14')<=30 THEN '1_30' WHEN date_diff('day',i.due_date,DATE '2026-10-14')<=90 THEN '31_90' ELSE 'over_90' END age,
         count(*) invoices,sum(i.total_amount-coalesce(r.paid,0)-coalesce(a.adjustment,0)) outstanding
         FROM ar_invoice i LEFT JOIN (SELECT invoice_id,sum(amount) paid FROM ar_receipt GROUP BY invoice_id) r USING(invoice_id)
         LEFT JOIN (SELECT invoice_id,sum(total_amount) adjustment FROM ar_adjustment GROUP BY invoice_id) a USING(invoice_id)
         WHERE i.total_amount>coalesce(r.paid,0)+coalesce(a.adjustment,0) GROUP BY age ORDER BY age"""),
      'ground_truth':[],'logical_hashes':{}}
    for sid,desc,expected,sql in c.execute('SELECT scenario_id,description,expected,validation_sql FROM ground_truth ORDER BY scenario_id').fetchall():
        actual=c.execute(sql).fetchone()[0]
        summary['ground_truth'].append(dict(id=sid,description=desc,expected=expected,actual=actual,passed=actual==expected))
    for table,key in [('ar_invoice','invoice_id'),('ar_receipt','receipt_id'),('ap_bill','bill_id'),('budget','year_no,month_no,branch_code,line_type,cost_category'),('gl_entry','entry_id')]:
        print(f'Hashing {table}...',flush=True)
        digest=hashlib.sha256()
        # SHA-256 of canonical JSON rows; fetch in bounded batches, independent of DB physical layout.
        cur=c.execute(f'SELECT to_json(t) FROM {table} t ORDER BY {key}')
        while batch:=cur.fetchmany(10000):
            for (text,) in batch: digest.update(text.encode('utf-8')+b'\n')
        summary['logical_hashes'][table]=digest.hexdigest()
    summary['all_pass']=summary['all_pass'] and all(g['passed'] for g in summary['ground_truth'])
    (folder/'validation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=serial),encoding='utf-8')
    c.close()
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);args=p.parse_args()
    result=validate(args.folder)
    print(json.dumps(result['annual_financials'],default=serial))
    sys.exit(0 if result['all_pass'] else 1)
