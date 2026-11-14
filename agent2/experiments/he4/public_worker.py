"""Ciphertext-only Concrete evaluation process. Never imports enterprise code."""
import argparse
import hashlib
import json
from pathlib import Path
import os
from concrete import fhe


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def evaluate(bundle,request,expected_circuit):
    manifest=json.loads((request/'request.json').read_bytes())
    if set(manifest)!={'version','circuit_sha256','evaluation_keys_sha256','arguments_sha256'} or manifest['version']!='he4-native-request/0.1.0':raise ValueError('invalid request')
    circuit=bundle/'server.zip'
    if digest(circuit)!=expected_circuit or expected_circuit!=manifest['circuit_sha256']:raise ValueError('unpinned circuit')
    if not isinstance(manifest['arguments_sha256'],list) or not 1<=len(manifest['arguments_sha256'])<=10:raise ValueError('argument count')
    key_path=request/'evaluation.keys'
    if key_path.stat().st_size>2*1024**3 or digest(key_path)!=manifest['evaluation_keys_sha256']:raise ValueError('public key integrity')
    arguments=[]
    for i,expected in enumerate(manifest['arguments_sha256']):
        path=request/f'argument-{i}.cipher'
        if path.stat().st_size>64*1024**2 or digest(path)!=expected:raise ValueError('ciphertext integrity')
        arguments.append(fhe.Value.deserialize(path.read_bytes()))
    keys=fhe.EvaluationKeys.deserialize(key_path.read_bytes())
    server=fhe.Server.load(circuit)
    (request/'native.started').write_text('ciphertext evaluation started',encoding='utf-8')
    result=server.run(*arguments,evaluation_keys=keys)
    raw=result.serialize();temporary=request/'result.pending';temporary.write_bytes(raw)
    os.replace(temporary,request/'result.cipher')
    (request/'result.json').write_text(json.dumps(dict(version='he4-native-response/0.1.0',request_sha256=digest(request/'request.json'),result_sha256=hashlib.sha256(raw).hexdigest())),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--request',type=Path,required=True);parser.add_argument('--circuit-sha256',required=True);a=parser.parse_args();evaluate(a.bundle,a.request,a.circuit_sha256)
