"""Shared authenticated HTTP transport and read-only JSON validation endpoint."""
import json
import re
import socket
from urllib.parse import urlsplit

from finance_input.json_io import loads
from finance_input import CONTRACT_VERSION
from finance_input.validation import issue
from .auth import AuthError
from .imports import validate_input, VALIDATOR_VERSION, PROFILE_VERSION, REPORT_VERSION

ROUTE = re.compile(r"/api/v1/companies/([A-Za-z0-9_.:-]{1,128})/imports/validate\Z")
MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 50000


class RequestFailure(AuthError):
    def __init__(self, status, code, message, action, **detail):
        super().__init__(status, code, message, action)
        self.detail = detail


def _report(code, message, action):
    return dict(status="rejected", contract_version=CONTRACT_VERSION, validator_version=VALIDATOR_VERSION,
                profile_version=PROFILE_VERSION, report_version=REPORT_VERSION, errors=[issue(code, "$", message, action)],
                warnings=[], counts={}, capabilities={}, analysis_limits={})


def respond_failure(handler, error):
    report = _report(error.code, error.message, error.action)
    report["errors"][0].update(getattr(error, "detail", {}))
    handler.respond(error.status, report)


def authorize_request(handler, authorizer, company_id):
    """Shared guard for validate, upload, preview, commit and snapshot reads."""
    handler.close_connection = True
    port = handler.server.server_port
    if handler.headers.get_all("Host", []) not in ([f"127.0.0.1:{port}"], [f"localhost:{port}"]):
        raise RequestFailure(403, "HOST_DENIED", "Địa chỉ truy cập backend không hợp lệ.", "Gọi backend qua địa chỉ loopback được cấu hình.")
    origins = handler.headers.get_all("Origin", [])
    if origins and origins not in ([f"http://127.0.0.1:{port}"], [f"http://localhost:{port}"]):
        raise RequestFailure(403, "ORIGIN_DENIED", "Nguồn yêu cầu không được phép.", "Gọi từ backend tin cậy; không gửi credential trực tiếp từ trang khác.")
    values = handler.headers.get_all("Authorization", [])
    authorization = values[0] if len(values) == 1 else None
    scope = authorizer.authorize(authorization, company_id)
    if urlsplit(handler.path).query:
        raise RequestFailure(400, "QUERY_NOT_SUPPORTED", "Endpoint này không nhận tham số quyền trên URL.", "Gửi đúng body; quyền và tenant do backend xác định.")
    return scope, lambda: authorizer.authorize(authorization, company_id)


def read_body(handler, *, file=False):
    """Bounded body read; caller must run authorize_request first."""
    if handler.headers.get_all("Transfer-Encoding", []):
        raise RequestFailure(400, "TRANSFER_ENCODING", "Kiểu truyền dữ liệu chưa được hỗ trợ.", "Gửi body với một Content-Length chính xác.")
    lengths = handler.headers.get_all("Content-Length", [])
    if len(lengths) != 1 or re.fullmatch(r"[0-9]{1,12}", lengths[0]) is None:
        raise RequestFailure(400, "CONTENT_LENGTH", "Thiếu hoặc sai kích thước body.", "Gửi đúng một Content-Length theo số byte.")
    length = int(lengths[0])
    if length <= 0:
        raise RequestFailure(400, "EMPTY_INPUT", "Chưa có dữ liệu để kiểm tra.", "Gửi dữ liệu theo hợp đồng 1.0.0.")
    if length > MAX_BYTES:
        raise RequestFailure(413, "INPUT_TOO_LARGE", "Dữ liệu vượt giới hạn 10 MB.", "Chia gói nhỏ hơn nhưng giữ đủ các bản ghi được tham chiếu.")
    types = handler.headers.get_all("Content-Type", [])
    allowed = {"application/json", "application/json;charset=utf-8"}
    if file:
        allowed.add("application/octet-stream")
    if len(types) != 1 or types[0].lower().replace(" ", "") not in allowed:
        raise RequestFailure(415, "CONTENT_TYPE", "Endpoint hiện nhận JSON UTF-8.", "Dùng application/json; tệp JSON nguyên byte có thể gửi application/octet-stream khi upload.")
    if handler.headers.get("Content-Encoding", "identity").lower() != "identity":
        raise RequestFailure(415, "CONTENT_ENCODING", "Chưa nhận body nén.", "Gửi dữ liệu UTF-8 không nén.")
    try:
        handler.connection.settimeout(10)
        raw = handler.rfile.read(length)
        if len(raw) != length:
            raise RequestFailure(400, "INCOMPLETE_BODY", "Dữ liệu truyền lên chưa đầy đủ.", "Gửi lại toàn bộ body với Content-Length chính xác.")
        return raw
    except (TimeoutError, socket.timeout):
        raise RequestFailure(408, "INPUT_TIMEOUT", "Truyền dữ liệu quá thời gian chờ.", "Kiểm tra kết nối rồi gửi lại.") from None


def read_json(handler):
    raw = read_body(handler)
    try:
        return loads(raw)
    except json.JSONDecodeError as error:
        raise RequestFailure(400, "INVALID_JSON", "Cú pháp JSON không hợp lệ.", "Sửa cú pháp tại dòng/cột JSON rồi gửi lại.", json_line=error.lineno, json_column=error.colno) from None
    except (UnicodeError, ValueError, RecursionError, OverflowError):
        raise RequestFailure(400, "INVALID_JSON", "JSON không hợp lệ, lặp khóa, quá sâu hoặc có số không hữu hạn.", "Xuất lại JSON UTF-8; mỗi trường một lần, không dùng NaN/Infinity.") from None


def handle_validation(handler, authorizer):
    route = ROUTE.fullmatch(urlsplit(handler.path).path)
    if not route:
        return False
    try:
        scope, recheck = authorize_request(handler, authorizer, route[1])
        bundle = read_json(handler)
        current = recheck()
        if current != scope:
            raise RequestFailure(409, "AUTH_CONTEXT_CHANGED", "Quyền đã đổi trong lúc đọc dữ liệu.", "Gửi lại theo quyền hiện hành.")
        if isinstance(bundle, dict) and sum(len(v) for v in bundle.values() if isinstance(v, list)) > MAX_ROWS:
            raise RequestFailure(413, "ROW_LIMIT", "Gói dữ liệu vượt 50.000 bản ghi.", "Chia gói và giữ đủ tham chiếu; không cắt bỏ dòng ngầm.")
        try:
            report = validate_input(bundle, scope)
        except (RecursionError, OverflowError):
            raise RequestFailure(400, "INPUT_STRUCTURE", "Cấu trúc dữ liệu quá sâu hoặc không hợp lệ.", "Xuất lại theo schema 1.0.0.") from None
        status = 200 if report["status"] != "rejected" else 403 if any(e["code"] == "ACCESS_DENIED" for e in report["errors"]) else 422
        handler.respond(status, report)
    except AuthError as error:
        respond_failure(handler, error)
    return True
