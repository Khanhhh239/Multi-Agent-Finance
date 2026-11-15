"""Committed snapshot -> binary feature plan -> real encryption -> signed receipt.

Only input preparation/upload is exercised. No labels are supplied and no train
job is created. Uses synthetic snapshots and existing synthetic DPAPI contexts,
never live Portal/model/snapshot storage. Raw public report is allowlisted.
"""
import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,NoEncryption

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests_he'),str(ROOT/'scripts')]
from training_snapshot_support import native,scope,commit,request
from sme_fraud.snapshots import SnapshotStore
from experiments.he_training.enterprise import Enterprise
from experiments.he_training.snapshot_adapter import ReadOnlySnapshots,prepare_snapshot_training
from experiments.he_training.protocol import canonical,strict_json,sha,atomic
from experiments.he_training import TARGET
from experiments.he4.windows_bridge import linux_path
from demo_encrypted_training import start_worker,stop_worker


def run(build,contexts,output):
    output.mkdir(parents=True,exist_ok=False);cloud=output/'cloud';cloud.mkdir();private=output/'enterprise';private.mkdir()
    code=cloud/'code/experiments/he_training';code.mkdir(parents=True);(code.parent/'__init__.py').write_text('',encoding='utf-8')
    for name in ('__init__.py','protocol.py','store.py','worker.py'):shutil.copy2(ROOT/'experiments/he_training'/name,code/name)
    public=cloud/'build';public.mkdir()
    for name in ('manifest.json','server.zip','client.specs.json'):shutil.copy2(build/name,public/name)
    signer=Ed25519PrivateKey.generate();keyfile=cloud/'worker-signing.key';keyfile.write_text(signer.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()).hex(),encoding='ascii')
    grants=[];nodes=[];plans=[];requests=[];source=SnapshotStore(private/'snapshots.sqlite3')
    for cid in ('C001','C002'):
        original=contexts/'enterprise'/cid;old=strict_json((original/'dataset.json').read_bytes());assert old['simulated'] is True
        authority=scope(cid,tenant='training-demo');data=native(cid,tenant='training-demo');sid=commit(source,data,authority,key=cid+'-snapshot')
        q=request(sid,data);plan=prepare_snapshot_training(ReadOnlySnapshots(source.path),authority,q)
        assert plan['status']=='ready' and plan['x']==[[1,1],[0,0],[1,0],[0,1]],plan['issues']
        root=private/cid;root.mkdir()
        for name in ('enterprise.json','wrapping.dpapi.json','node-signing.dpapi.json'):shutil.copy2(original/name,root/name)
        (root/'crypto').mkdir()
        for name in ('context.sealed','evaluation.keys'):(root/'crypto'/name).hardlink_to(original/'crypto'/name)
        node=Enterprise(root,build,authority)
        dataset=node.prepare_snapshot(ReadOnlySnapshots(source.path),q,expected_plan_sha256=plan['plan_sha256'])
        assert dataset['x']==plan['x'] and dataset['provenance']['snapshot']['snapshot_id']==sid
        again=node.prepare_snapshot(ReadOnlySnapshots(source.path),q,expected_plan_sha256=plan['plan_sha256']);assert again['dataset_id']==dataset['dataset_id']
        keys=cloud/(cid+'-evaluation.keys');keys.hardlink_to(root/'crypto/evaluation.keys')
        grants.append(dict(tenant_id=authority.tenant_id,company_id=cid,active=True,node_verify_key=node.public_key,key_epoch=node.meta['key_epoch'],target=TARGET,verification_mode='synthetic_expected',evaluation_keys_file=linux_path(keys),evaluation_keys_sha256=sha(keys.read_bytes())))
        nodes.append(node);plans.append(plan);requests.append(q)
        print(json.dumps(dict(company=cid,step='snapshot_encrypted',rows=4)),flush=True)
    config=cloud/'worker-config.json';atomic(config,canonical(dict(build=linux_path(public),state=linux_path(cloud/'state'),worker_signing_key=linux_path(keyfile),grants=grants)))
    process=None;ready=cloud/'not-ready'
    try:
        process,ready,url,pub=start_worker(cloud,config,0)
        assert pub==signer.public_key().public_bytes_raw().hex()
        checks=[]
        for node,plan in zip(nodes,plans):
            receipt=node.upload(url,pub);assert node.upload(url,pub)==receipt
            template=node.review_template();assert all(row['outcome'] is None for row in template['rows'])
            assert template['dataset_id']==node.dataset()['dataset_id']
            # Clear source/feature/provenance never enters the signed cloud payload.
            packet=strict_json((node.root/'upload.json').read_bytes())['payload'];assert not {'x','rows_source','provenance','row_ids','snapshot_id'}&set(packet)
            assert packet['x_cipher_sha256']==receipt['payload']['x_cipher_sha256']
            checks.append(dict(company_id=node.company,snapshot_id=plan['snapshot']['snapshot_id'],plan_sha256=plan['plan_sha256'],mapping_fingerprint=plan['mapping']['fingerprint'],features=plan['mapping']['columns'],rows=4,status='passed',snapshot_to_ciphertext=True,signed_receipt_verified=True,retry_kept_dataset=True,review_labels_null=True))
        with sqlite3.connect(cloud/'state/jobs.sqlite3') as c:
            assert c.execute('SELECT count(*) FROM datasets').fetchone()[0]==2
            assert c.execute('SELECT count(*) FROM jobs').fetchone()[0]==0
        assert plans[0]['row_ids']==plans[1]['row_ids'] and nodes[0].dataset()['dataset_id']!=nodes[1].dataset()['dataset_id']
        report=dict(status='passed',company_checks=checks,real_concrete_encryption=True,real_http_worker=True,source='committed synthetic agent2-rule-snapshot/1.0.0',plaintext_source_sent_to_worker=False,labels_supplied=False,train_jobs_created=0,new_key_generation=False,live_changed=False,limits=['Four explicitly selected rows and two existing binary features only.','This acceptance verifies input preparation and upload, not new encrypted training or fraud accuracy.'])
        atomic(output/'report.json',canonical(report));print(json.dumps(dict(status='passed',companies=2,training_jobs=0)),flush=True)
    finally:stop_worker(process,ready,config)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--demo-contexts',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.build.resolve(),a.demo_contexts.resolve(),a.output.resolve())
