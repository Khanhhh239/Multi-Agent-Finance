"""Enterprise-only sealed review revisions. Feedback is never a training label."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import base64
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .import_files import canonical, fail

VERSION='enterprise-reviews/1.0.0'
OUTCOMES={'confirmed_risk','legitimate','inconclusive'}


class ReviewStore:
    def __init__(self,path,key,clock=time.monotonic):
        if not isinstance(key,bytes) or len(key)!=32:raise ValueError('review key required')
        self.path=Path(path);self.aes=AESGCM(key);self.clock=clock
        self.leases={};self.lock=threading.RLock()
        with self.transaction() as conn:
            app=conn.execute('PRAGMA application_id').fetchone()[0]
            tables=conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if not tables and app==0:
                conn.execute('PRAGMA application_id=1381389873')
                conn.execute('CREATE TABLE reviews (owner TEXT, case_id TEXT, revision INTEGER, nonce BLOB, payload BLOB, PRIMARY KEY(owner,case_id,revision))')
                conn.execute('CREATE TABLE meta (nonce BLOB,payload BLOB)')
                nonce=os.urandom(12)
                conn.execute('INSERT INTO meta VALUES (?,?)',(nonce,self.aes.encrypt(nonce,VERSION.encode(),b'review-key-check')))
            elif app!=1381389873:raise ValueError('foreign review database')
            meta=conn.execute('SELECT * FROM meta').fetchone()
            if not meta or self.aes.decrypt(meta['nonce'],meta['payload'],b'review-key-check')!=VERSION.encode():
                raise ValueError('review database key/version mismatch')
            conn.execute('CREATE TABLE IF NOT EXISTS attachments (owner TEXT,case_id TEXT,id TEXT,nonce BLOB,payload BLOB,PRIMARY KEY(owner,case_id,id))')
            for table in ('reviews','attachments','meta'):
                for operation in ('UPDATE','DELETE'):
                    conn.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'append-only review history'); END")

    @contextmanager
    def transaction(self):
        conn=sqlite3.connect(self.path,timeout=15,isolation_level=None);conn.row_factory=sqlite3.Row
        try:
            conn.execute('PRAGMA synchronous=FULL');conn.execute('BEGIN IMMEDIATE')
            yield conn;conn.commit()
        finally:conn.close()

    @staticmethod
    def owner(scope):
        if len(scope.company_ids)!=1 or 'data.import' not in scope.permissions:
            fail(403,'ACCESS_DENIED','Không có quyền rà doanh nghiệp này.','Kiểm tra quyền trên Portal.')
        return hashlib.sha256(canonical([scope.tenant_id,next(iter(scope.company_ids)),scope.actor_id])).hexdigest()

    @staticmethod
    def case_id(scope,job_id,record_id,revision):
        return 'rvw_'+hashlib.sha256(canonical([ReviewStore.owner(scope),job_id,record_id,revision])).hexdigest()

    def aad(self,owner,case_id,revision):return canonical([VERSION,owner,case_id,revision])

    def _read(self,conn,owner,case_id):
        row=conn.execute('SELECT * FROM reviews WHERE owner=? AND case_id=? ORDER BY revision DESC LIMIT 1',(owner,case_id)).fetchone()
        import json
        value=dict(revision=0,feedback=None,history=[],active_seconds=0,attachments=[]) if row is None else json.loads(self.aes.decrypt(row['nonce'],row['payload'],self.aad(owner,case_id,row['revision'])))
        value['attachments']=[]
        for attachment in conn.execute('SELECT * FROM attachments WHERE owner=? AND case_id=? ORDER BY id',(owner,case_id)):
            item=json.loads(self.aes.decrypt(attachment['nonce'],attachment['payload'],canonical([VERSION,owner,case_id,attachment['id']])))
            value['attachments'].append({k:v for k,v in item.items() if k!='content'})
        return value

    def attach(self,scope,case_id,name,content):
        if not isinstance(name,str) or not 1<=len(name)<=160 or any(c in name for c in '/\\\r\n\x00'):
            fail(422,'ATTACHMENT_NAME','Tên tài liệu không hợp lệ.','Dùng tên tệp ngắn, không có đường dẫn.')
        try:raw=base64.b64decode(content,validate=True)
        except (ValueError,TypeError):fail(422,'ATTACHMENT_CONTENT','Tài liệu không hợp lệ.','Chọn lại tệp PDF, PNG hoặc JPEG.')
        if not 0<len(raw)<=2*1024*1024:fail(413,'ATTACHMENT_LIMIT','Mỗi tài liệu tối đa 2 MB.','Giảm kích thước tệp rồi thử lại.')
        mime='application/pdf' if raw.startswith(b'%PDF-') else 'image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else None
        if mime is None:fail(415,'ATTACHMENT_TYPE','Chỉ nhận PDF, PNG hoặc JPEG.','Xuất tài liệu sang một định dạng được hỗ trợ.')
        owner=self.owner(scope);identity='att_'+hashlib.sha256(raw).hexdigest()
        value=dict(id=identity,name=name,mime=mime,size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),content=base64.b64encode(raw).decode(),original_verified=False,actor_id=scope.actor_id,uploaded_at=time.time())
        with self.transaction() as conn:
            if conn.execute('SELECT 1 FROM attachments WHERE owner=? AND case_id=? AND id=?',(owner,case_id,identity)).fetchone():return identity
            if conn.execute('SELECT count(*) FROM attachments WHERE owner=? AND case_id=?',(owner,case_id)).fetchone()[0]>=10:
                fail(413,'ATTACHMENT_COUNT','Mỗi phiếu tối đa 10 tài liệu.','Gộp các trang trong một PDF tối đa 2 MB.')
            nonce=os.urandom(12);blob=self.aes.encrypt(nonce,canonical(value),canonical([VERSION,owner,case_id,identity]))
            conn.execute('INSERT INTO attachments VALUES (?,?,?,?,?)',(owner,case_id,identity,nonce,blob))
        return identity

    def attachment(self,scope,case_id,identity):
        import json
        owner=self.owner(scope)
        with self.transaction() as conn:
            row=conn.execute('SELECT * FROM attachments WHERE owner=? AND case_id=? AND id=?',(owner,case_id,identity)).fetchone()
            if row is None:fail(404,'ATTACHMENT_NOT_FOUND','Không tìm thấy tài liệu trong phiếu này.','Mở lại đúng phiếu rà.')
            return json.loads(self.aes.decrypt(row['nonce'],row['payload'],canonical([VERSION,owner,case_id,identity])))

    def get(self,scope,case_id):
        with self.transaction() as conn:return self._read(conn,self.owner(scope),case_id)

    def start(self,scope,case_id):
        owner=self.owner(scope);identity=owner,case_id
        with self.lock:
            now=self.clock();old=self.leases.get(identity)
            if old and now-old['beat']<=15:
                fail(409,'REVIEW_ALREADY_OPEN','Phiếu đang được rà ở một cửa sổ khác.','Dừng đồng hồ ở cửa sổ đó hoặc chờ 15 giây rồi thử lại.')
            token=secrets.token_hex(24);self.leases[identity]=dict(token=token,beat=now,seconds=0.)
            return dict(lease=token,heartbeat_seconds=5,max_gap_seconds=15)

    def _tick(self,owner,case_id,token):
        lease=self.leases.get((owner,case_id))
        if not lease or not isinstance(token,str) or not secrets.compare_digest(lease['token'],token):
            fail(409,'REVIEW_TIMER_REQUIRED','Đồng hồ chưa chạy hoặc phiên đã thay đổi.','Bấm Bắt đầu để rà tiếp; thời gian đã lưu vẫn được giữ.')
        now=self.clock();gap=max(0,now-lease['beat']);lease['beat']=now
        if gap<=15:lease['seconds']+=gap
        return lease

    def heartbeat(self,scope,case_id,token):
        with self.lock:
            lease=self._tick(self.owner(scope),case_id,token)
            return dict(active_seconds=round(lease['seconds'],3),timing_basis='server_connected_active_time')

    def save(self,scope,case_id,expected,feedback,allowed_evidence,lease_token,request_id):
        fields={'outcome','usefulness','explanation','action','missing_materials','evidence_ids','checks_completed'}
        if not isinstance(feedback,dict) or set(feedback)!=fields:
            fail(400,'REVIEW_FIELDS','Phiếu thiếu trường hoặc có trường không được nhận.','Tải lại phiếu và điền đúng các ô trên màn hình.')
        if feedback['outcome'] not in OUTCOMES or feedback['usefulness'] not in {'yes','no','not_assessed'}:
            fail(422,'REVIEW_OUTCOME','Chưa chọn kết quả hợp lệ.','Chọn kết quả nghiệp vụ và mức hữu ích riêng.')
        for field in ('explanation','action','missing_materials'):
            if not isinstance(feedback[field],str) or len(feedback[field])>4000:
                fail(422,'REVIEW_TEXT','Nội dung tối đa 4.000 ký tự mỗi ô.','Rút gọn nội dung rồi lưu lại.')
        if not feedback['explanation'].strip() or type(feedback['checks_completed']) is not bool:
            fail(422,'REVIEW_EXPLANATION','Cần giải thích những gì đã kiểm tra.','Ghi căn cứ và kết quả đối chiếu.')
        refs=feedback['evidence_ids']
        if not isinstance(refs,list) or any(not isinstance(x,str) for x in refs) or len(set(refs))!=len(refs):
            fail(422,'REVIEW_EVIDENCE','Danh sách căn cứ không hợp lệ.','Chọn các căn cứ đã xem trên phiếu.')
        if feedback['outcome']!='inconclusive' and (not refs or not feedback['checks_completed']):
            fail(422,'REVIEW_CHECKS','Chưa xác nhận đủ căn cứ để kết luận.','Đối chiếu tài liệu hoặc chọn Chưa đủ căn cứ.')
        if (feedback['outcome']=='inconclusive' and not feedback['missing_materials'].strip()) or ((feedback['usefulness']=='yes' or feedback['outcome'] in {'inconclusive','confirmed_risk'}) and not feedback['action'].strip()):
            fail(422,'REVIEW_ACTION','Cần ghi tài liệu còn thiếu và hành động tiếp theo.','Ghi rõ cần ai bổ sung hoặc xử lý điều gì.')
        if type(expected) is not int or expected<0 or not isinstance(request_id,str) or not 8<=len(request_id)<=128:
            fail(400,'REVIEW_REVISION','Thiếu phiên bản hoặc mã yêu cầu lưu.','Tải lại phiếu rồi thử lưu lại.')
        owner=self.owner(scope);digest=hashlib.sha256(canonical([expected,feedback])).hexdigest()
        with self.lock,self.transaction() as conn:
            old=self._read(conn,owner,case_id)
            for event in old['history']:
                if event['request_id']==request_id:
                    if event['request_hash']!=digest:fail(409,'REVIEW_REPLAY_CONFLICT','Mã yêu cầu đã dùng cho nội dung khác.','Tải lại kết quả đã lưu.')
                    return old
            if old['revision']!=expected:fail(409,'REVIEW_CONFLICT','Phiếu đã được cập nhật ở nơi khác.','Tải lại phiếu trước khi sửa; không ghi đè kết quả mới hơn.')
            allowed=set(allowed_evidence)|{a['id'] for a in old['attachments']}
            if not set(refs)<=allowed:fail(422,'REVIEW_FOREIGN_EVIDENCE','Có căn cứ ngoài tập nguồn của phiếu.','Chọn đúng căn cứ được liệt kê trong phiếu.')
            lease=self._tick(owner,case_id,lease_token)
            value=deepcopy(old);value.update(revision=expected+1,feedback=deepcopy(feedback),active_seconds=round(old['active_seconds']+lease['seconds'],3))
            value['history'].append(dict(revision=expected+1,request_id=request_id,request_hash=digest,actor_id=scope.actor_id,at=time.time(),feedback=deepcopy(feedback),active_seconds=value['active_seconds']))
            if len(value['history'])>100:fail(409,'REVIEW_REVISION_LIMIT','Phiếu đã đạt 100 lần sửa.','Người quản lý cần lưu trữ và mở đợt rà mới.')
            nonce=os.urandom(12);blob=self.aes.encrypt(nonce,canonical(value),self.aad(owner,case_id,expected+1))
            conn.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',(owner,case_id,expected+1,nonce,blob))
            del self.leases[(owner,case_id)]
            return value
