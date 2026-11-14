"""Synthetic P1 input declarations with the current evaluator; no model fitting."""
import argparse
import copy
import json
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from sme_fraud.imports import validate_input
from sme_fraud.import_files import canonical
from sme_fraud.p1_inputs import export_manifest,transaction_inputs
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.method_adapters import score_snapshot
from test_p1_inputs import p1_bundle
from test_snapshot_features import scope
from test_snapshots import commit_fields


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',required=True)
    parser.add_argument('--snapshot-db',default=str(ROOT/'.runtime/p1_input_demo/snapshots.sqlite3'))
    args=parser.parse_args();output=Path(args.output_dir);output.mkdir(parents=True,exist_ok=False)
    scope_one=scope();source=p1_bundle();summary=[];run=uuid.uuid4().hex
    for name in ('declared_complete','missing_channel','partial_history','tampered_manifest'):
        data=copy.deepcopy(source);tx=next(r for r in data['transactions'] if r['record_id']=='T001')
        claim=data['payment_history_coverage'][0]
        if name=='missing_channel':
            tx['payment_channel']='unknown';claim['manifest']=export_manifest(data,claim)
        elif name=='partial_history':claim['coverage_status']='partial'
        elif name=='tampered_manifest':claim['manifest']['records_sha256']='0'*64
        report=validate_input(data,scope_one);_,state=transaction_inputs(data,tx)
        assert state['available']==(name=='declared_complete')
        assert (report['status']=='rejected')==(name=='tampered_manifest')
        (output/(name+'.json')).write_bytes(canonical(data))
        (output/(name+'-validation.json')).write_bytes(canonical(report))
        summary.append(dict(scenario=name,validation_status=report['status'],target='T001',p1_input=state))
    store=SnapshotStore(args.snapshot_db)
    draft=store.upload(scope_one,canonical(source),'p1-source.json',run+'-upload')
    preview=store.preview(scope_one,draft['import_id'],1)
    saved=store.commit(scope_one,draft['import_id'],commit_fields(preview),run+'-commit')
    repeated=store.commit(scope_one,draft['import_id'],commit_fields(preview),run+'-commit')
    assert saved['snapshot']['snapshot_id']==repeated['snapshot']['snapshot_id']
    assert saved['snapshot']['contract_version']=='1.1.0'
    result=score_snapshot(store,scope_one,saved['snapshot']['snapshot_id'],'2026-10-13T00:00:00+07:00',methods=())
    assert result['row_count']==len(source['transactions'])==6
    target=next(r for r in result['rows'] if r['record_id']=='T001')
    p1=next(r for r in target['methods']['rules']['details']['rule_results']['rules'] if r['rule_id']=='P1')
    assert p1['score']==0 and p1['status']=='evaluated_no_hit' and p1['reason'] is None
    (output/'snapshot.json').write_bytes(canonical(saved['snapshot']))
    (output/'results.json').write_bytes(canonical(result))
    (output/'summary.json').write_bytes(canonical(dict(data_kind='synthetic_input_demo_not_accuracy',
        scenarios=summary,snapshot_id=saved['snapshot']['snapshot_id'],contract_version='1.1.0',
        commit_retry_same_snapshot=True,input_rows=6,output_rows=result['row_count'],
        P1_result=p1,active_model_changed=False,model_fit_performed=False)))
    for s in summary:print(s['scenario'],'|',s['validation_status'],'| P1 input:',s['p1_input']['available'])
    print('Snapshot 1.1.0: 6/6 kết quả; retry không trùng; P1 T001 không vượt tổng hóa đơn.')
    return 0


if __name__=='__main__':raise SystemExit(main())
