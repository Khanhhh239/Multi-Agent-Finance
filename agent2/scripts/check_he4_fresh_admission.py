"""Actual P1 HE over HTTP after a seven-hour unadmitted-envelope pause.

Controlled C002 synthetic source, isolated worker and existing isolated test keys.
Never edits live data/models/keys or reads Portal credentials.
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
from experiments.he4 import FRESH_ADMISSION
from experiments.he4.bundle import build
from experiments.he4.windows_bridge import CryptoBridge
from experiments.he4.client_transport import envelope,upload,download
from experiments.he4.p1_demo import source,scope,save_snapshot,inspect
from experiments.he4.inputs import decode_payment
from experiments.he_inference.protocol import canonical,sha,verify,public_hex,sign
from experiments.he_inference.http_common import post,ServiceError
from sme_fraud.snapshots import SnapshotStore


def run(output,prepared,bundle):
    if output.exists():raise ValueError('new evidence directory required')
    output.mkdir(parents=True);started=time.monotonic();authority=scope('C002')
    store=SnapshotStore(output/'source.sqlite3');sid=save_snapshot(store,'C002',source('C002'));reference,plan=inspect(store,'C002',sid)
    row=next(r for r in plan['rows'] if r['record_id']=='P1_T05');request,=row['branches']['rules']['requests']
    expected=next(r for r in reference['rows'] if r['record_id']=='P1_T05')['plain_circuit_checks'][0];expected={k:v for k,v in expected.items() if k!='role'}
    cloud=output/'worker';cloud.mkdir();build(cloud/'bundle');node=Ed25519PrivateKey.generate();key=Ed25519PrivateKey.generate()
    (cloud/'signing.hex').write_text(key.private_bytes_raw().hex())
    (cloud/'grants.json').write_bytes(canonical(dict(version='he-worker-grants/1.0.0',grants=[dict(tenant_id='demo',company_id='C002',node_verify_key=public_hex(node),active=True)])))
    config=cloud/'worker.json';config.write_bytes(canonical(dict(version='he4-worker/0.1.0',state_dir=linux_path(cloud/'state'),grants_file=linux_path(cloud/'grants.json'),signing_key_file=linux_path(cloud/'signing.hex'),builds={'rules':linux_path(bundle)})))
    with socket.socket() as free:free.bind(('127.0.0.1',0));port=free.getsockname()[1]
    runtime=LinuxRuntime(dict(bundle=str(cloud/'bundle'),config=str(config),port=port,distro='Debian',python='/home/sang/.local/share/agent2/he4/bin/python'),ROOT,output/'unused-node',output/'unused-config',Path(sys.executable),output/'logs')
    runtime.preflight=lambda keys_only=False:None  # protocol fixture; CryptoBridge key/build gates remain real
    bridge=CryptoBridge(prepared/'private',prepared/'wrapping.dpapi.json');url=f'http://127.0.0.1:{port}'
    try:
        runtime.start();context=bridge.encrypt(authority,bundle,request['values'],output/'input')
        upload(url,authority,node,public_hex(key),bridge.public_key(authority,bundle),'public_evaluation_keys')
        for i,expected_hash in enumerate(context['arguments_sha256']):
            if upload(url,authority,node,public_hex(key),output/'input'/f'argument-{i}.cipher','ciphertext')!=expected_hash:raise AssertionError('ciphertext hash')
        manifest=json.loads((bundle/'manifest.json').read_bytes())
        packet=envelope(authority,node,dict(profile='rules',circuit_sha256=manifest['files']['server.zip'],evaluation_keys_sha256=context['evaluation_keys_sha256'],arguments_sha256=context['arguments_sha256'],session_id='expired-unadmitted-p1',nonce='saved'))
        packet=sign(dict(packet['payload'],expires_at=int(time.time())-7*3600),node)
        for path,body,code in (('/v1/evaluate',packet,'HE4_EXPIRED'),('/v1/resume',envelope(authority,node,dict(request=packet)),'SESSION_NOT_REGISTERED')):
            try:post(url,path,body);raise AssertionError('expired/unadmitted old route unexpectedly accepted')
            except ServiceError as error:
                if error.code!=code:raise
        print(json.dumps(dict(stage='real_fhe_fresh_admission',company='C002',record_id='P1_T05',inner_age_seconds=7*3600)),flush=True)
        response=post(url,'/v1/admit',envelope(authority,node,dict(request=packet,purpose=FRESH_ADMISSION)),timeout=600)
        signed=verify(response,public_hex(key));original=packet['payload']
        binding=dict(version='he4-worker/0.1.0',tenant_id='demo',company_id='C002',session_id=original['session_id'],nonce=original['nonce'],request_sha256=sha(canonical(packet)),circuit_sha256=manifest['files']['server.zip'],result_sha256=signed['result_sha256'])
        if signed!=binding:raise AssertionError('signed output binding')
        download(url,authority,node,signed['result_sha256'],output/'result.cipher')
        actual=decode_payment(bridge.decrypt(authority,bundle,output/'result.cipher',signed['result_sha256'],output/'opened.sealed',context))
        if actual!=expected:raise AssertionError((actual,expected))
        if post(url,'/v1/admit',envelope(authority,node,dict(request=packet,purpose=FRESH_ADMISSION)),timeout=600)!=response:raise AssertionError('duplicate admission changed result')
        if post(url,'/v1/results',envelope(authority,node,dict(session_id=original['session_id'],nonce=original['nonce'],request_sha256=sha(canonical(packet)))))!=response:raise AssertionError('retrieval changed result')
        report=dict(status='passed',actual_fhe=True,company_id='C002',record_id='P1_T05',source_rows=8,source_engine_parity=True,actual=actual,expired_inner_preserved=True,inner_age_seconds=7*3600,evaluate_expired_rejected=True,resume_unadmitted_rejected=True,fresh_purpose_bound_admission=True,duplicate_admission_same_result=True,packet_sha256=sha(canonical(packet)),simulated_data=True,model_fit_performed=False,live_services_changed=False,supervisor_preflight_mocked=True,seconds=time.monotonic()-started)
        (output/'report.json').write_bytes(canonical(report));print(json.dumps(report),flush=True)
    finally:runtime.stop()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--prepared',type=Path,required=True);parser.add_argument('--bundle',type=Path,required=True);args=parser.parse_args();run(args.output.resolve(),args.prepared.resolve(),args.bundle.resolve())
