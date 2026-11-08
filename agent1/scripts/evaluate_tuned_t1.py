"""Đối chứng mặc định/tuned cùng ngân sách nguồn, tham số chỉ chọn trên cal."""
import gc
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.models import t1
from agent1.eval.cluster import mean_ci
from agent1.paths import OUT
from run_t1 import snapshots,censor,score


def main():
    directory=OUT/'t1'
    config=json.loads((directory/'best_params.json').read_text(encoding='utf-8'))
    fingerprint=hashlib.sha256(b''.join((Path(t1.__file__).parent/name).read_bytes()
        for name in ['t1.py','features.py'])).hexdigest()[:12]
    if config['test_used'] or not config.get('search_complete',False) or config['source_fingerprint'] != fingerprint:
        raise ValueError('Tham số không hợp lệ cho phiên bản mã hoặc đã dùng test')
    origin=pd.Timestamp(config['origin']); cal_lo=origin-pd.Timedelta(days=183);cal_hi=origin-pd.Timedelta(days=120)
    cut=pd.date_range('2019-07-01',origin+pd.Timedelta(days=175),freq='7D')
    cut=[T for T in cut if T>=cal_lo or T.isocalendar().week%2==0]
    source=snapshots('src',cut,tag='tuned_comparison')
    train=censor(source[source.cutoff<cal_lo],cal_lo)
    train=train.sample(min(len(train),config['max_train']),random_state=config['seed'])
    calibration=censor(source[source.cutoff.between(cal_lo,cal_hi)],origin)
    test=censor(source[source.cutoff>=origin],'2025-12-31')
    del source;gc.collect()
    predictions={};models={}
    for name,parameters in [('DH-GBM default (equal budget)',{}),('DH-GBM tuned',config['params'])]:
        model=t1.HazardGBM(parameters).fit(train)
        models[name]=model
        hazards=model.hazards(test);prob,survival=t1.pmf_from_hazard(hazards)
        predictions[name]=dict(Q=t1.quantiles_from_hazard(hazards),P=prob,cdf=1-survival)
        qhat=t1.cqr_fit_asym(calibration.remaining,t1.quantiles_from_hazard(model.hazards(calibration)))
        predictions[name+'+CQR']=dict(Q=t1.cqr_apply_asym(predictions[name]['Q'],qhat))
    predictions['B1-cust-median']=dict(Q=np.column_stack([t1.b1_predict(test)]*3))
    predictions['B1d-cust-quantiles']=dict(Q=t1.b1_dist(test))
    result=score(predictions,test,'source_tuned_equal_budget')
    result['n_train']=len(train);result['selection_origin']=str(origin.date())
    result['training_budget_limited']=True;result['test_used_for_selection']=False
    result['parameters_sha256']=hashlib.sha256((directory/'best_params.json').read_bytes()).hexdigest()
    y=np.minimum(test.remaining.to_numpy(),t1.CAP)
    def loss(q):
        err=y[:,None]-q
        return np.maximum(np.asarray(t1.QS)*err,(np.asarray(t1.QS)-1)*err).mean(1)
    base=loss(predictions['DH-GBM default (equal budget)']['Q'])
    for name in ['DH-GBM tuned','DH-GBM tuned+CQR']:
        ci=mean_ci(loss(predictions[name]['Q']),test.firm_id,baseline=base)
        for key in ['improvement_pct','improvement_ci_low','improvement_ci_high']:
            result.loc[result.model==name,'vs_default_'+key]=ci[key]
    result.to_csv(directory/'A_tuned_equal_budget.csv',index=False)
    print(result[['model','pinball_avg','cov80','ECE_4w']].to_string(),flush=True)


if __name__=='__main__':main()
