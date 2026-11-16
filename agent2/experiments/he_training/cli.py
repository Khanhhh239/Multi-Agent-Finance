"""Explicit enterprise operator steps; token/key material never on argv/output."""
import argparse
from pathlib import Path
from sme_fraud.auth import FileAuthorizer
from .enterprise import Enterprise
from .protocol import strict_json,require,atomic,canonical


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','preview-snapshot','prepare-snapshot','upload','review-template','confirm','run','status','receive','approve','shadow','batch-preview','batch-prepare','batch-create-labels','batch-upload','batch-review-template','batch-confirm','batch-confirm-locked','batch-run','batch-status','batch-receive','batch-evaluate','batch-approve','batch-shadow'])
    p.add_argument('--config',type=Path,required=True);p.add_argument('--token-file',type=Path,required=True)
    p.add_argument('--data',type=Path);p.add_argument('--labels',type=Path);p.add_argument('--reason-file',type=Path)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    require(not a.output.exists(),'OUTPUT_EXISTS');cfg=strict_json(a.config.read_bytes())
    auth=FileAuthorizer(cfg['auth_file']);header='Bearer '+a.token_file.read_text('utf-8').strip()
    check=lambda:auth.authorize(header,cfg['company_id']);scope=check()
    if a.action.startswith('batch-'):
        from .batch_cli import execute
        result=execute(a,cfg,scope,check)
        require(check()==scope,'AUTH_CONTEXT_CHANGED');atomic(a.output,canonical(result));print('Enterprise batch step saved:',a.action);return
    if a.action in ('preview-snapshot','prepare-snapshot'):
        from .snapshot_adapter import ReadOnlySnapshots,prepare_snapshot_training
        if a.action=='prepare-snapshot':require('model.fit' in scope.permissions,'MODEL_FIT_DENIED')
        require(a.data is not None,'SNAPSHOT_REQUEST_REQUIRED');request=strict_json(a.data.read_bytes())
        store=ReadOnlySnapshots(cfg['snapshot_db']);plan=prepare_snapshot_training(store,scope,request,check)
        if a.action=='preview-snapshot':atomic(a.output,canonical(plan));print('Snapshot training preview saved:',plan['status']);return
        require(plan['status']=='ready','SNAPSHOT_TRAINING_NOT_READY')
        # Review expectation is explicit. Changed mapping/request/source cannot
        # silently use an older preview, even after expensive crypto provision.
        require(cfg.get('expected_plan_sha256')==plan['plan_sha256'],'TRAINING_PREVIEW_STALE')
    node=Enterprise(cfg['enterprise_root'],cfg['build'],scope,recheck=check,python=cfg.get('linux_python','/home/sang/.local/share/agent2/he4/bin/python'),distro=cfg.get('distro','Debian'))
    url,pub=cfg.get('worker_url'),cfg.get('worker_verify_key')
    if a.action=='prepare-snapshot':
        dataset=node.prepare_snapshot(store,request,expected_plan_sha256=cfg['expected_plan_sha256'])
        result=dict(status='encrypted_from_snapshot',dataset_id=dataset['dataset_id'],plan_sha256=plan['plan_sha256'],uploaded=False)
    elif a.action=='prepare':
        require(a.data is not None,'DATA_FILE_REQUIRED');data=strict_json(a.data.read_bytes())
        dataset=node.prepare(data['x'],data['row_ids'],simulated=data['simulated'])
        result=dict(status='encrypted_locally',dataset_id=dataset['dataset_id'],uploaded=False)
    elif a.action=='upload':result=node.upload(url,pub)
    elif a.action=='review-template':result=node.review_template()
    elif a.action=='confirm':
        require(a.labels is not None,'LABEL_FILE_REQUIRED');result=node.confirm(url,pub,strict_json(a.labels.read_bytes()))
    elif a.action in ('run','status'):result=node.access(url,pub,a.action)[0]
    elif a.action=='receive':
        candidate=node.receive(url,pub);result=dict(status='candidate_validated',job_id=candidate['job_id'],operational_activation=False)
    elif a.action=='approve':
        require(a.reason_file is not None,'REASON_FILE_REQUIRED');result=node.approve(a.reason_file.read_text('utf-8'))
    else:
        require(a.data is not None,'DATA_FILE_REQUIRED');data=strict_json(a.data.read_bytes());result=node.predict_shadow(data['x'],mapping_fingerprint=data.get('mapping_fingerprint'))
    require(check()==scope,'AUTH_CONTEXT_CHANGED');atomic(a.output,canonical(result));print('Enterprise training step saved:',a.action)


if __name__=='__main__':main()
