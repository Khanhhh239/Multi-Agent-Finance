"""IW OOF so in-sample/pooled; cùng cohort/ngân sách DA-paired M6, không thay mặc định."""
import gc
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import ROOT,SYNTH,OUT
from agent1.models import t1
from agent1.models.domain_weight_oof import oof_domain_weights
from agent1.eval.adaptation import company_statistics,paired_improvement
from run_t1 import snapshots,censor,domain_weights
from run_da_paired import hazard_prediction
from run_collection_policy import file_hash


def main():
    directory=OUT/'t1/IW_oof';directory.mkdir(exist_ok=True)
    origin=pd.Timestamp('2024-07-01');visible=origin-pd.DateOffset(months=6);budget=40000
    files=['scripts/run_iw_oof.py','agent1/models/domain_weight_oof.py','scripts/run_t1.py','scripts/run_da_paired.py',
        'agent1/models/features.py','agent1/models/t1.py','agent1/eval/adaptation.py']
    protocol=dict(complete=False,source_budget=budget,target_budget=budget,origin=str(origin.date()),months_history=6,
        domain_classifier='4 folds hold out complete firms within each domain, 200 trees, seed7; same probability/weight clips as original',
        fit='all 3 pooled models 300 rounds; same source/target sample and target weight as DA-paired M6',
        limitation='synthetic truth, repeated weekly cohorts, diagnostic ablation not source-policy selection; no automatic adoption; OOF is not proof of overlap or calibrated density ratios',
        test_used_for_selection=False,code_sha256={p:file_hash(ROOT/p) for p in files},
        input_sha256={f'{world}/{table}.parquet':file_hash(SYNTH/world/f'{table}.parquet')
            for world in ['src','tgt','sens_uk','sens_coface'] for table in ['invoices','payments','promises']})
    path=directory/'protocol.json';path.write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    source=censor(snapshots('src',pd.date_range('2019-07-01',origin-pd.Timedelta(days=7),freq='14D'),tag='DA_paired_source'),origin)
    source=source.sample(min(len(source),budget),random_state=7).reset_index(drop=True)
    metrics=[];comparisons=[];diagnostics=[];company=[]
    for world in ['tgt','sens_uk','sens_coface']:
        target=censor(snapshots(world,pd.date_range(visible+pd.Timedelta(days=28),origin-pd.Timedelta(days=7),freq='7D'),
            visible_from=visible,tag='DA_paired_adapt_M6'),origin)
        target=target.sample(min(len(target),budget),random_state=7).reset_index(drop=True)
        test=censor(snapshots(world,pd.date_range(origin,periods=52,freq='7D'),visible_from=visible,tag='DA_paired_test_M6'),'2025-12-31')
        test=test[test.issue_date>=origin].copy()
        in_sample=domain_weights(source,target);oof,detail=oof_domain_weights(source,target,origin=origin)
        for name,weights in [('in-sample',in_sample),('company-OOF',oof)]:
            diagnostics.append(dict(world=world,method=name,n_source=len(source),n_target=len(target),weight_min=weights.min(),
                weight_max=weights.max(),weight_std=weights.std(),effective_sample_size=weights.sum()**2/np.square(weights).sum(),
                oof_domain_AUC=detail['oof_domain_AUC'] if name=='company-OOF' else np.nan))
        (directory/f'folds_{world}.json').write_text(json.dumps(detail,indent=2),encoding='utf-8')
        pooled=pd.concat([source,target],ignore_index=True);target_weight=np.full(len(target),max(1.,.3*len(source)/len(target)))
        parts=[]
        for name,weights in [('pooled',np.ones(len(source))),('IW-in-sample',in_sample),('IW-company-OOF',oof)]:
            model=t1.HazardGBM(rounds=300).fit(pooled,weight=np.r_[weights,target_weight]);Q,P=hazard_prediction(model,test)
            grouped=company_statistics(test,Q,P);grouped['model']=name;parts.append(grouped)
            metrics.append(dict(world=world,model=name,n_test=len(test),n_source=len(source),n_target=len(target),
                pinball_avg=grouped.pinball_sum.sum()/grouped.n.sum(),test_used_for_selection=False,
                measurement_version='IW-company-OOF-M6-locked-budget-v1-fullweek'))
            del model;gc.collect()
        current=pd.concat(parts,ignore_index=True)
        for baseline in ['pooled','IW-in-sample']:
            effect=paired_improvement(current,'IW-company-OOF',baseline,'pinball_sum')
            comparisons.append(dict(world=world,model='IW-company-OOF',baseline=baseline,**effect,
                status='supported' if effect['improvement_ci_low']>0 else 'rejected' if effect['improvement_ci_high']<0 else 'not_demonstrated',
                test_used_for_selection=False,measurement_version='IW-company-OOF-M6-locked-budget-v1-fullweek'))
        current['world']=world;company.append(current)
        pd.DataFrame(metrics).to_csv(directory/'metrics.csv',index=False)
        pd.DataFrame(comparisons).to_csv(directory/'comparisons.csv',index=False)
        pd.DataFrame(diagnostics).to_csv(directory/'weight_diagnostics.csv',index=False)
        pd.concat(company,ignore_index=True).to_csv(directory/'company_losses.csv',index=False)
        print(world,'OOF scored',flush=True);del target,test,pooled,current,parts;gc.collect()
    protocol.update(complete=True,metrics_sha256=file_hash(directory/'metrics.csv'))
    path.write_text(json.dumps(protocol,indent=2),encoding='utf-8')


if __name__=='__main__':main()
