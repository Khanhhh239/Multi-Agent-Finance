"""DA1–DA4: xác nhận cùng ngân sách hữu hạn, bootstrap cặp theo công ty."""
import gc
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import OUT, ROOT, SYNTH
from agent1.models import t1
from agent1.eval.adaptation import company_statistics, paired_improvement
from agent1.eval.cluster import ratio_ci
from run_t1 import snapshots, censor, domain_weights


def hazard_prediction(model, test):
    hazard = model.hazards(test)
    return t1.quantiles_from_hazard(hazard), t1.pmf_from_hazard(hazard)[0]


def hypothesis_status(effect, threshold=0, strict=False):
    if effect['improvement_ci_low'] > threshold or (not strict and effect['improvement_ci_low'] == threshold):
        return 'supported'
    if effect['improvement_ci_high'] < threshold or (strict and effect['improvement_ci_high'] == threshold):
        return 'rejected'
    return 'not_demonstrated'


def main():
    origin = pd.Timestamp('2024-07-01'); budget = 40000
    train = censor(snapshots('src',pd.date_range('2019-07-01',origin-pd.Timedelta(days=7),freq='14D'),tag='DA_paired_source'),origin)
    train = train.sample(min(len(train),budget),random_state=7).reset_index(drop=True)
    source = t1.HazardGBM(rounds=300).fit(train)
    summary, companies, pairs, weight_rows = [], [], [], []
    protocol = dict(complete=False, origin=str(origin.date()), source_budget=budget, target_budget=budget,
        source_rounds=300, pooled_rounds=300, target_only_rounds=300, finetune_rounds=150,
        adaptation_months=dict(tgt=[0,3,6,24],sens_uk=[6],sens_coface=[6]),
        weights='fixed source density-ratio classifier 200 trees, normalized/clipped [.05,20]; target weight max(1,.3*Nsrc/Ntgt)',
        selection='parameters locked; no selection from held-out test',
        acceptance='DA1 CI low>=20%; DA2 CI low>=10%; DA3 paired noninferiority at zero margin at M3/M6 and catchup M24; DA4 CI low>0 in BOTH sens domains',
        limitation='budget-limited confirmation separate from original B;synthetic truth labels;no CQR in this ablation;weekly overlapping forecasts clustered by firm')
    target_dir=OUT/'t1'; metadata=target_dir/'DA_paired_protocol.json'
    metadata.write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    for world, months in protocol['adaptation_months'].items():
        for month in months:
            visible = origin-pd.DateOffset(months=month) if month else origin
            test = censor(snapshots(world,pd.date_range(origin,periods=52,freq='7D'),visible_from=visible,tag=f'DA_paired_test_M{month}'),'2025-12-31')
            test = test[test.issue_date>=origin].copy()
            predictions = {'zero-shot':hazard_prediction(source,test)}; timings={'zero-shot':0.}
            point = t1.b1_predict(test); Q=np.column_stack([point]*3)
            cdf=(point[:,None]<=7*np.arange(1,14)).astype(float)
            predictions['B1']=(Q,np.diff(np.c_[np.zeros(len(test)),cdf],axis=1))
            Q=t1.b1_dist(test);cdf=t1.cdf_from_quantiles(Q)
            predictions['B1d']=(Q,np.diff(np.c_[np.zeros(len(test)),cdf],axis=1))
            n_target=0
            if month:
                adaptation = censor(snapshots(world,pd.date_range(visible+pd.Timedelta(days=28),origin-pd.Timedelta(days=7),freq='7D'),
                    visible_from=visible,tag=f'DA_paired_adapt_M{month}'),origin)
                adaptation=adaptation.sample(min(len(adaptation),budget),random_state=7).reset_index(drop=True)
                n_target=len(adaptation)
                for name,model,kwargs in [
                    ('target-only',t1.HazardGBM(dict(min_data_in_leaf=50,num_leaves=31),rounds=300),{}),
                    ('fine-tune',t1.HazardGBM(dict(learning_rate=.02),rounds=150),dict(init_model=source.booster))]:
                    began=time.monotonic();model.fit(adaptation,**kwargs)
                    timings[name]=time.monotonic()-began;predictions[name]=hazard_prediction(model,test)
                    del model;gc.collect()
                if month==6:
                    pooled=pd.concat([train,adaptation],ignore_index=True)
                    target_weight=np.full(len(adaptation),max(1.,.3*len(train)/len(adaptation)))
                    density_weights=domain_weights(train,adaptation)
                    weight_rows.append(dict(world=world,months_history=month,n_source=len(train),n_target=len(adaptation),
                        weight_min=float(density_weights.min()),weight_max=float(density_weights.max()),
                        weight_mean=float(density_weights.mean()),weight_std=float(density_weights.std()),
                        effective_sample_size=float(density_weights.sum()**2/np.square(density_weights).sum()),
                        constant_weights=bool(np.ptp(density_weights)<1e-12),
                        classifier='in-sample density ratio, fixed 200 trees; saturation can erase differences',
                        measurement_version='DA-paired-locked-budget-v1-fullweek'))
                    for name,source_weights in [('pooled',np.ones(len(train))),('IW-pooled',density_weights)]:
                        began=time.monotonic();model=t1.HazardGBM(rounds=300).fit(pooled,weight=np.r_[source_weights,target_weight])
                        timings[name]=time.monotonic()-began;predictions[name]=hazard_prediction(model,test)
                        del model;gc.collect()
                    del pooled
                del adaptation;gc.collect()
            per_model=[]
            for name,(Q,P) in predictions.items():
                grouped=company_statistics(test,Q,P);grouped['model']=name
                per_model.append(grouped)
                ci=ratio_ci(grouped.pinball_sum,grouped.n)
                summary.append(dict(world=world,months_history=month,model=name,n_test=len(test),n_firms=len(grouped),
                    n_source=len(train),n_target=n_target,pinball_avg=grouped.pinball_sum.sum()/grouped.n.sum(),
                    pinball_ci_low=ci['ci_low'],pinball_ci_high=ci['ci_high'],
                    WAPE_collect_w1_4=grouped.cash_error_w1_4.sum()/grouped.cash_actual_w1_4.sum(),
                    WAPE_collect_w5_13=grouped.cash_error_w5_13.sum()/grouped.cash_actual_w5_13.sum(),
                    fit_seconds=timings.get(name,0.),bootstrap_n=300,test_used_for_selection=False,measurement_version='DA-paired-locked-budget-v1-fullweek'))
            current=pd.concat(per_model,ignore_index=True)
            comparisons=[]
            if world=='tgt' and month==0:comparisons.append(('DA1','zero-shot','B1','cash_error_w1_4',20))
            if world=='tgt' and month==3:comparisons.append(('DA2','fine-tune','zero-shot','pinball_sum',10))
            if world=='tgt' and month in [3,6]:comparisons.append(('DA3','fine-tune','target-only','pinball_sum',0))
            if world=='tgt' and month==24:comparisons.append(('DA3','target-only','fine-tune','pinball_sum',0))
            if month==6:comparisons.append(('DA4','IW-pooled','pooled','pinball_sum',0))
            for hypothesis,model,baseline,metric,threshold in comparisons:
                effect=paired_improvement(current,model,baseline,metric)
                pairs.append(dict(hypothesis=hypothesis,world=world,months_history=month,model=model,baseline=baseline,
                    metric=metric,threshold_pct=threshold,**effect,status=hypothesis_status(effect,threshold,strict=hypothesis=='DA4'),
                    test_used_for_selection=False,measurement_version='DA-paired-locked-budget-v1-fullweek'))
            current['world']=world;current['months_history']=month;companies.append(current)
            pd.DataFrame(summary).to_csv(target_dir/'DA_paired_metrics.csv',index=False)
            pd.DataFrame(pairs).to_csv(target_dir/'DA_paired_comparisons.csv',index=False)
            pd.concat(companies).to_csv(target_dir/'DA_paired_company_losses.csv',index=False)
            if weight_rows:pd.DataFrame(weight_rows).to_csv(target_dir/'IW_weight_diagnostics.csv',index=False)
            print(world,'M',month,'scored',flush=True);del test,predictions;gc.collect()
    files=['scripts/run_da_paired.py','scripts/run_t1.py','agent1/models/features.py','agent1/models/t1.py','agent1/eval/adaptation.py','agent1/eval/cluster.py']
    protocol.update(complete=True,code_sha256=hashlib.sha256(b''.join((ROOT/p).read_bytes() for p in files)).hexdigest(),
        input_sha256={world:hashlib.sha256((SYNTH/world/'invoices.parquet').read_bytes()).hexdigest() for world in ['src','tgt','sens_uk','sens_coface']})
    metadata.write_text(json.dumps(protocol,indent=2),encoding='utf-8')


if __name__=='__main__':main()
