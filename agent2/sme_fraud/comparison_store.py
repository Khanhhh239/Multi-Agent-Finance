"""Append-only enterprise-local sealed selection plans, scoped like reviews."""
from contextlib import contextmanager
import json,os,sqlite3
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .import_files import canonical,digest,fail
from .review_store import ReviewStore
from .selection_comparison import VERSION,POLICY,BUDGET


class ComparisonStore:
    def __init__(self,path,key):
        self.path=Path(path);self.aes=AESGCM(key)
        with self.transaction() as conn:
            app=conn.execute('PRAGMA application_id').fetchone()[0];tables=conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if not tables and app==0:
                conn.execute('PRAGMA application_id=1129335857')
                conn.execute('CREATE TABLE meta(nonce BLOB,payload BLOB)')
                conn.execute('CREATE TABLE plans(owner TEXT,id TEXT,run_id TEXT,nonce BLOB,payload BLOB,PRIMARY KEY(owner,id))')
                nonce=os.urandom(12);conn.execute('INSERT INTO meta VALUES(?,?)',(nonce,self.aes.encrypt(nonce,VERSION.encode(),b'comparison-key-check')))
            elif app!=1129335857:raise ValueError('foreign comparison database')
            meta=conn.execute('SELECT * FROM meta').fetchone()
            if not meta or self.aes.decrypt(meta['nonce'],meta['payload'],b'comparison-key-check')!=VERSION.encode():raise ValueError('comparison key/version mismatch')
            for table in ('meta','plans'):
                for operation in ('UPDATE','DELETE'):
                    conn.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'immutable comparison plan'); END")

    @contextmanager
    def transaction(self):
        conn=sqlite3.connect(self.path,timeout=15,isolation_level=None);conn.row_factory=sqlite3.Row
        try:
            conn.execute('PRAGMA synchronous=FULL');conn.execute('BEGIN IMMEDIATE');yield conn;conn.commit()
        finally:conn.close()

    def identity(self,scope,run):
        owner=ReviewStore.owner(scope)
        return owner,'cmp_'+digest(canonical([VERSION,owner,run,POLICY,BUDGET]))

    def _read(self,conn,scope,run):
        owner,identity=self.identity(scope,run);row=conn.execute('SELECT * FROM plans WHERE owner=? AND id=? AND run_id=?',(owner,identity,run)).fetchone()
        if row is None:return None
        plan=json.loads(self.aes.decrypt(row['nonce'],row['payload'],canonical([VERSION,owner,identity,run])))
        if plan['run_id']!=run or plan['company_id']!=next(iter(scope.company_ids)) or plan['policy']!=POLICY or plan['budget']!=BUDGET:raise ValueError('comparison binding')
        return dict(plan_id=identity,plan_sha256=digest(canonical(plan)),plan=plan)

    def get(self,scope,run):
        with self.transaction() as conn:return self._read(conn,scope,run)

    def put(self,scope,plan):
        run=plan['run_id'];owner,identity=self.identity(scope,run)
        if plan['company_id']!=next(iter(scope.company_ids)) or plan['policy']!=POLICY or type(plan['budget']) is not int or plan['budget']!=BUDGET:
            fail(409,'COMPARISON_PLAN_SCOPE','Kế hoạch chưa khớp doanh nghiệp hoặc chính sách.','Dùng kế hoạch từ server.')
        with self.transaction() as conn:
            old=self._read(conn,scope,run)
            if old:
                expected={k:v for k,v in old['plan'].items() if k!='created_at'};received={k:v for k,v in plan.items() if k!='created_at'}
                if canonical(expected)!=canonical(received):fail(409,'COMPARISON_PLAN_CONFLICT','Lượt này đã có tập lựa chọn được khóa.','Mở báo cáo cũ; không thay lựa chọn sau khi rà.')
                return old
            nonce=os.urandom(12);conn.execute('INSERT INTO plans VALUES(?,?,?,?,?)',(owner,identity,run,nonce,self.aes.encrypt(nonce,canonical(plan),canonical([VERSION,owner,identity,run]))))
            return self._read(conn,scope,run)
