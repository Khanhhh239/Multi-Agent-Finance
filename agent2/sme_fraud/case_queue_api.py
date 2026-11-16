"""Authenticated HTTP endpoints for Case Coalescing, Case Budget Queue, Recovery, and Backlog."""
from __future__ import annotations

from copy import deepcopy
import re
from urllib.parse import urlsplit

from finance_input.json_io import loads

from .auth import AuthError
from .import_files import ImportFailure, canonical, fail
from .snapshot_analysis import analyze_snapshot
from .validation_api import authorize_request, read_json, respond_failure

_CID = r"([A-Za-z0-9_.:-]{1,128})"
_CASE_ID = r"(case_[a-f0-9]{32})"
_PERIOD = r"([A-Za-z0-9_.-]{1,64})"

_EVALUATE_RE = re.compile(rf"/api/v1/companies/{_CID}/case-queue/evaluate\Z")
_RECOVER_RE = re.compile(rf"/api/v1/companies/{_CID}/case-queue/recover\Z")
_REEVAL_RE = re.compile(rf"/api/v1/companies/{_CID}/case-queue/reevaluate-backlog\Z")
_QUEUE_RE = re.compile(
    rf"/api/v1/companies/{_CID}/case-queue/(active|shadow)(?:/periods/{_PERIOD})?(?:/(technical))?\Z"
)
_BACKLOG_RE = re.compile(rf"/api/v1/companies/{_CID}/case-queue/backlog(?:/(shadow))?(?:/(technical))?\Z")
_CASE_DETAIL_RE = re.compile(rf"/api/v1/companies/{_CID}/case-queue/cases/{_CASE_ID}(?:/(shadow))?(?:/(technical))?\Z")
_CASE_WF_RE = re.compile(rf"/api/v1/companies/{_CID}/case-queue/cases/{_CASE_ID}/workflow\Z")


def _require_director(handler, authorizer, company_id: str, scope):
    headers = handler.headers.get_all("Authorization", [])
    authorization = headers[0] if len(headers) == 1 else None
    if not hasattr(authorizer, "authorize_director"):
        fail(503, "ROLE_POLICY_UNAVAILABLE", "Chưa cấu hình phân quyền director phía server.", "Kiểm tra cấu hình auth policy.")
    check = lambda: authorizer.authorize_director(authorization, company_id)
    if check() != scope:
        fail(409, "AUTH_CONTEXT_CHANGED", "Quyền đã thay đổi.", "Gửi lại với quyền hiện hành.")
    return check


def _extract_idempotency_key(handler, body: dict) -> str:
    hdrs = handler.headers.get_all("Idempotency-Key", [])
    if len(hdrs) > 1:
        fail(400, "DUPLICATE_IDEMPOTENCY_HEADER", "Chỉ gửi một header Idempotency-Key.", "Loại bỏ header trùng lặp.")
    key = hdrs[0].strip() if len(hdrs) == 1 else str(body.get("idempotency_key") or "").strip()
    if not key or len(key) > 256:
        fail(422, "IDEMPOTENCY_KEY_REQUIRED", "Thiếu Idempotency-Key hợp lệ.", "Gửi header Idempotency-Key duy nhất.")
    return key


def _redact_action_response(result: dict, redaction: str) -> dict:
    if redaction == "technical":
        out = deepcopy(result)
        out["redaction"] = "technical"
        return out
    out = deepcopy(result)
    out["redaction"] = "review"
    if isinstance(out.get("policy_summary"), dict):
        out["policy_summary"].pop("policy_hash", None)
    for rec in out.get("decisions") or []:
        rec.pop("material_fingerprint", None)
    return out


def handle_case_queue(
    handler,
    authorizer,
    case_queue_store,
    method: str,
    snapshot_store=None,
    analysis_resources=None,
    release_service=None,
) -> bool:
    """Handle /api/v1/companies/{company_id}/case-queue/* routes if matched."""
    path = urlsplit(handler.path).path
    if "/case-queue" not in path:
        return False

    m_eval = _EVALUATE_RE.fullmatch(path)
    if m_eval:
        try:
            company_id = m_eval[1]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method != "POST":
                fail(405, "METHOD_NOT_ALLOWED", "Đánh giá hàng đợi vụ việc dùng POST.", "Gửi POST JSON kèm Idempotency-Key.")
            if case_queue_store is None:
                fail(503, "CASE_QUEUE_UNAVAILABLE", "Kho hàng đợi vụ việc chưa được khởi tạo.", "Kiểm tra cấu hình server.")
            body = read_json(handler)
            if not isinstance(body, dict):
                fail(400, "INVALID_BODY", "Body phải là JSON object.", "Gửi JSON hợp lệ.")
            allowed = {
                "mode",
                "period_key",
                "policy",
                "view",
                "bundle",
                "analysis",
                "raw_snapshot",
                "snapshot_id",
                "as_of",
                "ml_method",
                "extra_scores",
                "idempotency_key",
            }
            if set(body) - allowed:
                fail(400, "UNSUPPORTED_FIELDS", "Yêu cầu chứa trường không được hỗ trợ.", "Chỉ truyền các trường được khai báo.")
            view = body.get("view", "review")
            if view not in ("review", "technical"):
                fail(400, "INVALID_VIEW", "view chỉ nhận review hoặc technical.", "Chọn review hoặc technical.")
            active_recheck = recheck
            if view == "technical" or body.get("policy") is not None:
                # Non-default custom policy override or technical scoring view requires director privilege.
                active_recheck = _require_director(handler, authorizer, company_id, scope)

            idem = _extract_idempotency_key(handler, body)
            mode = body.get("mode", "active")
            if mode == "active" and release_service is not None:
                release_service.require_new_delivery(scope,active_recheck)
            period_key = body.get("period_key")
            policy = body.get("policy")
            bundle_or_analysis = body.get("bundle") or body.get("analysis")
            raw_snapshot = body.get("raw_snapshot")

            if bundle_or_analysis is None:
                snapshot_id = body.get("snapshot_id")
                as_of = body.get("as_of")
                if not snapshot_id or not as_of or snapshot_store is None:
                    fail(
                        422,
                        "MISSING_CASE_SOURCE",
                        "Cần cung cấp snapshot_id + as_of (khi có snapshot_store) hoặc bundle/analysis.",
                        "Chọn snapshot đã lưu kèm as_of hoặc gửi bundle case-queue-bundle/1.0.0.",
                    )
                bundle_or_analysis = analyze_snapshot(
                    snapshot_store,
                    scope,
                    snapshot_id,
                    as_of,
                    technical=True,
                    recheck=active_recheck,
                    resources=analysis_resources,
                )
                raw_snapshot = loads(snapshot_store.get_snapshot(scope, snapshot_id, active_recheck, data=True))

            res = case_queue_store.evaluate_and_enqueue(
                scope,
                bundle_or_analysis,
                policy=policy,
                mode=mode,
                period_key=period_key,
                idempotency_key=idem,
                recheck=active_recheck,
                raw_snapshot=raw_snapshot,
                ml_method=body.get("ml_method"),
                extra_scores=body.get("extra_scores"),
            )
            handler.respond(200, canonical(_redact_action_response(res, view)))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    m_rec = _RECOVER_RE.fullmatch(path)
    if m_rec:
        try:
            company_id = m_rec[1]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method != "POST":
                fail(405, "METHOD_NOT_ALLOWED", "Khôi phục outbox dùng POST.", "Gửi POST JSON {mode}.")
            if case_queue_store is None:
                fail(503, "CASE_QUEUE_UNAVAILABLE", "Kho hàng đợi chưa sẵn sàng.", "Kiểm tra cấu hình server.")
            body = read_json(handler)
            if not isinstance(body, dict) or (set(body) - {"mode"}):
                fail(400, "INVALID_BODY", "Chỉ nhận JSON object với mode tùy chọn.", "Truyền {mode: 'active' | 'shadow'}.")
            res = case_queue_store.recover_outbox(scope, mode=body.get("mode", "active"), recheck=recheck)
            handler.respond(200, canonical(res))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    m_reeval = _REEVAL_RE.fullmatch(path)
    if m_reeval:
        try:
            company_id = m_reeval[1]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method != "POST":
                fail(405, "METHOD_NOT_ALLOWED", "Tái đánh giá backlog dùng POST.", "Gửi POST JSON kèm target_period_key.")
            if case_queue_store is None:
                fail(503, "CASE_QUEUE_UNAVAILABLE", "Kho hàng đợi chưa sẵn sàng.", "Kiểm tra cấu hình server.")
            body = read_json(handler)
            if not isinstance(body, dict):
                fail(400, "INVALID_BODY", "Body phải là JSON object.", "Gửi JSON hợp lệ.")
            allowed = {
                "mode",
                "target_period_key",
                "policy",
                "view",
                "updated_bundle",
                "supplemental_sources",
                "idempotency_key",
            }
            if set(body) - allowed:
                fail(400, "UNSUPPORTED_FIELDS", "Yêu cầu chứa trường không được hỗ trợ.", "Chỉ truyền các trường tái đánh giá backlog.")
            view = body.get("view", "review")
            if view not in ("review", "technical"):
                fail(400, "INVALID_VIEW", "view chỉ nhận review hoặc technical.", "Chọn review hoặc technical.")
            active_recheck = recheck
            if view == "technical" or body.get("policy") is not None:
                active_recheck = _require_director(handler, authorizer, company_id, scope)
            idem = _extract_idempotency_key(handler, body)
            if body.get("mode", "active") == "active" and release_service is not None:
                release_service.require_new_delivery(scope,active_recheck)
            res = case_queue_store.reevaluate_backlog(
                scope,
                policy=body.get("policy"),
                mode=body.get("mode", "active"),
                target_period_key=body.get("target_period_key"),
                updated_bundle=body.get("updated_bundle"),
                supplemental_sources=body.get("supplemental_sources"),
                idempotency_key=idem,
                recheck=active_recheck,
            )
            handler.respond(200, canonical(_redact_action_response(res, view)))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    m_queue = _QUEUE_RE.fullmatch(path)
    if m_queue:
        try:
            company_id, mode, period_key, tech = m_queue[1], m_queue[2], m_queue[3], m_queue[4]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method != "GET":
                fail(405, "METHOD_NOT_ALLOWED", "Đọc hàng đợi dùng GET.", "Dùng HTTP GET.")
            if case_queue_store is None:
                fail(503, "CASE_QUEUE_UNAVAILABLE", "Kho hàng đợi chưa sẵn sàng.", "Kiểm tra cấu hình server.")
            active_recheck = recheck
            redaction = "review"
            if tech == "technical":
                active_recheck = _require_director(handler, authorizer, company_id, scope)
                redaction = "technical"
            res = case_queue_store.get_queue_state(
                scope,
                mode=mode,
                period_key=period_key,
                redaction=redaction,
                recheck=active_recheck,
            )
            handler.respond(200, canonical(res))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    m_backlog = _BACKLOG_RE.fullmatch(path)
    if m_backlog:
        try:
            company_id, shadow_part, tech = m_backlog[1], m_backlog[2], m_backlog[3]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method != "GET":
                fail(405, "METHOD_NOT_ALLOWED", "Đọc backlog dùng GET.", "Dùng HTTP GET.")
            if case_queue_store is None:
                fail(503, "CASE_QUEUE_UNAVAILABLE", "Kho hàng đợi chưa sẵn sàng.", "Kiểm tra cấu hình server.")
            active_recheck = recheck
            redaction = "review"
            if tech == "technical":
                active_recheck = _require_director(handler, authorizer, company_id, scope)
                redaction = "technical"
            res = case_queue_store.get_backlog(
                scope,
                mode="shadow" if shadow_part else "active",
                redaction=redaction,
                recheck=active_recheck,
            )
            handler.respond(200, canonical(res))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    m_detail = _CASE_DETAIL_RE.fullmatch(path)
    if m_detail:
        try:
            company_id, case_id, shadow_part, tech = m_detail[1], m_detail[2], m_detail[3], m_detail[4]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method != "GET":
                fail(405, "METHOD_NOT_ALLOWED", "Đọc chi tiết vụ việc dùng GET.", "Dùng HTTP GET.")
            if case_queue_store is None:
                fail(503, "CASE_QUEUE_UNAVAILABLE", "Kho hàng đợi chưa sẵn sàng.", "Kiểm tra cấu hình server.")
            active_recheck = recheck
            redaction = "review"
            if tech == "technical":
                active_recheck = _require_director(handler, authorizer, company_id, scope)
                redaction = "technical"
            res = case_queue_store.get_case_detail(
                scope,
                case_id,
                mode="shadow" if shadow_part else "active",
                redaction=redaction,
                recheck=active_recheck,
            )
            handler.respond(200, canonical(res))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    m_wf = _CASE_WF_RE.fullmatch(path)
    if m_wf:
        try:
            company_id, case_id = m_wf[1], m_wf[2]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method != "POST":
                fail(405, "METHOD_NOT_ALLOWED", "Cập nhật trạng thái vụ việc dùng POST.", "Gửi POST JSON {case_workflow_status, case_resolution, reason}.")
            if case_queue_store is None:
                fail(503, "CASE_QUEUE_UNAVAILABLE", "Kho hàng đợi chưa sẵn sàng.", "Kiểm tra cấu hình server.")
            body = read_json(handler)
            if not isinstance(body, dict) or (set(body) - {"mode", "case_workflow_status", "case_resolution", "reason"}):
                fail(400, "INVALID_WORKFLOW_BODY", "Yêu cầu chuyển trạng thái không hợp lệ.", "Truyền case_workflow_status và case_resolution (nếu đóng).")
            res = case_queue_store.update_case_workflow(
                scope,
                mode=body.get("mode", "active"),
                case_id=case_id,
                new_status=body.get("case_workflow_status"),
                resolution=body.get("case_resolution"),
                reason=body.get("reason", ""),
                recheck=recheck,
            )
            handler.respond(200, canonical(res))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    return False
