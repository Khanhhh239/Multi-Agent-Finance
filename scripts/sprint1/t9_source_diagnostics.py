"""Chẩn đoán phân bổ/precision–coverage trên DN nguồn chưa dùng fit, trước test tgt."""
import argparse
import json
from pathlib import Path
import sys
import pandas as pd
import pyarrow.parquet as pq
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from agent1.paths import OUT,SYNTH
from agent1.models.t9_fast import fast_source,reconcile_arrays,concatenate_parts
from run_e2e_protocol import source_reconciler
from run_t9_hardcases import load_observed,sha256
from run_t9 import evaluate
from agent1.models.t9_source_policy import ObservedAllocationPolicy,LedgerHazardPrior
from agent1.models.t9_recon import Reconciler

GRID=[.5,.6,.7,.8,.85,.9,.95,.975,.99]


def classify(bank,invoices,payments,links):
    customer=invoices.set_index('invoice_id').customer_id.to_dict()
    truth={key:set(g.invoice_id) for key,g in payments.groupby('txn_id')}
    predicted={key:set(g.invoice_id) for key,g in links.groupby('txn_id')}
    partial=set(payments.loc[payments.kind=='partial','txn_id']);rows=[]
    for txn in bank.itertuples(index=False):
        actual=truth.get(txn.txn_id,set());chosen=predicted.get(txn.txn_id,set())
        wrong_customer=bool(chosen and {customer.get(i) for i in chosen}-{customer.get(i) for i in actual})
        category=('noise' if not actual else 'wrong_customer' if wrong_customer else 'partial_payment'
            if txn.txn_id in partial else 'bank_fee' if getattr(txn,'fee_deducted',0)>0 else 'grouped_invoices' if len(actual)>1 else 'invoice_set')
        rows.append(dict(txn_id=txn.txn_id,firm_id=txn.firm_id,category=category,
            correct_customer=bool(chosen and not wrong_customer),exact_invoice_set=chosen==actual,
            tp=len(actual&chosen),fp=len(chosen-actual),fn=len(actual-chosen),automatic=bool(chosen)))
    return pd.DataFrame(rows)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--with-policy',action='store_true');args=parser.parse_args()
    directory=OUT/'t9/sprint3';directory.mkdir(exist_ok=True)
    # The old shared cache lacks training_firms. Fit/cache a separate source
    # classifier with explicit provenance before defining the firm holdout.
    source_directory=directory/'source_reconciler'
    source=fast_source(source_reconciler(source_directory,require_training_firms=True))
    excluded=set(source.provenance['training_firms'])
    hazard_model=None;hazard_protocol={}
    if args.with_policy:
        import lightgbm as lgb
        from agent1.models import t1
        model_dir=OUT/'t1/fullweek_A/2023-07-03'
        hazard_protocol=json.loads((model_dir/'protocol.json').read_text(encoding='utf-8'))
        if not hazard_protocol['expand_full_week_only'] or pd.Timestamp(hazard_protocol['training_label_end'])>=pd.Timestamp('2024-01-01'):
            raise ValueError('Cần prior A fullweek học trước calibration nguồn')
        hazard_model=t1.HazardGBM();hazard_model.booster=lgb.Booster(model_file=str(model_dir/'model.txt'))
    firms=pd.read_parquet(SYNTH/'src/firms.parquet').firm_id
    heldout=set(firms)-excluded
    if not heldout:raise ValueError('Không còn DN nguồn độc lập cho chọn tau')
    bank,inv,cust,pay=load_observed('src','2024-01-01','2024-06-30')
    bank_path=SYNTH/'src/bank_txns.parquet'
    if 'fee_deducted' in pq.ParquetFile(bank_path).schema.names:
        fees=pd.read_parquet(bank_path,columns=['txn_id','fee_deducted'])
        bank=bank.merge(fees,on='txn_id',how='left',validate='one_to_one')
    bank=bank[bank.firm_id.isin(heldout)];inv=inv[inv.firm_id.isin(heldout)]
    cust=cust[cust.firm_id.isin(heldout)];pay=pay[pay.txn_id.isin(bank.txn_id)]
    prepared=[]
    for fid,transactions in bank.groupby('firm_id'):
        invoices=inv[inv.firm_id==fid];customers=cust[cust.firm_id==fid]
        assignments=source.assign_customers(source.candidates(transactions,invoices,customers))
        planner=ObservedAllocationPolicy(LedgerHazardPrior(invoices,hazard_model,hazard_protocol['training_label_end'])) if args.with_policy else None
        prepared.append((transactions,invoices,customers,assignments,planner))
    rows=[];diagnostics=[]
    for variant,tau in [(variant,tau) for variant in (['baseline','candidate'] if args.with_policy else ['baseline']) for tau in GRID]:
        linked=[];reviews=[]
        for transactions,invoices,customers,assignments,planner in prepared:
            links,queue=reconcile_arrays(source,transactions,invoices,customers,assignments=assignments,tau_auto=tau,
                allocation_policy=planner if variant=='candidate' else None)
            linked.append(links);reviews.append(queue)
        links=concatenate_parts(linked);queue=concatenate_parts(reviews)
        metrics=evaluate('Hybrid source heldout',links,bank,inv,pay)
        metrics.update(tau=tau,variant=variant,auto_txn_coverage=links.txn_id.nunique()/len(bank),n_review=len(queue),
            selection_domain='src_company_holdout',target_used=False,measurement_version='T9-source-allocation-v1-fullweek')
        rows.append(metrics)
        if tau==.9 and variant=='baseline':diagnostics=classify(bank,inv,pay,links)
        pd.DataFrame(rows).to_csv(directory/'source_precision_coverage.csv',index=False)
        print('source',variant,'tau',tau,metrics['link_precision'],metrics['auto_txn_coverage'],flush=True)
    frame=pd.DataFrame(rows);eligible=frame[(frame.link_precision>=.95)&(frame.auto_txn_coverage>=.6)]
    selected=eligible.sort_values(['link_f1','auto_txn_coverage'],ascending=False).iloc[0] if len(eligible) else None
    diagnostics.groupby('category').agg(n_txns=('txn_id','size'),tp=('tp','sum'),fp=('fp','sum'),fn=('fn','sum'),
        exact_set_rate=('exact_invoice_set','mean'),automatic_rate=('automatic','mean')).reset_index().to_csv(directory/'source_allocation_diagnostics.csv',index=False)
    diagnostics.to_csv(directory/'source_transaction_diagnostics.csv',index=False)
    policy=dict(complete=True,source_firms=sorted(heldout),training_firms=sorted(excluded),
        selection_period=['2024-01-01','2024-06-30'],target_used=False,
        selected_tau=None if selected is None else float(selected.tau),
        selected_variant=None if selected is None else selected.variant,
        source_precision_coverage_joint_met=selected is not None,
        stop_rule_recommendation=('retain .6 requirement; request owner decision before reducing to .5'
            if selected is None and (frame.link_precision>=.95).any() else 'precision target not attained; no coverage relaxation justified' if selected is None else None),
        source_inputs={name:sha256(SYNTH/'src'/f'{name}.parquet') for name in ['invoices','bank_txns','customers','payments']},
        source_classifier={name:sha256(source_directory/name) for name in ['model.txt','metadata.json']},
        candidate_enabled=args.with_policy,
        hazard_prior=None if not args.with_policy else dict(model_sha256=sha256(model_dir/'model.txt'),
            protocol_sha256=sha256(model_dir/'protocol.json'),training_label_end=hazard_protocol['training_label_end']),
        source_code_sha256={name:sha256(ROOT/name) for name in ['scripts/sprint1/t9_source_diagnostics.py',
            'agent1/models/t9_source_policy.py','agent1/models/t9_fast.py','agent1/models/t9_recon.py']},
        note='source-only tau/variant selection; partial memo residual/COD and frozen T1 prior; contract retention split requires known_at, not synthetic future annotations')
    (directory/'source_policy.json').write_text(json.dumps(policy,indent=2),encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    figure,axis=plt.subplots(figsize=(7,5))
    for name,points in frame.groupby('variant'):
        points=points.sort_values('auto_txn_coverage')
        axis.plot(points.auto_txn_coverage,points.link_precision,marker='o',label=name)
    axis.axhline(.95,color='grey',linestyle='--');axis.axvline(.6,color='grey',linestyle='--')
    axis.set(xlabel='Automatic transaction coverage',ylabel='Link precision',title='Source company holdout; thresholds selected here')
    axis.legend();figure.tight_layout();figure.savefig(directory/'source_precision_coverage.png',dpi=160);plt.close(figure)
    if args.with_policy and selected is not None:
        target_rows=[]
        for world in ['tgt','hc_retention','hc_cod_realistic']:
            bt,it,ct,pt=load_observed(world,'2024-07-01','2025-06-29')
            methods={'R1':dict(rule_mode='amount'),'R2':dict(rule_mode='memo'),
                'Hybrid baseline tau=.9':dict(),'Deployment source-selected':dict()}
            all_links={name:[] for name in methods}
            for fid,transactions in bt.groupby('firm_id'):
                invoices=it[it.firm_id==fid];customers=ct[ct.firm_id==fid]
                assignments=source.assign_customers(source.candidates(transactions,invoices,customers))
                planner=ObservedAllocationPolicy(LedgerHazardPrior(invoices,hazard_model,hazard_protocol['training_label_end']))
                for name,kwargs in methods.items():
                    deployment=name.startswith('Deployment')
                    tau=float(selected.tau) if deployment else .9
                    rec=source if name.startswith(('Hybrid','Deployment')) else Reconciler()
                    links,_=reconcile_arrays(rec,transactions,invoices,customers,tau_auto=tau,
                        assignments=assignments if name.startswith(('Hybrid','Deployment')) else None,
                        allocation_policy=planner if deployment and selected.variant=='candidate' else None,**kwargs)
                    all_links[name].append(links)
            for name in methods:
                links=concatenate_parts(all_links[name]);metrics=evaluate(name,links,bt,it,pt)
                metrics.update(world=world,auto_txn_coverage=links.txn_id.nunique()/len(bt),
                    tau=float(selected.tau) if name.startswith('Deployment') else .9,selected_on='src_company_holdout',
                    test_used_for_selection=False,measurement_version='T9-source-selected-allocation-v1-fullweek')
                target_rows.append(metrics)
            pd.DataFrame(target_rows).to_csv(directory/'target_metrics.csv',index=False)
            print(world,'measured without threshold changes',flush=True)
        policy.update(target_complete=True,target_metrics_sha256=sha256(directory/'target_metrics.csv'))
        (directory/'source_policy.json').write_text(json.dumps(policy,indent=2),encoding='utf-8')


if __name__=='__main__':main()
