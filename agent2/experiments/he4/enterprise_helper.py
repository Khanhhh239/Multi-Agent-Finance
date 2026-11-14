"""Linux enterprise crypto helper. Secrets arrive only over parent stdin.

Never ship this module in the cloud bundle. Provision is an explicit operator
step; encrypt/open require the same saved context and cannot generate new keys.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import numpy as np
from concrete import fhe
from experiments.he_inference.node_job_store import StateLock
from .blob_store import BlobStore
from .vault import seal,open_private
from experiments.he_inference.protocol import canonical,sha


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['provision','encrypt','open']);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--vault',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
    # Stdout contains public hashes/status only. No secret, feature or model is
    # printed. Input is bounded; native key bytes are read from sealed storage.
    line=sys.stdin.buffer.read(8*1024*1024+1)
    if len(line)>8*1024*1024:raise ValueError('helper input limit')
    request=json.loads(line);required={'wrapping_key','tenant_id','company_id'}|({'values','recover_uncommitted'} if a.action=='encrypt' else {'ciphertext_file','ciphertext_sha256'} if a.action=='open' else set())
    if not isinstance(request,dict) or set(request)!=required:raise ValueError('helper fields')
    key=base64.b64decode(request.pop('wrapping_key'),validate=True)
    if len(key)!=32:raise ValueError('enterprise wrapping key')
    manifest=json.loads((a.bundle/'manifest.json').read_bytes())
    for name in ('server.zip','client.specs.json'):
        if BlobStore.digest(a.bundle/name)!=manifest['files'][name]:raise ValueError('build integrity')
    binding=dict(tenant_id=request['tenant_id'],company_id=request['company_id'],profile=manifest['profile'],circuit_sha256=manifest['files']['server.zip'],specs_sha256=manifest['files']['client.specs.json'])
    expected=hashlib.sha256(json.dumps(binding,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if a.vault.name!=expected:raise ValueError('private context path binding')
    if a.action=='provision':a.vault.mkdir(parents=True,exist_ok=True)
    if not a.vault.is_dir():raise ValueError('private context not provisioned')
    lock=StateLock(a.vault)
    try:
        client=fhe.Client(fhe.ClientSpecs.deserialize((a.bundle/'client.specs.json').read_bytes()))
        path=a.vault/'context.sealed';public_path=a.vault/'evaluation.keys';metadata=a.vault/'context.json'
        if a.action=='provision' and not path.exists():
            # Provision never overwrites partial/corrupt state or an old epoch.
            if public_path.exists() or metadata.exists():raise ValueError('incomplete provisioning requires operator recovery')
            client.keys.generate();raw=client.keys.serialize();seal(path,key,binding,raw);del raw
            public_path.write_bytes(client.evaluation_keys.serialize())
            meta=dict(binding=binding,evaluation_keys_sha256=BlobStore.digest(public_path),key_epoch='key_'+hashlib.sha256(os.urandom(32)).hexdigest())
            metadata.write_text(json.dumps(meta,sort_keys=True),encoding='utf-8')
        else:
            client.keys=fhe.Keys.deserialize(open_private(path,key,binding))
            meta=json.loads(metadata.read_bytes())
            if meta['binding']!=binding or meta['evaluation_keys_sha256']!=BlobStore.digest(public_path):raise ValueError('saved key context integrity')
        if a.action=='encrypt':
            def integers(value):return type(value) is int or isinstance(value,list) and all(integers(item) for item in value)
            if not isinstance(request['values'],list) or not all(integers(value) for value in request['values']):raise ValueError('integer inputs required; no implicit numeric conversion')
            values=[np.array(value,dtype=np.int64) for value in request['values']]
            profile=manifest['profile']
            shapes={'statistics':[(2,)],'graph':[(4,4,64),(4,4),(4,)],'rules':[(4,32),(4,32),(4,32),(4,),(32,),()],'c3':[(16,),(16,),(16,),(16,),(),(4,16),(4,16),(4,),(4,),(4,)]}[profile]
            if len(values)!=len(shapes) or any(value.shape!=shape for value,shape in zip(values,shapes)):raise ValueError('HE feature shape')
            if profile=='statistics':valid=np.all(np.abs(values[0])<=16383)
            elif profile=='graph':valid=np.all((values[0]>=0)&(values[0]<16)) and all(np.all((v>=0)&(v<=1)) for v in values[1:])
            elif profile=='c3':valid=(all(np.all((values[i]>=0)&(values[i]<16)) for i in (0,1,2,3,5,6)) and np.all((values[4]>=0)&(values[4]<=1)) and np.all((values[7]>=0)&(values[7]<=4)) and np.all((values[8]>=0)&(values[8]<=1)) and np.all((values[9]>=0)&(values[9]<=8)))
            else:valid=all(np.all((values[i]>=0)&(values[i]<16)) for i in (0,1,2,4)) and all(np.all((values[i]>=0)&(values[i]<=1)) for i in (3,5))
            if not valid:raise ValueError('HE feature domain')
            if a.output is None or type(request['recover_uncommitted']) is not bool:raise ValueError('encrypted output required')
            if a.output.exists():
                # This flag is only sent when the DN write-ahead record proves
                # no context/envelope has been sent. Hold the vault OS lock so
                # an orphaned old helper cannot still be writing these files.
                if not request['recover_uncommitted'] or (a.output/'manifest.sealed').exists():raise ValueError('committed output cannot be replaced')
                parts=list(a.output.iterdir());allowed={f'argument-{i}.cipher' for i in range(len(shapes))}
                if any(p.is_symlink() or not p.is_file() or p.name not in allowed for p in parts):raise ValueError('partial output integrity')
                for part in parts:part.unlink()
                a.output.rmdir()
            a.output.mkdir(parents=True);encrypted=client.encrypt(*values)
            if not isinstance(encrypted,tuple):encrypted=(encrypted,)
            args=[]
            for index,value in enumerate(encrypted):
                output=a.output/f'argument-{index}.cipher';output.write_bytes(value.serialize());args.append(BlobStore.digest(output))
            result=dict(status='encrypted',arguments_sha256=args,**meta)
            manifest_binding=dict(binding,purpose='encrypted-input',operation_id=a.output.name,input_sha256=sha(canonical(request['values'])))
            seal(a.output/'manifest.sealed',key,manifest_binding,canonical(result))
            print(json.dumps(result),flush=True)
        elif a.action=='open':
            cipher=Path(request['ciphertext_file'])
            if cipher.stat().st_size>64*1024**2:raise ValueError('ciphertext limit')
            if BlobStore.digest(cipher)!=request['ciphertext_sha256']:raise ValueError('ciphertext checksum')
            value=client.decrypt(fhe.Value.deserialize(cipher.read_bytes()))
            if a.output is None or a.output.exists():raise ValueError('new enterprise output file required')
            decoded=canonical(dict(value=np.asarray(value).tolist()))
            seal(a.output,key,dict(binding,purpose='opened-result',ciphertext_sha256=request['ciphertext_sha256']),decoded)
            print(json.dumps(dict(status='opened',**meta)),flush=True)
        else:print(json.dumps(dict(status='provisioned',**meta)),flush=True)
    finally:lock.close()


if __name__=='__main__':main()
