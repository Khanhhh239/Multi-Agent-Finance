"""DA7: ablation nguồn cố định, ba cấu hình khóa trước, hai cửa sổ khủng hoảng."""
import argparse
import gc
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import OUT
from agent1.models.features import SnapshotBuilder,FEATURES,add_labels
from agent1.models.adaptive_features import AdaptiveSnapshotBuilder
from agent1.models.t1 import HazardGBM,QS,CAP,quantiles_from_hazard,b1_dist
from agent1.eval.cluster import mean_ci
from run_t1 import load_world


def compact(builder,cuts,label_end):
    parts=[]
    for cutoff in cuts:
        frame=builder.snapshot(cutoff)
        if frame.empty:continue
        columns=list(dict.fromkeys(['invoice_id','firm_id','cutoff','label_date','writeoff_date','top1','top2',
            'hist_q10','hist_q50','hist_q90',*FEATURES,*(['f_resid_7d'] if 'f_resid_7d' in frame else [])]))
        frame=frame[[c for c in columns if c in frame]].copy()
        numeric=frame.select_dtypes('number').columns;frame[numeric]=frame[numeric].astype('float32');parts.append(frame)
    if not parts:raise ValueError('Không có snapshot')
    return add_labels(pd.concat(parts,ignore_index=True),label_end)


def loss(frame,q):
    error=np.minimum(frame.remaining.to_numpy(),CAP)[:,None]-q
    return np.maximum(np.asarray(QS)*error,(np.asarray(QS)-1)*error).mean(1)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--max-train',type=int,default=40000)
    parser.add_argument('--rounds',type=int,default=300);args=parser.parse_args()
    rows=[];company=[]
    for start,end in [('2021-07-01','2021-10-31'),('2022-10-01','2023-06-30')]:
        origin=pd.Timestamp(start);train_end=origin-pd.Timedelta(days=120)
        train_cuts=pd.date_range('2019-07-01',train_end-pd.Timedelta(days=7),freq='14D')
        test_cuts=pd.date_range(start,end,freq='7D');source=load_world('src')
        train90=compact(SnapshotBuilder(*source),train_cuts,train_end)
        indices=train90.sample(min(len(train90),args.max_train),random_state=7).index
        train90=train90.loc[indices].reset_index(drop=True)
        train30=compact(AdaptiveSnapshotBuilder(*source),train_cuts,train_end).loc[indices].reset_index(drop=True)
        del source;gc.collect()
        models={}
        for name,frame,feats in [('no_shock',train90,[c for c in FEATURES if c not in ['f_resid_28d','f_resid_trend']]),
                                 ('shock_28d',train90,FEATURES),('fast_30d_7d',train30,[*FEATURES,'f_resid_7d'])]:
            began=time.monotonic();models[name]=HazardGBM(rounds=args.rounds,feats=feats).fit(frame)
            print(start,name,'fit',round(time.monotonic()-began,1),flush=True)
        del train30,train90;gc.collect()
        for world in ['src','tgt']:
            data=load_world(world)
            standard=compact(SnapshotBuilder(*data),test_cuts,'2025-12-31')
            fast=compact(AdaptiveSnapshotBuilder(*data),test_cuts,'2025-12-31')
            if not standard[['invoice_id','cutoff']].equals(fast[['invoice_id','cutoff']]):raise ValueError('Cohort ablation không khớp')
            losses={'B1d':loss(standard,b1_dist(standard))}
            for name,model in models.items():
                frame=fast if name=='fast_30d_7d' else standard
                losses[name]=loss(frame,quantiles_from_hazard(model.hazards(frame)))
            for name,values in losses.items():
                ci=mean_ci(values,standard.firm_id,baseline=losses['no_shock'])
                rows.append(dict(world=world,regime_start=start,regime_end=end,model=name,pinball=float(values.mean()),
                    pinball_ci_low=ci['ci_low'],pinball_ci_high=ci['ci_high'],improvement_pct=ci['improvement_pct'],
                    improvement_ci_low=ci['improvement_ci_low'],improvement_ci_high=ci['improvement_ci_high'],
                    n_firms=ci['n_firms'],n_test=len(standard),n_train=len(indices),rounds=args.rounds,bootstrap_n=300,
                    training_label_end=str(train_end.date()),target_used_for_selection=False,
                    measurement_version='crisis-source-only-locked-ablation-v1-fullweek'))
                grouped=pd.DataFrame(dict(firm_id=standard.firm_id.to_numpy(),loss=values)).groupby('firm_id').agg(loss_sum=('loss','sum'),n=('loss','size')).reset_index()
                grouped['world']=world;grouped['model']=name;grouped['regime_start']=start;company.append(grouped)
            pd.DataFrame(rows).to_csv(OUT/'t1/crisis_ablation.csv',index=False)
            pd.concat(company).to_csv(OUT/'t1/crisis_company_losses.csv',index=False)
            print(start,world,'scored',flush=True);del data,standard,fast;gc.collect()


if __name__=='__main__':main()
