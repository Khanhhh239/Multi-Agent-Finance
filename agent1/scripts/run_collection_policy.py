"""E2E-4 cấu trúc: P0/P1/P2, 52 tuần, q=.3/.5/.7; không phải hiệu quả nhân quả."""
import gc
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import lightgbm as lgb
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH,OUT,PROCESSED,ROOT
from agent1.models.features import SnapshotBuilder,FEATURES,add_labels
from agent1.models.t1 import HazardGBM,pmf_from_hazard
from agent1.models.t1 import WEEK_FEATS
from agent1.models.t6_cash import collection_kernel
from agent1.eval.collection_policy import rank_delta,move_receipts,remaining_ar,response_uniform,count_shortfalls
from agent1.eval.cluster import mean_ci
from run_dr_comparison import row_sample
import run_t6 as R6


def file_hash(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):value.update(chunk)
    return value.hexdigest()


def training_rows(world,cuts,origin,visible,cache):
    integrity=cache.with_suffix('.sha256')
    if cache.exists() and integrity.exists() and file_hash(cache)==integrity.read_text(encoding='utf-8'):
        return pd.read_parquet(cache)
    directory=SYNTH/world;firms=pd.read_parquet(directory/'firms.parquet').firm_id.sort_values().tolist()
    reservoir=pd.DataFrame()
    for start in range(0,len(firms),4):
        filters=[('firm_id','in',firms[start:start+4])]
        inv=pd.read_parquet(directory/'invoices.parquet',filters=filters)
        pay=pd.read_parquet(directory/'payments.parquet',filters=filters)
        builder=SnapshotBuilder(inv,pay,None);parts=[]
        for cutoff in cuts:
            frame=builder.snapshot(cutoff,visible_from=visible)
            if frame.empty:continue
            keep=list(dict.fromkeys(['invoice_id','firm_id','cutoff','label_date','writeoff_date','top1','top2',*FEATURES]))
            frame=frame[[c for c in keep if c in frame]].copy()
            numeric=frame.select_dtypes('number').columns;frame[numeric]=frame[numeric].astype('float32');parts.append(frame)
        if parts:
            batch=add_labels(pd.concat(parts,ignore_index=True),origin)
            reservoir=row_sample(pd.concat([reservoir,batch],ignore_index=True),20000)
        del builder,inv,pay,parts;gc.collect()
        print('policy features',world,start+len(firms[start:start+4]),'/',len(firms),flush=True)
    reservoir.to_parquet(cache,index=False)
    integrity.write_text(file_hash(cache),encoding='utf-8')
    return reservoir


def revenue_intervals(invoices,cutoff):
    history=invoices[(invoices.issue_date<=cutoff)&(invoices.issue_date>cutoff-pd.Timedelta(days=91))]
    weekly=R6.weekly(history.groupby('issue_date').amount_gross.sum(),cutoff-pd.Timedelta(days=91))
    return np.tile(np.quantile(weekly,[.1,.5,.9]),(13,1))


def compatible_checkpoint(old,current):
    if old==current:return True
    left=json.loads(json.dumps(old));right=json.loads(json.dumps(current))
    for signature in [left,right]:signature['code']={name.replace('\\','/'):digest for name,digest in signature.get('code',{}).items()}
    if left['code'].get('scripts/run_collection_policy.py') not in {
        '5e8ec4cc7691971a3f3b04b16a4d17be075505179cadb3a02f768add4b579027',
        '8493b8d3b655fd164af00072d22c11f8458c988ef601a3f6b1e6c44b449c6340'}:return False
    left['code'].pop('scripts/run_collection_policy.py',None);right['code'].pop('scripts/run_collection_policy.py',None)
    return left==right


def projected_table(path,columns):
    available=pq.ParquetFile(path).schema.names
    return pd.read_parquet(path,columns=[column for column in columns if column in available])


def main():
    origin=pd.Timestamp('2024-07-01');end=origin+pd.Timedelta(days=364);visible=origin-pd.DateOffset(months=12)
    output=OUT/'t6/collection_policy';output.mkdir(exist_ok=True)
    paths=[ROOT/p for p in ['scripts/run_collection_policy.py','agent1/eval/collection_policy.py','scripts/run_dr_comparison.py',
        'agent1/models/features.py','agent1/models/t1.py','agent1/models/t6_cash.py','agent1/calendar_vn.py','scripts/run_t6.py']]
    inputs=[SYNTH/world/f'{table}.parquet' for world in ['src','tgt'] for table in ['invoices','payments','firms']]
    inputs.extend([SYNTH/'tgt/daily_cash.parquet',SYNTH/'tgt/outflows.parquet'])
    signature=dict(code={str(p.relative_to(ROOT)):file_hash(p) for p in paths},
        inputs={str(p.relative_to(SYNTH)):file_hash(p) for p in inputs},seed=7)
    protocol_path=output/'protocol.json';metrics_path=output/'metrics.csv';checkpoint_path=output/'checkpoint.json'
    if protocol_path.exists() and metrics_path.exists():
        old=json.loads(protocol_path.read_text(encoding='utf-8'))
        if old.get('complete') and old.get('signature')==signature and old.get('metrics_sha256')==file_hash(metrics_path):
            print('resumed verified collection policy',flush=True);return
    protocol=dict(complete=False,signature=signature,n_firms=14,n_weeks=52,
        source_budget=20000,source_rounds=300,finetune_budget=20000,finetune_rounds=150,
        histories='ideal observed receipt/settlement history as-of cutoff; oracle-label research arm, not T9-estimated E2E',
        action='one invoice per firm per week; successful response pulls only already-scheduled future receipts after week1 to week1',
        q=[.3,.5,.7],response='hash(invoice_id,cutoff,seed), shared across policies and q',
        P2='top50 amount*P(late>2w); CRN delta shortfall, 256 paths, rho=.15, df=4; historical revenue quantiles',
        outcome='actual synthetic balance plus cash-timing differences; expenses and owner draws fixed; total payment cash conserved',
        DSO='mean weekly gross AR net of known credits/receipts/writeoffs divided by fixed credit sales per day over 364d',
        limitation='policy simulation not causal; assumed response q; call cost not monetized; fixed expense/draw schedule; no T9 errors; one response seed',
        test_used_for_selection=False)
    checkpoint=json.loads(checkpoint_path.read_text(encoding='utf-8-sig')) if checkpoint_path.exists() else {}
    models=OUT/'t6/policy_models';models.mkdir(exist_ok=True);model_path=models/'T1_oracle_policy.txt'
    reusable=bool(checkpoint and compatible_checkpoint(checkpoint.get('signature',{}),signature) and model_path.exists()
        and file_hash(model_path)==checkpoint.get('model_sha256')
        and file_hash(output/'company_metrics.csv')==checkpoint.get('company_sha256')
        and file_hash(output/'actions.csv')==checkpoint.get('actions_sha256'))
    protocol['resumed_checkpoint_signature']=checkpoint.get('signature') if reusable else None
    protocol_path.write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    digest=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()[:12]
    cache=PROCESSED/('collection_policy_'+digest);cache.mkdir(exist_ok=True)
    if reusable:
        model=HazardGBM();model.booster=lgb.Booster(model_file=str(model_path))
        if model.booster.feature_name()!=FEATURES+WEEK_FEATS:raise ValueError('Sai đặc trưng checkpoint T1')
        previous_digest=hashlib.sha256(json.dumps(checkpoint['signature'],sort_keys=True).encode()).hexdigest()[:12]
        previous_cache=PROCESSED/('collection_policy_'+previous_digest)
        for name,column in [('src','n_source_train'),('tgt','n_target_train')]:
            source_file=previous_cache/f'{name}.parquet';integrity=source_file.with_suffix('.sha256')
            if source_file.exists() and integrity.exists() and file_hash(source_file)==integrity.read_text(encoding='utf-8'):
                protocol[column]=pq.ParquetFile(source_file).metadata.num_rows
    else:
        source=training_rows('src',pd.date_range('2019-07-01',origin-pd.Timedelta(days=7),freq='14D'),origin,None,cache/'src.parquet')
        protocol['n_source_train']=len(source)
        base=HazardGBM(rounds=300).fit(source);del source;gc.collect()
        target=training_rows('tgt',pd.date_range(visible+pd.Timedelta(days=28),origin-pd.Timedelta(days=7),freq='7D'),origin,visible,cache/'tgt.parquet')
        protocol['n_target_train']=len(target)
        model=HazardGBM(dict(learning_rate=.02),rounds=150).fit(target,init_model=base.booster)
        del target,base;gc.collect();model.booster.save_model(str(model_path))
    model.booster.free_dataset()
    invoice_columns=['invoice_id','firm_id','customer_id','issue_date','due_date','term_days','amount_gross',
        'paid_date_true','writeoff_date','credit_note','credit_note_date']
    invoices=projected_table(SYNTH/'tgt/invoices.parquet',invoice_columns)
    payments=projected_table(SYNTH/'tgt/payments.parquet',['firm_id','invoice_id','pay_date_true','amount','kind'])
    daily=projected_table(SYNTH/'tgt/daily_cash.parquet',['firm_id','date','inflow_ar','inflow_other','outflow','owner_draw','balance'])
    outflows=projected_table(SYNTH/'tgt/outflows.parquet',['firm_id','date','category','amount','known_at'])
    firms=sorted(invoices.firm_id.unique());cuts=pd.date_range(origin,periods=52,freq='7D')
    if len(firms)!=14:raise ValueError('Cần đúng 14 công ty đích')
    rows=[];actions=[];completed=set()
    if reusable:
        prior=pd.read_csv(output/'company_metrics.csv')
        expected={('P0',0.),*[(name,q) for q in [.3,.5,.7] for name in ['P1-largest','P2-delta']]}
        for firm,group in prior.groupby('firm_id'):
            if len(group)==7 and set(zip(group.policy,group.q))==expected and group.n_weeks.eq(52).all():completed.add(firm)
        rows=prior[prior.firm_id.isin(completed)].to_dict('records')
        prior_actions=pd.read_csv(output/'actions.csv',parse_dates=['cutoff'])
        actions=prior_actions[prior_actions.firm_id.isin(completed)].to_dict('records')
    # Xác minh loại metadata thô không đổi đặc trưng đầu vào.
    first=firms[0];filters=[('firm_id','==',first)]
    full=pd.read_parquet(SYNTH/'tgt/invoices.parquet',filters=filters)
    pp=payments[payments.firm_id==first]
    a=SnapshotBuilder(full,pp,None).snapshot(origin,visible_from=visible)
    b=SnapshotBuilder(invoices[invoices.firm_id==first],pp,None).snapshot(origin,visible_from=visible)
    comparison=list(dict.fromkeys(['invoice_id','cutoff',*FEATURES,*[c for c in ['top1','top2'] if c in a]]))
    pd.testing.assert_frame_equal(a[comparison],b[comparison])
    del full,pp,a,b;gc.collect()
    for firm_index,firm in enumerate(firms):
        if firm in completed:print(firm,'resumed verified completed company',flush=True);continue
        original_inv=invoices[invoices.firm_id==firm].copy();original_pay=payments[payments.firm_id==firm].copy()
        context=R6.firm_context('tgt',firm,invoices,outflows,daily)
        sales=original_inv.loc[(original_inv.issue_date>origin)&(original_inv.issue_date<=end)&(original_inv.term_days>0),'amount_gross'].sum()
        for policy,q in [('P0',0.),*[(name,q) for q in [.3,.5,.7] for name in ['P1-largest','P2-delta']]]:
            inv=original_inv.copy();pay=original_pay.copy();deltas=[];balances=[];receivables=[];calls=0;cash_accelerated=0.
            for week,cutoff in enumerate(cuts):
                chosen=None;delta_probability=np.nan;remaining=remaining_ar(inv,pay,cutoff)
                if policy=='P1-largest':
                    eligible=inv.loc[inv.issue_date>=visible,'invoice_id']
                    available=remaining[(remaining>25000.)&remaining.index.isin(eligible)]
                    if len(available):chosen=available.sort_values(ascending=False,kind='stable').index[0]
                elif policy=='P2-delta':
                    builder=SnapshotBuilder(inv,pay,None)
                    snapshot=builder.snapshot(cutoff,visible_from=visible)
                    if len(snapshot):
                        snapshot['amount_open']=snapshot.invoice_id.map(remaining).fillna(0.)
                        snapshot=snapshot[snapshot.amount_open>25000.].reset_index(drop=True)
                    if len(snapshot):
                        B0=float(context['bal'].loc[cutoff])
                        if deltas:
                            movements=pd.concat(deltas,ignore_index=True)
                            B0+=movements.loc[movements.date<=cutoff,'delta'].sum()
                        P=pmf_from_hazard(model.hazards(snapshot))[0]
                        known=R6.known_outflows(context,cutoff)
                        kernel=collection_kernel(inv,cutoff)
                        args=dict(B0=B0,known_out=known,rev_q=revenue_intervals(inv,cutoff),kernel=kernel,
                            capex_rate=0.,capex_sizes=[],n=256,rho=.15,seed=7000+firm_index*100+week)
                        ranked=rank_delta(snapshot,P,args,top_n=50)
                        chosen=ranked.iloc[0].invoice_id;delta_probability=float(ranked.iloc[0].delta_shortfall)
                    del builder
                moved_cash=0.;receipt=cutoff+pd.Timedelta(days=7)
                if chosen is not None:
                    calls+=1
                    if response_uniform(chosen,cutoff)<q:
                        updated,moved=move_receipts(pay,chosen,cutoff)
                        moved_cash=float(moved.amount.sum())
                        if len(moved):
                            before=float(pay.amount.sum());pay=updated
                            if not np.isclose(pay.amount.sum(),before,rtol=0,atol=.01):raise ValueError('Không bảo toàn tiền')
                            deltas.append(pd.DataFrame(dict(date=pd.concat([moved.old_date,moved.new_date],ignore_index=True),
                                delta=np.r_[-moved.amount.to_numpy(),moved.amount.to_numpy()])))
                            closed=pay[(pay.invoice_id==chosen)&pay.kind.isin(['full','final'])].pay_date_true
                            if len(closed):inv.loc[inv.invoice_id==chosen,'paid_date_true']=closed.max()
                    actions.append(dict(firm_id=firm,policy=policy,q=q,cutoff=cutoff,invoice_id=chosen,
                        cash_accelerated=moved_cash,delta_shortfall=delta_probability))
                cash_accelerated+=moved_cash
                balance=float(context['bal'].loc[receipt])
                if deltas:
                    movements=pd.concat(deltas,ignore_index=True)
                    balance+=movements.loc[movements.date<=receipt,'delta'].sum()
                balances.append(balance);receivables.append(float(remaining_ar(inv,pay,receipt).sum()))
            rows.append(dict(firm_id=firm,policy=policy,q=q,n_weeks=52,shortfall_events=count_shortfalls(balances),
                shortfall_weeks=int((np.asarray(balances)<0).sum()),minimum_balance=min(balances),
                DSO=float(np.mean(receivables)/(sales/364)) if sales>0 else np.nan,n_calls=calls,cash_accelerated=cash_accelerated,
                evidence_type='policy_simulation_not_causal',measurement_version='collection-policy-known-settlement-v2-fullweek'))
            print(firm,policy,q,'scored',flush=True)
        pd.DataFrame(rows).to_csv(output/'company_metrics.csv',index=False)
        pd.DataFrame(actions).to_csv(output/'actions.csv',index=False)
        checkpoint_path.write_text(json.dumps(dict(signature=signature,model_sha256=file_hash(model_path),
            company_sha256=file_hash(output/'company_metrics.csv'),actions_sha256=file_hash(output/'actions.csv')),indent=2),encoding='utf-8')
        gc.collect()
    frame=pd.DataFrame(rows);baseline=frame[frame.policy=='P0'].set_index('firm_id');summary=[]
    for (policy,q),part in frame.groupby(['policy','q']):
        part=part.set_index('firm_id').reindex(baseline.index)
        for metric in ['shortfall_events','shortfall_weeks','DSO']:
            valid=part[metric].notna()&baseline[metric].notna()
            difference=baseline.loc[valid,metric]-part.loc[valid,metric]
            ci=mean_ci(difference,part.index[valid])
            summary.append(dict(policy=policy,q=q,metric=metric,mean=part.loc[valid,metric].mean(),
                baseline_mean=baseline.loc[valid,metric].mean(),reduction_vs_P0=difference.mean(),
                reduction_ci_low=ci['ci_low'],reduction_ci_high=ci['ci_high'],n_firms=int(valid.sum()),bootstrap_n=300,
                n_calls=int(part.n_calls.sum()),cash_accelerated=float(part.cash_accelerated.sum()),
                evidence_type='policy_simulation_not_causal',test_used_for_selection=False,
                measurement_version='collection-policy-known-settlement-v2-fullweek'))
    pd.DataFrame(summary).to_csv(metrics_path,index=False)
    protocol.update(complete=True,metrics_sha256=file_hash(metrics_path))
    protocol_path.write_text(json.dumps(protocol,indent=2),encoding='utf-8')


if __name__=='__main__':main()
