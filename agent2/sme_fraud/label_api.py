"""Authenticated enterprise verification lists; no upload/train side effects."""
from datetime import timedelta
import re
import sqlite3
from urllib.parse import urlsplit
from cryptography.exceptions import InvalidTag
from finance_input.json_io import loads
from .auth import AuthError
from .import_files import ImportFailure, fail
from .label_packets import LabelStore, source_packet, checked
from .review_api import display_record
from .snapshot_features import utc
from .validation_api import authorize_request, read_json, respond_failure

ROUTE = re.compile(r'/api/v1/companies/([A-Za-z0-9_.:-]{1,128})/(label-sources(?:/(snp_[a-f0-9]{32}))?|label-packets(?:/(lbl_[a-f0-9]{64})(?:/(save|lock|reopen|export))?)?)\Z')


def sources(store, scope, recheck, sid=None):
    if sid is None:
        with store._transaction(scope, recheck) as conn:
            ids = [r[0] for r in conn.execute('SELECT snapshot_id FROM snapshots WHERE tenant_id=? AND company_id=? ORDER BY rowid DESC', (scope.tenant_id, next(iter(scope.company_ids))))]
            return dict(snapshots=[store._read_snapshot(conn, scope, i)[0] for i in ids])
    manifest = store.get_snapshot(scope, sid, recheck)
    raw = loads(store.get_snapshot(scope, sid, recheck, data=True))
    native = raw.get('contract_version') == 'agent2-rule-snapshot/1.0.0'
    as_of = raw['source']['as_of'] if native else manifest['created_at']
    rows = raw['source']['tables']['transactions'] if native else raw['transactions']
    selected = []
    for row in rows:
        event = row['posted_at'] if native else row['effective_at']
        if utc(row['observed_at']) > utc(as_of) or utc(event) > utc(as_of):
            continue
        selected.append(dict(record_id=row['transaction_id'] if native else row['record_id'], revision=row.get('revision', 1),
                             event_at=event, amount_vnd=str(row['amount_vnd']), description=row.get('description', '')))
    return dict(snapshot=manifest, as_of=as_of, rows=selected,
                training_start=(min((utc(r['event_at']) for r in selected), default=utc(as_of)) - timedelta(seconds=1)).isoformat(),
                training_end=as_of)


def handle_labels(handler, authorizer, snapshots, labels, method):
    match = ROUTE.fullmatch(urlsplit(handler.path).path)
    if not match:
        return False
    try:
        company, path, sid, pid, action = match.groups()
        scope, recheck = authorize_request(handler, authorizer, company)
        if labels is None or snapshots is None:
            fail(503, 'LABELS_NOT_CONFIGURED', 'Kho xác minh nhãn chưa được bật.', 'Người vận hành cấu hình kho nhãn và khóa bảo vệ tại doanh nghiệp.')
        if path.startswith('label-sources'):
            if method != 'GET':
                fail(405, 'METHOD_NOT_ALLOWED', 'Danh sách nguồn chỉ hỗ trợ xem.', 'Dùng GET.')
            result = sources(snapshots, scope, recheck, sid)
        elif not pid:
            if method == 'GET':
                result = dict(packets=labels.list(scope, recheck), can_verify='evidence.verify' in scope.permissions,
                              actor_id=scope.actor_id)
            elif method == 'POST':
                LabelStore.guard(scope, recheck, write=True)
                result = labels.create(scope, source_packet(snapshots, scope, read_json(handler), recheck), recheck)
            else:
                fail(405, 'METHOD_NOT_ALLOWED', 'Thao tác chưa được hỗ trợ.', 'Dùng GET hoặc POST.')
        elif action is None and method == 'GET':
            result = labels.get(scope, pid, recheck)
        elif action == 'export' and method == 'POST':
            body = read_json(handler)
            checked(isinstance(body, dict) and set(body) == {'revision', 'lock_sha256'} and type(body['revision']) is int,
                    'LABEL_EXPORT_REQUEST', 'Cần chỉ rõ phiên bản và checksum đã khóa.', status=400)
            result = labels.export(scope, pid, body['revision'], body['lock_sha256'], recheck)
        elif action in ('save', 'lock', 'reopen') and method == 'POST':
            result = labels.change(scope, pid, action, read_json(handler), recheck)
        else:
            fail(405, 'METHOD_NOT_ALLOWED', 'Thao tác chưa được hỗ trợ.', 'Dùng thao tác xem, ghi, khóa hoặc mở phiên bản mới.')
        LabelStore.guard(scope, recheck)
        handler.respond(200, display_record(result))
    except (AuthError, ImportFailure) as error:
        respond_failure(handler, error)
    except (sqlite3.Error, OSError, InvalidTag):
        respond_failure(handler, ImportFailure(503, 'LABEL_STORAGE_UNAVAILABLE', 'Kho nhãn tạm thời chưa sẵn sàng.', 'Gửi lại đúng mã yêu cầu; không tạo yêu cầu mới khi mất phản hồi.'))
    except ValueError as error:
        from experiments.he_training.protocol import TrainingError
        if not isinstance(error, TrainingError):
            raise
        respond_failure(handler, ImportFailure(422, error.code, 'Danh sách giao dịch hoặc thời điểm nguồn chưa hợp lệ.', 'Chọn đúng 4 giao dịch và kế hoạch đầu vào train rồi thử lại.'))
    return True
