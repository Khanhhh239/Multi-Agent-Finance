"""Orchestration fault tests with explicit fake crypto/transport, not HE proof."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from finance_input import AccessScope
from experiments.he4.coordinator import FourJobs
from experiments.he_inference.key_manager import create_key
from experiments.he_inference.protocol import canonical,sha,sign,public_hex
from experiments.he_inference.http_common import ServiceError
from experiments.he4 import FRESH_ADMISSION


class Bridge:
    def __init__(self,root):self.root=root;self.encryptions=0;self.opens=0
    def encrypt(self,scope,bundle,values,output,**kwargs):
        self.encryptions+=1;output.mkdir(parents=True)
        (output/'argument-0.cipher').write_bytes(canonical(values))
        return dict(arguments_sha256=[sha(canonical(values))],evaluation_keys_sha256='e'*64,binding=dict(company_id=next(iter(scope.company_ids))),key_epoch='test')
    def public_key(self,*args):
        p=self.root/'public.keys';p.write_bytes(b'public test bytes');return p
    def decrypt(self,scope,bundle,cipher,digest,output,context):
        self.opens+=1;return json.loads(cipher.read_bytes())['score']


class Coordinator(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.scope=AccessScope('test',frozenset({'C001'}),'reviewer',frozenset({'data.import'}));self.key=self.root/'wrap.json';create_key(self.key)
        auth=SimpleNamespace(authorize=lambda header,company:self.scope if company=='C001' else AccessScope('test',frozenset({company}),'reviewer',self.scope.permissions))
        self.ml=dict(company_id='C001',rows=[dict(record_id='T0',revision=1,available=True,status='available',reason=None,score=2.)])
        self.resumed_children=[]
        legacy=SimpleNamespace(submit=lambda *a:dict(job_id='child'),result=lambda *a:(200,deepcopy(self.ml)),resume=lambda *a:self.resumed_children.append(a[-1]),close=lambda:None)
        self.node=SimpleNamespace(auth=auth,jobs=legacy,model_db=self.root/'model.sqlite3',snapshot_db=self.root/'snapshots.sqlite3',provisioning_key=Ed25519PrivateKey.generate())
        self.cloud=Ed25519PrivateKey.generate();self.version='v1';self.evaluations=0;self.response=None;self.saved_packet=None;self.lose_reply=False
        self.context=dict(binding=dict(statistics_artifact_id=None),programs={n:dict(path=n,circuit_sha256=n[0]*64) for n in ('statistics','graph','rules')},worker_url='http://127.0.0.1:1',worker_verify_key=public_hex(self.cloud),version='v1')
        config=dict(state_dir=str(self.root/'state'),state_key_file=str(self.key),enterprise_root=str(self.root/'enterprise'),linux_distro='Debian',linux_python='/python')
        self.settings=SimpleNamespace(config=config,capture=lambda scope:dict(deepcopy(self.context),version=self.version),mutation_lock=threading.RLock())
        self.bridge=Bridge(self.root)
        self.plan=dict(plan_sha256='plan',rows=[dict(record_id='T0',revision=1,branches={
            'statistics':dict(available=True,status='ready',reason=None,requests=[dict(profile='statistics',role='statistics',values=[[-123,456]])]),
            'graph':dict(available=False,status='unavailable',reason='he_graph_node_limit',requests=[]),
            'rules':dict(available=False,status='unavailable',reason='rule_sources_unavailable',requests=[])
        })])
        self.jobs=FourJobs(self.node,self.settings,workers=0,bridge=self.bridge);self.addCleanup(lambda:self.jobs.close())
        from sme_fraud.snapshots import SnapshotStore
        SnapshotStore(self.node.snapshot_db)
        self.patch=patch.multiple('experiments.he4.coordinator',prepare_snapshot=lambda *a,**kw:deepcopy(self.plan),upload=self.upload,post=self.post,download=self.download)
        self.patch.start();self.addCleanup(self.patch.stop)

    def upload(self,url,scope,key,worker,path,purpose):return sha(Path(path).read_bytes())
    def post(self,url,path,packet,**kwargs):
        if path=='/v1/evaluate':
            self.evaluations+=1;self.saved_packet=deepcopy(packet);p=packet['payload']
            self.response=sign(dict(version='he4-worker/0.1.0',tenant_id=p['tenant_id'],company_id=p['company_id'],session_id=p['session_id'],nonce=p['nonce'],request_sha256=sha(canonical(packet)),circuit_sha256=p['circuit_sha256'],result_sha256=sha(b'{"score":579}')),self.cloud)
            if self.lose_reply:raise ServiceError(503,'WORKER_CONNECTION_UNAVAILABLE')
            return deepcopy(self.response)
        if path=='/v1/results' and self.response:return deepcopy(self.response)
        raise AssertionError(path)
    def download(self,url,scope,key,digest,path):Path(path).write_bytes(b'{"score":579}')
    def submit(self):return self.jobs.submit('C001','Bearer synthetic','stable-request-key',dict(artifact_id='mth_'+'a'*64,snapshot_id='snp_'+'b'*32,as_of='2026-10-10T00:00:00+07:00'))['job_id']

    def test_every_branch_and_unavailable_reason_kept_without_ensemble(self):
        job=self.submit();self.assertFalse(self.jobs._process(self.scope,job));status,value=self.jobs.result('C001','Bearer synthetic',job)
        self.assertEqual(status,200);self.assertEqual(value['row_count'],1);self.assertEqual(set(value['rows'][0]['branches']),{'rules','statistics','graph','ml'})
        self.assertEqual(value['rows'][0]['branches']['statistics']['raw_score'],579/1024)
        self.assertEqual(value['rows'][0]['branches']['graph']['reason'],'he_graph_node_limit');self.assertIsNone(value['aggregation']['score'])

    def test_lost_reply_restart_keeps_envelope_and_does_not_encrypt_again(self):
        self.lose_reply=True;job=self.submit();self.assertTrue(self.jobs._process(self.scope,job))
        _,saved=self.jobs.store.get(self.scope,job);packet=deepcopy(saved['pending']['tasks'][0]['packet'])
        self.jobs.close();self.jobs=FourJobs(self.node,self.settings,workers=0,bridge=self.bridge)
        self.jobs.resume('C001','Bearer synthetic',job);self.assertFalse(self.jobs._process(self.scope,job))
        self.assertEqual(self.evaluations,1);self.assertEqual(self.bridge.encryptions,1);self.assertEqual(self.saved_packet,packet)
        self.assertEqual(self.resumed_children,['child'])
        self.assertEqual(self.jobs.result('C001','Bearer synthetic',job)[0],200)

    def test_model_build_or_policy_change_cannot_resume_with_new_config(self):
        self.lose_reply=True;job=self.submit();self.assertTrue(self.jobs._process(self.scope,job));self.version='changed'
        self.assertFalse(self.jobs._process(self.scope,job));value=self.jobs.status('C001','Bearer synthetic',job)
        self.assertEqual(value['phase'],'failed');self.assertEqual(value['reason'],'he4_configuration_changed');self.assertEqual(self.evaluations,1)

    def test_missing_ml_model_does_not_hide_other_branch_or_fit(self):
        self.node.jobs.submit=lambda *args:(_ for _ in ()).throw(AssertionError('no implicit model/child'))
        job=self.jobs.submit('C001','Bearer synthetic','missing-ml-model',dict(artifact_id=None,snapshot_id='snp_'+'b'*32,as_of='2026-10-10T00:00:00+07:00'))['job_id']
        self.assertFalse(self.jobs._process(self.scope,job));status,value=self.jobs.result('C001','Bearer synthetic',job)
        self.assertEqual(status,200);self.assertEqual(value['row_count'],1);self.assertTrue(value['rows'][0]['branches']['statistics']['available']);self.assertEqual(value['rows'][0]['branches']['ml']['reason'],'artifact_missing')

    def test_response_tamper_is_rejected_before_native_open(self):
        original=self.post
        def bad(*args,**kwargs):
            value=original(*args,**kwargs);value['payload']['company_id']='C002';return value
        with patch('experiments.he4.coordinator.post',side_effect=bad):
            job=self.submit();self.assertFalse(self.jobs._process(self.scope,job))
        self.assertEqual(self.bridge.opens,0);self.assertEqual(self.jobs.status('C001','Bearer synthetic',job)['phase'],'failed')

    def pause_before_admission(self):
        from sme_fraud.auth import AuthError
        job=self.submit();save=self.jobs._save
        def pause(scope,job,data,phase,reason=None):
            if phase=='sending':raise AuthError(401,'AUTH_REQUIRED','fixture expired','reauthenticate')
            return save(scope,job,data,phase,reason)
        with patch.object(self.jobs,'_save',side_effect=pause):self.assertFalse(self.jobs._process(self.scope,job))
        row,data=self.jobs.store.get(self.scope,job);self.assertEqual(row['phase'],'waiting_authorization')
        self.assertEqual(self.evaluations,0);return job,deepcopy(data['pending']['tasks'][0]['packet'])

    def test_seven_hour_authorization_pause_before_admission_keeps_packet_key_and_job(self):
        import time
        job,original=self.pause_before_admission();future=time.time()+7*3600;admissions=[];ordinary=self.post
        def transport(url,path,packet,**kwargs):
            if path in ('/v1/results','/v1/resume'):raise ServiceError(403,'SESSION_NOT_REGISTERED')
            if path=='/v1/admit':
                self.assertEqual(packet['payload']['purpose'],FRESH_ADMISSION);self.assertEqual(packet['payload']['request'],original)
                self.assertGreater(packet['payload']['expires_at'],future);self.assertLess(original['payload']['expires_at'],future)
                admissions.append(packet);return ordinary(url,'/v1/evaluate',packet['payload']['request'])
            raise AssertionError('expired inner packet must not be re-evaluated directly')
        self.jobs.resume('C001','Bearer synthetic',job)
        with patch('experiments.he4.client_transport.time.time',return_value=future),patch('experiments.he4.coordinator.post',side_effect=transport):
            self.assertFalse(self.jobs._process(self.scope,job))
        self.assertEqual(len(admissions),1);self.assertEqual(self.evaluations,1);self.assertEqual(self.saved_packet,original)
        self.assertEqual(self.bridge.encryptions,1);self.assertEqual(self.bridge.opens,1);self.assertEqual(self.jobs.result('C001','Bearer synthetic',job)[0],200)

    def test_fresh_admission_lost_reply_recovers_without_new_cipher_or_packet(self):
        job,original=self.pause_before_admission();ordinary=self.post;admissions=[]
        def transport(url,path,packet,**kwargs):
            if path=='/v1/results' and self.response:return deepcopy(self.response)
            if path in ('/v1/results','/v1/resume'):raise ServiceError(403,'SESSION_NOT_REGISTERED')
            if path=='/v1/admit':
                admissions.append(packet);ordinary(url,'/v1/evaluate',packet['payload']['request']);raise ServiceError(503,'WORKER_CONNECTION_UNAVAILABLE')
            raise AssertionError(path)
        self.jobs.resume('C001','Bearer synthetic',job)
        with patch('experiments.he4.coordinator.post',side_effect=transport):
            self.assertTrue(self.jobs._process(self.scope,job));self.assertFalse(self.jobs._process(self.scope,job))
        self.assertEqual(len(admissions),1);self.assertEqual(self.evaluations,1);self.assertEqual(self.saved_packet,original);self.assertEqual(self.bridge.encryptions,1)
        self.assertEqual(self.jobs.result('C001','Bearer synthetic',job)[0],200)

    def test_expiry_before_initial_delivery_is_retryable_then_freshly_admitted(self):
        job=self.submit();ordinary=self.post;original=[];admissions=[]
        def transport(url,path,packet,**kwargs):
            if path=='/v1/evaluate':original.append(deepcopy(packet));raise ServiceError(410,'HE4_EXPIRED')
            if path in ('/v1/results','/v1/resume'):raise ServiceError(403,'SESSION_NOT_REGISTERED')
            if path=='/v1/admit':
                self.assertEqual(packet['payload']['request'],original[0]);admissions.append(packet)
                return ordinary(url,'/v1/evaluate',packet['payload']['request'])
            raise AssertionError(path)
        with patch('experiments.he4.coordinator.post',side_effect=transport):
            self.assertTrue(self.jobs._process(self.scope,job));self.assertEqual(self.jobs.status('C001','Bearer synthetic',job)['phase'],'retryable')
            self.assertFalse(self.jobs._process(self.scope,job))
        self.assertEqual(len(admissions),1);self.assertEqual(self.bridge.encryptions,1);self.assertEqual(self.evaluations,1)
        self.assertEqual(self.jobs.result('C001','Bearer synthetic',job)[0],200)
