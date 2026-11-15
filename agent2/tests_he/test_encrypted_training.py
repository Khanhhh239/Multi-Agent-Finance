"""Consent/scope/restart checks. Fake cipher bytes test lifecycle only, not HE."""
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import numpy as np
from experiments.he_training import VERSION,TARGET,PROFILE
from experiments.he_training.protocol import encode,decode,sign,verify,sha,canonical,TrainingError
from experiments.he_training.store import CloudStore
from experiments.he_training.enterprise import verified_labels as validate_labels,Enterprise
from experiments.he_training.circuit import oracle,update,samples


def verified_labels(review,ids,scope,**kwargs):
    return validate_labels(review,ids,scope,dataset_id='ds_test',receipt_sha256='e'*64,**kwargs)


class EncryptedTrainingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.node=Ed25519PrivateKey.generate();self.worker=Ed25519PrivateKey.generate();self.calls=[]
        self.grant=dict(active=True,node_verify_key=self.node.public_key().public_bytes_raw().hex(),key_epoch='key_C001',target=TARGET,verification_mode='synthetic_expected')
        self.grants={('demo','C001'):self.grant}
        self.base=dict(version=VERSION,profile=PROFILE,target=TARGET,tenant_id='demo',company_id='C001',key_epoch='key_C001',dataset_id='ds_example',build_sha256='b'*64)
        self.store=CloudStore(self.temp.name,self.grants,self.worker,'b'*64,self.evaluate)
        self.pub=self.worker.public_key().public_bytes_raw().hex()

    def evaluate(self,x,y,w,body):self.calls.append(w);return w+b'-step'

    def upload(self,**changes):
        b=dict(**self.base,x_cipher=encode(b'fake-X'),x_cipher_sha256=sha(b'fake-X'),rows=4,features=2);b.update(changes)
        return self.store.upload(sign(b,self.node))

    def consent(self,receipt=None,**changes):
        receipt=receipt or self.upload()
        body=dict(**self.base,consent_id='consent_one',receipt_sha256=sha(canonical(receipt)),label_revision=1,label_review_commitment='f'*64,y_cipher=encode(b'fake-y'),y_cipher_sha256=sha(b'fake-y'),weights_cipher=encode(b'fake-W0'),weights_cipher_sha256=sha(b'fake-W0'),steps=2,verification_mode='synthetic_expected')
        body.update(changes);return sign(body,self.node)

    def access(self,job,action='run',**changes):
        body=dict(**self.base,job_id=job,action=action);body.update(changes);return self.store.access(sign(body,self.node))

    def test_upload_receipt_does_not_train_or_create_model(self):
        first=self.upload();self.assertEqual(self.upload(),first);self.assertEqual(self.calls,[])
        self.assertEqual(verify(first,self.pub)['kind'],'dataset_received')
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM jobs').fetchone()[0],0)

    def test_confirm_then_run_retries_same_job_once_and_returns_ciphertext(self):
        packet=self.consent();one=self.store.confirm(packet);self.assertEqual(self.store.confirm(packet),one)
        job=verify(one,self.pub)['job_id'];self.assertEqual(self.calls,[])
        self.assertEqual(verify(self.access(job),self.pub)['completed_steps'],2)
        self.access(job);self.assertEqual(len(self.calls),2)
        result=verify(self.access(job,'result'),self.pub)
        self.assertEqual(decode(result['model_cipher']),b'fake-W0-step-step')
        self.assertNotIn('weights_code',result)

    def test_consent_required_before_run(self):
        self.upload()
        with self.assertRaisesRegex(TrainingError,'JOB_NOT_FOUND'):self.access('trn_'+'0'*32)
        with self.assertRaisesRegex(TrainingError,'DATASET_NOT_RECEIVED'):
            self.store.confirm(self.consent(dataset_id='another'))

    def test_plain_data_labels_unknown_fields_and_broken_cipher_rejected(self):
        for changes in [dict(X=[[1]]),dict(y=[0,1]),dict(weights=[0]),dict(rows=5),dict(x_cipher_sha256='a'*64)]:
            with self.subTest(changes=list(changes)):
                with self.assertRaises(TrainingError):self.upload(**changes)

    def test_data_and_consent_conflicts_do_not_overwrite(self):
        self.upload()
        with self.assertRaisesRegex(TrainingError,'DATASET_CONFLICT'):self.upload(x_cipher=encode(b'changed'),x_cipher_sha256=sha(b'changed'))
        self.store.confirm(self.consent())
        with self.assertRaisesRegex(TrainingError,'CONSENT_CONFLICT'):self.store.confirm(self.consent(steps=3))

    def test_wrong_receipt_context_target_or_key_denied(self):
        for change in [dict(receipt_sha256='0'*64),dict(key_epoch='wrong'),dict(build_sha256='wrong'),dict(target='needs-action/1.0.0'),dict(verification_mode='human_verified')]:
            with self.subTest(change=change):
                with self.assertRaises(TrainingError):self.store.confirm(self.consent(**change))

    def test_foreign_company_actor_signature_and_revoked_grant_denied(self):
        job=verify(self.store.confirm(self.consent()),self.pub)['job_id']
        with self.assertRaisesRegex(TrainingError,'COMPANY_DENIED'):self.access(job,company_id='C002')
        body=dict(**self.base,job_id=job,action='run')
        with self.assertRaisesRegex(TrainingError,'SIGNATURE_INVALID'):self.store.access(sign(body,Ed25519PrivateKey.generate()))
        self.grant['active']=False
        with self.assertRaisesRegex(TrainingError,'COMPANY_DENIED'):self.access(job)

    def test_same_dataset_id_in_two_companies_has_separate_jobs(self):
        key=Ed25519PrivateKey.generate();grant=dict(self.grant,node_verify_key=key.public_key().public_bytes_raw().hex(),key_epoch='key_C002')
        self.grants[('demo','C002')]=grant
        first=verify(self.store.confirm(self.consent()),self.pub)['job_id']
        source=dict(**self.base,x_cipher=encode(b'other-X'),x_cipher_sha256=sha(b'other-X'),rows=4,features=2);source.update(company_id='C002',key_epoch='key_C002')
        receipt=self.store.upload(sign(source,key));body=self.consent()['payload'].copy();body.update(company_id='C002',key_epoch='key_C002',receipt_sha256=sha(canonical(receipt)))
        second=verify(self.store.confirm(sign(body,key)),self.pub)['job_id'];self.assertNotEqual(first,second)
        request=dict(**self.base,job_id=first,action='result');request.update(company_id='C002',key_epoch='key_C002')
        with self.assertRaisesRegex(TrainingError,'JOB_NOT_FOUND'):self.store.access(sign(request,key))

    def test_enterprise_rechecks_permissions_and_requires_explicit_approval(self):
        node=Enterprise.__new__(Enterprise);node.scope=SimpleNamespace(permissions={'data.import'},actor_id='reader');node.recheck=lambda:node.scope
        with self.assertRaisesRegex(TrainingError,'PERMISSION_DENIED'):node.guard('model.fit')
        node.recheck=lambda:SimpleNamespace(permissions=set(),actor_id='reader')
        with self.assertRaisesRegex(TrainingError,'AUTH_CONTEXT_CHANGED'):node.guard()
        node.recheck=None;node.root=Path(self.temp.name)
        with self.assertRaisesRegex(TrainingError,'MODEL_NOT_APPROVED'):node.predict_shadow([[1,0]])

    def test_local_dataset_signature_detects_changes_after_encryption(self):
        node=Enterprise.__new__(Enterprise);node.root=Path(self.temp.name);node.meta={'company_id':'C001'}
        data=dict(dataset_id='ds_x',x=[[-1,0]]*4,row_ids=['a','b','c','d'],simulated=True)
        upload=canonical({'ciphertext':'fake'});(node.root/'upload.json').write_bytes(upload)
        (node.root/'dataset.json').write_bytes(canonical(data))
        signature=sign(dict(**node.meta,dataset_sha256=sha(canonical(data)),upload_sha256=sha(upload)),self.node)
        (node.root/'dataset-auth.json').write_bytes(canonical(signature))
        with patch.object(node,'signing_key',return_value=self.node):
            self.assertEqual(node.dataset(),data)
            data['x'][0][0]=1;(node.root/'dataset.json').write_bytes(canonical(data))
            with self.assertRaisesRegex(TrainingError,'LOCAL_DATASET_TAMPERED'):node.dataset()

    def test_shadow_requires_signed_approval_for_exact_candidate(self):
        node=Enterprise.__new__(Enterprise);node.root=Path(self.temp.name);node.meta={'company_id':'C001'}
        node.scope=SimpleNamespace(permissions={'data.import','model.fit'},actor_id='trainer');node.recheck=None
        model=dict(company_id='C001',validation='quantized_training_parity_passed',coefficients=[1,0],intercept=0)
        path=node.root/'candidate.json';path.write_bytes(canonical(sign(model,self.node)))
        with patch.object(node,'signing_key',return_value=self.node):
            with self.assertRaisesRegex(TrainingError,'MODEL_NOT_APPROVED'):node.predict_shadow([[1,0]])
            node.approve('Independent technical fixture approved for shadow.')
            result=node.predict_shadow([[-1,0],[1,0]]);self.assertLess(result['scores'][0],result['scores'][1]);self.assertFalse(result['fraud_verdicts'])
            changed=dict(model,intercept=1);path.write_bytes(canonical(sign(changed,self.node)))
            with self.assertRaisesRegex(TrainingError,'MODEL_NOT_APPROVED'):node.predict_shadow([[1,0]])

    def test_checkpoint_restart_continues_same_encrypted_weights(self):
        job=verify(self.store.confirm(self.consent()),self.pub)['job_id'];count=[0]
        def crash(x,y,w,b):
            count[0]+=1
            if count[0]==2:raise RuntimeError('simulated worker stop')
            return w+b'-step'
        self.store.evaluate=crash
        with self.assertRaises(RuntimeError):self.access(job)
        self.store=CloudStore(self.temp.name,self.grants,self.worker,'b'*64,self.evaluate)
        done=verify(self.access(job),self.pub);self.assertEqual(done['completed_steps'],2)
        self.assertEqual(self.calls,[b'fake-W0-step'])
        self.assertEqual(decode(verify(self.access(job,'result'),self.pub)['model_cipher']),b'fake-W0-step-step')

    def test_quantized_scalar_oracle_matches_vector_equations(self):
        for x,y,w in samples():self.assertEqual(update(x,y,w).tolist(),oracle(x,y,w))
        x=[[-1,-1],[-1,1],[1,-1],[1,1]];self.assertNotEqual(oracle(x,[0,0,1,1],[0,0,0]),oracle(x,[1,1,0,0],[0,0,0]))

    def test_only_explicit_verified_fraud_labels_are_accepted(self):
        ids=['a','b','c','d'];scope=SimpleNamespace(actor_id='reviewer',permissions={'evidence.verify'},tenant_id='demo',company_ids=frozenset({'C001'}))
        review=dict(target=TARGET,tenant_id='demo',company_id='C001',dataset_id='ds_test',receipt_sha256='e'*64,revision=1,verification_mode='synthetic_expected',rows=[dict(record_id=r,outcome='verified_fraud' if i>1 else 'verified_non_fraud',verified_by='reviewer',verified_at='2026-01-01T00:00:00+07:00',evidence_refs=['synthetic-case']) for i,r in enumerate(ids)])
        self.assertEqual(verified_labels(review,ids,scope,simulated=True),[0,0,1,1])
        for outcome in ('confirmed_risk','legitimate','inconclusive',None):
            changed=json.loads(json.dumps(review));changed['rows'][0]['outcome']=outcome
            with self.assertRaisesRegex(TrainingError,'LABEL_NOT_VERIFIED'):verified_labels(changed,ids,scope,simulated=True)
        for field,value in [('verified_by','other'),('verified_at','2099-01-01T00:00:00+07:00'),('evidence_refs',[])]:
            changed=json.loads(json.dumps(review));changed['rows'][0][field]=value
            with self.assertRaises(TrainingError):verified_labels(changed,ids,scope,simulated=True)
        with self.assertRaisesRegex(TrainingError,'LABEL_VERIFICATION_DENIED'):verified_labels(review,ids,SimpleNamespace(permissions=set()),simulated=True)
        with self.assertRaisesRegex(TrainingError,'LABEL_VERIFICATION_MODE'):verified_labels(review,ids,scope,simulated=False)
        for key,value in [('company_id','C002'),('dataset_id','other'),('receipt_sha256','f'*64),('tenant_id','other')]:
            changed=dict(review,**{key:value})
            with self.assertRaisesRegex(TrainingError,'LABEL_DATASET_BINDING'):verified_labels(changed,ids,scope,simulated=True)


if __name__=='__main__':unittest.main()
