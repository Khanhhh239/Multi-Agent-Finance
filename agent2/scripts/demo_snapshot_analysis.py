"""Real HTTP upload/commit/analyze with two scoped synthetic roles; no model fit."""
import argparse
from contextlib import closing
from datetime import datetime,timedelta,timezone
import hashlib
import http.client
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from sme_fraud.auth import FileAuthorizer
from sme_fraud.import_files import canonical
from sme_fraud.review_server import make_server
from sme_fraud.snapshots import SnapshotStore
from test_analysis_api import sample
from test_p1_evaluation import refresh,DAY
from test_snapshots import commit_fields
from test_validation_backend import policy_for


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',required=True)
    args=parser.parse_args();out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=False)
    reviewer=secrets.token_urlsafe(32);director=secrets.token_urlsafe(32)
    data=sample()
    for row in data['transactions']:row['description']='Giao dịch mô phỏng '+row['record_id']
    refresh(data)
    with tempfile.TemporaryDirectory() as tmp:
        base=Path(tmp);policy=policy_for(reviewer)
        manager=json.loads(json.dumps(policy['principals'][0]));manager.update(actor_id='synthetic-director',token_sha256=hashlib.sha256(director.encode()).hexdigest())
        manager['memberships'][0]['role']='director';policy['principals'].append(manager)
        path=base/'policy.json';path.write_bytes(canonical(policy));store=SnapshotStore(base/'snapshots.sqlite3')
        server=make_server(0,FileAuthorizer(path),store);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        checks=[]
        def call(name,method,route,expected,body=None,token=reviewer,headers=None):
            headers=dict(headers or {});headers.update(Authorization='Bearer '+token,**{'Content-Type':'application/json'})
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=30)
            try:
                connection.request(method,'/api/v1/companies/C001/'+route,canonical(body) if body is not None else None,headers)
                response=connection.getresponse();value=json.loads(response.read());assert response.status==expected,(name,response.status,value)
            finally:connection.close()
            (out/(name+'.json')).write_bytes(canonical(value));checks.append(dict(check=name,http_status=expected,passed=True));return value
        try:
            draft=call('upload','POST','imports/upload',201,data,headers={'Idempotency-Key':'analysis-demo-upload','X-File-Name':'synthetic-analysis.json'})
            prefix='imports/'+draft['import_id']
            preview=call('preview','POST',prefix+'/preview',200,dict(expected_revision=1))
            saved=call('commit','POST',prefix+'/commit',200,commit_fields(preview),headers={'Idempotency-Key':'analysis-demo-commit'})
            sid=saved['snapshot']['snapshot_id'];route='snapshots/'+sid+'/analyze'
            review=call('review','POST',route,200,dict(as_of=DAY(5)))
            technical=call('technical','POST',route,200,dict(as_of=DAY(5),view='technical'),token=director)
            repeated=call('repeat','POST',route,200,dict(as_of='2026-10-05T02:00:00Z'))
            assert review==repeated and review['analysis_id']==technical['analysis_id']
            assert review['row_count']==technical['row_count']==2
            row=next(r for r in technical['rows'] if r['transaction_id']=='NEW')
            assert row['rules']['P1']['score']==20 and row['rules']['E3']['score']==0 and row['rules']['E3']['matched']
            assert next(r for r in review['rows'] if r['transaction_id']=='NEW')['checks']['vendor_names']['needs_review']
            call('technical_denied_for_accountant','POST',route,403,dict(as_of=DAY(5),view='technical'))
            with closing(sqlite3.connect(store.path)) as conn:count=conn.execute('SELECT count(*) FROM snapshots').fetchone()[0]
            assert count==1
        finally:server.shutdown();server.server_close();thread.join(5)
    (out/'source.json').write_bytes(canonical(data))
    report=dict(data_kind='synthetic_HTTP_demo_not_accuracy',checks=checks,all_pass=True,rows=2,snapshot_count_after_repeat=count,
        review_and_technical_same_analysis_id=True,model_fit_performed=False,active_model_changed=False,queue_written=False,credentials_in_evidence=False)
    (out/'summary.json').write_bytes(canonical(report))
    print('HTTP analysis demo passed: 2 rows; P1=20; E3 matched with score=0; accountant technical denied; no fit.');return 0


if __name__=='__main__':raise SystemExit(main())
