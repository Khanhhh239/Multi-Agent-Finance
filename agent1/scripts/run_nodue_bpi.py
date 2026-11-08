"""WP-1.6: BPI có nhãn chín; tuổi thay hạn là nhánh riêng, không biến prior thành hạn thật."""
import gc
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from agent1.data.real_loaders import bpi2019
from agent1.models.features import SnapshotBuilder,FEATURES,add_labels
from agent1.models.no_due_features import NoDueSnapshotBuilder
from agent1.models.t1 import HazardGBM,b1_dist,pmf_from_hazard,quantiles_from_hazard,cdf_from_quantiles,CAP,QS
from agent1.paths import OUT
from agent1.eval.cluster import ratio_ci


def bounded_training(builder,cutoffs,label_end,budget=40000):
    reservoir=pd.DataFrame()
    for cutoff in cutoffs:
        frame=builder.snapshot(cutoff)
        if frame.empty:continue
        frame=add_labels(frame,label_end);frame['no_due']=1-frame.has_due
        keep=['invoice_id','firm_id','cutoff','remaining','event','time_obs','top1','top2',*FEATURES,'no_due']
        frame=frame[list(dict.fromkeys(c for c in keep if c in frame))].copy()
        numeric=frame.select_dtypes('number').columns;frame[numeric]=frame[numeric].astype('float32')
        frame['_priority']=pd.util.hash_pandas_object(frame[['invoice_id','cutoff']],index=False,hash_key='0000000000000007').to_numpy()
        frame=frame.nsmallest(min(len(frame),budget),'_priority')
        reservoir=pd.concat([reservoir,frame],ignore_index=True).nsmallest(budget,'_priority')
    return reservoir.sort_values('_priority').reset_index(drop=True)


def row_loss(y,Q):
    residual=np.minimum(y,CAP)[:,None]-Q
    return np.maximum(np.asarray(QS)*residual,(np.asarray(QS)-1)*residual).mean(1)


def aggregate(frame,Q,cdf,model):
    y=frame.remaining.to_numpy();capped=np.minimum(y,CAP)
    values=pd.DataFrame(dict(firm_id=frame.firm_id.to_numpy(),pinball=row_loss(y,Q),
        MAE=np.abs(capped-Q[:,1]),coverage=(capped>=Q[:,0])&(capped<=Q[:,2]),
        interval=Q[:,2]-Q[:,0]+10*np.maximum(Q[:,0]-capped,0)+10*np.maximum(capped-Q[:,2],0),
        IBS=np.mean(((y[:,None]<=7*np.arange(1,14))-cdf)**2,axis=1)))
    grouped=values.groupby('firm_id').agg(pinball=('pinball','sum'),MAE=('MAE','sum'),coverage=('coverage','sum'),
        interval=('interval','sum'),IBS=('IBS','sum'),n=('pinball','size')).reset_index()
    grouped['model']=model
    return grouped


def main():
    inv=bpi2019().copy();inv['due_date']=pd.NaT;inv['writeoff_date']=pd.NaT
    root=Path(__file__).resolve().parents[1]
    code_hash=hashlib.sha256(b''.join((root/path).read_bytes() for path in ['scripts/run_nodue_bpi.py','scripts/eval_by_regime.py',
        'scripts/run_t1.py','agent1/models/no_due_features.py','agent1/models/features.py','agent1/models/t1.py',
        'agent1/eval/metrics.py','agent1/eval/cluster.py','requirements-lock.txt'])).hexdigest()
    input_hash=hashlib.sha256(pd.util.hash_pandas_object(inv,index=True).to_numpy().tobytes()).hexdigest()
    protocol_path=OUT/'t1/BPI_no_due_protocol.json';output=OUT/'t1/BPI_no_due_ablation.csv'
    if protocol_path.exists() and output.exists():
        prior=json.loads(protocol_path.read_text(encoding='utf-8'))
        if prior.get('complete') and prior.get('code_hash')==code_hash and prior.get('input_hash')==input_hash and prior.get('output_sha256')==hashlib.sha256(output.read_bytes()).hexdigest():
            print('resumed verified BPI no-due result',flush=True);return
    data_end=inv.paid_date_true.max();origin=min(pd.Timestamp('2018-09-03'),data_end-pd.Timedelta(days=120+56))
    train_cuts=pd.date_range('2018-03-05',origin-pd.Timedelta(days=1),freq='7D')
    builders={'DH-GBM missing due (current)':SnapshotBuilder(inv),'DH-GBM virtual30 age/no_due':NoDueSnapshotBuilder(inv)}
    models={};training_keys=None;n_train=0
    for name,builder in builders.items():
        train=bounded_training(builder,train_cuts,origin);n_train=len(train)
        keys=train[['invoice_id','cutoff']]
        if training_keys is not None and not keys.equals(training_keys):raise ValueError('Mẫu train hai nhánh không khớp')
        training_keys=keys.copy()
        models[name]=HazardGBM(rounds=300,feats=FEATURES+(['no_due'] if 'virtual30' in name else [])).fit(train)
        print(name,'fit',n_train,flush=True);del train;gc.collect()
    parts=[]
    for cutoff in pd.date_range(origin,origin+pd.Timedelta(days=56),freq='7D'):
        keys=None
        for name,builder in builders.items():
            frame=add_labels(builder.snapshot(cutoff),data_end);frame['no_due']=1-frame.has_due
            current_keys=frame[['invoice_id','cutoff']].reset_index(drop=True)
            if keys is not None and not current_keys.equals(keys):raise ValueError('Cohort test không khớp')
            keys=current_keys
            H=models[name].hazards(frame);P,S=pmf_from_hazard(H)
            parts.append(aggregate(frame,quantiles_from_hazard(H),1-S,name))
            if name=='DH-GBM missing due (current)':
                Q=b1_dist(frame);cdf=cdf_from_quantiles(Q)
                parts.append(aggregate(frame,Q,cdf,'B1d-cust-quantiles'))
            del frame,H,P,S;gc.collect()
        print('test',str(cutoff.date()),'scored',flush=True)
    grouped=pd.concat(parts).groupby(['model','firm_id'],as_index=False).sum(numeric_only=True)
    base=grouped[grouped.model=='DH-GBM missing due (current)'].set_index('firm_id').pinball
    b1=grouped[grouped.model=='B1d-cust-quantiles'].set_index('firm_id').pinball
    rows=[]
    for name,g in grouped.groupby('model'):
        g=g.set_index('firm_id').reindex(base.index);ci=ratio_ci(g.pinball,g.n);coverage=ratio_ci(g.coverage,g.n)
        paired=ratio_ci(base-g.pinball,base);vs_b1=ratio_ci(b1-g.pinball,b1)
        rows.append(dict(setting='BPI_no_due_locked_ablation',model=name,n=int(g.n.sum()),n_firms=len(g),
            pinball_avg=g.pinball.sum()/g.n.sum(),pinball_ci_low=ci['ci_low'],pinball_ci_high=ci['ci_high'],
            MAE_p50=g.MAE.sum()/g.n.sum(),cov80=g.coverage.sum()/g.n.sum(),cov80_ci_low=coverage['ci_low'],cov80_ci_high=coverage['ci_high'],
            IS80=g.interval.sum()/g.n.sum(),IBS_13w=g.IBS.sum()/g.n.sum(),
            improvement_pct=100*(b1.sum()-g.pinball.sum())/b1.sum(),improvement_ci_low=100*vs_b1['ci_low'],improvement_ci_high=100*vs_b1['ci_high'],
            vs_current_improvement_pct=100*(base.sum()-g.pinball.sum())/base.sum(),
            vs_current_improvement_ci_low=100*paired['ci_low'],vs_current_improvement_ci_high=100*paired['ci_high'],
            bootstrap_n=300,n_train=n_train,origin=str(origin.date()),test_used_for_selection=False,
            measurement_version='BPI-no-due-age-proxy-v2-streamed'))
    result=pd.DataFrame(rows)
    result['limitation']='virtual_due_is_proxy_not_contract;no_CQR_when_120d_calibration_gap_unavailable;BPI_payables_not_VN_AR'
    result.to_csv(output,index=False)
    protocol_path.write_text(json.dumps(dict(complete=True,code_hash=code_hash,input_hash=input_hash,
        output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),training_label_end=str(origin.date()),
        source='BPI2019',test_used_for_selection=False,max_train=40000,rounds=300),indent=2),encoding='utf-8')


if __name__=='__main__':main()
