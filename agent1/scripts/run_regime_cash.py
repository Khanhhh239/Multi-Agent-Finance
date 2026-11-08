"""WP-7.4: T6 có/không RegimeController trong hai khủng hoảng, nguồn/cal đều trước test."""
import gc
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH,OUT,PROCESSED,ROOT
from agent1.models.features import SnapshotBuilder,FEATURES
from agent1.models.adaptive_features import AdaptiveSnapshotBuilder
from agent1.models.t1 import HazardGBM,pmf_from_hazard,_week_feats,WEEK_FEATS
from agent1.models.t6_cash import simulate,collection_kernel
from agent1.models.t7_portfolio import RegimeController
from agent1.eval.regime_control import payment_residual,PortfolioCUSUM,calibrate_portfolio,DelayedACI,remove_common_customer_residual
from agent1.eval.cluster import mean_ci
from agent1.eval.collection_policy import remaining_ar
from agent1.eval.cash_cohort import forecast_pmf,validate_cash_cohort
from run_collection_policy import training_rows,revenue_intervals,file_hash
import run_t6 as R6


def week1(model,frame):
    features=frame[model.feats].to_numpy(dtype='float32')
    weekly=_week_feats(frame,1)
    matrix=np.c_[features,np.column_stack([weekly[c] for c in WEEK_FEATS]).astype('float32')]
    return np.clip(model.booster.predict(matrix),1e-5,1-1e-5)


def fast_training(frame):
    parts=[];firms=sorted(frame.firm_id.unique())
    for start in range(0,len(firms),4):
        subset=firms[start:start+4];filters=[('firm_id','in',subset)]
        inv=pd.read_parquet(SYNTH/'src/invoices.parquet',filters=filters)
        pay=pd.read_parquet(SYNTH/'src/payments.parquet',filters=filters)
        builder=AdaptiveSnapshotBuilder(inv,pay,None)
        selected=frame[frame.firm_id.isin(subset)]
        for cutoff,base in selected.groupby('cutoff'):
            fast=builder.snapshot(cutoff);fast['_found']=1
            columns=list(dict.fromkeys(['invoice_id',*FEATURES,'f_resid_7d','top1','top2','_found']))
            combined=base.drop(columns=[*FEATURES,'top1','top2'],errors='ignore').merge(
                fast[[c for c in columns if c in fast]],on='invoice_id',how='left',validate='one_to_one')
            if combined._found.isna().any():raise ValueError('Cohort fast/default không khớp')
            parts.append(combined.drop(columns='_found'))
        del builder,inv,pay;gc.collect()
    combined=pd.concat(parts,ignore_index=True).set_index(['invoice_id','cutoff'])
    return combined.reindex(pd.MultiIndex.from_frame(frame[['invoice_id','cutoff']])).reset_index()


def source_calibration(model,origin):
    start=origin-pd.Timedelta(days=365);end=origin-pd.Timedelta(days=127)
    cuts=pd.date_range(start,end,freq='7D');firms=[f'F{i:03d}' for i in range(16)];rows=[]
    for offset in range(0,len(firms),4):
        filters=[('firm_id','in',firms[offset:offset+4])]
        inv=pd.read_parquet(SYNTH/'src/invoices.parquet',filters=filters)
        pay=pd.read_parquet(SYNTH/'src/payments.parquet',filters=filters)
        builder=SnapshotBuilder(inv,pay,None)
        for cutoff in cuts:
            frame=builder.snapshot(cutoff)
            if frame.empty:continue
            p=week1(model,frame);frame=frame.assign(_p=p)
            for firm,part in frame.groupby('firm_id'):
                rows.append(dict(firm_id=firm,date=cutoff+pd.Timedelta(days=7),
                    residual=payment_residual(part,part._p,cutoff+pd.Timedelta(days=7))))
        del builder,inv,pay;gc.collect()
    stream=pd.DataFrame(rows)
    if stream.date.max()>origin-pd.Timedelta(days=120):raise ValueError('Calibration chưa tách đủ 120 ngày')
    return calibrate_portfolio(stream),stream


def main():
    directory=OUT/'t7/regime_cash';directory.mkdir(exist_ok=True)
    inputs=[SYNTH/world/f'{table}.parquet' for world in ['src','tgt'] for table in ['invoices','payments','firms']]
    inputs.extend([SYNTH/'tgt/daily_cash.parquet',SYNTH/'tgt/outflows.parquet'])
    files=[ROOT/p for p in ['scripts/run_regime_cash.py','scripts/run_collection_policy.py','agent1/eval/regime_control.py',
        'agent1/models/features.py','agent1/models/adaptive_features.py','agent1/models/t1.py','agent1/models/t6_cash.py',
        'agent1/models/t7_portfolio.py','agent1/calendar_vn.py','scripts/run_t6.py']]
    signature=dict(code={str(p.relative_to(ROOT)):file_hash(p) for p in files},inputs={str(p.relative_to(SYNTH)):file_hash(p) for p in inputs})
    protocol=dict(complete=False,signature=signature,source_budget=20000,rounds=300,n_paths=512,
        calibration='source first16 firms; model labels end O-365; calibration week1 outcomes end <=O-120; all alarms counted false conservatively',
        mechanism='weekly expected-minus-observed payment counts; source-selected CUSUM; crisis uses source-trained EWM30/f_resid7 model and ACI gamma x3',
        criterion='controller overall cov80 >=.70 in both windows; compare paired covariance/IS without selecting from target',
        limitation='oracle receipt histories; bounded T1; historical revenue quantiles; separate from estimated-T9 E2E; no automatic adoption',
        test_used_for_selection=False,windows=[])
    (directory/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    digest=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()[:12]
    cache=PROCESSED/('regime_cash_'+digest);cache.mkdir(exist_ok=True)
    invoices=pd.read_parquet(SYNTH/'tgt/invoices.parquet');payments=pd.read_parquet(SYNTH/'tgt/payments.parquet')
    daily=pd.read_parquet(SYNTH/'tgt/daily_cash.parquet');outflows=pd.read_parquet(SYNTH/'tgt/outflows.parquet')
    rows=[];customer_rows=[]
    for start,end in [('2021-07-01','2021-10-31'),('2022-10-01','2023-06-30')]:
        origin=pd.Timestamp(start);fit_end=origin-pd.Timedelta(days=365)
        training=training_rows('src',pd.date_range('2019-07-01',fit_end-pd.Timedelta(days=7),freq='14D'),fit_end,None,cache/f'base_{start}.parquet')
        base=HazardGBM(rounds=300).fit(training)
        fast_frame=fast_training(training)
        fast=HazardGBM(rounds=300,feats=[*FEATURES,'f_resid_7d']).fit(fast_frame)
        del training,fast_frame;gc.collect()
        (h,calibration),stream=source_calibration(base,origin)
        calibration.to_csv(directory/f'calibration_{start}.csv',index=False);stream.to_csv(directory/f'source_residuals_{start}.csv',index=False)
        protocol['windows'].append(dict(start=start,end=end,training_label_end=str(fit_end.date()),
            calibration_label_end=str((origin-pd.Timedelta(days=120)).date()),cusum_h=h,controller_enabled=h is not None))
        for firm_index,firm in enumerate(sorted(invoices.firm_id.unique())):
            inv=invoices[invoices.firm_id==firm];pay=payments[payments.firm_id==firm]
            normal_builder=SnapshotBuilder(inv,pay,None);fast_builder=AdaptiveSnapshotBuilder(inv,pay,None)
            context=R6.firm_context('tgt',firm,invoices,outflows,daily)
            detector=PortfolioCUSUM(np.inf if h is None else h);controller=RegimeController()
            calibration_states={'without_controller':DelayedACI(),'with_controller':DelayedACI()}
            previous=None
            cuts=list(pd.date_range(origin-pd.Timedelta(days=119),origin-pd.Timedelta(days=7),freq='7D'))+list(pd.date_range(start,end,freq='7D'))
            for week,cutoff in enumerate(cuts):
                alarm=False
                if previous is not None:
                    previous_frame,previous_p=previous
                    residual=payment_residual(previous_frame,previous_p,cutoff)
                    alarm=detector.update(cutoff,residual)
                    if cutoff>=origin:
                        observed=((previous_frame.label_date>previous_frame.cutoff)&(previous_frame.label_date<=cutoff)).astype(float)
                        customer=previous_frame.assign(_p=previous_p,_y=observed)
                        for cid,part in customer.groupby('customer_id'):
                            customer_rows.append(dict(window=start,firm_id=firm,customer_id=cid,date=cutoff,
                                residual=(part._p.sum()-part._y.sum())/np.sqrt((part._p*(1-part._p)).sum()+1.),weight=len(part)))
                state=controller.update(cutoff,portfolio_alarm=alarm)
                snapshot=normal_builder.snapshot(cutoff)
                previous=None if snapshot.empty else (snapshot.copy(),week1(base,snapshot))
                if cutoff<origin:continue
                remaining=remaining_ar(inv,pay,cutoff)
                snapshot['amount_open']=snapshot.invoice_id.map(remaining).fillna(0.)
                B0,truth=R6.truth_path(context,cutoff);known=R6.known_outflows(context,cutoff);scale=max(known.mean(),1.)
                kernel=collection_kernel(inv,cutoff);revenue=revenue_intervals(inv,cutoff)
                capex=context['capex'];history=capex[(capex.date<cutoff)&(capex.date>=cutoff-pd.Timedelta(days=365))]
                args=dict(B0=B0,known_out=known,rev_q=revenue,kernel=kernel,capex_rate=len(history)/(365/7),
                    capex_sizes=history.amount.to_numpy(),n=512,rho=.15,seed=7000+firm_index*100+week,**R6.draw_policy(context,cutoff))
                normal_P=forecast_pmf(base,snapshot)
                normal_balance=simulate(snapshot,normal_P,**args)[0]
                crisis=state['state']=='crisis'
                if crisis:
                    fast_snapshot=fast_builder.snapshot(cutoff)
                    if not snapshot.invoice_id.reset_index(drop=True).equals(fast_snapshot.invoice_id.reset_index(drop=True)):raise ValueError('Cohort test lệch')
                    fast_snapshot['amount_open']=snapshot.amount_open.to_numpy()
                    controller_P=forecast_pmf(fast,fast_snapshot)
                    controlled_balance=simulate(fast_snapshot,controller_P,**args)[0]
                else:controlled_balance=normal_balance
                for name,balances in [('without_controller',normal_balance),('with_controller',controlled_balance)]:
                    adaptive=calibration_states[name]
                    adaptive.aci.gamma=state['aci_gamma'] if name=='with_controller' else .01
                    adaptive.reveal(cutoff)
                    for k in range(13):
                        lo,hi=adaptive.aci.interval(balances[:,k],k);median=float(np.median(balances[:,k]))
                        adaptive.add(cutoff,k,lo/scale,hi/scale,truth[k]/scale)
                        rows.append(dict(window=start,window_end=end,model=name,firm_id=firm,cutoff=cutoff,k=k+1,
                            y=truth[k]/scale,lo=lo/scale,med=median/scale,hi=hi/scale,state=state['state'],
                            alarm=alarm,fast_model_used=crisis and name=='with_controller'))
            print(start,firm,'regime scored',flush=True)
        pd.DataFrame(rows).to_parquet(directory/'predictions.parquet',index=False)
    frame=pd.DataFrame(rows);summary=[]
    for start,end in [('2021-07-01','2021-10-31'),('2022-10-01','2023-06-30')]:
        validate_cash_cohort(frame[frame.window==start],14,len(pd.date_range(start,end,freq='7D')),2)
    for window,window_frame in frame.groupby('window'):
        for horizon,mask in [('all',window_frame.k>0),('w1-4',window_frame.k<=4),('w5-13',window_frame.k>4)]:
            part=window_frame[mask];baseline=part[part.model=='without_controller'].set_index(['firm_id','cutoff','k'])
            for name,group in part.groupby('model'):
                group=group.set_index(['firm_id','cutoff','k']).reindex(baseline.index);firms=group.index.get_level_values('firm_id')
                coverage=group.y.between(group.lo,group.hi).astype(float);base_cov=baseline.y.between(baseline.lo,baseline.hi).astype(float)
                interval=group.hi-group.lo+10*(group.lo-group.y).clip(lower=0)+10*(group.y-group.hi).clip(lower=0)
                base_interval=baseline.hi-baseline.lo+10*(baseline.lo-baseline.y).clip(lower=0)+10*(baseline.y-baseline.hi).clip(lower=0)
                ci=mean_ci(coverage,firms);difference=mean_ci(coverage-base_cov,firms);score=mean_ci(interval,firms,baseline=base_interval)
                summary.append(dict(window=window,horizon=horizon,model=name,n=len(group),n_firms=len(set(firms)),cov80=coverage.mean(),
                    cov80_ci_low=ci['ci_low'],cov80_ci_high=ci['ci_high'],coverage_change=(coverage-base_cov).mean(),
                    coverage_change_ci_low=difference['ci_low'],coverage_change_ci_high=difference['ci_high'],IS80=interval.mean(),
                    IS80_improvement_pct=score['improvement_pct'],IS80_improvement_ci_low=score['improvement_ci_low'],
                    IS80_improvement_ci_high=score['improvement_ci_high'],point_coverage_target_met=coverage.mean()>=.7,
                    bootstrap_n=300,test_used_for_selection=False,measurement_version='regime-cash-source-cal-120gap-v1-fullweek'))
    pd.DataFrame(summary).to_csv(directory/'metrics.csv',index=False)
    if customer_rows:remove_common_customer_residual(pd.DataFrame(customer_rows)).to_parquet(directory/'customer_residual_diagnostics.parquet',index=False)
    protocol.update(complete=True,metrics_sha256=file_hash(directory/'metrics.csv'))
    (directory/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')


if __name__=='__main__':main()
