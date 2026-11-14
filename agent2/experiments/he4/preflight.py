"""DN interpreter performs key/protocol checks for the stdlib-only Portal."""
import argparse
import json
from pathlib import Path
import secrets
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from finance_input import AccessScope
from .coordinator import Settings
from .windows_bridge import CryptoBridge
from .vault import open_private
from .client_transport import envelope
from .blob_store import BlobStore
from experiments.he_inference.key_manager import load_key,PROVIDER
from experiments.he_inference.protocol import verify,read_json
from experiments.he_inference.http_common import post


def check(node_config,config,keys_only=False):
    node=read_json(node_config);settings=Settings(read_json(config));c=settings.config
    if Path(node['state_key_file']).resolve()!=Path(c['state_key_file']).resolve():raise ValueError('wrapping key mismatch')
    signing=load_key(node['provisioning_key_file'],purpose='node-signing',required_provider=PROVIDER)
    signer=Ed25519PrivateKey.from_private_bytes(signing.material)
    bindings=read_json(c['bindings_file'])['bindings'];bridge=CryptoBridge(c['enterprise_root'],c['state_key_file'],distro=c['linux_distro'],python=c['linux_python'])
    if not bindings:raise ValueError('company bindings required')
    for row in bindings:
        scope=AccessScope(row['tenant_id'],frozenset({row['company_id']}),'operator-preflight',frozenset({'data.import'}))
        captured=settings.capture(scope)
        for program in captured['programs'].values():
            _,vault,binding,key=bridge.context(scope,program['path']);meta=read_json(vault/'context.json')
            if meta['binding']!=binding or meta['evaluation_keys_sha256']!=BlobStore.digest(vault/'evaluation.keys'):raise ValueError('public context mismatch')
            private=open_private(vault/'context.sealed',key,binding);del private
        if not keys_only:
            request=envelope(scope,signer,dict(challenge=secrets.token_hex(32)))
            actual=verify(post(c['worker_url'],'/v1/readiness',request),c['worker_verify_key'])
            expected=dict(request['payload'],worker_verify_key=c['worker_verify_key'],builds={k:v['circuit_sha256'] for k,v in captured['programs'].items()})
            if actual!=expected:raise ValueError('worker profile/key mismatch')
    return dict(status='ready',companies=len(bindings),keys_protected=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node-config',required=True);p.add_argument('--config',required=True);p.add_argument('--keys-only',action='store_true');a=p.parse_args()
    try:print(json.dumps(check(a.node_config,a.config,a.keys_only)))
    except Exception:print(json.dumps(dict(status='unavailable')));raise SystemExit(2)
