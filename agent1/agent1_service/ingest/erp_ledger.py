import pandas as pd
from .dates import local_dates


def normalize_ledger(df, firm_id, mapping):
    out=df.rename(columns=mapping).copy()
    required={'invoice_id','customer_id','issue_date','due_date','amount_gross'}
    if not required<=set(out):
        raise ValueError(f'Thiếu cột công nợ ERP: {sorted(required-set(out))}')
    out['firm_id']=firm_id
    for c in ('issue_date','due_date','ledger_clear_date'):
        if c in out:
            out[c]=local_dates(out[c],dayfirst=True)
    invalid=out['issue_date'].isna() | out.invoice_id.duplicated(keep=False)
    if invalid.any():
        raise ValueError(f'Dòng {int(invalid.to_numpy().nonzero()[0][0]) + 2}: ngày, tiền hoặc khoá ERP không hợp lệ')
    out['term_days']=(out.due_date-out.issue_date).dt.days
    return out
