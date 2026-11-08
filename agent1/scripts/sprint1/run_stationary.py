"""P4: A hai gốc, B M12, CI/BPI v2; cùng train/test và bootstrap cặp, mặc định tắt."""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from agent1.paths import SYNTH,PROCESSED,OUT
from agent1.models import t1
from agent1.models.features import StationaryFeatures
from agent1.eval.cluster import mean_ci
from run_t1 import snapshots,censor
from run_real_v2 import CFG,cap_rows,W_GRID,per_row_pinball,blend


def age(frame,invoices,visible=None):
    result=frame.copy();first=invoices.groupby('firm_id').issue_date.min()
    beginning=result.firm_id.map(first)
    if visible is not None:beginning=beginning.clip(lower=pd.Timestamp(visible))
    result['firm_history_days']=(result.cutoff-beginning).dt.days
    return result


def predict(model,frame,state=None):
    parts=[]
    for start in range(0,len(frame),40000):
        block=frame.iloc[start:start+40000]
        if state is not None:block=state.transform(block)
        parts.append(t1.quantiles_from_hazard(model.hazards(block)))
    return np.vstack(parts)


def fit(frame,enabled,params=None,rounds=600,state=None,init=None):
    state=state or (StationaryFeatures().fit(frame) if enabled else None)
    data=state.transform(frame) if enabled else frame
    model=t1.HazardGBM(params,rounds=rounds).fit(data,init_model=init)
    return model,state


def save(dataset,test,predictions,details,directory):
    baseline=per_row_pinball(test.remaining,predictions['baseline'])
    candidate=per_row_pinball(test.remaining,predictions['stationary'])
    groups=test.customer_id if dataset in ['ci','bpi'] else test.firm_id
    effect=mean_ci(candidate,groups,baseline=baseline)
    if dataset in ['ci','bpi']:
        reference=pd.read_csv(OUT/'t1/real_v2/C_real_v2.csv')
        reference=reference[(reference.setting==dataset)&reference.model.str.startswith('BLEND(DH-GBM,B1d) w=')]
        if len(reference)!=1 or reference.n.iloc[0]!=len(test) or abs(baseline.mean()/reference.pinball_avg.iloc[0]-1)>.005:
            raise ValueError('Baseline P4 không tái lập BLEND v2 trong sai số 0.5%')
    rows=[]
    for name,quantiles in predictions.items():
        stats=mean_ci(per_row_pinball(test.remaining,quantiles),groups,baseline=baseline)
        rows.append(dict(dataset=dataset,model=name,**t1.evaluate_quantiles(test.remaining.to_numpy(),quantiles),
            n=len(test),n_firms=len(set(groups)),bootstrap_groups='customer_id' if dataset in ['ci','bpi'] else 'firm_id',
            **{key:value for key,value in stats.items() if key!='n_firms'},measurement_version='P4-stationary-matched-protocol-v1-fullweek',test_used_for_selection=False))
    pd.DataFrame(rows).to_csv(directory/f'{dataset}_metrics.csv',index=False)
    pd.DataFrame(dict(group=np.asarray(groups),baseline_loss=baseline,candidate_loss=candidate)).groupby('group').agg(
        baseline_sum=('baseline_loss','sum'),candidate_sum=('candidate_loss','sum'),n=('baseline_loss','size')).to_csv(directory/f'{dataset}_paired_losses.csv')
    (directory/f'{dataset}_protocol.json').write_text(json.dumps(dict(complete=True,**details),indent=2),encoding='utf-8')
    print(dataset,effect,flush=True)


def real_dataset(name,directory):
    loader,snap,origin,test_days=CFG[name];invoices=loader();end=invoices.paid_date_true.max()
    origin=min(pd.Timestamp(origin),end-pd.Timedelta(days=int(t1.CAP)+test_days))
    frame=pd.read_parquet(PROCESSED/snap)
    # Match the protected v2 input precision before either ablation branch.
    # Different precision can change tree split ties and confound P4.
    float_columns=frame.select_dtypes('float64').columns
    frame[float_columns]=frame[float_columns].astype('float32')
    frame=age(frame,invoices);del invoices;gc.collect()
    cal_lo,cal_hi=origin-pd.Timedelta(days=183),origin-pd.Timedelta(days=120)
    test=censor(frame[frame.cutoff>=origin],end);test=test[test.cutoff<=end-pd.Timedelta(days=int(t1.CAP))]
    final=cap_rows(censor(frame[frame.cutoff<origin],origin))
    if (frame.cutoff<cal_lo).sum()>1000 and frame.cutoff.between(cal_lo,cal_hi).sum()>1000:
        selection=cap_rows(censor(frame[frame.cutoff<cal_lo],cal_lo));cal=censor(frame[frame.cutoff.between(cal_lo,cal_hi)],origin)
    else:
        cuts=np.sort(frame.cutoff[frame.cutoff<=origin-pd.Timedelta(days=int(t1.CAP))].unique())
        start=pd.Timestamp(cuts[-4]) if len(cuts)>=6 else pd.Timestamp(cuts[len(cuts)//2])
        selection=cap_rows(censor(frame[frame.cutoff<start],start))
        cal=censor(frame[frame.cutoff.between(start,origin-pd.Timedelta(days=int(t1.CAP)))],origin)
    del frame;gc.collect();predictions={};details={}
    for enabled,name_model in [(False,'baseline'),(True,'stationary')]:
        model,state=fit(selection,enabled,dict(min_data_in_leaf=100))
        qc=predict(model,cal,state);anchor=t1.b1_dist(cal)
        losses={w:per_row_pinball(cal.remaining,blend(qc,anchor,w)).mean() for w in W_GRID}
        weight=min(losses,key=losses.get);del model,qc;gc.collect()
        model,state=fit(final,enabled,dict(min_data_in_leaf=100))
        predictions[name_model]=blend(predict(model,test,state),t1.b1_dist(test),weight)
        details[name_model]=dict(calibration_w=weight,calibration_losses=losses,n_train=len(final),
            train_count_cap=state.count_cap if state else None)
        del model;gc.collect()
    save(name,test,predictions,dict(origin=str(origin.date()),protocol='exact v2 split/refit and DH-GBM params; no CQR',choices=details),directory)


def synthetic(directory):
    inv=pd.read_parquet(SYNTH/'src/invoices.parquet',columns=['firm_id','issue_date'])
    source=age(snapshots('src',pd.date_range('2019-07-01','2025-09-29',freq='7D'),tag='weekly'),inv)
    del inv;gc.collect()
    for origin in map(pd.Timestamp,['2023-07-03','2024-07-01']):
        cal_lo=origin-pd.Timedelta(days=183)
        train=censor(source[source.cutoff<cal_lo],cal_lo)
        train=train[train.cutoff.dt.isocalendar().week.astype(int)%2==0]
        test=censor(source[(source.cutoff>=origin)&(source.cutoff<origin+pd.Timedelta(days=182))],'2025-12-31')
        predictions={}
        for enabled,name in [(False,'baseline'),(True,'stationary')]:
            model,state=fit(train,enabled);predictions[name]=predict(model,test,state);del model;gc.collect()
        save('A_'+str(origin.date()),test,predictions,dict(origin=str(origin.date()),n_train=len(train),model='DH-GBM raw; exact A training rows/params'),directory)
    origin=pd.Timestamp('2024-07-01');visible=origin-pd.DateOffset(months=12)
    src=censor(source[source.cutoff.isin(pd.date_range('2019-07-01',origin-pd.Timedelta(days=7),freq='14D'))],origin)
    del source;gc.collect()
    inv=pd.read_parquet(SYNTH/'tgt/invoices.parquet',columns=['firm_id','issue_date'])
    target=age(censor(snapshots('tgt',pd.date_range(visible+pd.Timedelta(days=28),origin-pd.Timedelta(days=7),freq='7D'),
        visible_from=visible,tag='adapt_M12'),origin),inv,visible)
    cal_lo=origin-pd.Timedelta(days=183);cal_hi=origin-pd.Timedelta(days=120)
    if target.cutoff.between(cal_lo,cal_hi).sum()>200 and (target.cutoff<cal_lo).sum()>200:
        target=censor(target[target.cutoff<cal_lo],cal_lo)
    test=age(censor(snapshots('tgt',pd.date_range(origin,periods=52,freq='7D'),visible_from=visible,tag='test_M12'),'2025-12-31'),inv,visible)
    test=test[test.issue_date>=origin];predictions={}
    for enabled,name in [(False,'baseline'),(True,'stationary')]:
        pretrained,state=fit(src,enabled)
        model,_=fit(target,enabled,dict(learning_rate=.02),rounds=150,state=state,init=pretrained.booster)
        predictions[name]=predict(model,test,state);del model,pretrained;gc.collect()
    save('B_M12',test,predictions,dict(origin=str(origin.date()),n_source=len(src),n_target=len(target),
        protocol='exact B M12 source pretrain+150 fine-tune; P4 count cap frozen from source train'),directory)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data',default='synthetic,ci,bpi');args=parser.parse_args()
    directory=OUT/'t1/P4';directory.mkdir(exist_ok=True)
    for name in args.data.split(','):
        if name=='synthetic':synthetic(directory)
        else:real_dataset(name,directory)
    files=[directory/f'{name}_metrics.csv' for name in ['A_2023-07-03','A_2024-07-01','B_M12','ci','bpi']]
    if not all(p.exists() for p in files):return
    frame=pd.concat([pd.read_csv(p) for p in files]);frame.to_csv(directory/'metrics.csv',index=False)
    candidate=frame[frame.model=='stationary'];real=candidate[candidate.dataset.isin(['ci','bpi'])]
    eligible=bool((candidate.improvement_pct>=-1).all() and (real.improvement_pct>=2).any())
    (directory/'protocol.json').write_text(json.dumps(dict(complete=True,eligible=eligible,default_enabled=False,
        criterion='no dataset worse >1%; >=2% gain on at least one real dataset',test_used_for_hyperparameter_selection=False,
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        protected_real_v2_sha256=hashlib.sha256((ROOT/'scripts/sprint1/run_real_v2.py').read_bytes()).hexdigest()),indent=2),encoding='utf-8')
    print('P4 eligible',eligible,flush=True)


if __name__=='__main__':main()
