"""T9 quanh sốc 2022, mô hình và ngưỡng nguồn chốt trước sốc; không chọn lại từ test."""
import hashlib
import json
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import ROOT,OUT,SYNTH
from agent1.models.t9_recon import Reconciler
from agent1.models.t9_fast import fast_source,reconcile_arrays,concatenate_parts
from run_t9_hardcases import load_observed,sha256
from run_t9 import evaluate

WINDOWS=[('before','2022-06-01','2022-10-02'),('shock','2022-10-03','2022-11-27'),
    ('after','2022-11-28','2023-03-31')]


def main():
    directory=OUT/'t9/supply_shock_2022';directory.mkdir(parents=True,exist_ok=True)
    world='hc_supply_shock_v2'
    if not (SYNTH/world/'hard_case_complete.txt').exists():raise ValueError('Cần thế giới sốc v2 đã xác nhận')
    files=['scripts/run_t9_supply_shock.py','scripts/run_t9_hardcases.py','scripts/run_t9.py',
        'agent1/models/t9_recon.py','agent1/models/t9_fast.py','agent1/models/reconciliation_pipeline.py','agent1/eval/cluster.py']
    signature=dict(code={p:sha256(ROOT/p) for p in files},
        inputs={f'{w}/{table}':sha256(SYNTH/w/f'{table}.parquet') for w in ['src',world]
            for table in ['invoices','bank_txns','customers','payments','firms']},tau_auto=.9,windows=WINDOWS)
    protocol=dict(complete=False,signature=signature,source_training=['2020-01-01','2020-12-31'],
        source_calibration=['2021-01-01','2021-12-31'],test_used_for_selection=False,tau_auto=.9,
        measurement_version='T9-supply-shock-pre2022-source-v1',
        scope='synthetic shock with before/during/after periods; frozen tau=.9, source-only isotonic; not new G15 adoption',
        limitation='one synthetic world/seed, few steel firms; not independent companies across windows; ledger information only available as-of transaction')
    path=directory/'protocol.json';path.write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    model_dir=directory/'source_model'
    provenance=dict(training_world='src',training_firms=[f'F{i:03d}' for i in range(12)],
        training_period=protocol['source_training'],calibration_period=protocol['source_calibration'],
        target_used=False,input_sha256={k:v for k,v in signature['inputs'].items() if k.startswith('src/')},
        fast_code_sha256=signature['code']['agent1/models/t9_fast.py'])
    try:
        model=Reconciler.load(model_dir)
        if model.provenance!=provenance:raise ValueError('Mô hình nguồn cũ khác giao thức')
        source=fast_source(model)
    except (FileNotFoundError,ValueError,KeyError):
        source=fast_source(Reconciler())
        for stage,period in [('fit',protocol['source_training']),('calibrate',protocol['source_calibration'])]:
            bank,inv,cust,_=load_observed('src',*period)
            firms=provenance['training_firms']
            bank=bank[bank.firm_id.isin(firms)];inv=inv[inv.firm_id.isin(firms)];cust=cust[cust.firm_id.isin(firms)]
            if bank.empty or bank.value_date.max()>pd.Timestamp(period[1]):raise ValueError('Sai cửa sổ nguồn')
            getattr(source,stage)(source.candidates(bank,inv,cust))
            print('source',stage,'complete',flush=True)
        source.save(model_dir,provenance)
    bank,inv,cust,pay=load_observed(world,WINDOWS[0][1],WINDOWS[-1][2])
    firms=pd.read_parquet(SYNTH/world/'firms.parquet',columns=['firm_id','industry'])
    steel=set(firms.loc[firms.industry=='steel_metals','firm_id'])
    methods=['R1 unique amount','R2 memo','Hybrid frozen pre2022 tau=.9']
    links_by={name:[] for name in methods};reviews_by={name:[] for name in methods}
    for fid,transactions in bank.groupby('firm_id'):
        invoices=inv[inv.firm_id==fid];customers=cust[cust.firm_id==fid]
        assignments=source.assign_customers(source.candidates(transactions,invoices,customers))
        for name,model,kwargs in [(methods[0],Reconciler(),dict(rule_mode='amount')),
            (methods[1],Reconciler(),dict(rule_mode='memo')),(methods[2],source,dict(assignments=assignments))]:
            links,queue=reconcile_arrays(model,transactions,invoices,customers,tau_auto=.9,**kwargs)
            links_by[name].append(links);reviews_by[name].append(queue)
        print(fid,'reconciled',flush=True)
    rows=[]
    for name in methods:
        links=concatenate_parts(links_by[name]);queue=concatenate_parts(reviews_by[name])
        for window,start,end in WINDOWS:
            for stratum,selected in [('all',set(bank.firm_id)),('steel_shock',steel),('other_industries',set(bank.firm_id)-steel)]:
                observed=bank[bank.value_date.between(start,end)&bank.firm_id.isin(selected)]
                if observed.empty:continue
                ids=set(observed.txn_id);pred=links[links.txn_id.isin(ids)];truth=pay[pay.txn_id.isin(ids)]
                result=evaluate(name,pred,observed,inv[inv.firm_id.isin(selected)],truth)
                result.update(window=window,test_start=start,test_end=end,stratum=stratum,world=world,n_bank=len(observed),
                    n_review=int(queue.txn_id.isin(ids).sum()),auto_txn_coverage=pred.txn_id.nunique()/len(observed),
                    source_calibration_end='2021-12-31',tau_auto=.9,test_used_for_selection=False,
                    measurement_version=protocol['measurement_version'])
                rows.append(result)
        if name.startswith('Hybrid'):
            links.to_parquet(directory/'auto_links.parquet',index=False)
            queue.to_parquet(directory/'review_queue.parquet',index=False)
    frame=pd.DataFrame(rows);frame.to_csv(directory/'metrics.csv',index=False)
    protocol.update(complete=True,n_rows=len(frame),source_model_sha256=sha256(model_dir/'model.txt'),
        metrics_sha256=sha256(directory/'metrics.csv'),n_steel_firms=len(steel),
        source_signature_sha256=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest())
    path.write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    print('supply shock complete',len(frame),'rows',flush=True)


if __name__=='__main__':main()
