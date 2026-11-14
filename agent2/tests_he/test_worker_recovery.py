"""Fenced ownership, bound replay and actual subprocess crash/recovery boundaries."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from experiments.he_inference.worker_store import WorkerStore,APPLICATION_ID
from experiments.he_inference.cloud_worker import reserve
from experiments.he_inference.http_common import ServiceError
from experiments.he_inference.protocol import HEUnavailable,canonical,sha,read_json,sign,verify,public_hex,ABS_TOLERANCE,REL_TOLERANCE
from experiments.he_inference.services_demo import Pair,request
from experiments.he_inference.demo import worker_environment
from experiments.he_inference.key_manager import load_key
from experiments.he_inference.node_job_store import JobStore
from experiments.he_inference.registry_demo import database_dump
from experiments.he_inference.registry_export import ReadOnlySnapshots,_load_model,export_snapshot
from experiments.he_inference.worker_server import Worker
from sme_fraud.snapshot_features import build_from_snapshot
from sme_fraud.method_preprocess import row_values


class WorkerOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='worker-store-recovery-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=WorkerStore(self.root);self.addCleanup(lambda:self.store.close())
        self.p=dict(tenant_id='demo',company_id='C001',session_id='session',nonce='nonce')
        self.digest='a'*64
    def reopen(self):
        self.store.close();self.store=WorkerStore(self.root)
    def code(self,code,callback):
        with self.assertRaises((ServiceError,HEUnavailable)) as e:callback()
        self.assertEqual(e.exception.code,code)
    def test_second_worker_cannot_reset_running_job(self):
        _,_,token=self.store.claim(self.p,self.digest)
        before=database_dump(self.store.path)
        self.code('WORKER_STATE_IN_USE',lambda:WorkerStore(self.root))
        self.assertEqual(database_dump(self.store.path),before)
        self.store.finish(self.p,self.digest,token,{'ok':True},'done')
    def test_concurrent_duplicate_claims_have_one_owner(self):
        def claim(_):
            try:return self.store.claim(self.p,self.digest)[1]
            except ServiceError as e:return e.code
        with ThreadPoolExecutor(4) as pool:values=list(pool.map(claim,range(4)))
        self.assertEqual(values.count('new'),1);self.assertEqual(values.count('WORKER_IN_PROGRESS'),3)
    def test_restart_only_retries_exact_request_hash_and_fences_old_token(self):
        _,_,old=self.store.claim(self.p,self.digest);self.reopen()
        self.code('REQUEST_NONCE_CONFLICT',lambda:self.store.claim(self.p,'b'*64))
        _,state,new=self.store.claim(self.p,self.digest)
        self.assertEqual(state,'resume');self.assertNotEqual(old,new)
        self.code('WORKER_ATTEMPT_STALE',lambda:self.store.finish(self.p,self.digest,old,{'wrong':1},'done'))
        self.store.finish(self.p,self.digest,new,{'correct':1},'done')
        self.assertEqual(self.store.claim(self.p,self.digest)[:2],({'correct':1},'done'))
    def test_committed_result_cannot_be_overwritten(self):
        _,_,token=self.store.claim(self.p,self.digest);self.store.finish(self.p,self.digest,token,{'ok':1},'done')
        self.code('WORKER_ATTEMPT_STALE',lambda:self.store.finish(self.p,self.digest,token,{'wrong':1},'failed'))
        self.reopen();self.assertEqual(self.store.claim(self.p,self.digest)[:2],({'ok':1},'done'))
    def test_reserve_requires_current_claim(self):
        _,_,token=self.store.claim(self.p,self.digest);called=[]
        self.code('WORKER_ATTEMPT_STALE',lambda:self.store.reserve(self.p,self.digest,'wrong',lambda:called.append(1)))
        self.assertEqual(called,[])
        self.store.reserve(self.p,self.digest,token,lambda:called.append(1));self.assertEqual(called,[1])
    def test_managed_replay_can_only_resume_same_bound_hash(self):
        path=self.store.replay_path
        reserve(path,self.p,request_hash=self.digest)
        self.code('REPLAY_REJECTED',lambda:reserve(path,self.p,request_hash=self.digest))
        self.code('REPLAY_REQUEST_CONFLICT',lambda:reserve(path,self.p,request_hash='b'*64,resuming=True))
        reserve(path,self.p,request_hash=self.digest,resuming=True)
        self.code('REPLAY_REJECTED',lambda:reserve(path,self.p))
        with closing(sqlite3.connect(path)) as c:self.assertEqual(c.execute('SELECT count(*) FROM requests').fetchone()[0],1)
    def test_legacy_burned_nonce_is_never_upgraded_to_resumable(self):
        reserve(self.store.replay_path,self.p)
        self.code('REPLAY_REJECTED',lambda:reserve(self.store.replay_path,self.p,request_hash=self.digest,resuming=True))
    def test_crash_before_reservation_can_create_bound_reservation_on_resume(self):
        self.store.claim(self.p,self.digest);self.reopen();_,state,token=self.store.claim(self.p,self.digest)
        self.assertEqual(state,'resume')
        self.store.reserve(self.p,self.digest,token,lambda:reserve(self.store.replay_path,self.p,request_hash=self.digest,resuming=True))
    def test_retrieval_requests_recompute_only_for_pending_exact_hash(self):
        self.store.claim(self.p,self.digest);self.reopen()
        self.code('RESULT_REQUEST_MISMATCH',lambda:self.store.retrieve(dict(self.p,request_sha256='b'*64)))
        self.code('RESULT_NOT_READY',lambda:self.store.retrieve(dict(self.p,request_sha256=self.digest)))
    def test_terminal_failure_never_reopens(self):
        _,_,token=self.store.claim(self.p,self.digest)
        self.store.finish(self.p,self.digest,token,dict(reason=dict(code='INVALID_CIPHERTEXT')),'failed');self.reopen()
        self.assertEqual(self.store.claim(self.p,self.digest)[1],'failed')
    def test_legacy_jobs_migrate_without_reopening_old_failed_or_burned_requests(self):
        self.store.close()
        # Separate, explicitly legacy worker state, not an unrelated DB.
        root=self.root/'legacy';root.mkdir();path=root/'jobs.sqlite3'
        with closing(sqlite3.connect(path)) as c:
            with c:
                c.execute(f'PRAGMA application_id={APPLICATION_ID}')
                c.execute('CREATE TABLE sessions (tenant TEXT,company TEXT,session TEXT,node_key TEXT,expires INTEGER,policy BLOB,PRIMARY KEY(tenant,company,session))')
                c.execute('CREATE TABLE jobs (tenant TEXT,company TEXT,session TEXT,nonce TEXT,request_hash TEXT,state TEXT,result BLOB,PRIMARY KEY(tenant,company,session,nonce))')
                c.execute("INSERT INTO jobs VALUES ('demo','C001','session','nonce',?,'running',NULL)",(self.digest,))
        with closing(WorkerStore(root)) as migrated:
            value,state,_=migrated.claim(self.p,self.digest)
            self.assertEqual(state,'failed');self.assertEqual(value['reason']['code'],'WORKER_INTERRUPTED_LEGACY')
    def test_newer_storage_is_rejected_without_rewriting_database(self):
        self.store.close()
        with closing(sqlite3.connect(self.store.path)) as c:
            with c:c.execute('PRAGMA user_version=999')
        before=self.store.path.read_bytes()
        self.code('WORKER_STORAGE_VERSION',lambda:WorkerStore(self.root))
        self.assertEqual(self.store.path.read_bytes(),before)


# Trusted test bootstrap only, run outside the bundle. No production fault
# switches or request-controlled pause/skip/replay flags are added to the API.
BOOTSTRAP=r'''
import sys,time
from pathlib import Path
from experiments.he_inference import worker_server as server,cloud_worker
from experiments.he_inference.worker_store import WorkerStore
stage,marker,release=sys.argv[1:4];sys.argv=sys.argv[:1]+sys.argv[4:]
entered=False
def pause():
    global entered
    if entered:return
    entered=True;Path(marker).write_text(stage)
    while not Path(release).exists():time.sleep(.005)
if stage=='claimed':
    original=WorkerStore.claim
    def claim(self,*args):
        result=original(self,*args)
        if result[1] in ('new','resume'):pause()
        return result
    WorkerStore.claim=claim
elif stage=='reserved':
    original=server.reserve
    def reserve(*args,**kwargs):
        result=original(*args,**kwargs);pause();return result
    server.reserve=reserve
elif stage=='computed':
    original=server.evaluate
    def evaluate(*args,**kwargs):
        result=original(*args,**kwargs);pause();return result
    server.evaluate=evaluate
elif stage=='committed':
    original=WorkerStore.finish
    def finish(self,*args,**kwargs):
        result=original(self,*args,**kwargs)
        if args[-1]=='done':pause()
        return result
    WorkerStore.finish=finish
server.main()
'''


def start_fault_worker(pair,stage):
    pair._stop(pair.worker_process)
    folder=pair.worker_root/('fault-'+stage+'-'+str(time.time_ns()));folder.mkdir()
    ready=folder/'ready.json';marker=folder/'paused';release=folder/'release'
    env=worker_environment();env['PYTHONPATH']=str(pair.bundle)
    cmd=[sys.executable,'-X','utf8','-B','-c',BOOTSTRAP,stage,str(marker),str(release),
         '--config',str(pair.worker_config),'--port',str(pair.worker_port),'--ready-file',str(ready)]
    process=subprocess.Popen(cmd,cwd=pair.bundle,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    pair.stack.callback(pair._stop,process);pair.worker_process=process
    end=time.monotonic()+25
    while not ready.exists():
        if process.poll() is not None:raise RuntimeError(process.stderr.read().decode('utf-8',errors='replace'))
        if time.monotonic()>end:raise RuntimeError('fault worker startup timeout')
        time.sleep(.02)
    return marker,release


def node_payload(pair,job):
    # Read only within this test's private enterprise fixture. Never print keys,
    # original nonce, ciphertext, source values or context into test output.
    key=load_key(pair.state_key_path,purpose='state-wrapping').material
    keys=HKDF(algorithm=hashes.SHA256(),length=64,salt=b'he-node-jobs-v1',info=b'enterprise-storage-and-idempotency').derive(key)
    reader=object.__new__(JobStore);reader.aes=AESGCM(keys[:32])
    with closing(sqlite3.connect(pair.enterprise/'state/jobs.sqlite3')) as c:
        c.row_factory=sqlite3.Row;row=c.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone()
    return reader.open(row)


class NativeWorkerRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='native-worker-recovery-');cls.addClassCleanup(cls.temp.cleanup)
        cls.pair=Pair(cls.temp.name);cls.addClassCleanup(cls.pair.close);cls.pair.start()
        cls.auth=cls.pair.env['policy'].read_bytes();cls.grants=cls.pair.grants_file.read_bytes()
        cls.original={k:database_dump(cls.pair.env[k]) for k in ('model_db','snapshot_db')}
        cls.keys=[cls.pair.node_key_path.read_bytes(),cls.pair.state_key_path.read_bytes()]
    def setUp(self):
        self.pair.env['policy'].write_bytes(self.auth);self.pair.grants_file.write_bytes(self.grants)
        self.pair.restart_worker();self.pair.restart_node()
    def tearDown(self):
        self.assertEqual(self.original,{k:database_dump(self.pair.env[k]) for k in self.original})
        self.assertEqual(self.keys,[self.pair.node_key_path.read_bytes(),self.pair.state_key_path.read_bytes()])
    def endpoint(self,company='C001'):return '/v1/companies/'+company+'/he/jobs'
    def call(self,path,body=None,headers=None):
        return request(self.pair.node_port,path,body,headers={'Authorization':self.pair.env['header'],**(headers or {})})
    def submit(self,company,key):return self.call(self.endpoint(company),self.pair.body(company),{'Idempotency-Key':key})
    def wait_paused(self,marker):
        end=time.monotonic()+35
        while not marker.exists():
            self.assertIsNone(self.pair.worker_process.poll())
            if time.monotonic()>end:self.fail('fault boundary not reached')
            time.sleep(.01)
    def wait_terminal(self,company,job):
        end=time.monotonic()+40
        while time.monotonic()<end:
            code,value=self.call(self.endpoint(company)+'/'+job)
            self.assertEqual(code,200,value)
            if value['phase'] in ('completed','failed','expired','waiting_authorization'):return value
            time.sleep(.05)
        self.fail('job did not reach terminal state')
    def exercise(self,stage,company='C001',restart_node=False):
        pair=self.pair;marker,_=start_fault_worker(pair,stage);key='fault-'+stage+'-'+company+('-node' if restart_node else '')
        code,state=self.submit(company,key);self.assertIn(code,(200,202));job=state['job_id'];self.wait_paused(marker)
        pending=node_payload(pair,job);packet=pending['pending']['packet'];request_hash=sha(canonical(packet))
        context_hash=sha(pending['pending']['private_context'].encode())
        with closing(sqlite3.connect(pair.worker_root/'state/jobs.sqlite3')) as c:
            row=c.execute('SELECT state,result,generation FROM jobs WHERE request_hash=?',(request_hash,)).fetchone()
        self.assertEqual(row[0],'done' if stage=='committed' else 'running')
        cached=row[1]
        pair._stop(pair.worker_process);pair.restart_worker()
        if restart_node:
            pair.restart_node();saved=node_payload(pair,job)
            self.assertEqual(sha(saved['pending']['private_context'].encode()),context_hash)
        # Repeated clicks/resumes keep the original enterprise job/key/packet.
        for _ in range(3):self.assertEqual(self.submit(company,key)[1]['job_id'],job)
        state=self.wait_terminal(company,job);self.assertEqual(state['phase'],'completed',state)
        code,result=self.call(self.endpoint(company)+'/'+job+'/result');self.assertEqual(code,200,result)
        self.assertEqual(result['row_count'],5);self.assertTrue(all(r['available'] for r in result['rows']))
        done=node_payload(pair,job);self.assertEqual(done['receipt']['request_sha256'],request_hash)
        self.assertEqual(done['receipt']['opaque_model_id'],pending['pending']['receipt']['opaque_model_id'])
        scope=pair.env['auth'].authorize(pair.env['header'],company)
        _,manifest,model=_load_model(pair.env['model_db'],scope,pair.env['artifacts'][company],lambda:scope)
        frame=build_from_snapshot(ReadOnlySnapshots(pair.env['snapshot_db']),scope,pair.env['queries'][company],pair.body(company)['as_of'])
        clear=model.score(np.asarray([row_values(frame,v,manifest['preprocess'])[0] for v in frame['features']]))
        np.testing.assert_allclose([r['score'] for r in result['rows']],clear,atol=ABS_TOLERANCE,rtol=REL_TOLERANCE)
        with closing(sqlite3.connect(pair.worker_root/'state/jobs.sqlite3')) as c:
            rows=c.execute('SELECT state,result,generation FROM jobs WHERE request_hash=?',(request_hash,)).fetchall()
        self.assertEqual(len(rows),1);self.assertEqual(rows[0][0],'done')
        self.assertEqual(rows[0][2],1 if stage=='committed' else 2)
        if cached is not None:self.assertEqual(rows[0][1],cached)
    def test_crash_after_claim_before_reservation(self):self.exercise('claimed')
    def test_crash_after_durable_nonce_reservation(self):self.exercise('reserved')
    def test_crash_after_native_compute_before_commit(self):self.exercise('computed','C002')
    def test_crash_after_result_commit_returns_identical_cached_ciphertext(self):self.exercise('committed')
    def test_worker_and_node_restart_preserve_same_private_context(self):self.exercise('reserved','C002',True)
    def test_second_process_cannot_steal_job_while_first_is_paused(self):
        pair=self.pair;marker,release=start_fault_worker(pair,'reserved')
        _,state=self.submit('C001','second-process-ownership');job=state['job_id'];self.wait_paused(marker)
        before=database_dump(pair.worker_root/'state/jobs.sqlite3')
        env=worker_environment();env['PYTHONPATH']=str(pair.bundle)
        cmd=[sys.executable,'-X','utf8','-B','-m','experiments.he_inference.worker_server','--config',str(pair.worker_config),'--port','0']
        result=subprocess.run(cmd,cwd=pair.bundle,env=env,capture_output=True,timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.assertNotEqual(result.returncode,0);self.assertIn(b'WORKER_STATE_IN_USE',result.stderr)
        self.assertEqual(before,database_dump(pair.worker_root/'state/jobs.sqlite3'))
        release.write_text('continue');self.assertEqual(self.wait_terminal('C001',job)['phase'],'completed')

    def interrupted_export(self):
        from experiments.he_inference import worker_server
        pair=self.pair;env=pair.env
        temp=tempfile.TemporaryDirectory(dir=pair.root);self.addCleanup(temp.cleanup)
        exported=export_snapshot(env['model_db'],env['snapshot_db'],env['auth'],env['header'],'C001',
            env['artifacts']['C001'],env['queries']['C001'],pair.body()['as_of'],public_hex(pair.worker_key))
        package=exported.cloud_package();p=package['request']['payload']
        worker=Worker(temp.name,pair.grants_file,pair.worker_key)
        try:
            worker.register(sign(dict(version='he-session-registration/1.0.0',node_verify_key=public_hex(pair.node_key),
                expires_at=p['expires_at'],policy=package['policy']),pair.node_key))
            original=worker_server.reserve
            def reserve_and_crash(*args,**kwargs):
                original(*args,**kwargs);raise SystemExit('test interrupt after reservation')
            with patch.object(worker_server,'reserve',side_effect=reserve_and_crash),self.assertRaises(SystemExit):
                worker.score(package['request'])
        finally:worker.close()
        return exported,package,Path(temp.name)

    def test_signed_changed_ciphertext_is_rejected_before_native_parse_on_retry(self):
        exported,package,folder=self.interrupted_export();packet=deepcopy(package['request'])
        packet['payload']['columns'][0]='AAAA';packet=sign(packet['payload'],exported._session.signer)
        with closing(Worker(folder,self.pair.grants_file,self.pair.worker_key)) as worker:
            with patch('experiments.he_inference.cloud_worker.ts.context_from',side_effect=AssertionError('must reject before native parse')):
                with self.assertRaises(ServiceError) as error:worker.score(packet)
            self.assertEqual(error.exception.code,'REQUEST_NONCE_CONFLICT')
            # This direct Worker unit runs inside the enterprise test process,
            # which intentionally has sklearn imported. Do not claim it meets
            # the subprocess boundary or pass it to enterprise.open. The six
            # real-process tests above verify full boundary/decryption/parity.
            response=verify(worker.score(package['request']),public_hex(self.pair.worker_key))
            self.assertEqual(response['request_sha256'],sha(canonical(package['request'])))
            self.assertEqual(worker.store.claim(package['request']['payload'],response['request_sha256'])[1],'done')

    def test_expired_pending_request_cannot_be_recomputed_on_restart(self):
        _,package,folder=self.interrupted_export();p=package['request']['payload']
        with closing(Worker(folder,self.pair.grants_file,self.pair.worker_key)) as worker:
            before=database_dump(worker.store.path)
            with patch('experiments.he_inference.worker_server.time.time',return_value=p['expires_at']+1):
                with self.assertRaises(ServiceError) as error:worker.score(package['request'])
            self.assertEqual(error.exception.code,'SESSION_EXPIRED')
            self.assertEqual(before,database_dump(worker.store.path))

    def test_current_grant_revocation_blocks_retry_without_changing_pending_state(self):
        _,package,folder=self.interrupted_export();grants=read_json(self.pair.grants_file)
        grants['grants'][0]['active']=False;self.pair.grants_file.write_bytes(canonical(grants))
        try:
            with closing(Worker(folder,self.pair.grants_file,self.pair.worker_key)) as worker:
                before=database_dump(worker.store.path)
                with self.assertRaises(ServiceError) as error:worker.score(package['request'])
                self.assertEqual(error.exception.code,'NODE_GRANT_DENIED')
                self.assertEqual(before,database_dump(worker.store.path))
        finally:self.pair.grants_file.write_bytes(self.grants)
