"""Synthetic business examples of allocation-based P1; no model fit/activation."""
import argparse
import json
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from sme_fraud.import_files import canonical
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.method_adapters import score_snapshot
from test_p1_evaluation import payments,DAY
from test_snapshot_features import scope
from test_snapshots import commit_fields


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',required=True)
    parser.add_argument('--snapshot-db',default=str(ROOT/'.runtime/p1_evaluation_demo/snapshots.sqlite3'))
    args=parser.parse_args();output=Path(args.output_dir);output.mkdir(parents=True,exist_ok=False)
    examples={
        'prior_overpayment':(payments([('OLD',4_000_000,DAY(1)),('NEW',7_000_000,DAY(2))]),'NEW',20),
        'simultaneous':(payments([('OLD',4_000_000,DAY(1)),('NEW',4_000_000,DAY(2)),('PEER',4_000_000,DAY(2))]),'NEW',0),
        'signed_reduction':(payments([('OLD',12_000_000,DAY(1)),('REDUCE',-2_000_000,DAY(2),{'adjusts':'OLD'}),('NEW',1_000_000,DAY(3))],cap=12_000_000),'NEW',0),
        'late_reduction':(payments([('OLD',12_000_000,DAY(1)),('REDUCE',-2_000_000,DAY(2),{'adjusts':'OLD','observed_at':DAY(4)}),('NEW',1_000_000,DAY(3))],cap=12_000_000),'NEW',20),
        'missing_history':(payments([('OLD',4_000_000,DAY(1)),('NEW',7_000_000,DAY(2))]),'NEW',None)}
    examples['missing_history'][0]['payment_history_coverage']=[]
    store=SnapshotStore(args.snapshot_db);authority=scope();summary=[]
    for name,(data,target,expected) in examples.items():
        run=uuid.uuid4().hex;draft=store.upload(authority,canonical(data),name+'.json',run+'-upload')
        preview=store.preview(authority,draft['import_id'],1);assert preview['status']!='rejected'
        saved=store.commit(authority,draft['import_id'],commit_fields(preview),run+'-commit')
        retry=store.commit(authority,draft['import_id'],commit_fields(preview),run+'-commit')
        assert saved['snapshot']['snapshot_id']==retry['snapshot']['snapshot_id']
        result=score_snapshot(store,authority,saved['snapshot']['snapshot_id'],DAY(20),methods=())
        assert result['row_count']==len(data['transactions'])
        row=next(r for r in result['rows'] if r['record_id']==target)
        p1=next(r for r in row['methods']['rules']['details']['rule_results']['rules'] if r['rule_id']=='P1')
        assert p1['score']==expected
        if name=='simultaneous':assert p1['details']['simultaneous_checks'][0]['points']==20
        if name=='signed_reduction':assert p1['details']['invoice_checks'][0]['prior_paid_vnd']==10_000_000
        if name=='late_reduction':
            earlier=score_snapshot(store,authority,saved['snapshot']['snapshot_id'],DAY(3),methods=())
            old=next(r for r in earlier['rows'] if r['record_id']==target)
            assert next(r for r in old['methods']['rules']['details']['rule_results']['rules'] if r['rule_id']=='P1')==p1
        for file,value in (('source',data),('validation',preview),('snapshot',saved['snapshot']),('results',result)):
            (output/(name+'-'+file+'.json')).write_bytes(canonical(value))
        summary.append(dict(scenario=name,target=target,input_rows=len(data['transactions']),output_rows=result['row_count'],
            status=p1['status'],row_score=p1['score'],reason=p1['reason'],invoice_checks=p1['details'].get('invoice_checks',[]),
            simultaneous_checks=p1['details'].get('simultaneous_checks',[]),commit_retry_same_snapshot=True))
        print(name,'|',p1['status'],'| row score:',p1['score'])
    report=dict(data_kind='synthetic_business_examples_not_accuracy',scenarios=summary,model_fit_performed=False,
        active_model_changed=False,queue_written=False,row_points_exclude_simultaneous_group_points=True)
    (output/'summary.json').write_bytes(canonical(report));return 0


if __name__=='__main__':raise SystemExit(main())
