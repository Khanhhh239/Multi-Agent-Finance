"""Authenticated HTTP parity using the actual DPAPI-protected company keys.

Isolated fixture only. Full Portal preflight is tested separately.
"""
import argparse
import json
from pathlib import Path
import socket
import sys
import time
import numpy as np
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT.parent)]
from finance_input import AccessScope
from portal.agent2_he4_runtime import LinuxRuntime,linux_path
from experiments.he4.bundle import build
from experiments.he4.windows_bridge import CryptoBridge
from experiments.he4.client_transport import envelope,upload,download
from experiments.he4.inputs import payment,graph
from experiments.he4 import circuits
from experiments.he_inference.protocol import canonical,verify,sha,public_hex
from experiments.he_inference.http_common import post


def run(output,prepared,builds):
    if output.exists():raise ValueError('new evidence directory required')
    output.mkdir(parents=True);started=time.monotonic();build(output/'bundle')
    node=Ed25519PrivateKey.generate();cloud=Ed25519PrivateKey.generate()
    (output/'cloud-signing.hex').write_text(cloud.private_bytes_raw().hex())
    scope=AccessScope('demo',frozenset({'C001'}),'fixture',frozenset({'data.import'}))
    (output/'grants.json').write_bytes(canonical(dict(version='he-worker-grants/1.0.0',grants=[dict(tenant_id='demo',company_id='C001',node_verify_key=public_hex(node),active=True)])))
    config=output/'worker.json';config.write_bytes(canonical(dict(version='he4-worker/0.1.0',state_dir=linux_path(output/'cloud'),grants_file=linux_path(output/'grants.json'),signing_key_file=linux_path(output/'cloud-signing.hex'),builds={k:linux_path(v) for k,v in builds.items()})))
    with socket.socket() as free:free.bind(('127.0.0.1',0));port=free.getsockname()[1]
    runtime=LinuxRuntime(dict(bundle=str(output/'bundle'),config=str(config),port=port,distro='Debian',python='/home/sang/.local/share/agent2/he4/bin/python'),ROOT,output/'unused-node',output/'unused-config',Path(sys.executable),output/'logs')
    runtime.preflight=lambda keys_only=False:None
    bridge=CryptoBridge(prepared/'private',prepared/'wrapping.dpapi.json');url=f'http://127.0.0.1:{port}';checks=[]
    samples=[('rules',payment([60000],[40002],[100000],['payment'])),
             ('rules',payment([60000,-20000],[40002],[100000],['payment','adjustment'])),
             ('graph',graph([{'bank_account':'demo-bank-1'},{'bank_account':'demo-bank-1','phone':'demo-phone'},{'phone':'demo-phone'},{'address':'context-only'}]))]
    try:
        runtime.start()
        for index,(profile,values) in enumerate(samples):
            before=time.monotonic();root=output/str(index);root.mkdir();bundle=builds[profile]
            context=bridge.encrypt(scope,bundle,[v.tolist() if hasattr(v,'tolist') else v for v in values],root/'input')
            upload(url,scope,node,public_hex(cloud),bridge.public_key(scope,bundle),'public_evaluation_keys')
            for i,expected in enumerate(context['arguments_sha256']):
                if upload(url,scope,node,public_hex(cloud),root/'input'/f'argument-{i}.cipher','ciphertext')!=expected:raise AssertionError('upload hash')
            circuit=json.loads((bundle/'manifest.json').read_bytes())['files']['server.zip']
            packet=envelope(scope,node,dict(profile=profile,circuit_sha256=circuit,evaluation_keys_sha256=context['evaluation_keys_sha256'],arguments_sha256=context['arguments_sha256'],session_id='http-parity-'+str(index),nonce='fixed-request'))
            response=post(url,'/v1/evaluate',packet,timeout=600);p=verify(response,public_hex(cloud))
            expected=dict(version='he4-worker/0.1.0',tenant_id='demo',company_id='C001',session_id=packet['payload']['session_id'],nonce=packet['payload']['nonce'],request_sha256=sha(canonical(packet)),result_sha256=p['result_sha256'],circuit_sha256=circuit)
            if p!=expected:raise AssertionError('response binding')
            download(url,scope,node,p['result_sha256'],root/'result.cipher')
            actual=bridge.decrypt(scope,bundle,root/'result.cipher',p['result_sha256'],root/'opened.sealed',context)
            clear={'rules':circuits.p1,'graph':circuits.graph}[profile](*values)
            if not np.array_equal(actual,clear):raise AssertionError('native parity')
            repeat=envelope(scope,node,dict(session_id=packet['payload']['session_id'],nonce=packet['payload']['nonce'],request_sha256=sha(canonical(packet))))
            if post(url,'/v1/results',repeat)!=response:raise AssertionError('committed result changed')
            checks.append(dict(profile=profile,case=index,parity=True,same_committed_ciphertext=True,seconds=time.monotonic()-before))
            print(json.dumps(checks[-1]),flush=True)
        report=dict(actual_fhe=True,authenticated_http=True,dpapi_real_keys=True,optimized_circuits=True,supervisor_preflight_mocked=True,cloud_deployment=False,checks=checks,seconds=time.monotonic()-started)
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
    finally:runtime.stop()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--build-root',type=Path,required=True);a=p.parse_args()
    run(a.output.resolve(),a.prepared.resolve(),{k:(a.build_root/v).resolve() for k,v in dict(statistics='build-statistics-v1',rules='build-rules-difference-v1',graph='build-graph-difference-v1').items()})
