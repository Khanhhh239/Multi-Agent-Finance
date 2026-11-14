"""Experimental ciphertext-only loopback service; no enterprise imports or DBs."""
import argparse
import importlib.util
from pathlib import Path
import re
import threading
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .cloud_worker import evaluate,reserve
from .http_common import Handler, LocalServer, ServiceError
from .protocol import (BINDING, CONTRACT, PROFILE, VERSION, HEUnavailable, canonical,
                       identifier, public_hex, read_json, sha, sign, verify)
from .worker_store import WorkerStore

REGISTRATION = 'he-session-registration/1.0.0'


def grants(path):
    value = read_json(path)
    if not isinstance(value, dict) or set(value) != {'version', 'grants'} or value['version'] != 'he-worker-grants/1.0.0':
        raise ServiceError(503, 'GRANTS_UNAVAILABLE')
    rows = value['grants']
    if not isinstance(rows, list) or len(rows) > 64:
        raise ServiceError(503, 'GRANTS_UNAVAILABLE')
    allowed = set()
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'tenant_id', 'company_id', 'node_verify_key', 'active'}
                or not all(identifier(row[k]) for k in ('tenant_id', 'company_id'))
                or not isinstance(row['node_verify_key'], str) or not re.fullmatch('[a-f0-9]{64}', row['node_verify_key'])
                or type(row['active']) is not bool):
            raise ServiceError(503, 'GRANTS_UNAVAILABLE')
        if row['active']:
            allowed.add((row['tenant_id'], row['company_id'], row['node_verify_key']))
    return allowed


class Worker:
    def __init__(self, state_dir, grants_file, signing_key):
        self.store = WorkerStore(state_dir)
        self.grants_file = Path(grants_file)
        self.signing_key = signing_key
        self.slots = threading.BoundedSemaphore(2)
        self.activity_lock = threading.Lock()
        self.idle=threading.Condition(self.activity_lock)
        self.active_evaluations = 0
        self.closing=False
        try:grants(self.grants_file)  # Invalid configuration prevents startup.
        except BaseException:self.store.close();raise

    def close(self):
        with self.idle:
            self.closing=True
            while self.active_evaluations:self.idle.wait(.2)
            self.store.close()

    def allowed(self, tenant, company, node_key):
        if (tenant, company, node_key) not in grants(self.grants_file):
            raise ServiceError(403, 'NODE_GRANT_DENIED')

    def readiness(self, packet):
        p = packet.get('payload') if isinstance(packet, dict) else None
        fields = {'version','tenant_id','company_id','node_verify_key','challenge','expires_at'}
        if (not isinstance(p,dict) or set(p)!=fields or p['version']!='he-worker-readiness/1.0.0'
                or not all(identifier(p[k]) for k in ('tenant_id','company_id'))
                or not isinstance(p['challenge'],str) or not re.fullmatch('[a-f0-9]{64}',p['challenge'])):
            raise ServiceError(400,'READINESS_FIELDS')
        self.allowed(p['tenant_id'],p['company_id'],p['node_verify_key'])
        verify(packet,p['node_verify_key'])
        if type(p['expires_at']) is not int or not int(time.time())<p['expires_at']<=int(time.time())+60:
            raise ServiceError(410,'READINESS_EXPIRED')
        return sign(dict(p,worker_verify_key=public_hex(self.signing_key)),self.signing_key)

    def register(self, packet):
        p = packet.get('payload') if isinstance(packet, dict) else None
        if not isinstance(p, dict) or set(p) != {'version', 'node_verify_key', 'expires_at', 'policy'}:
            raise ServiceError(400, 'REGISTRATION_FIELDS')
        policy = p['policy']
        fields = set(BINDING) | {'enabled', 'client_verify_key', 'quadratic_sha256'}
        if not isinstance(policy, dict) or set(policy) != fields:
            raise ServiceError(400, 'POLICY_FIELDS')
        if not all(identifier(policy.get(k)) for k in ('tenant_id', 'company_id', 'session_id', 'model_id', 'key_epoch')):
            raise ServiceError(400, 'POLICY_IDENTITY')
        self.allowed(policy['tenant_id'], policy['company_id'], p['node_verify_key'])
        verify(packet, p['node_verify_key'])
        if (p['version'] != REGISTRATION or type(p['expires_at']) is not int
                or not int(time.time()) < p['expires_at'] <= int(time.time()) + 300):
            raise ServiceError(400, 'REGISTRATION_EXPIRED')
        if ((policy['version'], policy['profile'], policy['contract']) != (VERSION, PROFILE, CONTRACT)
                or policy['enabled'] is not True
                or not all(isinstance(policy[k], str) and re.fullmatch('[a-f0-9]{64}', policy[k]) for k in ('context_sha256', 'client_verify_key'))
                or not isinstance(policy['quadratic_sha256'], list) or len(policy['quadratic_sha256']) != 3
                or not all(isinstance(v, str) and re.fullmatch('[a-f0-9]{64}', v) for v in policy['quadratic_sha256'])):
            raise ServiceError(400, 'POLICY_PROFILE')
        self.store.register(policy['tenant_id'], policy['company_id'], policy['session_id'], p['node_verify_key'], p['expires_at'], policy)
        self.allowed(policy['tenant_id'], policy['company_id'], p['node_verify_key'])
        return dict(status='registered', session_id=policy['session_id'])

    def score(self, packet):
        p = packet.get('payload') if isinstance(packet, dict) else None
        if not isinstance(p, dict) or not all(identifier(p.get(k)) for k in ('tenant_id', 'company_id', 'session_id', 'nonce')):
            raise ServiceError(400, 'REQUEST_IDENTITY')
        session = self.store.session(p['tenant_id'], p['company_id'], p['session_id'])
        self.allowed(p['tenant_id'], p['company_id'], session['node_key'])
        if session['expires'] <= int(time.time()):
            raise ServiceError(410, 'SESSION_EXPIRED')
        verify(packet, session['policy']['client_verify_key'])
        # Cached results also require current policy, signature and grant checks.
        expected = set(BINDING) | {'nonce', 'created_at', 'expires_at', 'row_handles', 'context', 'columns', 'quadratic'}
        if set(p) != expected:
            raise ServiceError(400, 'REQUEST_FIELDS')
        now = int(time.time())
        if (type(p['created_at']) is not int or type(p['expires_at']) is not int
                or not p['created_at'] <= now < p['expires_at'] <= p['created_at'] + 300
                or p['expires_at'] > session['expires']):
            raise ServiceError(410, 'REQUEST_EXPIRED')
        if any(p.get(k) != session['policy'][k] for k in BINDING):
            raise ServiceError(403, 'BINDING_MISMATCH')
        if not self.slots.acquire(blocking=False):
            raise ServiceError(503, 'WORKER_BUSY')
        with self.activity_lock:
            if self.closing:
                self.slots.release();raise ServiceError(503,'WORKER_CLOSING')
            self.active_evaluations += 1
        try:
            request_hash=sha(canonical(packet))
            cached, state,attempt = self.store.claim(p, request_hash)
            if state not in ('new','resume'):
                self.allowed(p['tenant_id'], p['company_id'], session['node_key'])
                if state == 'failed':
                    raise ServiceError(422, cached['reason']['code'])
                return cached
            try:
                def reservation(payload,digest):
                    if digest!=request_hash:raise ServiceError(409,'REQUEST_NONCE_CONFLICT')
                    self.store.reserve(payload,digest,attempt,lambda:reserve(self.store.replay_path,payload,
                        request_hash=digest,resuming=state=='resume'))
                result = evaluate(packet, session['policy'], self.signing_key, self.store.replay_path,reservation=reservation)
            except Exception as exc:
                code = exc.code if isinstance(exc, HEUnavailable) else 'HE_EVALUATION_FAILED'
                self.store.finish(p,request_hash,attempt,dict(status='unavailable', reason=dict(code=code)), 'failed')
                raise ServiceError(422, code) from exc
            self.store.finish(p,request_hash,attempt,result,'done')
            self.allowed(p['tenant_id'], p['company_id'], session['node_key'])
            return result
        finally:
            with self.idle:
                self.active_evaluations -= 1;self.idle.notify_all()
            self.slots.release()

    def retrieve(self, packet):
        p = packet.get('payload') if isinstance(packet, dict) else None
        expected = {'version', 'node_verify_key', 'expires_at', 'tenant_id', 'company_id',
                    'session_id', 'nonce', 'request_sha256', 'retrieval_id'}
        if (not isinstance(p, dict) or set(p) != expected
                or p['version'] != 'he-result-retrieval/1.0.0'
                or not all(identifier(p[k]) for k in ('tenant_id', 'company_id', 'session_id', 'nonce', 'retrieval_id'))):
            raise ServiceError(400, 'RETRIEVAL_FIELDS')
        self.allowed(p['tenant_id'], p['company_id'], p['node_verify_key'])
        verify(packet, p['node_verify_key'])
        if type(p['expires_at']) is not int or not int(time.time()) < p['expires_at'] <= int(time.time()) + 60:
            raise ServiceError(410, 'RETRIEVAL_EXPIRED')
        session = self.store.session(p['tenant_id'], p['company_id'], p['session_id'])
        if session['node_key'] != p['node_verify_key']:
            raise ServiceError(403, 'RESULT_OWNER_MISMATCH')
        # Fresh authorized retrieval of existing ciphertext may outlive the
        # original inference TTL. It never starts or repeats computation.
        result = self.store.retrieve(p)
        self.allowed(p['tenant_id'], p['company_id'], p['node_verify_key'])
        return result


def make_server(port, worker):
    class API(Handler):
        def do_GET(self):
            try:
                self.guard()
                if self.path != '/health':
                    raise ServiceError(404, 'ROUTE_NOT_FOUND')
                self.reply(200, dict(role='ciphertext_worker', protocol=VERSION,
                    response_verify_key=public_hex(worker.signing_key), active_evaluations=worker.active_evaluations,
                    enterprise_module_available=importlib.util.find_spec(__package__ + '.enterprise') is not None,
                    business_module_available=importlib.util.find_spec('sme_fraud') is not None,
                    enterprise_storage_configured=False))
            except ServiceError as exc:
                self.failure(exc)

        def do_POST(self):
            try:
                self.guard()
                if self.path not in ('/v1/sessions', '/v1/evaluate', '/v1/results','/v1/readiness'):
                    raise ServiceError(404, 'ROUTE_NOT_FOUND')
                packet = self.body(16 * 1024 if self.path != '/v1/evaluate' else 16 * 1024 * 1024)
                operation = {'/v1/sessions': worker.register, '/v1/evaluate': worker.score, '/v1/results': worker.retrieve,'/v1/readiness':worker.readiness}[self.path]
                self.reply(200, operation(packet))
            except ServiceError as exc:
                self.failure(exc)
            except HEUnavailable as exc:
                self.failure(ServiceError(403, exc.code))
            except Exception:
                self.failure(ServiceError(503, 'WORKER_UNAVAILABLE'))
    return LocalServer(port, API)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True); parser.add_argument('--port', type=int, default=8868)
    parser.add_argument('--ready-file')
    args = parser.parse_args()
    if (importlib.util.find_spec(__package__ + '.enterprise') is not None
            or importlib.util.find_spec('sme_fraud') is not None):
        raise SystemExit('WORKER_BUNDLE_REQUIRED: start from the isolated worker bundle')
    config = read_json(args.config)
    if not isinstance(config, dict) or set(config) != {'version', 'state_dir', 'grants_file', 'response_signing_key_file'} or config['version'] != 'he-worker-service/1.0.0':
        raise SystemExit('WORKER_CONFIG_INVALID')
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(Path(config['response_signing_key_file']).read_text().strip()))
    service = Worker(config['state_dir'], config['grants_file'], key)
    server = make_server(args.port, service)
    if args.ready_file:
        Path(args.ready_file).write_bytes(canonical(dict(port=server.server_port, role='ciphertext_worker', response_verify_key=public_hex(key))))
    try:
        server.serve_forever()
    finally:
        server.server_close()
        service.close()


if __name__ == '__main__':
    main()
