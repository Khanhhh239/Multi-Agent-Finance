"""Company-scoped immutable model bundles and durable offline fit receipts."""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import uuid

from finance_input.json_io import loads
from .import_files import canonical, digest, fail
from .method_adapters import LocalArtifact, ARTIFACT_VERSION, _scope
from .snapshot_features import utc

APPLICATION_ID = 1093817138
ARTIFACT_ID = re.compile(r'mth_[a-f0-9]{64}\Z')


def require_fit(scope):
    _scope(scope)
    if 'model.fit' not in scope.permissions:
        fail(403,'MODEL_FIT_DENIED','Chưa có quyền fit model cho doanh nghiệp này.','Cần permission model.fit được cấp từ backend; quyền đọc/chấm không tự cấp quyền fit.')


class MethodStore:
    def __init__(self, path, clock=None, *, read_only=False):
        self.path=Path(path).resolve();self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.read_only=read_only
        if read_only and not self.path.exists():return
        if not read_only:self.path.parent.mkdir(parents=True,exist_ok=True)
        try:
            with closing(self._connect()) as conn:
                self._check_storage(conn,allow_new=not read_only)
                if read_only:return
                conn.execute('PRAGMA journal_mode=WAL')
                sql=Path(__file__).with_name('method_storage.sql').read_text('utf-8')
                for table in ('method_artifacts','fit_events'):
                    for action in ('UPDATE','DELETE'):
                        sql+=f"\nCREATE TRIGGER IF NOT EXISTS {table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable model artifact/audit'); END;\n"
                conn.executescript('BEGIN IMMEDIATE;\n'+sql+'\nCOMMIT;')
        except sqlite3.DatabaseError:
            fail(503,'MODEL_STORAGE_VERSION','Không đọc được kho model đúng định dạng.','Kiểm tra DB model riêng; không nạp file model cũ thay DB.')

    def _connect(self):
        conn=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=30,isolation_level=None) if self.read_only else sqlite3.connect(self.path,timeout=30,isolation_level=None)
        try:
            conn.row_factory=sqlite3.Row
            conn.execute('PRAGMA foreign_keys=ON');conn.execute('PRAGMA synchronous=FULL')
            return conn
        except BaseException:
            conn.close();raise

    def _now(self):return self.clock().astimezone(timezone.utc).isoformat()

    @staticmethod
    def _check_storage(conn,*,allow_new=False):
        app=conn.execute('PRAGMA application_id').fetchone()[0];version=conn.execute('PRAGMA user_version').fetchone()[0]
        tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if allow_new and app==0 and not tables:return
        if app!=APPLICATION_ID or version!=1 or not {'fit_jobs','method_artifacts','fit_events'}<=tables:
            fail(503,'MODEL_STORAGE_VERSION','Đường dẫn không phải kho model phiên bản được hỗ trợ.','Dùng DB model mới riêng; không migrate DB/pickle cũ.')

    @contextmanager
    def _transaction(self,scope,recheck=None,*,fit=False,write=False,deadline=None):
        require_fit(scope) if fit else _scope(scope)
        if write and self.read_only:fail(403,'MODEL_STORE_READ_ONLY','Kho model được mở chỉ để đọc.','Dùng job fit riêng khi cần tạo phiên bản mới.')
        conn=self._connect()
        try:
            conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            self._guard(scope,recheck)
            self._check_storage(conn)
            yield conn
            self._guard(scope,recheck)
            if deadline and utc(self._now())>=utc(deadline):
                fail(409,'FIT_PERIOD_STARTED','Kỳ prospective đã bắt đầu trước khi công bố model.','Tạo job cho kỳ tương lai khác; artifact chưa được công bố.')
            conn.execute('COMMIT')
        except BaseException:
            if conn.in_transaction:conn.execute('ROLLBACK')
            raise
        finally:conn.close()

    @staticmethod
    def _guard(scope,recheck):
        if recheck is not None and recheck()!=scope:
            fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi khi xử lý model/job.','Chạy lại theo quyền hiện hành; chưa công bố artifact mới.')

    @staticmethod
    def _integrity():
        fail(500,'MODEL_ARTIFACT_INTEGRITY','Checksum hoặc metadata kho model không khớp.','Đối chiếu kho/backup; không bỏ kiểm tra hoặc tự ghi đè model.')

    def _job(self,conn,scope,job_id):
        tenant,company=_scope(scope)
        row=conn.execute('SELECT * FROM fit_jobs WHERE job_id=? AND tenant_id=? AND company_id=?',(job_id,tenant,company)).fetchone()
        if row is None:fail(404,'FIT_JOB_NOT_FOUND','Không có fit job trong phạm vi được phép.','Chọn đúng doanh nghiệp và job.')
        if not isinstance(row['request_json'],bytes) or digest(row['request_json'])!=row['request_hash']:self._integrity()
        return row

    @staticmethod
    def _view(row):
        return {k:row[k] for k in ('job_id','tenant_id','company_id','actor_id','request_hash','status','artifact_id','failure_code','created_at','finished_at')}

    def _event(self,conn,scope,job_id,event,detail):
        tenant,company=_scope(scope)
        conn.execute('INSERT INTO fit_events(job_id,tenant_id,company_id,actor_id,event,created_at,detail_json) VALUES (?,?,?,?,?,?,?)',
                     (job_id,tenant,company,scope.actor_id,event,self._now(),canonical(detail)))

    def begin_fit(self,scope,request,key,recheck=None):
        if not isinstance(key,str) or re.fullmatch(r'[A-Za-z0-9_.:-]{8,128}',key) is None:
            fail(400,'IDEMPOTENCY_KEY','Thiếu hoặc sai Idempotency-Key của fit job.','Giữ một khóa 8–128 ký tự cho mỗi yêu cầu.')
        encoded=canonical(request);request_hash=digest(encoded)
        with self._transaction(scope,recheck,fit=True,write=True) as conn:
            tenant,company=_scope(scope)
            prior=conn.execute('SELECT * FROM fit_jobs WHERE tenant_id=? AND company_id=? AND actor_id=? AND idempotency_key=?',
                               (tenant,company,scope.actor_id,key)).fetchone()
            if prior is not None:
                if prior['request_hash']!=request_hash:
                    fail(409,'FIT_IDEMPOTENCY_CONFLICT','Khóa fit đã dùng cho snapshot/cấu hình hoặc phiên bản khác.','Giữ yêu cầu cũ khi retry hoặc tạo khóa mới; không ghi đè model.')
                return self._view(self._job(conn,scope,prior['job_id'])),False
            job_id='fit_'+uuid.uuid4().hex
            conn.execute('INSERT INTO fit_jobs VALUES (?,?,?,?,?,?,?,?,?,?,?, ?,?)',
                         (job_id,tenant,company,scope.actor_id,key,request_hash,encoded,'running',None,None,self._now(),None,1))
            self._event(conn,scope,job_id,'queued',dict(request_hash=request_hash))
            self._event(conn,scope,job_id,'running',{})
            return self._view(self._job(conn,scope,job_id)),True

    def get_job(self,scope,job_id,recheck=None):
        require_fit(scope)
        if not self.path.is_file():fail(404,'FIT_JOB_NOT_FOUND','Chưa có kho/job model trong phạm vi được phép.','Tạo fit job riêng trước.')
        with self._transaction(scope,recheck,fit=True) as conn:return self._view(self._job(conn,scope,job_id))

    def _read_artifact(self,conn,scope,artifact_id):
        if not isinstance(artifact_id,str) or ARTIFACT_ID.fullmatch(artifact_id) is None:
            fail(404,'MODEL_ARTIFACT_NOT_FOUND','Không có model trong phạm vi được phép.','Dùng đúng artifact ID của doanh nghiệp.')
        tenant,company=_scope(scope)
        row=conn.execute('SELECT * FROM method_artifacts WHERE artifact_id=? AND tenant_id=? AND company_id=?',(artifact_id,tenant,company)).fetchone()
        if row is None:fail(404,'MODEL_ARTIFACT_NOT_FOUND','Không có model trong phạm vi được phép.','Fit job riêng hoặc chọn artifact đúng doanh nghiệp.')
        raw,payload=row['manifest_json'],row['payload']
        try:
            if not isinstance(raw,bytes) or not isinstance(payload,bytes) or 'mth_'+digest(raw)!=artifact_id:self._integrity()
            manifest=loads(raw)
            if (manifest['tenant_id'],manifest['company_id'])!=(tenant,company) or manifest['payload_sha256']!=digest(payload):self._integrity()
        except (ValueError,KeyError,TypeError):self._integrity()
        return LocalArtifact(artifact_id,raw,payload)

    def get_artifact(self,scope,artifact_id,recheck=None):
        _scope(scope)
        if not self.path.is_file():fail(404,'MODEL_ARTIFACT_NOT_FOUND','Chưa có kho/model trong phạm vi được phép.','Tạo fit job riêng trước.')
        with self._transaction(scope,recheck) as conn:return self._read_artifact(conn,scope,artifact_id)

    def publish(self,scope,job_id,artifact,recheck=None):
        require_fit(scope)
        manifest=loads(artifact.manifest);context=manifest.get('fit_context',{})
        deadline=context.get('evaluation_start') if context.get('evaluation_mode')=='prospective' else None
        with self._transaction(scope,recheck,fit=True,write=True,deadline=deadline) as conn:
            job=self._job(conn,scope,job_id)
            if job['actor_id']!=scope.actor_id or job['status']!='running':
                fail(409,'FIT_JOB_STATE','Job không ở trạng thái running của người thực hiện.','Đọc kết quả job hoặc tạo yêu cầu mới.')
            request=loads(job['request_json'])
            tenant,company=_scope(scope)
            if (manifest.get('version')!=ARTIFACT_VERSION or (manifest.get('tenant_id'),manifest.get('company_id'))!=(tenant,company)
                or context.get('job_id')!=job_id or context.get('request_hash')!=job['request_hash']
                or manifest.get('method_id')!=request['config']['method_id'] or manifest.get('versions')!=request['versions']
                or manifest.get('feature_contract')!=request['feature_contract']
                or manifest.get('history_binding')!=request['snapshot'] or manifest.get('reference_binding')!=request['snapshot']
                or context.get('config')!=request['config'] or manifest.get('preprocess',{}).get('policy')!=request['config']['missing_policy']
                or context.get('job_implementation_sha256')!=request.get('job_implementation_sha256')
                or context.get('job_started_at')!=job['created_at'] or utc(context['created_at'])<utc(job['created_at'])
                or manifest.get('selected_columns')!=request['config']['selected_columns']
                or manifest.get('minimum_history')!=request['config']['minimum_history'] or manifest.get('profile_id')!=request['config']['profile_id']
                or 'mth_'+digest(artifact.manifest)!=artifact.artifact_id or digest(artifact.payload)!=manifest.get('payload_sha256')):
                fail(409,'FIT_ARTIFACT_MISMATCH','Artifact không khớp job/snapshot/contract đã khóa.','Tạo fit job mới từ đúng nguồn/phiên bản; không công bố artifact này.')
            conn.execute('INSERT INTO method_artifacts VALUES (?,?,?,?,?,?,?,?)',
                         (artifact.artifact_id,tenant,company,manifest['method_id'],job_id,artifact.manifest,artifact.payload,self._now()))
            conn.execute("UPDATE fit_jobs SET status='succeeded',artifact_id=?,finished_at=? WHERE job_id=?",(artifact.artifact_id,self._now(),job_id))
            self._event(conn,scope,job_id,'succeeded',dict(artifact_id=artifact.artifact_id,model_version=manifest['model_version']))
            return self._view(self._job(conn,scope,job_id))

    def fail_job(self,scope,job_id,code,recheck=None):
        with self._transaction(scope,recheck,fit=True,write=True) as conn:
            job=self._job(conn,scope,job_id)
            if job['actor_id']!=scope.actor_id or job['status']!='running':return self._view(job)
            conn.execute("UPDATE fit_jobs SET status='failed',failure_code=?,finished_at=? WHERE job_id=?",(code,self._now(),job_id))
            self._event(conn,scope,job_id,'failed',dict(code=code))
            return self._view(self._job(conn,scope,job_id))
