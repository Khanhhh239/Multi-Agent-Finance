"""Director/model-manager HTTP API for Area B (Model Training & Governance)."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from .auth import AuthError
from .import_files import ImportFailure, fail
from .method_store import require_fit
from .snapshot_api import _key
from .validation_api import authorize_request, read_json, respond_failure

ROUTE = re.compile(
    r'/api/v1/companies/([A-Za-z0-9_.:-]{1,128})/model-lifecycle(?:/(profile|train|evaluate|approve|rollback|score-queue|analyze|training-data|lr-fhe/(?:status|worker-health|worker-restart|prepare|train|resume|decrypt|promote)|federated/(?:status|contribute|run|job|approve)|lr-registry(?:/(?:register|validate|transition))?))?\Z'
)


def handle_model_lifecycle(handler, authorizer, lifecycle, method: str) -> bool:
    url = urlsplit(handler.path)
    match = ROUTE.fullmatch(url.path)
    if match is None:
        return False
    try:
        company, action = match.groups()
        scope, _ = authorize_request(handler, authorizer, company)
        header = handler.headers.get_all('Authorization', [None])[0]
        if not hasattr(authorizer, 'authorize_director'):
            fail(403, 'MANAGER_REQUIRED', 'Cần quyền quản trị mô hình cho doanh nghiệp này.', 'Mở bằng tài khoản quản lý được cấp quyền.')
        recheck = lambda: authorizer.authorize_director(header, company)
        dir_scope = recheck()
        if dir_scope != scope:
            fail(403, 'MANAGER_REQUIRED', 'Cần quyền quản trị mô hình của doanh nghiệp.', 'Tải lại quyền từ Portal.')
        if lifecycle is None:
            fail(503, 'MODEL_LIFECYCLE_NOT_CONFIGURED', 'Chưa cấu hình kho huấn luyện và quản lý mô hình.', 'Liên hệ người vận hành.')
        if url.query:
            fail(400, 'MODEL_LIFECYCLE_QUERY', 'Không nhận tham số trên URL.', 'Dùng giao diện Huấn luyện & quản lý mô hình.')

        if method == 'GET' and action is None:
            value = lifecycle.overview(scope, recheck)
        elif action and action.startswith('lr-fhe/'):
            lr_svc = getattr(lifecycle, 'lr_fhe', None)
            if lr_svc is None:
                fail(503, 'LR_FHE_NOT_CONFIGURED', 'Chưa cấu hình dịch vụ huấn luyện LR FHE (worker 8870).', 'Khởi động Agent2 với kho huấn luyện.')
            sub = action.split('/', 1)[1]
            if method == 'GET' and sub == 'status':
                value = lr_svc.status(scope, recheck)
            elif method == 'GET' and sub == 'worker-health':
                value = lr_svc.probe_worker_health()
            elif method == 'POST' and sub == 'prepare':
                body = read_json(handler)
                value = lr_svc.prepare_dataset(scope, body if isinstance(body, dict) else {}, recheck)
            elif method == 'POST' and sub in ('worker-restart', 'train', 'resume', 'decrypt', 'promote'):
                require_fit(scope)
                if sub == 'worker-restart':
                    value = lr_svc.restart_worker(scope, recheck)
                else:
                    body = read_json(handler)
                    if not isinstance(body, dict):
                        fail(400, 'MODEL_LIFECYCLE_BODY', 'Nội dung yêu cầu không hợp lệ.', 'Điền đúng thông tin trên màn hình.')
                    idem = _key(handler) if handler.headers.get('Idempotency-Key') else str(body.get('request_id') or '').strip() or None
                    if sub == 'train':
                        value = lr_svc.start_training(scope, body, idem, recheck)
                    elif sub == 'resume':
                        value = lr_svc.resume_job(scope, body, idem, recheck)
                    elif sub == 'decrypt':
                        value = lr_svc.decrypt_and_validate(scope, body, idem, recheck)
                    else:
                        value = lr_svc.promote_to_releasable_model(scope, body, idem, recheck)
            else:
                fail(405, 'METHOD_NOT_ALLOWED', 'Thao tác huấn luyện LR FHE không hợp lệ.', 'Dùng đúng phương thức GET/POST.')
        elif action and action.startswith('federated/'):
            fed = getattr(lifecycle, 'federated', None)
            if fed is None:
                fail(503, 'FEDERATED_NOT_CONFIGURED', 'Chưa cấu hình huấn luyện chung nhiều doanh nghiệp.', 'Chạy thiết lập HE huấn luyện.')
            sub = action.split('/', 1)[1]
            if method == 'GET' and sub == 'status':
                value = fed.status()
            elif method == 'POST' and sub in ('contribute', 'run', 'job', 'approve'):
                body = read_json(handler)
                if not isinstance(body, dict):
                    fail(400, 'MODEL_LIFECYCLE_BODY', 'Nội dung yêu cầu không hợp lệ.', 'Điền đúng thông tin trên màn hình.')
                if sub == 'job':
                    value = fed.job(str(body.get('run_id') or ''))
                else:
                    require_fit(scope)
                    if sub == 'contribute':
                        value = fed.simulate(company, int(body.get('count') or 48)) if body.get('simulate') else fed.contribute(company, body)
                    elif sub == 'approve':
                        value = fed.approve(str(body.get('run_id') or ''), scope.actor_id, body.get('reason'))
                    else:
                        def scopes_for(cid):
                            sc = authorizer.authorize_director(header, cid)
                            require_fit(sc)
                            return sc
                        value = fed.start(scopes_for, body)
            else:
                fail(405, 'METHOD_NOT_ALLOWED', 'Thao tác huấn luyện chung không hợp lệ.', 'Dùng đúng phương thức GET/POST.')
        elif action and (action == 'lr-registry' or action.startswith('lr-registry/')):
            lr_reg = getattr(lifecycle, 'lr_registry', None)
            if lr_reg is None:
                fail(503, 'LR_REGISTRY_NOT_CONFIGURED', 'Chưa cấu hình LR Model Registry (R5).', 'Khởi động Agent2 với kho quản lý mô hình.')
            sub = action.split('/', 1)[1] if '/' in action else ''
            if method == 'GET' and sub == '':
                value = lr_reg.overview(scope, recheck)
            elif method == 'POST' and sub in ('register', 'validate', 'transition'):
                require_fit(scope)
                body = read_json(handler)
                if not isinstance(body, dict):
                    fail(400, 'MODEL_LIFECYCLE_BODY', 'Nội dung yêu cầu không hợp lệ.', 'Điền đúng thông tin trên màn hình.')
                if sub == 'register':
                    value = lr_reg.register_model(scope, body, recheck)
                elif sub == 'validate':
                    value = lr_reg.validate_model(scope, body, recheck)
                else:
                    value = lr_reg.transition_state(scope, body, recheck)
            else:
                fail(405, 'METHOD_NOT_ALLOWED', 'Thao tác LR Model Registry không hợp lệ.', 'Dùng đúng phương thức GET/POST.')
        elif method == 'POST' and action == 'profile':
            body = read_json(handler)
            sid = str((body or {}).get('snapshot_id') or '').strip() if isinstance(body, dict) else ''
            value = lifecycle.profile_snapshot(scope, sid, recheck)
        elif method == 'POST' and action in ('train', 'evaluate', 'approve', 'rollback', 'score-queue', 'analyze', 'training-data'):
            require_fit(scope)
            body = read_json(handler)
            if not isinstance(body, dict):
                fail(400, 'MODEL_LIFECYCLE_BODY', 'Nội dung yêu cầu không hợp lệ.', 'Điền đúng thông tin trên màn hình.')
            if action == 'evaluate':
                value = lifecycle.evaluate_version(
                    scope,
                    str(body.get('version_id') or '').strip(),
                    str(body.get('eval_snapshot_id') or '').strip(),
                    recheck,
                )
            else:
                idem = _key(handler) if handler.headers.get('Idempotency-Key') else str(body.get('request_id') or '').strip()
                if action == 'train':
                    value = lifecycle.train_candidate(scope, header, body, idem, recheck)
                elif action == 'approve':
                    value = lifecycle.approve_and_activate(scope, body, idem, recheck)
                elif action == 'rollback':
                    value = lifecycle.rollback_version(scope, body, idem, recheck)
                elif action == 'training-data':
                    value = lifecycle.ingest_training_files(scope, body, idem, recheck)
                elif action == 'analyze':
                    value = lifecycle.analyze_latest(scope, header, body, idem, recheck)
                else:
                    value = lifecycle.score_to_queue(scope, body, idem, recheck)
        else:
            fail(405, 'METHOD_NOT_ALLOWED', 'Thao tác quản lý mô hình không hợp lệ.', 'Dùng GET xem trạng thái hoặc POST đúng thao tác.')

        if recheck() != scope:
            fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền truy cập đã thay đổi trước khi trả kết quả.', 'Đăng nhập lại.')
        handler.respond(200, value)
    except (AuthError, ImportFailure) as error:
        respond_failure(handler, error)
    except Exception as exc:
        respond_failure(
            handler,
            ImportFailure(
                503,
                'MODEL_LIFECYCLE_UNAVAILABLE',
                f'Chưa hoàn tất thao tác quản lý mô hình ({type(exc).__name__}).',
                'Tải lại trạng thái trước khi thử lại; phiên bản đang dùng không bị thay đổi.',
            ),
        )
    return True
