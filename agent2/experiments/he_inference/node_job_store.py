"""Enterprise-only durable jobs; all requests, HE checkpoints and results sealed."""
from contextlib import contextmanager
import hashlib
import hmac
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .http_common import ServiceError, decode
from .protocol import canonical
from .key_manager import load_key

APP_ID = 0x48454E32
VERSION = 'he-node-jobs/1.0.0'
TERMINAL = {'completed', 'failed', 'expired'}
LABELS = dict(queued='Đã nhận yêu cầu', preparing='Đang chuẩn bị dữ liệu tại doanh nghiệp',
    ready='Đã mã hóa và lưu phiên', sending='Đang gửi bản mã', waiting_worker='Đang chờ worker',
    received='Đã nhận kết quả mã hóa', decrypting='Đang giải mã tại doanh nghiệp', completed='Đã hoàn tất',
    retryable='Đang chờ thử lại', waiting_authorization='Cần xác thực để tiếp tục',
    failed='Không thể hoàn tất', expired='Phiên đã hết hạn')


class StateLock:
    def __init__(self, folder):
        self.file = open(Path(folder) / 'node.lock', 'a+b')
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b'0'); self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise ServiceError(503, 'NODE_STATE_IN_USE') from exc

    def close(self):
        if not self.file.closed:
            if os.name == 'nt':
                import msvcrt
                self.file.seek(0); msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
            self.file.close()


class JobStore:
    def __init__(self, folder, key_file, required_provider=None):
        try:
            local_key = load_key(key_file, purpose='state-wrapping', required_provider=required_provider)
            keys = HKDF(algorithm=hashes.SHA256(), length=64, salt=b'he-node-jobs-v1',
                        info=b'enterprise-storage-and-idempotency').derive(local_key.material)
        except (OSError, ValueError) as exc:
            raise ServiceError(503, 'NODE_STATE_KEY_REQUIRED') from exc
        self.aes = AESGCM(keys[:32]); self.mac_key = keys[32:]
        folder = Path(folder).resolve(); folder.mkdir(parents=True, exist_ok=True)
        self.lock = StateLock(folder); self.path = folder / 'jobs.sqlite3'
        try:
            with self.transaction(initialize=True) as conn:
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not tables:
                    conn.execute('CREATE TABLE meta (version TEXT, nonce BLOB, verifier BLOB)')
                    nonce = os.urandom(12)
                    conn.execute('INSERT INTO meta VALUES (?,?,?)', (VERSION, nonce, self.aes.encrypt(nonce, b'node-key-verifier', VERSION.encode())))
                    conn.execute('CREATE TABLE jobs (id TEXT PRIMARY KEY, tenant TEXT, company TEXT, actor TEXT, idem TEXT, request_hash TEXT, phase TEXT, generation INTEGER, nonce BLOB, payload BLOB, created INTEGER, updated INTEGER, UNIQUE(tenant,company,actor,idem))')
                meta = conn.execute('SELECT * FROM meta').fetchone()
                if not meta or meta['version'] != VERSION or self.aes.decrypt(meta['nonce'], meta['verifier'], VERSION.encode()) != b'node-key-verifier':
                    raise ValueError()
                # No credential is persisted. Resume requires current owner auth.
                for row in conn.execute("SELECT * FROM jobs WHERE phase NOT IN ('completed','failed','expired')").fetchall():
                    data = self.open(row)
                    self._save(conn, row, data, 'waiting_authorization', 'NODE_RESTARTED')
        except Exception as exc:
            self.lock.close()
            if isinstance(exc, ServiceError):
                raise
            raise ServiceError(503, 'NODE_STATE_KEY_OR_INTEGRITY') from exc

    @contextmanager
    def transaction(self, initialize=False):
        conn = sqlite3.connect(self.path, isolation_level=None, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA synchronous=FULL'); conn.execute('BEGIN IMMEDIATE')
            app = conn.execute('PRAGMA application_id').fetchone()[0]
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if initialize and app == 0 and not tables:
                conn.execute(f'PRAGMA application_id={APP_ID}')
            elif app != APP_ID:
                raise ServiceError(503, 'NODE_JOB_STORAGE_VERSION')
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def owner(scope):
        if len(scope.company_ids) != 1 or 'data.import' not in scope.permissions:
            raise ServiceError(403, 'ACCESS_DENIED')
        return scope.tenant_id, next(iter(scope.company_ids)), scope.actor_id

    @staticmethod
    def aad(row):
        return canonical(dict(version=VERSION, **{k: row[k] for k in ('id', 'tenant', 'company', 'actor', 'idem', 'request_hash', 'phase', 'generation', 'created', 'updated')}))

    def open(self, row):
        try:
            value = decode(self.aes.decrypt(row['nonce'], row['payload'], self.aad(row)))
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except Exception as exc:
            raise ServiceError(503, 'NODE_STATE_INTEGRITY') from exc

    def _row(self, conn, scope, job_id):
        row = conn.execute('SELECT * FROM jobs WHERE id=? AND tenant=? AND company=? AND actor=?', (job_id, *self.owner(scope))).fetchone()
        if row is None:
            raise ServiceError(404, 'NODE_JOB_NOT_FOUND')
        return row

    def create(self, scope, key, request):
        owner = self.owner(scope)
        idem = hmac.new(self.mac_key, canonical([*owner, key]), hashlib.sha256).hexdigest()
        digest = hashlib.sha256(canonical(request)).hexdigest()
        with self.transaction() as conn:
            old = conn.execute('SELECT * FROM jobs WHERE tenant=? AND company=? AND actor=? AND idem=?', (*owner, idem)).fetchone()
            if old:
                self.open(old)
                if old['request_hash'] != digest:
                    raise ServiceError(409, 'IDEMPOTENCY_CONFLICT')
                return old['id']
            if conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] >= 512:
                raise ServiceError(503, 'NODE_JOB_CAPACITY')
            if conn.execute("SELECT COUNT(*) FROM jobs WHERE phase NOT IN ('completed','failed','expired')").fetchone()[0] >= 8:
                raise ServiceError(503, 'NODE_SESSION_CAPACITY')
            now = int(time.time()); job_id = 'herun_' + uuid.uuid4().hex
            row = dict(id=job_id, tenant=owner[0], company=owner[1], actor=owner[2], idem=idem,
                       request_hash=digest, phase='queued', generation=0, created=now, updated=now)
            data = dict(request=request, events=[dict(phase='queued', at=now)], attempts=0,
                        pending=None, response=None, result=None, seen_worker=False, reason=None)
            nonce, blob = self.seal(row, data)
            conn.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (job_id, *owner, idem, digest, 'queued', 0, nonce, blob, now, now))
            return job_id

    def seal(self, row, data):
        raw = canonical(data)
        if len(raw) > 16 * 1024 * 1024:
            raise ServiceError(503, 'NODE_STATE_LIMIT')
        nonce = os.urandom(12)
        return nonce, self.aes.encrypt(nonce, raw, self.aad(row))

    def get(self, scope, job_id):
        with self.transaction() as conn:
            row = self._row(conn, scope, job_id)
            return dict(row), self.open(row)

    def _save(self, conn, row, data, phase, reason=None):
        if phase not in LABELS:
            raise ServiceError(503, 'NODE_PHASE_INVALID')
        updated = dict(row, phase=phase, generation=row['generation'] + 1, updated=int(time.time()))
        data['reason'] = reason
        if not data['events'] or data['events'][-1]['phase'] != phase:
            data['events'].append(dict(phase=phase, at=updated['updated']))
        data['events'] = data['events'][-64:]
        nonce, blob = self.seal(updated, data)
        conn.execute('UPDATE jobs SET phase=?,generation=?,nonce=?,payload=?,updated=? WHERE id=?',
                     (phase, updated['generation'], nonce, blob, updated['updated'], row['id']))

    def save(self, scope, job_id, data, phase, reason=None):
        with self.transaction() as conn:
            row = self._row(conn, scope, job_id)
            self.open(row)  # Never overwrite a corrupted record to make progress.
            self._save(conn, row, data, phase, reason)

    def status(self, scope, job_id):
        row, data = self.get(scope, job_id)
        return dict(version=VERSION, job_id=job_id, run_id=job_id, company_id=row['company'],
                    phase=row['phase'], message=LABELS[row['phase']], attempts=data['attempts'],
                    reason=data['reason'], created_at=row['created'], updated_at=row['updated'],
                    can_resume=row['phase'] not in TERMINAL, events=data['events'])

    def close(self):
        self.lock.close()
