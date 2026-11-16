"""Fake ciphertext tests lifecycle only; native Concrete acceptance is separate."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timezone
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from finance_input import AccessScope
from experiments.he_training import TARGET,PROFILE
from experiments.he_training import batch_protocol as p
from experiments.he_training.batch_store import BatchCloudStore
from experiments.he_training.batch_enterprise import BatchEnterprise
from experiments.he_training.batch_plan import prepare_batch_plan
from experiments.he_training.circuit import oracle
from experiments.he_training.protocol import TrainingError,sign,verify,encode,decode,sha,canonical,strict_json
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.label_packets import LabelStore,source_packet
from training_snapshot_support import commit
from batch_training_support import native_batches


class FakeEnterprise(BatchEnterprise):
    def __init__(self,root,scope,key,store):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.scope=scope;self.company=next(iter(scope.company_ids));self.recheck=None
        self.meta=dict(tenant_id=scope.tenant_id,company_id=self.company,key_epoch='batch-key-'+self.company,build_sha256='b'*64)
        self.key=key;self.store=store;self.helpers=[]
    def signing_key(self):return self.key
    def commitment(self,purpose,value):return hmac.new(b'synthetic-hmac-test-only',purpose.encode()+canonical(value),hashlib.sha256).hexdigest()
    def helper(self,action,value):
        self.guard();self.helpers.append(action)
        if action=='encrypt-data':return dict(x_cipher=encode(canonical(value['x'])),x_cipher_sha256=sha(canonical(value['x'])))
        if action=='encrypt-batch-labels':
            result=dict(y_cipher=encode(canonical(value['y'])),y_cipher_sha256=sha(canonical(value['y'])))
            if value['initialize_weights']:result.update(weights_cipher=encode(canonical([0,0,0])),weights_cipher_sha256=sha(canonical([0,0,0])))
            return result
        w=strict_json(decode(value['model_cipher']))
        return dict(weights_code=w,coefficients=[v/2 for v in w[:2]],intercept=w[2]/2)
    def post(self,url,path,packet,worker_key):
        self.guard();signed={'/v2/datasets':self.store.upload,'/v2/confirm':self.store.confirm,'/v2/jobs':self.store.access}[path](packet)
        return verify(signed,worker_key),signed


class BatchTrainingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.scope=AccessScope('batch-demo',frozenset({'C001'}),'verified-reviewer',frozenset({'data.import','evidence.verify','model.fit'}))
        self.key=Ed25519PrivateKey.generate();self.worker_key=Ed25519PrivateKey.generate();self.pub=self.worker_key.public_key().public_bytes_raw().hex()
        self.grants={('batch-demo','C001'):dict(active=True,batch_training=True,node_verify_key=self.key.public_key().public_bytes_raw().hex(),key_epoch='batch-key-C001',target=TARGET,verification_mode='synthetic_expected')}
        self.calls=[];self.fail_on=None
        self.store=BatchCloudStore(self.root/'cloud',self.grants,self.worker_key,'b'*64,self.evaluate)
        self.addCleanup(lambda:self.store.close())
        self.node=FakeEnterprise(self.root/'enterprise',self.scope,self.key,self.store)
        self.train=[dict(x=[[1,1]]*4,row_ids=['T'+str(i) for i in range(4)]),dict(x=[[0,0]]*4,row_ids=['T'+str(i) for i in range(4,8)])]
        self.evaluation=[dict(x=[[0,0],[0,1],[1,0],[1,1]],row_ids=['E'+str(i) for i in range(4)])]

    def evaluate(self,x,y,w,body):
        self.calls.append((x,y,w))
        if self.fail_on==len(self.calls):raise RuntimeError('synthetic crash before checkpoint')
        return canonical(oracle(strict_json(x),strict_json(y),strict_json(w)))

    def prepared(self):
        self.node.prepare_batches(self.train,self.evaluation,simulated=True)
        self.node.upload_batches('fake',self.pub)

    def reviewed(self):
        reviews=self.node.batch_review_templates()
        for i,r in enumerate(reviews):
            for row in r['rows']:row.update(outcome='verified_fraud' if i==0 else 'verified_non_fraud',verified_at=datetime.now(timezone.utc).isoformat(),evidence_refs=['SYNTHETIC_ONLY'])
        return reviews

    def confirmed(self,epochs=2):
        self.prepared();return self.node.confirm_batch_reviews('fake',self.pub,self.reviewed(),epochs=epochs)

    def test_multi_batch_epoch_order_encrypted_carry_and_holdout_exclusion(self):
        self.confirmed();done,_=self.node.access_batches('fake',self.pub,'run');self.assertEqual(done['completed_updates'],4)
        self.assertEqual([strict_json(v[0]) for v in self.calls],[self.train[i]['x'] for i in (0,1,0,1)])
        for before,after in zip(self.calls,self.calls[1:]):self.assertEqual(after[2],canonical(oracle(strict_json(before[0]),strict_json(before[1]),strict_json(before[2]))))
        self.assertEqual(len(self.calls),4)
        candidate=self.node.receive_batches('fake',self.pub)
        self.assertEqual(candidate['weights_code'],[1,1,-1])
        self.assertEqual(candidate['training_rows'],8);self.assertEqual(candidate['evaluation_rows'],4)
        scores=self.node.evaluate_holdout();self.assertTrue(scores['held_out_from_training']);self.assertIsNone(scores['accuracy'])
        self.assertEqual({r['record_id'] for r in scores['rows']},set(self.evaluation[0]['row_ids']))
        self.node.access_batches('fake',self.pub,'run');self.assertEqual(len(self.calls),4)

    def test_upload_and_label_confirmation_do_not_compute(self):
        self.prepared();self.assertEqual(self.calls,[])
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],0)
        review=self.reviewed();a=self.node.confirm_batch_reviews('fake',self.pub,review);b=self.node.confirm_batch_reviews('fake',self.pub,review)
        self.assertEqual(a,b);self.assertEqual(self.calls,[])
        self.assertNotIn('open-model',self.node.helpers)

    def test_pending_update_resume_after_reopen_keeps_committed_weights(self):
        job=self.confirmed();self.fail_on=2
        with self.assertRaisesRegex(RuntimeError,'synthetic crash'):self.node.access_batches('fake',self.pub,'run')
        status,_=self.node.access_batches('fake',self.pub,'status');self.assertEqual(status['completed_updates'],1);self.assertEqual(status['inflight_update'],1)
        committed=self.calls[1][2]
        self.store.close();self.store=BatchCloudStore(self.root/'cloud',self.grants,self.worker_key,'b'*64,self.evaluate);self.node.store=self.store;self.fail_on=None
        self.node.access_batches('fake',self.pub,'run')
        self.assertEqual(self.calls[2][2],committed)
        self.assertEqual(self.node.receive_batches('fake',self.pub)['weights_code'],[1,1,-1])
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM checkpoints WHERE job=?',(job['job_id'],)).fetchone()[0],5)

    def test_parallel_run_status_poll_and_exclusive_state_lease(self):
        self.confirmed();entered=threading.Event();release=threading.Event();original=self.store.evaluate
        def slow(*args):entered.set();release.wait(10);return original(*args)
        self.store.evaluate=slow;errors=[]
        def run():
            try:self.node.access_batches('fake',self.pub,'run')
            except Exception as e:errors.append(str(e))
        thread=threading.Thread(target=run);thread.start();self.assertTrue(entered.wait(5))
        status,_=self.node.access_batches('fake',self.pub,'status');self.assertEqual(status['completed_updates'],0)
        self.node.access_batches('fake',self.pub,'run')
        with self.assertRaises(ValueError):BatchCloudStore(self.root/'cloud',self.grants,self.worker_key,'b'*64,self.evaluate)
        release.set();thread.join(15);self.assertEqual(errors,[]);self.assertEqual(len(self.calls),4)

    def test_source_and_evaluation_mutations_or_overlaps_rejected(self):
        for change in ('overlap','partial','outside'):
            train=deepcopy(self.train);evaluation=deepcopy(self.evaluation)
            if change=='overlap':evaluation[0]['row_ids'][0]=train[0]['row_ids'][0]
            if change=='partial':train[0]['row_ids'].pop()
            if change=='outside':train[0]['x'][0][0]=2
            with self.subTest(change=change),self.assertRaises(TrainingError):self.node.prepare_batches(train,evaluation,simulated=True)
        self.prepared();changed=deepcopy(self.evaluation);changed[0]['x'][0][0]=1
        with self.assertRaisesRegex(TrainingError,'BATCH_DATASET_IMMUTABLE'):self.node.prepare_batches(self.train,changed,simulated=True)

    def test_plaintext_fields_swapped_order_and_cipher_hash_denied(self):
        self.prepared();body=verify(strict_json((self.node.root/'batch-upload.json').read_bytes()),self.key.public_key().public_bytes_raw().hex())
        for kind in ('raw','order','hash','evaluation'):
            changed=deepcopy(body)
            if kind=='raw':changed['X']=[[1,1]]
            if kind=='order':changed['batches'].reverse()
            if kind=='hash':changed['batches'][0]['x_cipher_sha256']='a'*64
            if kind=='evaluation':changed['evaluation_batches']=self.evaluation
            with self.subTest(kind=kind),self.assertRaises(TrainingError):self.store.upload(sign(changed,self.key))

    def test_single_class_per_batch_allowed_but_global_one_class_null_denied(self):
        self.prepared();review=self.reviewed();self.assertTrue(self.node.confirm_batch_reviews('fake',self.pub,review))
        for value in ('verified_fraud',None):
            bad=deepcopy(review)
            for r in bad[1]['rows']:r['outcome']=value
            with self.assertRaises(TrainingError):self.node.confirm_batch_reviews('fake',self.pub,bad)

    def test_build_update_budget_and_mutated_consent_denied_before_helper(self):
        self.prepared();review=self.reviewed();before=len(self.node.helpers)
        with self.assertRaisesRegex(TrainingError,'BATCH_UPDATE_LIMIT'):self.node.confirm_batch_reviews('fake',self.pub,review,epochs=3)
        self.assertEqual(len(self.node.helpers),before)
        self.node.confirm_batch_reviews('fake',self.pub,review)
        with self.assertRaisesRegex(TrainingError,'BATCH_LOCAL_IMMUTABLE'):self.node.confirm_batch_reviews('fake',self.pub,review,epochs=2)

    def test_auth_revocation_after_compute_does_not_commit_or_return_model(self):
        self.confirmed();original=self.store.evaluate
        def revoked(*args):
            result=original(*args);self.grants[('batch-demo','C001')]['active']=False;return result
        self.store.evaluate=revoked
        with self.assertRaisesRegex(TrainingError,'BATCH_COMPANY_DENIED'):self.node.access_batches('fake',self.pub,'run')
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT cursor FROM jobs').fetchone()[0],0)

    def test_canonical_checkpoint_tamper_and_wrong_key_build_denied(self):
        self.confirmed()
        with self.store.connect() as c:c.execute('UPDATE jobs SET weights=?',(b'changed',))
        with self.assertRaisesRegex(TrainingError,'BATCH_CHECKPOINT_TAMPERED'):self.node.access_batches('fake',self.pub,'run')

    def test_wrong_receipt_key_build_epoch_and_batch_label_order_rejected(self):
        self.confirmed();original=strict_json((self.node.root/'batch-consent.json').read_bytes())['payload']
        for change in ('receipt','key','build','order','epochs'):
            body=deepcopy(original)
            if change=='receipt':body['receipt_sha256']='0'*64
            if change=='key':body['key_epoch']='different'
            if change=='build':body['build_sha256']='0'*64
            if change=='order':body['label_batches'].reverse()
            if change=='epochs':body['epochs']=3
            with self.subTest(change=change),self.assertRaises(TrainingError):self.store.confirm(sign(body,self.key))
        with self.assertRaisesRegex(TrainingError,'SIGNATURE_INVALID'):self.store.confirm(sign(original,Ed25519PrivateKey.generate()))

    def test_cross_company_and_ungranted_batch_access_denied(self):
        self.confirmed();source=self.node.saved('batch-source.json');consent=strict_json((self.node.root/'batch-consent.json').read_bytes())
        body=dict(**self.node.bbase(source),job_id='btr_'+sha(canonical(consent))[:32],action='result')
        changed=dict(body,company_id='C002')
        with self.assertRaisesRegex(TrainingError,'BATCH_COMPANY_DENIED'):self.store.access(sign(changed,self.key))
        self.grants[('batch-demo','C001')]['batch_training']=False
        with self.assertRaisesRegex(TrainingError,'BATCH_COMPANY_DENIED'):self.store.access(sign(body,self.key))

    def test_saved_signed_dataset_tamper_is_not_used_for_fit(self):
        self.confirmed()
        with self.store.connect() as c:
            old=c.execute('SELECT packet FROM datasets').fetchone()[0];packet=strict_json(old)
            packet['payload']['batches'].reverse()
            c.execute('UPDATE datasets SET packet=?',(canonical(packet),))
        with self.assertRaisesRegex(TrainingError,'SIGNATURE_INVALID'):self.node.access_batches('fake',self.pub,'run')
        self.assertEqual(self.calls,[])

    def test_snapshot_time_split_locks_and_missing_labels(self):
        snapshots=SnapshotStore(self.root/'snapshots.sqlite3');data,req=native_batches();req['snapshot_id']=commit(snapshots,data,self.scope)
        plan=prepare_batch_plan(snapshots,self.scope,req);self.assertEqual(plan['status'],'ready')
        self.node.prepare_snapshot_batches(snapshots,req,expected_plan_sha256=plan['plan_sha256']);self.node.upload_batches('fake',self.pub)
        labels=LabelStore(self.root/'labels.sqlite3',secrets.token_bytes(32));locks=[]
        for i,part in enumerate(plan['parts']['training']):
            packet=labels.create(self.scope,source_packet(snapshots,self.scope,part['request']))
            for case in packet['cases']:
                b=dict(expected_revision=packet['revision'],request_id=secrets.token_hex(16),label=dict(record_id=case['record_id'],revision=case['revision'],outcome='verified_fraud' if i==0 else 'verified_non_fraud',explanation='Synthetic records checked for fixture only.',evidence_ids=[case['evidence'][0]['evidence_id']],documents_checked=True))
                packet=labels.change(self.scope,packet['packet_id'],'save',b)
            packet=labels.change(self.scope,packet['packet_id'],'lock',dict(expected_revision=packet['revision'],request_id=secrets.token_hex(16)))
            locks.append({k:packet[k] for k in ('packet_id','revision','lock_sha256')})
        self.node.scope=replace(self.scope,actor_id='model-operator',permissions=frozenset({'data.import','model.fit'}))
        self.node.confirm_locked_batches('fake',self.pub,labels,locks,epochs=2)
        self.node.access_batches('fake',self.pub,'run');self.assertEqual(self.node.receive_batches('fake',self.pub)['weights_code'],[1,1,-1])

    def test_snapshot_overlap_window_and_stale_preview_fail_before_encryption(self):
        snapshots=SnapshotStore(self.root/'snapshots.sqlite3');data,req=native_batches();req['snapshot_id']=commit(snapshots,data,self.scope)
        for kind in ('overlap','window','stale'):
            changed=deepcopy(req)
            if kind=='overlap':changed['evaluation_batches'][0][0]=changed['training_batches'][0][0]
            if kind=='window':changed['evaluation_start']=changed['training_start']
            with self.subTest(kind=kind),self.assertRaises(TrainingError):self.node.prepare_snapshot_batches(snapshots,changed,expected_plan_sha256='0'*64)
        self.assertEqual(self.node.helpers,[])

    def test_batch_cli_preview_and_stale_plan_do_not_open_crypto(self):
        from experiments.he_training import cli
        from types import SimpleNamespace
        snapshots=SnapshotStore(self.root/'snapshots.sqlite3');data,req=native_batches();req['snapshot_id']=commit(snapshots,data,self.scope)
        config=self.root/'config.json';config.write_bytes(canonical(dict(auth_file='test-only',snapshot_db=str(snapshots.path),company_id='C001',expected_batch_plan_sha256='0'*64)))
        token=self.root/'token';token.write_text('synthetic-test-token');source=self.root/'request.json';source.write_bytes(canonical(req));output=self.root/'preview.json'
        args=['encrypted_training.py','batch-preview','--config',str(config),'--token-file',str(token),'--data',str(source),'--output',str(output)]
        with patch.object(cli,'FileAuthorizer') as auth,patch('experiments.he_training.batch_cli.BatchEnterprise') as crypto:
            auth.return_value.authorize.return_value=self.scope
            with patch('sys.argv',args):cli.main()
            self.assertEqual(strict_json(output.read_bytes())['status'],'ready');crypto.assert_not_called()
            output.unlink();args[1]='batch-prepare'
            with patch('sys.argv',args),self.assertRaisesRegex(TrainingError,'BATCH_PREVIEW_STALE'):cli.main()
            crypto.assert_not_called()

    def test_real_labels_use_vault_not_ad_hoc_review_file(self):
        self.prepared();source=self.node.saved('batch-source.json')
        source['content']['simulated']=False
        atomic=__import__('experiments.he_training.protocol',fromlist=['atomic']).atomic
        atomic(self.node.root/'batch-source.json',canonical(sign(source,self.key)))
        with self.assertRaisesRegex(TrainingError,'REAL_BATCH_LABELS_REQUIRE_LOCKED_PACKETS'):self.node.confirm_batch_reviews('fake',self.pub,[])

    def test_three_four_batches_and_sixteen_rows_respect_update_budget(self):
        for count in (3,4):
            with self.subTest(batches=count):
                node=FakeEnterprise(self.root/str(count),self.scope,self.key,self.store)
                training=deepcopy(self.train)+[dict(x=[[1,0]]*4,row_ids=['B'+str(i)+'-'+str(j) for j in range(4)]) for i in range(count-2)]
                node.prepare_batches(training,self.evaluation,simulated=True);node.upload_batches('fake',self.pub)
                reviews=node.batch_review_templates()
                for i,r in enumerate(reviews):
                    for row in r['rows']:row.update(outcome='verified_fraud' if i==0 else 'verified_non_fraud',verified_at=datetime.now(timezone.utc).isoformat(),evidence_refs=['SYNTHETIC_ONLY'])
                node.confirm_batch_reviews('fake',self.pub,reviews,epochs=1)
                done,_=node.access_batches('fake',self.pub,'run')
                self.assertEqual(done['completed_updates'],count)
                self.assertEqual(node.receive_batches('fake',self.pub)['training_rows'],count*4)

    def test_shadow_approval_requires_holdout_evaluation_and_blocks_unapproved_shadow(self):
        snapshots=SnapshotStore(self.root/'snapshots.sqlite3');data,req=native_batches();req['snapshot_id']=commit(snapshots,data,self.scope)
        plan=prepare_batch_plan(snapshots,self.scope,req)
        self.node.prepare_snapshot_batches(snapshots,req,expected_plan_sha256=plan['plan_sha256']);self.node.upload_batches('fake',self.pub)
        labels=LabelStore(self.root/'labels.sqlite3',secrets.token_bytes(32));locks=[];eval_locks=[]
        for i,part in enumerate(plan['parts']['training']):
            packet=labels.create(self.scope,source_packet(snapshots,self.scope,part['request']))
            for case in packet['cases']:
                b=dict(expected_revision=packet['revision'],request_id=secrets.token_hex(16),label=dict(record_id=case['record_id'],revision=case['revision'],outcome='verified_fraud' if i==0 else 'verified_non_fraud',explanation='Synthetic records checked for fixture only.',evidence_ids=[case['evidence'][0]['evidence_id']],documents_checked=True))
                packet=labels.change(self.scope,packet['packet_id'],'save',b)
            packet=labels.change(self.scope,packet['packet_id'],'lock',dict(expected_revision=packet['revision'],request_id=secrets.token_hex(16)))
            locks.append({k:packet[k] for k in ('packet_id','revision','lock_sha256')})
        for part in plan['parts']['evaluation']:
            packet=labels.create(self.scope,source_packet(snapshots,self.scope,part['request']))
            for case in packet['cases']:
                b=dict(expected_revision=packet['revision'],request_id=secrets.token_hex(16),label=dict(record_id=case['record_id'],revision=case['revision'],outcome='verified_non_fraud',explanation='Synthetic holdout label for inspection only.',evidence_ids=[case['evidence'][0]['evidence_id']],documents_checked=True))
                packet=labels.change(self.scope,packet['packet_id'],'save',b)
            packet=labels.change(self.scope,packet['packet_id'],'lock',dict(expected_revision=packet['revision'],request_id=secrets.token_hex(16)))
            eval_locks.append({k:packet[k] for k in ('packet_id','revision','lock_sha256')})
        self.node.confirm_locked_batches('fake',self.pub,labels,locks,epochs=1)
        with self.assertRaisesRegex(TrainingError,'BATCH_MODEL_NOT_RECEIVED'):
            self.node.approve_batches('Reason before receive is rejected.')
        self.node.access_batches('fake',self.pub,'run')
        candidate=self.node.receive_batches('fake',self.pub)
        with self.assertRaisesRegex(TrainingError,'BATCH_HOLDOUT_EVALUATION_REQUIRED'):
            self.node.approve_batches('Reason before holdout evaluation is rejected.')
        with self.assertRaisesRegex(TrainingError,'BATCH_MODEL_NOT_APPROVED'):
            self.node.evaluate_shadow_holdout()
        evaluation=self.node.evaluate_holdout(label_store=labels,evaluation_locks=eval_locks)
        self.assertTrue(evaluation['held_out_from_training'])
        self.assertFalse(evaluation['labels_used_for_fit'])
        self.assertEqual(evaluation['holdout_labels']['non_fraud_rows'],4)
        eval_sha=sha(canonical(evaluation))
        with self.assertRaisesRegex(TrainingError,'APPROVAL_REASON_REQUIRED'):
            self.node.approve_batches('too short')
        with self.assertRaisesRegex(TrainingError,'BATCH_APPROVAL_MODEL_MISMATCH'):
            self.node.approve_batches('Valid reason for mismatch test.',expected_model_cipher_sha256='0'*64)
        with self.assertRaisesRegex(TrainingError,'BATCH_APPROVAL_PLAN_MISMATCH'):
            self.node.approve_batches('Valid reason for mismatch test.',expected_plan_sha256='0'*64)
        with self.assertRaisesRegex(TrainingError,'BATCH_APPROVAL_EVALUATION_MISMATCH'):
            self.node.approve_batches('Valid reason for mismatch test.',expected_evaluation_sha256='0'*64)
        signed=self.node.approve_batches(
            'Approved for shadow evaluation only after verifying parity and holdout.',
            expected_model_cipher_sha256=candidate['model_cipher_sha256'],
            expected_plan_sha256=plan['plan_sha256'],
            expected_evaluation_sha256=eval_sha,
        )
        body=verify(signed,self.node.public_key)
        self.assertEqual(body['status'],'approved_for_shadow_evaluation')
        self.assertTrue(body['shadow_only'])
        self.assertFalse(body['operational_activation'])
        self.assertFalse(body['active_model_replaced'])
        self.assertFalse(body['operational_queue_changed'])
        self.assertEqual(body['plan_sha256'],plan['plan_sha256'])
        self.assertEqual(body['evaluation_sha256'],eval_sha)
        with self.assertRaisesRegex(TrainingError,'SNAPSHOT_FEATURE_MAPPING_REQUIRED'):
            self.node.predict_batch_shadow([[0,0],[1,1]],mapping_fingerprint='wrong')
        shadow=self.node.evaluate_shadow_holdout()
        self.assertTrue(shadow['shadow_only'])
        self.assertFalse(shadow['active_model_replaced'])
        self.assertFalse(shadow['operational_queue_changed'])
        self.assertEqual(len(shadow['rows']),4)

    def test_reopened_or_superseded_label_packet_blocks_confirm_locked_batches(self):
        snapshots=SnapshotStore(self.root/'snapshots.sqlite3');data,req=native_batches();req['snapshot_id']=commit(snapshots,data,self.scope)
        plan=prepare_batch_plan(snapshots,self.scope,req)
        self.node.prepare_snapshot_batches(snapshots,req,expected_plan_sha256=plan['plan_sha256']);self.node.upload_batches('fake',self.pub)
        labels=LabelStore(self.root/'labels.sqlite3',secrets.token_bytes(32));locks=[]
        for i,part in enumerate(plan['parts']['training']):
            packet=labels.create(self.scope,source_packet(snapshots,self.scope,part['request']))
            for case in packet['cases']:
                b=dict(expected_revision=packet['revision'],request_id=secrets.token_hex(16),label=dict(record_id=case['record_id'],revision=case['revision'],outcome='verified_fraud' if i==0 else 'verified_non_fraud',explanation='Synthetic records checked for fixture only.',evidence_ids=[case['evidence'][0]['evidence_id']],documents_checked=True))
                packet=labels.change(self.scope,packet['packet_id'],'save',b)
            packet=labels.change(self.scope,packet['packet_id'],'lock',dict(expected_revision=packet['revision'],request_id=secrets.token_hex(16)))
            locks.append({k:packet[k] for k in ('packet_id','revision','lock_sha256')})
        reopened=labels.change(self.scope,locks[0]['packet_id'],'reopen',dict(expected_revision=locks[0]['revision'],request_id=secrets.token_hex(16)))
        with self.assertRaisesRegex(TrainingError,'LABEL_PACKET_NOT_LOCKED'):
            self.node.confirm_locked_batches('fake',self.pub,labels,locks,epochs=1)
        relocked=labels.change(self.scope,locks[0]['packet_id'],'lock',dict(expected_revision=reopened['revision'],request_id=secrets.token_hex(16)))
        with self.assertRaisesRegex(TrainingError,'LABEL_PACKET_REVISION_STALE'):
            self.node.confirm_locked_batches('fake',self.pub,labels,locks,epochs=1)
        locks[0]={k:relocked[k] for k in ('packet_id','revision','lock_sha256')}
        job=self.node.confirm_locked_batches('fake',self.pub,labels,locks,epochs=1)
        self.assertTrue(job['job_id'].startswith('btr_'))


if __name__=='__main__':unittest.main()
