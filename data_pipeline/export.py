"""Stream exact common-source projections. Never changes active agent data."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import duckdb

DIGITS_VI = ('không', 'một', 'hai', 'ba', 'bốn', 'năm', 'sáu', 'bảy', 'tám', 'chín')
SCALES_VI = ((10**9, 'tỷ'), (10**6, 'triệu'), (10**3, 'nghìn'), (1, ''))
DEFAULT_ADDRESS = 'Số 195 Điện Biên Phủ, Quận Bình Thạnh, TP. Hồ Chí Minh (Mô phỏng)'


def q(s) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def a2_account(column: str) -> str:
    # Explicit chart mapping; retain detailed source accounts in journal_lines.
    return (
        '(CASE '
        + ' '.join(f"WHEN {column} LIKE '{prefix}%' THEN '{prefix}'" for prefix in ('112', '111', '511', '214', '334', '3331'))
        + f' ELSE {column} END)'
    )


def _read_triple_vi(val: int, full_hundreds: bool) -> list[str]:
    h, t, u = val // 100, (val // 10) % 10, val % 10
    words: list[str] = []
    if full_hundreds or h > 0:
        words.extend((DIGITS_VI[h], 'trăm'))
    if t == 0:
        if u > 0:
            if full_hundreds or h > 0:
                words.append('linh')
            words.append(DIGITS_VI[u])
    elif t == 1:
        words.append('mười')
        if u == 5:
            words.append('lăm')
        elif u > 0:
            words.append(DIGITS_VI[u])
    else:
        words.extend((DIGITS_VI[t], 'mươi'))
        if u == 1:
            words.append('mốt')
        elif u == 5:
            words.append('lăm')
        elif u > 0:
            words.append(DIGITS_VI[u])
    return words


def vnd_to_words(amount: int) -> str:
    """Convert non-negative integer VND into standard Vietnamese words compatible with QĐ 1450 / Agent 3."""
    n = int(amount)
    if n < 0:
        return 'Âm ' + vnd_to_words(-n).lower()
    if n == 0:
        return 'Không đồng chẵn'
    tokens: list[str] = []
    started = False
    rem = n
    # Handle >= 10**12 gracefully if ever needed while keeping < 10**12 exact for single-scale parsers
    if rem >= 10**12:
        trillions = rem // 10**9
        rem = rem % 10**9
        tokens.extend(_read_triple_vi(trillions, False))
        tokens.append('tỷ')
        started = True
    for scale_val, scale_word in SCALES_VI:
        if scale_val == 10**9 and n >= 10**12:
            continue
        group = rem // scale_val
        rem = rem % scale_val
        if group == 0:
            continue
        tokens.extend(_read_triple_vi(group, started))
        if scale_word:
            tokens.append(scale_word)
        started = True
    phrase = ' '.join(tokens).strip()
    return phrase[0].upper() + phrase[1:] + ' đồng chẵn'


def _canonical_json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _quantize_xml_lines(raw_lines: list[tuple[str, str, int, int]]) -> list[tuple[str, str, int, int, int]]:
    """Ensure every XML line has exact integer VND unit_price with SLuong * DGia == ThTien."""
    clean: list[tuple[str, str, int, int, int]] = []
    for desc, unit, qty, net in raw_lines:
        qty_i = max(1, int(qty))
        net_i = int(net)
        unit_s = str(unit or 'đơn vị')
        desc_s = str(desc or 'Hàng hóa, dịch vụ')
        if net_i % qty_i == 0:
            clean.append((desc_s, unit_s, qty_i, net_i // qty_i, net_i))
        elif qty_i == 1:
            clean.append((desc_s, unit_s, 1, net_i, net_i))
        else:
            base_p = net_i // qty_i
            first_net = (qty_i - 1) * base_p
            rem_net = net_i - first_net
            clean.append((desc_s, unit_s, qty_i - 1, base_p, first_net))
            clean.append((f'{desc_s} (lẻ điều chỉnh tròn đồng)', unit_s, 1, rem_net, rem_net))
    return clean


class Export:
    def __init__(self, folder, tenant_id: str = 'demo'):
        self.folder = Path(folder).resolve()
        self.tenant_id = tenant_id
        self.root = self.folder / 'inputs'
        self.root.mkdir(exist_ok=True)
        self.db = duckdb.connect(str(self.folder / 'warehouse.duckdb'), read_only=True)
        self.db.execute("SET memory_limit='1200MB'; SET threads=2; SET preserve_insertion_order=false")
        self.info = dict(self.db.execute('SELECT * FROM company_info').fetchall())
        self.cutoff = self.info.get('as_of_date', '2026-10-14')
        self.seed = int(self.info.get('seed', '20261108'))
        self.address = self.info.get('registered_address', DEFAULT_ADDRESS)
        self.tables = {
            r[0]
            for r in self.db.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
            ).fetchall()
        }
        self.manifest = []

    def csv(self, path: Path, sql: str):
        dest = self.root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.db.execute(f"COPY ({sql}) TO {q(dest)} (HEADER, DELIMITER ',')")
        print(path.as_posix(), flush=True)

    def prepare(self):
        # One bank movement per journal/account, including opening balance movements explicitly.
        self.db.execute(f"""CREATE OR REPLACE TEMP VIEW bank AS
            SELECT g.journal_id || ':' || g.account_code bank_id,
                   g.journal_id,
                   g.posting_date date,
                   g.account_code account,
                   sum(g.net_debit)::BIGINT net,
                   least(max(g.created_at)::DATE, {q(self.cutoff)}::DATE) known_at,
                   min(g.partner_code) partner_code,
                   min(p.partner_name) partner_name,
                   min(g.description) description
            FROM v_gl g
            LEFT JOIN dim_partner p USING(partner_code)
            WHERE g.account_code LIKE '112%'
            GROUP BY g.journal_id, g.posting_date, g.account_code
            HAVING sum(g.net_debit) <> 0""")
        self.db.execute(f"""CREATE OR REPLACE TEMP VIEW monthly_bank AS
            SELECT account,
                   date_trunc('month', date)::DATE start_date,
                   least(last_day(date), {q(self.cutoff)}::DATE) end_date,
                   sum(net)::BIGINT movement,
                   greatest(least(max(last_day(date)), {q(self.cutoff)}::DATE), max(known_at)) stmt_known_at
            FROM bank
            GROUP BY 1, 2, 3""")

    def a1(self):
        """Export Agent 1 longitudinal slice (full multi-year customer trajectories <= 50,000 invoices)."""
        # Deterministic stratified customer selection across ALL 46 months (2023-01..2026-10):
        # Retain top-10 enterprise accounts + pseudo-random cohort across all payment personas so every selected
        # customer carries its complete multi-year history while total invoice count stays <= 50,000.
        self.db.execute(f"""CREATE OR REPLACE TEMP TABLE a1_eligible_customers AS
            SELECT customer_code
            FROM (
                SELECT customer_code,
                       sum(inv_cnt) OVER (
                           ORDER BY CASE WHEN customer_code <= 'C000010' THEN 0 ELSE 1 END,
                                    hash(customer_code, {self.seed}, 91),
                                    customer_code
                           ROWS UNBOUNDED PRECEDING
                       ) cum_cnt
                FROM (
                    SELECT i.customer_code, count(*)::BIGINT inv_cnt
                    FROM warehouse.main.ar_invoice i
                    WHERE i.payment_terms_days > 0
                      AND NOT EXISTS (SELECT 1 FROM warehouse.main.ar_adjustment a WHERE a.invoice_id = i.invoice_id)
                      AND NOT EXISTS (SELECT 1 FROM warehouse.main.ar_receipt r WHERE r.invoice_id = i.invoice_id AND r.receipt_date < i.issue_date)
                    GROUP BY i.customer_code
                )
            )
            WHERE cum_cnt <= 50000""")

        self.db.execute("""CREATE OR REPLACE TEMP TABLE ar_invoice AS
            SELECT i.*
            FROM warehouse.main.ar_invoice i
            JOIN a1_eligible_customers c USING(customer_code)
            WHERE NOT EXISTS (SELECT 1 FROM warehouse.main.ar_adjustment a WHERE a.invoice_id = i.invoice_id)
              AND NOT EXISTS (SELECT 1 FROM warehouse.main.ar_receipt r WHERE r.invoice_id = i.invoice_id AND r.receipt_date < i.issue_date)""")
        self.db.execute('CREATE OR REPLACE TEMP TABLE ar_adjustment AS SELECT a.* FROM warehouse.main.ar_adjustment a JOIN a1_eligible_customers USING(customer_code)')
        self.db.execute('CREATE OR REPLACE TEMP TABLE ar_receipt AS SELECT r.* FROM warehouse.main.ar_receipt r JOIN ar_invoice i USING(invoice_id)')

        # Classify receipt journals so 02_bank.csv maps retail cash sales to 'cash_sale',
        # sliced AR receipts to 'ar' ('other' component), and non-sliced customer receipts to 'other_external' (NON_AR).
        self.db.execute('CREATE OR REPLACE TEMP TABLE a1_rcpt_journals AS SELECT DISTINCT journal_id, customer_code FROM ar_receipt')
        self.db.execute("""CREATE OR REPLACE TEMP TABLE retail_rcpt_journals AS
            SELECT DISTINCT r.journal_id
            FROM warehouse.main.ar_receipt r
            JOIN warehouse.main.ar_invoice i USING(invoice_id)
            WHERE i.payment_terms_days = 0
              AND r.journal_id NOT IN (SELECT journal_id FROM a1_rcpt_journals)""")
        self.db.execute("""CREATE OR REPLACE TEMP TABLE other_ar_rcpt_journals AS
            SELECT DISTINCT r.journal_id
            FROM warehouse.main.ar_receipt r
            WHERE r.journal_id NOT IN (SELECT journal_id FROM a1_rcpt_journals)
              AND r.journal_id NOT IN (SELECT journal_id FROM retail_rcpt_journals)""")

        bank_start = self.db.execute("SELECT date_trunc('month', min(issue_date))::DATE FROM warehouse.main.ar_invoice").fetchone()[0]
        months = [r[0] for r in self.db.execute("SELECT DISTINCT strftime(issue_date, '%Y-%m') FROM ar_invoice ORDER BY 1").fetchall()]

        self.csv(Path('a1/invoice_adjustments_reference.csv'), 'SELECT * FROM ar_adjustment ORDER BY adjustment_id')
        self.csv(
            Path('a1/prepayments_reference.csv'),
            """SELECT r.*, i.issue_date
               FROM warehouse.main.ar_receipt r
               JOIN warehouse.main.ar_invoice i USING(invoice_id)
               WHERE r.receipt_date < i.issue_date
               ORDER BY receipt_id""",
        )
        if 'customer_persona' in self.tables:
            self.csv(
                Path('a1/customer_personas_reference.csv'),
                """SELECT cp.*
                   FROM warehouse.main.customer_persona cp
                   JOIN a1_eligible_customers USING(customer_code)
                   ORDER BY cp.customer_code""",
            )

        for month in months:
            where = f"strftime(i.issue_date, '%Y-%m') = {q(month)}"
            self.csv(
                Path(f'a1/{month}/01_invoices.csv'),
                f"""SELECT 'INV-' || i.invoice_id invoice_id,
                           i.customer_code customer_id,
                           p.partner_name customer_name,
                           i.issue_date,
                           i.due_date,
                           i.total_amount::BIGINT amount,
                           'VND' currency,
                           i.issue_date known_at
                    FROM ar_invoice i
                    JOIN dim_partner p ON p.partner_code = i.customer_code
                    WHERE {where}
                    ORDER BY i.invoice_id""",
            )
            self.csv(
                Path(f'a1/{month}/03_payments.csv'),
                f"""SELECT 'REC-' || r.receipt_id payment_id,
                           'INV-' || r.invoice_id invoice_id,
                           greatest(r.receipt_date, i.issue_date) payment_date,
                           r.amount::BIGINT amount,
                           CASE WHEN r.receipt_date >= i.issue_date THEN r.journal_id || ':' || r.cash_account ELSE '' END bank_id,
                           greatest(r.receipt_date, i.issue_date, coalesce(b.known_at, r.receipt_date)) known_at
                    FROM ar_receipt r
                    JOIN ar_invoice i USING(invoice_id)
                    LEFT JOIN bank b ON b.bank_id = (r.journal_id || ':' || r.cash_account)
                    WHERE {where}
                    ORDER BY r.receipt_id""",
            )
            if 'customer_persona' in self.tables:
                self.csv(
                    Path(f'a1/{month}/06_actions.csv'),
                    f"""SELECT 'ACT-' || i.invoice_id event_id,
                               'INV-' || i.invoice_id invoice_id,
                               least(i.due_date + 7, {q(self.cutoff)}::DATE) date,
                               CASE WHEN cp.persona = 'DISPUTE_PRONE' AND i.invoice_id % 3 = 0 THEN 'dispute'
                                    WHEN cp.persona = 'CHRONIC_LATE' AND i.invoice_id % 2 = 0 THEN 'promise'
                                    ELSE 'contact' END kind,
                               CASE WHEN cp.persona = 'CHRONIC_LATE' AND i.invoice_id % 2 = 0
                                    THEN (least(i.due_date + 7, {q(self.cutoff)}::DATE) + 14)::VARCHAR
                                    ELSE '' END promise_date,
                               least(i.due_date + 7, {q(self.cutoff)}::DATE) known_at
                        FROM ar_invoice i
                        JOIN warehouse.main.customer_persona cp USING(customer_code)
                        WHERE {where}
                          AND i.due_date + 7 <= {q(self.cutoff)}::DATE
                          AND (cp.persona IN ('CHRONIC_LATE', 'DISPUTE_PRONE') AND i.invoice_id % 7 = 0)
                        ORDER BY i.invoice_id""",
                )
            else:
                self.csv(
                    Path(f'a1/{month}/06_actions.csv'),
                    f"""SELECT 'CONTACT-' || i.invoice_id event_id,
                               'INV-' || i.invoice_id invoice_id,
                               least(i.due_date + 7, {q(self.cutoff)}::DATE) date,
                               'contact' kind,
                               least(i.due_date + 7, {q(self.cutoff)}::DATE) known_at
                        FROM ar_invoice i
                        WHERE {where} AND i.due_date < {q(self.cutoff)}::DATE AND i.invoice_id % 101 = 0
                        ORDER BY i.invoice_id""",
                )

        for (month,) in self.db.execute(
            f"SELECT DISTINCT strftime(date, '%Y-%m') FROM bank WHERE date >= {q(bank_start)}::DATE ORDER BY 1"
        ).fetchall():
            self.csv(
                Path(f'a1/{month}/02_bank.csv'),
                f"""SELECT b.bank_id,
                           b.account,
                           b.date,
                           CASE WHEN b.net > 0 THEN 'in' ELSE 'out' END direction,
                           abs(b.net)::BIGINT amount,
                           greatest(b.date, b.known_at) known_at,
                           CASE WHEN r_ret.journal_id IS NOT NULL AND b.net > 0 THEN 'cash_sale'
                                WHEN b.journal_id LIKE 'OPEX-%' AND b.net < 0 THEN 'variable_cost'
                                ELSE 'other' END component,
                           coalesce(b.description, '') memo,
                           coalesce(b.partner_name, '') counterparty,
                           coalesce(r_a1.customer_code, '') customer_id,
                           CASE WHEN r_a1.journal_id IS NOT NULL THEN 'ar'
                                WHEN r_other.journal_id IS NOT NULL THEN 'other_external'
                                WHEN b.journal_id LIKE 'DRAW-%' OR b.journal_id LIKE 'REPAY-%'
                                     OR b.journal_id = 'OPEN-CASH' OR b.journal_id LIKE 'INTEREST-%' THEN 'financing'
                                WHEN b.journal_id LIKE 'VAT-PAY-%' OR b.journal_id LIKE 'CITPAY-%'
                                     OR b.journal_id LIKE 'HR-TAX-%' THEN 'tax'
                                ELSE 'operating' END cash_flow_class
                    FROM bank b
                    LEFT JOIN a1_rcpt_journals r_a1 ON r_a1.journal_id = b.journal_id
                    LEFT JOIN retail_rcpt_journals r_ret ON r_ret.journal_id = b.journal_id
                    LEFT JOIN other_ar_rcpt_journals r_other ON r_other.journal_id = b.journal_id
                    WHERE strftime(b.date, '%Y-%m') = {q(month)}
                    ORDER BY b.date, b.bank_id""",
            )

        # Include full cumulative opening balance from 2022-12-31 while exporting statements from bank_start
        self.csv(
            Path('a1/04_statements.csv'),
            f"""SELECT statement_id, account, start_date, end_date, opening_balance, closing_balance, known_at
                FROM (
                    SELECT account || ':' || start_date statement_id,
                           account,
                           start_date,
                           end_date,
                           (sum(movement) OVER(PARTITION BY account ORDER BY start_date) - movement)::BIGINT opening_balance,
                           sum(movement) OVER(PARTITION BY account ORDER BY start_date)::BIGINT closing_balance,
                           stmt_known_at known_at
                    FROM monthly_bank
                )
                WHERE start_date >= {q(bank_start)}::DATE
                ORDER BY account, start_date""",
        )

        # 05_outflows.csv: BOTH overdue unpaid AP (due_date <= cutoff) AND upcoming scheduled AP + accrued payroll/tax
        self.csv(
            Path('a1/05_outflows.csv'),
            f"""SELECT * FROM (
                SELECT 'SCHEDULE-AP-' || b.bill_id AS expense_id,
                       b.due_date AS date,
                       (b.total_amount - coalesce(p.paid, 0))::BIGINT AS amount,
                       'supplier' AS category,
                       least(b.bill_date, {q(self.cutoff)}::DATE) AS known_at,
                       'AP-BILL-' || b.bill_id AS obligation_ref,
                       strftime(b.bill_date, '%Y-%m') AS payment_period,
                       1 AS installment_no,
                       'open' AS status,
                       'Sổ công nợ phải trả NCC (TK 331)' AS source,
                       'true' AS verified
                FROM warehouse.main.ap_bill b
                LEFT JOIN (SELECT bill_id, sum(amount)::BIGINT paid FROM warehouse.main.ap_payment GROUP BY bill_id) p USING(bill_id)
                WHERE b.total_amount > coalesce(p.paid, 0)

                UNION ALL
                SELECT 'SCHEDULE-PAYROLL-' || e.year_month AS expense_id,
                       (max(e.accrued_on) + 5)::DATE AS date,
                       sum(w.net_pay)::BIGINT AS amount,
                       'payroll' AS category,
                       least(max(e.accrued_on), {q(self.cutoff)}::DATE) AS known_at,
                       'PAYROLL-NET' AS obligation_ref,
                       e.year_month AS payment_period,
                       1 AS installment_no,
                       'open' AS status,
                       'Bảng lương phải trả người lao động (TK 334)' AS source,
                       'true' AS verified
                FROM warehouse.main.payroll_events e
                JOIN warehouse.main.payroll w USING(year_month, employee_code)
                WHERE e.accrued_on + 5 > {q(self.cutoff)}::DATE
                GROUP BY e.year_month
                HAVING sum(w.net_pay) > 0

                UNION ALL
                SELECT 'SCHEDULE-HR-TAX-' || e.year_month AS expense_id,
                       (max(e.accrued_on) + 15)::DATE AS date,
                       sum(w.employer_contribution + w.employee_contribution + w.pit)::BIGINT AS amount,
                       'pit_withholding' AS category,
                       least(max(e.accrued_on), {q(self.cutoff)}::DATE) AS known_at,
                       'STATUTORY-BHXH-PIT' AS obligation_ref,
                       e.year_month AS payment_period,
                       1 AS installment_no,
                       'open' AS status,
                       'Hồ sơ BHXH bắt buộc và khấu trừ thuế TNCN (TK 3383/3335)' AS source,
                       'true' AS verified
                FROM warehouse.main.payroll_events e
                JOIN warehouse.main.payroll w USING(year_month, employee_code)
                WHERE e.accrued_on + 15 > {q(self.cutoff)}::DATE
                GROUP BY e.year_month
                HAVING sum(w.employer_contribution + w.employee_contribution + w.pit) > 0

                UNION ALL
                SELECT 'SCHEDULE-VAT-' || ym AS expense_id,
                       (accrued_on + 20)::DATE AS date,
                       greatest(output_vat - input_vat, 0)::BIGINT AS amount,
                       'tax' AS category,
                       least(accrued_on, {q(self.cutoff)}::DATE) AS known_at,
                       'STATUTORY-VAT' AS obligation_ref,
                       ym AS payment_period,
                       1 AS installment_no,
                       'open' AS status,
                       'Tờ khai thuế GTGT tháng (TK 33311)' AS source,
                       'true' AS verified
                FROM warehouse.main.monthly_vat
                WHERE accrued_on <= {q(self.cutoff)}::DATE
                  AND accrued_on + 20 > {q(self.cutoff)}::DATE
                  AND output_vat > input_vat
            )
            ORDER BY date, expense_id""",
        )

        for name in (
            'a1_eligible_customers',
            'ar_invoice',
            'ar_adjustment',
            'ar_receipt',
            'a1_rcpt_journals',
            'retail_rcpt_journals',
            'other_ar_rcpt_journals',
        ):
            self.db.execute('DROP TABLE temp.main.' + name)

    def a2(self):
        """Export Agent 2 rich tabular CSVs + Ground-Truth Fraud Reference + Canonical 1.1.0 JSON Bundle."""
        has_vmeta = 'vendor_meta' in self.tables
        has_emeta = 'employee_meta' in self.tables

        self.db.execute("""CREATE OR REPLACE TEMP TABLE journal_totals AS
            SELECT journal_id,
                   posting_date,
                   sum(debit_amount)::BIGINT amount,
                   sum(credit_amount)::BIGINT credit_total,
                   arg_max(account_code, debit_amount) debit_account,
                   arg_max(account_code, credit_amount) credit_account,
                   bool_or(account_code LIKE '111%') has_cash,
                   bool_or(account_code LIKE '112%') has_bank,
                   bool_and(tax_deductible) all_tax_deductible,
                   min(partner_code) partner_code,
                   min(employee_code) employee_code,
                   sum(CASE WHEN account_code LIKE '133%' THEN net_debit ELSE 0 END)::BIGINT input_vat,
                   sum(CASE WHEN account_code LIKE '3331%' THEN -net_debit ELSE 0 END)::BIGINT output_vat,
                   sum(CASE WHEN account_code = '154' THEN debit_amount ELSE 0 END)::BIGINT production_cost
            FROM v_gl
            WHERE NOT is_closing AND year_no >= 2023
            GROUP BY journal_id, posting_date""")

        # Link AP payments and AP bills so transactions carry real invoice_number & invoice_gross_vnd
        self.db.execute("""CREATE OR REPLACE TEMP TABLE ap_journal_links AS
            SELECT p.journal_id,
                   b.bill_id,
                   b.journal_id AS bill_journal_id,
                   b.vendor_invoice_no AS invoice_number,
                   b.bill_date::VARCHAR || 'T08:00:00+07:00' AS invoice_issued_at,
                   b.total_amount::BIGINT AS invoice_gross_vnd
            FROM ap_payment p
            JOIN ap_bill b USING(bill_id)
            UNION ALL
            SELECT b.journal_id,
                   b.bill_id,
                   b.journal_id AS bill_journal_id,
                   b.vendor_invoice_no AS invoice_number,
                   b.bill_date::VARCHAR || 'T08:00:00+07:00' AS invoice_issued_at,
                   b.total_amount::BIGINT AS invoice_gross_vnd
            FROM ap_bill b""")

        vmeta_join = 'LEFT JOIN vendor_meta vm ON vm.vendor_code = dp.partner_code' if has_vmeta else ''
        v_tax_expr = "coalesce(vm.a2_tax_id, dp.tax_id, '')" if has_vmeta else "coalesce(dp.tax_id, '')"
        v_bank_expr = (
            "coalesce(vm.bank_account, CASE WHEN dp.partner_type = 'VENDOR' THEN '99' || lpad(dp.partner_key::VARCHAR, 10, '0') ELSE '' END)"
            if has_vmeta
            else "CASE WHEN dp.partner_type = 'VENDOR' THEN '99' || lpad(dp.partner_key::VARCHAR, 10, '0') ELSE '' END"
        )
        v_bcode_expr = "coalesce(vm.bank_code, 'VCB')" if has_vmeta else "'VCB'"

        # Select ALL seeded anomalies + v_mgmt non-deductible rows + off-hours/weekend/backdated rows FIRST,
        # then stratified operational history from 2026-06..2026-10 up to 10,000 rows!
        self.db.execute(f"""CREATE OR REPLACE TEMP TABLE selected_a2_journals AS
            SELECT journal_id, is_anomaly_seed
            FROM (
                SELECT j.journal_id,
                       (j.journal_id IN ('DUP-PAY', 'TEST-UNBALANCED', 'SALE-17')
                        OR j.journal_id LIKE 'SPLIT-%'
                        OR j.journal_id LIKE 'CSPLIT-%'
                        OR j.journal_id LIKE 'WKND-SELF-%'
                        OR j.journal_id LIKE 'SPIKE-ROUND-%'
                        OR j.journal_id LIKE 'COLLUSION-PAY-%'
                        OR j.journal_id LIKE 'BUY-R02-%'
                        OR j.journal_id LIKE 'BUY-NON-DED-%'
                        OR j.journal_id LIKE 'BUY-ENTERTAIN-%'
                        OR j.journal_id LIKE 'BUY-WELFARE-%'
                        OR j.journal_id LIKE 'BUY-COLLUSION-%'
                        OR j.journal_id LIKE 'BUY-NOMST-%'
                        OR j.journal_id LIKE 'PAY-SPEC-%'
                        OR NOT t.all_tax_deductible
                        OR j.created_at > j.posting_date + INTERVAL 1 DAY
                        OR hour(j.created_at) >= 21) AS is_anomaly_seed,
                       j.posting_date,
                       hash(j.journal_id, {self.seed}, 93) AS sample_rk
                FROM gl_journal j
                JOIN journal_totals t USING(journal_id)
                WHERE t.amount > 0
                  AND (
                      j.doc_type IN ('SALES_INVOICE', 'RECEIPT', 'PAYMENT', 'PURCHASE_INVOICE',
                                     'PAYROLL_PAYMENT', 'DEPRECIATION', 'EXPENSE', 'VAT_OFFSET', 'TEST_ERROR')
                  )
            )
            ORDER BY CASE WHEN is_anomaly_seed THEN 0
                          WHEN posting_date >= DATE '2026-07-01' THEN 1
                          ELSE 2 END,
                     sample_rk,
                     posting_date DESC
            LIMIT 10000""")

        # Ensure original AP payments for any bills involved in selected AP payments (e.g. DUP-PAY's prior payment!) are ALSO in the slice
        self.db.execute("""INSERT INTO selected_a2_journals
            SELECT DISTINCT p_prior.journal_id, false
            FROM ap_payment p_sel
            JOIN selected_a2_journals s ON s.journal_id = p_sel.journal_id
            JOIN ap_payment p_prior ON p_prior.bill_id = p_sel.bill_id
            WHERE p_prior.journal_id NOT IN (SELECT journal_id FROM selected_a2_journals)""")

        self.db.execute(f"""CREATE OR REPLACE TEMP TABLE transaction_projection AS
            SELECT j.journal_id transaction_id,
                   strftime(greatest(j.created_at, j.posting_date::TIMESTAMP) + INTERVAL '10 minutes', '%Y-%m-%dT%H:%M:%S') || '+07:00' posted_at,
                   strftime(j.created_at, '%Y-%m-%dT%H:%M:%S') || '+07:00' created_at,
                   strftime(j.created_at + INTERVAL '5 minutes', '%Y-%m-%dT%H:%M:%S') || '+07:00' approved_at,
                   CASE j.doc_type
                       WHEN 'SALES_INVOICE' THEN 'sales_invoice'
                       WHEN 'RECEIPT' THEN 'customer_receipt'
                       WHEN 'PAYMENT' THEN 'vendor_payment'
                       WHEN 'PURCHASE_INVOICE' THEN 'stock_purchase'
                       WHEN 'COGS' THEN 'cogs'
                       WHEN 'PAYROLL_PAYMENT' THEN 'payroll'
                       WHEN 'DEPRECIATION' THEN 'depreciation'
                       WHEN 'EXPENSE' THEN 'rent'
                       WHEN 'VAT_OFFSET' THEN 'vat_offset'
                       ELSE 'adjustment' END txn_type,
                   t.amount amount_vnd,
                   20000000::BIGINT approval_limit_vnd,
                   coalesce(j.created_by, 'E000003') creator_id,
                   CASE
                       WHEN j.journal_id LIKE 'WKND-SELF-%' OR j.journal_id IN ('SPIKE-ROUND-2', 'CSPLIT-1')
                           THEN coalesce(j.created_by, 'E000005')
                       WHEN t.amount > 20000000
                           THEN CASE WHEN j.created_by = 'E000001' THEN 'E000002' ELSE 'E000001' END
                       ELSE CASE WHEN j.created_by = 'E000003' THEN 'E000004' ELSE 'E000003' END
                   END approver_id,
                   1 is_financial_entry,
                   t.debit_account,
                   t.credit_account,
                   t.debit_account || '/' || t.credit_account journal_signature,
                   CASE j.doc_type
                       WHEN 'SALES_INVOICE' THEN 'sales_invoice'
                       WHEN 'RECEIPT' THEN 'customer_receipt'
                       WHEN 'PAYMENT' THEN 'vendor_payment'
                       WHEN 'PURCHASE_INVOICE' THEN 'stock_purchase'
                       WHEN 'PAYROLL_PAYMENT' THEN 'payroll'
                       WHEN 'DEPRECIATION' THEN 'depreciation'
                       WHEN 'EXPENSE' THEN 'rent'
                       WHEN 'VAT_OFFSET' THEN 'vat_offset'
                       ELSE 'adjustment' END accounting_purpose,
                   greatest(t.input_vat, 0)::BIGINT recognised_input_vat_vnd,
                   greatest(t.output_vat, 0)::BIGINT recognised_output_vat_vnd,
                   0::BIGINT writeoff_provision_vnd,
                   t.production_cost::BIGINT production_cost_vnd,
                   'MPX10' company_id,
                   CASE WHEN t.partner_code LIKE 'V%' THEN t.partner_code ELSE '' END vendor_id,
                   coalesce(t.employee_code, '') employee_id,
                   CASE WHEN t.partner_code LIKE 'C%' THEN t.partner_code ELSE '' END customer_id,
                   CASE WHEN dp.partner_code IS NOT NULL THEN {v_tax_expr} ELSE '' END counterparty_tax_code,
                   CASE WHEN dp.partner_type = 'VENDOR' THEN {v_bank_expr} ELSE '' END recipient_account,
                   CASE WHEN dp.partner_type = 'VENDOR' THEN {v_bcode_expr} ELSE '' END recipient_bank_code,
                   CASE WHEN t.has_cash THEN 'cash'
                        WHEN t.has_bank THEN 'bank'
                        ELSE 'journal' END payment_channel,
                   coalesce(apl.invoice_number, '') invoice_number,
                   coalesce(apl.invoice_issued_at, '') invoice_issued_at,
                   coalesce(apl.invoice_gross_vnd, 0)::BIGINT invoice_gross_vnd,
                   CASE WHEN t.all_tax_deductible THEN 1 ELSE 0 END tax_deductible,
                   CASE WHEN apl.bill_id IS NOT NULL AND t.all_tax_deductible THEN 2 ELSE 0 END support_doc_count,
                   CASE WHEN apl.bill_id IS NOT NULL AND t.all_tax_deductible THEN 1 ELSE 0 END goods_receipt_verified,
                   CASE WHEN apl.bill_id IS NOT NULL AND t.all_tax_deductible THEN 1 ELSE 0 END evidence_on_file,
                   j.journal_id journal_document_id,
                   coalesce(apl.bill_journal_id, '') linked_document_id,
                   coalesce(j.description, 'Bút toán kế toán MPX10') business_purpose
            FROM gl_journal j
            JOIN selected_a2_journals sel USING(journal_id)
            JOIN journal_totals t USING(journal_id)
            LEFT JOIN dim_partner dp ON dp.partner_code = t.partner_code
            {vmeta_join}
            LEFT JOIN ap_journal_links apl ON apl.journal_id = j.journal_id""")

        self.db.execute(
            f"UPDATE transaction_projection SET debit_account = {a2_account('debit_account')}, credit_account = {a2_account('credit_account')}"
        )
        self.db.execute(f"""UPDATE transaction_projection SET journal_signature = p.signature
            FROM (
                WITH accounts AS (
                    SELECT DISTINCT journal_id, {a2_account('account_code')} account_code, debit_amount > 0 debit
                    FROM v_gl
                    WHERE journal_id IN (SELECT transaction_id FROM transaction_projection)
                )
                SELECT d.journal_id,
                       string_agg(DISTINCT d.account_code || '/' || c.account_code, ';' ORDER BY d.account_code || '/' || c.account_code) signature
                FROM accounts d JOIN accounts c USING(journal_id)
                WHERE d.debit AND NOT c.debit
                GROUP BY d.journal_id
            ) p
            WHERE transaction_id = p.journal_id""")

        self.csv(
            Path('a2/journal_documents.csv'),
            """SELECT j.journal_id document_id,
                      j.journal_id transaction_id,
                      'MPX10' company_id,
                      j.posting_date,
                      j.doc_type,
                      j.description,
                      t.accounting_purpose purpose,
                      t.posted_at,
                      j.created_by,
                      j.created_at
               FROM gl_journal j
               JOIN transaction_projection t ON t.transaction_id = j.journal_id
               ORDER BY j.posting_date, j.journal_id""",
        )
        self.csv(
            Path('a2/journal_lines.csv'),
            f"""SELECT g.entry_id line_id,
                       g.journal_id document_id,
                       g.journal_id transaction_id,
                       'MPX10' company_id,
                       {a2_account('g.account_code')} account_code,
                       g.account_code source_account_code,
                       g.debit_amount::BIGINT debit_vnd,
                       g.credit_amount::BIGINT credit_vnd,
                       g.partner_code,
                       g.item_code,
                       g.branch_code,
                       g.tax_deductible,
                       g.posting_date,
                       t.posted_at
                FROM v_gl g
                JOIN transaction_projection t ON t.transaction_id = g.journal_id
                ORDER BY g.entry_id""",
        )
        self.csv(
            Path('a2/companies.csv'),
            f"SELECT 'MPX10' AS company_id, {q(self.info['name'])} AS name, {q(self.info['tax_id'])} AS tax_id, "
            "'TT133' AS accounting_framework, 20000000 AS approval_limit_vnd, 0 AS saturday_operations, '2023-01-01T00:00:00+07:00' AS recorded_at",
        )
        if has_emeta:
            self.csv(
                Path('a2/employees.csv'),
                """SELECT e.employee_code AS employee_id,
                          'MPX10' AS company_id,
                          e.employee_name AS full_name,
                          e.department_code,
                          e.branch_code,
                          em.bank_account,
                          em.bank_code,
                          em.phone,
                          em.address,
                          em.role,
                          e.base_salary::BIGINT AS monthly_salary_vnd,
                          e.hire_date,
                          coalesce(e.leave_date::VARCHAR, '') AS termination_date,
                          e.hire_date::VARCHAR || 'T00:00:00+07:00' AS hired_at,
                          '2023-01-01T00:00:00+07:00' AS recorded_at,
                          1 AS contract_on_file,
                          1 AS leave_request_required,
                          0 AS self_approval_allowed,
                          em.self_approval_limit_vnd,
                          em.approval_limit_vnd
                   FROM dim_employee e
                   JOIN employee_meta em USING(employee_code)
                   ORDER BY e.employee_code""",
            )
        else:
            self.csv(
                Path('a2/employees.csv'),
                """SELECT employee_code AS employee_id, 'MPX10' AS company_id, employee_name AS full_name,
                          department_code, branch_code, '88' || lpad(employee_key::VARCHAR, 10, '0') AS bank_account,
                          'VCB' AS bank_code, '091' || lpad(employee_key::VARCHAR, 7, '0') AS phone, 'Hà Nội' AS address,
                          'staff' AS role, base_salary::BIGINT AS monthly_salary_vnd, hire_date,
                          coalesce(leave_date::VARCHAR, '') AS termination_date,
                          hire_date::VARCHAR || 'T00:00:00+07:00' AS hired_at, '2023-01-01T00:00:00+07:00' AS recorded_at,
                          1 AS contract_on_file, 1 AS leave_request_required, 0 AS self_approval_allowed,
                          0 AS self_approval_limit_vnd, 20000000 AS approval_limit_vnd
                   FROM dim_employee ORDER BY employee_code""",
            )

        if has_vmeta:
            self.csv(
                Path('a2/vendors.csv'),
                """SELECT p.partner_code AS vendor_id,
                          'MPX10' AS company_id,
                          p.partner_name AS name,
                          vm.a2_tax_id AS tax_id,
                          '2023-01-01T00:00:00+07:00' AS recorded_at,
                          '2021-01-01T00:00:00+07:00' AS registered_at,
                          '2023-01-01T00:00:00+07:00' AS onboarded_at,
                          '' AS related_party_disclosed_at,
                          vm.phone,
                          vm.address,
                          vm.bank_account,
                          vm.bank_code
                   FROM dim_partner p
                   JOIN vendor_meta vm ON vm.vendor_code = p.partner_code
                   WHERE p.partner_type = 'VENDOR'
                   ORDER BY p.partner_code""",
            )
        else:
            self.csv(
                Path('a2/vendors.csv'),
                """SELECT partner_code AS vendor_id, 'MPX10' AS company_id, partner_name AS name, tax_id,
                          '2023-01-01T00:00:00+07:00' AS recorded_at, '2021-01-01T00:00:00+07:00' AS registered_at,
                          '2023-01-01T00:00:00+07:00' AS onboarded_at, '' AS related_party_disclosed_at,
                          '02838' || lpad((partner_key % 100000)::VARCHAR, 5, '0') AS phone,
                          'TP. Hồ Chí Minh' AS address,
                          '99' || lpad(partner_key::VARCHAR, 10, '0') AS bank_account, 'VCB' AS bank_code
                   FROM dim_partner WHERE partner_type = 'VENDOR' ORDER BY partner_code""",
            )

        self.csv(
            Path('a2/customers.csv'),
            """SELECT partner_code AS customer_id, 'MPX10' AS company_id, partner_name AS name, tax_id,
                      '2023-01-01T00:00:00+07:00' AS recorded_at
               FROM dim_partner WHERE partner_type = 'CUSTOMER' ORDER BY partner_code""",
        )
        self.csv(
            Path('a2/calendar.csv'),
            "SELECT 'MPX10' AS company_id, calendar_date AS date, 1 AS is_holiday, 'Ngày nghỉ cuối tuần' AS name "
            "FROM dim_period WHERE NOT is_business_day ORDER BY calendar_date",
        )
        self.csv(
            Path('a2/anomaly_ground_truth.csv'),
            """SELECT t.transaction_id,
                      t.posted_at,
                      t.txn_type,
                      t.amount_vnd,
                      t.payment_channel,
                      t.creator_id,
                      t.approver_id,
                      t.vendor_id,
                      t.counterparty_tax_code,
                      t.tax_deductible,
                      CASE
                          WHEN t.transaction_id = 'DUP-PAY' THEN 'DUPLICATE_PAYMENT_P1'
                          WHEN t.transaction_id = 'TEST-UNBALANCED' THEN 'UNBALANCED_JOURNAL_AND_NONDEDUCTIBLE'
                          WHEN t.transaction_id LIKE 'SPLIT-%' THEN 'APPROVAL_LIMIT_SPLIT_20M_OFFHOURS'
                          WHEN t.transaction_id LIKE 'CSPLIT-%' THEN 'CASH_SPLIT_UNDER_5M_ND181'
                          WHEN t.transaction_id LIKE 'WKND-SELF-%' THEN 'WEEKEND_OFFHOURS_SELF_APPROVAL_ROUND'
                          WHEN t.transaction_id LIKE 'SPIKE-ROUND-%' THEN 'ROUND_NUMBER_SPIKE_NONDEDUCTIBLE'
                          WHEN t.transaction_id LIKE 'COLLUSION-PAY-%' THEN 'SHARED_EMPLOYEE_VENDOR_BANK_AND_MISSING_MST'
                          WHEN t.transaction_id LIKE 'BUY-NON-DED-%' OR t.transaction_id LIKE 'BUY-ENTERTAIN-%' THEN 'PERSONAL_ENTERTAINMENT_NONDEDUCTIBLE'
                          WHEN t.transaction_id = 'SALE-17' THEN 'PROMPT_INJECTION_PAYLOAD_TEST'
                          ELSE 'OTHER_ANOMALY_OR_LATE_POSTING'
                      END anomaly_family,
                      t.business_purpose
               FROM transaction_projection t
               JOIN selected_a2_journals s ON s.journal_id = t.transaction_id
               WHERE s.is_anomaly_seed
               ORDER BY t.posted_at, t.transaction_id""",
        )
        self.csv(Path('a2/transactions_full.csv'), 'SELECT * FROM transaction_projection ORDER BY posted_at, transaction_id')

        # Bounded CSV chunks
        cur = self.db.execute('SELECT * FROM transaction_projection ORDER BY posted_at, transaction_id')
        header = [d[0] for d in cur.description]
        index = 0
        while rows := cur.fetchmany(10000):
            index += 1
            path = self.root / f'a2/chunks/transactions_{index:04}.csv'
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(header)
                w.writerows(rows)

        # Build Canonical 1.1.0 JSON Bundle compatible with portal/agent2_intake.py and Agent 2 v2 SnapshotStore!
        bundle = self._build_a2_canonical_bundle()
        bundle_path = self.root / 'a2/canonical_bundle.json'
        bundle_bytes = _canonical_json_bytes(bundle)
        bundle_path.write_bytes(bundle_bytes)
        print(
            f'A2: {index} bounded CSV chunk(s) + canonical_bundle.json ({len(bundle["transactions"])} txs, {len(bundle_bytes):,} bytes)',
            flush=True,
        )
        for name in ('journal_totals', 'ap_journal_links', 'selected_a2_journals', 'transaction_projection'):
            self.db.execute('DROP TABLE temp.main.' + name)

    def _build_a2_canonical_bundle(self) -> dict:
        """Construct an exact 1.1.0 canonical input bundle preserving cash/bank anomalies, approvals, and P1 manifests."""
        tenant = self.tenant_id
        cid = 'MPX10'
        master_ts = '2023-01-01T00:00:00+07:00'

        def src(rid: str) -> dict:
            return {'system': 'mpx10-unified-pipeline', 'record_id': rid, 'is_simulated': True}

        def base(rid: str, obs: str, eff: str) -> dict:
            return {
                'tenant_id': tenant,
                'company_id': cid,
                'record_id': rid,
                'revision': 1,
                'observed_at': obs,
                'effective_at': eff,
                'source': src(rid),
            }

        # Select <= 1,200 transactions for the JSON bundle (< 4 MB, well under 9 MB / 50,000-record limits):
        # 100% of cash/bank/transfer anomalies + all linked prior AP payments + stratified operational history across Jul-Oct 2026
        self.db.execute(f"""CREATE OR REPLACE TEMP TABLE json_tx_ids AS
            SELECT transaction_id
            FROM (
                SELECT t.transaction_id,
                       s.is_anomaly_seed,
                       t.posted_at,
                       hash(t.transaction_id, {self.seed}, 97) rk
                FROM transaction_projection t
                JOIN selected_a2_journals s ON s.journal_id = t.transaction_id
                WHERE t.payment_channel IN ('bank', 'cash')
                   OR t.transaction_id = 'TEST-UNBALANCED'
            )
            ORDER BY CASE WHEN is_anomaly_seed THEN 0
                          WHEN posted_at >= '2026-09-01' THEN 1
                          ELSE 2 END,
                     rk,
                     posted_at DESC
            LIMIT 260""")

        # Pull in all prior AP payments on the same AP bills so P1 invoice payment history is 100% complete since inception!
        self.db.execute("""INSERT INTO json_tx_ids
            SELECT DISTINCT p_all.journal_id
            FROM ap_payment p_sel
            JOIN json_tx_ids j ON j.transaction_id = p_sel.journal_id
            JOIN ap_payment p_all ON p_all.bill_id = p_sel.bill_id
            WHERE p_all.journal_id NOT IN (SELECT transaction_id FROM json_tx_ids)""")

        tx_rows = self.db.execute("""SELECT t.transaction_id, t.posted_at, t.created_at, t.approved_at,
                   t.txn_type, t.amount_vnd, t.approval_limit_vnd, t.creator_id, t.approver_id,
                   t.vendor_id, t.employee_id, t.recipient_account, t.recipient_bank_code,
                   t.payment_channel, t.business_purpose, p.bill_id
            FROM transaction_projection t
            JOIN json_tx_ids j USING(transaction_id)
            LEFT JOIN ap_payment p ON p.journal_id = t.transaction_id
            ORDER BY t.posted_at, t.transaction_id""").fetchall()

        # Accounting lines per transaction
        line_map: dict[str, list[dict]] = {}
        for jid, acc, deb, cred in self.db.execute(f"""
            SELECT g.journal_id, {a2_account('g.account_code')}, g.debit_amount::BIGINT, g.credit_amount::BIGINT
            FROM v_gl g
            JOIN json_tx_ids j ON j.transaction_id = g.journal_id
            ORDER BY g.journal_id, g.entry_id""").fetchall():
            line_map.setdefault(jid, []).append({'account': acc, 'debit_vnd': int(deb), 'credit_vnd': int(cred)})

        used_vendors = {r[9] for r in tx_rows if r[9]}
        # Always include V000018, V000019, V000020, V000021 in vendor master so E3 fuzzy name & B5/graph comparisons see peers!
        for special_v in ('V000018', 'V000019', 'V000020', 'V000021'):
            if self.db.execute(f"SELECT count(*) FROM dim_partner WHERE partner_code = {q(special_v)}").fetchone()[0]:
                used_vendors.add(special_v)

        used_employees = ({r[7] for r in tx_rows if r[7]} | {r[8] for r in tx_rows if r[8]} | {r[10] for r in tx_rows if r[10]} | {'E000008'})
        bill_ids = sorted({int(r[15]) for r in tx_rows if r[15] is not None})

        # Vendors & vendor_bank_history
        vendors_json = []
        bank_history_json = []
        if used_vendors:
            v_in = ','.join(q(v) for v in sorted(used_vendors))
            if 'vendor_meta' in self.tables:
                v_records = self.db.execute(f"""
                    SELECT p.partner_code, p.partner_name, vm.a2_tax_id, vm.address, vm.bank_account, vm.bank_code
                    FROM dim_partner p JOIN vendor_meta vm ON vm.vendor_code = p.partner_code
                    WHERE p.partner_code IN ({v_in}) ORDER BY p.partner_code""").fetchall()
            else:
                v_records = self.db.execute(f"""
                    SELECT partner_code, partner_name, tax_id, 'TP. Hồ Chí Minh',
                           '99' || lpad(partner_key::VARCHAR, 10, '0'), 'VCB'
                    FROM dim_partner WHERE partner_code IN ({v_in}) ORDER BY partner_code""").fetchall()
            for vcode, vname, vmst, vaddr, vbank, vbcode in v_records:
                vitem = dict(
                    base(vcode, master_ts, master_ts),
                    name=vname,
                    tax_id=vmst if vmst else None,
                    address=vaddr or None,
                    bank_account=vbank or None,
                    bank_code=vbcode or None,
                )
                if not vmst:
                    vitem['missing_fields'] = {'tax_id': 'missing'}
                vendors_json.append(vitem)
                if vbank and vbcode:
                    bank_history_json.append(
                        dict(
                            base(f'VBH_{vcode}', master_ts, master_ts),
                            vendor_ref={'record_id': vcode, 'revision': 1},
                            bank_account=vbank,
                            bank_code=vbcode,
                            verification_status='unverified',
                        )
                    )

        # Employees
        employees_json = []
        if used_employees:
            e_in = ','.join(q(e) for e in sorted(used_employees))
            if 'employee_meta' in self.tables:
                e_records = self.db.execute(f"""
                    SELECT e.employee_code, e.employee_name, em.role, em.bank_account, em.bank_code,
                           e.hire_date, e.leave_date
                    FROM dim_employee e JOIN employee_meta em USING(employee_code)
                    WHERE e.employee_code IN ({e_in}) ORDER BY e.employee_code""").fetchall()
            else:
                e_records = self.db.execute(f"""
                    SELECT employee_code, employee_name, 'staff',
                           '88' || lpad(employee_key::VARCHAR, 10, '0'), 'VCB', hire_date, leave_date
                    FROM dim_employee WHERE employee_code IN ({e_in}) ORDER BY employee_code""").fetchall()
            for ecode, ename, erole, ebank, ebcode, ehire, eleave in e_records:
                eitem = dict(
                    base(ecode, master_ts, master_ts),
                    name=ename,
                    role=erole,
                    bank_account=ebank or None,
                    bank_code=ebcode or None,
                    hired_at=f'{ehire}T00:00:00+07:00' if ehire else None,
                    terminated_at=f'{eleave}T00:00:00+07:00' if eleave else None,
                )
                employees_json.append(eitem)

        # Invoices (AP bills referenced by payments)
        invoices_json = []
        bill_ts_map: dict[int, str] = {}
        if bill_ids:
            b_in = ','.join(str(b) for b in bill_ids)
            for bid, inv_no, bdate, ddate, vcode, tot in self.db.execute(f"""
                SELECT bill_id, vendor_invoice_no, bill_date, due_date, vendor_code, total_amount::BIGINT
                FROM ap_bill WHERE bill_id IN ({b_in}) ORDER BY bill_id""").fetchall():
                inv_rid = f'INV_AP_{bid}'
                its = f'{bdate}T08:00:00+07:00'
                bill_ts_map[int(bid)] = its
                invoices_json.append(
                    dict(
                        base(inv_rid, its, its),
                        amount_vnd=int(tot),
                        currency='VND',
                        number=str(inv_no),
                        kind='invoice',
                        vendor_ref={'record_id': vcode, 'revision': 1},
                        due_at=f'{ddate}T17:00:00+07:00' if ddate else None,
                    )
                )

        # Transactions, Approvals, Allocations, Supporting Documents
        kind_map = {
            'customer_receipt': 'receipt',
            'vendor_payment': 'payment',
            'rent': 'payment',
            'payroll': 'payroll',
        }
        transactions_json = []
        approvals_json = []
        allocations_json = []
        documents_json = []
        p1_tx_invoices: list[tuple[str, str, str]] = []  # (tx_id, tx_ts, inv_rid)

        for (
            tid,
            posted_at,
            created_at,
            approved_at,
            txn_type,
            amt,
            app_limit,
            creator_id,
            approver_id,
            vendor_id,
            employee_id,
            recip_acc,
            recip_bcode,
            pay_chan,
            purpose,
            bid,
        ) in tx_rows:
            kind = 'transfer' if tid == 'TEST-UNBALANCED' else kind_map.get(txn_type, 'payment')
            # Ensure event/observed timestamp is strictly >= created_at and >= linked invoice timestamp
            eff_ts = created_at if (tid.startswith(('WKND-SELF-', 'SPLIT-', 'CSPLIT-', 'SPIKE-ROUND-'))) else posted_at
            if bid is not None and int(bid) in bill_ts_map and eff_ts < bill_ts_map[int(bid)]:
                eff_ts = posted_at
            obs_ts = eff_ts

            tx_obj = dict(
                base(tid, obs_ts, eff_ts),
                amount_vnd=int(amt),
                currency='VND',
                kind=kind,
                description=str(purpose or tid)[:2000],
                payment_channel=pay_chan if pay_chan in ('bank', 'cash') else 'other',
                accounting_lines=line_map.get(tid, []),
            )
            if vendor_id:
                tx_obj['vendor_ref'] = {'record_id': vendor_id, 'revision': 1}
            if employee_id:
                tx_obj['employee_ref'] = {'record_id': employee_id, 'revision': 1}
            if creator_id:
                tx_obj['created_by_ref'] = {'record_id': creator_id, 'revision': 1}
            if recip_acc:
                tx_obj['bank_account'] = recip_acc
            if recip_bcode:
                tx_obj['bank_code'] = recip_bcode
            transactions_json.append(tx_obj)

            if approver_id and kind in ('payment', 'payroll'):
                approvals_json.append(
                    dict(
                        base(f'APP_{tid}', obs_ts, eff_ts),
                        transaction_ref={'record_id': tid, 'revision': 1},
                        employee_ref={'record_id': approver_id, 'revision': 1},
                        decision='approved',
                        limit_vnd=int(app_limit),
                    )
                )

            if bid is not None and kind == 'payment':
                inv_rid = f'INV_AP_{int(bid)}'
                alloc_rid = f'ALLOC_{tid}'
                allocations_json.append(
                    dict(
                        base(alloc_rid, obs_ts, eff_ts),
                        transaction_ref={'record_id': tid, 'revision': 1},
                        invoice_ref={'record_id': inv_rid, 'revision': 1},
                        amount_vnd=int(amt),
                        currency='VND',
                        kind='allocation',
                    )
                )
                p1_tx_invoices.append((tid, obs_ts, inv_rid))

            doc_bytes = f'DOC:{tid}:{amt}:{eff_ts}'.encode('utf-8')
            documents_json.append(
                dict(
                    base(f'DOC_{tid}', obs_ts, eff_ts),
                    name=f'Chứng từ kế toán {tid}.pdf',
                    document_kind='payment_voucher' if kind == 'payment' else 'accounting_voucher',
                    source_kind='simulated',
                    content_sha256=_sha256_hex(doc_bytes),
                    verification_status='unverified',
                    subject_refs=[{'table': 'transactions', 'record_id': tid, 'revision': 1}],
                )
            )

        bundle = {
            'contract_version': '1.1.0',
            'tenant_id': tenant,
            'companies': [
                dict(
                    base(cid, master_ts, master_ts),
                    name=self.info['name'],
                    tax_id=self.info['tax_id'],
                )
            ],
            'transactions': transactions_json,
            'vendors': vendors_json,
            'invoices': invoices_json,
            'payment_allocations': allocations_json,
            'employees': employees_json,
            'approvals': approvals_json,
            'supporting_documents': documents_json,
            'vendor_bank_history': bank_history_json,
            'payment_history_coverage': [],
        }

        # Compute exact point-in-time P1 payment_history_coverage manifests so P1 evaluates cleanly on linked AP payments
        seen_cov: set[tuple[str, str]] = set()
        inv_by_id = {r['record_id']: r for r in invoices_json}
        tx_by_id = {r['record_id']: r for r in transactions_json}
        for tid, cov_ts, inv_rid in p1_tx_invoices:
            if (inv_rid, cov_ts) in seen_cov:
                continue
            seen_cov.add((inv_rid, cov_ts))
            vis_inv = [inv_by_id[inv_rid]] if inv_by_id[inv_rid]['observed_at'] <= cov_ts else []
            vis_alloc = sorted(
                [
                    a
                    for a in allocations_json
                    if a['invoice_ref']['record_id'] == inv_rid
                    and a['observed_at'] <= cov_ts
                    and a['effective_at'] <= cov_ts
                ],
                key=lambda r: (r['record_id'], r['revision']),
            )
            vis_tx_ids = {a['transaction_ref']['record_id'] for a in vis_alloc}
            vis_tx = sorted(
                [tx_by_id[x] for x in vis_tx_ids if tx_by_id[x]['observed_at'] <= cov_ts],
                key=lambda r: (r['record_id'], r['revision']),
            )
            manifest_rows = {'invoices': vis_inv, 'transactions': vis_tx, 'payment_allocations': vis_alloc}
            manifest = {
                'invoice_refs': [{'record_id': r['record_id'], 'revision': r['revision']} for r in vis_inv],
                'transaction_refs': [{'record_id': r['record_id'], 'revision': r['revision']} for r in vis_tx],
                'allocation_refs': [{'record_id': r['record_id'], 'revision': r['revision']} for r in vis_alloc],
                'record_counts': {k: len(v) for k, v in manifest_rows.items()},
                'records_sha256': _sha256_hex(_canonical_json_bytes(manifest_rows)),
            }
            cov_id = f'COV_{tid}'
            bundle['payment_history_coverage'].append(
                dict(
                    base(cov_id, cov_ts, cov_ts),
                    invoice_refs=[{'record_id': inv_rid, 'revision': 1}],
                    covered_from=master_ts,
                    covered_through=cov_ts,
                    history_basis='since_inception',
                    coverage_status='complete',
                    export_id=f'EXP_{tid}',
                    manifest=manifest,
                )
            )

        self.db.execute('DROP TABLE temp.main.json_tx_ids')
        return bundle

    def xml(self, row, role: str, lines: list[tuple[str, str, int, int, int]]) -> bytes:
        identifier, day, partner, net, vat, total, _description, pay_method = row
        own = (self.info['tax_id'], self.info['name'], self.address, '0011009999999')
        other = self.partners[partner]
        seller, buyer = (own, other) if role == 'sales' else (other, own)
        symbol = f'K{day.year % 100:02d}TMP'
        words = vnd_to_words(int(total))

        def party(tag: str, p_info: tuple) -> str:
            mst, name, addr, bank_acc = p_info
            stk_xml = f'<STKNHang>{escape(str(bank_acc))}</STKNHang>' if tag == 'NBan' and bank_acc else ''
            return f'<{tag}><Ten>{escape(str(name))}</Ten><MST>{escape(str(mst))}</MST><DChi>{escape(str(addr))}</DChi>{stk_xml}</{tag}>'

        items_xml = ''.join(
            f'<HHDVu><TChat>1</TChat><STT>{n}</STT><THHDVu>{escape(str(desc))}</THHDVu>'
            f'<DVTinh>{escape(str(unit))}</DVTinh><SLuong>{qty}</SLuong><DGia>{price}</DGia>'
            f'<ThTien>{value}</ThTien><TSuat>10%</TSuat></HHDVu>'
            for n, (desc, unit, qty, price, value) in enumerate(lines, 1)
        )
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<HDon><DLHDon Id="{role}{identifier}">'
            f'<TTChung><PBan>2.1.0</PBan><THDon>Hóa đơn giá trị gia tăng (mô phỏng)</THDon>'
            f'<KHMSHDon>1</KHMSHDon><KHHDon>{symbol}</KHHDon><SHDon>{identifier:08}</SHDon>'
            f'<NLap>{day}</NLap><DVTTe>VND</DVTTe><HTTToan>{escape(str(pay_method))}</HTTToan></TTChung>'
            f'<NDHDon>{party("NBan", seller)}{party("NMua", buyer)}'
            f'<DSHHDVu>{items_xml}</DSHHDVu>'
            f'<TToan><THTTLTSuat><LTSuat><TSuat>10%</TSuat><ThTien>{net}</ThTien><TThue>{vat}</TThue></LTSuat></THTTLTSuat>'
            f'<TgTCThue>{net}</TgTCThue><TgTThue>{vat}</TgTThue><TgTTTBSo>{total}</TgTTTBSo>'
            f'<TgTTTBChu>{escape(words)}</TgTTTBChu></TToan>'
            f'</NDHDon></DLHDon><DSCKS><NBan/></DSCKS></HDon>'
        ).encode('utf-8')

    def a3(self):
        """Export Agent 3 e-invoice XMLs, bank statement CSVs, and portal list with realistic paid/unpaid/cash AP mix."""
        self.db.execute("""CREATE OR REPLACE TEMP TABLE ar_invoice AS
            SELECT i.*,
                   CASE WHEN EXISTS (SELECT 1 FROM warehouse.main.ar_receipt r WHERE r.invoice_id = i.invoice_id)
                        THEN 'CK' ELSE 'TM/CK' END pay_label
            FROM warehouse.main.ar_invoice i
            WHERE NOT EXISTS (SELECT 1 FROM warehouse.main.ar_adjustment a WHERE a.invoice_id = i.invoice_id)
            ORDER BY i.issue_date DESC, i.invoice_id DESC
            LIMIT 2500""")

        # Stratified 2,500 purchase invoices guaranteeing:
        # 1) All R02 same-day split pairs & welfare/entertainment/non-deductible test bills
        # 2) Paid AP bills matched to bank transfers (331 -> 11211)
        # 3) Cash-paid AP bills (331 -> 1111)
        # 4) Unpaid open AP bills (both overdue and not-yet-due)
        self.db.execute("""CREATE OR REPLACE TEMP TABLE ap_bill AS
            SELECT b.*,
                   CASE WHEN pm.pay_method = 'CASH' THEN 'TM'
                        WHEN pm.pay_method = 'BANK' THEN 'CK'
                        ELSE 'TM/CK' END pay_label
            FROM (
                SELECT b.*,
                       CASE
                           WHEN b.journal_id LIKE 'BUY-R02-%'
                                OR b.journal_id LIKE 'BUY-NON-DED-%'
                                OR b.journal_id LIKE 'BUY-ENTERTAIN-%'
                                OR b.journal_id LIKE 'BUY-WELFARE-%'
                                OR b.journal_id LIKE 'BUY-COLLUSION-%'
                                OR b.journal_id LIKE 'BUY-NOMST-%' THEN 0
                           WHEN pm.pay_method = 'BANK' THEN 1
                           WHEN pm.pay_method = 'CASH' THEN 2
                           ELSE 3
                       END bucket,
                       row_number() OVER (
                           PARTITION BY CASE
                               WHEN b.journal_id LIKE 'BUY-%' AND b.journal_id NOT LIKE 'BUY-0%' AND b.journal_id NOT LIKE 'BUY-1%'
                                    AND b.journal_id NOT LIKE 'BUY-2%' AND b.journal_id NOT LIKE 'BUY-3%'
                                    AND b.journal_id NOT LIKE 'BUY-4%' AND b.journal_id NOT LIKE 'BUY-5%'
                                    AND b.journal_id NOT LIKE 'BUY-6%' AND b.journal_id NOT LIKE 'BUY-7%'
                                    AND b.journal_id NOT LIKE 'BUY-8%' AND b.journal_id NOT LIKE 'BUY-9%' THEN 0
                               WHEN pm.pay_method = 'BANK' THEN 1
                               WHEN pm.pay_method = 'CASH' THEN 2
                               ELSE 3 END
                           ORDER BY b.bill_date DESC, b.bill_id DESC
                       ) rn
                FROM warehouse.main.ap_bill b
                LEFT JOIN (
                    SELECT bill_id, min(method) pay_method
                    FROM warehouse.main.ap_payment
                    GROUP BY bill_id
                ) pm USING(bill_id)
            ) b
            LEFT JOIN (
                SELECT bill_id, min(method) pay_method
                FROM warehouse.main.ap_payment
                GROUP BY bill_id
            ) pm USING(bill_id)
            WHERE (b.bucket = 0)
               OR (b.bucket = 1 AND b.rn <= 1700)
               OR (b.bucket = 2 AND b.rn <= 250)
               OR (b.bucket = 3 AND b.rn <= 600)
            ORDER BY b.bucket, b.bill_date DESC, b.bill_id DESC
            LIMIT 2500""")

        if 'vendor_meta' in self.tables:
            self.partners = {
                code: (tax, name, addr, bank_acc)
                for code, tax, name, addr, bank_acc in self.db.execute("""
                    SELECT p.partner_code,
                           p.tax_id,
                           p.partner_name,
                           coalesce(vm.address, 'Khu công nghiệp ' || p.province || ' (mô phỏng)'),
                           coalesce(vm.bank_account, CASE WHEN p.partner_type = 'VENDOR' THEN '99' || lpad(p.partner_key::VARCHAR, 10, '0') ELSE '' END)
                    FROM dim_partner p
                    LEFT JOIN vendor_meta vm ON vm.vendor_code = p.partner_code""").fetchall()
            }
        else:
            self.partners = {
                code: (
                    tax,
                    name,
                    f'Khu công nghiệp {prov} (mô phỏng)',
                    f'99{pkey:010d}' if ptype == 'VENDOR' else '',
                )
                for code, tax, name, prov, pkey, ptype in self.db.execute(
                    'SELECT partner_code, tax_id, partner_name, province, partner_key, partner_type FROM dim_partner'
                ).fetchall()
            }

        a3 = self.root / 'a3'
        a3.mkdir(exist_ok=True)
        pack = {
            'pack_version': 1,
            'simulated': True,
            'profile': {
                'tax_code': self.info['tax_id'],
                'legal_name': self.info['name'],
                'registered_address': self.address,
                'industry': ['Phân phối thiết bị công nghệ và dịch vụ kỹ thuật'],
                'vat_method': 'DEDUCTION',
                'filing_period': 'MONTH',
                'fiscal_year_end_month': 12,
            },
            'thresholds': {},
            'policies': [
                {
                    'id': 'WELFARE_REVIEW',
                    'flag': 'Kiểm tra định mức chi phúc lợi / tiếp khách và chứng từ phê duyệt nội bộ',
                    'description_contains': ['phúc lợi', 'tiếp khách', 'rượu', 'golf', 'spa'],
                }
            ],
            'reference_lists': [],
            'bank_formats': [
                {
                    'name': 'MPX10',
                    'columns': {
                        'date': 'Ngày',
                        'debit': 'Ghi Nợ',
                        'credit': 'Ghi Có',
                        'description': 'Nội dung',
                        'counterparty_account': 'Tài khoản đối tác',
                        'counterparty_name': 'Tên đối tác',
                    },
                    'date_format': '%Y-%m-%d',
                    'thousands': '',
                    'decimal': '.',
                    'delimiter': ',',
                }
            ],
        }
        (a3 / 'pack.json').write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding='utf-8')

        has_ap_lines = 'ap_bill_line' in self.tables
        for role, table, day, partner, description in [
            ('sales', 'ar_invoice', 'issue_date', 'customer_code', 'description'),
            ('purchase', 'ap_bill', 'bill_date', 'vendor_code', 'description'),
        ]:
            idcol = 'invoice_id' if role == 'sales' else 'bill_id'
            cur = self.db.execute(
                f'SELECT {idcol}, {day}, {partner}, subtotal::BIGINT, vat_amount::BIGINT, total_amount::BIGINT, {description}, pay_label '
                f'FROM {table} ORDER BY {day}, {idcol}'
            )
            z = None
            last = None
            part = 0
            count = 0
            try:
                while rows := cur.fetchmany(3000):
                    identifiers = ','.join(str(r[0]) for r in rows)
                    line_cursor = self.db.cursor()
                    if role == 'sales':
                        raw_detail = line_cursor.execute(f"""
                            SELECT l.invoice_id, i.item_name, i.unit, l.quantity::INT, l.net_amount::BIGINT
                            FROM ar_invoice_line l
                            JOIN dim_item i USING(item_code)
                            WHERE l.invoice_id IN ({identifiers})
                            ORDER BY l.invoice_id, i.item_code, l.quantity, l.net_amount""").fetchall()
                    elif has_ap_lines:
                        raw_detail = line_cursor.execute(f"""
                            SELECT bill_id, item_name, unit, quantity::INT, net_amount::BIGINT
                            FROM ap_bill_line
                            WHERE bill_id IN ({identifiers})
                            ORDER BY bill_id, line_no""").fetchall()
                    else:
                        raw_detail = line_cursor.execute(f"""
                            SELECT p.bill_id, i.item_name, i.unit, p.quantity::INT, p.cost::BIGINT
                            FROM purchase_events p
                            JOIN dim_item i USING(item_code)
                            WHERE p.bill_id IN ({identifiers})
                            ORDER BY p.bill_id""").fetchall()
                    line_cursor.close()

                    grouped_raw: dict[int, list[tuple[str, str, int, int]]] = {}
                    for doc_id, iname, iunit, iqty, inet in raw_detail:
                        grouped_raw.setdefault(int(doc_id), []).append((iname, iunit, int(iqty), int(inet)))

                    for row in rows:
                        doc_id = int(row[0])
                        fallback_lines = [(str(row[6]), 'gói', 1, int(row[3]))]
                        clean_lines = _quantize_xml_lines(grouped_raw.get(doc_id) or fallback_lines)
                        month = str(row[1])[:7]
                        if month != last or count == 3000:
                            if z:
                                z.close()
                            part = part + 1 if month == last else 1
                            last = month
                            count = 0
                            dest = a3 / month / f'{role}_{part:03}.zip'
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            z = zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED, compresslevel=3)
                        name = f'{role}_{doc_id:08}.xml'
                        info = zipfile.ZipInfo(name, date_time=(2023, 1, 1, 0, 0, 0))
                        info.compress_type = zipfile.ZIP_DEFLATED
                        z.writestr(info, self.xml(row, role, clean_lines))
                        count += 1
                print(f'A3 {role} XML complete', flush=True)
            finally:
                if z:
                    z.close()

        # Export bank statements & portal purchase lists for all months covered by A3 invoices/payments
        vmeta_join = 'LEFT JOIN vendor_meta vm ON vm.vendor_code = p.partner_code' if 'vendor_meta' in self.tables else ''
        acct_expr = (
            "coalesce(vm.bank_account, CASE WHEN p.partner_key IS NOT NULL THEN '99' || lpad(p.partner_key::VARCHAR, 10, '0') ELSE '' END)"
            if 'vendor_meta' in self.tables
            else "CASE WHEN p.partner_key IS NOT NULL THEN '99' || lpad(p.partner_key::VARCHAR, 10, '0') ELSE '' END"
        )
        self.db.execute("""CREATE OR REPLACE TEMP TABLE a3_relevant_bank_journals AS
            SELECT DISTINCT journal_id
            FROM warehouse.main.ap_payment
            WHERE method = 'BANK' AND bill_id IN (SELECT bill_id FROM ap_bill) AND journal_id <> 'DUP-PAY'
            UNION
            SELECT DISTINCT journal_id
            FROM warehouse.main.ar_receipt
            WHERE invoice_id IN (SELECT invoice_id FROM ar_invoice)""")

        a3_months = {
            r[0]
            for r in self.db.execute("""
                SELECT DISTINCT strftime(bill_date, '%Y-%m') m FROM ap_bill
                UNION
                SELECT DISTINCT strftime(issue_date, '%Y-%m') m FROM ar_invoice
                UNION
                SELECT DISTINCT strftime(b.date, '%Y-%m') m FROM bank b JOIN a3_relevant_bank_journals r USING(journal_id)
                ORDER BY 1""").fetchall()
        }
        for month in sorted(a3_months):
            self.csv(
                Path(f'a3/{month}/bank.csv'),
                f"""SELECT b.date "Ngày",
                           greatest(-b.net, 0)::BIGINT "Ghi Nợ",
                           greatest(b.net, 0)::BIGINT "Ghi Có",
                           b.description "Nội dung",
                           {acct_expr} "Tài khoản đối tác",
                           coalesce(p.partner_name, '') "Tên đối tác",
                           b.bank_id "Mã giao dịch"
                    FROM bank b
                    JOIN a3_relevant_bank_journals rel USING(journal_id)
                    LEFT JOIN dim_partner p USING(partner_code)
                    {vmeta_join}
                    WHERE strftime(b.date, '%Y-%m') = {q(month)}
                    ORDER BY b.date, b.bank_id""",
            )
            self.csv(
                Path(f'a3/{month}/purchase_portal.csv'),
                f"""SELECT p.tax_id "MST người bán",
                           '1' "Ký hiệu mẫu số",
                           'K' || strftime(b.bill_date, '%y') || 'TMP' "Ký hiệu hóa đơn",
                           lpad(b.bill_id::VARCHAR, 8, '0') "Số hóa đơn",
                           b.bill_date "Ngày lập",
                           b.vat_amount::BIGINT "Tổng tiền thuế",
                           b.total_amount::BIGINT "Tổng tiền thanh toán"
                    FROM ap_bill b
                    JOIN dim_partner p ON p.partner_code = b.vendor_code
                    WHERE strftime(b.bill_date, '%Y-%m') = {q(month)}
                    ORDER BY b.bill_id""",
            )

        for name in ('ar_invoice', 'ap_bill', 'a3_relevant_bank_journals'):
            self.db.execute('DROP TABLE temp.main.' + name)

    def finish(self):
        self.manifest = []
        for p in sorted(self.root.rglob('*')):
            if not p.is_file() or p.name == 'manifest.json':
                continue
            h = hashlib.sha256()
            with p.open('rb') as f:
                for block in iter(lambda: f.read(1024 * 1024), b''):
                    h.update(block)
            self.manifest.append(
                {
                    'file': p.relative_to(self.root).as_posix(),
                    'bytes': p.stat().st_size,
                    'sha256': h.hexdigest(),
                }
            )
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest, indent=2), encoding='utf-8')


def export_agent1(folder: str | Path) -> None:
    e = Export(folder)
    try:
        e.prepare()
        e.a1()
        e.finish()
    finally:
        e.db.close()


def export_agent2(folder: str | Path, tenant_id: str = 'demo') -> None:
    e = Export(folder, tenant_id=tenant_id)
    try:
        e.prepare()
        e.a2()
        e.finish()
    finally:
        e.db.close()


def export_agent3(folder: str | Path) -> None:
    e = Export(folder)
    try:
        e.prepare()
        e.a3()
        e.finish()
    finally:
        e.db.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder')
    p.add_argument('--agent', choices=['a1', 'a2', 'a3', 'all'], default='all')
    p.add_argument('--tenant-id', default='demo')
    a = p.parse_args()
    e = Export(a.folder, tenant_id=a.tenant_id)
    e.prepare()
    try:
        for agent in ['a1', 'a2', 'a3'] if a.agent == 'all' else [a.agent]:
            getattr(e, agent)()
        e.finish()
    finally:
        e.db.close()


if __name__ == '__main__':
    main()
