"""Nạp đúng dữ liệu tổng hợp được cấu hình; không đọc thư mục dữ liệu thật."""
import json
from pathlib import Path
import os
import pandas as pd
from .api import create_app


def seed(directory,store,firm):
    directory=Path(directory)
    keep={
        'invoices':['invoice_id','firm_id','customer_id','invoice_no','issue_date','due_date','amount_gross','term_days','ledger_clear_date'],
        'bank_txns':['txn_id','firm_id','value_date','amount','direction','counterparty','memo'],
        'customers':['customer_id','firm_id','short','name','mst'],
        'promises':['invoice_id','firm_id','customer_id','made_date','promised_date'],
        'outflows':['firm_id','date','category','amount','known_in_advance'],
        'cash_balances':['firm_id','date','balance'],
    }
    keys={'invoices':'invoice_id','bank_txns':'txn_id','customers':'customer_id','cash_balances':'date'}
    for kind,cols in keep.items():
        if store.get(firm,kind):continue
        data=pd.read_parquet(directory/f'{"daily_cash" if kind=="cash_balances" else kind}.parquet')
        data=data[data.firm_id==firm][[c for c in cols if c in data]]
        if kind=='promises':data['kept']=None
        records=json.loads(data.to_json(orient='records',date_format='iso'))
        for i,row in enumerate(records):row['id']=str(row[keys[kind]]) if kind in keys else str(i)
        store.put(firm,kind,records)


if __name__=='__main__':
    source=os.environ.get('AGENT1_DEMO_DIR')
    if source:
        app=create_app()
        seed(source,app.state.store,os.environ.get('AGENT1_FIRM_ID','F000'))
        app.state.store.connection.close()
