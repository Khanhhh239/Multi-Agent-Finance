"""Kiểm định chính sách bằng công ty nguồn giữ lại; không đọc tgt/sens hoặc điểm B."""
import gc
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.models import t1
from agent1.paths import SYNTH,OUT
from run_t1 import snapshots,censor,score


def prediction(model,test):
    h=model.hazards(test);p,s=t1.pmf_from_hazard(h)
    return dict(Q=t1.quantiles_from_hazard(h),P=p,cdf=1-s)


def main():
    origin=pd.Timestamp('2024-07-01'); budget=20000
    firms=sorted(pd.read_parquet(SYNTH/'src/firms.parquet').firm_id)
    training,validation=firms[:-8],firms[-8:]
    cuts=pd.date_range('2019-07-01',origin-pd.Timedelta(days=7),freq='28D')
    source=censor(snapshots('src',cuts,firms=training,tag='onboarding_pretrain'),origin)
    source=source.sample(min(budget,len(source)),random_state=7)
    model=t1.HazardGBM(dict(num_leaves=31,min_data_in_leaf=50),rounds=300).fit(source)
    del source;gc.collect()
    rows=[];rules=[]
    for months in [0,3,6,12,24]:
        visible=origin-pd.DateOffset(months=months)
        test=censor(snapshots('src',pd.date_range(origin,periods=13,freq='14D'),
            firms=validation,visible_from=visible,tag=f'onboarding_validation_M{months}'),'2025-12-31')
        test=test[test.issue_date>=origin]
        preds={'zero-shot':prediction(model,test),'B1d':dict(Q=t1.b1_dist(test))}
        n_train=0
        if months:
            cuts=pd.date_range(visible+pd.Timedelta(days=28),origin-pd.Timedelta(days=7),freq='14D')
            history=censor(snapshots('src',cuts,firms=validation,visible_from=visible,tag=f'onboarding_adapt_M{months}'),origin)
            history=history.sample(min(budget,len(history)),random_state=7);n_train=len(history)
            target=t1.HazardGBM(dict(num_leaves=31,min_data_in_leaf=30),rounds=200).fit(history)
            preds['target-only']=prediction(target,test)
            fine=t1.HazardGBM(dict(learning_rate=.02),rounds=100).fit(history,init_model=model.booster)
            preds['fine-tune']=prediction(fine,test)
            preds['ensemble-b1d']=dict(Q=(preds['fine-tune']['Q']+preds['B1d']['Q'])/2)
            del history,target,fine
        result=score({'B1d-cust-quantiles' if k=='B1d' else k:v for k,v in preds.items()},test,'onboarding_source_company_holdout')
        result['months_history']=months;result['n_target_rows']=n_train
        result['selection_domain']='src_company_holdout';result['target_used']=False
        rows.append(result)
        eligible=result[(result.model!='B1d-cust-quantiles')&(result.cov80>=.6)]
        winner=eligible.sort_values('pinball_avg').model.iloc[0] if len(eligible) else 'zero-shot'
        rules.append(dict(months_history=months,min_rows=0 if winner=='zero-shot' else n_train,strategy=winner))
        pd.concat(rows).to_csv(OUT/'t1/onboarding_source_validation.csv',index=False)
        print(months,winner,flush=True)
    # Chưa kiểm định trên shift AUC>0.9; không suy diễn tác dụng IW/fine-tune ở đó.
    policy=dict(selection_domain='src_company_holdout',target_used=False,training_firms=training,
        validation_firms=validation,max_validated_domain_auc=.9,domain_auc_limit_status='predeclared_applicability_limit_not_empirical_guarantee',
        seed=7,training_budget=budget,rules=rules,research_only=True)
    (OUT/'t1/onboarding_source_policy.json').write_text(json.dumps(policy,indent=2),encoding='utf-8')


if __name__=='__main__':main()
