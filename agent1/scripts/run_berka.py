"""T6 phân vị trực tiếp + ACI và T7 chèn sốc trên tài khoản Berka thật.

Không suy ra hiệu quả mô hình hoá đơn từ bài kiểm tra dòng tiền tài khoản.
"""
import argparse
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import lightgbm as lgb
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.data.real_loaders import berka_weekly
from agent1.models.t6_cash import ACI
from agent1.models.t7_changepoint import residual_stream,cusum
from agent1.eval.metrics import coverage,interval_score
from agent1.eval.cluster import mean_ci
from agent1.paths import OUT
from agent1.threads import NT


def features(net,balance,dates,t):
    scale=max(np.mean(np.abs(net[t-12:t+1])),1.)
    base=list(net[t-12:t+1][::-1]/scale)+[float(net[t-3:t+1].mean()/scale),float(net[t-12:t+1].std()/scale),balance[t]/scale]
    return np.array([base+[k,int((dates[t]+pd.Timedelta(days=7*k)).month)] for k in range(1,14)],dtype='float32'),scale


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--accounts',type=int,default=0);args=parser.parse_args()
    data=berka_weekly();ids=sorted(data.account_id.unique())
    if args.accounts:ids=ids[:args.accounts]
    series={aid:g.sort_values('week').reset_index(drop=True) for aid,g in data[data.account_id.isin(ids)].groupby('account_id')}
    Xs,Ys=[],[]
    for aid,g in series.items():
        net,bal=g.net.to_numpy(),g.balance.to_numpy();dates=pd.DatetimeIndex(g.week)
        for t in range(20,len(g)-13,4):
            if dates[t+13]>pd.Timestamp('1996-12-31'):continue
            X,scale=features(net,bal,dates,t)
            Xs.append(X);Ys.append((bal[t+1:t+14]-bal[t])/scale)
    X,Y=np.vstack(Xs),np.concatenate(Ys)
    models={a:lgb.train(dict(objective='quantile',alpha=a,num_leaves=31,min_data_in_leaf=100,
        learning_rate=.05,num_threads=NT,verbosity=-1,seed=7),lgb.Dataset(X,Y),300) for a in (.1,.5,.9)}
    rows=[]
    for aid,g in series.items():
        net,bal=g.net.to_numpy(),g.balance.to_numpy();dates=pd.DatetimeIndex(g.week);aci=ACI();pending=[]
        for t in range(20,len(g)-13,4):
            if not pd.Timestamp('1997-01-01')<=dates[t]<=pd.Timestamp('1998-09-30'):continue
            for reveal,k,lo,hi,y in [p for p in pending if p[0]<=t]:aci.update(k,not lo<=y<=hi)
            pending=[p for p in pending if p[0]>t]
            X,scale=features(net,bal,dates,t)
            Q=np.sort(np.column_stack([models[a].predict(X) for a in (.1,.5,.9)]),axis=1)
            truth=(bal[t+1:t+14]-bal[t])/scale
            # Nội suy lưới phân vị dày từ phân vị trực tiếp để ACI cắt khoảng.
            u=np.linspace(.001,.999,1001)
            for k in range(13):
                samples=np.where(u<.5,Q[k,1]+(Q[k,1]-Q[k,0])*(u-.5)/.4,
                                 Q[k,1]+(Q[k,2]-Q[k,1])*(u-.5)/.4)
                lo,hi=aci.interval(samples,k);pending.append((t+k+1,k,lo,hi,truth[k]))
                for name,l,h in [('Direct LGBM-Q',Q[k,0],Q[k,2]),('Direct LGBM-Q + ACI',lo,hi)]:
                    rows.append(dict(account_id=aid,model=name,cutoff=dates[t],k=k+1,y=truth[k],lo=l,hi=h,med=Q[k,1]))
    frame=pd.DataFrame(rows);directory=OUT/'berka';directory.mkdir(exist_ok=True)
    frame.to_parquet(directory/'cash_predictions.parquet',index=False)
    summary=[]
    for name,g in frame.groupby('model'):
        ci=mean_ci(((g.y>=g.lo)&(g.y<=g.hi)).astype(float),g.account_id)
        summary.append(dict(model=name,cov80=coverage(g.y,g.lo,g.hi),IS80=interval_score(g.y,g.lo,g.hi),
            ci_low=ci['ci_low'],ci_high=ci['ci_high'],bootstrap_n=300,cluster_unit='account',
            n_accounts=g.account_id.nunique(),measurement_version='berka-train-through1996-test1997-98-v1',seed=7))
    pd.DataFrame(summary).to_csv(directory/'cash_metrics.csv',index=False)
    shock_rows=[];rng=np.random.default_rng(7)
    for aid,g in series.items():
        net=g.net.to_numpy().copy();injected=bool(rng.random()<.5)
        t0=int(rng.integers(40,max(41,len(net)-26)))
        if injected:net[t0:]-=.5*max(np.median(np.abs(net-np.median(net))),1.)
        z,raw=residual_stream(-net)
        alarms=np.asarray(cusum(z,k=.5,h=6))
        detected=bool(np.any((alarms>=t0)&(alarms<=t0+26))) if injected else np.nan
        exposure=max((g.week.iloc[-1]-g.week.iloc[0]).days/365.25,.1)
        shock_rows.append(dict(account_id=aid,injected=injected,detected_180d=detected,
            false_alarms_before_or_without_injection=int((alarms<t0).sum()) if injected else len(alarms),
            exposure_years=max(t0/52,.1) if injected else exposure,seed=7,
            limitation='natural_shifts_unlabelled;semi_synthetic_not_real_change_accuracy'))
    pd.DataFrame(shock_rows).to_csv(directory/'changepoint_injected.csv',index=False)


if __name__=='__main__':main()
