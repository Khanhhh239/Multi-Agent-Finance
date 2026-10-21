"""Chẩn đoán hằng tuần từ dữ liệu quan sát; chạy bằng scheduler local do người dùng chọn."""
import argparse
import json
import os
from pathlib import Path
import numpy as np

from agent1.jobs.retrain import observed_tables
from agent1.models.features import SnapshotBuilder
from agent1.models.t9_recon import Reconciler
from agent1.models.reconciliation_pipeline import build_bank_labels
from agent1_service.model_registry import load
from agent1_service.monitoring import weekly_report
from agent1_service.store import Store


def run(store,firm,cutoff):
    _,record=load(store,firm,cutoff)
    current=None
    if record:
        tables=observed_tables(store,firm,cutoff)
        links,_=Reconciler().reconcile(tables['bank_txns'],tables['invoices'],tables['customers'])
        inv=build_bank_labels(tables['invoices'],links)
        promises=tables['promises'].copy()
        if len(promises):promises['kept']=np.nan
        current=SnapshotBuilder(inv,links,promises if len(promises) else None,label_col='paid_date_est').snapshot(cutoff)
    return weekly_report(store,firm,cutoff,current,record['reference'] if record else None)


def main():
    p=argparse.ArgumentParser();p.add_argument('--firm',required=True);p.add_argument('--cutoff',required=True)
    p.add_argument('--state',default=os.environ.get('AGENT1_STATE_DIR','.state'));args=p.parse_args()
    directory=Path(args.state)
    if not (directory/'encryption.key').exists():raise ValueError('Kho dữ liệu chưa được khởi tạo')
    store=Store(directory/'agent1.db',(directory/'encryption.key').read_bytes())
    try:print(json.dumps(run(store,args.firm,args.cutoff),ensure_ascii=False,allow_nan=False))
    finally:store.connection.close()


if __name__=='__main__':main()
