"""Opt-in loopback FHE worker with signed requests and separate blob transport.

Operator-pinned circuits only; the worker never accepts a client program,
plaintext input, model pickle, or secret key. This service is not public TLS.
"""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from experiments.he_inference.protocol import canonical,sha,sign,verify,public_hex,read_json,HEUnavailable,identifier
from experiments.he_inference.http_common import Handler,LocalServer,ServiceError,decode
from experiments.he_inference.worker_store import WorkerStore
from .blob_store import BlobStore,HASH
from . import VERSION,FRESH_ADMISSION


def grants(path):
    value=read_json(path)
    if not isinstance(value,dict) or set(value)!={'version','grants'} or value['version']!='he-worker-grants/1.0.0' or not isinstance(value['grants'],list) or len(value['grants'])>256:raise ServiceError(503,'GRANTS_UNAVAILABLE')
    result=set()
    for row in value['grants']:
        if not isinstance(row,dict) or set(row)!={'tenant_id','company_id','node_verify_key','active'} or not all(identifier(row[k]) for k in ('tenant_id','company_id')) or not isinstance(row['node_verify_key'],str) or not HASH.fullmatch(row['node_verify_key']) or type(row['active']) is not bool:raise ServiceError(503,'GRANTS_UNAVAILABLE')
        if row['active']:result.add((row['tenant_id'],row['company_id'],row['node_verify_key']))
    return result


class Worker:
    def __init__(self,state,grants_file,key,builds):
        self.state=Path(state).resolve();self.state.mkdir(parents=True,exist_ok=True)
        self.store=WorkerStore(self.state/'state');self.blobs=BlobStore(self.state/'blobs')
        self.grants_file=Path(grants_file);self.key=key;self.builds={};self.slots=threading.BoundedSemaphore(1)
        self.idle=threading.Condition();self.active=0;self.closing=False
        for profile,path in builds.items():
            if profile not in {'rules','statistics','graph','c3'}:raise ValueError('unsupported profile')
            root=Path(path).resolve();manifest=read_json(root/'manifest.json')
            if manifest['profile']!=profile or manifest['version']!='he4-circuit-build/0.1.0':raise ValueError('build profile')
            for name in ('server.zip','client.specs.json'):
                if BlobStore.digest(root/name)!=manifest['files'][name]:raise ValueError('build hash')
            self.builds[profile]=(root,manifest['files']['server.zip'])
        grants(self.grants_file)

    def close(self):
        with self.idle:
            self.closing=True
            while self.active:self.idle.wait(.2)
            self.store.close()

    def authenticate(self,packet,fields,*,check_expiry=True):
        p=packet.get('payload') if isinstance(packet,dict) else None
        common={'version','tenant_id','company_id','node_verify_key','expires_at'}
        if not isinstance(p,dict) or set(p)!=common|set(fields) or p['version']!=VERSION:raise ServiceError(400,'HE4_FIELDS')
        if not all(identifier(p[k]) for k in ('tenant_id','company_id')) or not isinstance(p['node_verify_key'],str) or not HASH.fullmatch(p['node_verify_key']):raise ServiceError(400,'HE4_IDENTITY')
        if (p['tenant_id'],p['company_id'],p['node_verify_key']) not in grants(self.grants_file):raise ServiceError(403,'NODE_GRANT_DENIED')
        verify(packet,p['node_verify_key'])
        if type(p['expires_at']) is not int or p['expires_at']<=0 or check_expiry and not int(time.time())<p['expires_at']<=int(time.time())+300:raise ServiceError(410,'HE4_EXPIRED')
        return p

    def upload(self,packet,size,stream):
        p=self.authenticate(packet,{'sha256','size','purpose'})
        if p['purpose'] not in {'public_evaluation_keys','ciphertext'} or type(p['size']) is not int or p['size']!=size:raise ServiceError(400,'HE4_BLOB_FIELDS')
        if p['purpose']=='ciphertext' and size>64*1024**2:raise ServiceError(413,'CIPHERTEXT_LIMIT')
        scope=self.blobs.scope(p['tenant_id'],p['company_id'],p['node_verify_key'])
        self.blobs.put(scope,p['sha256'],size,stream,lambda:self.authenticate(packet,{'sha256','size','purpose'}))
        return sign(dict(status='stored',sha256=p['sha256'],tenant_id=p['tenant_id'],company_id=p['company_id']),self.key)

    def blob_status(self,packet):
        p=self.authenticate(packet,{'sha256'})
        scope=self.blobs.scope(p['tenant_id'],p['company_id'],p['node_verify_key'])
        path=self.blobs.get(scope,p['sha256'])
        return sign(dict(status='stored',sha256=p['sha256'],size=path.stat().st_size,tenant_id=p['tenant_id'],company_id=p['company_id']),self.key)

    def readiness(self,packet):
        p=self.authenticate(packet,{'challenge'})
        if not isinstance(p['challenge'],str) or not HASH.fullmatch(p['challenge']):raise ServiceError(400,'READINESS_CHALLENGE')
        return sign(dict(p,worker_verify_key=public_hex(self.key),builds={k:v[1] for k,v in self.builds.items()}),self.key)

    def defer(self,p,request_hash,attempt):
        key=tuple(p[k] for k in ('tenant_id','company_id','session_id','nonce'))
        with self.store.transaction() as conn:
            self.store._owned(conn,key,request_hash,attempt)
            conn.execute("UPDATE jobs SET state='retryable',attempt=NULL WHERE tenant=? AND company=? AND session=? AND nonce=?",key)

    def score(self,packet,*,resuming=False,fresh_admission=False):
        fields={'profile','circuit_sha256','evaluation_keys_sha256','arguments_sha256','session_id','nonce'}
        # An expired inner packet needs a distinct, fresh node-signed admission
        # capability. Existing evaluate/resume contracts remain unchanged.
        p=self.authenticate(packet,fields,check_expiry=not (resuming or fresh_admission))
        if not all(identifier(p[k]) for k in ('session_id','nonce')):raise ServiceError(400,'HE4_REQUEST_ID')
        build=self.builds.get(p['profile'])
        if not build or p['circuit_sha256']!=build[1]:raise ServiceError(409,'HE4_CIRCUIT_INCOMPATIBLE')
        if not isinstance(p['arguments_sha256'],list) or len(p['arguments_sha256'])!={'rules':6,'graph':3,'statistics':1,'c3':10}[p['profile']]:raise ServiceError(400,'HE4_ARGUMENTS')
        if not all(isinstance(h,str) and HASH.fullmatch(h) for h in [p['evaluation_keys_sha256'],*p['arguments_sha256']]):raise ServiceError(400,'HE4_BLOB_HASH')
        scope=self.blobs.scope(p['tenant_id'],p['company_id'],p['node_verify_key'])
        paths=[self.blobs.get(scope,h) for h in [p['evaluation_keys_sha256'],*p['arguments_sha256']]]
        request_hash=sha(canonical(packet))
        if resuming:
            session=self.store.session(p['tenant_id'],p['company_id'],p['session_id'])
            if session['node_key']!=p['node_verify_key']:raise ServiceError(403,'RESULT_OWNER_MISMATCH')
            with self.store.transaction() as conn:
                old=conn.execute('SELECT request_hash FROM jobs WHERE tenant=? AND company=? AND session=? AND nonce=?',(p['tenant_id'],p['company_id'],p['session_id'],p['nonce'])).fetchone()
            if old is None or old['request_hash']!=request_hash:raise ServiceError(409,'HE4_REQUEST_NOT_ADMITTED')
        else:
            self.store.register(p['tenant_id'],p['company_id'],p['session_id'],p['node_verify_key'],p['expires_at'],
                {k:p[k] for k in ('profile','circuit_sha256','evaluation_keys_sha256')})
        # Persist admission before returning BUSY. A fresh signed resume may
        # later continue this exact hash even after its admission TTL elapsed.
        cached,state,attempt=self.store.claim(p,request_hash)
        if state not in ('new','resume'):
            self.authenticate(packet,fields,check_expiry=False)
            if state=='failed':raise ServiceError(422,'HE4_EVALUATION_FAILED')
            return cached
        if not self.slots.acquire(blocking=False):
            self.defer(p,request_hash,attempt);raise ServiceError(503,'WORKER_BUSY')
        with self.idle:
            if self.closing:self.defer(p,request_hash,attempt);self.slots.release();raise ServiceError(503,'WORKER_CLOSING')
            self.active+=1
        try:
            root=self.state/('attempt_'+attempt)
            # Attempts use distinct directories: an orphaned old native process
            # cannot overwrite output from a newly fenced recovery attempt.
            try:
                root.mkdir()
                for i,path in enumerate(paths):
                    (root/('evaluation.keys' if i==0 else f'argument-{i-1}.cipher')).hardlink_to(path)
                request={k:p[k] for k in ('circuit_sha256','evaluation_keys_sha256','arguments_sha256')};request['version']='he4-native-request/0.1.0'
                (root/'request.json').write_bytes(canonical(request))
            except OSError:
                self.defer(p,request_hash,attempt)
                if root.is_dir() and root.parent==self.state:shutil.rmtree(root)
                raise ServiceError(503,'HE4_STORAGE_UNAVAILABLE') from None
            try:
                subprocess.run([sys.executable,'-m','experiments.he4.public_worker','--bundle',str(build[0]),'--request',str(root),'--circuit-sha256',build[1]],check=True,timeout=600,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                output=root/'result.cipher';digest=BlobStore.digest(output)
                with output.open('rb') as stream:self.blobs.put(scope,digest,output.stat().st_size,stream,lambda:self.authenticate(packet,fields,check_expiry=False))
                result=sign(dict(version=VERSION,tenant_id=p['tenant_id'],company_id=p['company_id'],session_id=p['session_id'],nonce=p['nonce'],request_sha256=request_hash,result_sha256=digest,circuit_sha256=build[1]),self.key)
                self.store.finish(p,request_hash,attempt,result,'done')
                self.authenticate(packet,fields,check_expiry=False);return result
            except Exception:
                # A rejected native execution never becomes a plaintext fall-
                # back or success. A hard process death is recovered by store.
                with self.store.transaction() as conn:
                    row=conn.execute('SELECT state FROM jobs WHERE tenant=? AND company=? AND session=? AND nonce=?',(p['tenant_id'],p['company_id'],p['session_id'],p['nonce'])).fetchone()
                if row and row['state']=='running':self.store.finish(p,request_hash,attempt,dict(reason='HE4_EVALUATION_FAILED'),'failed')
                raise
            finally:
                # Only generated fixed attempt directory beneath state is removed.
                if root.parent==self.state and root.name=='attempt_'+attempt:shutil.rmtree(root)
        finally:
            with self.idle:self.active-=1;self.idle.notify_all()
            self.slots.release()

    def retrieve(self,packet):
        fields={'session_id','nonce','request_sha256'};p=self.authenticate(packet,fields)
        if not all(identifier(p[k]) for k in ('session_id','nonce')) or not isinstance(p['request_sha256'],str) or not HASH.fullmatch(p['request_sha256']):raise ServiceError(400,'HE4_RETRIEVAL_FIELDS')
        session=self.store.session(p['tenant_id'],p['company_id'],p['session_id'])
        if session['node_key']!=p['node_verify_key']:raise ServiceError(403,'RESULT_OWNER_MISMATCH')
        result=self.store.retrieve(p);self.authenticate(packet,fields);return result

    def resume(self,packet):
        p=self.authenticate(packet,{'request'})
        original=p['request'].get('payload') if isinstance(p['request'],dict) else None
        if not isinstance(original,dict) or any(original.get(k)!=p[k] for k in ('tenant_id','company_id','node_verify_key')):raise ServiceError(403,'HE4_RESUME_OWNER')
        return self.score(p['request'],resuming=True)

    def admit(self,packet):
        """Fresh authorization for the exact saved packet, including its hash.

        A client may pause before worker admission and return after the inner
        packet expires. Keep that packet and ciphertext intact; the fresh,
        domain-separated wrapper supplies admission authority. Register/claim
        still fence conflicting session policy, nonce, and request hashes.
        """
        p=self.authenticate(packet,{'request','purpose'})
        if p['purpose']!=FRESH_ADMISSION:raise ServiceError(400,'HE4_ADMISSION_PURPOSE')
        original=p['request'].get('payload') if isinstance(p['request'],dict) else None
        if not isinstance(original,dict) or any(original.get(k)!=p[k] for k in ('tenant_id','company_id','node_verify_key')):raise ServiceError(403,'HE4_ADMISSION_OWNER')
        return self.score(p['request'],fresh_admission=True)

    def download(self,packet):
        p=self.authenticate(packet,{'sha256'})
        scope=self.blobs.scope(p['tenant_id'],p['company_id'],p['node_verify_key'])
        path=self.blobs.get(scope,p['sha256'])
        if path.stat().st_size>64*1024**2:raise ServiceError(413,'RESULT_DOWNLOAD_LIMIT')
        return path


def make_server(port,worker):
    class API(Handler):
        def do_GET(self):
            try:
                self.guard()
                if self.path!='/health':raise ServiceError(404,'ROUTE_NOT_FOUND')
                self.reply(200,dict(version=VERSION,role='ciphertext_worker',profiles=sorted(worker.builds),response_verify_key=public_hex(worker.key)))
            except ServiceError as e:self.failure(e)
        def do_POST(self):
            try:
                self.guard()
                if self.path=='/v1/blobs':
                    values=self.headers.get_all('X-HE-Envelope',[]);lengths=self.headers.get_all('Content-Length',[])
                    if len(values)!=1 or len(values[0])>8192 or len(lengths)!=1 or not lengths[0].isascii() or not lengths[0].isdigit() or self.headers.get_all('Transfer-Encoding',[]) or self.headers.get_all('Content-Encoding',[]):raise ServiceError(400,'UPLOAD_HEADERS')
                    if self.headers.get_all('Content-Type',[])!=['application/octet-stream']:raise ServiceError(415,'BINARY_REQUIRED')
                    packet=decode(base64.b64decode(values[0],validate=True));self.connection.settimeout(60)
                    self.reply(200,worker.upload(packet,int(lengths[0]),self.rfile));return
                if self.path not in {'/v1/evaluate','/v1/blobs/read','/v1/blobs/check','/v1/results','/v1/resume','/v1/admit','/v1/readiness'}:raise ServiceError(404,'ROUTE_NOT_FOUND')
                packet=self.body(16384)
                if self.path=='/v1/evaluate':self.reply(200,worker.score(packet));return
                if self.path=='/v1/resume':self.reply(200,worker.resume(packet));return
                if self.path=='/v1/admit':self.reply(200,worker.admit(packet));return
                if self.path=='/v1/results':self.reply(200,worker.retrieve(packet));return
                if self.path=='/v1/blobs/check':self.reply(200,worker.blob_status(packet));return
                if self.path=='/v1/readiness':self.reply(200,worker.readiness(packet));return
                path=worker.download(packet);self.send_response(200);self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Length',str(path.stat().st_size));self.send_header('Cache-Control','no-store');self.end_headers();self.close_connection=True
                with path.open('rb') as stream:shutil.copyfileobj(stream,self.wfile,1024*1024)
            except ServiceError as e:self.failure(e)
            except HEUnavailable as e:self.failure(ServiceError(403,e.code))
            except Exception:self.failure(ServiceError(503,'HE4_WORKER_UNAVAILABLE'))
    return LocalServer(port,API)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,required=True);parser.add_argument('--port',type=int,default=8869);args=parser.parse_args()
    if importlib.util.find_spec('sme_fraud') is not None or importlib.util.find_spec('experiments.he_inference.enterprise') is not None:raise SystemExit('HE4_WORKER_BUNDLE_REQUIRED')
    config=read_json(args.config)
    if set(config)!={'version','state_dir','grants_file','signing_key_file','builds'} or config['version']!=VERSION:raise ValueError('config')
    key=Ed25519PrivateKey.from_private_bytes(bytes.fromhex(Path(config['signing_key_file']).read_text().strip()))
    worker=Worker(config['state_dir'],config['grants_file'],key,config['builds']);server=make_server(args.port,worker)
    try:server.serve_forever()
    finally:server.server_close();worker.close()


if __name__=='__main__':main()
