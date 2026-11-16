"""Real isolated Concrete batch SGD, locked labels, holdout and hard-crash resume.

Uses synthetic source records and synthetic expected labels only. Existing demo
contexts may be reused without rotation; never open production data or services.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests_he'),str(Path(__file__).resolve().parent)]
from finance_input import AccessScope
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,NoEncryption
from batch_training_support import native_batches
from training_snapshot_support import commit
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.label_packets import LabelStore,source_packet
from experiments.he_training import TARGET
from experiments.he_training.batch_protocol import VERSION
from experiments.he_training.batch_plan import prepare_batch_plan
from experiments.he_training.batch_enterprise import BatchEnterprise
from experiments.he_training.protocol import atomic,canonical,strict_json,sha
from experiments.he4.windows_bridge import linux_path
from demo_encrypted_training import start_worker,stop_worker


def hard_kill(process,ready,config):
    pid=int(strict_json(ready.read_bytes())['pid'])
    code="import os,signal,sys; p=int(sys.argv[1]); raw=open('/proc/'+str(p)+'/cmdline','rb').read(); assert sys.argv[2].encode() in raw; os.kill(p,signal.SIGKILL)"
    result=subprocess.run(['wsl.exe','-d','Debian','--exec','/usr/bin/python3','-c',code,str(pid),linux_path(config)],capture_output=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError('owned worker hard-crash injection failed')
    process.wait(timeout=20)


def run(build,output,reuse):
    if os.name!='nt':raise RuntimeError('native acceptance requires Windows DPAPI + Debian Concrete')
    output.mkdir(parents=True,exist_ok=False);cloud=output/'cloud';cloud.mkdir();enterprise=output/'enterprise'
    snapshots=SnapshotStore(output/'source-snapshots.sqlite3')
    code=cloud/'code/experiments/he_training';code.mkdir(parents=True);(code.parent/'__init__.py').write_text('')
    modules=('__init__.py','protocol.py','store.py','worker.py','batch_protocol.py','batch_store.py')
    for name in modules:shutil.copy2(ROOT/'experiments/he_training'/name,code/name)
    public=cloud/'build';public.mkdir()
    for name in ('manifest.json','server.zip','client.specs.json'):shutil.copy2(build/name,public/name)
    key=Ed25519PrivateKey.generate();keyfile=cloud/'worker-signing.key';keyfile.write_text(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()).hex(),encoding='ascii')
    config=cloud/'worker-config.json';grants=[];records=[];process=None;ready=cloud/'none';started=time.monotonic()
    try:
        for number,company in enumerate(('C001','C002')):
            old=reuse/'enterprise'/company
            require_demo=strict_json((old/'dataset.json').read_bytes())
            if require_demo['simulated'] is not True or not (old/'approval.json').is_file():raise RuntimeError('reuse only completed synthetic demo contexts')
            dest=enterprise/company;dest.mkdir(parents=True);(dest/'crypto').mkdir()
            for name in ('enterprise.json','wrapping.dpapi.json','node-signing.dpapi.json'):shutil.copy2(old/name,dest/name)
            for name in ('context.sealed','evaluation.keys'):(dest/'crypto'/name).hardlink_to(old/'crypto'/name)
            meta=strict_json((dest/'enterprise.json').read_bytes())
            scope=AccessScope(meta['tenant_id'],frozenset({company}),'synthetic-label-reviewer',frozenset({'data.import','evidence.verify','model.fit'}))
            node=BatchEnterprise(dest,build,scope)
            data,request=native_batches(company,scope.tenant_id);request['snapshot_id']=commit(snapshots,data,scope,key='native-batch-'+company)
            plan=prepare_batch_plan(snapshots,scope,request)
            assert plan['status']=='ready'
            node.prepare_snapshot_batches(snapshots,request,expected_plan_sha256=plan['plan_sha256'])
            assert node.prepare_snapshot_batches(snapshots,request,expected_plan_sha256=plan['plan_sha256'])['dataset_id']==node.saved('batch-source.json')['dataset_id']
            labels=LabelStore.from_state_key(dest/'labels.sqlite3',node.wrap_file);pins=[]
            for index,part in enumerate(plan['parts']['training']):
                packet=labels.create(scope,source_packet(snapshots,scope,part['request']))
                for case in packet['cases']:
                    fraud=index==0 if company=='C001' else index!=0
                    packet=labels.change(scope,packet['packet_id'],'save',dict(expected_revision=packet['revision'],request_id=__import__('secrets').token_hex(16),
                        label=dict(record_id=case['record_id'],revision=case['revision'],outcome='verified_fraud' if fraud else 'verified_non_fraud',
                        explanation='Synthetic expected label for isolated technical acceptance only.',evidence_ids=[case['evidence'][0]['evidence_id']],documents_checked=True)))
                packet=labels.change(scope,packet['packet_id'],'lock',dict(expected_revision=packet['revision'],request_id=__import__('secrets').token_hex(16)))
                pins.append({k:packet[k] for k in ('packet_id','revision','lock_sha256')})
            # Fitting operator reads attestations, without performing new verification.
            fit_scope=replace(scope,actor_id='synthetic-fit-operator',permissions=frozenset({'data.import','model.fit'}))
            node=BatchEnterprise(dest,build,fit_scope)
            keys=cloud/(company+'-evaluation.keys');keys.hardlink_to(dest/'crypto/evaluation.keys')
            grants.append(dict(tenant_id=scope.tenant_id,company_id=company,active=True,batch_training=True,node_verify_key=node.public_key,
                key_epoch=node.meta['key_epoch'],target=TARGET,verification_mode='synthetic_expected',evaluation_keys_file=linux_path(keys),evaluation_keys_sha256=sha(keys.read_bytes())))
            atomic(config,canonical(dict(build=linux_path(public),state=linux_path(cloud/'state'),worker_signing_key=linux_path(keyfile),grants=grants,batch_training=True)))
            process,ready,url,pub=start_worker(cloud,config,number*3)
            node.upload_batches(url,pub);node.upload_batches(url,pub)
            job=node.confirm_locked_batches(url,pub,labels,pins,epochs=2)
            assert node.confirm_locked_batches(url,pub,labels,pins,epochs=2)['job_id']==job['job_id']
            before=time.monotonic();recovery=None
            print(json.dumps(dict(company=company,phase='confirmed',training_rows=8,evaluation_rows=4,total_updates=4)),flush=True)
            if number==0:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future=pool.submit(node.access_batches,url,pub,'run');deadline=time.monotonic()+300;pending=None
                    while time.monotonic()<deadline:
                        pending,_=node.access_batches(url,pub,'status')
                        if pending['completed_updates']==1 and pending['inflight_update']==1:break
                        if future.done():raise RuntimeError('native run ended before crash checkpoint was observed')
                        time.sleep(.5)
                    else:raise RuntimeError('native checkpoint observation timeout')
                    hard_kill(process,ready,config);process=None
                    try:future.result(timeout=20)
                    except (OSError,ValueError):pass
                node=BatchEnterprise(dest,build,fit_scope)
                process,ready,url,pub=start_worker(cloud,config,number*3+1)
                restored,_=node.access_batches(url,pub,'status')
                assert restored['job_id']==job['job_id'] and restored['completed_updates']==1
                print(json.dumps(dict(company=company,phase='hard_crash_restored',completed_updates=1,same_request=True)),flush=True)
                recovery=dict(injection='SIGKILL owned worker while update 2 pending',committed_updates_before_crash=1,
                    committed_updates_after_restart=restored['completed_updates'],same_job=True,same_key_epoch=True,same_build=True)
            done,_=node.access_batches(url,pub,'run');seconds=time.monotonic()-before
            assert done['status']=='completed' and done['completed_updates']==4
            candidate=node.receive_batches(url,pub);holdout=node.evaluate_holdout()
            assert holdout['evaluation_rows']==4 and holdout['held_out_from_training']
            expected=[1,1,-1] if company=='C001' else [-1,-1,1]
            assert candidate['weights_code']==expected
            node.access_batches(url,pub,'run');again,_=node.access_batches(url,pub,'result')
            assert again['model_cipher_sha256']==candidate['model_cipher_sha256']
            stop_worker(process,ready,config);process=None
            node=BatchEnterprise(dest,build,fit_scope)
            process,ready,url,pub=start_worker(cloud,config,number*3+2)
            final=node.receive_batches(url,pub)
            assert final['model_cipher_sha256']==candidate['model_cipher_sha256'] and final['weights_code']==candidate['weights_code']
            stop_worker(process,ready,config);process=None
            records.append(dict(company_id=company,status='passed',training_rows=8,evaluation_rows=4,batch_size=4,training_batches=2,epochs=2,completed_updates=4,
                weights_code=candidate['weights_code'],oracle_exact=True,locked_labels_used=True,labels_read_without_new_verification=True,
                holdout_excluded_from_fit=True,encrypted_weights_carried_across_batches=True,http_training_seconds=seconds,
                encrypted_model_stable_after_restart=True,hard_crash_recovery=recovery))
            atomic(output/'progress.json',canonical(dict(companies=records)))
            print(json.dumps(dict(company=company,phase='passed',http_seconds=round(seconds,3))),flush=True)
        forbidden={'context.sealed','wrapping.dpapi.json','node-signing.dpapi.json','batch-source.json','batch-verified-reviews.json','batch-candidate.json','enterprise.py','batch_enterprise.py','helper.py','labels.sqlite3','source-snapshots.sqlite3'}
        assert not [p.name for p in cloud.rglob('*') if p.name in forbidden]
        report=dict(version=VERSION,status='passed',real_concrete_fhe=True,companies=records,seconds=time.monotonic()-started,
            cloud_inputs_only_ciphertext_and_public_metadata=True,worker_has_enterprise_keys=False,cloud_has_holdout_rows=False,
            synthetic_only=True,real_verified_fraud_labels=0,live_services_changed=False,production_activated=False,
            limits=['Fixed 4 rows / 2 binary predictors per batch, 4 total updates in current build.','Holdout scores are uncalibrated; no business accuracy claimed.','SIGKILL may recompute an uncommitted update; committed weights/cursor are atomic.','Same-account worker process separation is not an OS sandbox or proof against malicious computation.'])
        atomic(output/'report.json',canonical(report));print(json.dumps(dict(status='passed',companies=2)),flush=True)
    finally:stop_worker(process,ready,config)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--build',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--reuse-demo-contexts',type=Path,required=True)
    a=parser.parse_args();run(a.build.resolve(),a.output.resolve(),a.reuse_demo_contexts.resolve())
