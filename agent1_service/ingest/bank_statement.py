import hashlib
import pandas as pd
from .dates import local_dates

BANK_COLUMNS = {
    'vcb': {'Ngày giao dịch':'value_date','Số tiền ghi có':'amount','Tên đối tác':'counterparty','Nội dung':'memo'},
    'bidv': {'Ngày GD':'value_date','Ghi có':'amount','Đối tác':'counterparty','Diễn giải':'memo'},
    'tcb': {'Transaction Date':'value_date','Credit':'amount','Counterparty':'counterparty','Description':'memo'},
    'mb': {'Ngày hạch toán':'value_date','Phát sinh có':'amount','Đơn vị đối ứng':'counterparty','Nội dung':'memo'},
    'acb': {'Ngày':'value_date','Tiền vào':'amount','Tên người chuyển':'counterparty','Nội dung giao dịch':'memo'},
}


def normalize_statement(df, firm_id, bank='vcb', mapping=None, dayfirst=True):
    out=df.rename(columns=mapping or BANK_COLUMNS[bank]).copy()
    if not {'value_date','amount','memo'} <= set(out):
        raise ValueError('Thiếu ngày, tiền ghi có hoặc nội dung; cần cấu hình ánh xạ cột')
    out['value_date']=local_dates(out.value_date,dayfirst=dayfirst)
    if not pd.api.types.is_numeric_dtype(out.amount):
        raise ValueError('Cột tiền phải là số; cần chỉ rõ quy ước dấu thập phân khi đọc CSV')
    out['amount']=pd.to_numeric(out.amount,errors='coerce')
    if out[['value_date','amount']].isna().any().any() or (out.amount<0).any():
        raise ValueError('Ngày hoặc số tiền không hợp lệ')
    out['memo']=out.memo.fillna('').astype(str)
    out['counterparty']=out.get('counterparty',pd.Series('',index=out.index)).fillna('').astype(str)
    out['firm_id'],out['direction']=firm_id,'in'
    if 'txn_id' not in out:
        # Thứ tự trùng trong cùng file giữ hai giao dịch có cùng ngày/tiền/nội dung.
        base=out[['value_date','amount','memo','counterparty']].astype(str).agg('|'.join,axis=1)
        duplicate=base.groupby(base).cumcount().astype(str)
        out['txn_id']=[firm_id+'-'+hashlib.sha256((a+'|'+b).encode()).hexdigest()[:24] for a,b in zip(base,duplicate)]
    if out.txn_id.duplicated().any():
        raise ValueError('Trùng txn_id')
    return out[['txn_id','firm_id','value_date','amount','direction','counterparty','memo']]


def read_statement(path, firm_id, bank='vcb', mapping=None, **read_options):
    loader=pd.read_excel if str(path).lower().endswith(('.xlsx','.xls')) else pd.read_csv
    return normalize_statement(loader(path,**read_options),firm_id,bank,mapping)
