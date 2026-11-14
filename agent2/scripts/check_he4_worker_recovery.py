"""Actual HTTP FHE hard-crash recovery; isolated from live Portal services."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT.parent)]
from finance_input import AccessScope
from portal.agent2_he4_runtime import LinuxRuntime,linux_path
from experiments.he4.bundle import build
from experiments.he4.windows_bridge import CryptoBridge
from experiments.he4.client_transport import envelope,upload,download
from experiments.he4.blob_store import BlobStore
from experiments.he_inference.protocol import canonical,sign,verify,sha,public_hex
from experiments.he_inference.http_common import post
from experiments.he_inference.key_manager import create_key


def run(output,prepared,builds,port):
    if output.exists():raise ValueError('new recovery evidence directory required')
    output.mkdir(parents=True);start=time.monotonic();build(output/'bundle')
    key=create_key(output/'node-signing.dpapi.json',purpose='node-signing');node_key=Ed25519PrivateKey.from_private_bytes(key.material)
    cloud_key=Ed25519PrivateKey.generate();(output/'cloud-signing.hex').write_text(cloud_key.private_bytes_raw().hex())
    scope=AccessScope('he4-acceptance',frozenset({'C001'}),'operator',frozenset({'data.import','model.fit'}))
    (output/'grants.json').write_bytes(canonical(dict(version='he-worker-grants/1.0.0',grants=[dict(tenant_id=scope.tenant_id,company_id='C001',node_verify_key=public_hex(node_key),active=True)])))
    config=output/'worker.json';config.write_bytes(canonical(dict(version='he4-worker/0.1.0',state_dir=linux_path(output/'cloud'),grants_file=linux_path(output/'grants.json'),signing_key_file=linux_path(output/'cloud-signing.hex'),builds={k:linux_path(v) for k,v in builds.items()})))
    worker=dict(bundle=str(output/'bundle'),config=str(config),port=port,distro='Debian',python='/home/sang/.local/share/agent2/he4/bin/python')
    runtime=LinuxRuntime(worker,ROOT,prepared/'unused-node.json',prepared/'unused-config.json',ROOT/'.venv/Scripts/python.exe',output/'logs')
    # This fixture tests supervisor ownership; DPAPI/native-context verification
    # is performed by the actual bridge below, not a fake preflight result.
    runtime.preflight=lambda keys_only=False:None
    bridge=CryptoBridge(prepared/'private',prepared/'wrapping.dpapi.json');stats=builds['statistics']
    context=bridge.encrypt(scope,stats,[[-123,456]],output/'encrypted')
    url=f'http://127.0.0.1:{port}';error=[]
    try:
        runtime.start()
        upload(url,scope,node_key,public_hex(cloud_key),bridge.public_key(scope,stats),'public_evaluation_keys')
        upload(url,scope,node_key,public_hex(cloud_key),output/'encrypted/argument-0.cipher','ciphertext')
        circuit=json.loads((stats/'manifest.json').read_bytes())['files']['server.zip']
        payload=envelope(scope,node_key,dict(profile='statistics',circuit_sha256=circuit,evaluation_keys_sha256=context['evaluation_keys_sha256'],arguments_sha256=context['arguments_sha256'],session_id='recovery',nonce='same-request'))['payload']
        payload['expires_at']=int(time.time())+10;packet=sign(payload,node_key)
        def submit():
            try:post(url,'/v1/evaluate',packet,timeout=600)
            except Exception as e:error.append(type(e).__name__)
        thread=threading.Thread(target=submit);thread.start()
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            if list((output/'cloud').glob('attempt_*/native.started')):break
            if not thread.is_alive():raise AssertionError('request ended before native crash injection')
            time.sleep(.1)
        else:raise AssertionError('native compute marker not reached')
        while time.time()<=payload['expires_at']:time.sleep(.1)
        command=['wsl.exe','-d','Debian','--cd',linux_path(output/'bundle'),'--exec',worker['python'],'-B','-m','experiments.he4.runner','--config',linux_path(config),'--port',str(port),'--kill-owned']
        killed=subprocess.run(command,input=canonical(dict(token=runtime.token))+b'\n',stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
        if killed.returncode:raise AssertionError('owned SIGKILL rejected')
        thread.join(20)
        if thread.is_alive() or not error:raise AssertionError('lost computation not observed')
        runtime.stop();runtime.start()
        response=post(url,'/v1/resume',envelope(scope,node_key,dict(request=packet)),timeout=600)
        signed=verify(response,public_hex(cloud_key))
        if signed['request_sha256']!=sha(canonical(packet)):raise AssertionError('request changed')
        download(url,scope,node_key,signed['result_sha256'],output/'result.cipher')
        value=CryptoBridge(prepared/'private',prepared/'wrapping.dpapi.json').decrypt(scope,stats,output/'result.cipher',signed['result_sha256'],output/'opened.sealed',context)
        if value!=579:raise AssertionError('recovered score mismatch')
        retrieval=envelope(scope,node_key,dict(session_id='recovery',nonce='same-request',request_sha256=sha(canonical(packet))))
        if post(url,'/v1/results',retrieval)!=response:raise AssertionError('cache changed')
        import sqlite3
        with sqlite3.connect(output/'cloud/state/jobs.sqlite3') as conn:
            jobs=conn.execute('SELECT state,generation FROM jobs').fetchall()
        if jobs!=[('done',2)]:raise AssertionError(jobs)
        report=dict(actual_fhe=True,authenticated_http=True,sigkill_during_native_compute=True,admission_ttl_elapsed=True,fresh_resume_same_envelope=True,same_dpapi_private_context=True,score=579,logical_jobs=1,attempts=2,committed_result_reused=True,supervisor_start_stop=True,supervisor_preflight_mocked=True,seconds=time.monotonic()-start)
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
    finally:runtime.stop()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--build-root',type=Path,required=True);p.add_argument('--port',type=int,default=8869);a=p.parse_args()
    run(a.output.resolve(),a.prepared.resolve(),{name:(a.build_root/path).resolve() for name,path in {'statistics':'build-statistics-v1','graph':'build-graph-difference-v1','rules':'build-rules-difference-v1'}.items()},a.port)
