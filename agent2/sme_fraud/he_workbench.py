"""Optional enterprise HE web adapter. No HE dependency is loaded by default."""
import hashlib
import hmac
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit

from finance_input.json_io import loads
from finance_input.validation import stamp
from .auth import AuthError
from .import_files import ImportFailure, fail
from .snapshot_api import _key
from .validation_api import authorize_request, read_json, respond_failure

ROUTE = re.compile(r'/api/v1/companies/([A-Za-z0-9_.:-]{1,128})/he/(datasets|runs|jobs(?:/(herun_[a-f0-9]{32})(?:/(result|resume))?)?)\Z')


def saved_runs(jobs,scope):
    owned=[];children=set();child_keys=set();stores=[jobs.store]
    if hasattr(jobs,'legacy'):stores.append(jobs.legacy.store)
    for number,store in enumerate(stores):
        with store.transaction() as conn:
            rows=conn.execute('SELECT * FROM jobs WHERE tenant=? AND company=? AND actor=? ORDER BY created DESC LIMIT 512',store.owner(scope)).fetchall()
            for row in rows:
                if number==0 and hasattr(jobs,'legacy'):
                    from experiments.he_inference.protocol import canonical
                    child_keys.add(hmac.new(jobs.legacy.store.mac_key,canonical([*store.owner(scope),'four:'+row['id']]),hashlib.sha256).hexdigest())
                if number==1 and row['idem'] in child_keys:continue
                data=store.open(row)
                if number==0 and data.get('legacy_job'):children.add(data['legacy_job'])
                owned.append(dict(job_id=row['id'],snapshot_id=data['request']['snapshot_id'],as_of=data['request']['as_of'],phase=row['phase'],
                    created_at=row['created'],row_count=(data.get('result') or {}).get('row_count'),analysis_mode='four_encrypted_branches' if hasattr(jobs,'legacy') and number==0 else 'mahalanobis'))
    values=sorted((r for r in owned if r['job_id'] not in children),key=lambda r:(r['created_at'],r['job_id']),reverse=True)
    return dict(runs=values[:50],limited=len(values)>50)


class HEWorkbench:
    def __init__(self, node, bindings_file):
        if node.jobs is None:
            raise ValueError('HE web requires durable jobs')
        self.node, self.bindings_file = node, Path(bindings_file)

    def selection(self, scope):
        try:
            with self.bindings_file.open('rb') as stream:
                raw = stream.read(65537)
            value = loads(raw)
            if len(raw) > 65536 or not isinstance(value, dict) or set(value) != {'version', 'bindings'} or value['version'] != 'he-ui-bindings/1.0.0':
                raise ValueError()
            if not isinstance(value['bindings'], list) or len(value['bindings']) > 256:
                raise ValueError()
            seen = set(); selected = None
            for row in value['bindings']:
                if not isinstance(row, dict) or set(row) != {'tenant_id', 'company_id', 'artifact_id'}:
                    raise ValueError()
                if not all(isinstance(row[k], str) for k in row) or not all(re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', row[k]) for k in ('tenant_id','company_id')) or not re.fullmatch(r'mth_[a-f0-9]{64}', row['artifact_id']):
                    raise ValueError()
                identity = row['tenant_id'], row['company_id']
                if identity in seen:
                    raise ValueError()
                seen.add(identity)
                if identity == (scope.tenant_id, next(iter(scope.company_ids))):
                    selected = row['artifact_id']
            return selected
        except (OSError, ValueError, TypeError, RecursionError):
            fail(503, 'HE_BINDINGS_UNAVAILABLE', 'Chưa đọc được cấu hình phân tích bảo mật.', 'Người quản lý cần kiểm tra cấu hình model theo doanh nghiệp.')

    def datasets(self, scope, recheck):
        from experiments.he_inference.registry_export import ReadOnlySnapshots, _load_model
        from experiments.he_inference.protocol import HEUnavailable
        selected = self.selection(scope)
        compatible = selected is not None
        message = '' if selected else 'Chưa có model được cấu hình cho doanh nghiệp này. Người quản lý cần chuẩn bị model trước khi chạy.'
        if selected:
            try:
                _load_model(self.node.model_db, scope, selected, recheck, metadata_only=True)
            except (HEUnavailable, ImportFailure):
                compatible = False
                message = 'Model chưa có hoặc không tương thích. Người quản lý cần kiểm tra phiên bản trước khi chạy.'
        store = ReadOnlySnapshots(self.node.snapshot_db)
        with store._transaction(scope, recheck) as conn:
            tenant, company, _ = store._scope(scope)
            ids = [r[0] for r in conn.execute('SELECT snapshot_id FROM snapshots WHERE tenant_id=? AND company_id=? ORDER BY rowid DESC', (tenant, company))]
            rows = []; has_more = False
            for sid in ids:
                manifest, raw = store._read_snapshot(conn, scope, sid)
                if manifest.get('contract_version') == 'agent2-rule-snapshot/1.0.0':
                    continue
                if len(rows) >= 100:
                    has_more = True
                    break
                source = loads(raw); events = sorted((str(t['effective_at']) for t in source['transactions']), key=stamp)
                rows.append(dict(snapshot_id=sid, created_at=manifest['created_at'], checksum=manifest['checksum'],
                    record_count=len(source['transactions']), period_start=events[0] if events else None,
                    period_end=events[-1] if events else None, as_of=manifest['created_at'],
                    simulated_records=sum(bool(t.get('source',{}).get('is_simulated')) for t in source['transactions'])))
        owner = hashlib.sha256((scope.tenant_id + '\0' + scope.actor_id).encode()).hexdigest()
        worker_ready=False
        try:worker_ready=self.node.check_worker(scope)
        except Exception:
            if not message:message='Chưa kết nối được bộ xử lý hoặc chưa xác nhận được khóa. Kết nối lại để tiếp tục.'
        return dict(owner_id=owner, available=compatible and worker_ready, model_available=compatible,
                    worker_ready=worker_ready,datasets=rows, limited=has_more, message=message)

    def submit(self, scope, recheck, company, header, key, body):
        from experiments.he_inference.registry_export import ReadOnlySnapshots
        if not isinstance(body, dict) or set(body) != {'snapshot_id'} or not isinstance(body['snapshot_id'], str) or not re.fullmatch(r'snp_[a-f0-9]{32}', body['snapshot_id']):
            fail(400, 'HE_REQUEST_FIELDS', 'Chọn đúng một bản dữ liệu đã lưu.', 'Không gửi model, khóa hoặc thiết lập phân tích từ giao diện.')
        artifact = self.selection(scope)
        if artifact is None:
            fail(409, 'HE_MODEL_REQUIRED', 'Doanh nghiệp chưa có model phân tích bảo mật.', 'Người quản lý cần chuẩn bị model trước khi chạy.')
        manifest = ReadOnlySnapshots(self.node.snapshot_db).get_snapshot(scope, body['snapshot_id'], recheck)
        if manifest.get('contract_version') == 'agent2-rule-snapshot/1.0.0':
            fail(422, 'HE_PROFILE_UNSUPPORTED', 'Bản dữ liệu nguồn 35 luật chưa hỗ trợ phân tích mã hóa HE.', 'Dùng nút Xem 35 luật tại node doanh nghiệp ở màn hình Nhập dữ liệu.')
        if recheck() != scope:
            fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi.', 'Tải lại danh sách doanh nghiệp.')
        return self.node.jobs.submit(company, header, key, dict(artifact_id=artifact, snapshot_id=body['snapshot_id'], as_of=manifest['created_at']))


def handle_he_workbench(handler, authorizer, backend, method):
    route = ROUTE.fullmatch(urlsplit(handler.path).path)
    if route is None:
        return False
    try:
        company, action, job, detail = route.groups()
        scope, recheck = authorize_request(handler, authorizer, company)
        header = handler.headers.get_all('Authorization', [None])[0]
        if backend is None:
            fail(503, 'HE_NOT_CONFIGURED', 'Phân tích bảo mật chưa được bật cho node này.', 'Người quản lý cần cấu hình node và model; không có phân tích thay thế tự động.')
        if method=='GET' and action=='runs':
            value=saved_runs(backend.node.jobs,scope);status=200
        elif method == 'GET' and action == 'datasets':
            value = backend.datasets(scope, recheck); status = 200
            try:
                header=handler.headers.get_all('Authorization',[None])[0]
                value['can_manage']=hasattr(authorizer,'authorize_director') and authorizer.authorize_director(header,company)==scope
            except AuthError:value['can_manage']=False
        else:
            header = handler.headers.get_all('Authorization', [None])[0]
            if method == 'POST' and action == 'jobs':
                value = backend.submit(scope, recheck, company, header, _key(handler), read_json(handler)); status = 202
            elif method == 'GET' and job and detail == 'result':
                status, value = backend.node.jobs.result(company, header, job)
            elif method == 'GET' and job and detail is None:
                value = backend.node.jobs.status(company, header, job); status = 200
            elif method == 'POST' and job and detail == 'resume':
                if read_json(handler) != {}:
                    fail(400, 'HE_RESUME_FIELDS', 'Không cần thay đổi dữ liệu để tiếp tục.', 'Gửi yêu cầu tiếp tục phiên hiện tại.')
                value = backend.node.jobs.resume(company, header, job); status = 202
            else:
                fail(405, 'METHOD_NOT_ALLOWED', 'Thao tác không được hỗ trợ.', 'Dùng đúng thao tác trên giao diện.')
        if recheck() != scope:
            fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi.', 'Đăng nhập lại để tiếp tục.')
        # Status URLs from the node belong to its internal API, not the browser.
        if isinstance(value, dict) and 'job_id' in value:
            value = {k:v for k,v in value.items() if k in {'job_id','phase','message','attempts','reason','created_at','updated_at','events','poll_after_ms'}}
        if isinstance(value,dict) and value.get('version')=='he-four-branch-result/1.0.0':
            def money_strings(item):
                if isinstance(item,dict):return {k:str(v) if k.endswith('_vnd') and type(v) is int else money_strings(v) for k,v in item.items()}
                if isinstance(item,list):return [money_strings(v) for v in item]
                return item
            value=money_strings(value)
        if isinstance(value,dict) and ('rows' in value or 'runs' in value):
            director=False
            try:director=hasattr(authorizer,'authorize_director') and authorizer.authorize_director(header,company)==scope
            except AuthError:pass
            if not director:
                if 'rows' in value:
                    from .he_result_view import review_result
                    value=review_result(value)
                else:
                    value=dict(value,runs=[dict(r,analysis_mode='four_encrypted_branches' if r.get('analysis_mode')=='four_encrypted_branches' else 'encrypted_analysis') for r in value['runs']])
        if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền truy cập đã thay đổi.','Mở lại từ Portal.')
        handler.respond(status, value)
    except (AuthError, ImportFailure) as error:
        respond_failure(handler, error)
    except Exception as error:
        code = getattr(error, 'code', '')
        status = getattr(error, 'status', 503)
        if status not in (400,401,403,404,409,410,413,422,429,503): status = 503
        message = ('Không có phiên trong phạm vi được phép.' if status == 404 else
                   'Yêu cầu cũ không còn khớp dữ liệu hoặc cấu hình hiện tại.' if code == 'IDEMPOTENCY_CONFLICT' else
                   'Chưa thể hoàn tất phân tích bảo mật. Phiên đã lưu vẫn được giữ để kiểm tra hoặc tiếp tục.')
        respond_failure(handler, AuthError(status, 'HE_REQUEST_UNAVAILABLE', message, 'Kiểm tra kết nối và quyền truy cập rồi thử lại cùng yêu cầu.'))
    return True
