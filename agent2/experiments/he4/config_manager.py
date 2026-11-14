"""Manager-only drafts and explicit offline fit. No business-policy defaults."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from finance_input.json_io import loads
from sme_fraud.import_files import canonical,digest,fail
from sme_fraud.method_jobs import validate_config,run_fit_job
from sme_fraud.method_store import MethodStore,require_fit
from experiments.he_inference import registry_fit
from .snapshot_adapter import load_statistics
from experiments.he_inference.registry_export import _load_model


class Journal:
    def __init__(self,path,master):
        self.path=Path(path);keys=HKDF(algorithm=hashes.SHA256(),length=64,salt=b'he4-config-v1',info=b'configuration-journal').derive(master)
        self.aes=AESGCM(keys[:32]);self.mac=keys[32:]
        with self.tx() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS events (tenant TEXT,company TEXT,revision INTEGER,actor TEXT,idem TEXT,digest TEXT,nonce BLOB,payload BLOB,PRIMARY KEY(tenant,company,revision),UNIQUE(tenant,company,actor,idem))')
            for op in ('UPDATE','DELETE'):conn.execute(f"CREATE TRIGGER IF NOT EXISTS events_{op.lower()} BEFORE {op} ON events BEGIN SELECT RAISE(ABORT,'immutable configuration event'); END")
    @contextmanager
    def tx(self):
        conn=sqlite3.connect(self.path,isolation_level=None,timeout=15);conn.row_factory=sqlite3.Row
        try:conn.execute('PRAGMA synchronous=FULL');conn.execute('BEGIN IMMEDIATE');yield conn;conn.commit()
        finally:conn.close()
    @staticmethod
    def identity(scope):return scope.tenant_id,next(iter(scope.company_ids))
    def opened(self,row):return loads(self.aes.decrypt(row['nonce'],row['payload'],canonical({k:row[k] for k in ('tenant','company','revision','actor','idem','digest')})))
    def get(self,scope):
        with self.tx() as conn:
            row=conn.execute('SELECT * FROM events WHERE tenant=? AND company=? ORDER BY revision DESC LIMIT 1',self.identity(scope)).fetchone()
            return self.opened(row) if row else dict(revision=0,draft=None,fit=None,history=[])
    def save(self,scope,expected,key,change,operation):
        identity=self.identity(scope);idem=hmac.new(self.mac,canonical([*identity,scope.actor_id,key]),hashlib.sha256).hexdigest()
        fingerprint=digest(canonical([expected,operation,change]))
        with self.tx() as conn:
            old=conn.execute('SELECT * FROM events WHERE tenant=? AND company=? AND actor=? AND idem=?',(*identity,scope.actor_id,idem)).fetchone()
            if old:
                if old['digest']!=fingerprint:fail(409,'CONFIG_IDEMPOTENCY','Yêu cầu đã dùng cho nội dung khác.','Tải lại cấu hình đã lưu.')
                return self.opened(old)
            previous=conn.execute('SELECT * FROM events WHERE tenant=? AND company=? ORDER BY revision DESC LIMIT 1',identity).fetchone()
            value=self.opened(previous) if previous else dict(revision=0,draft=None,fit=None,history=[])
            if type(expected) is not int or value['revision']!=expected:fail(409,'CONFIG_REVISION','Cấu hình đã được cập nhật ở nơi khác.','Tải lại rồi sửa trên phiên bản mới.')
            value.update(deepcopy(change),revision=expected+1)
            value['history'].append(dict(revision=expected+1,operation=operation,actor=scope.actor_id,at=time.time()))
            row=dict(tenant=identity[0],company=identity[1],revision=expected+1,actor=scope.actor_id,idem=idem,digest=fingerprint)
            nonce=os.urandom(12);payload=self.aes.encrypt(nonce,canonical(value),canonical(row))
            conn.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',(*identity,expected+1,scope.actor_id,idem,fingerprint,nonce,payload));return value

    def receipt(self,scope,key,expected,change,operation):
        identity=self.identity(scope);idem=hmac.new(self.mac,canonical([*identity,scope.actor_id,key]),hashlib.sha256).hexdigest()
        with self.tx() as conn:row=conn.execute('SELECT * FROM events WHERE tenant=? AND company=? AND actor=? AND idem=?',(*identity,scope.actor_id,idem)).fetchone()
        if row is None:return None
        if row['digest']!=digest(canonical([expected,operation,change])):fail(409,'CONFIG_IDEMPOTENCY','Mã yêu cầu đã dùng cho nội dung khác.','Tải lại cấu hình hiện hành.')
        return self.opened(row)


class Manager:
    def __init__(self,backend,snapshots):
        self.backend,self.snapshots=backend,snapshots;self.jobs=backend.node.jobs;self.auth=backend.node.auth
        self.journal=Journal(self.jobs.store.path.with_name('configurations.sqlite3'),self.jobs.store.mac_key)
        self.epoch=uuid.uuid4().hex;self.lock=threading.RLock();self.running=set()

    def get(self,scope):
        value=self.journal.get(scope)
        if value['fit'] and value['fit']['status']=='fitting' and value['fit']['epoch']!=self.epoch:value['fit']=dict(value['fit'],status='interrupted')
        value.update(active=self.backend.settings.capture(scope)['binding'],can_fit='model.fit' in scope.permissions,
            analysis_mode='technical_shadow',business_policy=dict(weights=None,budget=None,mandatory_routing=None,production_approved=False))
        return value

    def draft(self,scope,body,key):
        with self.lock:return self._draft(scope,body,key)

    def _draft(self,scope,body,key):
        require_fit(scope)
        if set(body)!={'expected_revision','config'}:fail(400,'CONFIG_FIELDS','Yêu cầu cấu hình không hợp lệ.','Dùng các trường trên màn hình.')
        try:cfg=validate_config(body['config'])
        except (TypeError,ValueError):fail(422,'CONFIG_INVALID','Kỳ dữ liệu hoặc cấu hình chưa hợp lệ.','Điền đủ ngày giờ; kỳ lịch sử phải kết thúc trước tập đối chiếu và kỳ đánh giá. Chọn dữ liệu đã lưu cùng doanh nghiệp, hai feature hiện có và ít nhất 20 dòng lịch sử.')
        if cfg['method_id']!='robust_z' or cfg['selected_columns']!=['log_abs_amount','event_hour_sin'] or cfg['missing_policy']!='strict' or cfg['minimum_history']<20 or not cfg['profile_id'].startswith('technical-'):fail(422,'CONFIG_PROFILE','Phiên bản hiện hỗ trợ profile kỹ thuật với hai đầu vào đã kiểm chứng.','Dùng technical- profile, strict, tối thiểu 20 dòng lịch sử và hai feature hiện có.')
        self.snapshots.get_snapshot(scope,cfg['snapshot_id'])
        state=self.journal.get(scope)
        if state['fit'] and state['fit']['status']=='fitting' and state['fit']['epoch']==self.epoch:fail(409,'CONFIG_FIT_RUNNING','Đang chuẩn bị model.','Chờ hoàn tất trước khi đổi cấu hình.')
        return self.journal.save(scope,body['expected_revision'],key,dict(draft=cfg,fit=None,activation=None),'draft')

    def fit(self,scope,header,expected,key):
        with self.lock:return self._request_fit(scope,header,expected,key)

    def _request_fit(self,scope,header,expected,key):
        require_fit(scope);state=self.journal.get(scope)
        if state['draft'] is None:fail(409,'CONFIG_DRAFT_REQUIRED','Chưa có cấu hình nháp.','Lưu cấu hình đã kiểm tra trước.')
        identity=self.journal.identity(scope)
        fit_id='fit4_'+digest(canonical([*identity,scope.actor_id,key,expected]))[:32]
        change=dict(fit=dict(status='fitting',epoch=self.epoch,fit_id=fit_id))
        # Replaying a completed fit request must not start its thread again.
        if state['fit'] and state['fit']['fit_id']==fit_id and state['fit']['status']!='fitting':return state
        with self.lock:
            if identity in self.running:fail(409,'CONFIG_FIT_RUNNING','Đang chuẩn bị model.','Chờ hoàn tất rồi tải lại.')
            value=self.journal.save(scope,expected,key,change,'fit_requested')
            if value['fit']['status']!='fitting' or value['fit']['epoch']!=self.epoch:return value
            self.running.add(identity)
        thread=threading.Thread(target=self._fit,args=(scope,header,value,key),daemon=True);thread.start();return value

    def _fit(self,scope,header,state,key):
        company=next(iter(scope.company_ids));cfg=state['draft'];models=MethodStore(self.backend.node.model_db)
        try:
            ml_cfg=dict(cfg,version=registry_fit.CONFIG_VERSION,method_id=registry_fit.METHOD)
            ml=registry_fit.run_fit_job(self.snapshots,models,self.auth,header,company,ml_cfg,key+'-ml')
            stats=run_fit_job(self.snapshots,models,self.auth,header,company,cfg,key+'-statistics')
            if ml.get('error') or stats.get('error') or ml['job']['status']!='succeeded' or stats['job']['status']!='succeeded':raise ValueError('fit incomplete')
            current=self.auth.authorize_director(header,company);require_fit(current)
            if current!=scope:raise ValueError('auth changed')
            fit=dict(state['fit'],status='succeeded',ml_artifact_id=ml['job']['artifact_id'],statistics_artifact_id=stats['job']['artifact_id'])
        except Exception:fit=dict(state['fit'],status='failed',reason='FIT_INCOMPLETE_OR_REVOKED')
        try:self.journal.save(scope,state['revision'],key+'-finished',dict(fit=fit),'fit_finished')
        finally:
            with self.lock:self.running.discard(self.journal.identity(scope))

    def activate(self,scope,header,expected,key):
        with self.backend.settings.mutation_lock,self.lock:
            return self._activate(scope,header,expected,key)

    def _activate(self,scope,header,expected,key):
        require_fit(scope);state=self.journal.get(scope);fit=state['fit']
        if not fit or fit['status']!='succeeded':fail(409,'CONFIG_NOT_READY','Chưa có cặp model đã fit thành công trên cấu hình này.','Kiểm tra trạng thái và tải lại cấu hình.')
        change=dict(activation=dict(status='requested',fit_id=fit['fit_id']))
        replay=self.journal.receipt(scope,key,expected,change,'activation_requested')
        if replay and (state.get('activation') or {}).get('status')=='active' and state['activation']['fit_id']==fit['fit_id']:return state
        if not replay and expected!=state['revision']:fail(409,'CONFIG_REVISION','Cấu hình đã thay đổi.','Tải lại trước khi kích hoạt.')
        check=lambda:self.auth.authorize_director(header,next(iter(scope.company_ids)))
        _load_model(self.backend.node.model_db,scope,fit['ml_artifact_id'],check,metadata_only=True)
        loaded,reason=load_statistics(self.backend.node.model_db,scope,fit['statistics_artifact_id'],check)
        if loaded is None:fail(409,'CONFIG_INCOMPATIBLE','Phiên bản thống kê không tương thích.','Chuẩn bị lại model đúng contract hiện tại.')
        for store in (self.jobs.store,self.jobs.legacy.store):
            with store.transaction() as conn:
                count=conn.execute("SELECT count(*) FROM jobs WHERE tenant=? AND company=? AND phase NOT IN ('completed','failed','expired')",self.journal.identity(scope)).fetchone()[0]
            if count:fail(409,'CONFIG_PENDING_RUNS','Doanh nghiệp đang có yêu cầu phân tích chưa hoàn tất.','Hoàn tất các yêu cầu đang lưu trước khi đổi phiên bản model.')
        path=Path(self.backend.settings.config['bindings_file'])
        value=loads(path.read_bytes());rows=deepcopy(value['bindings'])
        if sum((row['tenant_id'],row['company_id'])==self.journal.identity(scope) for row in rows)!=1:fail(409,'CONFIG_BINDING_REQUIRED','Chưa có cấu hình cho doanh nghiệp này.','Người vận hành cần chuẩn bị node và khóa trước khi kích hoạt.')
        for row in rows:
            if (row['tenant_id'],row['company_id'])==self.journal.identity(scope):row.update(ml_artifact_id=fit['ml_artifact_id'],statistics_artifact_id=fit['statistics_artifact_id'])
        if check()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Mở lại từ Portal.')
        pending=replay or self.journal.save(scope,expected,key,change,'activation_requested')
        temporary=path.with_name(path.name+'.pending-'+uuid.uuid4().hex)
        temporary.write_bytes(canonical(dict(version='he4-company-bindings/1.1.0',bindings=rows)));os.replace(temporary,path)
        return self.journal.save(scope,pending['revision'],key+'-finished',dict(activation=dict(status='active',fit_id=fit['fit_id'],mode='technical_shadow')),'activation_finished')
