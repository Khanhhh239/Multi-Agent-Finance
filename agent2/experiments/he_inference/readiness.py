"""Enterprise-only proof of worker identity/grant. Never sends clear features."""
import argparse
import json
import secrets
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from .http_common import ServiceError, post, worker_address
from .key_manager import load_key, PROVIDER
from .protocol import HEUnavailable, public_hex, read_json, sign, verify


def probe(url, expected_key, signing_key, tenant, company):
    payload=dict(version='he-worker-readiness/1.0.0',tenant_id=tenant,company_id=company,
        node_verify_key=public_hex(signing_key),challenge=secrets.token_hex(32),expires_at=int(time.time())+30)
    try:
        response=post(url,'/v1/readiness',sign(payload,signing_key),timeout=2)
        verify(response,expected_key)
        if response.get('payload')!=dict(payload,worker_verify_key=expected_key):
            raise ValueError('binding')
    except (ServiceError,HEUnavailable,ValueError,KeyError,TypeError) as error:
        raise ServiceError(503,'WORKER_READINESS_UNAVAILABLE') from error
    return True


def configuration(node_file, bindings_file, worker_port):
    config=read_json(node_file)
    required={'version','key_protection','auth_file','model_db','snapshot_db','worker_url','worker_verify_key',
              'provisioning_key_file','state_dir','state_key_file'}
    if (not isinstance(config,dict) or set(config)!=required or config['version']!='he-enterprise-service/1.2.0'
            or config['key_protection']!=PROVIDER):raise ValueError('config')
    host,port=worker_address(config['worker_url'])
    if port!=worker_port:raise ValueError('port')
    wrapping=load_key(config['state_key_file'],purpose='state-wrapping',required_provider=PROVIDER)
    signing=load_key(config['provisioning_key_file'],purpose='node-signing',required_provider=PROVIDER)
    # Reuse the same strict server-side binding parser as the web. No DB/model
    # deserialization, fit, HE context generation, or state lock in this check.
    from sme_fraud.he_workbench import HEWorkbench
    from finance_input import AccessScope
    bindings=read_json(bindings_file)
    if not isinstance(bindings,dict) or not isinstance(bindings.get('bindings'),list) or not bindings['bindings']:
        raise ValueError('bindings')
    checker=object.__new__(HEWorkbench)
    from pathlib import Path
    checker.bindings_file=Path(bindings_file)
    scopes=[]
    for row in bindings['bindings']:
        scope=AccessScope(row['tenant_id'],frozenset({row['company_id']}),'readiness',frozenset({'data.import'}))
        if checker.selection(scope) is None:raise ValueError('binding')
        scopes.append(scope)
    return config,Ed25519PrivateKey.from_private_bytes(signing.material),scopes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node-config',required=True);parser.add_argument('--bindings',required=True)
    parser.add_argument('--worker-port',type=int,required=True);parser.add_argument('--keys-only',action='store_true')
    args=parser.parse_args()
    try:
        config,key,scopes=configuration(args.node_config,args.bindings,args.worker_port)
        if not args.keys_only:
            for scope in scopes:probe(config['worker_url'],config['worker_verify_key'],key,scope.tenant_id,next(iter(scope.company_ids)))
        print(json.dumps(dict(status='ready',scope_count=len(scopes))))
        return 0
    except (Exception,SystemExit):
        print(json.dumps(dict(status='unavailable',message='Không xác nhận được kết nối hoặc khóa phân tích.')))
        return 2


if __name__=='__main__':raise SystemExit(main())
