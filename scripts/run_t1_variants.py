"""WP-1.9: PDP→monotone, daily 28d, due mixture, EB ML-II; nguồn khóa trước."""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import OUT,SYNTH
from agent1.models import t1
from agent1.models.features import FEATURES
from agent1.models.t1_variants import DailyEarlyHazard,DueMixture,source_pdp_constraints
from agent1.models.eb_ml2 import learn_industry_k,apply_learned_eb
from agent1.eval.cluster import mean_ci
from run_t1 import snapshots,censor,score,load_world


def prediction(model,frame):
    H=model.hazards(frame);P,S=t1.pmf_from_hazard(H)
    return dict(Q=t1.quantiles_from_hazard(H),P=P,cdf=1-S)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--max-train',type=int,default=40000)
    parser.add_argument('--rounds',type=int,default=300);args=parser.parse_args()
    directory=OUT/'t1';origin=pd.Timestamp('2024-07-01');label_end=origin-pd.Timedelta(days=183)
    cuts=pd.date_range('2019-07-01',label_end-pd.Timedelta(days=7),freq='14D')
    train=censor(snapshots('src',cuts,tag='variants_training'),label_end)
    train=train.sample(min(len(train),args.max_train),random_state=7)
    cal=censor(snapshots('src',pd.date_range(label_end,origin-pd.Timedelta(days=120),freq='7D'),tag='variants_calibration'),origin)
    cal=cal.sample(min(len(cal),10000),random_state=7)
    inv,_,_=load_world('src');source_firms=pd.read_parquet(SYNTH/'src/firms.parquet')
    learned=learn_industry_k(inv,source_firms,label_end);del inv;gc.collect()
    (directory/'EB_ml2_source.json').write_text(json.dumps(learned,indent=2),encoding='utf-8')
    models={};timings={}
    start=time.monotonic();base=t1.HazardGBM(rounds=args.rounds).fit(train)
    models['DH-GBM default']=base;timings['DH-GBM default']=time.monotonic()-start
    constraints,pdp=source_pdp_constraints(base,cal)
    pdp['measurement_version']='source-PDP-locked-signs-v1-fullweek';pdp.to_csv(directory/'source_PDP.csv',index=False)
    import matplotlib.pyplot as plt
    features=['c_late_share','c_delay_eb','c_delay_ewm','c_max_dpd','c_promise_rel']
    figure,axes=plt.subplots(1,5,figsize=(15,3))
    for feature,axis in zip(features,axes):
        values=pdp[pdp.feature==feature]
        axis.plot(values.value,values.mean_hazard,marker='o');axis.set_title(feature,fontsize=9)
        axis.set_xlabel('Gia tri dac trung');axis.grid(alpha=.2)
    axes[0].set_ylabel('Mean weekly hazard')
    figure.tight_layout();figure.savefig(directory/'source_PDP.png',dpi=150);plt.close(figure)
    start=time.monotonic()
    models['DH-GBM monotone PDP']=t1.HazardGBM(dict(monotone_constraints=constraints,monotone_constraints_method='advanced'),rounds=args.rounds).fit(train)
    timings['DH-GBM monotone PDP']=time.monotonic()-start;print('monotone fit',flush=True)
    start=time.monotonic();daily=DailyEarlyHazard(base,rounds=200).fit(train)
    timings['DH daily28 + weekly tail']=time.monotonic()-start;print('daily fit',flush=True)
    start=time.monotonic();models['Due-window mixture']=DueMixture(base,rounds=args.rounds).fit(train,cal)
    timings['Due-window mixture']=time.monotonic()-start;print('mixture fit',flush=True)
    start=time.monotonic();industry=source_firms.set_index('firm_id').industry
    models['DH-GBM EB ML-II']=t1.HazardGBM(rounds=args.rounds).fit(apply_learned_eb(train,learned,industry))
    timings['DH-GBM EB ML-II']=time.monotonic()-start;print('EB fit',flush=True)
    del train,cal;gc.collect();results=[];decision_rows=[]
    for world in ['src','tgt']:
        test=censor(snapshots(world,pd.date_range(origin,periods=52,freq='7D'),tag='variants_test'),'2025-12-31')
        firms=pd.read_parquet(SYNTH/world/'firms.parquet').set_index('firm_id').industry
        preds={'B1d-cust-quantiles':dict(Q=t1.b1_dist(test)),
               'B1-cust-median':dict(Q=np.column_stack([t1.b1_predict(test)]*3))}
        for name,model in models.items():
            frame=apply_learned_eb(test,learned,firms) if name=='DH-GBM EB ML-II' else test
            preds[name]=prediction(model,frame)
        preds['DH daily28 + weekly tail']=daily.predict(test)
        result=score(preds,test,world,extra=dict(measurement_version='T1-locked-source-variants-v1-fullweek'))
        y=np.minimum(test.remaining.to_numpy(),t1.CAP)
        def loss(q):
            residual=y[:,None]-q
            return np.maximum(np.asarray(t1.QS)*residual,(np.asarray(t1.QS)-1)*residual).mean(1)
        baseline=loss(preds['DH-GBM default']['Q'])
        for name,pred in preds.items():
            ci=mean_ci(loss(pred['Q']),test.firm_id,baseline=baseline)
            for key in ['improvement_pct','improvement_ci_low','improvement_ci_high']:
                result.loc[result.model==name,'vs_default_'+key]=ci[key]
            result.loc[result.model==name,'fit_seconds']=timings.get(name,0.)
            decision_rows.append(dict(world=world,model=name,improvement_pct=ci['improvement_pct'],
                ci_low=ci['improvement_ci_low'],ci_high=ci['improvement_ci_high'],candidate_adopted=False,
                test_used_for_selection=False,measurement_version='T1-locked-source-variants-v1-fullweek'))
        result['n_train_budget']=args.max_train;result['rounds']=args.rounds;result['test_used_for_selection']=False
        result['limitation']='budget_limited_research;mixture_conditions_on_known_component;daily_200_extra_rounds;no_automatic_adoption'
        results.append(result);pd.concat(results).to_csv(directory/'T1_variants.csv',index=False)
        pd.DataFrame(decision_rows).to_csv(directory/'T1_variant_decisions.csv',index=False)
        print(world,'scored',flush=True);del test,preds;gc.collect()
    signature=hashlib.sha256(b''.join(Path(module).read_bytes() for module in [t1.__file__,Path(t1.__file__).parent/'features.py',Path(t1.__file__).parent/'t1_variants.py',Path(t1.__file__).parent/'eb_ml2.py'])).hexdigest()
    (directory/'T1_variants_protocol.json').write_text(json.dumps(dict(origin=str(origin.date()),training_label_end=str(label_end.date()),
        calibration_last_cutoff=str((origin-pd.Timedelta(days=120)).date()),source_only_selection=True,
        code_sha256=signature,n_train_budget=args.max_train,rounds=args.rounds,constraints=dict(zip(FEATURES+t1.WEEK_FEATS,constraints)),
        pdp_rule='sign*Spearman>=.7 and >=.75 correctly directed steps; source only',
        methods_reference='https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html#monotone_constraints'),indent=2),encoding='utf-8')


if __name__=='__main__':main()
