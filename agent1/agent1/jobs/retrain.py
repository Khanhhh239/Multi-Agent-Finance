"""Huấn luyện ứng viên T1 từ dữ liệu đối soát đã quan sát, không dùng nhãn oracle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np
import pandas as pd

from agent1.models.t1 import HazardGBM,quantiles_from_hazard,QS,b1_dist,cdf_from_quantiles
from agent1.models.features import MODEL_VISIBLE_COLUMNS
from agent1.eval.observed_t1 import horizon_metrics
from agent1.reconciliation.pipeline import ObservedSource,ObservedSnapshotBuilder
from agent1_service.ingest.dates import local_dates
from agent1_service.store import Store
from agent1_service.model_registry import register,activate,code_signature


def observed_tables(store,firm,cutoff):
    cutoff=pd.Timestamp(cutoff);result={}
    for kind in ['invoices','bank_txns','customers','promises']:
        records=store.as_of(firm,kind,cutoff) if kind in {'customers','promises'} else store.get(firm,kind)
        data=pd.DataFrame(records)
        for col in data.columns:
            if 'date' in col:data[col]=local_dates(data[col],dayfirst=False)
        date={'invoices':'issue_date','bank_txns':'value_date','promises':'made_date'}.get(kind)
        if date and len(data):data=data[data[date]<=cutoff]
        result[kind]=data
    statements=store.get(firm,'bank_statements')
    if statements:
        from agent1_service.ingest.bank_statement import statement_scope
        from agent1_service.ingest.bank_accounts import load_account_registry,registry_path
        registry=load_account_registry(registry_path(store.path.parent),firm)
        visible=[s for s in statements if s.get('available_on',s['period_end'])<=str(cutoff.date())]
        coverage=statement_scope(visible,min(s['period_start'] for s in statements),str(cutoff.date()),registry)
        if not coverage['verified']:
            raise ValueError(f'Phạm vi sao kê chưa đầy đủ tại ngày cắt: {coverage.get("missing_from",coverage.get("reason"))}')
        result['bank_txns']=result['bank_txns'][result['bank_txns'].statement_id.isin(
            {s['statement_id'] for s in visible}) &
            (result['bank_txns'].available_on<=str(cutoff.date()))].copy()
        if any(s['currency']!='VND' for s in visible):
            raise ValueError('Huấn luyện hiện tính bằng VND; cần quy đổi tỷ giá có nguồn cho sao kê ngoại tệ')
    from agent1_service.ingest.invoices import effective_invoices
    if len(result['invoices']):
        versions=store.get(firm,'invoice_versions')
        result['invoices']=effective_invoices(versions or store.get(firm,'invoices'),store.get(firm,'invoice_events'),cutoff)
        for col in result['invoices'].columns:
            if 'date' in col:
                result['invoices'][col]=local_dates(result['invoices'][col],dayfirst=False)
        if 'currency' in result['invoices'] and not result['invoices'].currency.eq('VND').all():
            raise ValueError('Huấn luyện hiện tính bằng VND; cần quy đổi tỷ giá có nguồn cho hóa đơn ngoại tệ')
    if any(result[k].empty for k in ['invoices','bank_txns','customers']):
        raise ValueError('Cần hoá đơn, giao dịch và khách hàng trước cutoff')
    if len(result['promises']):
        result['promises']=result['promises'][result['promises'].invoice_id.isin(result['invoices'].invoice_id)]
    # Chỉ giữ khách đã xuất hiện trên hoá đơn quan sát được.
    result['customers']=result['customers'][result['customers'].customer_id.isin(result['invoices'].customer_id)]
    for kind in ('bank_txns','customers','promises'):
        frame=result[kind]
        if len(frame) and 'available_on' in frame:
            result[kind]=frame[pd.to_datetime(frame.available_on)<=cutoff].copy()
    return result


def prepare_training_data(store,firm,cutoff):
    """Rebuild both roles through the same reviewed, knowledge-time source."""
    T=pd.Timestamp(cutoff)
    tables=observed_tables(store,firm,T)
    source=ObservedSource(store,firm)
    view=source.view(T);inv=view['invoices']
    builder=ObservedSnapshotBuilder(source)
    train_end=T-pd.Timedelta(days=120)
    cuts=pd.date_range(max(inv.issue_date.min()+pd.Timedelta(days=60),T-pd.Timedelta(days=730)),train_end-pd.Timedelta(days=7),freq='14D')
    if not len(cuts):raise ValueError('Chưa đủ lịch sử và khoảng cách nhãn 120 ngày')
    train=builder.build(cuts,label_end=train_end)
    train_gaps=list(getattr(builder,'missing_windows',[]))
    validation=builder.build([train_end],label_end=T)
    fingerprints={k:hashlib.sha256(v.to_json(orient='split',date_format='iso').encode()).hexdigest() for k,v in tables.items()}
    return dict(train=train,validation=validation,firm_id=firm,available_at=T.isoformat(),
                training_label_end=train_end.isoformat(),label_mode='accepted_ledger',
                data_contract=view['contract_version'],data_snapshot=view['snapshot_hash'],
                data_hash=hashlib.sha256(json.dumps(fingerprints,sort_keys=True).encode()).hexdigest(),
                missing_windows=dict(train=train_gaps,validation=list(getattr(builder,'missing_windows',[]))))


def export_training_data(store,firm,cutoff,output):
    """Export encrypted, versioned samples; never train, activate, or rewrite T0."""
    output=Path(output)
    if output.exists():raise ValueError('Thư mục dataset đã tồn tại; cần tên phiên bản mới')
    prepared=prepare_training_data(store,firm,cutoff)
    labels=('label_date','writeoff_date','remaining','obs_window','time_obs','event')
    columns=list(dict.fromkeys((*MODEL_VISIBLE_COLUMNS,*labels)))
    payloads={}
    records={}
    for role in ('train','validation'):
        frame=prepared[role]
        frame=frame.loc[:,[c for c in columns if c in frame]].copy()
        content=frame.to_parquet(index=False)
        encrypted=store.cipher.encrypt(content)
        payloads[role+'.parquet.enc']=encrypted
        records[role]=dict(file=role+'.parquet.enc',rows=len(frame),
                           events=int(frame.event.sum()) if len(frame) else 0,
                           columns=list(frame.columns),plaintext_sha256=hashlib.sha256(content).hexdigest(),
                           encrypted_sha256=hashlib.sha256(encrypted).hexdigest())
    train=prepared['train']
    ready=len(train)>=100 and train.event.nunique()>=2
    manifest={k:v for k,v in prepared.items() if k not in {'train','validation'}}
    manifest.update(schema_version=1,code_signature=code_signature(),files=records,
                    trainable=bool(ready),status='prepared' if ready else 'insufficient_mature_labels',
                    trained=False,activated=False,encryption='Fernet; same tenant key as source store',
                    limitation='observed_ledger_only;no_synthetic_or_backdated_approvals;not_pilot_acceptance')
    output.mkdir(parents=True,exist_ok=False)
    for name,payload in payloads.items():(output/name).write_bytes(payload)
    (output/'dataset.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return manifest


def train_candidate(store,firm,cutoff,reason,*,rounds=200,max_rows=40000):
    start=time.monotonic()
    if reason not in {'psi','coverage','scheduled','manual'}:raise ValueError('Lý do retrain không hợp lệ')
    prepared=prepare_training_data(store,firm,cutoff)
    train=prepared['train'];validation=prepared['validation']
    if len(train)<100 or train.event.nunique()<2:raise ValueError('Chưa đủ nhãn đã chín để huấn luyện')
    train=train.sample(min(len(train),max_rows),random_state=7)
    model=HazardGBM(dict(min_data_in_leaf=30,num_leaves=31),rounds=rounds).fit(train)
    known=validation[(validation.event==1)&(validation.remaining<=120)] if len(validation) else validation
    H=model.hazards(validation) if len(validation) else np.empty((0,13))
    cdf=1-np.cumprod(1-H,axis=1)
    baseline=cdf_from_quantiles(b1_dist(validation)) if len(validation) else np.empty((0,13))
    metrics=horizon_metrics(validation,cdf,baseline)
    metrics['resolved_rows']=len(known)
    # Retain resolved-only timing scores strictly as secondary diagnostics.
    if len(known):
        q=quantiles_from_hazard(model.hazards(known));error=known.remaining.to_numpy()[:,None]-q
        metrics['pinball_resolved']=float(np.maximum(np.asarray(QS)*error,(np.asarray(QS)-1)*error).mean())
        metrics['cov80_resolved']=float(np.mean((known.remaining>=q[:,0])&(known.remaining<=q[:,2])))
    metadata=dict({k:v for k,v in prepared.items() if k not in {'train','validation'}},
                  reason=reason,n_rows=len(train),rounds=rounds,parameters=model.p,metrics=metrics,
                  seconds=time.monotonic()-start,
                  limitation='local_research;complete_horizon_followup_only;noncash_censoring_may_be_informative;not_pilot_acceptance')
    return register(store,firm,model,metadata,train.sample(min(1000,len(train)),random_state=7))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--firm',required=True)
    parser.add_argument('--reason',required=True,choices=['psi','coverage','scheduled','manual'])
    parser.add_argument('--cutoff',required=True);parser.add_argument('--state',default=os.environ.get('AGENT1_STATE_DIR','.state'))
    parser.add_argument('--activate',action='store_true')
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--dataset-output',type=Path)
    args=parser.parse_args()
    if args.prepare_only and (args.activate or args.dataset_output is None):
        parser.error('--prepare-only cần --dataset-output và không đi cùng --activate')
    if args.dataset_output is not None and not args.prepare_only:
        parser.error('--dataset-output chỉ dùng với --prepare-only')
    directory=Path(args.state)
    if not (directory/'agent1.db').is_file():
        raise ValueError('Chưa có agent1.db nguồn; không tạo kho rỗng hoặc dữ liệu giả để retrain')
    key_dir=Path(os.environ.get('AGENT1_KEY_DIR') or directory.parent/(directory.name+'-keys'))
    key_file=key_dir/'encryption.key'
    if not key_file.exists():key_file=directory/'encryption.key'
    if not key_file.exists():raise ValueError('Kho dữ liệu chưa được khởi tạo')
    store=Store(directory/'agent1.db',key_file.read_bytes())
    try:
        result=export_training_data(store,args.firm,args.cutoff,args.dataset_output) if args.prepare_only else train_candidate(store,args.firm,args.cutoff,args.reason)
        if args.activate:activate(store,args.firm,result['id'])
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    finally:store.connection.close()


if __name__=='__main__':main()
