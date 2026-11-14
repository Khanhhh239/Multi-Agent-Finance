"""Terminate the real DN coordinator during native HTTP computation, then resume.

Synthetic isolated fixture, real encrypted worker and persisted private keys.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT.parent)]
from portal.agent2_he4_runtime import LinuxRuntime,linux_path
from experiments.he4.bundle import build
from experiments.he4.coordinator import FourJobs,Settings
from experiments.he_inference.enterprise_server import load_node
from experiments.he_inference.services_demo import Pair
from experiments.he_inference.registry_demo import commit,source_for
from experiments.he_inference.protocol import canonical,sha,public_hex
from sme_fraud.method_jobs import run_fit_job


def child(config,four,snapshot,artifact,receipt):
    header=json.loads(sys.stdin.buffer.readline())['authorization']
    node=load_node(json.loads(config.read_bytes()));node.jobs=FourJobs(node,Settings(json.loads(four.read_bytes())))
    try:
        scope=node.auth.authorize(header,'C001')
        from experiments.he_inference.registry_export import ReadOnlySnapshots
        manifest=ReadOnlySnapshots(node.snapshot_db).get_snapshot(scope,snapshot)
        job=node.jobs.submit('C001',header,'coordinator-crash-fixed-request',dict(snapshot_id=snapshot,artifact_id=artifact,as_of=manifest['created_at']))['job_id']
        receipt.write_bytes(canonical(dict(job_id=job)))
        while True:
            status=node.jobs.status('C001',header,job)
            if status['phase'] in ('completed','failed','expired'):raise AssertionError('did not inject crash before completion')
            time.sleep(.2)
    finally:node.jobs.close()


def run(output,prepared,builds):
    if output.exists():raise ValueError('new evidence directory required')
    output.mkdir(parents=True);started=time.monotonic()
    (output/'fixture').mkdir()
    with closing(Pair(output/'fixture',state_key_file=prepared/'wrapping.dpapi.json').start()) as pair:
        pair._stop(pair.node_process)
        env=pair.env;scope=env['auth'].authorize(env['fit_header'],'C001')
        source=source_for('C001','query');source['transactions']=source['transactions'][:1];source['payment_allocations']=source['payment_allocations'][:1]
        snapshot=commit(env['snapshots'],scope,source,'single-query-native-restart')
        cfg=dict(env['configs']['C001'],version='company-fit-config/1.0.0',method_id='robust_z',profile_id='technical-restart-fixture')
        fit=run_fit_job(env['snapshots'],env['models'],env['auth'],env['fit_header'],'C001',cfg,'fit-real-coordinator-statistics')
        if fit.get('error'):raise AssertionError(fit)
        (output/'bindings.json').write_bytes(canonical(dict(version='he4-company-bindings/1.0.0',bindings=[dict(tenant_id='demo',company_id='C001',statistics_artifact_id=fit['job']['artifact_id'])])))
        cloud=output/'cloud';cloud.mkdir();build(cloud/'bundle');key=Ed25519PrivateKey.generate();(cloud/'signing.hex').write_text(key.private_bytes_raw().hex())
        (cloud/'grants.json').write_bytes(canonical(pair.grants));worker=cloud/'worker.json'
        worker.write_bytes(canonical(dict(version='he4-worker/0.1.0',state_dir=linux_path(cloud/'state'),grants_file=linux_path(cloud/'grants.json'),signing_key_file=linux_path(cloud/'signing.hex'),builds={k:linux_path(v) for k,v in builds.items()})))
        with socket.socket() as free:free.bind(('127.0.0.1',0));port=free.getsockname()[1]
        config=dict(version='he4-enterprise/1.0.0',state_dir=str(output/'jobs'),enterprise_root=str(prepared/'private'),state_key_file=str(pair.state_key_path),worker_url=f'http://127.0.0.1:{port}',worker_verify_key=public_hex(key),builds={k:str(v) for k,v in builds.items()},bindings_file=str(output/'bindings.json'),linux_distro='Debian',linux_python='/home/sang/.local/share/agent2/he4/bin/python')
        (output/'node-four.json').write_bytes(canonical(config))
        runtime=LinuxRuntime(dict(bundle=str(cloud/'bundle'),config=str(worker),port=port,distro='Debian',python=config['linux_python']),ROOT,pair.node_config,output/'node-four.json',Path(sys.executable),output/'logs')
        runtime.preflight=lambda keys_only=False:None
        process=None;node=None
        try:
            runtime.start()
            with (output/'coordinator.log').open('ab') as log:
                command=[sys.executable,'-B',str(Path(__file__).resolve()),'--child','--node',str(pair.node_config),'--four',str(output/'node-four.json'),'--snapshot',snapshot,'--artifact',env['artifacts']['C001'],'--receipt',str(output/'receipt.json')]
                process=subprocess.Popen(command,cwd=ROOT,stdin=subprocess.PIPE,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
                process.stdin.write(canonical(dict(authorization=env['header']))+b'\n');process.stdin.close()
            end=time.monotonic()+180
            while time.monotonic()<end:
                if list((cloud/'state').glob('attempt_*/native.started')):break
                if process.poll() is not None:raise AssertionError('coordinator ended before injection')
                time.sleep(.2)
            else:raise AssertionError('native computation not reached')
            process.kill();process.wait(15)  # Windows TerminateProcess, no cleanup callback.
            receipt=json.loads((output/'receipt.json').read_bytes());job=receipt['job_id']
            node=load_node(json.loads(pair.node_config.read_bytes()));node.jobs=FourJobs(node,Settings(config),workers=0)
            scope=node.auth.authorize(env['header'],'C001');row,data=node.jobs.store.get(scope,job)
            if row['phase']!='waiting_authorization':raise AssertionError('missing restart auth fence')
            task=next(t for t in data['pending']['tasks'] if t['packet']);packet_hash=sha(canonical(task['packet']));private_context=sha(canonical(task['context']));child_id=data['legacy_job']
            node.jobs.resume('C001',env['header'],job)
            end=time.monotonic()+900
            while time.monotonic()<end:
                again=node.jobs._process(scope,job)
                status=node.jobs.status('C001',env['header'],job)
                if status['phase']=='completed':break
                if not again:raise AssertionError(status)
                time.sleep(.5)
            else:raise AssertionError('resume did not finish')
            status,result=node.jobs.result('C001',env['header'],job)
            if status!=200 or result['row_count']!=1 or set(result['rows'][0]['branches'])!={'rules','statistics','graph','ml'}:raise AssertionError('incomplete result')
            if not all(result['rows'][0]['branches'][p]['available'] for p in ('statistics','graph','ml')):raise AssertionError('native branches unavailable')
            _,final=node.jobs.store.get(scope,job)
            if final['legacy_job']!=child_id:raise AssertionError('ML child duplicated')
            # The immutable encrypted request/argument files survived the crash.
            # A completed job deliberately clears the temporary plan; its worker
            # request hash remains in the durable worker store.
            import sqlite3
            with sqlite3.connect(cloud/'state/state/jobs.sqlite3') as conn:
                requests=conn.execute('SELECT request_hash,state,generation FROM jobs').fetchall()
            if not any(r[0]==packet_hash and r[1]=='done' and r[2]==1 for r in requests):raise AssertionError('accepted envelope was replaced/recomputed')
            if len(requests)!=2:raise AssertionError('unexpected concrete logical jobs')
            report=dict(actual_fhe=True,authenticated_http=True,coordinator_terminated_during_native_compute=True,same_admitted_envelope=True,same_saved_private_context=True,private_context_hash=private_context,one_parent_job=True,same_ml_child=True,all_four_statuses=True,concrete_logical_jobs=len(requests),supervisor_preflight_mocked=True,simulated_data=True,seconds=time.monotonic()-started)
            (output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
        finally:
            if process and process.poll() is None:process.kill();process.wait(15)
            if node:node.jobs.close()
            runtime.stop()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--child',action='store_true');p.add_argument('--node',type=Path);p.add_argument('--four',type=Path);p.add_argument('--snapshot');p.add_argument('--artifact');p.add_argument('--receipt',type=Path);p.add_argument('--output',type=Path);p.add_argument('--prepared',type=Path);p.add_argument('--build-root',type=Path);a=p.parse_args()
    if a.child:child(a.node,a.four,a.snapshot,a.artifact,a.receipt)
    else:run(a.output.resolve(),a.prepared.resolve(),{k:(a.build_root/v).resolve() for k,v in dict(statistics='build-statistics-v1',rules='build-rules-difference-v1',graph='build-graph-difference-v1').items()})
