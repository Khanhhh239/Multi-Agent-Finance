"""Cùng số hoá đơn mỗi cặp DN; lấy mẫu trước khi tính đặc trưng as-of."""
import hashlib
import numpy as np
import pandas as pd


def choose_shard_size(free_bytes):
    if free_bytes is None or free_bytes>=2*1024**3:return 8
    return 4 if free_bytes>=1024**3 else 2


def paired_quotas(left,right):
    left=left.sort_values('company_key').reset_index(drop=True)
    right=right.sort_values('company_key').reset_index(drop=True)
    if len(left)!=len(right) or not len(left):raise ValueError('Hai nhánh cần cùng số công ty')
    if left.company_key.duplicated().any() or right.company_key.duplicated().any():raise ValueError('Trùng mã công ty')
    count=np.minimum(left.n_invoices.to_numpy(),right.n_invoices.to_numpy()).astype(int)
    if (count<1).any():raise ValueError('Mỗi công ty cần ít nhất một hoá đơn trước origin')
    result=pd.DataFrame(dict(pair_index=np.arange(len(left)),left_company=left.company_key,right_company=right.company_key,n_invoices=count))
    return result


def sample_company_invoices(invoices,quotas,world,origin,seed=7):
    eligible=invoices[invoices.issue_date<=pd.Timestamp(origin)].copy();parts=[]
    for firm,group in eligible.groupby('firm_id'):
        key=world+'/'+firm
        if key not in quotas:raise ValueError('Thiếu quota công ty: '+key)
        count=int(quotas[key])
        if not 0<count<=len(group):raise ValueError('Quota không hợp lệ')
        state=int.from_bytes(hashlib.sha256(f'{seed}|{key}|{origin}'.encode()).digest()[:4],'little')
        parts.append(group.sample(count,random_state=state))
    return pd.concat(parts).sort_values('invoice_id').reset_index(drop=True)
