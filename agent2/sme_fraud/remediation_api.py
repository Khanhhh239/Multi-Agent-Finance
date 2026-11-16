"""Authenticated HTTP endpoints for Document Checklist, Evidence Documents, ActionTask remediation, and Business Reporting."""
from __future__ import annotations

import base64
import binascii
import re
from urllib.parse import urlsplit

from finance_input.json_io import loads

from .auth import AuthError
from .import_files import ImportFailure, canonical, fail
from .remediation_policy import reconcile_obligation
from .validation_api import authorize_request, read_json, respond_failure

_CID = r"([A-Za-z0-9_.:-]{1,128})"
_CASE_KEY = r"([A-Za-z0-9_.:-]{1,128})"
_DOC_ID = r"(doc_[a-f0-9]{24})"
_TASK_ID = r"(tsk_[a-f0-9]{24})"
_FILTER = r"(all|mine_or_dept|due_soon|overdue|awaiting_confirmation|completed)"

_SUMMARY_RE = re.compile(rf"/api/v1/companies/{_CID}/remediation/summary\Z")
_TASKS_FILTER_RE = re.compile(rf"/api/v1/companies/{_CID}/remediation/tasks/filter/{_FILTER}\Z")
_TASKS_QUERY_RE = re.compile(rf"/api/v1/companies/{_CID}/remediation/tasks/query\Z")
_REPORT_RE = re.compile(rf"/api/v1/companies/{_CID}/remediation/report\Z")
_CASE_GET_RE = re.compile(rf"/api/v1/companies/{_CID}/remediation/cases/{_CASE_KEY}\Z")
_CASE_CHECKLIST_RE = re.compile(rf"/api/v1/companies/{_CID}/remediation/cases/{_CASE_KEY}/checklist\Z")
_CASE_DOCS_RE = re.compile(rf"/api/v1/companies/{_CID}/remediation/cases/{_CASE_KEY}/documents\Z")
_DOC_GET_RE = re.compile(rf"/api/v1/companies/{_CID}/remediation/documents/{_DOC_ID}(?:/versions/([0-9]{{1,4}}))?(?:/(content))?\Z")
_DOC_VERIFY_RE = re.compile(rf"/api/v1/companies/{_CID}/remediation/documents/{_DOC_ID}/verify\Z")
_TASK_CREATE_RE = re.compile(rf"/api/v1/companies/{_CID}/remediation/tasks\Z")
_TASK_ASSIGN_RE = re.compile(rf"/api/v1/companies/{_CID}/remediation/tasks/{_TASK_ID}/assign\Z")
_TASK_SUBMIT_RE = re.compile(rf"/api/v1/companies/{_CID}/remediation/tasks/{_TASK_ID}/submit\Z")
_TASK_DECISION_RE = re.compile(rf"/api/v1/companies/{_CID}/remediation/tasks/{_TASK_ID}/decision\Z")


def _extract_idempotency_key(handler, body: dict, *, required: bool = False) -> str | None:
    hdrs = handler.headers.get_all("Idempotency-Key", [])
    if len(hdrs) > 1:
        fail(400, "DUPLICATE_IDEMPOTENCY_HEADER", "Chỉ gửi một header Idempotency-Key.", "Loại bỏ header trùng lặp.")
    key = hdrs[0].strip() if len(hdrs) == 1 else str(body.get("idempotency_key") or "").strip()
    if required and (not key or len(key) > 256):
        fail(422, "IDEMPOTENCY_KEY_REQUIRED", "Thiếu Idempotency-Key hợp lệ.", "Gửi header Idempotency-Key duy nhất.")
    return key or None


def _collect_case_statuses(case_queue_store, scope, recheck) -> dict[str, str]:
    statuses: dict[str, str] = {}
    if case_queue_store is None:
        return statuses
    try:
        q = case_queue_store.get_queue_state(scope, mode="active", redaction="review", recheck=recheck)
        for item in q.get("items") or []:
            c = item.get("case") or {}
            if c.get("case_id") and c.get("case_workflow_status"):
                statuses[c["case_id"]] = c["case_workflow_status"]
        b = case_queue_store.get_backlog(scope, mode="active", redaction="review", recheck=recheck)
        for item in b.get("items") or []:
            cid = item.get("case_id")
            if cid and cid not in statuses and item.get("case_workflow_status"):
                statuses[cid] = item["case_workflow_status"]
    except ImportFailure:
        pass
    return statuses


def _extract_snapshot_sources(snapshot_store, scope, snapshot_id: str, recheck) -> tuple[list[str], dict]:
    if snapshot_store is None or not snapshot_id:
        return [], {}
    raw = loads(snapshot_store.get_snapshot(scope, snapshot_id, recheck, data=True))
    tables = raw.get("tables") if isinstance(raw.get("tables"), dict) else raw
    avail: list[str] = []
    if isinstance(tables, dict):
        for k, v in tables.items():
            if isinstance(v, list) and len(v) > 0:
                avail.append(str(k))
    return sorted(avail), raw


def handle_remediation(
    handler,
    authorizer,
    remediation_store,
    method: str,
    *,
    case_queue_store=None,
    snapshot_store=None,
) -> bool:
    """Handle /api/v1/companies/{cid}/remediation/* endpoints when path matches."""
    path = urlsplit(handler.path).path
    if "/remediation" not in path or ".." in path:
        return False

    def _require_store():
        if remediation_store is None:
            fail(503, "REMEDIATION_UNAVAILABLE", "Kho quản lý hồ sơ và công việc R4 chưa được khởi tạo.", "Kiểm tra cấu hình server.")

    m = _SUMMARY_RE.fullmatch(path)
    if m:
        try:
            company_id = m[1]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method != "GET":
                fail(405, "METHOD_NOT_ALLOWED", "Dùng GET để đọc tổng quan xử lý hồ sơ.", "Gửi GET.")
            _require_store()
            tasks_view = remediation_store.list_tasks(scope, filter_name="all", recheck=recheck)
            case_statuses = _collect_case_statuses(case_queue_store, scope, recheck)
            report = remediation_store.build_business_report(
                scope,
                case_statuses_by_id=case_statuses,
                recheck=recheck,
            )
            handler.respond(200, canonical({"tasks_view": tasks_view, "report": report}))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    m = _TASKS_FILTER_RE.fullmatch(path)
    if m:
        try:
            company_id, filter_name = m[1], m[2]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method != "GET":
                fail(405, "METHOD_NOT_ALLOWED", "Dùng GET để lọc danh sách công việc.", "Gửi GET.")
            _require_store()
            res = remediation_store.list_tasks(scope, filter_name=filter_name, recheck=recheck)
            handler.respond(200, canonical(res))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    m = _TASKS_QUERY_RE.fullmatch(path)
    if m:
        try:
            company_id = m[1]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method != "POST":
                fail(405, "METHOD_NOT_ALLOWED", "Dùng POST JSON để truy vấn lọc công việc.", "Gửi POST.")
            _require_store()
            body = read_json(handler)
            if not isinstance(body, dict) or (set(body) - {"filter", "now", "due_soon_hours", "department_role"}):
                fail(400, "INVALID_BODY", "Tham số lọc không hợp lệ.", "Chỉ truyền filter, now, due_soon_hours, department_role.")
            res = remediation_store.list_tasks(
                scope,
                filter_name=str(body.get("filter") or "all"),
                now=body.get("now"),
                due_soon_hours=int(body.get("due_soon_hours", 48)),
                department_role=body.get("department_role"),
                recheck=recheck,
            )
            handler.respond(200, canonical(res))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    m = _REPORT_RE.fullmatch(path)
    if m:
        try:
            company_id = m[1]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method not in ("GET", "POST"):
                fail(405, "METHOD_NOT_ALLOWED", "Dùng GET hoặc POST JSON để lấy báo cáo nghiệp vụ.", "Gửi GET hoặc POST.")
            _require_store()
            body = {}
            if method == "POST":
                body = read_json(handler)
                if not isinstance(body, dict) or (set(body) - {"as_of", "now", "due_soon_hours", "case_statuses_by_id"}):
                    fail(400, "INVALID_BODY", "Tham số báo cáo không hợp lệ.", "Kiểm tra body JSON.")
            case_statuses = body.get("case_statuses_by_id") or _collect_case_statuses(case_queue_store, scope, recheck)
            report = remediation_store.build_business_report(
                scope,
                case_statuses_by_id=case_statuses,
                as_of=body.get("as_of"),
                now=body.get("now"),
                due_soon_hours=int(body.get("due_soon_hours", 48)),
                recheck=recheck,
            )
            handler.respond(200, canonical(report))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    m = _CASE_GET_RE.fullmatch(path)
    if m:
        try:
            company_id, case_key = m[1], m[2]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method != "GET":
                fail(405, "METHOD_NOT_ALLOWED", "Dùng GET để xem hồ sơ và công việc theo vụ.", "Gửi GET.")
            _require_store()
            res = remediation_store.get_case_remediation(scope, case_key, recheck=recheck)
            linked_case = None
            if case_queue_store is not None and case_key.startswith("case_"):
                try:
                    detail = case_queue_store.get_case_detail(scope, case_key, mode="active", redaction="review", recheck=recheck)
                    cobj = detail.get("case") or {}
                    linked_case = {
                        "case_id": detail["case_id"],
                        "case_workflow_status": detail["case_workflow_status"],
                        "case_resolution": detail["case_resolution"],
                        "obligation_id": cobj.get("obligation_id"),
                        "problem_family": cobj.get("problem_family"),
                        "rule_ids": cobj.get("rule_ids") or [],
                        "as_of": cobj.get("as_of"),
                        "candidate_ids": cobj.get("candidate_ids") or [],
                        "evidence_tx_ids": cobj.get("evidence_tx_ids") or [],
                    }
                except ImportFailure as exc:
                    if exc.code != "CASE_NOT_FOUND":
                        raise
            res["linked_case"] = linked_case
            handler.respond(200, canonical(res))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    m = _CASE_CHECKLIST_RE.fullmatch(path)
    if m:
        try:
            company_id, case_key = m[1], m[2]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method != "POST":
                fail(405, "METHOD_NOT_ALLOWED", "Đánh giá/cập nhật checklist dùng POST.", "Gửi POST JSON.")
            _require_store()
            body = read_json(handler)
            if not isinstance(body, dict):
                fail(400, "INVALID_BODY", "Body phải là JSON object.", "Gửi JSON hợp lệ.")
            allowed = {
                "obligation_id",
                "problem_family",
                "rule_ids",
                "issue_type",
                "as_of",
                "snapshot_id",
                "snapshot_tables",
                "available_sources",
                "applicability_flags",
                "payment_count",
                "has_refund_or_adjustment",
                "reconciliation_status",
                "reconciliation_context",
                "human_overrides",
                "policy",
            }
            if set(body) - allowed:
                fail(400, "UNSUPPORTED_FIELDS", "Yêu cầu chứa trường không được hỗ trợ.", "Chỉ truyền các trường hợp lệ.")

            snap_sources: list[str] = []
            if body.get("snapshot_id"):
                snap_sources, _ = _extract_snapshot_sources(snapshot_store, scope, str(body["snapshot_id"]), recheck)

            avail_sources = body.get("available_sources")
            if avail_sources is None and snap_sources:
                avail_sources = snap_sources

            recon_report = None
            recon_ctx = body.get("reconciliation_context")
            if isinstance(recon_ctx, dict):
                recon_report = reconcile_obligation(
                    recon_ctx.get("obligation") or {"obligation_id": body.get("obligation_id") or case_key},
                    recon_ctx.get("transactions") or (),
                    recon_ctx.get("allocations") or (),
                    recon_ctx.get("adjustments") or (),
                    company_id=company_id,
                    as_of=body.get("as_of"),
                    available_sources=avail_sources,
                    confirmed_loss_vnd=recon_ctx.get("confirmed_loss_vnd"),
                    recovered_vnd=recon_ctx.get("recovered_vnd"),
                    disputed=bool(recon_ctx.get("disputed", False)),
                )

            ctx = {
                "case_id": case_key,
                "obligation_id": body.get("obligation_id") or case_key,
                "problem_family": body.get("problem_family") or "payment_invoice",
                "rule_ids": body.get("rule_ids") or [],
                "issue_type": body.get("issue_type"),
                "as_of": body.get("as_of"),
                "applicability_flags": body.get("applicability_flags") or [],
                "payment_count": int(body.get("payment_count") or (len(recon_report["allocations"]) if recon_report else 0)),
                "has_refund_or_adjustment": bool(
                    body.get("has_refund_or_adjustment")
                    or (
                        recon_report
                        and (recon_report["refund_and_reversal_vnd"] > 0 or recon_report["adjustment_signed_vnd"] != 0)
                    )
                ),
                "reconciliation_status": body.get("reconciliation_status") or (recon_report["status"] if recon_report else ""),
            }
            checklist = remediation_store.evaluate_and_store_checklist(
                scope,
                ctx,
                snapshot_tables=body.get("snapshot_tables"),
                available_sources=avail_sources,
                policy=body.get("policy"),
                human_overrides=body.get("human_overrides"),
                reconciliation=recon_report,
                issue_type=body.get("issue_type"),
                recheck=recheck,
            )
            handler.respond(200, canonical({"checklist": checklist, "reconciliation": recon_report}))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    m = _CASE_DOCS_RE.fullmatch(path)
    if m:
        try:
            company_id, case_key = m[1], m[2]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method != "POST":
                fail(405, "METHOD_NOT_ALLOWED", "Tải chứng từ dùng POST JSON.", "Gửi POST.")
            _require_store()
            body = read_json(handler)
            if not isinstance(body, dict):
                fail(400, "INVALID_BODY", "Body phải là JSON object.", "Gửi JSON hợp lệ.")
            allowed = {
                "obligation_id",
                "document_type",
                "filename",
                "mime",
                "content_base64",
                "document_date",
                "source_kind",
                "note",
                "document_id",
                "case_as_of",
                "requested_verification_status",
                "idempotency_key",
            }
            if set(body) - allowed:
                fail(400, "UNSUPPORTED_FIELDS", "Trường tải chứng từ không hợp lệ.", "Kiểm tra danh sách trường cho phép.")
            b64 = body.get("content_base64")
            if not isinstance(b64, str) or not b64:
                fail(422, "CONTENT_BASE64_REQUIRED", "Thiếu content_base64 của tệp chứng từ.", "Mã hóa tệp sang base64.")
            try:
                content = base64.b64decode(b64, validate=True)
            except (binascii.Error, ValueError):
                fail(422, "INVALID_BASE64", "content_base64 không hợp lệ.", "Kiểm tra chuỗi base64.")
            idem = _extract_idempotency_key(handler, body, required=False)
            res = remediation_store.upload_document(
                scope,
                case_id=case_key,
                obligation_id=body.get("obligation_id"),
                document_type=str(body.get("document_type") or ""),
                filename=str(body.get("filename") or ""),
                mime=str(body.get("mime") or ""),
                content=content,
                document_date=body.get("document_date"),
                source_kind=str(body.get("source_kind") or "enterprise_upload"),
                note=str(body.get("note") or ""),
                document_id=body.get("document_id"),
                case_as_of=body.get("case_as_of"),
                idempotency_key=idem,
                requested_verification_status=body.get("requested_verification_status"),
                recheck=recheck,
            )
            handler.respond(200, canonical(res))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    m = _DOC_GET_RE.fullmatch(path)
    if m:
        try:
            company_id, doc_id, ver_str, want_content = m[1], m[2], m[3], m[4]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method != "GET":
                fail(405, "METHOD_NOT_ALLOWED", "Đọc chứng từ dùng GET.", "Gửi GET.")
            _require_store()
            ver_no = int(ver_str) if ver_str else None
            res = remediation_store.get_document(scope, doc_id, version=ver_no, include_bytes=bool(want_content), recheck=recheck)
            if want_content:
                handler.respond(200, res["content"], res["mime"])
            else:
                handler.respond(200, canonical(res))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    m = _DOC_VERIFY_RE.fullmatch(path)
    if m:
        try:
            company_id, doc_id = m[1], m[2]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method != "POST":
                fail(405, "METHOD_NOT_ALLOWED", "Xác minh chứng từ dùng POST.", "Gửi POST JSON.")
            _require_store()
            body = read_json(handler)
            if not isinstance(body, dict) or (set(body) - {"decision", "verification_note", "version"}):
                fail(400, "INVALID_BODY", "Body chỉ nhận decision, verification_note, version.", "Kiểm tra payload xác minh.")
            doc = remediation_store.verify_document(
                scope,
                document_id=doc_id,
                decision=str(body.get("decision") or ""),
                verification_note=str(body.get("verification_note") or ""),
                version=body.get("version"),
                recheck=recheck,
            )
            handler.respond(200, canonical({"document": doc}))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    m = _TASK_CREATE_RE.fullmatch(path)
    if m:
        try:
            company_id = m[1]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method != "POST":
                fail(405, "METHOD_NOT_ALLOWED", "Tạo tác vụ dùng POST.", "Gửi POST JSON.")
            _require_store()
            body = read_json(handler)
            if not isinstance(body, dict):
                fail(400, "INVALID_BODY", "Body phải là JSON object.", "Gửi JSON hợp lệ.")
            allowed = {
                "case_id",
                "obligation_id",
                "task_type",
                "issue_type",
                "title",
                "what_to_do",
                "reason",
                "assignee_kind",
                "assignee_key",
                "assignee_label",
                "due_at",
                "require_evidence",
                "required_document_types",
                "allow_multiple_open",
                "idempotency_key",
            }
            if set(body) - allowed:
                fail(400, "UNSUPPORTED_FIELDS", "Trường tạo ActionTask không hợp lệ.", "Kiểm tra danh sách trường hợp lệ.")
            idem = _extract_idempotency_key(handler, body, required=True)
            res = remediation_store.create_task(
                scope,
                case_id=str(body.get("case_id") or ""),
                obligation_id=body.get("obligation_id"),
                task_type=str(body.get("task_type") or ""),
                issue_type=str(body.get("issue_type") or ""),
                title=str(body.get("title") or ""),
                what_to_do=str(body.get("what_to_do") or ""),
                reason=str(body.get("reason") or ""),
                assignee_kind=str(body.get("assignee_kind") or "department_role"),
                assignee_key=str(body.get("assignee_key") or ""),
                assignee_label=str(body.get("assignee_label") or ""),
                due_at=body.get("due_at"),
                require_evidence=bool(body.get("require_evidence", True)),
                required_document_types=body.get("required_document_types") or (),
                allow_multiple_open=bool(body.get("allow_multiple_open", False)),
                idempotency_key=idem,
                recheck=recheck,
            )
            handler.respond(200, canonical(res))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    m = _TASK_ASSIGN_RE.fullmatch(path)
    if m:
        try:
            company_id, task_id = m[1], m[2]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method != "POST":
                fail(405, "METHOD_NOT_ALLOWED", "Giao lại/gia hạn tác vụ dùng POST.", "Gửi POST JSON.")
            _require_store()
            body = read_json(handler)
            if not isinstance(body, dict) or (set(body) - {"expected_revision", "assignee_kind", "assignee_key", "assignee_label", "due_at", "clear_due_at", "reason"}):
                fail(400, "INVALID_BODY", "Trường assign không hợp lệ.", "Kiểm tra payload.")
            if not isinstance(body.get("expected_revision"), int):
                fail(422, "EXPECTED_REVISION_REQUIRED", "Bắt buộc gửi expected_revision kiểu số nguyên.", "Truyền revision hiện tại.")
            task = remediation_store.assign_task(
                scope,
                task_id=task_id,
                expected_revision=int(body["expected_revision"]),
                assignee_kind=str(body.get("assignee_kind") or ""),
                assignee_key=str(body.get("assignee_key") or ""),
                assignee_label=str(body.get("assignee_label") or ""),
                due_at=body.get("due_at"),
                clear_due_at=bool(body.get("clear_due_at", False)),
                reason=str(body.get("reason") or ""),
                recheck=recheck,
            )
            handler.respond(200, canonical({"task": task}))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    m = _TASK_SUBMIT_RE.fullmatch(path)
    if m:
        try:
            company_id, task_id = m[1], m[2]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method != "POST":
                fail(405, "METHOD_NOT_ALLOWED", "Nộp kết quả tác vụ dùng POST.", "Gửi POST JSON.")
            _require_store()
            body = read_json(handler)
            if not isinstance(body, dict) or (set(body) - {"expected_revision", "result_summary", "document_ids", "evidence_ids", "waiting_external"}):
                fail(400, "INVALID_BODY", "Trường submit không hợp lệ.", "Kiểm tra payload.")
            if not isinstance(body.get("expected_revision"), int):
                fail(422, "EXPECTED_REVISION_REQUIRED", "Bắt buộc gửi expected_revision.", "Truyền revision hiện tại.")
            task = remediation_store.submit_task(
                scope,
                task_id=task_id,
                expected_revision=int(body["expected_revision"]),
                result_summary=str(body.get("result_summary") or ""),
                document_ids=body.get("document_ids") or (),
                evidence_ids=body.get("evidence_ids") or (),
                waiting_external=bool(body.get("waiting_external", False)),
                recheck=recheck,
            )
            handler.respond(200, canonical({"task": task}))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    m = _TASK_DECISION_RE.fullmatch(path)
    if m:
        try:
            company_id, task_id = m[1], m[2]
            scope, recheck = authorize_request(handler, authorizer, company_id)
            if method != "POST":
                fail(405, "METHOD_NOT_ALLOWED", "Xác nhận/yêu cầu làm lại/mở lại tác vụ dùng POST.", "Gửi POST JSON.")
            _require_store()
            body = read_json(handler)
            if not isinstance(body, dict) or (set(body) - {"expected_revision", "decision", "note"}):
                fail(400, "INVALID_BODY", "Trường decision không hợp lệ.", "Chỉ truyền expected_revision, decision, note.")
            if not isinstance(body.get("expected_revision"), int):
                fail(422, "EXPECTED_REVISION_REQUIRED", "Bắt buộc gửi expected_revision.", "Truyền revision hiện tại.")
            task = remediation_store.decide_task(
                scope,
                task_id=task_id,
                expected_revision=int(body["expected_revision"]),
                decision=str(body.get("decision") or ""),
                note=str(body.get("note") or ""),
                recheck=recheck,
            )
            handler.respond(200, canonical({"task": task}))
        except (AuthError, ImportFailure) as error:
            respond_failure(handler, error)
        return True

    return False
