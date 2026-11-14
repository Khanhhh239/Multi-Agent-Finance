"""Real HE/HTTP parity from the new immutable P1 source snapshot.

Uses existing isolated company test keys. No live model/key/state changes.
Missing history and the standalone adjustment must not be sent for P1 scoring.
"""
import argparse
import json
from pathlib import Path
import socket
import sys
import time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT.parent)]
from portal.agent2_he4_runtime import LinuxRuntime,linux_path
from experiments.he4.bundle import build
from experiments.he4.windows_bridge import CryptoBridge
from experiments.he4.client_transport import envelope,upload,download
from experiments.he4.p1_demo import source,scope,save_snapshot,inspect
from experiments.he4.inputs import decode_payment
from experiments.he_inference.protocol import canonical,sha,verify,public_hex
from experiments.he_inference.http_common import post
from sme_fraud.snapshots import SnapshotStore


def run(output,prepared,builds,company):
    if output.exists():raise ValueError('new evidence directory required')
    output.mkdir(parents=True);started=time.monotonic();authority=scope(company)
    store=SnapshotStore(output/'source.sqlite3');sid=save_snapshot(store,company,source(company));reference,plan=inspect(store,company,sid)
    (output/'source-check.json').write_bytes(canonical(reference))
    requests={};rows={r['record_id']:r for r in reference['rows']}
    # Six evaluated rows are retained in the plan. T01 is the history anchor;
    # five distinct encrypted inputs cover the actual acceptance scenarios.
    for row in plan['rows']:
        if row['record_id']=='P1_T01':continue
        branch=row['branches']['rules']
        for req in branch['requests']:
            fingerprint=sha(canonical(req['values']))
            target=requests.setdefault(fingerprint,dict(values=req['values'],members=[]))
            want=rows[row['record_id']]['plain_circuit_checks']
            check=next(r for r in want if r['role']==req['role'])
            target['members'].append(dict(record_id=row['record_id'],role=req['role'],expected={k:v for k,v in check.items() if k!='role'}))
    if len(requests)!=5:raise AssertionError('changed source scenario coverage')
    if any(m['record_id'] in ('P1_T04','P1_T08') for task in requests.values() for m in task['members']):raise AssertionError('missing/not-applicable encrypted')
    cloud=output/'worker';cloud.mkdir();build(cloud/'bundle');node=Ed25519PrivateKey.generate();key=Ed25519PrivateKey.generate()
    (cloud/'signing.hex').write_text(key.private_bytes_raw().hex())
    (cloud/'grants.json').write_bytes(canonical(dict(version='he-worker-grants/1.0.0',grants=[dict(tenant_id='demo',company_id=company,node_verify_key=public_hex(node),active=True)])))
    config=cloud/'worker.json';config.write_bytes(canonical(dict(version='he4-worker/0.1.0',state_dir=linux_path(cloud/'state'),grants_file=linux_path(cloud/'grants.json'),signing_key_file=linux_path(cloud/'signing.hex'),builds={k:linux_path(v) for k,v in builds.items()})))
    with socket.socket() as free:free.bind(('127.0.0.1',0));port=free.getsockname()[1]
    runtime=LinuxRuntime(dict(bundle=str(cloud/'bundle'),config=str(config),port=port,distro='Debian',python='/home/sang/.local/share/agent2/he4/bin/python'),ROOT,output/'unused-node',output/'unused-config',Path(sys.executable),output/'logs')
    runtime.preflight=lambda keys_only=False:None  # this fixture isolates P1; real key gates still run below
    bridge=CryptoBridge(prepared/'private',prepared/'wrapping.dpapi.json');url=f'http://127.0.0.1:{port}';bundle=builds['rules'];manifest=json.loads((bundle/'manifest.json').read_bytes());checks=[]
    try:
        runtime.start()
        for index,task in enumerate(requests.values()):
            before=time.monotonic();root=output/('task-'+str(index));root.mkdir()
            context=bridge.encrypt(authority,bundle,task['values'],root/'input')
            upload(url,authority,node,public_hex(key),bridge.public_key(authority,bundle),'public_evaluation_keys')
            for i,expected in enumerate(context['arguments_sha256']):
                if upload(url,authority,node,public_hex(key),root/'input'/f'argument-{i}.cipher','ciphertext')!=expected:raise AssertionError('argument checksum')
            packet=envelope(authority,node,dict(profile='rules',circuit_sha256=manifest['files']['server.zip'],evaluation_keys_sha256=context['evaluation_keys_sha256'],arguments_sha256=context['arguments_sha256'],session_id='p1-source-'+str(index),nonce='fixed'))
            response=post(url,'/v1/evaluate',packet,timeout=600);signed=verify(response,public_hex(key));original=packet['payload']
            binding=dict(version='he4-worker/0.1.0',tenant_id='demo',company_id=company,session_id=original['session_id'],nonce=original['nonce'],request_sha256=sha(canonical(packet)),circuit_sha256=manifest['files']['server.zip'],result_sha256=signed['result_sha256'])
            if signed!=binding:raise AssertionError('signed response binding')
            download(url,authority,node,signed['result_sha256'],root/'result.cipher')
            value=bridge.decrypt(authority,bundle,root/'result.cipher',signed['result_sha256'],root/'opened.sealed',context);actual=decode_payment(value)
            for member in task['members']:
                if actual!=member['expected']:raise AssertionError((member['record_id'],member['role'],'HE/source-engine mismatch'))
            again=post(url,'/v1/results',envelope(authority,node,dict(session_id=original['session_id'],nonce=original['nonce'],request_sha256=sha(canonical(packet)))))
            if again!=response:raise AssertionError('committed result changed')
            checks.append(dict(members=[{k:v for k,v in m.items() if k!='expected'} for m in task['members']],parity=True,actual=actual,seconds=time.monotonic()-before))
            (output/'progress.json').write_bytes(canonical(dict(company_id=company,completed=len(checks),total=5,checks=checks)))
            print(json.dumps(dict(company_id=company,completed=len(checks),total=5,seconds=checks[-1]['seconds'])),flush=True)
        report=dict(status='passed',company_id=company,actual_fhe=True,authenticated_http=True,source_snapshot_validated=True,
            simulated_data=True,source_rows_retained=8,distinct_p1_encrypted_requests=5,checks=checks,
            missing_history_unavailable=True,standalone_adjustment_not_applicable=True,supervisor_preflight_mocked=True,
            live_services_changed=False,model_fit_performed=False,seconds=time.monotonic()-started)
        (output/'report.json').write_bytes(canonical(report));print(json.dumps(dict(status='passed',company_id=company,actual_fhe=True,checks=len(checks))),flush=True)
    finally:runtime.stop()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--build-root',type=Path,required=True);p.add_argument('--company',choices=('C001','C002'),required=True);a=p.parse_args()
    run(a.output.resolve(),a.prepared.resolve(),{k:(a.build_root/v).resolve() for k,v in dict(statistics='build-statistics-v1',rules='build-rules-difference-v1',graph='build-graph-difference-v1').items()},a.company)
