"""Offline, score-only IF replay of an attested feature cache; no fit or queue writes."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
local_packages=ROOT/'.runtime/site-packages'
if local_packages.exists():
    sys.path.insert(0,str(local_packages))

import joblib
import numpy as np
import sklearn

from .feature_contract import digest, require_model, sha, validate_cache

VERSION='score-only-cache-v1'
EXCLUDED={'labels.csv','splits.csv'}


def guarded(path):
    path=Path(path).resolve()
    if any(p.casefold() in {'005','sme_fraud_005'} for p in path.parts):
        raise ValueError('Holdout 005 is excluded from shadow scoring')
    return path


def instant(value):
    if not isinstance(value,str):
        raise ValueError('Time must be ISO with a timezone')
    try:
        parsed=datetime.fromisoformat(value)
        if parsed.utcoffset() is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except (ValueError,OverflowError):
        raise ValueError('Time must be ISO with a timezone') from None


def scoring_scope(raw):
    if not isinstance(raw,dict) or set(raw)!={'company_ids','start_at','end_at','source_ref'}:
        raise ValueError('Scope requires company_ids, start_at, end_at and source_ref only')
    companies=raw['company_ids']
    if (not isinstance(companies,list) or not 1<=len(companies)<=100 or
            any(not isinstance(c,str) or not c.strip() or c!=c.strip() or len(c)>100 for c in companies) or
            len(set(companies))!=len(companies)):
        raise ValueError('Scope needs unique nonempty company IDs')
    if not isinstance(raw['source_ref'],str) or not raw['source_ref'].strip() or len(raw['source_ref'])>500:
        raise ValueError('Scope needs a source reference')
    start,end=instant(raw['start_at']),instant(raw['end_at'])
    if start>=end:
        raise ValueError('Scope start must be before its exclusive end')
    return dict(raw,company_ids=sorted(companies)),start,end


def output_guard(output,dataset,model):
    if output.exists():
        raise FileExistsError('Use a new output directory; existing runs are immutable')
    if output.is_relative_to(ROOT/'data') or output.is_relative_to(dataset) or output.is_relative_to(model.parent):
        raise ValueError('Output must be outside input/model directories')
    for parent in output.parents:
        if any((parent/name).is_file() for name in ('manifest.json','case_queue.csv','predictions_frozen.json')):
            raise ValueError('Output must be outside source/detection snapshots')


def source_checks(dataset,metadata):
    checks={}
    for name,entry in metadata['files'].items():
        if not isinstance(name,str) or Path(name).name!=name or '\\' in name or '/' in name:
            raise ValueError('Manifest input names must be plain filenames')
        if name in EXCLUDED:
            continue
        path=guarded(dataset/name)
        if not path.is_relative_to(dataset):
            raise ValueError('Manifest input resolves outside the feature cache')
        expected=entry['sha256'] if isinstance(entry,dict) else entry
        if sha(path)!=expected:
            raise ValueError('Input checksum differs from manifest: '+name)
        checks[name]=expected
    if not {'features.csv','transactions.csv'}<=set(checks):
        raise ValueError('Manifest must bind features.csv and transactions.csv')
    return checks


def selected_matrix(dataset,columns,scope,start,end):
    transactions={}
    selected={}
    with (dataset/'transactions.csv').open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream)
        if not {'transaction_id','company_id','posted_at'}<=set(reader.fieldnames or []):
            raise ValueError('Transactions need stable ID, company and posted_at')
        for row in reader:
            tid=row['transaction_id']
            if not tid or tid in transactions:
                raise ValueError('Duplicate or empty transaction ID')
            when=instant(row['posted_at'])
            transactions[tid]=row['company_id']
            if row['company_id'] in scope['company_ids'] and start<=when<end:
                selected[tid]={k:row[k] for k in ('transaction_id','company_id','posted_at')}
    if set(scope['company_ids'])-set(transactions.values()):
        raise ValueError('Requested company is absent from source')
    records=[]
    matrix=[]
    seen=set()
    with (dataset/'features.csv').open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.reader(stream)
        if next(reader,None)!=['transaction_id',*columns]:
            raise ValueError('Feature columns must exactly match the ordered allowlist')
        for row in reader:
            if len(row)!=1+len(columns) or not row[0] or row[0] in seen:
                raise ValueError('Invalid feature width or duplicate/empty ID')
            tid=row[0]
            seen.add(tid)
            if tid not in transactions:
                raise ValueError('Feature ID is absent from transactions')
            values=np.asarray(row[1:],dtype=np.float32)
            if not np.isfinite(values).all():
                raise ValueError('Nonfinite feature values')
            if tid in selected:
                records.append(selected[tid]);matrix.append(values)
    if seen!=set(transactions):
        raise ValueError('Feature and transaction coverage differ')
    if not records:
        raise ValueError('No observations in the requested company/time scope')
    return records,np.asarray(matrix,dtype=np.float32)


def run_shadow(dataset,model_path,output,*,model_sha256,scope,batch_size=2048):
    dataset,model_path,output=(guarded(p) for p in (dataset,model_path,output))
    scope,start,end=scoring_scope(scope)
    if type(batch_size) is not int or not 1<=batch_size<=10000:
        raise ValueError('Batch size must be 1–10000')
    output_guard(output,dataset,model_path)
    manifest_bytes=(dataset/'manifest.json').read_bytes()
    manifest_sha=hashlib.sha256(manifest_bytes).hexdigest()
    metadata=json.loads(manifest_bytes)
    contract=validate_cache(metadata)
    model_bytes=model_path.read_bytes()
    actual_model_sha=hashlib.sha256(model_bytes).hexdigest()
    if actual_model_sha!=model_sha256:
        raise ValueError('Model checksum differs from the explicitly selected artifact')
    # Only load trusted workspace artifacts. Deserialization uses the exact checked bytes.
    artifact=joblib.load(io.BytesIO(model_bytes))
    compatibility=require_model(artifact,metadata,sklearn.__version__)
    inputs=source_checks(dataset,metadata)
    rows,matrix=selected_matrix(dataset,contract['columns'],scope,start,end)
    scores=[]
    for offset in range(0,len(rows),batch_size):
        batch=matrix[offset:offset+batch_size]
        result=-np.asarray(artifact['model'].score_samples(batch),dtype=np.float64)
        if result.shape!=(len(batch),) or not np.isfinite(result).all():
            raise ValueError('Estimator returned invalid scores')
        scores.extend(float(v) for v in result)
    if sha(dataset/'manifest.json')!=manifest_sha or sha(model_path)!=actual_model_sha or source_checks(dataset,metadata)!=inputs:
        raise ValueError('Scoring inputs changed during the run')
    run=dict(version=VERSION,mode='technical_cache_replay',scope=scope,scope_end_exclusive=True,
        dataset=str(dataset),dataset_version=metadata['version'],data_origin=metadata.get('data_origin','not_attested'),
        manifest_sha256=manifest_sha,input_sha256=inputs,model_path=str(model_path),model_sha256=actual_model_sha,
        feature_contract_fingerprint=contract['fingerprint'],sklearn_version=sklearn.__version__,
        training_feature_fingerprint=artifact['training_feature_fingerprint'],compatibility=compatibility,
        rows_scored=len(rows),score_direction='higher_is_more_anomalous',models_fitted=0,
        labels_loaded=False,splits_loaded=False,feature_rebuild=False,threshold_changed=False,
        queue_changed=False,external_notifications=0,holdout_005_loaded_or_scored=False,
        source_acceptance_verified=False,model_training_window_disjointness_verified=False,
        operational_benefit_measured=False,independent_review=False,
        gates=dict(real_source='awaiting_accepted_real_data',protocol='awaiting_business_approval',
                   temporal_model_provenance='not_verified_by_this_runner',benefit='not_measured'))
    run['run_id']=digest(run)
    output.parent.mkdir(parents=True,exist_ok=True)
    # Inherit the destination ACL. tempfile.mkdtemp uses private Windows ACLs,
    # which would remain on a renamed output directory and block other readers.
    staged=output.parent/('.shadow-'+uuid.uuid4().hex)
    staged.mkdir()
    try:
        with (staged/'shadow_scores.csv').open('w',encoding='utf-8',newline='') as stream:
            fields=['run_id','transaction_id','company_id','posted_at','anomaly_score']
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
            writer.writerows(dict(row,run_id=run['run_id'],anomaly_score=score) for row,score in zip(rows,scores))
        run['scores_sha256']=sha(staged/'shadow_scores.csv')
        (staged/'run.json').write_text(json.dumps(run,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if output.exists():
            raise FileExistsError('Output appeared during scoring; refusing to replace it')
        staged.rename(output)
    finally:
        if staged.exists():
            for name in ('shadow_scores.csv','run.json'):
                (staged/name).unlink(missing_ok=True)
            staged.rmdir()
    return run


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',required=True,type=Path)
    parser.add_argument('--model',required=True,type=Path)
    parser.add_argument('--model-sha256',required=True)
    parser.add_argument('--scope',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--batch-size',type=int,default=2048)
    args=parser.parse_args()
    scope=json.loads(guarded(args.scope).read_text(encoding='utf-8'))
    result=run_shadow(args.dataset,args.model,args.output,model_sha256=args.model_sha256,scope=scope,batch_size=args.batch_size)
    print(json.dumps(dict(run_id=result['run_id'],rows_scored=result['rows_scored'],mode=result['mode'],output=str(args.output))))


if __name__=='__main__':main()
