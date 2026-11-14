"""Real Portal-owned node/worker lifecycle, identity checks and preserved jobs."""
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT.parent)]
from test_portal_auth import PortalHarness
from portal import server as portal
from portal.agent2_runtime import stop_owned
from experiments.he_inference.services_demo import Pair
from experiments.he_inference.protocol import public_hex,sign,verify,read_json
from experiments.he_inference.readiness import probe
from experiments.he_inference.registry_demo import database_dump
from experiments.he_inference.http_common import post,ServiceError
from sme_fraud.import_files import digest


def free_port():
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


class ManagedHarness:
    def __enter__(self):
        self.stack=ExitStack();root=Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='managed-he-')))
        self.pair=Pair(root);self.stack.callback(self.pair.close)
        self.h=self.stack.enter_context(PortalHarness());self.h.agent.shutdown();self.h.agent.server_close()
        self.stack.enter_context(patch.object(portal,'HE_RUNTIME',None));self.stack.enter_context(patch.object(portal,'HE_RUNTIME_SETTINGS',None))
        self.port=self.h.agent.server_port;self.worker_port=free_port()
        while self.worker_port in (self.port,self.h.portal.server_port):self.worker_port=free_port()
        pair=self.pair
        self.node=pair.enterprise/'node.json'
        self.config=dict(version='he-enterprise-service/1.2.0',key_protection='windows-dpapi-current-user',
            auth_file=str(pair.env['policy']),model_db=str(pair.env['model_db']),snapshot_db=str(pair.env['snapshot_db']),
            worker_url=f'http://127.0.0.1:{self.worker_port}',worker_verify_key=public_hex(pair.worker_key),
            provisioning_key_file=str(pair.node_key_path),state_dir=str(pair.enterprise/'state'),state_key_file=str(pair.state_key_path))
        self.write_node()
        self.bindings=pair.enterprise/'bindings.json';self.bindings.write_text(json.dumps(dict(version='he-ui-bindings/1.0.0',bindings=[dict(tenant_id='demo',company_id=c,artifact_id=pair.env['artifacts'][c]) for c in ('C001','C002')])),encoding='utf-8')
        portal.CFG['agents']['agent2'].update(root=str(ROOT),python=sys.executable,port=self.port,
            snapshot_db=str(pair.env['snapshot_db']),model_db=str(pair.env['model_db']),
            env=dict(AGENT2_HE_NODE_CONFIG=str(self.node),AGENT2_HE_BINDINGS=str(self.bindings)),
            he_worker=dict(bundle=str(pair.bundle),config=str(pair.worker_config),port=self.worker_port))
        self.stack.callback(self.stop)
        return self
    def write_node(self):self.node.write_text(json.dumps(self.config),encoding='utf-8')
    def stop(self):
        if portal.PROCS.get('agent2') is not None or portal.HE_RUNTIME is not None:
            try:portal.stop_agent('agent2')
            except ValueError:
                if portal.HE_RUNTIME:portal.HE_RUNTIME.stop()
    def request(self,tail,body=None,**kwargs):return self.h.request(self.h.url('he/'+tail),body,**kwargs)
    def __exit__(self,*args):self.stack.close()


class ManagedWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.fixture=ManagedHarness().__enter__()
    @classmethod
    def tearDownClass(cls):cls.fixture.__exit__()
    def setUp(self):
        self.f=self.fixture;self.f.stop();self.original=dict(self.f.config)
    def tearDown(self):self.f.stop();self.f.config=self.original;self.f.write_node()
    def start(self):
        status,value=self.f.h.request('/api/agents/agent2/start',{});self.assertEqual(status,200,value)
        self.assertEqual(value['state'],'running');self.assertEqual(value['dependency']['status'],'ready');return value

    def test_start_stop_restart_preserves_models_keys_and_completed_results(self):
        f=self.f;before={k:database_dump(f.pair.env[k]) for k in ('model_db','snapshot_db')}
        keys=[f.pair.node_key_path.read_bytes(),f.pair.state_key_path.read_bytes()]
        self.start();worker=portal.HE_RUNTIME.process;node=portal.PROCS['agent2']
        self.assertTrue(f.request('datasets')[1]['worker_ready'])
        body=dict(snapshot_id=f.pair.env['queries']['C001']);headers={'Idempotency-Key':'managed-completed-request'}
        status,state=f.request('jobs',body,headers=headers);self.assertEqual(status,202,state)
        job=state['job_id'];deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            code,result=f.request('jobs/'+job+'/result')
            if code==200:break
            self.assertEqual(code,202,result);time.sleep(.1)
        self.assertEqual(code,200);self.assertEqual(result['row_count'],5)
        self.assertTrue(all(r['available'] for r in result['rows']))
        again=self.start();self.assertIs(portal.HE_RUNTIME.process,worker);self.assertIs(portal.PROCS['agent2'],node)
        f.stop();self.assertIsNotNone(worker.poll());self.assertIsNotNone(node.poll())
        self.assertFalse(portal.port_open(f.worker_port));self.assertFalse(portal.port_open(f.port))
        self.start();self.assertEqual(f.request('jobs/'+job+'/result')[1],result)
        self.assertEqual(f.request('jobs',body,headers=headers)[1]['job_id'],job)
        self.assertEqual(before,{k:database_dump(f.pair.env[k]) for k in before})
        self.assertEqual(keys,[f.pair.node_key_path.read_bytes(),f.pair.state_key_path.read_bytes()])

    def test_worker_loss_recover_keeps_pending_job_and_node(self):
        f=self.f;self.start();node=portal.PROCS['agent2']
        stop_owned(portal.HE_RUNTIME.process)
        catalog=f.request('datasets')[1];self.assertFalse(catalog['worker_ready']);self.assertFalse(catalog['available'])
        body=dict(snapshot_id=f.pair.env['queries']['C001']);headers={'Idempotency-Key':'managed-outage-pending'}
        _,state=f.request('jobs',body,headers=headers);job=state['job_id']
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            current=f.request('jobs/'+job)[1]
            if current['phase']=='retryable':break
            time.sleep(.1)
        self.assertEqual(current['phase'],'retryable')
        self.assertEqual(f.h.request('/api/agents/agent2/recover',{},token=False)[0],401)
        status,recovered=f.h.request('/api/agents/agent2/recover',{});self.assertEqual(status,200,recovered)
        self.assertIs(portal.PROCS['agent2'],node)
        f.request('jobs/'+job+'/resume',{})
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            code,result=f.request('jobs/'+job+'/result')
            if code==200:break
            self.assertEqual(code,202,result);time.sleep(.1)
        self.assertEqual(code,200);self.assertEqual(result['run_id'],job)
        self.assertEqual(f.request('jobs',body,headers=headers)[1]['job_id'],job)

    def test_wrong_pinned_worker_key_never_starts_node_and_rolls_back_worker(self):
        self.f.config['worker_verify_key']='0'*64;self.f.write_node()
        status,value=self.f.h.request('/api/agents/agent2/start',{})
        self.assertEqual(status,400,value);self.assertFalse(portal.port_open(self.f.port));self.assertFalse(portal.port_open(self.f.worker_port))
        self.assertIsNone(portal.PROCS.get('agent2'))

    def test_stop_start_preserves_pending_request_for_same_owner_resume(self):
        f=self.f;self.start();stop_owned(portal.HE_RUNTIME.process)
        body=dict(snapshot_id=f.pair.env['queries']['C001']);headers={'Idempotency-Key':'managed-stop-pending'}
        _,state=f.request('jobs',body,headers=headers);job=state['job_id']
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            phase=f.request('jobs/'+job)[1]['phase']
            if phase=='retryable':break
            time.sleep(.1)
        self.assertEqual(phase,'retryable');f.stop();self.start()
        self.assertEqual(f.request('jobs/'+job)[1]['phase'],'waiting_authorization')
        self.assertEqual(f.request('jobs',body,headers=headers)[1]['job_id'],job)
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            code,result=f.request('jobs/'+job+'/result')
            if code==200:break
            self.assertEqual(code,202,result);time.sleep(.1)
        self.assertEqual(code,200);self.assertEqual(result['run_id'],job)

    def test_invalid_dpapi_key_does_not_launch_services_or_overwrite_key(self):
        path=self.f.pair.state_key_path;original=path.read_bytes();path.write_bytes(b'not-a-key')
        try:
            status,_=self.f.h.request('/api/agents/agent2/start',{})
            self.assertEqual(status,400);self.assertEqual(path.read_bytes(),b'not-a-key')
            self.assertFalse(portal.port_open(self.f.port));self.assertFalse(portal.port_open(self.f.worker_port))
        finally:path.write_bytes(original)

    def test_external_occupied_worker_port_is_not_adopted_or_stopped(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1',self.f.worker_port));occupied.listen()
            status,_=self.f.h.request('/api/agents/agent2/start',{})
            self.assertEqual(status,400);self.assertIsNone(portal.HE_RUNTIME.process)
            self.assertTrue(portal.port_open(self.f.worker_port))

    def test_readiness_binds_fresh_challenge_scope_and_pinned_key_without_jobs(self):
        self.start();f=self.f
        from contextlib import closing
        import sqlite3
        with closing(sqlite3.connect(f.pair.worker_root/'state/jobs.sqlite3')) as conn:before=conn.execute('SELECT count(*) FROM jobs').fetchone()[0]
        self.assertTrue(probe(f'http://127.0.0.1:{f.worker_port}',public_hex(f.pair.worker_key),f.pair.node_key,'demo','C001'))
        with self.assertRaises(ServiceError):probe(f'http://127.0.0.1:{f.worker_port}','0'*64,f.pair.node_key,'demo','C001')
        with self.assertRaises(ServiceError):probe(f'http://127.0.0.1:{f.worker_port}',public_hex(f.pair.worker_key),f.pair.node_key,'demo','OTHER')
        with closing(sqlite3.connect(f.pair.worker_root/'state/jobs.sqlite3')) as conn:self.assertEqual(before,conn.execute('SELECT count(*) FROM jobs').fetchone()[0])


if __name__=='__main__':unittest.main()
