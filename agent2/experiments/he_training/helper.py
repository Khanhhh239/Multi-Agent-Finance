"""Enterprise-only Concrete helper. Wrapping key arrives through stdin, never argv."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
from concrete import fhe
from experiments.he4.vault import seal,open_private
from .protocol import sha,canonical,require,atomic,decode,encode,strict_json


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['provision','encrypt-data','encrypt-labels','open-model']);p.add_argument('--root',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    request=strict_json(sys.stdin.buffer.read(24*1024*1024+1));key=decode(request.pop('wrapping_key'));require(len(key)==32,'WRAPPING_KEY')
    binding=request['binding'];manifest=json.loads((a.build/'manifest.json').read_bytes())
    require(manifest['files']['server.zip']==binding['build_sha256'],'BUILD_BINDING')
    for name,digest in manifest['files'].items():require(sha((a.build/name).read_bytes())==digest,'BUILD_TAMPERED')
    a.root.mkdir(parents=True,exist_ok=True)
    client=fhe.Client(fhe.ClientSpecs.deserialize((a.build/'client.specs.json').read_bytes()))
    private=a.root/'context.sealed';public=a.root/'evaluation.keys'
    if a.action=='provision':
        require(not private.exists() and not public.exists(),'CONTEXT_ALREADY_EXISTS')
        client.keys.generate();seal(private,key,binding,client.keys.serialize());atomic(public,client.evaluation_keys.serialize())
        result=dict(binding=binding,evaluation_keys_sha256=sha(public.read_bytes()),private_keys_persisted='AES-GCM wrapped by enterprise DPAPI key')
    else:
        raw=open_private(private,key,binding);client.keys=fhe.Keys.deserialize(raw);del raw
        if a.action=='encrypt-data':
            x=np.asarray(request['x']);require(x.shape==(4,2) and np.issubdtype(x.dtype,np.integer) and np.all((-1<=x)&(x<=1)),'FEATURE_DOMAIN')
            values=client.encrypt(x.astype(np.int64),None,None);result=dict(x_cipher=encode(values[0].serialize()),x_cipher_sha256=sha(values[0].serialize()))
        elif a.action=='encrypt-labels':
            y=np.asarray(request['y']);require(y.shape==(4,) and np.issubdtype(y.dtype,np.integer) and set(y.tolist())=={0,1},'LABEL_DOMAIN')
            values=client.encrypt(None,y.astype(np.int64),np.zeros(3,dtype=np.int64));result=dict(y_cipher=encode(values[1].serialize()),y_cipher_sha256=sha(values[1].serialize()),weights_cipher=encode(values[2].serialize()),weights_cipher_sha256=sha(values[2].serialize()))
        else:
            raw=decode(request['model_cipher']);require(sha(raw)==request['model_cipher_sha256'],'MODEL_CIPHER_HASH')
            weights=np.asarray(client.decrypt(fhe.Value.deserialize(raw)));require(weights.shape==(3,) and np.all((-2<=weights[:2])&(weights[:2]<=2)) and -4<=weights[2]<=4,'MODEL_DOMAIN')
            result=dict(weights_code=weights.tolist(),coefficients=(weights[:2]/2).tolist(),intercept=float(weights[2]/2))
    atomic(a.output,canonical(result));print(json.dumps(dict(status='ok',action=a.action)),flush=True)


if __name__=='__main__':main()
