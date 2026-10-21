"""Độ ổn định T1 trên nguồn; không đọc miền đích để chọn seed."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_t1 as R
from agent1.models import t1


def main():
    O=pd.Timestamp('2024-07-01');cal_start=O-pd.Timedelta(days=183)
    S=R.snapshots('src',pd.date_range('2019-07-01','2025-09-29',freq='7D'),tag='weekly')
    tr=R.censor(S[S.cutoff<cal_start],cal_start)
    tr=tr[tr.cutoff.dt.isocalendar().week.astype(int)%2==0]
    te=R.censor(S[(S.cutoff>=O)&(S.cutoff<O+pd.Timedelta(days=182))],'2025-12-31')
    rows=[]
    for seed in (3,7,11):
        model=t1.HazardGBM(dict(seed=seed)).fit(tr)
        H=model.hazards(te);P,Sv=t1.pmf_from_hazard(H)
        metrics=R.score({'B1d-cust-quantiles':{'Q':t1.b1_dist(te)},'DH-GBM':{'Q':t1.quantiles_from_hazard(H),'cdf':1-Sv,'P':P}},te,'source_seed')
        metrics['seed']=seed;rows.append(metrics)
        print(seed,'done',flush=True)
    result=pd.concat(rows,ignore_index=True)
    result.to_csv(R.RES/'A_seed_stability.csv',index=False)
    dh=result[result.model=='DH-GBM']
    pd.DataFrame([dict(metric='pinball_avg',cv=float(dh.pinball_avg.std(ddof=0)/dh.pinball_avg.mean()),
                       meets_005=bool(dh.pinball_avg.std(ddof=0)/dh.pinball_avg.mean()<.005),
                       measurement_version=dh.measurement_version.iloc[0])]).to_csv(R.RES/'A_seed_cv.csv',index=False)


if __name__=='__main__':main()
