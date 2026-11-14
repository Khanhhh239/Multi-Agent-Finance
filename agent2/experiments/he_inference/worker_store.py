"""Worker-owned public policy and ciphertext result cache. No enterprise data."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import uuid
import os

from .protocol import canonical
from .http_common import decode, ServiceError

APPLICATION_ID = 0x48455332
STORAGE_VERSION = 2


class StateLock:
    """One worker owns this state until exit; OS releases the lock on crash.

    No time-based lease can expire underneath a long native computation.
    Each job also has an attempt token fencing stale completion callbacks.
    """
    def __init__(self,folder):
        self.file=open(Path(folder)/'worker.lock','a+b')
        self.file.seek(0,2)
        if self.file.tell()==0:self.file.write(b'0');self.file.flush()
        self.file.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise ServiceError(503,'WORKER_STATE_IN_USE') from exc

    def close(self):
        if self.file.closed:return
        if os.name=='nt':
            import msvcrt
            self.file.seek(0);msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
        self.file.close()


class WorkerStore:
    def __init__(self, folder):
        folder = Path(folder).resolve(); folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / 'jobs.sqlite3'
        self.replay_path = folder / 'replay.sqlite3'
        self.lock=StateLock(folder);self.closed=False
        try:
            with self.transaction(initialize=True) as conn:
                version=conn.execute('PRAGMA user_version').fetchone()[0]
                if version not in (0,STORAGE_VERSION):raise ServiceError(503,'WORKER_STORAGE_VERSION')
                conn.execute('CREATE TABLE IF NOT EXISTS sessions (tenant TEXT, company TEXT, session TEXT, node_key TEXT, expires INTEGER, policy BLOB, PRIMARY KEY(tenant,company,session))')
                conn.execute('CREATE TABLE IF NOT EXISTS jobs (tenant TEXT, company TEXT, session TEXT, nonce TEXT, request_hash TEXT, state TEXT, result BLOB, attempt TEXT, generation INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(tenant,company,session,nonce))')
                columns={r[1] for r in conn.execute('PRAGMA table_info(jobs)')}
                old={'tenant','company','session','nonce','request_hash','state','result'}
                if columns==old and version==0:
                    conn.execute('ALTER TABLE jobs ADD COLUMN attempt TEXT')
                    conn.execute('ALTER TABLE jobs ADD COLUMN generation INTEGER NOT NULL DEFAULT 0')
                elif columns!=old|{'attempt','generation'}:raise ServiceError(503,'WORKER_STORAGE_VERSION')
                # Legacy running jobs have no bound managed reservation/attempt;
                # never silently unburn a legacy nonce or reopen terminal jobs.
                conn.execute("UPDATE jobs SET state='failed',result=? WHERE state='running' AND attempt IS NULL",
                    (canonical(dict(status='unavailable',reason=dict(code='WORKER_INTERRUPTED_LEGACY'))),))
                conn.execute("UPDATE jobs SET state='retryable',attempt=NULL WHERE state='running'")
                conn.execute(f'PRAGMA user_version={STORAGE_VERSION}')
        except BaseException:
            self.close();raise

    def close(self):
        if not self.closed:
            self.closed=True;self.lock.close()

    @contextmanager
    def transaction(self, initialize=False):
        if self.closed:raise ServiceError(503,'WORKER_STATE_CLOSED')
        conn = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA synchronous=FULL')
            conn.execute('BEGIN IMMEDIATE')
            app = conn.execute('PRAGMA application_id').fetchone()[0]
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if initialize and app == 0 and not tables:
                conn.execute(f'PRAGMA application_id={APPLICATION_ID}')
            elif app != APPLICATION_ID:
                raise ServiceError(503, 'WORKER_STORAGE_VERSION')
            yield conn
            conn.commit()
        finally:
            conn.close()

    def register(self, tenant, company, session, node_key, expires, policy):
        packed = canonical(policy)
        with self.transaction() as conn:
            old = conn.execute('SELECT * FROM sessions WHERE tenant=? AND company=? AND session=?', (tenant, company, session)).fetchone()
            if old:
                if (old['node_key'], old['expires'], old['policy']) != (node_key, expires, packed):
                    raise ServiceError(409, 'SESSION_POLICY_CONFLICT')
                return
            if conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] >= 128:
                raise ServiceError(503, 'SESSION_CAPACITY')
            conn.execute('INSERT INTO sessions VALUES (?,?,?,?,?,?)', (tenant, company, session, node_key, expires, packed))

    def session(self, tenant, company, session):
        with self.transaction() as conn:
            row = conn.execute('SELECT * FROM sessions WHERE tenant=? AND company=? AND session=?', (tenant, company, session)).fetchone()
            if not row:
                raise ServiceError(403, 'SESSION_NOT_REGISTERED')
            return dict(row, policy=decode(row['policy']))

    def claim(self, p, request_hash):
        key = tuple(p[k] for k in ('tenant_id', 'company_id', 'session_id', 'nonce'))
        with self.transaction() as conn:
            row = conn.execute('SELECT * FROM jobs WHERE tenant=? AND company=? AND session=? AND nonce=?', key).fetchone()
            if row:
                if row['request_hash'] != request_hash:
                    raise ServiceError(409, 'REQUEST_NONCE_CONFLICT')
                if row['state'] == 'running':
                    raise ServiceError(409, 'WORKER_IN_PROGRESS')
                if row['state']=='retryable':
                    token=uuid.uuid4().hex
                    conn.execute("UPDATE jobs SET state='running',attempt=?,generation=generation+1 WHERE tenant=? AND company=? AND session=? AND nonce=?",(token,*key))
                    return None,'resume',token
                if row['state'] not in ('done','failed'):raise ServiceError(503,'WORKER_STORAGE_STATE')
                return decode(row['result']), row['state'],None
            if conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] >= 512:
                raise ServiceError(503, 'JOB_CAPACITY')
            token=uuid.uuid4().hex
            conn.execute("INSERT INTO jobs (tenant,company,session,nonce,request_hash,state,result,attempt,generation) VALUES (?,?,?,?,?,'running',NULL,?,1)", (*key, request_hash,token))
            return None, 'new',token

    def _owned(self,conn,key,request_hash,attempt):
        row=conn.execute('SELECT * FROM jobs WHERE tenant=? AND company=? AND session=? AND nonce=?',key).fetchone()
        if row is None or row['state']!='running' or not attempt or row['attempt']!=attempt or row['request_hash']!=request_hash:
            raise ServiceError(409,'WORKER_ATTEMPT_STALE')

    def reserve(self,p,request_hash,attempt,operation):
        key=tuple(p[k] for k in ('tenant_id','company_id','session_id','nonce'))
        with self.transaction() as conn:
            self._owned(conn,key,request_hash,attempt)
            operation()  # durable request-hash-bound replay reservation

    def finish(self, p, request_hash,attempt,result, state):
        if state not in ('done','failed'):raise ServiceError(503,'WORKER_STORAGE_STATE')
        key = tuple(p[k] for k in ('tenant_id', 'company_id', 'session_id', 'nonce'))
        with self.transaction() as conn:
            self._owned(conn,key,request_hash,attempt)
            conn.execute('UPDATE jobs SET state=?, result=?,attempt=NULL WHERE tenant=? AND company=? AND session=? AND nonce=?',
                         (state, canonical(result), *key))

    def retrieve(self, p):
        key = tuple(p[k] for k in ('tenant_id', 'company_id', 'session_id', 'nonce'))
        with self.transaction() as conn:
            row = conn.execute('SELECT * FROM jobs WHERE tenant=? AND company=? AND session=? AND nonce=?', key).fetchone()
            if row is None:
                raise ServiceError(404, 'RESULT_NOT_READY')
            if row['request_hash'] != p['request_sha256']:
                raise ServiceError(403, 'RESULT_REQUEST_MISMATCH')
            if row['state'] == 'running':
                raise ServiceError(409, 'WORKER_IN_PROGRESS')
            if row['state']=='retryable':raise ServiceError(404,'RESULT_NOT_READY')
            value = decode(row['result'])
            if row['state'] == 'failed':
                raise ServiceError(422, value['reason']['code'])
            return value
