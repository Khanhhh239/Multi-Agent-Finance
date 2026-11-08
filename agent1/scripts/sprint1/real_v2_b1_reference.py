"""Đối chứng B1 trên đúng cohort CI v2, không đổi script v2 đã khoá."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from agent1.models import t1
from agent1.data import real_loaders as RL
from run_t1 import censor
from run_real_v2 import CFG


def main():
    _,snap,origin,test_days=CFG['ci']
    end=RL.customer_invoices().paid_date_true.max()
    origin=min(pd.Timestamp(origin),end-pd.Timedelta(days=int(t1.CAP)+test_days))
    test=pd.read_parquet(ROOT/'data/processed'/snap)
    test=censor(test[test.cutoff>=origin],end);test=test[test.cutoff<=end-pd.Timedelta(days=int(t1.CAP))]
    quantiles=np.repeat(t1.b1_predict(test)[:,None],3,axis=1)
    row=dict(setting='ci',model='B1-cust-median',n=len(test),**t1.evaluate_quantiles(test.remaining.to_numpy(),quantiles),
        origin=str(origin.date()),test_end=str(end.date()),measurement_version='C-real-v2-B1-reference-fullweek',
        source_script_sha256=hashlib.sha256((ROOT/'scripts/sprint1/run_real_v2.py').read_bytes()).hexdigest())
    directory=ROOT/'outputs/t1/real_v2'
    existing=pd.read_csv(directory/'C_real_v2.csv');expected=existing[existing.setting=='ci'].n.unique()
    if len(expected)!=1 or expected[0]!=len(test):raise ValueError('B1 khác cohort v2')
    pd.DataFrame([row]).to_csv(directory/'B1_reference.csv',index=False)
    print(json.dumps({k:row[k] for k in ['n','pinball_avg','MAE_p50']}))


if __name__=='__main__':main()
