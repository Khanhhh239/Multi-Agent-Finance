"""SQLite ACID storage, schema migration, evidence versioning, ActionTask lifecycle, and business reports for R4."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any

from .import_files import ImportFailure, canonical, digest, fail
from .remediation_policy import (
    ACTION_TASK_STATUSES,
    ALLOWED_DOCUMENT_MIMES,
    BUSINESS_REPORT_SCHEMA_VERSION,
    CHECKLIST_ITEM_STATUSES,
    DOCUMENT_SCHEMA_VERSION,
    ISSUE_TYPES,
    MAX_DOCUMENT_BYTES,
    TASK_SCHEMA_VERSION,
    default_document_requirement_policy,
    evaluate_document_checklist,
    parse_iso_datetime,
    validate_against_schema,
)

APPLICATION_ID = 1380271437
CURRENT_SCHEMA_VERSION = 2
_BUSY_ERRORS = ("database is locked", "database schema is locked", "locking protocol")

ROLE_LABELS_VI = {
    "ke_toan_cong_no": "Bộ phận Kế toán công nợ",
    "nhan_su_tien_luong": "Bộ phận Nhân sự & Tiền lương",
    "ke_toan_thanh_toan": "Bộ phận Kế toán thanh toán",
    "kiem_soat_noi_bo": "Bộ phận Kiểm soát nội bộ",
    "phe_duyet_tai_chinh": "Bộ phận Phê duyệt tài chính",
    "ke_toan_tong_hop": "Bộ phận Kế toán tổng hợp",
    "giam_doc": "Ban Giám đốc",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str, *parts: Any) -> str:
    entropy = os.urandom(8).hex()
    return f"{prefix}_" + digest(canonical([prefix, entropy, *parts]))[:24]


def _normalize_optional_date(value: str | None, *, field_name: str = "document_date") -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        # Normalize date-only strings explicitly to Vietnam standard offset rather than naive midnight.
        raw = f"{raw}T00:00:00+07:00"
    dt = parse_iso_datetime(raw, field_name=field_name)
    return dt.isoformat()


def _require_read_scope(scope, recheck=None) -> tuple[str, str, str]:
    if scope is None or len(scope.company_ids) != 1:
        fail(403, "ACCESS_DENIED", "Không có quyền truy cập dữ liệu xử lý hồ sơ cho doanh nghiệp này.", "Kiểm tra membership công ty.")
    perms = set(scope.permissions or ())
    if "data.import" not in perms and "evidence.verify" not in perms:
        fail(
            403,
            "ACCESS_DENIED",
            "Tài khoản không có quyền nghiệp vụ (cần data.import hoặc evidence.verify; quyền model.fit không mở quyền hồ sơ/tác vụ).",
            "Cấp quyền nghiệp vụ phù hợp trên Portal.",
        )
    if recheck is not None:
        current = recheck()
        if current != scope:
            fail(409, "AUTH_CONTEXT_CHANGED", "Quyền đã thay đổi trong lúc xử lý.", "Thử lại với phiên hiện hành.")
    return str(scope.tenant_id), str(next(iter(scope.company_ids))), str(scope.actor_id)


def _require_operator_scope(scope, recheck=None) -> tuple[str, str, str]:
    tenant_id, company_id, actor_id = _require_read_scope(scope, recheck)
    perms = set(scope.permissions or ())
    if "data.import" not in perms:
        fail(
            403,
            "OPERATOR_PERMISSION_REQUIRED",
            "Thao tác nghiệp vụ này yêu cầu quyền data.import của doanh nghiệp (không chấp nhận model.fit đơn lẻ).",
            "Kiểm tra quyền tài khoản trong access policy.",
        )
    return tenant_id, company_id, actor_id


def _scope_role_label(scope) -> str:
    perms = set(scope.permissions or ())
    return "verifier" if "evidence.verify" in perms else "operator"


def _require_verifier_scope(scope, recheck=None) -> tuple[str, str, str]:
    tenant_id, company_id, actor_id = _require_read_scope(scope, recheck)
    perms = set(scope.permissions or ())
    if "evidence.verify" not in perms:
        fail(
            403,
            "VERIFIER_PERMISSION_REQUIRED",
            "Xác minh chứng từ hoặc xác nhận hoàn tất tác vụ yêu cầu quyền evidence.verify.",
            "Chuyển cho người có thẩm quyền xác minh.",
        )
    return tenant_id, company_id, actor_id


def build_assignee_ref(
    *,
    assignee_kind: str,
    assignee_key: str,
    display_label: str = "",
) -> dict[str, Any]:
    kind = str(assignee_kind or "").strip()
    key = str(assignee_key or "").strip()
    if kind not in ("server_actor", "department_role"):
        fail(422, "INVALID_ASSIGNEE_KIND", "assignee_kind phải là 'server_actor' hoặc 'department_role'.", "Không dùng tên gõ tay tự do làm định danh đã xác thực.")
    if not key:
        fail(422, "ASSIGNEE_KEY_REQUIRED", "Thiếu mã người phụ trách hoặc mã bộ phận.", "Cung cấp assignee_key hợp lệ.")
    if kind == "server_actor":
        note = "Định danh tài khoản cấp phát từ cấu hình xác thực server; nếu Portal dùng tài khoản dùng chung thì đây là actor workspace."
        verified = False  # Portal currently uses shared workspace login unless per-user IAM proves otherwise.
        label = display_label or key
    else:
        note = "Phân công theo vai trò/bộ phận nghiệp vụ; tên hiển thị không thay thế xác thực danh tính cá nhân."
        verified = False
        label = display_label or ROLE_LABELS_VI.get(key, key)
    return {
        "assignee_kind": kind,
        "assignee_key": key,
        "display_label": label,
        "identity_verified": verified,
        "identity_note": note,
    }


def compute_next_step_vi(
    checklist: dict[str, Any] | None,
    tasks: list[dict[str, Any]],
) -> str:
    active_tasks = [t for t in tasks if t["status"] in ("open", "in_progress", "waiting_external")]
    awaiting = [
        t
        for t in active_tasks
        if t.get("submission") is not None
        and (
            t.get("verification") is None
            or t["verification"]["confirmed_at"] < t["submission"]["submitted_at"]
        )
    ]
    if awaiting:
        return f"Người có thẩm quyền rà soát kết quả đã gửi và xác nhận hoàn tất hoặc yêu cầu làm lại cho {len(awaiting)} công việc."
    if checklist:
        summary = checklist["summary"]
        if summary["missing"] > 0:
            if active_tasks:
                return f"Còn {summary['missing']} chứng từ xác nhận thiếu; người phụ trách tải bổ sung lên tác vụ đang mở."
            return f"Giao việc hoặc gửi yêu cầu bổ sung {summary['missing']} chứng từ đang xác nhận thiếu."
        if summary["pending_verification"] > 0:
            return f"Còn {summary['pending_verification']} chứng từ đã nhận chưa xác minh; người có quyền kiểm tra đối chiếu và xác nhận."
        if summary["unknown"] > 0:
            return f"Bổ sung nguồn dữ liệu hoặc kiểm tra thủ công cho {summary['unknown']} mục chứng từ chưa có nguồn kiểm tra."
    if active_tasks:
        return f"Tiếp tục xử lý {len(active_tasks)} công việc khắc phục đang mở."
    if checklist and checklist["summary"]["ready_for_closure"]:
        return "Hồ sơ đã đủ chứng từ xác minh; sẵn sàng tổng hợp báo cáo hoặc xem xét đóng vụ độc lập."
    return "Kiểm tra hồ sơ chứng từ và mở công việc khắc phục nếu phát hiện chênh lệch."


class RemediationStore:
    """Thread-safe SQLite ACID store scoped strictly by (tenant_id, company_id)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("PRAGMA journal_mode = WAL")
                app_id = conn.execute("PRAGMA application_id").fetchone()[0]
                if app_id not in (0, APPLICATION_ID):
                    fail(
                        500,
                        "INVALID_REMEDIATION_DB",
                        f"File SQLite {self.path} thuộc application_id={app_id}, không phải RemediationStore.",
                        "Dùng đường dẫn remediation.sqlite3 riêng.",
                    )
                conn.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                self._migrate_locked(conn)
            finally:
                conn.close()

    @staticmethod
    def _ensure_base_tables(conn: sqlite3.Connection) -> None:
        stmts = (
            """
            CREATE TABLE IF NOT EXISTS remediation_policies (
                policy_key TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                policy_id TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                policy_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS document_checklists (
                tenant_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                obligation_id TEXT NOT NULL,
                checklist_id TEXT NOT NULL,
                policy_id TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                problem_family TEXT NOT NULL,
                as_of TEXT,
                overrides_json TEXT NOT NULL,
                checklist_json TEXT NOT NULL,
                revision INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                PRIMARY KEY (tenant_id, company_id, case_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS evidence_documents (
                tenant_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                obligation_id TEXT NOT NULL,
                document_type TEXT NOT NULL,
                current_version INTEGER NOT NULL,
                verification_status TEXT NOT NULL,
                late_arrival_after_as_of INTEGER NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, company_id, document_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS evidence_document_versions (
                tenant_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                filename TEXT NOT NULL,
                mime TEXT NOT NULL,
                size INTEGER NOT NULL,
                document_date TEXT,
                received_at TEXT NOT NULL,
                uploaded_by TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                verification_status TEXT NOT NULL,
                version_json TEXT NOT NULL,
                content_blob BLOB NOT NULL,
                PRIMARY KEY (tenant_id, company_id, document_id, version),
                FOREIGN KEY (tenant_id, company_id, document_id)
                    REFERENCES evidence_documents(tenant_id, company_id, document_id)
                    ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS action_tasks (
                tenant_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                obligation_id TEXT NOT NULL,
                task_type TEXT NOT NULL,
                revision INTEGER NOT NULL,
                status TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                assignee_kind TEXT NOT NULL,
                assignee_key TEXT NOT NULL,
                due_at TEXT,
                deduplicate_slot INTEGER NOT NULL DEFAULT 1,
                task_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, company_id, task_id)
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_open_task_slot
            ON action_tasks (tenant_id, company_id, case_id, obligation_id, task_type)
            WHERE status IN ('open', 'in_progress', 'waiting_external') AND deduplicate_slot = 1
            """,
            """
            CREATE TABLE IF NOT EXISTS action_task_revisions (
                tenant_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                status TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                at TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                PRIMARY KEY (tenant_id, company_id, task_id, revision)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS case_financial_links (
                tenant_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                obligation_id TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                reconciliation_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, company_id, case_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS request_receipts (
                tenant_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, company_id, operation, idempotency_key)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS remediation_audit_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                tenant_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                detail_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_remediation_audit_no_update
            BEFORE UPDATE ON remediation_audit_events
            BEGIN
                SELECT RAISE(ABORT, 'remediation_audit_events is append-only');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_remediation_audit_no_delete
            BEFORE DELETE ON remediation_audit_events
            BEGIN
                SELECT RAISE(ABORT, 'remediation_audit_events is append-only');
            END
            """,
        )
        for stmt in stmts:
            conn.execute(stmt)

    def _migrate_locked(self, conn: sqlite3.Connection) -> None:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL,
                    note TEXT NOT NULL
                )
                """
            )
            row = conn.execute("SELECT COALESCE(MAX(version), 0) AS ver FROM schema_migrations").fetchone()
            cur = int(row["ver"]) if row else 0
            now = _utc_now()
            if cur < 1:
                self._ensure_base_tables(conn)
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at, note) VALUES (?, ?, ?)",
                    (1, now, "v1 base remediation tables"),
                )
                cur = 1
            if cur < 2:
                self._ensure_base_tables(conn)
                cols = {r[1] for r in conn.execute("PRAGMA table_info(case_financial_links)").fetchall()}
                if "case_context_json" not in cols:
                    conn.execute(
                        "ALTER TABLE case_financial_links ADD COLUMN case_context_json TEXT NOT NULL DEFAULT '{}'"
                    )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tasks_company_status ON action_tasks (tenant_id, company_id, status, due_at)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_docs_company_case ON evidence_documents (tenant_id, company_id, case_id, document_type)"
                )
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at, note) VALUES (?, ?, ?)",
                    (2, now, "v2 case_context_json and query indexes"),
                )
            if conn.in_transaction:
                conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

    @contextmanager
    def _write_tx(self):
        with self._lock:
            last_err = None
            for attempt in range(8):
                conn = self._connect()
                try:
                    conn.execute("BEGIN IMMEDIATE")
                except sqlite3.OperationalError as exc:
                    conn.close()
                    if any(msg in str(exc).lower() for msg in _BUSY_ERRORS) and attempt < 7:
                        last_err = exc
                        time.sleep(0.015 * (attempt + 1))
                        continue
                    raise
                try:
                    yield conn
                    conn.execute("COMMIT")
                    return
                except Exception:
                    try:
                        conn.execute("ROLLBACK")
                    except sqlite3.Error:
                        pass
                    raise
                finally:
                    conn.close()
            if last_err is not None:
                raise last_err

    @contextmanager
    def _read_conn(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def schema_versions(self) -> list[dict[str, Any]]:
        with self._read_conn() as conn:
            rows = conn.execute("SELECT version, applied_at, note FROM schema_migrations ORDER BY version").fetchall()
            return [dict(r) for r in rows]

    def _insert_audit(
        self,
        conn: sqlite3.Connection,
        *,
        tenant_id: str,
        company_id: str,
        entity_type: str,
        entity_id: str,
        event_type: str,
        actor_id: str,
        actor_role: str,
        detail: dict[str, Any],
        created_at: str | None = None,
    ) -> str:
        ev_id = _new_id("raud", tenant_id, company_id, entity_id, event_type, created_at or _utc_now())
        conn.execute(
            """
            INSERT INTO remediation_audit_events (
                event_id, tenant_id, company_id, entity_type, entity_id, event_type,
                actor_id, actor_role, detail_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ev_id,
                tenant_id,
                company_id,
                entity_type,
                entity_id,
                event_type,
                actor_id,
                actor_role,
                canonical(detail),
                created_at or _utc_now(),
            ),
        )
        return ev_id

    def _check_idempotency(
        self,
        conn: sqlite3.Connection,
        *,
        tenant_id: str,
        company_id: str,
        operation: str,
        idempotency_key: str | None,
        payload_hash: str,
    ) -> dict[str, Any] | None:
        if not idempotency_key:
            return None
        row = conn.execute(
            """
            SELECT payload_hash, response_json
            FROM request_receipts
            WHERE tenant_id = ? AND company_id = ? AND operation = ? AND idempotency_key = ?
            """,
            (tenant_id, company_id, operation, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        if row["payload_hash"] != payload_hash:
            fail(
                409,
                "IDEMPOTENCY_PAYLOAD_MISMATCH",
                f"Idempotency-Key '{idempotency_key}' đã dùng cho payload khác.",
                "Dùng Idempotency-Key mới cho yêu cầu có nội dung khác.",
            )
        cached = json.loads(row["response_json"])
        cached["idempotent_replay"] = True
        return cached

    def _save_receipt(
        self,
        conn: sqlite3.Connection,
        *,
        tenant_id: str,
        company_id: str,
        operation: str,
        idempotency_key: str | None,
        payload_hash: str,
        response: dict[str, Any],
        created_at: str,
    ) -> None:
        if not idempotency_key:
            return
        conn.execute(
            """
            INSERT OR IGNORE INTO request_receipts (
                tenant_id, company_id, operation, idempotency_key, payload_hash, response_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (tenant_id, company_id, operation, idempotency_key, payload_hash, canonical(response), created_at),
        )

    def _load_documents_for_case_conn(
        self,
        conn: sqlite3.Connection,
        tenant_id: str,
        company_id: str,
        case_id: str,
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT metadata_json
            FROM evidence_documents
            WHERE tenant_id = ? AND company_id = ? AND case_id = ?
            ORDER BY created_at, document_id
            """,
            (tenant_id, company_id, case_id),
        ).fetchall()
        return [json.loads(r["metadata_json"]) for r in rows]

    def _load_tasks_for_case_conn(
        self,
        conn: sqlite3.Connection,
        tenant_id: str,
        company_id: str,
        case_id: str,
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT task_json
            FROM action_tasks
            WHERE tenant_id = ? AND company_id = ? AND case_id = ?
            ORDER BY created_at, task_id
            """,
            (tenant_id, company_id, case_id),
        ).fetchall()
        return [json.loads(r["task_json"]) for r in rows]

    def save_policy(self, scope, policy: dict[str, Any], *, recheck=None) -> dict[str, Any]:
        tenant_id, company_id, actor_id = _require_verifier_scope(scope, recheck)
        validate_against_schema(policy, "document_requirement_policy")
        key = f"{tenant_id}:{company_id}:{policy['policy_id']}:{policy['policy_version']}"
        now = _utc_now()
        with self._write_tx() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO remediation_policies (
                    policy_key, tenant_id, company_id, policy_id, policy_version, policy_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (key, tenant_id, company_id, policy["policy_id"], policy["policy_version"], canonical(policy), now),
            )
            self._insert_audit(
                conn,
                tenant_id=tenant_id,
                company_id=company_id,
                entity_type="policy",
                entity_id=key,
                event_type="policy_saved",
                actor_id=actor_id,
                actor_role=str(getattr(scope, "role", "")),
                detail={"policy_id": policy["policy_id"], "policy_version": policy["policy_version"]},
                created_at=now,
            )
        return deepcopy(policy)

    def evaluate_and_store_checklist(
        self,
        scope,
        context: dict[str, Any],
        *,
        snapshot_tables: dict[str, Any] | None = None,
        available_sources: set[str] | list[str] | tuple[str, ...] | None = None,
        policy: dict[str, Any] | None = None,
        human_overrides: dict[str, dict[str, Any]] | None = None,
        reconciliation: dict[str, Any] | None = None,
        issue_type: str | None = None,
        recheck=None,
    ) -> dict[str, Any]:
        """Evaluate and persist DocumentChecklist inside company scope without creating duplicate tasks."""
        if human_overrides:
            # Confirming present/missing manually requires verifier privilege.
            for ovr in human_overrides.values():
                if ovr.get("item_status") in ("present", "missing", "not_applicable"):
                    _require_verifier_scope(scope, recheck)
                    break
            else:
                _require_operator_scope(scope, recheck)
        else:
            _require_operator_scope(scope, recheck)

        tenant_id = str(scope.tenant_id)
        company_id = str(next(iter(scope.company_ids)))
        actor_id = str(scope.actor_id)
        role = str(getattr(scope, "role", "") or "accountant")

        case_id = str(context.get("case_id") or "").strip()
        obligation_id = str(context.get("obligation_id") or case_id).strip()
        if not case_id:
            fail(422, "CASE_ID_REQUIRED", "Thiếu case_id để đánh giá hồ sơ.", "Cung cấp case_id hợp lệ.")
        as_of = context.get("as_of")
        if as_of is not None:
            parse_iso_datetime(str(as_of), field_name="as_of")

        with self._write_tx() as conn:
            docs = self._load_documents_for_case_conn(conn, tenant_id, company_id, case_id)
            prev_row = conn.execute(
                """
                SELECT revision, overrides_json, checklist_json
                FROM document_checklists
                WHERE tenant_id = ? AND company_id = ? AND case_id = ?
                """,
                (tenant_id, company_id, case_id),
            ).fetchone()
            merged_overrides = json.loads(prev_row["overrides_json"]) if prev_row else {}
            if human_overrides:
                for dt, ovr in human_overrides.items():
                    status = str(ovr.get("item_status") or "").strip()
                    if status not in CHECKLIST_ITEM_STATUSES:
                        fail(422, "INVALID_CHECKLIST_STATUS", f"Trạng thái chứng từ không hợp lệ: {status}.", f"Chọn trong {CHECKLIST_ITEM_STATUSES}.")
                    merged_overrides[str(dt)] = {
                        "item_status": status,
                        "checked_by": actor_id,
                        "note": str(ovr.get("note") or f"Cập nhật bởi {actor_id}"),
                    }

            rev = (int(prev_row["revision"]) + 1) if prev_row else 1
            now = _utc_now()
            eval_ctx = dict(context)
            eval_ctx.update(
                {
                    "tenant_id": tenant_id,
                    "company_id": company_id,
                    "case_id": case_id,
                    "obligation_id": obligation_id,
                }
            )
            checklist = evaluate_document_checklist(
                eval_ctx,
                docs,
                snapshot_tables=snapshot_tables,
                policy=policy,
                available_sources=available_sources,
                as_of=as_of,
                checked_by=actor_id,
                checked_at=now,
                human_overrides=merged_overrides,
                revision=rev,
            )

            conn.execute(
                """
                INSERT OR REPLACE INTO document_checklists (
                    tenant_id, company_id, case_id, obligation_id, checklist_id,
                    policy_id, policy_version, problem_family, as_of,
                    overrides_json, checklist_json, revision, updated_at, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    company_id,
                    case_id,
                    obligation_id,
                    checklist["checklist_id"],
                    checklist["policy_id"],
                    checklist["policy_version"],
                    checklist["problem_family"],
                    as_of,
                    canonical(merged_overrides),
                    canonical(checklist),
                    rev,
                    now,
                    actor_id,
                ),
            )
            existing_link = conn.execute(
                "SELECT issue_type, reconciliation_json FROM case_financial_links WHERE tenant_id = ? AND company_id = ? AND case_id = ?",
                (tenant_id, company_id, case_id),
            ).fetchone()
            ctx_snapshot = {
                "problem_family": checklist["problem_family"],
                "rule_ids": checklist["rule_ids"],
                "as_of": as_of,
                "available_sources": sorted(available_sources) if available_sources is not None else sorted(k for k in (snapshot_tables or {}).keys() if (snapshot_tables or {})[k] is not None),
                "applicability_flags": list(context.get("applicability_flags") or []),
                "payment_count": int(context.get("payment_count") or 0),
                "has_refund_or_adjustment": bool(context.get("has_refund_or_adjustment")),
                "exceeds_split_threshold": bool(context.get("exceeds_split_threshold")),
                "reconciliation_status": str(context.get("reconciliation_status") or (reconciliation["status"] if reconciliation is not None else "")),
            }
            if reconciliation is not None:
                validate_against_schema(reconciliation, "reconciliation_report")
                if str(reconciliation["company_id"]) != company_id:
                    fail(403, "CROSS_COMPANY_FORBIDDEN", "Không được gắn đối chiếu của doanh nghiệp khác.", "Kiểm tra company_id.")
                it_type = str(issue_type or context.get("issue_type") or (existing_link["issue_type"] if existing_link else "payment_discrepancy"))
                if it_type not in ISSUE_TYPES:
                    fail(422, "INVALID_ISSUE_TYPE", f"issue_type không hợp lệ: {it_type}.", f"Chọn trong {ISSUE_TYPES}.")
                recon_json = canonical(reconciliation)
            else:
                it_type = str(issue_type or context.get("issue_type") or (existing_link["issue_type"] if existing_link else "missing_document"))
                if it_type not in ISSUE_TYPES:
                    it_type = "missing_document"
                recon_json = existing_link["reconciliation_json"] if existing_link else "{}"

            conn.execute(
                """
                INSERT OR REPLACE INTO case_financial_links (
                    tenant_id, company_id, case_id, obligation_id, issue_type, reconciliation_json, updated_at, case_context_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    company_id,
                    case_id,
                    obligation_id,
                    it_type,
                    recon_json,
                    now,
                    canonical(ctx_snapshot),
                ),
            )

            self._insert_audit(
                conn,
                tenant_id=tenant_id,
                company_id=company_id,
                entity_type="checklist",
                entity_id=checklist["checklist_id"],
                event_type="checklist_evaluated",
                actor_id=actor_id,
                actor_role=role,
                detail={"case_id": case_id, "revision": rev, "summary": checklist["summary"]},
                created_at=now,
            )
            return checklist

    def upload_document(
        self,
        scope,
        *,
        case_id: str,
        obligation_id: str | None = None,
        document_type: str,
        filename: str,
        mime: str,
        content: bytes,
        document_date: str | None = None,
        source_kind: str = "enterprise_upload",
        note: str = "",
        document_id: str | None = None,
        case_as_of: str | None = None,
        idempotency_key: str | None = None,
        requested_verification_status: str | None = None,
        recheck=None,
    ) -> dict[str, Any]:
        """Store an unverified evidence document (or new version) cleanly inside company scope.

        Rule guarantees:
        - Uploading a file NEVER self-verifies (`verification_status` always starts at 'pending_verification').
        - Late arrival after snapshot `case_as_of` sets `late_arrival_after_as_of=True` and NEVER alters snapshots/features.
        """
        tenant_id, company_id, actor_id = _require_operator_scope(scope, recheck)
        role = str(getattr(scope, "role", "") or "accountant")

        if requested_verification_status and requested_verification_status != "pending_verification":
            fail(
                422,
                "SELF_VERIFICATION_FORBIDDEN",
                "Không được tự đánh dấu Đã xác minh ngay khi tải tệp; chứng từ mới bắt buộc qua bước kiểm tra.",
                "Tải tệp ở trạng thái pending_verification rồi gọi endpoint verify.",
            )
        cid_case = str(case_id or "").strip()
        ob_id = str(obligation_id or cid_case).strip()
        dt = str(document_type or "").strip()
        fname = Path(str(filename or "").strip()).name
        if not cid_case or not dt or not fname:
            fail(422, "DOCUMENT_FIELDS_REQUIRED", "Thiếu case_id, document_type hoặc filename.", "Cung cấp đủ thông tin chứng từ.")
        if mime not in ALLOWED_DOCUMENT_MIMES:
            fail(415, "UNSUPPORTED_MEDIA_TYPE", "Chỉ chấp nhận tệp PDF, PNG hoặc JPEG.", f"Chọn MIME trong {ALLOWED_DOCUMENT_MIMES}.")
        if not isinstance(content, (bytes, bytearray)) or len(content) == 0:
            fail(422, "EMPTY_DOCUMENT", "Tệp chứng từ không được rỗng.", "Chọn tệp hợp lệ.")
        if len(content) > MAX_DOCUMENT_BYTES:
            fail(413, "DOCUMENT_TOO_LARGE", f"Tệp chứng từ vượt giới hạn {MAX_DOCUMENT_BYTES} bytes.", "Giảm kích thước tệp <= 2 MiB.")
        if source_kind not in ("enterprise_upload", "snapshot_source", "accounting_export", "bank_statement", "hr_record"):
            fail(422, "INVALID_SOURCE_KIND", f"source_kind không hợp lệ: {source_kind}.", "Chọn source_kind chuẩn.")

        doc_date_iso = _normalize_optional_date(document_date, field_name="document_date")
        sha = hashlib.sha256(bytes(content)).hexdigest()
        payload_hash = digest(
            canonical(
                [
                    cid_case,
                    ob_id,
                    dt,
                    fname,
                    mime,
                    sha,
                    doc_date_iso,
                    source_kind,
                    note,
                    document_id or "",
                ]
            )
        )

        with self._write_tx() as conn:
            cached = self._check_idempotency(
                conn,
                tenant_id=tenant_id,
                company_id=company_id,
                operation="upload_document",
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
            )
            if cached is not None:
                return cached

            now = _utc_now()
            now_dt = parse_iso_datetime(now, field_name="received_at")
            as_of_str = case_as_of
            if as_of_str is None:
                chk_row = conn.execute(
                    "SELECT as_of FROM document_checklists WHERE tenant_id = ? AND company_id = ? AND case_id = ?",
                    (tenant_id, company_id, cid_case),
                ).fetchone()
                if chk_row:
                    as_of_str = chk_row["as_of"]
            as_of_dt = parse_iso_datetime(as_of_str, field_name="case_as_of") if as_of_str else None
            late = False
            if as_of_dt is not None:
                doc_dt = parse_iso_datetime(doc_date_iso, field_name="document_date") if doc_date_iso else None
                late = (now_dt > as_of_dt) or (doc_dt is not None and doc_dt > as_of_dt)

            if document_id:
                existing = conn.execute(
                    """
                    SELECT metadata_json, case_id
                    FROM evidence_documents
                    WHERE tenant_id = ? AND company_id = ? AND document_id = ?
                    """,
                    (tenant_id, company_id, document_id),
                ).fetchone()
                if existing is None:
                    fail(404, "DOCUMENT_NOT_FOUND", f"Không tìm thấy document_id {document_id} trong doanh nghiệp này.", "Kiểm tra lại document_id.")
                if existing["case_id"] != cid_case:
                    fail(409, "DOCUMENT_CASE_MISMATCH", "document_id thuộc về vụ việc khác.", "Không gắn chéo chứng từ sang vụ khác.")
                meta = json.loads(existing["metadata_json"])
                prev_ver = int(meta["current_version"])
                ver_no = prev_ver + 1
                supersedes = prev_ver
                doc_id = str(document_id)
            else:
                doc_id = _new_id("doc", tenant_id, company_id, cid_case, dt, sha)
                ver_no = 1
                supersedes = None
                meta = {
                    "schema_version": DOCUMENT_SCHEMA_VERSION,
                    "document_id": doc_id,
                    "tenant_id": tenant_id,
                    "company_id": company_id,
                    "case_id": cid_case,
                    "obligation_id": ob_id,
                    "document_type": dt,
                    "current_version": 1,
                    "verification_status": "pending_verification",
                    "late_arrival_after_as_of": late,
                    "mutates_snapshot_or_features": False,
                    "versions": [],
                    "created_at": now,
                    "updated_at": now,
                }

            ver_entry = {
                "version": ver_no,
                "sha256": sha,
                "filename": fname,
                "mime": mime,
                "size": len(content),
                "document_date": doc_date_iso,
                "received_at": now,
                "uploaded_by": actor_id,
                "uploaded_role": role,
                "source_kind": source_kind,
                "note": str(note or ""),
                "supersedes_version": supersedes,
                "late_arrival_after_as_of": late,
                "verification_status": "pending_verification",
                "verified_by": None,
                "verified_at": None,
                "verification_note": "",
            }
            meta["versions"].append(ver_entry)
            meta["current_version"] = ver_no
            meta["verification_status"] = "pending_verification"
            meta["late_arrival_after_as_of"] = bool(meta["late_arrival_after_as_of"] or late)
            meta["updated_at"] = now
            validate_against_schema(meta, "evidence_document")

            conn.execute(
                """
                INSERT INTO evidence_documents (
                    tenant_id, company_id, document_id, case_id, obligation_id, document_type,
                    current_version, verification_status, late_arrival_after_as_of, metadata_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, company_id, document_id) DO UPDATE SET
                    current_version = excluded.current_version,
                    verification_status = excluded.verification_status,
                    late_arrival_after_as_of = excluded.late_arrival_after_as_of,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    tenant_id,
                    company_id,
                    doc_id,
                    cid_case,
                    ob_id,
                    dt,
                    ver_no,
                    "pending_verification",
                    1 if meta["late_arrival_after_as_of"] else 0,
                    canonical(meta),
                    meta["created_at"],
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO evidence_document_versions (
                    tenant_id, company_id, document_id, version, sha256, filename, mime, size,
                    document_date, received_at, uploaded_by, source_kind, verification_status,
                    version_json, content_blob
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    company_id,
                    doc_id,
                    ver_no,
                    sha,
                    fname,
                    mime,
                    len(content),
                    doc_date_iso,
                    now,
                    actor_id,
                    source_kind,
                    "pending_verification",
                    canonical(ver_entry),
                    sqlite3.Binary(bytes(content)),
                ),
            )
            self._insert_audit(
                conn,
                tenant_id=tenant_id,
                company_id=company_id,
                entity_type="evidence_document",
                entity_id=doc_id,
                event_type="document_version_uploaded",
                actor_id=actor_id,
                actor_role=role,
                detail={
                    "case_id": cid_case,
                    "document_type": dt,
                    "version": ver_no,
                    "sha256": sha,
                    "late_arrival_after_as_of": late,
                },
                created_at=now,
            )
            self._refresh_existing_checklist_conn(conn, tenant_id, company_id, cid_case, actor_id, now)
            res = {"document": meta, "idempotent_replay": False}
            self._save_receipt(
                conn,
                tenant_id=tenant_id,
                company_id=company_id,
                operation="upload_document",
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                response=res,
                created_at=now,
            )
            return res

    def _refresh_existing_checklist_conn(
        self,
        conn: sqlite3.Connection,
        tenant_id: str,
        company_id: str,
        case_id: str,
        actor_id: str,
        now: str,
    ) -> None:
        row = conn.execute(
            """
            SELECT policy_id, policy_version, overrides_json, checklist_json, revision
            FROM document_checklists
            WHERE tenant_id = ? AND company_id = ? AND case_id = ?
            """,
            (tenant_id, company_id, case_id),
        ).fetchone()
        if row is None:
            return
        prev = json.loads(row["checklist_json"])
        overrides = json.loads(row["overrides_json"])
        link = conn.execute(
            "SELECT case_context_json FROM case_financial_links WHERE tenant_id = ? AND company_id = ? AND case_id = ?",
            (tenant_id, company_id, case_id),
        ).fetchone()
        link_ctx = json.loads(link["case_context_json"]) if link else {}
        docs = self._load_documents_for_case_conn(conn, tenant_id, company_id, case_id)
        # Re-evaluate using stored context and newly updated docs; preserve any human overrides unless newly verified doc supersedes missing.
        for doc in docs:
            dt = doc["document_type"]
            if doc["verification_status"] == "present" and dt in overrides and overrides[dt].get("item_status") == "missing":
                overrides.pop(dt, None)
        rev = int(row["revision"]) + 1
        ctx = {
            "tenant_id": tenant_id,
            "company_id": company_id,
            "case_id": case_id,
            "obligation_id": prev["obligation_id"],
            "problem_family": prev["problem_family"],
            "rule_ids": prev["rule_ids"],
            "as_of": prev["as_of"],
            "applicability_flags": link_ctx.get("applicability_flags") or [],
            "payment_count": link_ctx.get("payment_count") or 0,
            "has_refund_or_adjustment": bool(link_ctx.get("has_refund_or_adjustment")),
            "reconciliation_status": link_ctx.get("reconciliation_status") or "",
        }
        avail = link_ctx.get("available_sources")
        updated = evaluate_document_checklist(
            ctx,
            docs,
            available_sources=avail,
            as_of=prev["as_of"],
            checked_by=actor_id,
            checked_at=now,
            human_overrides=overrides,
            revision=rev,
        )
        conn.execute(
            """
            UPDATE document_checklists
            SET overrides_json = ?, checklist_json = ?, revision = ?, updated_at = ?, updated_by = ?
            WHERE tenant_id = ? AND company_id = ? AND case_id = ?
            """,
            (canonical(overrides), canonical(updated), rev, now, actor_id, tenant_id, company_id, case_id),
        )

    def verify_document(
        self,
        scope,
        *,
        document_id: str,
        decision: str,
        verification_note: str,
        version: int | None = None,
        recheck=None,
    ) -> dict[str, Any]:
        """Verify or reject an uploaded document version (requires evidence.verify or director)."""
        tenant_id, company_id, actor_id = _require_verifier_scope(scope, recheck)
        role = str(getattr(scope, "role", "") or "director")
        if decision not in ("present", "rejected"):
            fail(422, "INVALID_VERIFY_DECISION", "Quyết định xác minh phải là 'present' hoặc 'rejected'.", "Chọn present để xác nhận hoặc rejected để từ chối.")
        note = str(verification_note or "").strip()
        if not note:
            fail(422, "VERIFICATION_NOTE_REQUIRED", "Phải nhập ghi chú đối chiếu khi xác minh hoặc từ chối chứng từ.", "Ghi rõ kết quả kiểm tra.")

        with self._write_tx() as conn:
            row = conn.execute(
                """
                SELECT metadata_json, case_id
                FROM evidence_documents
                WHERE tenant_id = ? AND company_id = ? AND document_id = ?
                """,
                (tenant_id, company_id, document_id),
            ).fetchone()
            if row is None:
                fail(404, "DOCUMENT_NOT_FOUND", f"Không tìm thấy chứng từ {document_id}.", "Kiểm tra lại mã chứng từ hoặc doanh nghiệp.")
            meta = json.loads(row["metadata_json"])
            target_ver = int(version or meta["current_version"])
            matched = None
            for v in meta["versions"]:
                if int(v["version"]) == target_ver:
                    matched = v
                    break
            if matched is None:
                fail(404, "DOCUMENT_VERSION_NOT_FOUND", f"Không tìm thấy phiên bản v{target_ver} của {document_id}.", "Kiểm tra phiên bản chứng từ.")

            now = _utc_now()
            matched["verification_status"] = decision
            matched["verified_by"] = actor_id
            matched["verified_at"] = now
            matched["verification_note"] = note
            if target_ver == int(meta["current_version"]):
                meta["verification_status"] = decision
            meta["updated_at"] = now
            validate_against_schema(meta, "evidence_document")

            conn.execute(
                """
                UPDATE evidence_documents
                SET verification_status = ?, metadata_json = ?, updated_at = ?
                WHERE tenant_id = ? AND company_id = ? AND document_id = ?
                """,
                (meta["verification_status"], canonical(meta), now, tenant_id, company_id, document_id),
            )
            conn.execute(
                """
                UPDATE evidence_document_versions
                SET verification_status = ?, version_json = ?
                WHERE tenant_id = ? AND company_id = ? AND document_id = ? AND version = ?
                """,
                (decision, canonical(matched), tenant_id, company_id, document_id, target_ver),
            )
            self._insert_audit(
                conn,
                tenant_id=tenant_id,
                company_id=company_id,
                entity_type="evidence_document",
                entity_id=document_id,
                event_type=f"document_verified_{decision}",
                actor_id=actor_id,
                actor_role=role,
                detail={"case_id": row["case_id"], "version": target_ver, "note": note},
                created_at=now,
            )
            self._refresh_existing_checklist_conn(conn, tenant_id, company_id, row["case_id"], actor_id, now)
            return meta

    def get_document(
        self,
        scope,
        document_id: str,
        *,
        version: int | None = None,
        include_bytes: bool = False,
        recheck=None,
    ) -> dict[str, Any]:
        tenant_id, company_id, _ = _require_read_scope(scope, recheck)
        with self._read_conn() as conn:
            row = conn.execute(
                """
                SELECT metadata_json
                FROM evidence_documents
                WHERE tenant_id = ? AND company_id = ? AND document_id = ?
                """,
                (tenant_id, company_id, document_id),
            ).fetchone()
            if row is None:
                fail(404, "DOCUMENT_NOT_FOUND", f"Không tìm thấy chứng từ {document_id}.", "Kiểm tra company_id hoặc document_id.")
            meta = json.loads(row["metadata_json"])
            out: dict[str, Any] = {"document": meta}
            if include_bytes:
                target_ver = int(version or meta["current_version"])
                vrow = conn.execute(
                    """
                    SELECT content_blob, mime, filename, sha256
                    FROM evidence_document_versions
                    WHERE tenant_id = ? AND company_id = ? AND document_id = ? AND version = ?
                    """,
                    (tenant_id, company_id, document_id, target_ver),
                ).fetchone()
                if vrow is None:
                    fail(404, "DOCUMENT_VERSION_NOT_FOUND", f"Không tìm thấy phiên bản v{target_ver}.", "Kiểm tra số phiên bản.")
                out["version"] = target_ver
                out["content"] = bytes(vrow["content_blob"])
                out["mime"] = vrow["mime"]
                out["filename"] = vrow["filename"]
                out["sha256"] = vrow["sha256"]
            return out

    def create_task(
        self,
        scope,
        *,
        case_id: str,
        obligation_id: str | None = None,
        task_type: str,
        issue_type: str,
        title: str,
        what_to_do: str,
        reason: str,
        assignee_kind: str,
        assignee_key: str,
        assignee_label: str = "",
        due_at: str | None = None,
        require_evidence: bool = True,
        required_document_types: list[str] | tuple[str, ...] = (),
        allow_multiple_open: bool = False,
        idempotency_key: str | None = None,
        source_binding: dict[str, Any] | None = None,
        recheck=None,
    ) -> dict[str, Any]:
        """Create an ActionTask inside company scope with duplicate prevention & idempotency."""
        tenant_id, company_id, actor_id = _require_operator_scope(scope, recheck)
        role = str(getattr(scope, "role", "") or "accountant")

        cid_case = str(case_id or "").strip()
        ob_id = str(obligation_id or cid_case).strip()
        if not cid_case:
            fail(422, "CASE_ID_REQUIRED", "Thiếu case_id khi tạo tác vụ.", "Cung cấp case_id.")
        if task_type not in ("request_documents", "reconcile_payment", "verify_control", "remediate_issue"):
            fail(422, "INVALID_TASK_TYPE", f"Loại tác vụ không hợp lệ: {task_type}.", "Chọn request_documents, reconcile_payment, verify_control hoặc remediate_issue.")
        if issue_type not in ISSUE_TYPES:
            fail(422, "INVALID_ISSUE_TYPE", f"issue_type không hợp lệ: {issue_type}.", f"Chọn trong {ISSUE_TYPES}.")
        ttl = str(title or "").strip()
        todo = str(what_to_do or "").strip()
        rsn = str(reason or "").strip()
        if not ttl or not todo or not rsn:
            fail(422, "TASK_DESCRIPTION_REQUIRED", "Cần ghi rõ tiêu đề, việc phải làm và lý do tạo tác vụ.", "Bổ sung title, what_to_do và reason.")

        assignee = build_assignee_ref(
            assignee_kind=assignee_kind,
            assignee_key=assignee_key,
            display_label=assignee_label,
        )
        due_iso = None
        if due_at is not None and str(due_at).strip() != "":
            due_iso = parse_iso_datetime(str(due_at), field_name="due_at").isoformat()
        req_docs = [str(d).strip() for d in required_document_types if str(d).strip()]
        payload_hash = digest(
            canonical(
                [
                    cid_case,
                    ob_id,
                    task_type,
                    issue_type,
                    ttl,
                    todo,
                    rsn,
                    assignee["assignee_kind"],
                    assignee["assignee_key"],
                    due_iso,
                    bool(require_evidence),
                    req_docs,
                    bool(allow_multiple_open),
                    *([source_binding] if source_binding is not None else []),
                ]
            )
        )

        with self._write_tx() as conn:
            _require_operator_scope(scope, recheck)
            cached = self._check_idempotency(
                conn,
                tenant_id=tenant_id,
                company_id=company_id,
                operation="create_task",
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
            )
            if cached is not None:
                _require_operator_scope(scope, recheck)
                return cached

            if not allow_multiple_open:
                existing = conn.execute(
                    """
                    SELECT task_json
                    FROM action_tasks
                    WHERE tenant_id = ? AND company_id = ? AND case_id = ?
                      AND obligation_id = ? AND task_type = ?
                      AND status IN ('open', 'in_progress', 'waiting_external')
                      AND deduplicate_slot = 1
                    """,
                    (tenant_id, company_id, cid_case, ob_id, task_type),
                ).fetchone()
                if existing is not None:
                    existing_task = json.loads(existing["task_json"])
                    if source_binding is not None and existing_task.get('source_binding') != source_binding:
                        fail(409, 'TASK_SOURCE_CONFLICT', 'Công việc đã có không khớp nguồn của vụ.', 'Mở đúng lần phân tích; không gán lại nguồn công việc cũ.')
                    res = {
                        "task": existing_task,
                        "created": False,
                        "deduplicated_existing": True,
                        "idempotent_replay": False,
                    }
                    self._save_receipt(
                        conn,
                        tenant_id=tenant_id,
                        company_id=company_id,
                        operation="create_task",
                        idempotency_key=idempotency_key,
                        payload_hash=payload_hash,
                        response=res,
                        created_at=_utc_now(),
                    )
                    _require_operator_scope(scope, recheck)
                    return res

            now = _utc_now()
            task_id = _new_id("tsk", tenant_id, company_id, cid_case, ob_id, task_type, now)
            initial_status = "waiting_external" if task_type == "request_documents" else "open"
            task = {
                "schema_version": TASK_SCHEMA_VERSION,
                "task_id": task_id,
                "tenant_id": tenant_id,
                "company_id": company_id,
                "case_id": cid_case,
                "obligation_id": ob_id,
                "revision": 1,
                "task_type": task_type,
                "issue_type": issue_type,
                "title": ttl,
                "what_to_do": todo,
                "reason": rsn,
                "assignee": assignee,
                "due_at": due_iso,
                "status": initial_status,
                "require_evidence": bool(require_evidence),
                "required_document_types": req_docs,
                "submission": None,
                "verification": None,
                "reopen_reason": None,
                "cancel_reason": None,
                "mutates_case_status": False,
                "generates_ml_label": False,
                "created_by": actor_id,
                "created_at": now,
                "updated_by": actor_id,
                "updated_at": now,
                "history": [
                    {
                        "revision": 1,
                        "event_type": "task_created",
                        "from_status": None,
                        "to_status": initial_status,
                        "actor_id": actor_id,
                        "actor_role": role,
                        "at": now,
                        "reason": rsn,
                        "assignee": assignee,
                        "due_at": due_iso,
                    }
                ],
            }
            if source_binding is not None:
                task['source_binding'] = deepcopy(source_binding)
            validate_against_schema(task, "action_task")

            dedup_slot = 0 if allow_multiple_open else 1
            conn.execute(
                """
                INSERT INTO action_tasks (
                    tenant_id, company_id, task_id, case_id, obligation_id, task_type,
                    revision, status, issue_type, assignee_kind, assignee_key, due_at,
                    deduplicate_slot, task_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    company_id,
                    task_id,
                    cid_case,
                    ob_id,
                    task_type,
                    1,
                    initial_status,
                    issue_type,
                    assignee["assignee_kind"],
                    assignee["assignee_key"],
                    due_iso,
                    dedup_slot,
                    canonical(task),
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO action_task_revisions (
                    tenant_id, company_id, task_id, revision, event_type, status, actor_id, at, snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (tenant_id, company_id, task_id, 1, "task_created", initial_status, actor_id, now, canonical(task)),
            )
            self._insert_audit(
                conn,
                tenant_id=tenant_id,
                company_id=company_id,
                entity_type="action_task",
                entity_id=task_id,
                event_type="task_created",
                actor_id=actor_id,
                actor_role=role,
                detail={"case_id": cid_case, "task_type": task_type, "assignee": assignee, "due_at": due_iso,
                        **({'source_binding':source_binding} if source_binding is not None else {})},
                created_at=now,
            )
            res = {
                "task": task,
                "created": True,
                "deduplicated_existing": False,
                "idempotent_replay": False,
            }
            self._save_receipt(
                conn,
                tenant_id=tenant_id,
                company_id=company_id,
                operation="create_task",
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                response=res,
                created_at=now,
            )
            _require_operator_scope(scope, recheck)
            return res

    def _load_task_for_update_conn(
        self,
        conn: sqlite3.Connection,
        tenant_id: str,
        company_id: str,
        task_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT task_json, revision
            FROM action_tasks
            WHERE tenant_id = ? AND company_id = ? AND task_id = ?
            """,
            (tenant_id, company_id, task_id),
        ).fetchone()
        if row is None:
            fail(404, "TASK_NOT_FOUND", f"Không tìm thấy tác vụ {task_id}.", "Kiểm tra task_id hoặc phạm vi doanh nghiệp.")
        if int(row["revision"]) != int(expected_revision):
            fail(
                409,
                "REVISION_CONFLICT",
                f"Tác vụ {task_id} đã được cập nhật lên revision {row['revision']} (client gửi expected_revision={expected_revision}).",
                "Tải lại chi tiết tác vụ trước khi thao tác tiếp.",
            )
        return json.loads(row["task_json"])

    def _save_task_transition_conn(
        self,
        conn: sqlite3.Connection,
        task: dict[str, Any],
        *,
        event_type: str,
        actor_id: str,
        actor_role: str,
        detail: dict[str, Any],
    ) -> dict[str, Any]:
        validate_against_schema(task, "action_task")
        conn.execute(
            """
            UPDATE action_tasks
            SET revision = ?, status = ?, assignee_kind = ?, assignee_key = ?,
                due_at = ?, task_json = ?, updated_at = ?
            WHERE tenant_id = ? AND company_id = ? AND task_id = ?
            """,
            (
                task["revision"],
                task["status"],
                task["assignee"]["assignee_kind"],
                task["assignee"]["assignee_key"],
                task["due_at"],
                canonical(task),
                task["updated_at"],
                task["tenant_id"],
                task["company_id"],
                task["task_id"],
            ),
        )
        conn.execute(
            """
            INSERT INTO action_task_revisions (
                tenant_id, company_id, task_id, revision, event_type, status, actor_id, at, snapshot_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task["tenant_id"],
                task["company_id"],
                task["task_id"],
                task["revision"],
                event_type,
                task["status"],
                actor_id,
                task["updated_at"],
                canonical(task),
            ),
        )
        self._insert_audit(
            conn,
            tenant_id=task["tenant_id"],
            company_id=task["company_id"],
            entity_type="action_task",
            entity_id=task["task_id"],
            event_type=event_type,
            actor_id=actor_id,
            actor_role=actor_role,
            detail=detail,
            created_at=task["updated_at"],
        )
        return task

    def assign_task(
        self,
        scope,
        *,
        task_id: str,
        expected_revision: int,
        assignee_kind: str,
        assignee_key: str,
        assignee_label: str = "",
        due_at: str | None = None,
        clear_due_at: bool = False,
        reason: str,
        recheck=None,
    ) -> dict[str, Any]:
        tenant_id, company_id, actor_id = _require_operator_scope(scope, recheck)
        role = str(getattr(scope, "role", "") or "accountant")
        rsn = str(reason or "").strip()
        if not rsn:
            fail(422, "ASSIGN_REASON_REQUIRED", "Cần ghi rõ lý do khi đổi người phụ trách hoặc gia hạn.", "Nhập reason.")
        assignee = build_assignee_ref(
            assignee_kind=assignee_kind,
            assignee_key=assignee_key,
            display_label=assignee_label,
        )

        with self._write_tx() as conn:
            task = self._load_task_for_update_conn(conn, tenant_id, company_id, task_id, expected_revision)
            if task["status"] in ("completed", "cancelled"):
                fail(409, "INVALID_TASK_STATE", "Không thể giao lại tác vụ đã hoàn tất hoặc đã hủy; cần Mở lại (reopen) trước.", "Gọi quyết định reopen kèm lý do.")

            new_due = task["due_at"]
            if clear_due_at:
                new_due = None
            elif due_at is not None and str(due_at).strip() != "":
                new_due = parse_iso_datetime(str(due_at), field_name="due_at").isoformat()

            now = _utc_now()
            rev = int(task["revision"]) + 1
            prev_status = task["status"]
            next_status = "in_progress" if prev_status == "open" else prev_status
            task["revision"] = rev
            task["assignee"] = assignee
            task["due_at"] = new_due
            task["status"] = next_status
            task["updated_by"] = actor_id
            task["updated_at"] = now
            task["history"].append(
                {
                    "revision": rev,
                    "event_type": "task_reassigned_or_rescheduled",
                    "from_status": prev_status,
                    "to_status": next_status,
                    "actor_id": actor_id,
                    "actor_role": role,
                    "at": now,
                    "reason": rsn,
                    "assignee": assignee,
                    "due_at": new_due,
                }
            )
            return self._save_task_transition_conn(
                conn,
                task,
                event_type="task_reassigned_or_rescheduled",
                actor_id=actor_id,
                actor_role=role,
                detail={"revision": rev, "assignee": assignee, "due_at": new_due, "reason": rsn},
            )

    def submit_task(
        self,
        scope,
        *,
        task_id: str,
        expected_revision: int,
        result_summary: str,
        document_ids: list[str] | tuple[str, ...] = (),
        evidence_ids: list[str] | tuple[str, ...] = (),
        waiting_external: bool = False,
        recheck=None,
    ) -> dict[str, Any]:
        tenant_id, company_id, actor_id = _require_operator_scope(scope, recheck)
        role = str(getattr(scope, "role", "") or "accountant")
        summary = str(result_summary or "").strip()
        if not summary:
            fail(422, "SUBMISSION_SUMMARY_REQUIRED", "Phải nhập giải trình/kết quả thực hiện trước khi gửi.", "Nhập result_summary.")
        doc_id_list = [str(d).strip() for d in document_ids if str(d).strip()]
        ev_id_list = [str(e).strip() for e in evidence_ids if str(e).strip()]

        with self._write_tx() as conn:
            task = self._load_task_for_update_conn(conn, tenant_id, company_id, task_id, expected_revision)
            if task["status"] in ("completed", "cancelled"):
                fail(409, "INVALID_TASK_STATE", "Tác vụ đã hoàn tất hoặc đã hủy không thể gửi kết quả mới khi chưa Mở lại.", "Thực hiện reopen nếu cần xử lý tiếp.")

            for did in doc_id_list:
                drow = conn.execute(
                    """
                    SELECT case_id FROM evidence_documents
                    WHERE tenant_id = ? AND company_id = ? AND document_id = ?
                    """,
                    (tenant_id, company_id, did),
                ).fetchone()
                if drow is None or drow["case_id"] != task["case_id"]:
                    fail(
                        422,
                        "DOCUMENT_NOT_IN_CASE",
                        f"Chứng từ {did} không tồn tại hoặc không thuộc vụ việc {task['case_id']} của doanh nghiệp {company_id}.",
                        "Chỉ đính kèm chứng từ thuộc cùng doanh nghiệp và vụ việc.",
                    )

            now = _utc_now()
            rev = int(task["revision"]) + 1
            prev_status = task["status"]
            next_status = "waiting_external" if waiting_external else "in_progress"
            task["revision"] = rev
            task["status"] = next_status
            task["updated_by"] = actor_id
            task["updated_at"] = now
            task["submission"] = {
                "result_summary": summary,
                "submitted_by": actor_id,
                "submitted_role": role,
                "submitted_at": now,
                "submitted_document_ids": doc_id_list,
                "submitted_evidence_ids": ev_id_list,
            }
            task["history"].append(
                {
                    "revision": rev,
                    "event_type": "task_result_submitted",
                    "from_status": prev_status,
                    "to_status": next_status,
                    "actor_id": actor_id,
                    "actor_role": role,
                    "at": now,
                    "reason": summary,
                    "extra": {"submitted_document_ids": doc_id_list},
                }
            )
            return self._save_task_transition_conn(
                conn,
                task,
                event_type="task_result_submitted",
                actor_id=actor_id,
                actor_role=role,
                detail={"revision": rev, "submitted_document_ids": doc_id_list},
            )

    def decide_task(
        self,
        scope,
        *,
        task_id: str,
        expected_revision: int,
        decision: str,
        note: str,
        recheck=None,
    ) -> dict[str, Any]:
        """Confirm completion, request rework, reopen, or cancel an ActionTask (requires verifier privilege)."""
        tenant_id, company_id, actor_id = _require_verifier_scope(scope, recheck)
        role = str(getattr(scope, "role", "") or "director")
        if decision not in ("confirm_complete", "request_rework", "reopen", "cancel"):
            fail(422, "INVALID_TASK_DECISION", f"Quyết định tác vụ không hợp lệ: {decision}.", "Chọn confirm_complete, request_rework, reopen hoặc cancel.")
        reason_note = str(note or "").strip()
        if not reason_note:
            fail(422, "DECISION_NOTE_REQUIRED", "Bắt buộc nhập ghi chú/lý do cho quyết định xác nhận, làm lại, mở lại hoặc hủy.", "Nhập note.")

        with self._write_tx() as conn:
            task = self._load_task_for_update_conn(conn, tenant_id, company_id, task_id, expected_revision)
            now = _utc_now()
            rev = int(task["revision"]) + 1
            prev_status = task["status"]
            verified_doc_ids: list[str] = []

            if decision == "confirm_complete":
                if prev_status not in ("open", "in_progress", "waiting_external"):
                    fail(409, "INVALID_TASK_STATE", f"Không thể xác nhận hoàn tất từ trạng thái {prev_status}.", "Tác vụ phải đang mở hoặc đang xử lý.")
                sub = task.get("submission")
                if sub is None:
                    fail(
                        422,
                        "SUBMISSION_REQUIRED_BEFORE_CONFIRM",
                        "Chưa có kết quả thực hiện từ người phụ trách; không thể xác nhận hoàn tất.",
                        "Gửi kết quả thực hiện trước khi xác nhận.",
                    )
                last_verif = task.get("verification")
                if last_verif and last_verif.get("decision") in ("request_rework", "reopen") and sub["submitted_at"] <= last_verif["confirmed_at"]:
                    fail(
                        422,
                        "NEW_SUBMISSION_REQUIRED_AFTER_REWORK",
                        "Tác vụ đã bị yêu cầu làm lại hoặc mở lại; người phụ trách cần gửi kết quả mới trước khi xác nhận hoàn tất.",
                        "Gửi lại kết quả sau khi bổ sung.",
                    )

                docs = self._load_documents_for_case_conn(conn, tenant_id, company_id, task["case_id"])
                verified_by_type: dict[str, list[str]] = {}
                all_verified_ids: set[str] = set()
                for d in docs:
                    if d["verification_status"] == "present":
                        verified_by_type.setdefault(d["document_type"], []).append(d["document_id"])
                        all_verified_ids.add(d["document_id"])

                if task["require_evidence"]:
                    req_types = list(task.get("required_document_types") or [])
                    if req_types:
                        missing_verified = [rt for rt in req_types if not verified_by_type.get(rt)]
                        if missing_verified:
                            fail(
                                422,
                                "VERIFIED_EVIDENCE_REQUIRED",
                                f"Chưa thể xác nhận hoàn tất vì thiếu chứng từ đã xác minh cho: {', '.join(missing_verified)} (tệp mới tải lên chưa xác minh không được tính).",
                                "Tải lên và xác minh chứng từ trước khi hoàn tất.",
                            )
                        for rt in req_types:
                            verified_doc_ids.extend(verified_by_type.get(rt, []))
                    else:
                        submitted_docs = [did for did in sub.get("submitted_document_ids") or [] if did in all_verified_ids]
                        if not submitted_docs and not all_verified_ids:
                            fail(
                                422,
                                "VERIFIED_EVIDENCE_REQUIRED",
                                "Tác vụ yêu cầu bằng chứng xác minh nhưng chưa có chứng từ nào được xác minh trong vụ việc.",
                                "Xác minh chứng từ đính kèm trước khi hoàn tất.",
                            )
                        verified_doc_ids = sorted(set(submitted_docs or list(all_verified_ids)))
                next_status = "completed"
                event_type = "task_confirmed_completed"
            elif decision == "request_rework":
                if prev_status not in ("open", "in_progress", "waiting_external"):
                    fail(409, "INVALID_TASK_STATE", f"Không thể yêu cầu làm lại từ trạng thái {prev_status}.", "Dùng reopen nếu tác vụ đã đóng/hủy.")
                next_status = "in_progress"
                event_type = "task_rework_requested"
            elif decision == "reopen":
                if prev_status not in ("completed", "cancelled"):
                    fail(409, "INVALID_TASK_STATE", "Chỉ mở lại được tác vụ đang ở trạng thái completed hoặc cancelled.", "Kiểm tra trạng thái hiện tại.")
                next_status = "open"
                task["reopen_reason"] = reason_note
                event_type = "task_reopened"
            else:
                if prev_status in ("completed", "cancelled"):
                    fail(409, "INVALID_TASK_STATE", "Không thể hủy tác vụ đã hoàn tất hoặc đã hủy.", "Dùng reopen nếu cần mở lại.")
                next_status = "cancelled"
                task["cancel_reason"] = reason_note
                event_type = "task_cancelled"

            task["revision"] = rev
            task["status"] = next_status
            task["updated_by"] = actor_id
            task["updated_at"] = now
            task["verification"] = {
                "decision": decision,
                "confirmed_by": actor_id,
                "confirmed_role": role,
                "confirmed_at": now,
                "confirmation_note": reason_note,
                "verified_document_ids": sorted(set(verified_doc_ids)),
            }
            task["history"].append(
                {
                    "revision": rev,
                    "event_type": event_type,
                    "from_status": prev_status,
                    "to_status": next_status,
                    "actor_id": actor_id,
                    "actor_role": role,
                    "at": now,
                    "reason": reason_note,
                    "extra": {"verified_document_ids": sorted(set(verified_doc_ids))},
                }
            )
            return self._save_task_transition_conn(
                conn,
                task,
                event_type=event_type,
                actor_id=actor_id,
                actor_role=role,
                detail={
                    "revision": rev,
                    "decision": decision,
                    "note": reason_note,
                    "verified_document_ids": sorted(set(verified_doc_ids)),
                },
            )

    def get_case_remediation(self, scope, case_id: str, *, recheck=None) -> dict[str, Any]:
        tenant_id, company_id, _ = _require_read_scope(scope, recheck)
        with self._read_conn() as conn:
            chk_row = conn.execute(
                """
                SELECT checklist_json FROM document_checklists
                WHERE tenant_id = ? AND company_id = ? AND case_id = ?
                """,
                (tenant_id, company_id, case_id),
            ).fetchone()
            checklist = json.loads(chk_row["checklist_json"]) if chk_row else None
            docs = self._load_documents_for_case_conn(conn, tenant_id, company_id, case_id)
            tasks = self._load_tasks_for_case_conn(conn, tenant_id, company_id, case_id)
            link_row = conn.execute(
                """
                SELECT issue_type, reconciliation_json, case_context_json
                FROM case_financial_links
                WHERE tenant_id = ? AND company_id = ? AND case_id = ?
                """,
                (tenant_id, company_id, case_id),
            ).fetchone()
            recon = None
            issue_type = None
            if link_row:
                issue_type = link_row["issue_type"]
                raw_recon = json.loads(link_row["reconciliation_json"])
                if raw_recon:
                    recon = raw_recon
            audits = conn.execute(
                """
                SELECT event_id, entity_type, entity_id, event_type, actor_id, actor_role, detail_json, created_at
                FROM remediation_audit_events
                WHERE tenant_id = ? AND company_id = ?
                  AND (entity_id = ? OR detail_json LIKE ?)
                ORDER BY seq
                """,
                (tenant_id, company_id, case_id, f'%"{case_id}"%'),
            ).fetchall()

        missing_docs = [it for it in (checklist["items"] if checklist else []) if it["item_status"] in ("missing", "unknown", "pending_verification")]
        active_tasks = [t for t in tasks if t["status"] in ("open", "in_progress", "waiting_external")]
        return {
            "tenant_id": tenant_id,
            "company_id": company_id,
            "case_id": case_id,
            "issue_type": issue_type,
            "checklist": checklist,
            "documents": docs,
            "tasks": tasks,
            "reconciliation": recon,
            "what_is_missing": missing_docs,
            "who_and_when": [
                {
                    "task_id": t["task_id"],
                    "title": t["title"],
                    "status": t["status"],
                    "assignee": t["assignee"],
                    "due_at": t["due_at"],
                }
                for t in active_tasks
            ],
            "next_step_vi": compute_next_step_vi(checklist, tasks),
            "audit_events": [
                {
                    "event_id": a["event_id"],
                    "entity_type": a["entity_type"],
                    "entity_id": a["entity_id"],
                    "event_type": a["event_type"],
                    "actor_id": a["actor_id"],
                    "actor_role": a["actor_role"],
                    "detail": json.loads(a["detail_json"]),
                    "created_at": a["created_at"],
                }
                for a in audits
            ],
        }

    def list_tasks(
        self,
        scope,
        *,
        filter_name: str = "all",
        now: str | None = None,
        due_soon_hours: int = 48,
        department_role: str | None = None,
        recheck=None,
    ) -> dict[str, Any]:
        tenant_id, company_id, actor_id = _require_read_scope(scope, recheck)
        if filter_name not in ("all", "mine_or_dept", "due_soon", "overdue", "awaiting_confirmation", "completed"):
            fail(422, "INVALID_TASK_FILTER", f"Bộ lọc tác vụ không hợp lệ: {filter_name}.", "Chọn all, mine_or_dept, due_soon, overdue, awaiting_confirmation hoặc completed.")
        now_dt = parse_iso_datetime(now, field_name="now") if now else datetime.now(timezone.utc)
        soon_delta = timedelta(hours=int(due_soon_hours))

        with self._read_conn() as conn:
            rows = conn.execute(
                """
                SELECT task_json FROM action_tasks
                WHERE tenant_id = ? AND company_id = ?
                ORDER BY updated_at DESC, task_id
                """,
                (tenant_id, company_id),
            ).fetchall()
        all_tasks = [json.loads(r["task_json"]) for r in rows]

        def _is_awaiting(t: dict[str, Any]) -> bool:
            if t["status"] not in ("open", "in_progress", "waiting_external"):
                return False
            sub = t.get("submission")
            if not sub:
                return False
            ver = t.get("verification")
            return ver is None or ver["confirmed_at"] < sub["submitted_at"]

        def _is_overdue(t: dict[str, Any]) -> bool:
            if t["status"] not in ("open", "in_progress", "waiting_external") or not t.get("due_at"):
                return False
            return parse_iso_datetime(t["due_at"], field_name="due_at") < now_dt

        def _is_due_soon(t: dict[str, Any]) -> bool:
            if t["status"] not in ("open", "in_progress", "waiting_external") or not t.get("due_at"):
                return False
            delta = parse_iso_datetime(t["due_at"], field_name="due_at") - now_dt
            return timedelta(0) <= delta <= soon_delta

        filtered: list[dict[str, Any]] = []
        for t in all_tasks:
            if filter_name == "all":
                filtered.append(t)
            elif filter_name == "mine_or_dept":
                ass = t["assignee"]
                match_actor = ass["assignee_kind"] == "server_actor" and ass["assignee_key"] == actor_id
                match_dept = ass["assignee_kind"] == "department_role" and (
                    (department_role and ass["assignee_key"] == department_role)
                    or (not department_role)
                )
                if match_actor or match_dept:
                    filtered.append(t)
            elif filter_name == "due_soon" and _is_due_soon(t):
                filtered.append(t)
            elif filter_name == "overdue" and _is_overdue(t):
                filtered.append(t)
            elif filter_name == "awaiting_confirmation" and _is_awaiting(t):
                filtered.append(t)
            elif filter_name == "completed" and t["status"] == "completed":
                filtered.append(t)

        return {
            "tenant_id": tenant_id,
            "company_id": company_id,
            "filter": filter_name,
            "as_of_now": now_dt.isoformat(),
            "tasks": filtered,
            "counts": {
                "all": len(all_tasks),
                "overdue": sum(1 for t in all_tasks if _is_overdue(t)),
                "due_soon": sum(1 for t in all_tasks if _is_due_soon(t)),
                "awaiting_confirmation": sum(1 for t in all_tasks if _is_awaiting(t)),
                "completed": sum(1 for t in all_tasks if t["status"] == "completed"),
            },
        }

    def build_business_report(
        self,
        scope,
        *,
        case_statuses_by_id: dict[str, str] | None = None,
        as_of: str | None = None,
        now: str | None = None,
        due_soon_hours: int = 48,
        recheck=None,
    ) -> dict[str, Any]:
        """Aggregate distinct case/task/document counts, timings, and deduplicated amounts per company."""
        tenant_id, company_id, _ = _require_read_scope(scope, recheck)
        now_dt = parse_iso_datetime(now, field_name="now") if now else datetime.now(timezone.utc)
        soon_delta = timedelta(hours=int(due_soon_hours))

        with self._read_conn() as conn:
            chk_rows = conn.execute(
                "SELECT case_id, obligation_id, checklist_json FROM document_checklists WHERE tenant_id = ? AND company_id = ?",
                (tenant_id, company_id),
            ).fetchall()
            task_rows = conn.execute(
                "SELECT case_id, obligation_id, issue_type, task_json FROM action_tasks WHERE tenant_id = ? AND company_id = ?",
                (tenant_id, company_id),
            ).fetchall()
            doc_rows = conn.execute(
                "SELECT case_id, verification_status FROM evidence_documents WHERE tenant_id = ? AND company_id = ?",
                (tenant_id, company_id),
            ).fetchall()
            link_rows = conn.execute(
                "SELECT case_id, obligation_id, issue_type, reconciliation_json FROM case_financial_links WHERE tenant_id = ? AND company_id = ?",
                (tenant_id, company_id),
            ).fetchall()

        distinct_case_ids: set[str] = set(case_statuses_by_id.keys()) if case_statuses_by_id else set()
        for r in chk_rows:
            distinct_case_ids.add(r["case_id"])
        for r in task_rows:
            distinct_case_ids.add(r["case_id"])
        for r in doc_rows:
            distinct_case_ids.add(r["case_id"])
        for r in link_rows:
            distinct_case_ids.add(r["case_id"])

        case_wf_counts = {"new": 0, "in_review": 0, "waiting_evidence": 0, "closed": 0}
        status_map = case_statuses_by_id or {}
        for cid_case in distinct_case_ids:
            wf = status_map.get(cid_case)
            if wf in case_wf_counts:
                case_wf_counts[wf] += 1
            else:
                case_wf_counts["in_review"] += 1

        tasks = [json.loads(r["task_json"]) for r in task_rows]
        task_counts = {
            "total_tasks": len(tasks),
            "open": sum(1 for t in tasks if t["status"] == "open"),
            "in_progress": sum(1 for t in tasks if t["status"] == "in_progress"),
            "waiting_external": sum(1 for t in tasks if t["status"] == "waiting_external"),
            "completed": sum(1 for t in tasks if t["status"] == "completed"),
            "cancelled": sum(1 for t in tasks if t["status"] == "cancelled"),
            "overdue": 0,
            "due_soon": 0,
            "awaiting_confirmation": 0,
        }
        proc_hours: list[float] = []
        wait_hours: list[float] = []

        for t in tasks:
            if t["status"] in ("open", "in_progress", "waiting_external"):
                if t.get("due_at"):
                    delta = parse_iso_datetime(t["due_at"], field_name="due_at") - now_dt
                    if delta.total_seconds() < 0:
                        task_counts["overdue"] += 1
                    elif delta <= soon_delta:
                        task_counts["due_soon"] += 1
                sub = t.get("submission")
                ver = t.get("verification")
                if sub and (ver is None or ver["confirmed_at"] < sub["submitted_at"]):
                    task_counts["awaiting_confirmation"] += 1
            elif t["status"] == "completed":
                c_dt = parse_iso_datetime(t["created_at"], field_name="created_at")
                end_str = (t.get("verification") or {}).get("confirmed_at") or t["updated_at"]
                end_dt = parse_iso_datetime(end_str, field_name="confirmed_at")
                proc_hours.append(max(0.0, (end_dt - c_dt).total_seconds() / 3600.0))

            # Compute time spent waiting_external across history segments.
            hist = t.get("history") or []
            wait_start = None
            for h in hist:
                to_s = h.get("to_status")
                at_dt = parse_iso_datetime(h["at"], field_name="history_at")
                if to_s == "waiting_external" and wait_start is None:
                    wait_start = at_dt
                elif to_s != "waiting_external" and wait_start is not None:
                    wait_hours.append(max(0.0, (at_dt - wait_start).total_seconds() / 3600.0))
                    wait_start = None
            if wait_start is not None:
                wait_hours.append(max(0.0, (now_dt - wait_start).total_seconds() / 3600.0))

        checklists = [json.loads(r["checklist_json"]) for r in chk_rows]
        incomplete = sum(1 for c in checklists if not c["summary"]["ready_for_closure"])
        missing_items = sum(c["summary"]["missing"] for c in checklists)
        unknown_items = sum(c["summary"]["unknown"] for c in checklists)
        total_docs = len(doc_rows)
        pending_docs = sum(1 for d in doc_rows if d["verification_status"] == "pending_verification")
        verified_docs = sum(1 for d in doc_rows if d["verification_status"] == "present")
        rejected_docs = sum(1 for d in doc_rows if d["verification_status"] == "rejected")

        # Deduplicate financial amounts by obligation_id (one entry per distinct obligation).
        by_obligation: dict[str, dict[str, Any]] = {}
        case_issue_map: dict[str, str] = {}
        for r in link_rows:
            case_issue_map[r["case_id"]] = r["issue_type"]
            recon = json.loads(r["reconciliation_json"])
            if not recon:
                continue
            ob_key = str(recon.get("obligation_id") or r["obligation_id"] or r["case_id"])
            by_obligation[ob_key] = recon

        rel_vals = [r["related_amount_vnd"] for r in by_obligation.values() if r.get("related_amount_vnd") is not None]
        disc_vals = [r["discrepancy_amount_vnd"] for r in by_obligation.values() if r.get("discrepancy_amount_vnd") is not None]
        loss_vals = [r["confirmed_loss_vnd"] for r in by_obligation.values() if r.get("confirmed_loss_vnd") is not None]
        rec_vals = [r["recovered_vnd"] for r in by_obligation.values() if r.get("recovered_vnd") is not None]

        by_issue: dict[str, dict[str, Any]] = {}
        ob_seen_per_issue: dict[str, set[str]] = {}
        for t in tasks:
            it = t["issue_type"]
            bucket = by_issue.setdefault(it, {"tasks": 0, "open_tasks": 0, "completed_tasks": 0, "related_amount_vnd": None})
            bucket["tasks"] += 1
            if t["status"] in ("open", "in_progress", "waiting_external"):
                bucket["open_tasks"] += 1
            elif t["status"] == "completed":
                bucket["completed_tasks"] += 1
        for r in link_rows:
            it = r["issue_type"]
            bucket = by_issue.setdefault(it, {"tasks": 0, "open_tasks": 0, "completed_tasks": 0, "related_amount_vnd": None})
            recon = json.loads(r["reconciliation_json"])
            if recon and recon.get("related_amount_vnd") is not None:
                ob_key = str(recon.get("obligation_id") or r["obligation_id"])
                seen_set = ob_seen_per_issue.setdefault(it, set())
                if ob_key not in seen_set:
                    seen_set.add(ob_key)
                    bucket["related_amount_vnd"] = (bucket["related_amount_vnd"] or 0) + int(recon["related_amount_vnd"])

        report = {
            "schema_version": BUSINESS_REPORT_SCHEMA_VERSION,
            "tenant_id": tenant_id,
            "company_id": company_id,
            "as_of": as_of,
            "generated_at": _utc_now(),
            "case_counts": {
                "total_distinct_cases": len(distinct_case_ids),
                **case_wf_counts,
            },
            "task_counts": task_counts,
            "document_counts": {
                "checklists_evaluated": len(checklists),
                "incomplete_checklists": incomplete,
                "incomplete_rate": round(incomplete / len(checklists), 4) if checklists else 0.0,
                "total_documents": total_docs,
                "pending_verification_docs": pending_docs,
                "verified_docs": verified_docs,
                "rejected_docs": rejected_docs,
                "missing_items": missing_items,
                "unknown_items": unknown_items,
            },
            "timings": {
                "avg_task_processing_hours": round(sum(proc_hours) / len(proc_hours), 3) if proc_hours else None,
                "avg_waiting_evidence_hours": round(sum(wait_hours) / len(wait_hours), 3) if wait_hours else None,
                "completed_tasks_timed": len(proc_hours),
            },
            "amounts_vnd": {
                "related_amount_vnd": sum(int(x) for x in rel_vals) if rel_vals else None,
                "discrepancy_amount_vnd": sum(int(x) for x in disc_vals) if disc_vals else None,
                "confirmed_loss_vnd": sum(int(x) for x in loss_vals) if loss_vals else None,
                "recovered_vnd": sum(int(x) for x in rec_vals) if rec_vals else None,
                "deduplicated_obligation_count": len(by_obligation),
            },
            "by_issue_type": by_issue,
        }
        validate_against_schema(report, "remediation_business_report")
        return report
