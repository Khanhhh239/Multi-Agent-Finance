"""Huấn luyện ứng viên T1 từ dữ liệu đối soát đã quan sát, không dùng nhãn oracle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np
import pandas as pd

from agent1.models.features import SnapshotBuilder
from agent1.models.t1 import HazardGBM,quantiles_from_hazard,QS
from agent1.models.t9_recon import Reconciler
from agent1.models.reconciliation_pipeline import build_bank_labels
from agent1_service.ingest.dates import local_dates
from agent1_service.store import Store
from agent1_service.model_registry import register,activate


def observed_tables(store,firm,cutoff):
    cutoff=pd.Timestamp(cutoff);result={}
    for kind in ['invoices','bank_txns','customers','promises']:
        data=pd.DataFrame(store.get(firm,kind))
        for col in data.columns:
            if 'date' in col:data[col]=local_dates(data[col],dayfirst=False)
        date={'invoices':'issue_date','bank_txns':'value_date','promises':'made_date'}.get(kind)
        if date and len(data):data=data[data[date]<=cutoff]
        result[kind]=data
    if any(result[k].empty for k in ['invoices','bank_txns','customers']):
        raise ValueError('Cần hoá đơn, giao dịch và khách hàng trước cutoff')
    # Chỉ giữ khách đã xuất hiện trên hoá đơn quan sát được.
    result['customers']=result['customers'][result['customers'].customer_id.isin(result['invoices'].customer_id)]
    return result


def train_candidate(store,firm,cutoff,reason,*,rounds=200,max_rows=40000):
    start=time.monotonic();T=pd.Timestamp(cutoff)
    if reason not in {'psi','coverage','scheduled','manual'}:raise ValueError('Lý do retrain không hợp lệ')
    tables=observed_tables(store,firm,T)
    links,_=Reconciler().reconcile(tables['bank_txns'],tables['invoices'],tables['customers'])
    inv=build_bank_labels(tables['invoices'],links);inv['writeoff_date']=pd.NaT
    prom=tables['promises']
    if len(prom):
        # Chưa có kết quả hứa được đối chiếu: không tin cột kept do người nhập gửi.
        prom=prom.copy();prom['kept']=np.nan
    builder=SnapshotBuilder(inv,links,prom if len(prom) else None,label_col='paid_date_est')
    train_end=T-pd.Timedelta(days=120)
    cuts=pd.date_range(max(inv.issue_date.min()+pd.Timedelta(days=60),T-pd.Timedelta(days=730)),train_end-pd.Timedelta(days=7),freq='14D')
    if not len(cuts):raise ValueError('Chưa đủ lịch sử và khoảng cách nhãn 120 ngày')
    train=builder.build(cuts,label_end=train_end)
    if len(train)<100 or train.event.nunique()<2:raise ValueError('Chưa đủ nhãn đã chín để huấn luyện')
    train=train.sample(min(len(train),max_rows),random_state=7)
    model=HazardGBM(dict(min_data_in_leaf=30,num_leaves=31),rounds=rounds).fit(train)
    validation=builder.build([train_end],label_end=T)
    known=validation[(validation.event==1)&(validation.remaining<=120)] if len(validation) else validation
    metrics=dict(validation_rows=len(validation),resolved_rows=len(known),resolved_only=True)
    if len(known):
        q=quantiles_from_hazard(model.hazards(known));error=known.remaining.to_numpy()[:,None]-q
        metrics['pinball_resolved']=float(np.maximum(np.asarray(QS)*error,(np.asarray(QS)-1)*error).mean())
        metrics['cov80_resolved']=float(np.mean((known.remaining>=q[:,0])&(known.remaining<=q[:,2])))
    fingerprints={k:hashlib.sha256(v.to_json(orient='split',date_format='iso').encode()).hexdigest() for k,v in tables.items()}
    metadata=dict(firm_id=firm,available_at=T.isoformat(),training_label_end=train_end.isoformat(),
                  data_hash=hashlib.sha256(json.dumps(fingerprints,sort_keys=True).encode()).hexdigest(),
                  reason=reason,n_rows=len(train),rounds=rounds,parameters=model.p,metrics=metrics,
                  label_mode='observed_rule_reconciliation',seconds=time.monotonic()-start,
                  limitation='local_research;resolved_validation_survivorship;not_pilot_acceptance')
    return register(store,firm,model,metadata,train.sample(min(1000,len(train)),random_state=7))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--firm',required=True)
    parser.add_argument('--reason',required=True,choices=['psi','coverage','scheduled','manual'])
    parser.add_argument('--cutoff',required=True);parser.add_argument('--state',default=os.environ.get('AGENT1_STATE_DIR','.state'))
    parser.add_argument('--activate',action='store_true');args=parser.parse_args()
    directory=Path(args.state)
    if not (directory/'encryption.key').exists():raise ValueError('Kho dữ liệu chưa được khởi tạo')
    store=Store(directory/'agent1.db',(directory/'encryption.key').read_bytes())
    try:
        result=train_candidate(store,args.firm,args.cutoff,args.reason)
        if args.activate:activate(store,args.firm,result['id'])
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    finally:store.connection.close()


if __name__=='__main__':main()
