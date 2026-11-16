"""Enterprise release objects, append-only audit, CAS pointers and frozen run pins.

This database owns release metadata only. It never restores or updates review,
label, task, delivery, budget, model, snapshot or key stores.
"""
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
import os
import re
import sqlite3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from finance_input.json_io import loads
from .import_files import canonical,digest,fail
from .snapshots import SnapshotStore

VERSION='pipeline-release-store/1.0.0'
APP_ID=1093817149
PREFIX={'artifact':'rart_','bundle':'rbun_','gate':'rgat_','approval':'rapr_','activation':'ract_','pin':'rpin_','observation':'robs_','revocation':'rrev_','execution':'rexe_','review_packet':'rpkt_'}


def ensure(ok,code,message,status=409):
    if not ok:fail(status,code,message,'Tải lại trạng thái; kiểm tra đúng doanh nghiệp, bundle và revision trước khi thử lại.')


class ReleaseStore:
    def __init__(self,path,key,clock=None):
        ensure(isinstance(key,bytes) and len(key)==32,'RELEASE_KEY_REQUIRED','Cần khóa bảo vệ kho release tại doanh nghiệp.',503)
        self.path=Path(path).resolve();self.path.parent.mkdir(parents=True,exist_ok=True)
        self.aes=AESGCM(key);self.clock=clock or (lambda:datetime.now(timezone.utc))
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        self.review_key=HKDF(algorithm=hashes.SHA256(),length=32,salt=b'agent2-bundle-reviews-v1',info=b'enterprise-company-case-reviews').derive(key)
        with self.tx() as c:
            app=c.execute('PRAGMA application_id').fetchone()[0]
            tables=c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            ensure(app==APP_ID or app==0 and not tables,'RELEASE_STORAGE_VERSION','Đường dẫn không phải kho release riêng đúng phiên bản.',503)
            c.execute(f'PRAGMA application_id={APP_ID}')
            c.execute('CREATE TABLE IF NOT EXISTS meta(nonce BLOB,payload BLOB)')
            row=c.execute('SELECT * FROM meta').fetchone()
            if row is None:
                n=os.urandom(12);c.execute('INSERT INTO meta VALUES (?,?)',(n,self.aes.encrypt(n,VERSION.encode(),b'release-key-check')))
            else:
                try:valid=self.aes.decrypt(row['nonce'],row['payload'],b'release-key-check')==VERSION.encode()
                except InvalidTag:valid=False
                ensure(valid,'RELEASE_KEY_MISMATCH','Không mở được kho release bằng khóa này.',503)
            c.execute('CREATE TABLE IF NOT EXISTS objects(owner TEXT,id TEXT,kind TEXT,nonce BLOB,payload BLOB,PRIMARY KEY(owner,id))')
            c.execute('CREATE TABLE IF NOT EXISTS pointers(owner TEXT,lane TEXT,revision INTEGER,event_id TEXT,PRIMARY KEY(owner,lane))')
            c.execute('CREATE TABLE IF NOT EXISTS receipts(owner TEXT,actor TEXT,request_id TEXT,hash TEXT,result BLOB,PRIMARY KEY(owner,actor,request_id))')
            c.execute('CREATE TABLE IF NOT EXISTS pins(owner TEXT,run_id TEXT,object_id TEXT,request_hash TEXT,PRIMARY KEY(owner,run_id))')
            c.execute('CREATE TABLE IF NOT EXISTS revoked(owner TEXT,id TEXT,actor TEXT,at TEXT,reason TEXT,PRIMARY KEY(owner,id))')
            c.execute('CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY,owner TEXT,object_id TEXT,kind TEXT)')
            for table in ('objects','receipts','pins','revoked','audit','meta'):
                for op in ('UPDATE','DELETE'):
                    c.execute(f"CREATE TRIGGER IF NOT EXISTS release_{table}_{op.lower()} BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT,'append-only release metadata'); END")
            c.execute("CREATE TRIGGER IF NOT EXISTS release_pointer_delete BEFORE DELETE ON pointers BEGIN SELECT RAISE(ABORT,'release pointer must advance revision'); END")

    def now(self):return self.clock().astimezone(timezone.utc).isoformat()

    @staticmethod
    def owner(scope):
        tenant,company,_=SnapshotStore._scope(scope)
        return digest(canonical([tenant,company]))

    @contextmanager
    def tx(self,scope=None,recheck=None,*,write=True):
        if scope is not None:self.owner(scope)
        c=sqlite3.connect(self.path,timeout=30,isolation_level=None);c.row_factory=sqlite3.Row
        try:
            c.execute('PRAGMA synchronous=FULL');c.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            if recheck is not None:ensure(recheck()==scope,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.',403)
            yield c
            if recheck is not None:ensure(recheck()==scope,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi trước khi lưu/trả kết quả.',403)
            c.commit()
        except BaseException:
            if c.in_transaction:c.rollback()
            raise
        finally:c.close()

    def put(self,c,scope,kind,value):
        owner=self.owner(scope);oid=PREFIX[kind]+digest(canonical(value))
        old=c.execute('SELECT 1 FROM objects WHERE owner=? AND id=?',(owner,oid)).fetchone()
        if old is None:
            n=os.urandom(12);ct=self.aes.encrypt(n,canonical(value),canonical([VERSION,owner,kind,oid]))
            c.execute('INSERT INTO objects VALUES (?,?,?,?,?)',(owner,oid,kind,n,ct))
            c.execute('INSERT INTO audit(owner,object_id,kind) VALUES (?,?,?)',(owner,oid,kind))
        return oid

    def read(self,c,scope,oid,kind=None):
        owner=self.owner(scope)
        row=c.execute('SELECT * FROM objects WHERE owner=? AND id=?',(owner,oid)).fetchone()
        ensure(row is not None and (kind is None or row['kind']==kind),'RELEASE_OBJECT_NOT_FOUND','Không có đối tượng release trong doanh nghiệp này.',404)
        try:value=loads(self.aes.decrypt(row['nonce'],row['payload'],canonical([VERSION,owner,row['kind'],oid])))
        except (InvalidTag,ValueError):fail(503,'RELEASE_STORAGE_INTEGRITY','Kho release không toàn vẹn.','Kiểm tra khóa và bản sao lưu; không ghi đè kho.')
        ensure(oid==PREFIX[row['kind']]+digest(canonical(value)),'RELEASE_STORAGE_INTEGRITY','Checksum đối tượng release không khớp.',503)
        return value

    def get(self,scope,oid,kind=None,recheck=None):
        with self.tx(scope,recheck,write=False) as c:return self.read(c,scope,oid,kind)

    def list(self,scope,kind,recheck=None):
        with self.tx(scope,recheck,write=False) as c:
            ids=[r[0] for r in c.execute('SELECT id FROM objects WHERE owner=? AND kind=? ORDER BY rowid DESC',(self.owner(scope),kind))]
            return [dict(id=i,value=self.read(c,scope,i,kind)) for i in ids]

    def is_revoked(self,scope,oid):
        with self.tx(scope,write=False) as c:return c.execute('SELECT 1 FROM revoked WHERE owner=? AND id=?',(self.owner(scope),oid)).fetchone() is not None

    def revoke(self,scope,oid,reason,recheck=None):
        ensure(isinstance(reason,str) and 10<=len(reason.strip())<=1000,'RELEASE_REASON','Cần lý do rõ ràng.',400)
        with self.tx(scope,recheck) as c:
            self.read(c,scope,oid)
            event=self.put(c,scope,'revocation',dict(id=oid,actor_id=scope.actor_id,at=self.now(),reason=reason))
            c.execute('INSERT OR IGNORE INTO revoked VALUES (?,?,?,?,?)',(self.owner(scope),oid,scope.actor_id,self.now(),event))
        return dict(id=oid,revoked=True)

    def pointer(self,c,scope,lane):
        ensure(lane in ('staging','production'),'RELEASE_LANE','Chọn staging hoặc production.',400)
        row=c.execute('SELECT * FROM pointers WHERE owner=? AND lane=?',(self.owner(scope),lane)).fetchone()
        if row is None:return dict(lane=lane,revision=0,bundle_id=None,event_id=None)
        event=self.read(c,scope,row['event_id'],'activation')
        ensure(event['revision']==row['revision'] and event['lane']==lane,'RELEASE_POINTER_INTEGRITY','Con trỏ release không khớp audit.',503)
        return dict(event,event_id=row['event_id'])

    def current(self,scope,lane,recheck=None):
        with self.tx(scope,recheck,write=False) as c:return self.pointer(c,scope,lane)

    def receipt(self,c,scope,key,request_hash,result=None):
        ensure(isinstance(key,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{8,128}',key),'RELEASE_IDEMPOTENCY_KEY','Cần Idempotency-Key 8–128 ký tự.',400)
        owner=self.owner(scope)
        prior=c.execute('SELECT * FROM receipts WHERE owner=? AND actor=? AND request_id=?',(owner,scope.actor_id,key)).fetchone()
        if prior is not None:
            ensure(prior['hash']==request_hash,'RELEASE_IDEMPOTENCY_CONFLICT','Mã yêu cầu đã dùng cho nội dung khác.')
            # Only protected object IDs are stored in receipts, never a caller's result body.
            try:
                raw=prior['result'];return loads(self.aes.decrypt(raw[:12],raw[12:],canonical([VERSION,'receipt',owner,scope.actor_id,key,request_hash])))
            except (InvalidTag,ValueError):fail(503,'RELEASE_STORAGE_INTEGRITY','Phiếu chống gửi trùng không toàn vẹn.','Kiểm tra kho release; không đổi mã yêu cầu để vượt lỗi.')
        if result is not None:
            n=os.urandom(12);sealed=n+self.aes.encrypt(n,canonical(result),canonical([VERSION,'receipt',owner,scope.actor_id,key,request_hash]))
            c.execute('INSERT INTO receipts VALUES (?,?,?,?,?)',(owner,scope.actor_id,key,request_hash,sealed))
        return None

    def switch(self,scope,lane,bundle_id,approval_id,gate_id,expected_revision,reason,key,action,guard,recheck=None):
        ensure(type(expected_revision) is int and expected_revision>=0,'RELEASE_REVISION','Thiếu revision của con trỏ.',400)
        ensure(action in ('activate','rollback') and isinstance(reason,str) and 10<=len(reason.strip())<=1000,'RELEASE_REASON','Cần thao tác và lý do hợp lệ.',400)
        body=dict(lane=lane,bundle_id=bundle_id,approval_id=approval_id,gate_id=gate_id,expected_revision=expected_revision,reason=reason,action=action)
        request_hash=digest(canonical(body))
        with self.tx(scope,recheck) as c:
            prior=self.receipt(c,scope,key,request_hash)
            if prior is not None:return dict(self.read(c,scope,prior['event_id'],'activation'),event_id=prior['event_id'])
            current=self.pointer(c,scope,lane)
            ensure(current['revision']==expected_revision,'RELEASE_REVISION_CONFLICT','Có người đã đổi bundle đang dùng. Yêu cầu này chưa được áp dụng.')
            ensure(current.get('bundle_id')!=bundle_id,'RELEASE_ALREADY_CURRENT','Bundle này đã là phiên bản đang dùng.')
            if action=='rollback':
                history=c.execute('SELECT object_id FROM audit WHERE owner=? AND kind=?',(self.owner(scope),'activation')).fetchall()
                used=any((v:=self.read(c,scope,r['object_id'],'activation'))['lane']==lane and v['bundle_id']==bundle_id for r in history)
                ensure(used,'RELEASE_ROLLBACK_TARGET','Rollback chỉ chọn bundle đã được dùng trong lane này.')
            guard(c)
            event=dict(lane=lane,revision=expected_revision+1,bundle_id=bundle_id,approval_id=approval_id,gate_id=gate_id,
                previous_bundle_id=current.get('bundle_id'),action=action,reason=reason,actor_id=scope.actor_id,at=self.now())
            oid=self.put(c,scope,'activation',event)
            if expected_revision==0:c.execute('INSERT INTO pointers VALUES (?,?,?,?)',(self.owner(scope),lane,1,oid))
            else:
                changed=c.execute('UPDATE pointers SET revision=?,event_id=? WHERE owner=? AND lane=? AND revision=?',(expected_revision+1,oid,self.owner(scope),lane,expected_revision))
                ensure(changed.rowcount==1,'RELEASE_REVISION_CONFLICT','Con trỏ release đã thay đổi.')
            self.receipt(c,scope,key,request_hash,dict(event_id=oid))
            return dict(event,event_id=oid)

    def pin(self,scope,run_id,lane,request,recheck=None):
        ensure(isinstance(run_id,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{8,128}',run_id),'RELEASE_RUN_ID','Cần mã lượt chạy ổn định.',400)
        request_hash=digest(canonical(dict(lane=lane,request=request)))
        with self.tx(scope,recheck) as c:
            old=c.execute('SELECT * FROM pins WHERE owner=? AND run_id=?',(self.owner(scope),run_id)).fetchone()
            if old is not None:
                ensure(old['request_hash']==request_hash,'RELEASE_RUN_CONFLICT','Mã lượt chạy đã dùng cho nguồn/tham số khác.')
                return dict(pin_id=old['object_id'],**self.read(c,scope,old['object_id'],'pin'))
            active=self.pointer(c,scope,lane)
            ensure(active['bundle_id'] is not None,'RELEASE_NO_ACTIVE_BUNDLE','Lane này chưa có bundle được kích hoạt.')
            bundle=self.read(c,scope,active['bundle_id'],'bundle')
            pin=dict(run_id=run_id,lane=lane,pointer_revision=active['revision'],event_id=active['event_id'],bundle_id=active['bundle_id'],
                     bundle=bundle,request=request,actor_id=scope.actor_id,at=self.now())
            oid=self.put(c,scope,'pin',pin)
            c.execute('INSERT INTO pins VALUES (?,?,?,?)',(self.owner(scope),run_id,oid,request_hash))
            return dict(pin_id=oid,**pin)
