"""Ciphertext-only HTTP worker for a fixed encrypted logistic training program.

The worker bundle contains this module, protocol/store, public circuit/evaluation
keys and the worker's own signing key. Never include enterprise key material.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from .protocol import strict_json,canonical,require,TrainingError,MAX_PACKET,atomic,sha
from .store import CloudStore


class NativeEvaluator:
    def __init__(self,build,grants):
        from concrete import fhe
        self.fhe=fhe;self.build=Path(build);self.grants=grants
        self.manifest=json.loads((self.build/'manifest.json').read_bytes())
        require(self.manifest.get('all_inputs_encrypted') is True and self.manifest.get('composable') is True,'BUILD_NOT_ENCRYPTED')
        for name,digest in self.manifest['files'].items():require(sha((self.build/name).read_bytes())==digest,'BUILD_TAMPERED')
        self.server=fhe.Server.load(self.build/'server.zip');self.keys={}

    def __call__(self,x,y,weights,body):
        owner=(body['tenant_id'],body['company_id']);grant=self.grants[owner]
        if owner not in self.keys:
            raw=Path(grant['evaluation_keys_file']).read_bytes();require(sha(raw)==grant['evaluation_keys_sha256'],'EVALUATION_KEYS_TAMPERED')
            self.keys[owner]=self.fhe.EvaluationKeys.deserialize(raw)
        values=[self.fhe.Value.deserialize(raw) for raw in (x,y,weights)]
        return self.server.run(*values,evaluation_keys=self.keys[owner]).serialize()


def make_server(port,store,batch_store=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_POST(self):
            try:
                require(self.headers.get_all('Host') in ([f'127.0.0.1:{self.server.server_port}'],[f'localhost:{self.server.server_port}']),'HOST_DENIED')
                require(not self.headers.get_all('Origin') and not self.headers.get_all('Transfer-Encoding'),'TRANSPORT_DENIED')
                require(self.headers.get_all('Content-Type')==['application/json'],'JSON_REQUIRED')
                sizes=self.headers.get_all('Content-Length',[]);require(len(sizes)==1 and sizes[0].isascii() and sizes[0].isdigit(),'LENGTH_REQUIRED')
                size=int(sizes[0]);require(0<size<=MAX_PACKET,'PACKET_LIMIT');raw=self.rfile.read(size);require(len(raw)==size,'BODY_INCOMPLETE');packet=strict_json(raw)
                if self.path=='/v1/datasets':result=store.upload(packet)
                elif self.path=='/v1/confirm':result=store.confirm(packet)
                elif self.path=='/v1/jobs':result=store.access(packet)
                elif self.path in ('/v2/datasets','/v2/confirm','/v2/jobs'):
                    require(batch_store is not None,'BATCH_TRAINING_NOT_CONFIGURED')
                    result={'/v2/datasets':batch_store.upload,'/v2/confirm':batch_store.confirm,'/v2/jobs':batch_store.access}[self.path](packet)
                else:raise TrainingError('ROUTE_NOT_FOUND')
                status=200
            except TrainingError as error:status=409;result=dict(error=error.code)
            except Exception:status=503;result=dict(error='TRAINING_WORKER_UNAVAILABLE')
            body=canonical(result);self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('Connection','close');self.end_headers()
            try:self.wfile.write(body)
            except OSError:pass
        def setup(self):super().setup();self.connection.settimeout(600)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True;return server


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--port',type=int,default=0);p.add_argument('--ready',type=Path,required=True);a=p.parse_args()
    cfg=strict_json(a.config.read_bytes());grants={(g['tenant_id'],g['company_id']):g for g in cfg['grants']}
    key=Ed25519PrivateKey.from_private_bytes(bytes.fromhex(Path(cfg['worker_signing_key']).read_text().strip()))
    evaluator=NativeEvaluator(cfg['build'],grants)
    store=CloudStore(cfg['state'],grants,key,evaluator.manifest['files']['server.zip'],evaluator)
    batches=None
    if cfg.get('batch_training') is True:
        from .batch_store import BatchCloudStore
        batches=BatchCloudStore(Path(cfg['state'])/'batch',grants,key,evaluator.manifest['files']['server.zip'],evaluator,max_updates=evaluator.manifest['max_steps'])
    server=make_server(a.port,store,batches);atomic(a.ready,canonical(dict(port=server.server_port,pid=os.getpid(),worker_verify_key=key.public_key().public_bytes_raw().hex())))
    print('Encrypted training worker ready',flush=True);server.serve_forever()


if __name__=='__main__':main()
