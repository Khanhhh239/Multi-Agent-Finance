"""WP-6.5: chọn rho_p/rho_c bằng IS nguồn; kiểm cặp trên T6 đích, không ACI."""
import gc
import hashlib
import json
from pathlib import Path
import sys
import lightgbm as lgb
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH,ROOT,OUT,PROCESSED
from agent1.models.features import SnapshotBuilder,FEATURES
from agent1.models.t1 import HazardGBM,pmf_from_hazard,WEEK_FEATS
from agent1.models.t6_cash import simulate,collection_kernel
from agent1.eval.collection_policy import remaining_ar
from agent1.eval.cluster import mean_ci
from agent1.eval.copula_selection import select_copulas
from agent1.eval.cash_cohort import forecast_pmf,validate_cash_cohort
from run_collection_policy import training_rows,file_hash,revenue_intervals,projected_table
import run_t6 as R6


def tables(world,firms=None):
    filters=[('firm_id','in',firms)] if firms else None
    columns={'invoices':['invoice_id','firm_id','customer_id','issue_date','due_date','term_days','amount_gross',
        'paid_date_true','writeoff_date','credit_note','credit_note_date'],
        'payments':['firm_id','invoice_id','pay_date_true','amount','kind'],
        'daily_cash':['firm_id','date','inflow_ar','inflow_other','outflow','owner_draw','balance'],
        'outflows':['firm_id','date','category','amount','known_at']}
    result={}
    for table,keep in columns.items():
        path=SYNTH/world/f'{table}.parquet'
        if filters:
            import pyarrow.parquet as pq
            actual=pq.ParquetFile(path).schema.names
            result[table]=pd.read_parquet(path,columns=[c for c in keep if c in actual],filters=filters)
        else:result[table]=projected_table(path,keep)
    return result


def portfolio_rows(world,firm,data,cuts,model,choices,*,week_offset=0):
    inv=data['invoices'][data['invoices'].firm_id==firm];pay=data['payments'][data['payments'].firm_id==firm]
    builder=SnapshotBuilder(inv,pay,None);context=R6.firm_context(world,firm,data['invoices'],data['outflows'],data['daily_cash'])
    rows=[]
    for week,cutoff in enumerate(cuts):
        snapshot=builder.snapshot(cutoff)
        snapshot['amount_open']=snapshot.invoice_id.map(remaining_ar(inv,pay,cutoff)).fillna(0.)
        P=forecast_pmf(model,snapshot)
        B0,truth=R6.truth_path(context,cutoff);known=R6.known_outflows(context,cutoff);scale=max(float(known.mean()),1.)
        history=context['capex'];history=history[(history.date<cutoff)&(history.date>=cutoff-pd.Timedelta(days=365))]
        args=dict(B0=B0,known_out=known,rev_q=revenue_intervals(inv,cutoff),kernel=collection_kernel(inv,cutoff),
            capex_rate=len(history)/(365/7),capex_sizes=history.amount.to_numpy(),n=512,seed=7100+week+week_offset,nu=4,**R6.draw_policy(context,cutoff))
        for name,(rho,rho_c) in choices.items():
            balance=simulate(snapshot,P,rho=rho,rho_customer=rho_c,**args)[0]
            quantiles=np.quantile(balance,[.1,.5,.9],axis=0).T/scale
            for k,(lo,med,hi) in enumerate(quantiles):
                y=float(truth[k]/scale)
                rows.append(dict(world=world,firm_id=firm,cutoff=cutoff,k=k+1,model=name,rho=rho,rho_customer=rho_c,
                    y=y,lo=lo,med=med,hi=hi,IS80=hi-lo+10*max(lo-y,0)+10*max(y-hi,0),
                    outcome_end=cutoff+pd.Timedelta(days=7*(k+1))))
    return rows


def summarize(frame):
    validate_cash_cohort(frame,14,52,3)
    metrics=[]
    for horizon,mask in [('all',frame.k>0),('w1-4',frame.k<=4),('w5-13',frame.k>4)]:
        part=frame[mask];base=part[part.model=='source_selected_one_factor'].set_index(['firm_id','cutoff','k']).sort_index()
        for name,group in part.groupby('model'):
            group=group.set_index(['firm_id','cutoff','k']).sort_index().reindex(base.index)
            if group.y.isna().any() or not np.array_equal(group.y.to_numpy(),base.y.to_numpy()):raise ValueError('Cohort copula lệch')
            firms=group.index.get_level_values('firm_id');ci=mean_ci(group.IS80,firms,baseline=base.IS80)
            cov=group.y.between(group.lo,group.hi).astype(float);coverage=mean_ci(cov,firms)
            metrics.append(dict(horizon=horizon,model=name,n=len(group),n_firms=len(set(firms)),IS80=group.IS80.mean(),
                vs_one_factor_improvement_pct=ci['improvement_pct'],vs_one_factor_improvement_ci_low=ci['improvement_ci_low'],
                vs_one_factor_improvement_ci_high=ci['improvement_ci_high'],cov80=cov.mean(),cov80_ci_low=coverage['ci_low'],
                cov80_ci_high=coverage['ci_high'],bootstrap_n=300,target_used_for_selection=False,
                measurement_version='copula-source-grid-full-cohort-v2-fullweek'))
    return pd.DataFrame(metrics)


def main():
    directory=OUT/'t6/copula_hierarchy';directory.mkdir(exist_ok=True)
    policy=OUT/'t6/collection_policy';checkpoint=json.loads((policy/'checkpoint.json').read_text(encoding='utf-8'))
    if not json.loads((policy/'protocol.json').read_text(encoding='utf-8')).get('complete'):raise ValueError('Thiếu mô hình T1 trước test')
    model_path=OUT/'t6/policy_models/T1_oracle_policy.txt'
    if file_hash(model_path)!=checkpoint['model_sha256']:raise ValueError('Mô hình T1 không khớp checkpoint')
    for name,digest in checkpoint['signature']['inputs'].items():
        if file_hash(SYNTH/name)!=digest:raise ValueError('Dữ liệu chính sách đã đổi')
    for name,digest in checkpoint['signature']['code'].items():
        if name.startswith('agent1') and file_hash(ROOT/name)!=digest:raise ValueError('Mã đặc trưng/mô phỏng đã đổi')
    files=['scripts/run_copula_hierarchy.py','agent1/eval/copula_selection.py','scripts/run_collection_policy.py','scripts/run_t6.py',
        'agent1/models/features.py','agent1/models/t1.py','agent1/models/t6_cash.py','agent1/eval/collection_policy.py','agent1/eval/cash_cohort.py']
    signature=dict(code={name:file_hash(ROOT/name) for name in files},data=checkpoint['signature']['inputs'],target_model=file_hash(model_path))
    digest=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()[:12]
    cache=PROCESSED/('copula_hierarchy_'+digest);cache.mkdir(exist_ok=True)
    origin=pd.Timestamp('2024-07-01');fit_end=pd.Timestamp('2022-12-31')
    protocol=dict(complete=False,signature=signature,nu=4,n_paths=512,calibration='4 source firms, 13 weekly origins Jan-Mar2023, outcomes end Jun2023; source model trained labels <=2022-12-31',
        criterion='paired IS80 improvement on target, CI by firm; no automatic adoption',target_used_for_selection=False,
        limitation='oracle receipt histories, historical revenue quantiles, raw intervals without ACI, 20k-source/20k-target frozen T1; separate from T9 E2E; fixed grid has different search sizes',choices={})
    protocol_path=directory/'protocol.json';protocol_path.write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    source=training_rows('src',pd.date_range('2019-07-01',fit_end-pd.Timedelta(days=7),freq='14D'),fit_end,None,cache/'src.parquet')
    source_model=HazardGBM(rounds=300).fit(source);protocol['n_source_train']=len(source);del source;gc.collect()
    grid={f'p{rp}_c{rc}':(rp,rc) for rp in [0.,.15,.3] for rc in [0.,.1,.25]}
    source_data=tables('src',[f'F{i:03d}' for i in range(4)]);cal=[]
    for firm in sorted(source_data['invoices'].firm_id.unique()):
        cal.extend(portfolio_rows('src',firm,source_data,pd.date_range('2023-01-02',periods=13,freq='7D'),source_model,grid))
        print('copula source calibration',firm,flush=True)
    calibration=pd.DataFrame(cal);calibration.to_parquet(cache/'calibration_predictions.parquet',index=False)
    calibration.groupby(['rho','rho_customer'],as_index=False).agg(IS80=('IS80','mean'),n=('IS80','size')).to_csv(directory/'source_grid.csv',index=False)
    choices=select_copulas(calibration,test_origin=origin);choices['fixed_one_factor']=(.15,0.)
    protocol['choices']=choices;print('selected',choices,flush=True)
    del source_data,source_model,cal,calibration;gc.collect()
    target=HazardGBM();target.booster=lgb.Booster(model_file=str(model_path))
    if target.booster.feature_name()!=FEATURES+WEEK_FEATS:raise ValueError('Sai bộ đặc trưng T1')
    data=tables('tgt');rows=[]
    for firm in sorted(data['invoices'].firm_id.unique()):
        rows.extend(portfolio_rows('tgt',firm,data,pd.date_range(origin,periods=52,freq='7D'),target,choices))
        pd.DataFrame(rows).to_parquet(directory/'predictions.parquet',index=False)
        print('copula target',firm,flush=True)
    summarize(pd.DataFrame(rows)).to_csv(directory/'metrics.csv',index=False)
    protocol.update(complete=True,metrics_sha256=file_hash(directory/'metrics.csv'))
    protocol_path.write_text(json.dumps(protocol,indent=2),encoding='utf-8')


if __name__=='__main__':main()
