"""Generate a small, balanced TT133-inspired ledger in DuckDB.

Run: python generate_data.py --output ai_fin.duckdb --months 6
"""
from __future__ import annotations
import argparse
from datetime import date, datetime
from decimal import Decimal
import calendar
import duckdb

ACCOUNTS = [
    ('111','Tiền mặt','Tài sản','D'),('112','Tiền gửi ngân hàng','Tài sản','D'),
    ('131','Phải thu khách hàng','Tài sản','D'),('1331','Thuế GTGT được khấu trừ','Tài sản','D'),
    ('152','Nguyên liệu, vật liệu','Tài sản','D'),('156','Hàng hóa','Tài sản','D'),
    ('211','Tài sản cố định hữu hình','Tài sản','D'),('214','Hao mòn TSCĐ','Tài sản','C'),
    ('331','Phải trả người bán','Nợ phải trả','C'),('3331','Thuế GTGT phải nộp','Nợ phải trả','C'),
    ('3334','Thuế TNDN','Nợ phải trả','C'),('334','Phải trả người lao động','Nợ phải trả','C'),
    ('338','Phải trả, phải nộp khác','Nợ phải trả','C'),('341','Vay và nợ thuê tài chính','Nợ phải trả','C'),
    ('411','Vốn đầu tư của chủ sở hữu','Vốn chủ sở hữu','C'),('421','Lợi nhuận sau thuế chưa phân phối','Vốn chủ sở hữu','C'),
    ('511','Doanh thu bán hàng và cung cấp dịch vụ','Doanh thu','C'),('515','Doanh thu hoạt động tài chính','Doanh thu','C'),
    ('521','Các khoản giảm trừ doanh thu','Doanh thu','D'),('632','Giá vốn hàng bán','Chi phí','D'),
    ('635','Chi phí tài chính','Chi phí','D'),('641','Chi phí bán hàng','Chi phí','D'),
    ('642','Chi phí quản lý doanh nghiệp','Chi phí','D'),('811','Chi phí khác','Chi phí','D'),
    ('821','Chi phí thuế TNDN','Chi phí','D'),('911','Xác định kết quả kinh doanh','Chi phí','D'),
]

def months(n):
    end = date.today().replace(day=1)
    out=[]
    for i in range(n-1,-1,-1):
        y, m = end.year, end.month-i
        while m <= 0: y, m = y-1, m+12
        out.append(date(y,m,1))
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output',default='ai_fin.duckdb'); ap.add_argument('--months',type=int,default=6); args=ap.parse_args()
    if args.months < 6: raise SystemExit('--months must be >= 6')
    con=duckdb.connect(args.output)
    con.execute("CREATE OR REPLACE TABLE dim_account(account_key BIGINT PRIMARY KEY, account_code VARCHAR UNIQUE, account_name VARCHAR, account_type VARCHAR, normal_balance VARCHAR, parent_account_code VARCHAR, is_postable BOOLEAN, effective_from DATE, effective_to DATE)")
    con.execute("CREATE OR REPLACE TABLE dim_partner(partner_key BIGINT PRIMARY KEY, partner_code VARCHAR UNIQUE, partner_name VARCHAR, partner_type VARCHAR, tax_id VARCHAR, is_active BOOLEAN)")
    con.execute("CREATE OR REPLACE TABLE dim_period(period_key INTEGER PRIMARY KEY, calendar_date DATE UNIQUE, day_of_month SMALLINT, month_no SMALLINT, quarter_no SMALLINT, year_no SMALLINT, month_start_date DATE, month_end_date DATE)")
    con.execute("CREATE OR REPLACE TABLE dim_item(item_key BIGINT PRIMARY KEY, item_code VARCHAR UNIQUE, item_name VARCHAR, item_type VARCHAR, unit VARCHAR, standard_cost DECIMAL(18,2), is_active BOOLEAN)")
    con.execute("CREATE OR REPLACE TABLE gl_entry(entry_id BIGINT, journal_id VARCHAR, entry_no INTEGER, posting_date DATE, period_key INTEGER, account_key BIGINT, partner_key BIGINT, item_key BIGINT, description VARCHAR, debit_amount DECIMAL(18,2), credit_amount DECIMAL(18,2), currency_code VARCHAR, source_document_type VARCHAR, source_document_no VARCHAR, created_at TIMESTAMP)")
    con.executemany("INSERT INTO dim_account VALUES (?,?,?,?,?,?,?,?,?)", [(i+1,*a,None,True,date(2020,1,1),None) for i,a in enumerate(ACCOUNTS)])
    partners=[(1,'C001','Công ty An Phú','CUSTOMER','0100000001',True),(2,'C002','Công ty Bình Minh','CUSTOMER','0100000002',True),(3,'V001','Nhà cung cấp Sao Việt','VENDOR','0100000003',True),(4,'E001','Nguyễn Văn An','EMPLOYEE',None,True)]
    con.executemany("INSERT INTO dim_partner VALUES (?,?,?,?,?,?)",partners)
    con.executemany("INSERT INTO dim_item VALUES (?,?,?,?,?,?,?)",[(1,'SP001','Sản phẩm A','PRODUCT','cái',Decimal('100000'),True),(2,'DV001','Dịch vụ tư vấn','SERVICE','giờ',Decimal('300000'),True)])
    for d in months(args.months):
        last=calendar.monthrange(d.year,d.month)[1]
        for day in range(1,last+1):
            x=date(d.year,d.month,day); con.execute("INSERT INTO dim_period VALUES (?,?,?,?,?,?,?,?)",(int(x.strftime('%Y%m%d')),x,x.day,x.month,(x.month-1)//3+1,x.year,d,x.replace(day=last)))
    pkey_of={p[1]:p[0] for p in partners}
    key={r[1]:r[0] for r in con.execute('SELECT account_key,account_code FROM dim_account').fetchall()}; item_key={'SP001':1,'DV001':2}; eid=1; rows=[]
    for mi,d in enumerate(months(args.months)):
        season=Decimal(str(1 + ((mi % 3)-1)*0.08)); revenue=(Decimal('120000000')*season).quantize(Decimal('0.01')); cogs=(revenue*Decimal('0.60')).quantize(Decimal('0.01')); salary=Decimal('18000000'); opex=Decimal('12000000'); day=min(28,calendar.monthrange(d.year,d.month)[1]); x=date(d.year,d.month,day); pkey=int(x.strftime('%Y%m%d'))
        events=[('SALES',key['131'],key['511'],revenue,1,'C001',2,'Doanh thu bán hàng'),('COGS',key['632'],key['156'],cogs,0,None,1,'Giá vốn hàng bán'),('SALARY',key['642'],key['334'],salary,0,'E001',None,'Chi phí lương'),('OPEX',key['642'],key['112'],opex,0,None,None,'Chi phí quản lý')]
        for j,(doc,dr,cr,amt,partnerflag,partner,item,desc) in enumerate(events):
            jid=f'{d:%Y%m}-{doc}'; rows += [(eid,jid,1,x,pkey,dr,pkey_of.get(partner),item_key['DV001'] if item==2 else item_key['SP001'] if item==1 else None,desc,amt,Decimal(0),'VND','invoice',jid,datetime.now()),(eid+1,jid,2,x,pkey,cr,pkey_of.get(partner),item_key['DV001'] if item==2 else item_key['SP001'] if item==1 else None,desc,Decimal(0),amt,'VND','invoice',jid,datetime.now())]; eid+=2
    con.executemany("INSERT INTO gl_entry VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",rows)
    bad=con.execute("SELECT COUNT(*) FROM (SELECT journal_id FROM gl_entry GROUP BY journal_id HAVING SUM(debit_amount)<>SUM(credit_amount))").fetchone()[0]
    if bad: raise RuntimeError(f'unbalanced journals: {bad}')
    print(f'generated {len(rows)} gl_entry rows, {args.months} months; debit=credit={con.execute("SELECT SUM(debit_amount) FROM gl_entry").fetchone()[0]}')
    con.close()
if __name__ == '__main__': main()
