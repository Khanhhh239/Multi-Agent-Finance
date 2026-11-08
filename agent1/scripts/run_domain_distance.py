"""WP-3.4: AUC phân biệt miền và top-10 đặc trưng, giữ lại nguyên công ty."""
import gc
import hashlib
import json
from pathlib import Path
import sys

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import OUT,ROOT
from agent1.threads import NT
from agent1.models.features import FEATURES,SnapshotBuilder
from agent1.data.real_loaders import customer_invoices
from agent1.eval.domain_distance import split_companies,auc_cluster_ci
from run_t1 import load_world


def domain_rows(world,origin):
    if world=='Customer Invoices':inv,pay,prom=customer_invoices(),None,None
    else:inv,pay,prom=load_world(world)
    builder=SnapshotBuilder(inv,pay,prom);parts=[]
    for cutoff in pd.date_range(end=pd.Timestamp(origin),periods=6,freq='28D'):
        part=builder.snapshot(cutoff)
        if not len(part):continue
        part=part[['firm_id',*FEATURES]].copy()
        if len(part)>8000:part=part.sample(8000,random_state=7)
        parts.append(part)
    if not parts:raise ValueError(f'{world}: không có snapshot')
    frame=pd.concat(parts,ignore_index=True)
    return frame


def main():
    directory=OUT/'t1';rows=[];importance=[];protocol=[]
    for target,origin in [('tgt','2024-07-01'),('sens_uk','2024-07-01'),('sens_coface','2024-07-01'),('Customer Invoices','2019-10-01')]:
        left=domain_rows('src',origin);right=domain_rows(target,origin)
        a,b=split_companies(left);c,d=split_companies(right)
        protocol.append(dict(domain=target,origin=origin,source_train_firms=sorted(a.firm_id.unique()),source_test_firms=sorted(b.firm_id.unique()),
                             target_train_firms=sorted(c.firm_id.unique()),target_test_firms=sorted(d.firm_id.unique())))
        for feature_set in ['all_T1','shared_without_promises']:
            feats=FEATURES if feature_set=='all_T1' else [f for f in FEATURES if 'promis' not in f]
            train=pd.concat([a.assign(domain=0),c.assign(domain=1)],ignore_index=True)
            test=pd.concat([b.assign(domain=0),d.assign(domain=1)],ignore_index=True)
            n=min(20000,*(train.groupby('domain').size()))
            train=train.groupby('domain',group_keys=False).sample(n=n,random_state=7)
            model=lgb.LGBMClassifier(n_estimators=150,num_leaves=15,min_child_samples=100,learning_rate=.05,
                                     n_jobs=NT,random_state=7,verbosity=-1)
            model.fit(train[feats],train.domain)
            p=model.predict_proba(test[feats])[:,1]
            low,high=auc_cluster_ci(test.domain,p,test.domain,test.firm_id)
            rows.append(dict(domain=target,feature_set=feature_set,AUC=roc_auc_score(test.domain,p),AUC_ci_low=low,AUC_ci_high=high,
                             n_train=len(train),n_test=len(test),n_source_test_firms=b.firm_id.nunique(),n_target_test_firms=d.firm_id.nunique(),
                             bootstrap_n=300,target_used_for_policy_selection=False,measurement_version='domain-snapshot-company-heldout-v1',
                             limitation='domain_diagnostic_not_performance'+(';ledger_labels;only_one_heldout_real_company' if target=='Customer Invoices' else '')))
            gains=model.booster_.feature_importance(importance_type='gain');order=np.argsort(gains)[::-1][:10]
            for rank,index in enumerate(order,1):
                importance.append(dict(domain=target,feature_set=feature_set,rank=rank,feature=feats[index],gain=gains[index],
                                       measurement_version='domain-snapshot-company-heldout-v1'))
            pd.DataFrame(rows).to_csv(directory/'domain_distance.csv',index=False)
            pd.DataFrame(importance).to_csv(directory/'domain_top_features.csv',index=False)
        print(target,'done',flush=True);del left,right,a,b,c,d,train,test;gc.collect()
    signature=hashlib.sha256((ROOT/'agent1/models/features.py').read_bytes()).hexdigest()
    (directory/'domain_distance_protocol.json').write_text(json.dumps(dict(splits=protocol,feature_code_sha256=signature,
        test_used_for_model_or_policy_selection=False,seed=7,rounds=150),indent=2),encoding='utf-8')


if __name__=='__main__':main()
