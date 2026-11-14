"""Durable enterprise scoring lifecycle. Network only carries signed ciphertext."""
from copy import deepcopy
import queue
import threading
import time
import uuid

from sme_fraud.auth import AuthError
from sme_fraud.import_files import ImportFailure
from sme_fraud.snapshot_features import utc
from .checkpoint import freeze, restore
from .http_common import ServiceError, post
from .node_job_store import JobStore, TERMINAL
from .protocol import HEUnavailable, canonical, public_hex, sha, sign
from .registry_export import export_snapshot


class Jobs:
    def __init__(self, node, folder, key_file, required_provider=None):
        self.node = node
        self.store = JobStore(folder, key_file, required_provider=required_provider)
        self.queue = queue.Queue(16)
        self.active = set(); self.tickets = {}; self.timers = []
        self.lock = threading.Lock(); self.stopping = threading.Event()
        self.threads = [threading.Thread(target=self._loop, daemon=True) for _ in range(2)]
        for thread in self.threads:
            thread.start()

    def _scope(self, header, company):
        return self.node.auth.authorize(header, company)

    def guard(self, job_id, owner):
        with self.lock:
            header = self.tickets.get(job_id)
        if header is None:
            raise ServiceError(401, 'AUTH_REQUIRED')
        scope = self._scope(header, next(iter(owner.company_ids)))
        if self.store.owner(scope) != self.store.owner(owner):
            raise ServiceError(403, 'ACCESS_DENIED')
        return scope, header

    def schedule(self, scope, header, job_id):
        row, _ = self.store.get(scope, job_id)
        if row['phase'] in TERMINAL:
            return
        with self.lock:
            self.tickets[job_id] = header
            if job_id in self.active or self.stopping.is_set():
                return
            self.active.add(job_id)
            self.queue.put_nowait((scope, job_id))

    def submit(self, company, header, key, body):
        scope = self._scope(header, company)
        # Same strict reference-only contract as the existing synchronous API.
        import re
        if (not isinstance(body, dict) or set(body) != {'artifact_id', 'snapshot_id', 'as_of'}
                or not all(isinstance(v, str) for v in body.values())
                or not re.fullmatch(r'mth_[a-f0-9]{64}', body['artifact_id'])
                or not re.fullmatch(r'snp_[a-f0-9]{32}', body['snapshot_id'])
                or not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{8,128}', key)):
            raise ServiceError(400, 'NODE_REQUEST_FIELDS')
        request = dict(body, as_of=utc(body['as_of']).isoformat())
        job_id = self.store.create(scope, key, request)
        self.schedule(scope, header, job_id)
        return self.status(company, header, job_id)

    def status(self, company, header, job_id):
        scope = self._scope(header, company)
        value = self.store.status(scope, job_id)
        if self.store.owner(self._scope(header, company)) != self.store.owner(scope):
            raise ServiceError(409, 'AUTH_CONTEXT_CHANGED')
        value.update(status_url=f'/v1/companies/{company}/he/jobs/{job_id}',
                     result_url=f'/v1/companies/{company}/he/jobs/{job_id}/result', poll_after_ms=500)
        return value

    def resume(self, company, header, job_id):
        scope = self._scope(header, company)
        self.schedule(scope, header, job_id)
        return self.status(company, header, job_id)

    def result(self, company, header, job_id):
        scope = self._scope(header, company)
        row, data = self.store.get(scope, job_id)
        if self.store.owner(self._scope(header, company)) != self.store.owner(scope):
            raise ServiceError(409, 'AUTH_CONTEXT_CHANGED')
        if row['phase'] == 'completed':
            return 200, data['result']
        return (409 if row['phase'] in TERMINAL else 202), self.status(company, header, job_id)

    def wait(self, company, header, job_id, seconds=40):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            status, value = self.result(company, header, job_id)
            if status == 200:
                return value
            if status == 409:
                raise ServiceError(502, value['reason'] or 'NODE_JOB_FAILED')
            time.sleep(.05)
        raise ServiceError(503, 'NODE_JOB_PENDING_USE_STATUS')

    def _loop(self):
        while not self.stopping.is_set():
            try:
                scope, job_id = self.queue.get(timeout=.2)
            except queue.Empty:
                continue
            retry = False
            try:
                retry = self._process(scope, job_id)
            except Exception:
                retry = False  # Integrity/storage failures must not kill dispatch.
            finally:
                with self.lock:
                    self.active.discard(job_id)
                self.queue.task_done()
            if retry and not self.stopping.is_set():
                _, data = self.store.get(scope, job_id)
                delay = min(30, 2 ** min(data['attempts'], 5))
                timer = threading.Timer(delay, self._retry, (scope, job_id))
                timer.daemon = True; self.timers.append(timer); timer.start()

    def _retry(self, scope, job_id):
        try:
            _, header = self.guard(job_id, scope)
            self.schedule(scope, header, job_id)
        except (AuthError, ServiceError):
            pass

    def _process(self, scope, job_id):
        row, data = self.store.get(scope, job_id)
        if row['phase'] in TERMINAL:
            return False
        try:
            _, header = self.guard(job_id, scope)
            company = next(iter(scope.company_ids))
            if data['response'] is None:
                self.node.check_worker(scope)
            if data['pending'] is None:
                self.store.save(scope, job_id, data, 'preparing')
                r = data['request']
                export = export_snapshot(self.node.model_db, self.node.snapshot_db, self.node.auth, header,
                    company, r['artifact_id'], r['snapshot_id'], r['as_of'], self.node.worker_verify_key)
                if not export.ready:
                    return self._complete(scope, job_id, data, export.local_result())
                data['pending'] = freeze(export)
                # Durable write-ahead: no network action is allowed before this.
                self.store.save(scope, job_id, data, 'ready')
            check = lambda: self.guard(job_id, scope)
            export = restore(data['pending'], check, scope, self.node.worker_verify_key)
            package = export.cloud_package()
            packet = package['request']
            if data['response'] is None:
                if not data['seen_worker'] and packet['payload']['expires_at'] <= int(time.time()):
                    raise ServiceError(410, 'REQUEST_EXPIRED')
                data['attempts'] += 1
                self.store.save(scope, job_id, data, 'sending')
                if data['seen_worker']:
                    retrieval = sign(dict(version='he-result-retrieval/1.0.0',
                        node_verify_key=public_hex(self.node.provisioning_key), expires_at=int(time.time()) + 60,
                        tenant_id=scope.tenant_id, company_id=company,
                        session_id=packet['payload']['session_id'], nonce=packet['payload']['nonce'],
                        request_sha256=sha(canonical(packet)), retrieval_id='get_' + uuid.uuid4().hex), self.node.provisioning_key)
                    try:
                        check()
                        data['response'] = post(self.node.worker_url, '/v1/results', retrieval)
                    except ServiceError as exc:
                        if exc.code != 'RESULT_NOT_READY':
                            raise
                if data['response'] is None:
                    if packet['payload']['expires_at'] <= int(time.time()):
                        raise ServiceError(410, 'REQUEST_EXPIRED')
                    registration = sign(dict(version='he-session-registration/1.0.0',
                        node_verify_key=public_hex(self.node.provisioning_key),
                        expires_at=packet['payload']['expires_at'], policy=package['policy']), self.node.provisioning_key)
                    check(); post(self.node.worker_url, '/v1/sessions', registration)
                    data['seen_worker'] = True
                    # If killed here, recovery fetches this exact nonce/hash.
                    self.store.save(scope, job_id, data, 'waiting_worker')
                    check(); data['response'] = post(self.node.worker_url, '/v1/evaluate', packet)
                check()
                self.store.save(scope, job_id, data, 'received')
            self.store.save(scope, job_id, data, 'decrypting')
            check()
            return self._complete(scope, job_id, data, export.open(data['response']))
        except (AuthError, ServiceError, HEUnavailable, ImportFailure) as exc:
            code = getattr(exc, 'code', 'NODE_JOB_FAILED')
            status = getattr(exc, 'status', 502)
            if isinstance(exc, AuthError) or status in (401, 403):
                phase = 'waiting_authorization'
            elif code in ('REQUEST_EXPIRED', 'SESSION_EXPIRED', 'REGISTRATION_EXPIRED'):
                phase = 'expired'
            elif isinstance(exc, ServiceError) and status == 503:
                phase = 'retryable'
            else:
                phase = 'failed'
            if phase in TERMINAL:
                data['pending'] = data['response'] = None
            self.store.save(scope, job_id, data, phase, code)
            if phase != 'retryable':
                with self.lock:
                    self.tickets.pop(job_id, None)
            return phase == 'retryable'
        except Exception:
            # Never leave a silent running job or fall back to plaintext scoring.
            data['pending'] = data['response'] = None
            self.store.save(scope, job_id, data, 'failed', 'NODE_JOB_FAILED')
            with self.lock:
                self.tickets.pop(job_id, None)
            return False

    def _complete(self, scope, job_id, data, local):
        self.guard(job_id, scope)
        result = dict(version='he-enterprise-result/1.1.0', run_id=job_id,
            company_id=next(iter(scope.company_ids)), snapshot_id=data['request']['snapshot_id'],
            as_of=local['receipt']['as_of'], status=local['status'], row_count=local['row_count'],
            score_meaning='Điểm bất thường của phép thử, không phải xác suất sai phạm.',
            rows=[dict(record_id=r['record_id'], revision=r['revision'], status=r['status'], available=r['available'],
                       score=r['raw_score'], reason=r['reason']) for r in local['rows']])
        data['result'] = result
        data['receipt'] = local['receipt']
        data['pending'] = data['response'] = None
        self.guard(job_id, scope)
        self.store.save(scope, job_id, data, 'completed')
        with self.lock:
            self.tickets.pop(job_id, None)
        return False

    def close(self):
        self.stopping.set()
        for timer in self.timers:
            timer.cancel()
        for thread in self.threads:
            thread.join(timeout=45)
        self.tickets.clear()
        if not any(t.is_alive() for t in self.threads):
            self.store.close()
