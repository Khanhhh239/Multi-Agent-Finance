"""Real serialized FHE parity test against a separate ciphertext-only process.

This is a developer test harness, not an authenticated cloud service. Public
hashes detect corruption but provide no adversarial authenticity guarantee.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from concrete import fhe
from . import circuits as c
from .public_worker import digest


def inputs(profile):
    if profile=='statistics':return [(np.array([-16383,1]),),(np.array([0,0]),)]
    if profile=='graph':
        tokens=np.zeros((4,4,c.TOKEN_DIGITS),dtype=np.int64)
        for i in range(4):tokens[i,:,:]=i
        tokens[1,0]=tokens[0,0];tokens[2,1]=tokens[1,1];tokens[3,2]=tokens[0,2]
        return [(tokens,np.ones((4,4),dtype=np.int64),np.ones(4,dtype=np.int64))]
    def rows(values):return np.array([c.encode_money(v) for v in values+[0]*(4-len(values))])
    return [(rows([60000]),rows([40002]),rows([100000]),np.array([1,0,0,0]),c.encode_money(1),0),
            (rows([60000,-20000]),rows([40002]),rows([100000]),np.array([1,0,0,0]),c.encode_money(1),0)]


def check(bundle,output,worker_url=None,node_key_file=None,worker_key=None):
    manifest=json.loads((bundle/'manifest.json').read_bytes());profile=manifest['profile']
    for name,expected in manifest['files'].items():
        if digest(bundle/name)!=expected:raise ValueError('build integrity')
    if output.exists():raise ValueError('output exists')
    output.mkdir(parents=True);started=time.monotonic()
    specs=fhe.ClientSpecs.deserialize((bundle/'client.specs.json').read_bytes())
    client=fhe.Client(specs);client.keys.generate()
    keygen_seconds=time.monotonic()-started
    public_keys=client.evaluation_keys.serialize()
    key_path=output/'evaluation.keys';key_path.write_bytes(public_keys);key_hash=hashlib.sha256(public_keys).hexdigest();del public_keys
    checked=[];function={'rules':c.p1,'graph':c.graph,'statistics':c.robust_z}[profile]
    c.ARRAY=np.array
    for index,values in enumerate(inputs(profile)):
        root=output/f'trial-{index}';root.mkdir()
        # Hardlink the same public evaluation context, never private key bytes.
        (root/'evaluation.keys').hardlink_to(key_path)
        encrypted=client.encrypt(*values)
        if not isinstance(encrypted,tuple):encrypted=(encrypted,)
        hashes=[]
        for i,value in enumerate(encrypted):
            raw=value.serialize();(root/f'argument-{i}.cipher').write_bytes(raw);hashes.append(hashlib.sha256(raw).hexdigest())
        request=dict(version='he4-native-request/0.1.0',circuit_sha256=manifest['files']['server.zip'],evaluation_keys_sha256=key_hash,arguments_sha256=hashes)
        (root/'request.json').write_text(json.dumps(request,sort_keys=True),encoding='utf-8')
        before=time.monotonic()
        if worker_url:
            from types import SimpleNamespace
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from experiments.he_inference.http_common import post
            from experiments.he_inference.protocol import verify,sha,canonical
            from .client_transport import upload,download,envelope
            key=Ed25519PrivateKey.from_private_bytes(bytes.fromhex(Path(node_key_file).read_text().strip()))
            scope=SimpleNamespace(tenant_id='he4-test',company_ids=frozenset({'C001'}))
            public_hash=upload(worker_url,scope,key,worker_key,key_path,'public_evaluation_keys')
            argument_hashes=[upload(worker_url,scope,key,worker_key,root/f'argument-{i}.cipher','ciphertext') for i in range(len(encrypted))]
            packet=envelope(scope,key,dict(profile=profile,circuit_sha256=request['circuit_sha256'],evaluation_keys_sha256=public_hash,arguments_sha256=argument_hashes,session_id='test_'+output.name.replace('-','_')+'_'+str(index),nonce='trial_'+str(index)))
            response=post(worker_url,'/v1/evaluate',packet,timeout=600);p=verify(response,worker_key)
            expected_binding=dict(version='he4-worker/0.1.0',tenant_id='he4-test',company_id='C001',session_id=packet['payload']['session_id'],nonce=packet['payload']['nonce'],request_sha256=sha(canonical(packet)),result_sha256=p['result_sha256'],circuit_sha256=request['circuit_sha256'])
            if p!=expected_binding:raise ValueError('signed response binding')
            download(worker_url,scope,key,p['result_sha256'],root/'result.cipher')
            # Exact signed replay returns the committed ciphertext, not a new job.
            if post(worker_url,'/v1/evaluate',packet,timeout=30)!=response:raise ValueError('duplicate response mismatch')
            (root/'result.json').write_text(json.dumps(dict(request_sha256=digest(root/'request.json'),result_sha256=digest(root/'result.cipher'))))
        else:
            subprocess.run([sys.executable,'-m','experiments.he4.public_worker','--bundle',str(bundle),'--request',str(root),'--circuit-sha256',request['circuit_sha256']],check=True,timeout=600)
        elapsed=time.monotonic()-before;response=json.loads((root/'result.json').read_bytes())
        if response['request_sha256']!=digest(root/'request.json') or response['result_sha256']!=digest(root/'result.cipher'):raise ValueError('response integrity')
        actual=client.decrypt(fhe.Value.deserialize((root/'result.cipher').read_bytes()));expected=function(*values)
        if not np.array_equal(actual,expected):raise AssertionError(dict(actual=np.asarray(actual).tolist(),expected=np.asarray(expected).tolist()))
        checked.append(dict(trial=index,parity=True,seconds=elapsed))
    report=dict(profile=profile,actual_fhe=True,simulation=False,separate_worker_process=True,authenticated_http=bool(worker_url),cloud_deployment=False,checks=checked,keygen_seconds=keygen_seconds,evaluation_key_bytes=key_path.stat().st_size,seconds=time.monotonic()-started)
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--worker-url');p.add_argument('--node-key-file',type=Path);p.add_argument('--worker-key');a=p.parse_args()
    if a.worker_url and (not a.node_key_file or not a.worker_key):p.error('HTTP mode requires test node signing key and pinned worker key')
    check(a.bundle,a.output,a.worker_url,a.node_key_file,a.worker_key)
