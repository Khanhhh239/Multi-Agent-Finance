"""WP-2.1: ablation cohort trước, tách ngày và độ trễ công bố giả định."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.isotonic import IsotonicRegression
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.data.real_loaders import sba_7a
from agent1.data.sba_macro import prior_cohort_features
from agent1.paths import RAW,OUT,ROOT
from agent1.threads import NT
from agent1.eval.cluster import mean_ci
from run_t2_t3 import CAT,NUM,prob_metrics


def sha(path):
    digest=hashlib.sha256()
    with open(path,'rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def main():
    directory=OUT/'t2_t3';raw=[RAW/'sba'/name for name in ['FOIA_7a_FY2010_FY2019.csv','FOIA_7a_FY2020_Present.csv']]
    protocol=dict(complete=False,publication_lag_days=90,cohort='[approval-2 calendar years, approval-1 calendar year)',
        denominator='all approvals with valid date; no filtering on final LoanStatus',
        train='FY<=2013',calibration='FY2014',test='FY2018-2022',horizon_years=3,
        limitation='SBA retrospective extract, no historical release vintages; 90d is assumed reporting lag; borrower-name/address bootstrap proxy; US loans are not VN invoices',
        test_used_for_selection=False,source_sha256={p.name:sha(p) for p in raw},
        code_sha256={str(p):sha(ROOT/p) for p in ['scripts/run_sba_macro.py','agent1/data/sba_macro.py','agent1/data/real_loaders.py','scripts/run_t2_t3.py']})
    path=directory/'sba_macro_protocol.json';path.write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    history=pd.concat([pd.read_csv(p,usecols=['ApprovalDate','ChargeOffDate'],low_memory=False) for p in raw],ignore_index=True)
    metrics=[];calibrations=[];comparisons=[]
    for policy in ['drop','keep','censor']:
        frame=sba_7a(exempt=policy);frame=frame[frame.label_observed].copy();frame['y']=frame.y.astype(int)
        frame['is_franchise']=frame.FranchiseCode.notna().astype(int)
        frame['out_of_state_lender']=(frame.BankState!=frame.BorrState).astype(int)
        frame=frame.join(prior_cohort_features(history,frame.ApprovalDate))
        for col in CAT:frame[col]=frame[col].astype(str).fillna('NA').astype('category')
        fy=frame.ApprovalFY.astype(int);train=frame[fy<=2013];cal=frame[fy==2014];test=frame[fy.between(2018,2022)]
        predictions={}
        for name,extra in [('without_prior_cohort',[]),('with_prior_cohort',['prior_cohort_chgoff_rate','prior_cohort_n','prior_cohort_missing'])]:
            feats=CAT+NUM+extra
            params=dict(objective='binary',learning_rate=.05,num_leaves=63,min_data_in_leaf=200,feature_fraction=.8,
                bagging_fraction=.8,bagging_freq=1,lambda_l2=5.,verbose=-1,num_threads=NT,seed=1)
            model=lgb.train(params,lgb.Dataset(train[feats],train.y),800,valid_sets=[lgb.Dataset(cal[feats],cal.y)],
                callbacks=[lgb.early_stopping(50,verbose=False)])
            iso=IsotonicRegression(out_of_bounds='clip').fit(model.predict(cal[feats]),cal.y)
            p=iso.predict(model.predict(test[feats]));predictions[name]=p
            for stratum,mask in [('all',np.ones(len(test),dtype=bool)),('term<=120',test.TermInMonths.le(120).to_numpy()),('term>120',test.TermInMonths.gt(120).to_numpy())]:
                y=test.y.to_numpy()[mask];pp=p[mask];ci=mean_ci((y-pp)**2,test.borrower_cluster.to_numpy()[mask])
                metrics.append(dict(exempt_policy=policy,model=name,stratum=stratum,n_test=int(mask.sum()),
                    bootstrap_n=300,Brier_ci_low=ci['ci_low'],Brier_ci_high=ci['ci_high'],**prob_metrics(y,pp),
                    measurement_version='sba-prior-cohort-asof-lag90-v1'))
            byfy=pd.DataFrame(dict(fy=test.ApprovalFY,y=test.y,p=p)).groupby('fy').agg(base_rate=('y','mean'),mean_p=('p','mean'),n=('y','size')).reset_index()
            byfy['relative_calibration_error']=(byfy.mean_p-byfy.base_rate).abs()/byfy.base_rate.clip(lower=1e-12)
            byfy['model']=name;byfy['exempt_policy']=policy;calibrations.append(byfy)
            print(policy,name,'scored',model.best_iteration,flush=True)
        base=(test.y.to_numpy()-predictions['without_prior_cohort'])**2
        candidate=(test.y.to_numpy()-predictions['with_prior_cohort'])**2
        ci=mean_ci(candidate,test.borrower_cluster,baseline=base)
        comparisons.append(dict(exempt_policy=policy,metric='Brier',**ci,
            decision='supported' if ci['improvement_ci_low']>0 else 'rejected' if ci['improvement_ci_high']<0 else 'not_demonstrated',test_used_for_selection=False))
        pd.DataFrame(metrics).to_csv(directory/'sba_macro_metrics.csv',index=False)
        pd.concat(calibrations,ignore_index=True).to_csv(directory/'sba_macro_by_fy.csv',index=False)
        pd.DataFrame(comparisons).to_csv(directory/'sba_macro_comparisons.csv',index=False)
    protocol.update(complete=True,metrics_sha256=sha(directory/'sba_macro_metrics.csv'))
    path.write_text(json.dumps(protocol,indent=2),encoding='utf-8')


if __name__=='__main__':main()
