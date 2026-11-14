"""Create isolated synthetic signing grants; no existing company keys touched."""
import argparse
import json
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from experiments.he_inference.protocol import public_hex
from .bundle import build
from . import VERSION


def prepare(output,builds):
    output=output.resolve()
    if output.exists():raise ValueError('new test folder required')
    output.mkdir(parents=True);build(output/'bundle')
    node=Ed25519PrivateKey.generate();worker=Ed25519PrivateKey.generate()
    (output/'node-signing.hex').write_text(node.private_bytes_raw().hex())
    (output/'worker-signing.hex').write_text(worker.private_bytes_raw().hex())
    (output/'grants.json').write_text(json.dumps(dict(version='he-worker-grants/1.0.0',grants=[dict(tenant_id='he4-test',company_id='C001',node_verify_key=public_hex(node),active=True)])))
    config=dict(version=VERSION,state_dir=str(output/'cloud'),grants_file=str(output/'grants.json'),signing_key_file=str(output/'worker-signing.hex'),builds=builds)
    (output/'worker.json').write_text(json.dumps(config,indent=2))
    (output/'public.json').write_text(json.dumps(dict(worker_verify_key=public_hex(worker))))
    print(json.dumps(dict(prepared=True,worker_verify_key=public_hex(worker))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--statistics',required=True);p.add_argument('--graph',required=True);p.add_argument('--rules',required=True);a=p.parse_args();prepare(a.output,{k:getattr(a,k) for k in ('statistics','graph','rules')})
