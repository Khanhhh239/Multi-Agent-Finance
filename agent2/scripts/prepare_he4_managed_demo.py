"""Explicit local-operator setup for the two existing simulated companies.

Adds immutable RobustZ artifacts and new protected contexts. Does not activate
Portal settings, edit roles, rotate old keys, or overwrite existing state.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time
from types import SimpleNamespace
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT.parent)]
from finance_input import AccessScope
from experiments.he4.bundle import build
from experiments.he4.windows_bridge import CryptoBridge,linux_path
from experiments.he_inference.protocol import canonical,public_hex,sha
from experiments.he_inference.key_manager import load_key,PROVIDER
from experiments.he_inference.registry_export import ReadOnlySnapshots,_load_model
from sme_fraud.method_store import MethodStore
from sme_fraud.method_jobs import run_fit_job


def run(node_path,pins_path,root,builds,port):
    if root.exists():raise ValueError('new deployment directory required')
    root.mkdir(parents=True);started=time.monotonic();node=json.loads(node_path.read_bytes());pins=json.loads(pins_path.read_bytes())
    if {r['company_id'] for r in pins['bindings']}!={'C001','C002'} or any(r['tenant_id']!='demo' for r in pins['bindings']):raise ValueError('only explicitly prepared C001/C002 simulated demo')
    backups=root/'backup-before-setup';backups.mkdir()
    # Online consistent DB backups before appending any new immutable artifact.
    for name in ('model_db','snapshot_db'):
        source=sqlite3.connect(Path(node[name]).resolve().as_uri()+'?mode=ro',uri=True);target=sqlite3.connect(backups/(name+'.sqlite3'))
        try:source.backup(target)
        finally:source.close();target.close()
    for label,path in [('node.json',node_path),('he-ui-bindings.json',pins_path),('state-wrapping.dpapi.json',Path(node['state_key_file'])),('node-signing.dpapi.json',Path(node['provisioning_key_file']))]:(backups/label).write_bytes(path.read_bytes())
    snapshots=ReadOnlySnapshots(node['snapshot_db']);models=MethodStore(node['model_db']);rows=[]
    bridge=CryptoBridge(root/'enterprise/private',node['state_key_file'])
    for row in pins['bindings']:
        company=row['company_id'];scope=AccessScope('demo',frozenset({company}),'he4-local-setup-operator',frozenset({'data.import','model.fit'}))
        _,manifest,_=_load_model(node['model_db'],scope,row['artifact_id'],lambda:scope,metadata_only=True)
        cfg=dict(manifest['fit_context']['config'],version='company-fit-config/1.0.0',method_id='robust_z',profile_id='technical-shadow-he4')
        raw=json.loads(snapshots.get_snapshot(scope,cfg['snapshot_id'],data=True))
        if not all(r['source']['is_simulated'] for value in raw.values() if isinstance(value,list) for r in value):raise ValueError('real source requires its own approved preparation')
        # An explicit operator service context for this setup only. Portal roles
        # are neither read as fit permission nor modified here.
        auth=SimpleNamespace(authorize=lambda header,c,expected=company,s=scope:s if c==expected else (_ for _ in ()).throw(ValueError('scope')))
        fit=run_fit_job(snapshots,models,auth,None,company,cfg,'he4-managed-prepare-'+company)
        if fit.get('error') or fit['job']['status']!='succeeded':raise ValueError('statistics preparation incomplete')
        rows.append(dict(tenant_id='demo',company_id=company,ml_artifact_id=row['artifact_id'],statistics_artifact_id=fit['job']['artifact_id']))
        for profile,bundle in builds.items():
            bridge.provision(scope,bundle);print(json.dumps(dict(stage='protected-context-ready',company=company,profile=profile)),flush=True)
    enterprise=root/'enterprise';(enterprise/'bindings.json').write_bytes(canonical(dict(version='he4-company-bindings/1.1.0',bindings=rows)))
    cloud=root/'worker';cloud.mkdir();build(cloud/'bundle');key=Ed25519PrivateKey.generate();(cloud/'signing.hex').write_text(key.private_bytes_raw().hex())
    signer=Ed25519PrivateKey.from_private_bytes(load_key(node['provisioning_key_file'],purpose='node-signing',required_provider=PROVIDER).material)
    (cloud/'grants.json').write_bytes(canonical(dict(version='he-worker-grants/1.0.0',grants=[dict(tenant_id='demo',company_id=c,node_verify_key=public_hex(signer),active=True) for c in ('C001','C002')])))
    (cloud/'worker.json').write_bytes(canonical(dict(version='he4-worker/0.1.0',state_dir=linux_path(cloud/'state'),grants_file=linux_path(cloud/'grants.json'),signing_key_file=linux_path(cloud/'signing.hex'),builds={k:linux_path(v) for k,v in builds.items()})))
    config=dict(version='he4-enterprise/1.0.0',state_dir=str(enterprise/'jobs'),enterprise_root=str(enterprise/'private'),state_key_file=node['state_key_file'],worker_url=f'http://127.0.0.1:{port}',worker_verify_key=public_hex(key),builds={k:str(v) for k,v in builds.items()},bindings_file=str(enterprise/'bindings.json'),linux_distro='Debian',linux_python='/home/sang/.local/share/agent2/he4/bin/python')
    (enterprise/'node.json').write_bytes(canonical(config))
    report=dict(status='prepared_not_activated',companies=['C001','C002'],new_protected_contexts=6,existing_ml_models_preserved=True,portal_roles_unchanged=True,backups=True,seconds=time.monotonic()-started)
    (root/'preparation.json').write_bytes(canonical(report));print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--node',type=Path,required=True);p.add_argument('--bindings',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--build-root',type=Path,required=True);p.add_argument('--port',type=int,default=8869);a=p.parse_args()
    run(a.node.resolve(),a.bindings.resolve(),a.output.resolve(),{k:(a.build_root/v).resolve() for k,v in dict(statistics='build-statistics-v1',rules='build-rules-difference-v1',graph='build-graph-difference-v1').items()},a.port)
