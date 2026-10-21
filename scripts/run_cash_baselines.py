"""WP-6.6: ETS/ARIMA/B0 trên cùng 14 DN×52 tuần với E2E, không tune theo test."""
import gc
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import OUT,SYNTH,ROOT
from agent1.models.cash_baselines import time_series_paths,due_spreadsheet
from agent1.models.t6_cash import collection_kernel
from agent1.eval.cluster import mean_ci
from agent1.eval.metrics import pinball
import run_t6 as R6
from run_t1 import snapshots


def main():
    world='e2e_observed_tgt';origin=pd.Timestamp('2024-07-01')
    visible=origin-pd.DateOffset(months=12)
    target=OUT/'t6/traditional';target.mkdir(exist_ok=True)
    inv=pd.read_parquet(SYNTH/world/'invoices.parquet')
    out=pd.read_parquet(SYNTH/world/'outflows.parquet')
    daily=pd.read_parquet(SYNTH/'tgt/daily_cash.parquet')
    reference=pd.read_parquet(OUT/'e2e/protocol/t6_predictions.parquet')
    reference=reference[reference.model=='MC-copula-t + ACI'].copy()
    if reference.firm_id.nunique()!=14 or reference.cutoff.nunique()!=52:
        raise ValueError('Cần E2E đầy đủ 14 DN × 52 tuần làm đối chiếu')
    cuts=pd.date_range(origin,periods=52,freq='7D')
    frame=snapshots(world,cuts,visible_from=visible,tag='test_M12')
    rows,diagnostics,shortfalls=[],[],[]
    for firm_index,firm in enumerate(sorted(inv.firm_id.unique())):
        context=R6.firm_context(world,firm,inv,out,daily)
        for t_index,cutoff in enumerate(cuts):
            began=time.monotonic();B0,truth=R6.truth_path(context,cutoff)
            known=R6.known_outflows(context,cutoff);scale=max(known.mean(),1.)
            history=R6.weekly(context['net'],cutoff-pd.Timedelta(days=364),k_weeks=52)
            ref=reference[(reference.firm_id==firm)&(reference.cutoff==cutoff)].sort_values('k')
            if len(ref)!=13 or not np.allclose(truth/scale,ref.y.to_numpy(),rtol=1e-9,atol=1e-8):
                raise ValueError('Cohort/số dư/chuẩn hoá lệch E2E; không ghép bảng')
            for model in ['ETS','ARIMA']:
                net,info=time_series_paths(history,model,n=1000,seed=7000+100*firm_index+t_index)
                balances=B0+net.cumsum(1);Q=np.quantile(balances,[.1,.5,.9],axis=0).T
                for k in range(13):
                    rows.append(dict(model=model+' (declared fallback)',firm_id=firm,cutoff=cutoff,k=k+1,
                        y=truth[k]/scale,lo=Q[k,0]/scale,med=Q[k,1]/scale,hi=Q[k,2]/scale))
                shortfalls.append(dict(model=model,firm_id=firm,cutoff=cutoff,y4=float(truth[:4].min()<0),
                    y13=float(truth.min()<0),p4=float((balances[:,:4].min(1)<0).mean()),p13=float((balances.min(1)<0).mean())))
                diagnostics.append(dict(firm_id=firm,cutoff=cutoff,**info,seconds=time.monotonic()-began))
            snap=frame[(frame.firm_id==firm)&(frame.cutoff==cutoff)]
            historical_inv=context['inv'][context['inv'].issue_date<=cutoff]
            kernel=collection_kernel(historical_inv,cutoff)
            mean_revenue=historical_inv.loc[historical_inv.issue_date>cutoff-pd.Timedelta(days=91),'amount_gross'].sum()/13
            point=due_spreadsheet(snap,known,kernel,mean_revenue,B0)
            for k in range(13):rows.append(dict(model='B0 due spreadsheet',firm_id=firm,cutoff=cutoff,k=k+1,
                y=truth[k]/scale,lo=point[k]/scale,med=point[k]/scale,hi=point[k]/scale))
        print(firm,'52 cutoffs scored',flush=True);gc.collect()
    predictions=pd.DataFrame(rows)
    predictions.to_parquet(target/'predictions.parquet',index=False)
    pd.DataFrame(diagnostics).to_csv(target/'fit_diagnostics.csv',index=False)
    pd.DataFrame(shortfalls).to_csv(target/'shortfall_predictions.csv',index=False)
    combined=pd.concat([reference,predictions],ignore_index=True);summary=[]
    for (model,horizon),part in combined.assign(horizon=lambda d:np.where(d.k<=4,'w1-4','w5-13')).groupby(['model','horizon']):
        coverage=part.y.between(part.lo,part.hi).astype(float)
        interval=part.hi-part.lo+10*(part.lo-part.y).clip(lower=0)+10*(part.y-part.hi).clip(lower=0)
        ci=mean_ci(coverage,part.firm_id)
        interval_ci=mean_ci(interval,part.firm_id)
        matched=part.merge(reference[['firm_id','cutoff','k','y','lo','hi']],on=['firm_id','cutoff','k'],
                           suffixes=('','_reference'),validate='one_to_one')
        baseline_interval=(matched.hi_reference-matched.lo_reference+
            10*(matched.lo_reference-matched.y_reference).clip(lower=0)+10*(matched.y_reference-matched.hi_reference).clip(lower=0))
        current_interval=(matched.hi-matched.lo+10*(matched.lo-matched.y).clip(lower=0)+10*(matched.y-matched.hi).clip(lower=0))
        improvement=mean_ci(current_interval,matched.firm_id,baseline=baseline_interval)
        loss=np.mean([pinball(part.y,part[c],a) for c,a in [('lo',.1),('med',.5),('hi',.9)]])
        summary.append(dict(model=model,horizon=horizon,n=len(part),n_firms=part.firm_id.nunique(),
            cov80=coverage.mean(),cov80_ci_low=ci['ci_low'],cov80_ci_high=ci['ci_high'],IS80=interval.mean(),
            IS80_ci_low=interval_ci['ci_low'],IS80_ci_high=interval_ci['ci_high'],
            vs_E2E_ACI_improvement_pct=improvement['improvement_pct'],
            vs_E2E_ACI_improvement_ci_low=improvement['improvement_ci_low'],
            vs_E2E_ACI_improvement_ci_high=improvement['improvement_ci_high'],
            MAE_p50=(part.y-part.med).abs().mean(),pinball=loss,bootstrap_n=300,
            measurement_version='cash-traditional-same-E2E-cohort-v1',test_used_for_selection=False))
    summary=pd.DataFrame(summary)
    summary.to_csv(target/'metrics.csv',index=False)
    files=['scripts/run_cash_baselines.py','agent1/models/cash_baselines.py','scripts/run_t6.py','agent1/models/t6_cash.py']
    protocol=dict(complete=True,n_firms=14,n_weeks=52,n_paths=1000,training='rolling 52 net-cash weeks ending at cutoff; observed balance B0',
        ETS='additive damped trend, no seasonal component, bootstrap fitted innovations',ARIMA='(1,0,1) constant; Gaussian conditional path simulation',
        fallback='nonconvergence or nonfinite paths -> historical mean plus iid bootstrap residuals, counted explicitly',
        B0='point due dates + known-outflows estimate + historical revenue mean through observed collection kernel',
        parameters_selected_on_test=False,comparison='saved estimated-T9 E2E ACI, exact truth/cohort/normalization match asserted',
        limitation='synthetic;traditional models do not receive obligation covariates;B0 excludes unplanned capex and owner draw;Chronos not measured',
        code_sha256=hashlib.sha256(b''.join((ROOT/p).read_bytes() for p in files)).hexdigest(),
        reference_sha256=hashlib.sha256((OUT/'e2e/protocol/t6_predictions.parquet').read_bytes()).hexdigest(),
        input_sha256={str(p.relative_to(SYNTH)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [SYNTH/'tgt/daily_cash.parquet',*[SYNTH/world/f'{table}.parquet'
                for table in ['invoices','payments','promises','outflows']]]})
    (target/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')


if __name__=='__main__':main()
