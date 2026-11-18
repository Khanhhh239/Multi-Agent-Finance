"""Independent accounting, foreign-key, persona, and cross-agent (Warehouse <-> A1 <-> A2 <-> A3) validation."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from decimal import Decimal
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[1]
for rel in ('', 'agent2', 'shared/finance_input/src'):
    cand = str((REPO / rel).resolve())
    if cand not in sys.path:
        sys.path.insert(0, cand)

UNITS_VI = {
    'không': 0, 'một': 1, 'mốt': 1, 'hai': 2, 'ba': 3, 'bốn': 4, 'tư': 4,
    'năm': 5, 'lăm': 5, 'nhăm': 5, 'sáu': 6, 'bảy': 7, 'bẩy': 7, 'tám': 8, 'chín': 9,
}
SCALES_VI = {'nghìn': 10**3, 'ngàn': 10**3, 'triệu': 10**6, 'tỷ': 10**9, 'tỉ': 10**9}


def serial(value):
    return str(value) if isinstance(value, Decimal) else value.isoformat() if hasattr(value, 'isoformat') else str(value)


def _words_to_int(text: str) -> int | None:
    t = re.sub(r'[.,;]', ' ', (text or '').lower())
    t = re.sub(r'\b(đồng|chẵn|việt nam|vnd)\b', ' ', t)
    total = hundreds = tens = 0
    digit = None
    for w in t.split():
        if w in UNITS_VI:
            digit = UNITS_VI[w]
        elif w == 'trăm':
            hundreds, digit = (digit or 0), None
        elif w == 'mười':
            tens, digit = 10, None
        elif w == 'mươi':
            tens, digit = (digit or 0) * 10, None
        elif w in ('linh', 'lẻ'):
            pass
        elif w in SCALES_VI:
            total += (hundreds * 100 + tens + (digit or 0)) * SCALES_VI[w]
            hundreds = tens = 0
            digit = None
        else:
            return None
    return total + hundreds * 100 + tens + (digit or 0)


def _validate_cross_agent_exports(c: duckdb.DuckDBPyConnection, folder: Path, record_check) -> dict:
    inputs = folder / 'inputs'
    reconciliations: dict = {}

    # ---------------- A1 <-> Warehouse ----------------
    if (inputs / 'a1').is_dir():
        inv_glob = (inputs / 'a1').as_posix() + '/*/01_invoices.csv'
        pay_glob = (inputs / 'a1').as_posix() + '/*/03_payments.csv'
        bnk_glob = (inputs / 'a1').as_posix() + '/*/02_bank.csv'
        stmt_csv = (inputs / 'a1/04_statements.csv').as_posix()
        out_csv = (inputs / 'a1/05_outflows.csv').as_posix()

        c.execute(f"CREATE OR REPLACE TEMP TABLE x_a1_inv AS SELECT * FROM read_csv_auto('{inv_glob}', all_varchar=true)")
        c.execute(f"CREATE OR REPLACE TEMP TABLE x_a1_pay AS SELECT * FROM read_csv_auto('{pay_glob}', all_varchar=true)")
        c.execute(f"CREATE OR REPLACE TEMP TABLE x_a1_bnk AS SELECT * FROM read_csv_auto('{bnk_glob}', all_varchar=true)")
        c.execute(f"CREATE OR REPLACE TEMP TABLE x_a1_stmt AS SELECT * FROM read_csv_auto('{stmt_csv}', all_varchar=true)")
        c.execute(f"CREATE OR REPLACE TEMP TABLE x_a1_out AS SELECT * FROM read_csv_auto('{out_csv}', all_varchar=true)")

        record_check(
            'cross_a1_invoice_reconciliation_vnd',
            """SELECT coalesce(sum(abs(x.amount::BIGINT - (w.total_amount - coalesce(adj.tot, 0))::BIGINT)), 0)::BIGINT
               FROM x_a1_inv x
               LEFT JOIN ar_invoice w ON ('INV-' || w.invoice_id) = x.invoice_id
               LEFT JOIN (SELECT invoice_id, sum(total_amount) tot FROM ar_adjustment GROUP BY invoice_id) adj ON adj.invoice_id = w.invoice_id""",
            0,
        )
        record_check(
            'cross_a1_missing_invoices',
            "SELECT count(*) FROM x_a1_inv x LEFT JOIN ar_invoice w ON ('INV-' || w.invoice_id) = x.invoice_id WHERE w.invoice_id IS NULL",
            0,
        )
        record_check(
            'cross_a1_longitudinal_months_ok',
            "SELECT CASE WHEN count(DISTINCT substr(issue_date, 1, 7)) >= 24 AND count(*) BETWEEN 1 AND 50000 THEN 1 ELSE 0 END FROM x_a1_inv",
            1,
        )
        record_check(
            'cross_a1_payment_reconciliation_vnd',
            """SELECT coalesce(sum(abs(x.amount::BIGINT - r.amount::BIGINT)), 0)::BIGINT
               FROM x_a1_pay x
               LEFT JOIN ar_receipt r ON ('REC-' || r.receipt_id) = x.payment_id""",
            0,
        )
        record_check(
            'cross_a1_unmatched_payment_bank_refs',
            """SELECT count(*)
               FROM x_a1_pay p
               LEFT JOIN x_a1_bnk b ON b.bank_id = p.bank_id
               WHERE p.bank_id <> '' AND b.bank_id IS NULL""",
            0,
        )
        record_check(
            'cross_a1_statement_closing_reconciliation_vnd',
            """SELECT (SELECT sum(closing_balance::BIGINT)
                       FROM (SELECT account, arg_max(closing_balance, end_date) closing_balance FROM x_a1_stmt GROUP BY account))
                      - (SELECT sum(net_debit)::BIGINT FROM v_gl WHERE account_code LIKE '112%')""",
            0,
        )
        record_check(
            'cross_a1_operating_components_ok',
            """SELECT CASE WHEN count(DISTINCT CASE WHEN component = 'cash_sale' THEN strftime(date::DATE, '%G-%V') END) >= 104
                            AND count(DISTINCT CASE WHEN component = 'variable_cost' THEN strftime(date::DATE, '%G-%V') END) >= 104
                           THEN 1 ELSE 0 END
               FROM x_a1_bnk""",
            1,
        )
        record_check(
            'cross_a1_outflows_ap_reconciliation_vnd',
            """SELECT coalesce((SELECT sum(amount::BIGINT) FROM x_a1_out WHERE category = 'supplier'), 0)
                      - coalesce((SELECT sum(b.total_amount - coalesce(p.paid, 0))::BIGINT
                                  FROM ap_bill b
                                  LEFT JOIN (SELECT bill_id, sum(amount) paid FROM ap_payment GROUP BY bill_id) p USING(bill_id)
                                  WHERE b.total_amount > coalesce(p.paid, 0)), 0)""",
            0,
        )
        reconciliations['a1'] = {
            'invoices': c.execute('SELECT count(*) FROM x_a1_inv').fetchone()[0],
            'payments': c.execute('SELECT count(*) FROM x_a1_pay').fetchone()[0],
            'bank_rows': c.execute('SELECT count(*) FROM x_a1_bnk').fetchone()[0],
            'statements': c.execute('SELECT count(*) FROM x_a1_stmt').fetchone()[0],
            'outflows': c.execute('SELECT count(*) FROM x_a1_out').fetchone()[0],
            'longitudinal_months': c.execute('SELECT count(DISTINCT substr(issue_date, 1, 7)) FROM x_a1_inv').fetchone()[0],
        }

    # ---------------- A2 <-> Warehouse ----------------
    if (inputs / 'a2/transactions_full.csv').is_file():
        tx_csv = (inputs / 'a2/transactions_full.csv').as_posix()
        c.execute(f"CREATE OR REPLACE TEMP TABLE x_a2_tx AS SELECT * FROM read_csv_auto('{tx_csv}', all_varchar=true)")
        record_check(
            'cross_a2_csv_gl_reconciliation_vnd',
            """SELECT coalesce(sum(abs(x.amount_vnd::BIGINT - g.deb)), 0)::BIGINT
               FROM x_a2_tx x
               LEFT JOIN (SELECT journal_id, sum(debit_amount)::BIGINT deb FROM v_gl GROUP BY journal_id) g
                 ON g.journal_id = x.transaction_id""",
            0,
        )
        record_check(
            'cross_a2_fraud_signals_preserved',
            """SELECT CASE WHEN sum(CASE WHEN payment_channel = 'cash' THEN 1 ELSE 0 END) > 0
                            AND sum(CASE WHEN creator_id = approver_id THEN 1 ELSE 0 END) > 0
                            AND sum(CASE WHEN tax_deductible::INT = 0 THEN 1 ELSE 0 END) > 0
                            AND sum(CASE WHEN vendor_id <> '' AND coalesce(counterparty_tax_code, '') = '' THEN 1 ELSE 0 END) > 0
                            AND sum(CASE WHEN transaction_id = 'DUP-PAY' THEN 1 ELSE 0 END) = 1
                           THEN 1 ELSE 0 END
               FROM x_a2_tx""",
            1,
        )

        bundle_file = inputs / 'a2/canonical_bundle.json'
        bundle_errors = 999
        bundle_tx_diff = 999
        bundle_tx_count = 0
        if bundle_file.is_file():
            from finance_input import AccessScope
            from sme_fraud.imports import validate_input

            bundle = json.loads(bundle_file.read_text(encoding='utf-8'))
            bundle_tx_count = len(bundle.get('transactions', []))
            scope = AccessScope(
                tenant_id=bundle.get('tenant_id', 'demo'),
                company_ids=frozenset({'MPX10'}),
                actor_id='validator',
                permissions=frozenset({'data.import', 'evidence.verify'}),
            )
            rep = validate_input(bundle, scope)
            bundle_errors = len(rep.get('errors', [])) if rep.get('status') == 'rejected' else 0
            gl_debits = dict(
                c.execute(
                    'SELECT journal_id, sum(debit_amount)::BIGINT FROM v_gl WHERE journal_id IN (SELECT transaction_id FROM x_a2_tx) GROUP BY journal_id'
                ).fetchall()
            )
            bundle_tx_diff = sum(abs(int(t['amount_vnd']) - int(gl_debits.get(t['record_id'], -1))) for t in bundle.get('transactions', []))
        record_check('cross_a2_canonical_bundle_errors', f'SELECT {int(bundle_errors)}', 0)
        record_check('cross_a2_canonical_bundle_gl_diff_vnd', f'SELECT {int(bundle_tx_diff)}', 0)
        reconciliations['a2'] = {
            'csv_transactions': c.execute('SELECT count(*) FROM x_a2_tx').fetchone()[0],
            'canonical_json_transactions': bundle_tx_count,
            'cash_transactions': c.execute("SELECT count(*) FROM x_a2_tx WHERE payment_channel = 'cash'").fetchone()[0],
            'self_approved_transactions': c.execute('SELECT count(*) FROM x_a2_tx WHERE creator_id = approver_id').fetchone()[0],
            'mgmt_only_nondeductible_transactions': c.execute('SELECT count(*) FROM x_a2_tx WHERE tax_deductible::INT = 0').fetchone()[0],
        }

    # ---------------- A3 <-> Warehouse ----------------
    if (inputs / 'a3').is_dir():
        ar_totals = dict(c.execute('SELECT invoice_id, total_amount::BIGINT FROM ar_invoice').fetchall())
        ap_totals = dict(c.execute('SELECT bill_id, total_amount::BIGINT FROM ap_bill').fetchall())

        xml_errors = 0
        raw_code_descriptions = 0
        welfare_items_found = 0
        sales_xml_count = 0
        purchase_xml_count = 0
        purchase_keys: set[tuple[str, str]] = set()
        purchase_by_seller_day: dict[tuple[str, str], list[int]] = {}

        for zpath in sorted((inputs / 'a3').rglob('*.zip')):
            role = zpath.stem.split('_')[0]
            with zipfile.ZipFile(zpath) as zf:
                for member in zf.namelist():
                    if not member.endswith('.xml'):
                        continue
                    doc_id = int(member.split('_')[1].split('.')[0])
                    root = ET.fromstring(zf.read(member))
                    dl = root.find('DLHDon')
                    if dl is None:
                        xml_errors += 1
                        continue
                    seller_mst = (dl.findtext('NDHDon/NBan/MST') or '').strip()
                    issue_day = (dl.findtext('TTChung/NLap') or '').strip()
                    inv_no = (dl.findtext('TTChung/SHDon') or '').strip()
                    net_tot = int(dl.findtext('NDHDon/TToan/TgTCThue') or -1)
                    vat_tot = int(dl.findtext('NDHDon/TToan/TgTThue') or -1)
                    gross_tot = int(dl.findtext('NDHDon/TToan/TgTTTBSo') or -1)
                    words_txt = (dl.findtext('NDHDon/TToan/TgTTTBChu') or '').strip()
                    parsed_words = _words_to_int(words_txt)

                    if net_tot + vat_tot != gross_tot or parsed_words != gross_tot:
                        xml_errors += 1
                    expected_wh = ar_totals.get(doc_id) if role == 'sales' else ap_totals.get(doc_id)
                    if expected_wh != gross_tot:
                        xml_errors += 1

                    line_sum = 0
                    for hh in dl.findall('NDHDon/DSHHDVu/HHDVu'):
                        desc = (hh.findtext('THHDVu') or '').strip()
                        qty_s = (hh.findtext('SLuong') or '').strip()
                        price_s = (hh.findtext('DGia') or '').strip()
                        val_s = (hh.findtext('ThTien') or '').strip()
                        if re.fullmatch(r'I\d{5}', desc):
                            raw_code_descriptions += 1
                        if any(kw in desc.lower() for kw in ('golf', 'spa', 'tiếp khách', 'phúc lợi')):
                            welfare_items_found += 1
                        if '.' in price_s or not qty_s.isdigit() or not price_s.lstrip('-').isdigit() or not val_s.lstrip('-').isdigit():
                            xml_errors += 1
                        else:
                            q_i, p_i, v_i = int(qty_s), int(price_s), int(val_s)
                            if q_i * p_i != v_i:
                                xml_errors += 1
                            line_sum += v_i
                    if line_sum != net_tot:
                        xml_errors += 1

                    if role == 'sales':
                        sales_xml_count += 1
                    else:
                        purchase_xml_count += 1
                        purchase_keys.add((seller_mst, inv_no))
                        purchase_by_seller_day.setdefault((seller_mst, issue_day), []).append(gross_tot)

        # Reconcile A3 bank.csv rows with warehouse 112% ledger
        bank_csvs = sorted((inputs / 'a3').rglob('bank.csv'))
        a3_bank_diff = 0
        a3_out_bank_count = 0
        wh_bank = dict(
            c.execute(
                "SELECT journal_id || ':' || account_code, sum(net_debit)::BIGINT FROM v_gl WHERE account_code LIKE '112%' GROUP BY 1"
            ).fetchall()
        )
        for bpath in bank_csvs:
            with bpath.open(encoding='utf-8-sig', newline='') as f:
                for row in csv.DictReader(f):
                    debit = int(row['Ghi Nợ'] or 0)
                    credit = int(row['Ghi Có'] or 0)
                    net = credit - debit
                    if debit > 0:
                        a3_out_bank_count += 1
                    wh_net = wh_bank.get(row['Mã giao dịch'])
                    if wh_net is None or wh_net != net:
                        a3_bank_diff += abs(net - (wh_net or 0)) + (1 if wh_net is None else 0)

        same_day_split_sellers = sum(
            1 for (_s, d), amts in purchase_by_seller_day.items() if d >= '2025-07-01' and len(amts) >= 2 and sum(amts) >= 5_000_000
        )

        record_check('cross_a3_xml_integrity_and_reconciliation_errors', f'SELECT {xml_errors + raw_code_descriptions}', 0)
        record_check('cross_a3_bank_reconciliation_vnd', f'SELECT {a3_bank_diff}', 0)
        record_check(
            'cross_a3_paid_unpaid_split_welfare_mix_ok',
            f'SELECT {1 if (a3_out_bank_count > 0 and purchase_xml_count > a3_out_bank_count and same_day_split_sellers > 0 and welfare_items_found > 0) else 0}',
            1,
        )
        reconciliations['a3'] = {
            'sales_xml_invoices': sales_xml_count,
            'purchase_xml_invoices': purchase_xml_count,
            'outgoing_supplier_bank_payments': a3_out_bank_count,
            'unpaid_or_cash_purchase_invoices': purchase_xml_count - a3_out_bank_count,
            'same_day_split_seller_groups': same_day_split_sellers,
            'welfare_entertainment_test_lines': welfare_items_found,
        }

    return reconciliations


def validate(folder: str | Path) -> dict:
    folder = Path(folder)
    c = duckdb.connect(str(folder / 'warehouse.duckdb'), read_only=True)
    c.execute("SET memory_limit='1200MB'; SET threads=2; SET preserve_insertion_order=false")
    checks = {}

    def check(name: str, sql: str, expected=0):
        value = c.execute(sql).fetchone()[0]
        checks[name] = {'actual': value, 'expected': expected, 'pass': value == expected}
        print(f'{name}: {value} (expected {expected})', flush=True)

    tables = [
        r[0]
        for r in c.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main' AND table_type='BASE TABLE' ORDER BY table_name"
        ).fetchall()
    ]
    counts = {t: c.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables}

    check(
        'unlabelled_unbalanced_journals',
        "SELECT count(*) FROM (SELECT journal_id FROM gl_entry WHERE journal_id <> 'TEST-UNBALANCED' GROUP BY journal_id HAVING sum(debit_amount) <> sum(credit_amount))",
    )
    check('labelled_imbalance_vnd', "SELECT sum(debit_amount - credit_amount) FROM gl_entry WHERE journal_id = 'TEST-UNBALANCED'", 1000)
    check(
        'ar_reconciliation_vnd',
        "SELECT (SELECT sum(net_debit) FROM v_gl WHERE account_code = '131') - (SELECT sum(total_amount) FROM ar_invoice) + (SELECT sum(amount) FROM ar_receipt) + (SELECT coalesce(sum(total_amount), 0) FROM ar_adjustment)",
    )
    check(
        'ap_reconciliation_vnd',
        "SELECT (SELECT -sum(net_debit) FROM v_gl WHERE account_code = '331') - (SELECT sum(total_amount) FROM ap_bill) + (SELECT sum(amount) FROM ap_payment)",
    )
    check(
        'inventory_reconciliation_vnd',
        "SELECT (SELECT sum(net_debit) FROM v_gl WHERE account_code LIKE '156%') - (SELECT sum(value) FROM inventory_txn)",
    )
    check(
        'invoice_lines_net_vnd',
        'SELECT sum(abs(i.subtotal - l.net)) FROM ar_invoice i JOIN (SELECT invoice_id, sum(net_amount) net FROM ar_invoice_line GROUP BY invoice_id) l USING(invoice_id)',
    )
    check(
        'invoice_lines_vat_vnd',
        'SELECT sum(abs(i.vat_amount - l.vat)) FROM ar_invoice i JOIN (SELECT invoice_id, sum(vat_amount) vat FROM ar_invoice_line GROUP BY invoice_id) l USING(invoice_id)',
    )
    check('invoice_total_vnd', 'SELECT sum(abs(total_amount - subtotal - vat_amount)) FROM ar_invoice')

    if 'ap_bill_line' in counts:
        check(
            'ap_bill_lines_net_vnd',
            'SELECT coalesce(sum(abs(b.subtotal - l.net)), 0)::BIGINT FROM ap_bill b JOIN (SELECT bill_id, sum(net_amount) net FROM ap_bill_line GROUP BY bill_id) l USING(bill_id)',
        )
        check(
            'ap_bill_line_exact_integer_arith',
            'SELECT count(*) FROM ap_bill_line WHERE quantity * unit_price <> net_amount',
        )

    for table, key, dimension, dkey in [
        ('gl_entry', 'journal_id', 'gl_journal', 'journal_id'),
        ('gl_entry', 'account_key', 'dim_account', 'account_key'),
        ('gl_entry', 'partner_key', 'dim_partner', 'partner_key'),
        ('gl_entry', 'item_key', 'dim_item', 'item_key'),
        ('gl_entry', 'employee_key', 'dim_employee', 'employee_key'),
        ('gl_entry', 'branch_key', 'dim_branch', 'branch_key'),
        ('gl_entry', 'department_key', 'dim_department', 'department_key'),
        ('gl_entry', 'period_key', 'dim_period', 'period_key'),
        ('ar_invoice', 'customer_code', 'dim_partner', 'partner_code'),
        ('ar_invoice', 'salesperson_code', 'dim_employee', 'employee_code'),
        ('ar_invoice_line', 'invoice_id', 'ar_invoice', 'invoice_id'),
        ('ar_invoice_line', 'item_code', 'dim_item', 'item_code'),
        ('ar_receipt', 'invoice_id', 'ar_invoice', 'invoice_id'),
        ('ar_receipt', 'journal_id', 'gl_journal', 'journal_id'),
        ('ap_bill', 'vendor_code', 'dim_partner', 'partner_code'),
        ('ap_payment', 'bill_id', 'ap_bill', 'bill_id'),
        ('inventory_txn', 'journal_id', 'gl_journal', 'journal_id'),
        ('payroll', 'employee_code', 'dim_employee', 'employee_code'),
    ]:
        check(
            f'fk_{table}_{key}',
            f'SELECT count(*) FROM {table} t LEFT JOIN {dimension} d ON t.{key} = d.{dkey} WHERE t.{key} IS NOT NULL AND d.{dkey} IS NULL',
        )

    check(
        'overpaid_ar_invoices',
        """SELECT count(*)
           FROM ar_invoice i
           LEFT JOIN (SELECT invoice_id, sum(amount) paid FROM ar_receipt GROUP BY invoice_id) r USING(invoice_id)
           LEFT JOIN (SELECT invoice_id, sum(total_amount) adj FROM ar_adjustment GROUP BY invoice_id) a USING(invoice_id)
           WHERE coalesce(r.paid, 0) + coalesce(a.adj, 0) > i.total_amount""",
    )
    check(
        'negative_daily_inventory_quantity',
        """SELECT count(*) FROM (
               SELECT item_code, txn_date, sum(sum(quantity)) OVER(PARTITION BY item_code ORDER BY txn_date) qty
               FROM inventory_txn GROUP BY item_code, txn_date
           ) WHERE qty < 0""",
    )
    check(
        'negative_daily_inventory_value',
        """SELECT count(*) FROM (
               SELECT item_code, txn_date, sum(sum(value)) OVER(PARTITION BY item_code ORDER BY txn_date) val
               FROM inventory_txn GROUP BY item_code, txn_date
           ) WHERE val < 0""",
    )
    check(
        'negative_daily_bank_balance',
        """SELECT count(*) FROM (
               SELECT account_code, posting_date, sum(sum(net_debit)) OVER(PARTITION BY account_code ORDER BY posting_date) bal
               FROM v_gl WHERE account_code LIKE '112%' GROUP BY account_code, posting_date
           ) WHERE bal < 0""",
    )
    check(
        'negative_daily_cash_balance',
        """SELECT count(*) FROM (
               SELECT account_code, posting_date, sum(sum(net_debit)) OVER(PARTITION BY account_code ORDER BY posting_date) bal
               FROM v_gl WHERE account_code LIKE '111%' GROUP BY account_code, posting_date
           ) WHERE bal < 0""",
    )
    check(
        'closed_period_unclosed_pnl',
        """SELECT count(*) FROM (
               SELECT year_month, account_code, sum(net_debit) bal
               FROM v_gl
               WHERE year_month BETWEEN '2023-01' AND '2026-08' AND regexp_matches(account_code, '^[5-8]')
               GROUP BY ALL HAVING bal <> 0
           )""",
    )
    check(
        'monthly_accounting_equation',
        """SELECT count(*) FROM (
               SELECT year_month, sum(sum(net_debit)) OVER(ORDER BY year_month) balance
               FROM v_gl GROUP BY year_month
           ) WHERE balance <> CASE WHEN year_month >= '2026-09' THEN 1000 ELSE 0 END""",
    )

    if 'customer_persona' in counts:
        check(
            'customer_persona_separation_ok',
            """WITH settled AS (
                   SELECT i.invoice_id,
                          cp.persona,
                          date_diff('day', i.due_date, max(r.receipt_date)) delay_days
                   FROM ar_invoice i
                   JOIN customer_persona cp USING(customer_code)
                   JOIN ar_receipt r USING(invoice_id)
                   GROUP BY i.invoice_id, cp.persona, i.due_date, i.total_amount
                   HAVING sum(r.amount) = i.total_amount
               ),
               med AS (
                   SELECT persona, median(delay_days) m_delay
                   FROM settled
                   GROUP BY persona
               )
               SELECT CASE WHEN (SELECT m_delay FROM med WHERE persona = 'PROMPT') < 0
                            AND (SELECT m_delay FROM med WHERE persona = 'STANDARD_CORP') BETWEEN 0 AND 10
                            AND (SELECT m_delay FROM med WHERE persona = 'CHRONIC_LATE') >= 20
                           THEN 1 ELSE 0 END""",
            1,
        )

    def rows(sql: str):
        cur = c.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    yearly = rows(
        """SELECT year_no,
                  sum(CASE WHEN account_code LIKE '511%' THEN -net_debit ELSE 0 END) revenue,
                  sum(CASE WHEN account_code = '632' THEN net_debit ELSE 0 END) cogs,
                  -sum(CASE WHEN regexp_matches(account_code, '^[5-8]') THEN net_debit ELSE 0 END) net_profit
           FROM v_gl WHERE NOT is_closing AND year_no >= 2023
           GROUP BY year_no ORDER BY year_no"""
    )
    for row in yearly:
        row['gross_margin_pct'] = round((row['revenue'] - row['cogs']) / row['revenue'] * 100, 3)
        row['net_margin_pct'] = round(row['net_profit'] / row['revenue'] * 100, 3)

    concentration = c.execute(
        "SELECT sum(CASE WHEN customer_code <= 'C000010' THEN subtotal ELSE 0 END) / sum(subtotal) * 100 FROM ar_invoice"
    ).fetchone()[0]

    cross_agent = _validate_cross_agent_exports(c, folder, check) if (folder / 'inputs').is_dir() else {}

    summary = {
        'checks': checks,
        'all_pass': all(x['pass'] for x in checks.values()),
        'counts': counts,
        'cross_agent_reconciliation': cross_agent,
        'annual_financials': yearly,
        'top10_customer_revenue_pct': concentration,
        'branch_revenue': rows('SELECT year(issue_date) AS year, branch_code, sum(subtotal) revenue FROM ar_invoice GROUP BY ALL ORDER BY ALL'),
        'product_revenue': rows("SELECT year_no, product_line, sum(-net_debit) revenue FROM v_gl WHERE account_code LIKE '511%' AND NOT is_closing GROUP BY ALL ORDER BY ALL"),
        'closing_balances': rows('SELECT account_code, sum(net_debit) debit_balance FROM v_gl GROUP BY account_code ORDER BY account_code'),
        'debt_aging': rows(
            """SELECT CASE WHEN date_diff('day', i.due_date, DATE '2026-10-14') <= 0 THEN 'not_due'
                           WHEN date_diff('day', i.due_date, DATE '2026-10-14') <= 30 THEN '1_30'
                           WHEN date_diff('day', i.due_date, DATE '2026-10-14') <= 90 THEN '31_90'
                           ELSE 'over_90' END age,
                      count(*) invoices,
                      sum(i.total_amount - coalesce(r.paid, 0) - coalesce(a.adjustment, 0)) outstanding
               FROM ar_invoice i
               LEFT JOIN (SELECT invoice_id, sum(amount) paid FROM ar_receipt GROUP BY invoice_id) r USING(invoice_id)
               LEFT JOIN (SELECT invoice_id, sum(total_amount) adjustment FROM ar_adjustment GROUP BY invoice_id) a USING(invoice_id)
               WHERE i.total_amount > coalesce(r.paid, 0) + coalesce(a.adjustment, 0)
               GROUP BY age ORDER BY age"""
        ),
        'ground_truth': [],
        'logical_hashes': {},
    }

    for sid, desc, expected, sql in c.execute(
        'SELECT scenario_id, description, expected, validation_sql FROM ground_truth ORDER BY scenario_id'
    ).fetchall():
        actual = c.execute(sql).fetchone()[0]
        summary['ground_truth'].append(dict(id=sid, description=desc, expected=expected, actual=actual, passed=actual == expected))

    for table, key in [
        ('ar_invoice', 'invoice_id'),
        ('ar_receipt', 'receipt_id'),
        ('ap_bill', 'bill_id'),
        ('budget', 'year_no,month_no,branch_code,line_type,cost_category'),
        ('gl_entry', 'entry_id'),
    ]:
        print(f'Hashing {table}...', flush=True)
        digest = hashlib.sha256()
        cur = c.execute(f'SELECT to_json(t) FROM {table} t ORDER BY {key}')
        while batch := cur.fetchmany(10000):
            for (text,) in batch:
                digest.update(text.encode('utf-8') + b'\n')
        summary['logical_hashes'][table] = digest.hexdigest()

    summary['all_pass'] = summary['all_pass'] and all(g['passed'] for g in summary['ground_truth'])
    (folder / 'validation.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=serial), encoding='utf-8')
    c.close()
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder', type=Path)
    args = p.parse_args()
    result = validate(args.folder)
    print(json.dumps(result['annual_financials'], default=serial))
    sys.exit(0 if result['all_pass'] else 1)
