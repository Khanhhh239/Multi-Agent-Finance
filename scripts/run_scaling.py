"""Scaling cùng một nguồn, tập mẫu lồng nhau, không chỉnh tham số theo tgt."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH,PROCESSED,OUT
from agent1.models.features import SnapshotBuilder,FEATURES,add_labels
from agent1.models import t1
from agent1.data.scaling import NestedRowWriter


def expanded_count(invoices,cutoffs,origin):
    total=0
    for cutoff in cutoffs:
        op=invoices[(invoices.issue_date<=cutoff)&(invoices.paid_date_true.isna()|(invoices.paid_date_true>cutoff))&
            (invoices.writeoff_date.isna()|(invoices.writeoff_date>cutoff))]
        days=(op.paid_date_true-cutoff).dt.days.to_numpy(dtype=float)
        event=op.paid_date_true.notna()&(op.paid_date_true<=origin)
        available=min((origin-cutoff).days//7,t1.K)
        events=np.minimum(np.ceil(days/7),available if t1.FULL_WEEK_ONLY else t1.K)
        total+=int(np.where(event.to_numpy(),events,available).sum())
    return total


def prepare(world,sizes,origin):
    source=SYNTH/world;cutoffs=pd.date_range('2019-07-01',origin-pd.Timedelta(days=7),freq='14D')
    digest=hashlib.sha256()
    for table in ['invoices','payments','promises']:
        with (source/f'{table}.parquet').open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    for file in [Path(t1.__file__),Path(t1.__file__).with_name('features.py')]:digest.update(file.read_bytes())
    digest.update(json.dumps(dict(sizes=sizes,origin=str(origin),seed=7,expand_full_week_only=t1.FULL_WEEK_ONLY)).encode())
    fingerprint=digest.hexdigest();directory=PROCESSED/f'scaling_{world}_{fingerprint[:12]}'
    if (directory/'manifest.json').exists():return directory
    columns=len(FEATURES+t1.WEEK_FEATS)
    needed=sum(sizes)*(columns+1)*4+1024**3
    if shutil.disk_usage(PROCESSED).free<needed:raise RuntimeError('Không đủ dung lượng cho memmap và 1 GiB dự phòng')
    invoices=pd.read_parquet(source/'invoices.parquet',columns=['issue_date','paid_date_true','writeoff_date'])
    total=expanded_count(invoices,cutoffs,origin);del invoices
    print('expanded population',total,flush=True)
    writer=NestedRowWriter(directory,sizes,total,columns)
    firms=pd.read_parquet(source/'firms.parquet').firm_id.sort_values().tolist()
    for start in range(0,len(firms),12):
        subset=firms[start:start+12];filters=[('firm_id','in',subset)]
        inv,pay,prom=[pd.read_parquet(source/f'{table}.parquet',filters=filters) for table in ['invoices','payments','promises']]
        builder=SnapshotBuilder(inv,pay,prom)
        for cutoff in cutoffs:
            frame=builder.snapshot(cutoff)
            if frame.empty:continue
            frame=add_labels(frame,origin)
            X,y,ix=t1.expand(frame,True)
            writer.append(X,y,frame.firm_id.to_numpy()[ix])
        print(world,'firms',start+len(subset),'/',len(firms),'selected',writer.selected,flush=True)
    writer.finish(dict(world=world,seed=7,origin=str(origin.date()),source_fingerprint=fingerprint,
        features=FEATURES+t1.WEEK_FEATS,n_population=total,n_source_firms=len(firms),test_used_for_selection=False,
        expand_full_week_only=t1.FULL_WEEK_ONLY))
    return directory


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--world',default='big_000')
    parser.add_argument('--sizes',default='1000000,3000000,10000000');parser.add_argument('--rounds',type=int,default=300)
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args();sizes=sorted(set(map(int,args.sizes.split(','))))
    directory=prepare(args.world,sizes,pd.Timestamp('2024-07-01'))
    manifest=dict(json.loads((directory/'manifest.json').read_text(encoding='utf-8')),cache_directory=str(directory))
    (OUT/'t1/scaling_data_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    if args.prepare_only:return
    for size in sizes:
        result_path=OUT/f't1/scaling_{size}.csv';loss_path=OUT/f't1/scaling_company_losses_{size}.csv'
        if result_path.exists() and loss_path.exists():
            previous=pd.read_csv(result_path)
            if len(previous)==14 and set(previous.months_history)=={0,3,6,12,24} and previous.source_fingerprint.eq(manifest['source_fingerprint']).all() and previous.pretraining_rounds.eq(args.rounds).all():
                print('resumed completed',size,flush=True);continue
        subprocess.run([sys.executable,'-u',str(Path(__file__).with_name('scaling_worker.py')),
            '--cache',str(directory),'--rows',str(size),'--rounds',str(args.rounds)],check=True)
    from plot_scaling import main as plot
    plot()


if __name__=='__main__':main()
