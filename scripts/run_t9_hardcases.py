"""WP-4.5: mô hình nguồn và ngưỡng khoá trước, recall riêng 12 hard cases có đối chứng."""
import gc
import hashlib
import json
from pathlib import Path
import sys
import time
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import OUT, SYNTH, ROOT
from agent1.synth.hard_cases import CASES
from agent1.models.t9_recon import Reconciler
from agent1.models.t9_fast import fast_source,concatenate_parts,reconcile_arrays as reconcile
from run_e2e_protocol import source_reconciler
from run_t9 import evaluate


def sha256(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def load_observed(world,start,end):
    columns=dict(bank_txns=['txn_id','firm_id','value_date','amount','memo','counterparty','direction','txn_type','true_customer_id'],
        invoices=['invoice_id','firm_id','customer_id','invoice_no','issue_date','due_date','amount_gross','ledger_clear_date','credit_note','credit_note_date'],
        customers=['firm_id','customer_id','short'],payments=['firm_id','txn_id','invoice_id','kind','pay_date_true'])
    result={}
    for table,requested in columns.items():
        path=SYNTH/world/f'{table}.parquet';available=pq.ParquetFile(path).schema.names
        result[table]=pd.read_parquet(path,columns=[c for c in requested if c in available])
    bank=result['bank_txns'];bank=bank[bank.value_date.between(start,end)].copy()
    invoices=result['invoices'];invoices=invoices[invoices.issue_date<=end].copy()
    payments=result['payments'];payments=payments[payments.txn_id.isin(bank.txn_id)].copy()
    return bank,invoices,result['customers'],payments


def equivalent_signature(cached,expected):
    if cached==expected:return True
    # Chỉ chấp nhận đúng wrapper cũ đã chạy; thuật toán, model, dữ liệu và lịch phải khớp.
    old_wrappers={'1922c568fb2513fb6e9b0f5afd1e44d3031b3b5c71387af7b2ee7ad0241ea88e',
                  '86d900a0d52073abfbd8ef4a0f810d2d67bb31775bd2864ac65274309e14ec65',
                  'd3c31003303325f8ea70b5245a8f1b38ba98fc83cfb2903f84cca1ee76f5cc84'}
    if cached.get('code',{}).get('scripts/run_t9_hardcases.py') not in old_wrappers:return False
    left=json.loads(json.dumps(cached));right=json.loads(json.dumps(expected))
    left['code'].pop('scripts/run_t9_hardcases.py',None)
    right['code'].pop('scripts/run_t9_hardcases.py',None)
    right['code'].pop('agent1/models/t9_fast.py',None)
    if 'agent1/models/t9_fast.py' in left['code']:
        if left['code']['agent1/models/t9_fast.py'] not in {
            '457a699d4359e8aecf5534a5f60accaba631646781fdff96191f85d4814bd4a1',
            '332f23884b712f65b933166ad30a45f998fcb6a969d2dbbd5cd72eec026f226c'}:return False
        left['code'].pop('agent1/models/t9_fast.py')
    return left==right


def main():
    start, end = '2024-07-01', '2025-06-29'
    directory=OUT/'t9/hard_cases';directory.mkdir(exist_ok=True)
    source=fast_source(source_reconciler())
    files=['scripts/run_t9_hardcases.py','scripts/run_t9.py','agent1/models/t9_recon.py',
           'agent1/models/reconciliation_pipeline.py','agent1/eval/cluster.py','agent1/models/t9_fast.py']
    signature=dict(code={p:sha256(ROOT/p) for p in files},
        source_model={p.name:sha256(p) for p in (OUT/'t9/source_reconciler').glob('*') if p.is_file()},
        start=start,end=end,tau_auto=.9)
    protocol=dict(complete=False,source_used_for_selection_only=True,test_used_for_selection=False,
        start=start,end=end,tau_auto=.9,measurement_version='T9-hard-case-post-calibration-v1',
        limitation='synthetic;hard-case contract does not certify semantic fidelity;source thresholds frozen;no target tuning')
    protocol['execution']='firm partition, vectorized identical amount features; tests/test_t9_fast.py checks reference equivalence'
    protocol['resumed_prior_wrappers']=[]
    protocol_path=directory/'protocol.json'
    protocol_path.write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    rows=[]
    for case in CASES:
        revised=SYNTH/f'hc_{case}_v2'
        world=revised.name if (revised/'hard_case_complete.txt').exists() else f'hc_{case}'
        case_dir=directory/case;case_dir.mkdir(exist_ok=True)
        expected=dict(signature,world=world,inputs={name:sha256(SYNTH/world/f'{name}.parquet')
            for name in ['bank_txns','invoices','customers','payments']})
        marker=case_dir/'complete.json';table=case_dir/'metrics.csv'
        if marker.exists() and table.exists():
            cached=json.loads(marker.read_text(encoding='utf-8'))
            if equivalent_signature(cached.get('signature',{}),expected) and cached.get('output_sha256')==sha256(table):
                protocol['resumed_prior_wrappers'].append(dict(case=case,signature=cached['signature']))
                rows.append(pd.read_csv(table));print(case,'resumed verified result',flush=True);continue
        began=time.monotonic();bank,invoices,customers,payments=load_observed(world,start,end)
        if bank.empty or payments.empty:raise ValueError(f'{world}: thiếu dữ liệu cửa sổ test')
        methods=['R1 unique amount','R2 memo','Hybrid frozen tau=.9']
        all_links={name:[] for name in methods};all_reviews={name:[] for name in methods}
        for fid,firm_bank in bank.groupby('firm_id'):
            firm_inv=invoices[invoices.firm_id==fid];firm_cust=customers[customers.firm_id==fid]
            assignments=source.assign_customers(source.candidates(firm_bank,firm_inv,firm_cust))
            for name,rec,kwargs in [
                (methods[0],Reconciler(),dict(rule_mode='amount')),
                (methods[1],Reconciler(),dict(rule_mode='memo')),
                (methods[2],source,dict(assignments=assignments))]:
                links,queue=reconcile(rec,firm_bank,firm_inv,firm_cust,tau_auto=.9,**kwargs)
                all_links[name].append(links);all_reviews[name].append(queue)
            print(case,fid,'reconciled',flush=True)
        current=[]
        for name in methods:
            links=concatenate_parts(all_links[name])
            queue=concatenate_parts(all_reviews[name])
            result=evaluate(name,links,bank,invoices,payments)
            result.update(case=case,world=world,n_bank=len(bank),auto_txn_coverage=links.txn_id.nunique()/len(bank),
                n_review=len(queue),test_start=start,test_end=end,tau_auto=.9,test_used_for_selection=False,
                observed_first_bank_date=str(bank.value_date.min().date()),observed_last_bank_date=str(bank.value_date.max().date()),
                measurement_version=protocol['measurement_version'])
            current.append(result)
            if name.startswith('Hybrid'):
                links.to_parquet(case_dir/'auto_links.parquet',index=False)
                queue.to_parquet(case_dir/'review_queue.parquet',index=False)
        frame=pd.DataFrame(current);frame['seconds']=time.monotonic()-began
        frame.to_csv(table,index=False);rows.append(frame)
        marker.write_text(json.dumps(dict(signature=expected,output_sha256=sha256(table)),indent=2),encoding='utf-8')
        pd.concat(rows).to_csv(OUT/'t9/hard_case_recall.csv',index=False)
        print(case,'scored',round(time.monotonic()-began,1),'seconds',flush=True)
        del bank,invoices,customers,payments,assignments,links,queue,all_links,all_reviews;gc.collect()
    pd.concat(rows).to_csv(OUT/'t9/hard_case_recall.csv',index=False)
    protocol.update(complete=True,n_cases=len(CASES),signature=signature,
                    output_sha256=sha256(OUT/'t9/hard_case_recall.csv'))
    protocol_path.write_text(json.dumps(protocol,indent=2),encoding='utf-8')


if __name__=='__main__':main()
