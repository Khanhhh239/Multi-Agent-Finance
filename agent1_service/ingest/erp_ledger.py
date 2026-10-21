import pandas as pd
from .dates import local_dates


def normalize_ledger(df, firm_id, mapping):
    out=df.rename(columns=mapping).copy()
    required={'invoice_id','customer_id','issue_date','due_date','amount_gross'}
    if not required<=set(out):
        raise ValueError('Thiếu cột công nợ ERP')
    out['firm_id']=firm_id
    for c in ('issue_date','due_date','ledger_clear_date'):
        if c in out:
            out[c]=local_dates(out[c],dayfirst=True)
    out['amount_gross']=pd.to_numeric(out.amount_gross,errors='coerce')
    if out[['issue_date','amount_gross']].isna().any().any() or out.invoice_id.duplicated().any():
        raise ValueError('Ngày/tiền/khoá ERP không hợp lệ')
    out['term_days']=(out.due_date-out.issue_date).dt.days
    return out
