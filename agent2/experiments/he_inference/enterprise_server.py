"""Enterprise-owned loopback node. Plaintext, models and HE keys stay here."""
import argparse
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
import re
import threading
import time
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sme_fraud.auth import AuthError, FileAuthorizer
from sme_fraud.import_files import ImportFailure
from .http_common import Handler, LocalServer, ServiceError, post, worker_address
from .protocol import HEUnavailable, canonical, public_hex, read_json, sha, sign
from .registry_export import export_snapshot

REGISTRATION = 'he-session-registration/1.0.0'
ROUTE = re.compile(r'/v1/companies/([A-Za-z0-9_.:-]{1,128})/he/analyze\Z')
JOB_ROUTE = re.compile(r'/v1/companies/([A-Za-z0-9_.:-]{1,128})/he/jobs(?:/(herun_[a-f0-9]{32})(?:/(result|resume))?)?\Z')


@dataclass
class Pending:
    scope: object
    digest: str
    born: float
    run_id: str = field(default_factory=lambda: 'herun_' + uuid.uuid4().hex)
    lock: object = field(default_factory=threading.Lock)
    export: object = None
    result: object = None
    failed: bool = False


class EnterpriseNode:
    def __init__(self, auth, model_db, snapshot_db, worker_url, worker_verify_key, provisioning_key):
        worker_address(worker_url)
        if not re.fullmatch('[a-f0-9]{64}', worker_verify_key):
            raise ServiceError(503, 'WORKER_KEY_INVALID')
        self.auth = auth
        self.model_db, self.snapshot_db = model_db, snapshot_db
        self.worker_url, self.worker_verify_key = worker_url, worker_verify_key
        self.provisioning_key = provisioning_key
        self.entries = {}
        self.expired = set()
        self.lock = threading.Lock()
        self.jobs = None

    def enable_jobs(self, folder, key_file, required_provider=None):
        from .node_jobs import Jobs
        self.jobs = Jobs(self, folder, key_file, required_provider=required_provider)

    def check_worker(self, scope):
        from .readiness import probe
        return probe(self.worker_url,self.worker_verify_key,self.provisioning_key,
                     scope.tenant_id,next(iter(scope.company_ids)))

    def _entry(self, scope, company, key, body):
        identity = (scope.tenant_id, company, scope.actor_id, key)
        digest = sha(canonical(body))
        with self.lock:
            now = time.monotonic()
            for old_key, value in list(self.entries.items()):
                if now - value.born > 290 and not value.lock.locked():
                    del self.entries[old_key]
                    self.expired.add(old_key)
            if identity in self.expired:
                raise ServiceError(410, 'NODE_SESSION_EXPIRED')
            entry = self.entries.get(identity)
            if entry:
                if entry.scope != scope:
                    raise ServiceError(409, 'AUTH_CONTEXT_CHANGED')
                if entry.digest != digest:
                    raise ServiceError(409, 'IDEMPOTENCY_CONFLICT')
                return entry
            if len(self.entries) >= 8 or len(self.expired) >= 512:
                raise ServiceError(503, 'NODE_SESSION_CAPACITY')
            entry = Pending(scope, digest, now)
            self.entries[identity] = entry
            return entry

    def analyze(self, company, authorization, key, body):
        if self.jobs is not None:
            state = self.jobs.submit(company, authorization, key, body)
            return self.jobs.wait(company, authorization, state['job_id'])
        scope = self.auth.authorize(authorization, company)
        if (not isinstance(body, dict) or set(body) != {'artifact_id', 'snapshot_id', 'as_of'}
                or not all(isinstance(v, str) for v in body.values())
                or not re.fullmatch(r'mth_[a-f0-9]{64}', body['artifact_id'])
                or not re.fullmatch(r'snp_[a-f0-9]{32}', body['snapshot_id'])):
            raise ServiceError(400, 'NODE_REQUEST_FIELDS')
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{8,128}', key):
            raise ServiceError(400, 'IDEMPOTENCY_KEY_REQUIRED')

        def recheck():
            if self.auth.authorize(authorization, company) != scope:
                raise ServiceError(409, 'AUTH_CONTEXT_CHANGED')

        entry = self._entry(scope, company, key, body)
        if not entry.lock.acquire(blocking=False):
            raise ServiceError(409, 'NODE_IN_PROGRESS')
        try:
            recheck()
            if entry.failed:
                raise ServiceError(409, 'NODE_REQUEST_CANNOT_RESUME')
            if entry.result is not None:
                return deepcopy(entry.result)
            if entry.export is None:
                entry.export = export_snapshot(self.model_db, self.snapshot_db, self.auth, authorization, company,
                    body['artifact_id'], body['snapshot_id'], body['as_of'], self.worker_verify_key)
            export = entry.export
            if export.ready:
                package = export.cloud_package()
                registration = sign(dict(version=REGISTRATION, node_verify_key=public_hex(self.provisioning_key),
                    expires_at=package['request']['payload']['expires_at'], policy=package['policy']), self.provisioning_key)
                post(self.worker_url, '/v1/sessions', registration)
                response = post(self.worker_url, '/v1/evaluate', package['request'])
                recheck()
                local = export.open(response)
            else:
                local = export.local_result()
            # Public enterprise DTO deliberately excludes receipt/model/feature
            # metadata, keys, artifact IDs and ciphertext. It never goes to worker.
            result = dict(version='he-enterprise-result/1.0.0', run_id=entry.run_id,
                company_id=company, snapshot_id=body['snapshot_id'], as_of=local['receipt']['as_of'],
                status=local['status'], row_count=local['row_count'],
                score_meaning='Điểm bất thường của phép thử, không phải xác suất sai phạm.',
                rows=[dict(record_id=r['record_id'], revision=r['revision'], status=r['status'],
                           available=r['available'], score=r['raw_score'], reason=r['reason']) for r in local['rows']])
            recheck()
            entry.result = result
            # Drop HE keys and private model buffers when no longer needed.
            entry.export = None
            return deepcopy(result)
        except (AuthError, ImportFailure):
            entry.failed = True
            entry.export = None
            raise
        except HEUnavailable as exc:
            entry.failed = True
            entry.export = None
            raise ServiceError(502, 'HE_RESPONSE_REJECTED') from exc
        except ServiceError as exc:
            # A transport failure can safely retry the same encrypted request
            # while its enterprise key is still held in memory.
            if exc.status != 503:
                entry.failed = True
                entry.export = None
            raise
        finally:
            entry.lock.release()


def make_server(port, node):
    class API(Handler):
        def do_GET(self):
            try:
                self.guard()
                route = JOB_ROUTE.fullmatch(self.path)
                if route and route[2] and route[3] != 'resume':
                    headers = self.headers.get_all('Authorization', [])
                    header = headers[0] if len(headers) == 1 else None
                    node.auth.authorize(header, route[1])
                    if node.jobs is None:
                        raise ServiceError(503, 'NODE_JOB_STORAGE_REQUIRED')
                    if route[3] == 'result':
                        status, value = node.jobs.result(route[1], header, route[2])
                    else:
                        status, value = 200, node.jobs.status(route[1], header, route[2])
                    self.reply(status, value)
                    return
                if self.path != '/health':
                    raise ServiceError(404, 'ROUTE_NOT_FOUND')
                self.reply(200, dict(role='enterprise_node', raw_data_location='enterprise',
                                    he_decryption_location='enterprise', production_ready=False))
            except (AuthError, ImportFailure) as exc:
                self.failure(ServiceError(exc.status, exc.code))
            except ServiceError as exc:
                self.failure(exc)
            except Exception:
                self.failure(ServiceError(503, 'NODE_UNAVAILABLE'))

        def do_POST(self):
            try:
                self.guard()
                job_route = JOB_ROUTE.fullmatch(self.path)
                if job_route and (job_route[2] is None or job_route[3] == 'resume'):
                    headers = self.headers.get_all('Authorization', [])
                    header = headers[0] if len(headers) == 1 else None
                    node.auth.authorize(header, job_route[1])
                    if node.jobs is None:
                        raise ServiceError(503, 'NODE_JOB_STORAGE_REQUIRED')
                    body = self.body(4096)
                    if job_route[2] is None:
                        keys = self.headers.get_all('Idempotency-Key', [])
                        state = node.jobs.submit(job_route[1], header, keys[0] if len(keys) == 1 else None, body)
                    else:
                        if body != {}:
                            raise ServiceError(400, 'RESUME_BODY_EMPTY')
                        state = node.jobs.resume(job_route[1], header, job_route[2])
                    self.reply(200 if state['phase'] in ('completed', 'failed', 'expired') else 202, state)
                    return
                route = ROUTE.fullmatch(self.path)
                if route is None:
                    raise ServiceError(404, 'ROUTE_NOT_FOUND')
                headers = self.headers.get_all('Authorization', [])
                authorization = headers[0] if len(headers) == 1 else None
                # Deny before parsing the body or opening any enterprise DB.
                scope = node.auth.authorize(authorization, route[1])
                keys = self.headers.get_all('Idempotency-Key', [])
                key = keys[0] if len(keys) == 1 else None
                value = node.analyze(route[1], authorization, key, self.body(4096))
                if node.auth.authorize(authorization, route[1]) != scope:
                    raise ServiceError(409, 'AUTH_CONTEXT_CHANGED')
                self.reply(200, value)
            except ServiceError as exc:
                self.failure(exc)
            except (AuthError, ImportFailure) as exc:
                self.failure(ServiceError(exc.status, exc.code))
            except (ValueError, TypeError, KeyError):
                self.failure(ServiceError(400, 'NODE_REQUEST_INVALID'))
            except Exception:
                self.failure(ServiceError(503, 'NODE_UNAVAILABLE'))
    return LocalServer(port, API)


def load_node(config, authorizer=None):
    """Load private configuration locally; an embedding server owns its auth."""
    required = {'version', 'auth_file', 'model_db', 'snapshot_db', 'worker_url', 'worker_verify_key', 'provisioning_key_file'}
    storage = {'state_dir', 'state_key_file'}
    from .key_manager import load_key, PROVIDER
    if not isinstance(config, dict):
        raise SystemExit('ENTERPRISE_CONFIG_INVALID')
    version = config.get('version')
    valid = (version == 'he-enterprise-service/1.0.0' and set(config) in (required, required | storage)
             or version == 'he-enterprise-service/1.1.0' and set(config) == required | storage
             or version == 'he-enterprise-service/1.2.0' and set(config) == required | storage | {'key_protection'}
                and config['key_protection'] == PROVIDER)
    if not valid:
        raise SystemExit('ENTERPRISE_CONFIG_INVALID')
    provider = config.get('key_protection')
    local_key = load_key(config['provisioning_key_file'], purpose='node-signing', required_provider=provider)
    key = Ed25519PrivateKey.from_private_bytes(local_key.material)
    node = EnterpriseNode(authorizer or FileAuthorizer(config['auth_file']), config['model_db'], config['snapshot_db'],
                          config['worker_url'], config['worker_verify_key'], key)
    if 'state_dir' in config:
        node.enable_jobs(config['state_dir'], config['state_key_file'], required_provider=provider)
    return node


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True); parser.add_argument('--port', type=int, default=8869)
    parser.add_argument('--ready-file')
    args = parser.parse_args()
    node = load_node(read_json(args.config))
    server = make_server(args.port, node)
    if args.ready_file:
        Path(args.ready_file).write_bytes(canonical(dict(port=server.server_port, role='enterprise_node')))
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if node.jobs is not None:
            node.jobs.close()


if __name__ == '__main__':
    main()
