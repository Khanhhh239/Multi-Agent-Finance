"""Synthetic five-row snapshots: evaluated hit, no-hit and unavailable."""
import argparse
import copy
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import secrets
import sys
import tempfile
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import jsonschema
from sme_fraud.auth import FileAuthorizer
from sme_fraud.import_files import canonical
from sme_fraud.method_adapters import score_snapshot
from sme_fraud.snapshots import SnapshotStore
from demo_method_scores import canonical_source


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir')
    parser.add_argument('--snapshot-db',default=str(ROOT/'.runtime/rule_result_demo/snapshots.sqlite3'))
    args=parser.parse_args();run=uuid.uuid4().hex
    output=Path(args.output_dir) if args.output_dir else ROOT/'.runtime/rule_result_demo'/run
    output.mkdir(parents=True,exist_ok=False)
    schema=json.loads((ROOT/'sme_fraud/rule_results.schema.json').read_text('utf-8'))
    store=SnapshotStore(args.snapshot_db);token=secrets.token_urlsafe(32);summary=[]
    with tempfile.TemporaryDirectory(prefix='rule_result_demo_') as temporary:
        path=Path(temporary)/'policy.json'
        policy={'policy_version':'1.0.0','principals':[{
            'actor_id':'rule-demo','tenant_id':'demo','token_sha256':hashlib.sha256(token.encode()).hexdigest(),
            'status':'active','expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
            'memberships':[{'company_id':'C001','role':'accountant','status':'active','permissions':['data.import']}]}]}
        path.write_bytes(canonical(policy))
        auth=FileAuthorizer(path);authorization='Bearer '+token
        scope=auth.authorize(authorization,'C001');recheck=lambda:auth.authorize(authorization,'C001')
        for label,name,status in (
                ('hit','North Harbour Equipment','evaluated_hit'),
                ('no_hit','Orchid Marine Instruments','evaluated_no_hit'),
                ('insufficient_name','12345','unavailable')):
            source=canonical_source()
            source['transactions']=[r for r in source['transactions'] if r['record_id'].startswith('T')]
            ids={r['record_id'] for r in source['transactions']}
            source['payment_allocations']=[a for a in source['payment_allocations'] if a['transaction_ref']['record_id'] in ids]
            current=source['vendors'][0];current['name']='North Harbor Equipment'
            other=copy.deepcopy(current);other.update(record_id='V002',name=name)
            other['source']['record_id']='V002';source['vendors'].append(other)
            draft=store.upload(scope,canonical(source),label+'.json',run+'-'+label+'-upload',recheck)
            preview=store.preview(scope,draft['import_id'],1,recheck)
            body={k:preview[k] for k in ('preview_id','source_hash','mapping_hash','report_hash','context_hash')}
            body.update(expected_revision=1,acknowledge=True)
            saved=store.commit(scope,draft['import_id'],body,run+'-'+label+'-commit',recheck)
            identity=saved['snapshot']['snapshot_id']
            result=score_snapshot(store,scope,identity,'2026-10-06T00:00:00+07:00',methods=(),recheck=recheck)
            assert result['row_count']==5 and [r['record_id'] for r in result['rows']]==['T0','T1','T2','T3','T4']
            for row in result['rows']:
                evaluated=row['methods']['rules']['details']['rule_results'];jsonschema.validate(evaluated,schema)
                e3=next(r for r in evaluated['rules'] if r['rule_id']=='E3')
                assert e3['status']==status and len(evaluated['rules'])==35
                assert row['methods']['rules']['score'] is None
            sample=result['rows'][0]['methods']['rules']['details']['rule_results']
            e3=next(r for r in sample['rules'] if r['rule_id']=='E3')
            c2=next(r for r in sample['rules'] if r['rule_id']=='C2')
            assert c2['status']=='unavailable' and c2['score'] is None and c2['matched'] is None
            assert any(g['table']=='approval_authorities' for g in c2['gaps'])
            assert recheck()==scope
            (output/(label+'.json')).write_bytes(canonical(result))
            summary.append(dict(scenario=label,snapshot_id=identity,input_transactions=5,output_results=5,
                E3={k:e3[k] for k in ('status','available','matched','intrinsic_points','score','reason','evidence_refs','details')},
                C2={k:c2[k] for k in ('status','available','matched','score','reason','gaps')},
                aggregate=sample['aggregate']))
            print(label,'| E3:',e3['status'],'| matched:',e3['matched'],'| gốc:',e3['intrinsic_points'],'| đóng góp:',e3['score'])
    (output/'summary.json').write_bytes(canonical(dict(data_kind='synthetic_technical_demo_not_accuracy',
        model_fit_called=False,active_model_changed=False,scenarios=summary)))
    print('Dữ liệu mô phỏng, không kết luận gian lận/độ chính xác. Kết quả:',output.resolve())
    return 0


if __name__=='__main__':raise SystemExit(main())
