"""Isolated Windows-enterprise / Linux-cloud encrypted supervised training demo.

All labels are synthetic expected outcomes, never real verified fraud labels.
No Portal/live DB/model/key changes. Public report excludes raw source, keys,
ciphertexts and signatures. Worker is a separate process and allowlisted bundle,
not an OS sandbox against a malicious process running under the same account.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from finance_input import AccessScope
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,NoEncryption
from experiments.he_training import VERSION,TARGET
from experiments.he_training.enterprise import Enterprise
from experiments.he_training.protocol import canonical,strict_json,sha,atomic,sign,verify
from experiments.he4.windows_bridge import linux_path


def stop_worker(process,ready,config):
    if process is None:return
    if process.poll() is None and ready.exists():
        pid=int(strict_json(ready.read_bytes())['pid'])
        code="import os,signal,sys; p=int(sys.argv[1]); raw=open('/proc/'+str(p)+'/cmdline','rb').read(); assert sys.argv[2].encode() in raw; os.kill(p,signal.SIGTERM)"
        subprocess.run(['wsl.exe','-d','Debian','--exec','/usr/bin/python3','-c',code,str(pid),linux_path(config)],capture_output=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:process.wait(timeout=20)
    except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=10)


def start_worker(cloud,config,index):
    ready=cloud/f'ready-{index}.json';log=(cloud/f'worker-{index}.log').open('ab')
    command=['wsl.exe','-d','Debian','--cd',linux_path(cloud/'code'),'--exec','/home/sang/.local/share/agent2/he4/bin/python','-m','experiments.he_training.worker','--config',linux_path(config),'--ready',linux_path(ready)]
    process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));log.close()
    deadline=time.monotonic()+60
    while not ready.exists():
        if process.poll() is not None:raise RuntimeError('training worker startup failed; inspect private runtime log')
        if time.monotonic()>deadline:stop_worker(process,ready,config);raise RuntimeError('training worker timeout')
        time.sleep(.1)
    meta=strict_json(ready.read_bytes());return process,ready,'http://127.0.0.1:'+str(meta['port']),meta['worker_verify_key']


def run(build,output,companies,reuse=None):
    if os.name!='nt':raise RuntimeError('demo requires enterprise Windows DPAPI and Debian Concrete runtime')
    output.mkdir(parents=True,exist_ok=False);enterprise=output/'enterprise';cloud=output/'cloud';cloud.mkdir()
    code=cloud/'code/experiments/he_training';code.mkdir(parents=True);(code.parent/'__init__.py').write_text('',encoding='utf-8')
    for name in ('__init__.py','protocol.py','store.py','worker.py'):shutil.copy2(ROOT/'experiments/he_training'/name,code/name)
    public=cloud/'build';public.mkdir()
    for name in ('manifest.json','server.zip','client.specs.json'):shutil.copy2(build/name,public/name)
    worker_key=Ed25519PrivateKey.generate();keyfile=cloud/'worker-signing.key'
    keyfile.write_text(worker_key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()).hex(),encoding='ascii')
    grants=[];records=[];process=None;ready=cloud/'not-ready';config=cloud/'worker-config.json'
    started=time.monotonic()
    try:
        for index,cid in enumerate(companies):
            scope=AccessScope('training-demo',frozenset({cid}),'synthetic-reviewer-'+cid,frozenset({'data.import','model.fit','evidence.verify'}))
            if reuse:
                source=reuse/'enterprise'/cid
                previous=strict_json((source/'dataset.json').read_bytes())
                assert previous['simulated'] is True and (source/'approval.json').is_file()
                dest=enterprise/cid;dest.mkdir(parents=True)
                for name in ('enterprise.json','wrapping.dpapi.json','node-signing.dpapi.json'):shutil.copy2(source/name,dest/name)
                (dest/'crypto').mkdir()
                # Immutable sealed context/public keys: reuse without key rotation,
                # never link enterprise private context into the cloud tree.
                for name in ('context.sealed','evaluation.keys'):(dest/'crypto'/name).hardlink_to(source/'crypto'/name)
            before=time.monotonic();node=Enterprise(enterprise/cid,build,scope)
            context_seconds=time.monotonic()-before
            x=[[-1,-1],[-1,1],[1,-1],[1,1]]
            # Opposite synthetic targets demonstrate independent company models.
            labels=[0,0,1,1] if cid=='C001' else [1,1,0,0]
            dataset=node.prepare(x,[cid+'-SIM-'+str(i) for i in range(4)],simulated=True)
            keys=cloud/(cid+'-evaluation.keys');shutil.copy2(node.root/'crypto/evaluation.keys',keys)
            grants.append(dict(tenant_id=scope.tenant_id,company_id=cid,active=True,node_verify_key=node.public_key,key_epoch=node.meta['key_epoch'],target=TARGET,verification_mode='synthetic_expected',evaluation_keys_file=linux_path(keys),evaluation_keys_sha256=sha(keys.read_bytes())))
            atomic(config,canonical(dict(build=linux_path(public),state=linux_path(cloud/'state'),worker_signing_key=linux_path(keyfile),grants=grants)))
            process,ready,url,pub=start_worker(cloud,config,index*2)
            node.upload(url,pub);node.upload(url,pub)
            review=node.review_template()
            for i,row in enumerate(review['rows']):row.update(outcome='verified_fraud' if labels[i] else 'verified_non_fraud',verified_at=datetime.now(timezone.utc).isoformat(),evidence_refs=['SYNTHETIC_EXPECTED_CASE_'+str(i)])
            before=time.monotonic();job=node.confirm(url,pub,review,steps=2);repeat=node.confirm(url,pub,review,steps=2)
            assert repeat['job_id']==job['job_id'] and repeat['completed_steps']==0
            approved_seconds=time.monotonic()-before
            before=time.monotonic();done,_=node.access(url,pub,'run');training_seconds=time.monotonic()-before
            assert done['completed_steps']==2 and done['status']=='completed'
            candidate=node.receive(url,pub)
            # Completed run retries are cached, never a fresh fit.
            node.access(url,pub,'run');again,_=node.access(url,pub,'result')
            assert again['model_cipher_sha256']==candidate['model_cipher_sha256']
            approval=node.approve('Synthetic technical parity passed; approve shadow evaluation only.')
            assert verify(approval,node.public_key)['status']=='approved_for_shadow_evaluation'
            shadow=node.predict_shadow([[-1,0],[1,0]])
            assert shadow['shadow_only'] and len(shadow['scores'])==2
            assert candidate['weights_code']!=[0,0,0]
            stop_worker(process,ready,config);process=None
            # Fresh worker process + freshly loaded enterprise/DPAPI keys.
            reopened=Enterprise(enterprise/cid,build,scope)
            process,ready,url,pub=start_worker(cloud,config,index*2+1)
            received=reopened.receive(url,pub)
            assert received['model_cipher_sha256']==candidate['model_cipher_sha256'] and received['weights_code']==candidate['weights_code']
            stop_worker(process,ready,config);process=None
            records.append(dict(company_id=cid,job_id=job['job_id'],status='passed',training_rows=4,features=2,steps=2,weights_code=candidate['weights_code'],quantized_oracle_exact_match=True,model_changed_from_initialization=True,key_context_seconds=context_seconds,consent_encrypt_seconds=approved_seconds,training_http_seconds=training_seconds,evaluation_key_bytes=keys.stat().st_size,enterprise_restart_real_keys=True,worker_restart_cached_model=True,approval='shadow_evaluation_only',real_business_labels=0))
            atomic(output/'progress.json',canonical(dict(completed_companies=len(records),records=records)))
            print(json.dumps(dict(company=cid,status='passed',http_seconds=round(training_seconds,3))),flush=True)
        if len(records)==2:assert records[0]['weights_code']!=records[1]['weights_code']
        # The worker tree cannot contain enterprise secret context, local data or labels.
        forbidden={'context.sealed','wrapping.dpapi.json','node-signing.dpapi.json','dataset.json','verified-labels.json','candidate.json','enterprise.py','helper.py'}
        assert not [p for p in cloud.rglob('*') if p.name in forbidden]
        report=dict(version=VERSION,status='passed',model='bounded quantized logistic SGD; not Concrete ML SGDClassifier',target=TARGET,companies=records,real_concrete_fhe=True,training_inputs_labels_weights_encrypted=True,worker_has_enterprise_secret_keys=False,worker_bundle_allowlist_verified=True,simulation_cases_in_build=144,verified_human_labels=0,training_labels='synthetic_expected',portal_integrated=False,cloud_public_deployed=False,production_activated=False,seconds=time.monotonic()-started,limitations=['Two features / four training rows / two update steps; not a full trained production model.','Exact parity is with the quantized SGD equations, not convergence or fraud detection accuracy.','Worker process and bundle isolation is not an OS sandbox against a malicious same-account process.','Worker signatures bind receipts, not cryptographic proof of correct training.','Native restart check is after completion; mid-compute hard-crash is not claimed.'])
        atomic(output/'report.json',canonical(report));print(json.dumps(dict(status='passed',companies=len(records))),flush=True)
    finally:stop_worker(process,ready,config)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--company',choices=['C001','C002'],action='append');p.add_argument('--reuse-demo-contexts',type=Path);a=p.parse_args();run(a.build.resolve(),a.output.resolve(),a.company or ['C001','C002'],a.reuse_demo_contexts.resolve() if a.reuse_demo_contexts else None)
