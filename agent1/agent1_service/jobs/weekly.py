"""Chẩn đoán hằng tuần từ dữ liệu quan sát; chạy bằng scheduler local do người dùng chọn."""
import argparse
import json
import os
from pathlib import Path

from agent1.jobs.retrain import observed_tables
from agent1.reconciliation.pipeline import ObservedSource,ObservedSnapshotBuilder
from agent1_service.model_registry import load
from agent1_service.monitoring import weekly_report
from agent1_service.store import Store


def run(store,firm,cutoff):
    _,record=load(store,firm,cutoff)
    current=None
    if record:
        observed_tables(store,firm,cutoff)
        current=ObservedSnapshotBuilder(ObservedSource(store,firm)).snapshot(cutoff)
    return weekly_report(store,firm,cutoff,current,record['reference'] if record else None)


def main():
    p=argparse.ArgumentParser();p.add_argument('--firm',required=True);p.add_argument('--cutoff',required=True)
    p.add_argument('--state',default=os.environ.get('AGENT1_STATE_DIR','.state'));args=p.parse_args()
    directory=Path(args.state)
    key_dir=Path(os.environ.get('AGENT1_KEY_DIR') or directory.parent/(directory.name+'-keys'))
    key_file=key_dir/'encryption.key'
    if not key_file.exists():key_file=directory/'encryption.key'
    if not key_file.exists():raise ValueError('Kho dữ liệu chưa được khởi tạo')
    store=Store(directory/'agent1.db',key_file.read_bytes())
    try:print(json.dumps(run(store,args.firm,args.cutoff),ensure_ascii=False,allow_nan=False))
    finally:store.connection.close()


if __name__=='__main__':main()
