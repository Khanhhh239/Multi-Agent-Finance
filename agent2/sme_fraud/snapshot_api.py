"""Authenticated upload -> preview -> explicit immutable snapshot commit."""
import re
import sqlite3
from urllib.parse import unquote, urlsplit

from .auth import AuthError
from .import_files import ImportFailure, fail
from .snapshots import COMMIT_FIELDS
from .validation_api import authorize_request, read_body, read_json, respond_failure

PREFIX = r"/api/v1/companies/([A-Za-z0-9_.:-]{1,128})/"
UPLOAD = re.compile(PREFIX+r"imports/upload\Z")
IMPORT = re.compile(PREFIX+r"imports/(imp_[a-f0-9]{32})(?:/(source|mapping|inspect|preview|commit|report))?\Z")
SNAPSHOT = re.compile(PREFIX+r"snapshots/(snp_[a-f0-9]{32})(/data)?\Z")


def _key(handler):
    values = handler.headers.get_all("Idempotency-Key", [])
    if len(values) != 1 or re.fullmatch(r"[A-Za-z0-9_.:-]{8,128}", values[0]) is None:
        fail(400, "IDEMPOTENCY_KEY", "Thiếu hoặc sai Idempotency-Key.", "Dùng một khóa 8–128 ký tự và giữ nguyên khi gửi lại cùng yêu cầu.")
    return values[0]


def _fields(value, required):
    if not isinstance(value, dict) or set(value) != required:
        fail(400, "REQUEST_FIELDS", "Body thiếu trường bắt buộc hoặc chứa trường không được phép.", "Gửi đúng các trường theo import protocol 1.0.0; không gửi quyền hoặc report tự tạo.")
    if "expected_revision" in required and (type(value["expected_revision"]) is not int or value["expected_revision"] < 1):
        fail(400, "EXPECTED_REVISION", "expected_revision phải là số nguyên từ 1.", "Lấy revision mới nhất của lần nhập từ server.")
    return value


def _filename(handler):
    values = handler.headers.get_all("X-File-Name", [])
    if len(values) != 1:
        fail(400, "FILENAME_REQUIRED", "Chưa có tên tệp tải lên.", "Gửi X-File-Name là tên tệp .csv, .xlsx hoặc .json, URL-encode nếu có tiếng Việt.")
    return unquote(values[0])


def handle_snapshots(handler, authorizer, store, method):
    path = urlsplit(handler.path).path
    upload, draft, snapshot = UPLOAD.fullmatch(path), IMPORT.fullmatch(path), SNAPSHOT.fullmatch(path)
    route = upload or draft or snapshot
    if route is None:
        return False
    try:
        scope, recheck = authorize_request(handler, authorizer, route[1])
        if store is None:
            fail(503, "SNAPSHOT_STORAGE_REQUIRED", "Kho snapshot chưa được cấu hình.", "Người vận hành đặt --snapshot-db hoặc AGENT2_SNAPSHOT_DB trỏ tới DB mới riêng.")
        if upload and method == "POST":
            key = _key(handler); filename = _filename(handler)
            handler.respond(201, store.upload(scope, read_body(handler, file=True), filename, key, recheck))
        elif snapshot and method == "GET":
            value = store.get_snapshot(scope, snapshot[2], recheck, data=bool(snapshot[3]))
            handler.respond(200, value)
        elif draft:
            import_id, action = draft[2], draft[3]
            if method == "GET" and action in {None, "report"}:
                value = store.get_report(scope, import_id, recheck) if action else store.get_import(scope, import_id, recheck)
                handler.respond(200, value)
            elif method == "PUT" and action == "source":
                key = _key(handler); filename = _filename(handler)
                revisions = handler.headers.get_all("X-Expected-Revision", [])
                if len(revisions) != 1 or re.fullmatch(r"[1-9][0-9]{0,8}", revisions[0]) is None:
                    fail(400, "EXPECTED_REVISION", "Thiếu X-Expected-Revision khi đổi tệp.", "Gửi revision đang xem; đổi tệp tạo revision mới và phải preview lại.")
                handler.respond(200, store.revise(scope, import_id, int(revisions[0]), key,
                    raw=read_body(handler, file=True), filename=filename, recheck=recheck))
            elif method == "PUT" and action == "mapping":
                key = _key(handler); body = _fields(read_json(handler), {"expected_revision", "mapping"})
                handler.respond(200, store.revise(scope, import_id, body["expected_revision"], key, mapping=body["mapping"], recheck=recheck))
            elif method == 'POST' and action == 'inspect':
                body=_fields(read_json(handler),{'expected_revision'})
                handler.respond(200,store.inspect_sources(scope,import_id,body['expected_revision'],recheck))
            elif method == "POST" and action == "preview":
                body = _fields(read_json(handler), {"expected_revision"})
                value = store.preview(scope, import_id, body["expected_revision"], recheck)
                status = 200 if value["status"] != "rejected" else 403 if any(e["code"] == "ACCESS_DENIED" for e in value["errors"]) else 422
                handler.respond(status, value)
            elif method == "POST" and action == "commit":
                key = _key(handler); body = _fields(read_json(handler), COMMIT_FIELDS)
                handler.respond(200, store.commit(scope, import_id, body, key, recheck))
            else:
                fail(405, "METHOD_NOT_ALLOWED", "Thao tác không được hỗ trợ tại endpoint này.", "Dùng đúng phương thức upload/preview/commit/read theo tài liệu.")
        else:
            fail(405, "METHOD_NOT_ALLOWED", "Thao tác không được hỗ trợ tại endpoint này.", "Dùng POST upload hoặc GET snapshot; snapshot không có API sửa/xóa.")
    except (AuthError, ImportFailure) as error:
        respond_failure(handler, error)
    except (sqlite3.Error, OSError):
        respond_failure(handler, ImportFailure(503, "STORAGE_UNAVAILABLE", "Kho snapshot tạm thời không sẵn sàng; chưa xác nhận lưu thành công.", "Gửi lại đúng Idempotency-Key sau khi kho hoạt động; không tạo khóa mới chỉ vì mất phản hồi."))
    return True
