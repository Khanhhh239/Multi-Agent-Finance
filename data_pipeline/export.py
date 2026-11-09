"""Stream exact common-source projections. Never changes active agent data."""
import argparse
import csv
import hashlib
import json
import zipfile
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

import duckdb


def q(s): return "'"+str(s).replace("'","''")+"'"

def a2_account(column):
    # Explicit chart mapping; retain detailed source accounts in journal_lines.
    return '(CASE '+ ' '.join(f"WHEN {column} LIKE '{prefix}%' THEN '{prefix}'" for prefix in
        ('112','111','511','214','334','3331'))+f' ELSE {column} END)'


class Export:
    def __init__(self,folder):
        self.folder=Path(folder).resolve()
        self.root=self.folder/'inputs'
        self.root.mkdir(exist_ok=True)
        self.db=duckdb.connect(str(self.folder/'warehouse.duckdb'),read_only=True)
        self.db.execute("SET memory_limit='1200MB'; SET threads=2; SET preserve_insertion_order=false")
        self.info=dict(self.db.execute('SELECT * FROM company_info').fetchall())
        self.manifest=[]

    def csv(self,path,sql):
        dest=self.root/path;dest.parent.mkdir(parents=True,exist_ok=True)
        self.db.execute(f'COPY ({sql}) TO {q(dest)} (HEADER, DELIMITER \',\')')
        print(path,flush=True)

    def prepare(self):
        # One bank movement per journal/account, including opening balance movements explicitly.
        self.db.execute("""CREATE TEMP VIEW bank AS SELECT journal_id||':'||account_code bank_id,journal_id,
            posting_date date,account_code account,sum(net_debit)::BIGINT net,
            max(created_at)::DATE known_at, min(partner_code) partner_code,min(description) description
            FROM v_gl WHERE account_code LIKE '112%' GROUP BY journal_id,posting_date,account_code
            HAVING sum(net_debit)<>0""")
        self.db.execute("""CREATE TEMP VIEW monthly_bank AS SELECT account,date_trunc('month',date)::DATE start_date,
            least(last_day(date),DATE '2026-10-14') end_date,sum(net)::BIGINT movement FROM bank GROUP BY ALL""")

    def a1(self):
        # A1 cannot represent credit notes or receipts before invoice issue. Keep exact
        # source values by selecting supported invoices, instead of rewriting dates/amounts.
        self.db.execute('''CREATE TEMP TABLE ar_invoice AS SELECT i.* FROM warehouse.main.ar_invoice i
            WHERE NOT EXISTS (SELECT 1 FROM warehouse.main.ar_adjustment a WHERE a.invoice_id=i.invoice_id)
            AND NOT EXISTS (SELECT 1 FROM warehouse.main.ar_receipt r WHERE r.invoice_id=i.invoice_id AND r.receipt_date<i.issue_date)
            ORDER BY issue_date DESC,invoice_id DESC LIMIT 50000''')
        self.db.execute('CREATE TEMP TABLE ar_adjustment AS SELECT a.* FROM warehouse.main.ar_adjustment a JOIN ar_invoice i USING(invoice_id)')
        self.db.execute('CREATE TEMP TABLE ar_receipt AS SELECT r.* FROM warehouse.main.ar_receipt r JOIN ar_invoice i USING(invoice_id)')
        bank_start=self.db.execute("SELECT date_trunc('month',min(issue_date)-5)::DATE FROM ar_invoice").fetchone()[0]
        months=[r[0] for r in self.db.execute("SELECT DISTINCT strftime(issue_date,'%Y-%m') FROM ar_invoice ORDER BY 1").fetchall()]
        # Preserve original gross; A1 lacks credit-note input. Reconciled net claim is an explicit adapter projection.
        self.csv(Path('a1/invoice_adjustments_reference.csv'),"SELECT * FROM ar_adjustment ORDER BY adjustment_id")
        self.csv(Path('a1/prepayments_reference.csv'),"""SELECT r.*,i.issue_date FROM ar_receipt r JOIN ar_invoice i USING(invoice_id)
            WHERE r.receipt_date<i.issue_date ORDER BY receipt_id""")
        for month in months:
            where=f"strftime(i.issue_date,'%Y-%m')={q(month)}"
            self.csv(Path(f'a1/{month}/01_invoices.csv'),f"""SELECT 'INV-'||i.invoice_id invoice_id,i.customer_code customer_id,
                i.issue_date,i.due_date,(i.total_amount-coalesce(a.adj,0))::BIGINT amount,'VND' currency,
                greatest(i.issue_date,coalesce(a.adjusted_on,i.issue_date)) known_at
                FROM ar_invoice i LEFT JOIN (SELECT invoice_id,sum(total_amount) adj,max(adjustment_date) adjusted_on
                     FROM ar_adjustment GROUP BY invoice_id) a USING(invoice_id) WHERE {where} ORDER BY i.invoice_id""")
            self.csv(Path(f'a1/{month}/03_payments.csv'),f"""SELECT 'REC-'||r.receipt_id payment_id,'INV-'||r.invoice_id invoice_id,
                greatest(r.receipt_date,i.issue_date) payment_date,r.amount::BIGINT amount,
                CASE WHEN r.receipt_date>=i.issue_date THEN r.journal_id||':'||r.cash_account ELSE '' END bank_id,
                greatest(r.receipt_date,i.issue_date) known_at FROM ar_receipt r JOIN ar_invoice i USING(invoice_id)
                WHERE {where} ORDER BY r.receipt_id""")
            self.csv(Path(f'a1/{month}/06_actions.csv'),f"""SELECT 'CONTACT-'||i.invoice_id event_id,'INV-'||i.invoice_id invoice_id,
                least(i.due_date+7,DATE '2026-10-14') date,'contact' kind,
                least(i.due_date+7,DATE '2026-10-14') known_at
                FROM ar_invoice i WHERE {where} AND i.due_date<DATE '2026-10-14' AND i.invoice_id%101=0 ORDER BY i.invoice_id""")
        for month, in self.db.execute(f"SELECT DISTINCT strftime(date,'%Y-%m') FROM bank WHERE date>={q(bank_start)}::DATE ORDER BY 1").fetchall():
            self.csv(Path(f'a1/{month}/02_bank.csv'),f"""SELECT bank_id,account,date,CASE WHEN net>0 THEN 'in' ELSE 'out' END direction,
                abs(net) amount,greatest(date,known_at) known_at,'other' component FROM bank
                WHERE strftime(date,'%Y-%m')={q(month)} ORDER BY date,bank_id""")
        self.csv(Path('a1/04_statements.csv'),f"""SELECT * FROM (SELECT account||':'||start_date statement_id,account,start_date,end_date,
            (sum(movement) OVER(PARTITION BY account ORDER BY start_date)-movement)::BIGINT opening_balance,
            sum(movement) OVER(PARTITION BY account ORDER BY start_date)::BIGINT closing_balance,
            DATE '2026-10-14' known_at FROM monthly_bank) WHERE start_date>={q(bank_start)}::DATE ORDER BY account,start_date""")
        self.csv(Path('a1/05_outflows.csv'),"""SELECT 'SCHEDULE-AP-'||bill_id expense_id,due_date date,
            (total_amount-coalesce(p.paid,0))::BIGINT amount,'supplier' category,DATE '2026-10-14' known_at
            FROM ap_bill LEFT JOIN (SELECT bill_id,sum(amount) paid FROM ap_payment GROUP BY bill_id) p USING(bill_id)
            WHERE due_date>DATE '2026-10-14' AND total_amount>coalesce(p.paid,0) ORDER BY bill_id""")
        for name in ('ar_invoice','ar_adjustment','ar_receipt'):self.db.execute('DROP TABLE temp.main.'+name)

    def a2(self):
        self.db.execute("""CREATE TEMP TABLE journal_totals AS SELECT journal_id,posting_date,
            sum(debit_amount)::BIGINT amount,arg_max(account_code,debit_amount) debit_account,
            arg_max(account_code,credit_amount) credit_account,
            min(partner_code) partner_code,min(employee_code) employee_code,
            sum(CASE WHEN account_code LIKE '133%' THEN net_debit ELSE 0 END)::BIGINT input_vat,
            sum(CASE WHEN account_code LIKE '3331%' THEN -net_debit ELSE 0 END)::BIGINT output_vat,
            sum(CASE WHEN account_code='154' THEN debit_amount ELSE 0 END)::BIGINT production_cost
            FROM v_gl WHERE NOT is_closing AND year_no>=2023 GROUP BY journal_id,posting_date""")
        self.db.execute("""CREATE TEMP TABLE transaction_projection AS SELECT j.journal_id transaction_id,
            strftime(greatest(j.created_at,j.posting_date::TIMESTAMP)+INTERVAL 10 MINUTE,'%Y-%m-%dT%H:%M:%S')||'+07:00' posted_at,
            strftime(j.created_at,'%Y-%m-%dT%H:%M:%S')||'+07:00' created_at,
            strftime(j.created_at+INTERVAL 5 MINUTE,'%Y-%m-%dT%H:%M:%S')||'+07:00' approved_at,
            CASE j.doc_type WHEN 'SALES_INVOICE' THEN 'sales_invoice' WHEN 'RECEIPT' THEN 'customer_receipt'
              WHEN 'PAYMENT' THEN 'vendor_payment' WHEN 'PURCHASE_INVOICE' THEN 'stock_purchase'
              WHEN 'COGS' THEN 'cogs' WHEN 'PAYROLL_PAYMENT' THEN 'payroll' WHEN 'DEPRECIATION' THEN 'depreciation'
              WHEN 'EXPENSE' THEN 'rent' WHEN 'VAT_OFFSET' THEN 'vat_offset' ELSE 'adjustment' END txn_type,
            t.amount amount_vnd,20000000::BIGINT approval_limit_vnd,'E000001' creator_id,'E000002' approver_id,
            1 is_financial_entry,t.debit_account,t.credit_account,t.debit_account||'/'||t.credit_account journal_signature,
            txn_type accounting_purpose,greatest(t.input_vat,0) recognised_input_vat_vnd,
            greatest(t.output_vat,0) recognised_output_vat_vnd,0::BIGINT writeoff_provision_vnd,t.production_cost production_cost_vnd,
            'MPX10' company_id,CASE WHEN t.partner_code LIKE 'V%' THEN t.partner_code ELSE '' END vendor_id,
            coalesce(t.employee_code,'') employee_id,CASE WHEN t.partner_code LIKE 'C%' THEN t.partner_code ELSE '' END customer_id,
            CASE WHEN t.debit_account LIKE '112%' OR t.credit_account LIKE '112%' THEN 'bank' ELSE 'journal' END payment_channel,
            0 support_doc_count,0 goods_receipt_verified,0 evidence_on_file,
            j.journal_id journal_document_id,'' linked_document_id,
            'Dữ liệu mô phỏng; định khoản đầy đủ trong journal_lines.csv' business_purpose
            FROM gl_journal j JOIN journal_totals t USING(journal_id) WHERE t.amount>0
            AND j.doc_type IN ('SALES_INVOICE','RECEIPT','PAYMENT','PAYROLL_PAYMENT','DEPRECIATION','EXPENSE','VAT_OFFSET')
            ORDER BY j.posting_date DESC,j.journal_id DESC LIMIT 10000""")
        self.db.execute(f'UPDATE transaction_projection SET debit_account={a2_account("debit_account")},credit_account={a2_account("credit_account")}')
        self.db.execute(f'''UPDATE transaction_projection SET journal_signature=p.signature FROM (
            WITH accounts AS (SELECT DISTINCT journal_id,{a2_account('account_code')} account_code,debit_amount>0 debit FROM v_gl
                WHERE journal_id IN (SELECT transaction_id FROM transaction_projection))
            SELECT d.journal_id,string_agg(DISTINCT d.account_code||'/'||c.account_code,';' ORDER BY d.account_code||'/'||c.account_code) signature
            FROM accounts d JOIN accounts c USING(journal_id) WHERE d.debit AND NOT c.debit GROUP BY d.journal_id
            ) p WHERE transaction_id=p.journal_id''')
        self.csv(Path('a2/journal_documents.csv'),"""SELECT journal_id document_id,journal_id transaction_id,'MPX10' company_id,posting_date,doc_type,
            description,(SELECT t.accounting_purpose FROM transaction_projection t WHERE t.transaction_id=gl_journal.journal_id) purpose,
            (SELECT t.posted_at FROM transaction_projection t WHERE t.transaction_id=gl_journal.journal_id) posted_at,
            created_by,created_at FROM gl_journal WHERE journal_id IN (SELECT transaction_id FROM transaction_projection)
            ORDER BY posting_date,journal_id""")
        self.csv(Path('a2/journal_lines.csv'),f"""SELECT entry_id line_id,journal_id document_id,journal_id transaction_id,'MPX10' company_id,
            {a2_account('account_code')} account_code,account_code source_account_code,debit_amount::BIGINT debit_vnd,credit_amount::BIGINT credit_vnd,partner_code,item_code,branch_code,
            posting_date,(SELECT t.posted_at FROM transaction_projection t WHERE t.transaction_id=v_gl.journal_id) posted_at
            FROM v_gl WHERE journal_id IN (SELECT transaction_id FROM transaction_projection) ORDER BY entry_id""")
        self.csv(Path('a2/companies.csv'),f"SELECT 'MPX10' company_id,{q(self.info['name'])} name,'TT133' accounting_framework,20000000 approval_limit_vnd,0 saturday_operations")
        self.csv(Path('a2/employees.csv'),"""SELECT employee_code employee_id,'MPX10' company_id,employee_name full_name,
            department_code,branch_code,'' bank_account,'' phone,'staff' role,base_salary::BIGINT monthly_salary_vnd,hire_date,coalesce(leave_date::VARCHAR,'') termination_date,
            hire_date::VARCHAR||'T00:00:00+07:00' hired_at,hire_date::VARCHAR||'T00:00:00+07:00' recorded_at,
            1 contract_on_file,1 leave_request_required,0 self_approval_allowed,0 self_approval_limit_vnd,20000000 approval_limit_vnd
            FROM dim_employee ORDER BY employee_code""")
        self.csv(Path('a2/vendors.csv'),"""SELECT partner_code vendor_id,'MPX10' company_id,partner_name name,tax_id,
            '2022-01-01T00:00:00+07:00' recorded_at,'2020-01-01T00:00:00+07:00' registered_at,
            '2022-01-01T00:00:00+07:00' onboarded_at,'' related_party_disclosed_at,
            '' phone,'99'||lpad(partner_key::VARCHAR,10,'0') bank_account FROM dim_partner WHERE partner_type='VENDOR' ORDER BY partner_code""")
        self.csv(Path('a2/customers.csv'),"""SELECT partner_code customer_id,'MPX10' company_id,partner_name name,tax_id,
            '2022-01-01T00:00:00+07:00' recorded_at FROM dim_partner WHERE partner_type='CUSTOMER' ORDER BY partner_code""")
        self.csv(Path('a2/calendar.csv'),"SELECT calendar_date date,'Ngày nghỉ mô phỏng' name FROM dim_period WHERE NOT is_business_day ORDER BY calendar_date")
        self.csv(Path('a2/transactions_full.csv'),"SELECT * FROM transaction_projection ORDER BY posted_at,transaction_id")
        # Web-safe chunks are transport files; NOT sequential replacement imports.
        cur=self.db.execute('SELECT * FROM transaction_projection ORDER BY posted_at,transaction_id')
        header=[d[0] for d in cur.description]; index=0
        while rows:=cur.fetchmany(10000):
            index+=1;path=self.root/f'a2/chunks/transactions_{index:04}.csv';path.parent.mkdir(exist_ok=True)
            with path.open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.writer(f);w.writerow(header);w.writerows(rows)
        print(f'A2: {index} bounded chunks; full dataset retained',flush=True)

    def xml(self,row,role,lines):
        identifier,day,partner,net,vat,total,description=row
        own=(self.info['tax_id'],self.info['name']);other=self.partners[partner]
        seller,buyer=(own,other) if role=='sales' else (other,own)
        symbol=f'K{day.year%100}TMP'
        def party(tag,p): return f'<{tag}><Ten>{escape(p[1])}</Ten><MST>{p[0]}</MST><DChi>Địa chỉ mô phỏng</DChi></{tag}>'
        return (f'<?xml version="1.0" encoding="UTF-8"?><HDon><DLHDon Id="{role}{identifier}"><TTChung><PBan>2.1.0</PBan>'
          f'<THDon>Hóa đơn mô phỏng, không có giá trị pháp lý</THDon><KHMSHDon>1</KHMSHDon><KHHDon>{symbol}</KHHDon>'
          f'<SHDon>{identifier:08}</SHDon><NLap>{day}</NLap><DVTTe>VND</DVTTe><HTTToan>CK</HTTToan></TTChung><NDHDon>'
          +party('NBan',seller)+party('NMua',buyer)+'<DSHHDVu>'+''.join(
          f'<HHDVu><TChat>1</TChat><STT>{n}</STT><THHDVu>{escape(str(desc))}</THHDVu><DVTinh>đơn vị</DVTinh>'
          f'<SLuong>{qty}</SLuong><DGia>{price}</DGia><ThTien>{value}</ThTien><TSuat>10%</TSuat></HHDVu>'
          for n,(desc,qty,price,value) in enumerate(lines,1))+'</DSHHDVu>'+
          f'<TToan><TgTCThue>{net}</TgTCThue><TgTThue>{vat}</TgTThue><TgTTTBSo>{total}</TgTTTBSo></TToan></NDHDon></DLHDon>'
          '<DSCKS><NBan/></DSCKS></HDon>').encode('utf-8')

    def a3(self):
        self.db.execute('''CREATE TEMP TABLE ar_invoice AS SELECT i.* FROM warehouse.main.ar_invoice i
            WHERE NOT EXISTS (SELECT 1 FROM warehouse.main.ar_adjustment a WHERE a.invoice_id=i.invoice_id)
            ORDER BY issue_date DESC,invoice_id DESC LIMIT 2500''')
        self.db.execute('CREATE TEMP TABLE ap_bill AS SELECT * FROM warehouse.main.ap_bill ORDER BY bill_date DESC,bill_id DESC LIMIT 2500')
        self.partners={code:(tax,name) for code,tax,name in self.db.execute('SELECT partner_code,tax_id,partner_name FROM dim_partner').fetchall()}
        a3=self.root/'a3';a3.mkdir(exist_ok=True)
        pack={'pack_version':1,'simulated':True,'profile':{'tax_code':self.info['tax_id'],'legal_name':self.info['name'],
              'registered_address':'Địa chỉ mô phỏng','industry':['Phân phối thiết bị và dịch vụ kỹ thuật'],
              'vat_method':'DEDUCTION','filing_period':'MONTH','fiscal_year_end_month':12},'thresholds':{},'policies':[],
              'reference_lists':[],'bank_formats':[{'name':'MPX10','columns':{'date':'Ngày','debit':'Ghi Nợ','credit':'Ghi Có',
              'description':'Nội dung','counterparty_account':'Tài khoản đối tác','counterparty_name':'Tên đối tác'},
              'date_format':'%Y-%m-%d','thousands':'','decimal':'.','delimiter':','}]}
        (a3/'pack.json').write_text(json.dumps(pack,ensure_ascii=False,indent=2),encoding='utf-8')
        for role,table,day,partner,description in [('sales','ar_invoice','issue_date','customer_code','description'),
                                                   ('purchase','ap_bill','bill_date','vendor_code','description')]:
            idcol='invoice_id' if role=='sales' else 'bill_id'
            cur=self.db.execute(f'SELECT {idcol},{day},{partner},subtotal::BIGINT,vat_amount::BIGINT,total_amount::BIGINT,{description} FROM {table} ORDER BY {day},{idcol}')
            z=None;last=None;part=0;count=0
            try:
                while rows:=cur.fetchmany(3000):
                    identifiers=','.join(str(r[0]) for r in rows)
                    line_cursor=self.db.cursor()
                    if role=='sales':
                        detail=line_cursor.execute(f'''SELECT invoice_id,item_code,quantity,unit_price::BIGINT,net_amount::BIGINT
                            FROM ar_invoice_line WHERE invoice_id IN ({identifiers}) ORDER BY invoice_id,item_code,quantity,net_amount''').fetchall()
                    else:
                        detail=[(doc,item,qty,Decimal(cost)/Decimal(qty),cost) for doc,item,qty,cost in
                            line_cursor.execute(f'''SELECT bill_id,item_code,quantity,cost FROM purchase_events
                                WHERE bill_id IN ({identifiers}) ORDER BY bill_id''').fetchall()]
                    line_cursor.close()
                    detail_map={}
                    for doc,*line in detail:detail_map.setdefault(doc,[]).append(line)
                    for row in rows:
                        month=str(row[1])[:7]
                        if month!=last or count==3000:
                            if z:z.close()
                            part=part+1 if month==last else 1;last=month;count=0
                            dest=a3/month/f'{role}_{part:03}.zip';dest.parent.mkdir(exist_ok=True)
                            z=zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=3)
                        name=f'{role}_{row[0]:08}.xml';info=zipfile.ZipInfo(name,date_time=(2023,1,1,0,0,0))
                        info.compress_type=zipfile.ZIP_DEFLATED
                        z.writestr(info,self.xml(row,role,detail_map[row[0]]));count+=1
                print(f'A3 {role} XML complete',flush=True)
            finally:
                if z:z.close()
        for month, in self.db.execute("SELECT DISTINCT strftime(date,'%Y-%m') FROM bank ORDER BY 1").fetchall():
            self.csv(Path(f'a3/{month}/bank.csv'),f"""SELECT b.date "Ngày",greatest(-net,0) "Ghi Nợ",greatest(net,0) "Ghi Có",
                b.description "Nội dung",CASE WHEN p.partner_key IS NOT NULL THEN '99'||lpad(p.partner_key::VARCHAR,10,'0') ELSE '' END "Tài khoản đối tác",
                coalesce(p.partner_name,'') "Tên đối tác",b.bank_id "Mã giao dịch" FROM bank b LEFT JOIN dim_partner p USING(partner_code)
                WHERE strftime(b.date,'%Y-%m')={q(month)} AND b.journal_id IN (
                    SELECT journal_id FROM ap_payment WHERE bill_id IN (SELECT bill_id FROM ap_bill)
                    UNION ALL SELECT journal_id FROM ar_receipt WHERE invoice_id IN (SELECT invoice_id FROM ar_invoice))
                ORDER BY b.date,b.bank_id""")
            self.csv(Path(f'a3/{month}/purchase_portal.csv'),f"""SELECT p.tax_id "MST người bán",'1' "Ký hiệu mẫu số",
                'K'||strftime(b.bill_date,'%y')||'TMP' "Ký hiệu hóa đơn",lpad(b.bill_id::VARCHAR,8,'0') "Số hóa đơn",
                b.bill_date "Ngày lập",b.vat_amount::BIGINT "Tổng tiền thuế",b.total_amount::BIGINT "Tổng tiền thanh toán"
                FROM ap_bill b JOIN dim_partner p ON p.partner_code=b.vendor_code WHERE strftime(b.bill_date,'%Y-%m')={q(month)} ORDER BY b.bill_id""")
        for name in ('ar_invoice','ap_bill'):self.db.execute('DROP TABLE temp.main.'+name)

    def finish(self):
        for p in sorted(self.root.rglob('*')):
            if not p.is_file() or p.name=='manifest.json':continue
            h=hashlib.sha256()
            with p.open('rb') as f:
                for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
            self.manifest.append({'file':p.relative_to(self.root).as_posix(),'bytes':p.stat().st_size,'sha256':h.hexdigest()})
        (self.root/'manifest.json').write_text(json.dumps(self.manifest,indent=2),encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');p.add_argument('--agent',choices=['a1','a2','a3','all'],default='all');a=p.parse_args()
    e=Export(a.folder);e.prepare()
    try:
        for agent in ['a1','a2','a3'] if a.agent=='all' else [a.agent]:getattr(e,agent)()
        e.finish()
    finally:e.db.close()
