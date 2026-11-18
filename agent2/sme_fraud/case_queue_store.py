"""SQLite ACID storage, crash-safe transactional outbox, atomic case budget, idempotency, and backlog manager."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import sqlite3
import threading
import time

from .case_coalescing import (
    BUNDLE_VERSION,
    build_case_bundle_from_rule_analysis,
    coalesce_cases,
    evaluate_material_change,
)
from .case_queue_policy import (
    BACKLOG_REASONS,
    CASE_RESOLUTIONS,
    REPORT_VERSION,
    WORKFLOW_STATUSES,
    assess_case_eligibility,
    case_priority_key,
    default_fixture_policy,
    policy_hash,
    validate_against_schema,
    validate_policy,
)
from .import_files import ImportFailure, canonical, digest, fail

APPLICATION_ID = 1129468741
CURRENT_SCHEMA_VERSION = 2
MODES = ("active", "shadow")

_BUSY_ERRORS = ("database is locked", "database schema is locked", "locking protocol")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str, *parts) -> str:
    entropy = os.urandom(8).hex()
    return f"{prefix}_" + digest(canonical([prefix, entropy, *parts]))[:24]


def _require_scope(scope, recheck=None, permission: str = "data.import") -> tuple[str, str, str]:
    if scope is None or len(scope.company_ids) != 1 or permission not in scope.permissions:
        fail(403, "ACCESS_DENIED", "Không có quyền thao tác hàng đợi vụ việc cho doanh nghiệp này.", "Kiểm tra membership và quyền Portal.")
    if recheck is not None:
        current = recheck()
        if current != scope:
            fail(409, "AUTH_CONTEXT_CHANGED", "Quyền đã thay đổi trong lúc xử lý.", "Gửi lại yêu cầu theo quyền hiện hành.")
    company_id = next(iter(scope.company_ids))
    return str(scope.tenant_id), str(company_id), str(scope.actor_id)


def _validate_mode(mode: str) -> str:
    if mode not in MODES:
        fail(422, "INVALID_QUEUE_MODE", f"Chế độ hàng đợi không hợp lệ: {mode}.", "Chỉ chọn active hoặc shadow.")
    return mode


def _queue_target(mode: str) -> str:
    return "active_queue" if mode == "active" else "shadow_queue"


def redact_case_for_view(case_obj: dict, redaction: str = "review") -> dict:
    """Apply RULE-UI-01 redaction for business review vs technical director view."""
    out = deepcopy(case_obj)
    if redaction == "technical":
        return out
    # Business / accountant review view: strip internal ML scores, calibration internals, model pins, weights.
    out.pop("calibrated_fraud_probability", None)
    out.pop("method_versions", None)
    out.pop("model_pins", None)
    out.pop("case_score", None)
    if isinstance(out.get("score_breakdown"), dict):
        out["score_breakdown"] = {
            "redacted": True,
            "note": "Chi tiết trọng số/ngưỡng/điểm ML kỹ thuật được ẩn ở chế độ nghiệp vụ (RULE-UI-01).",
        }
    return out


def redact_policy_for_view(policy: dict, redaction: str = "review") -> dict:
    if redaction == "technical":
        return deepcopy(policy)
    return {
        "version": policy["version"],
        "policy_id": policy["policy_id"],
        "policy_version": policy["policy_version"],
        "fixture_declaration": deepcopy(policy["fixture_declaration"]),
        "budget": {
            "unit": policy["budget"]["unit"],
            "case_budget_limit": policy["budget"]["case_budget_limit"],
            "period_kind": policy["budget"]["period_kind"],
            "benchmark_transaction_cap_preserved": policy["budget"]["benchmark_transaction_cap_preserved"],
            "benchmark_separated": policy["budget"]["benchmark_separated"],
        },
        "backlog": deepcopy(policy["backlog"]),
        "scoring_redacted": True,
    }


_SCHEMA_V2_TABLES = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    note TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
    mode_namespace TEXT NOT NULL CHECK(mode_namespace IN ('active','shadow')),
    tenant_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    problem_family TEXT NOT NULL,
    obligation_id TEXT NOT NULL,
    current_revision INTEGER NOT NULL DEFAULT 1,
    case_workflow_status TEXT NOT NULL CHECK(case_workflow_status IN ('new','in_review','waiting_evidence','closed')),
    case_resolution TEXT CHECK(case_resolution IS NULL OR case_resolution IN ('confirmed_risk','legitimate','inconclusive')),
    reopen_count INTEGER NOT NULL DEFAULT 0,
    manual_waiting_hold INTEGER NOT NULL DEFAULT 0,
    last_delivered_fingerprint TEXT,
    last_material_fingerprint TEXT,
    latest_case_json TEXT NOT NULL,
    workflow_history_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (mode_namespace, tenant_id, company_id, case_id)
);

CREATE TABLE IF NOT EXISTS case_revisions (
    mode_namespace TEXT NOT NULL CHECK(mode_namespace IN ('active','shadow')),
    tenant_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    revision_no INTEGER NOT NULL,
    material_fingerprint TEXT NOT NULL,
    is_material_change INTEGER NOT NULL,
    diff_json TEXT NOT NULL,
    snapshot_id TEXT,
    run_id TEXT,
    analysis_id TEXT,
    case_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (mode_namespace, tenant_id, company_id, case_id, revision_no)
);

CREATE TABLE IF NOT EXISTS budget_periods (
    mode_namespace TEXT NOT NULL CHECK(mode_namespace IN ('active','shadow')),
    tenant_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    period_key TEXT NOT NULL,
    budget_limit INTEGER NOT NULL CHECK(budget_limit >= 0),
    reserved_count INTEGER NOT NULL DEFAULT 0 CHECK(reserved_count >= 0 AND reserved_count <= budget_limit),
    policy_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (mode_namespace, tenant_id, company_id, period_key)
);

CREATE TABLE IF NOT EXISTS budget_reservations (
    mode_namespace TEXT NOT NULL CHECK(mode_namespace IN ('active','shadow')),
    tenant_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    period_key TEXT NOT NULL,
    case_id TEXT NOT NULL,
    revision_no INTEGER NOT NULL,
    material_fingerprint TEXT NOT NULL,
    decision TEXT NOT NULL CHECK(decision IN ('selected','mandatory_route')),
    status TEXT NOT NULL CHECK(status IN ('reserved','committed')),
    request_idempotency_key TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (mode_namespace, tenant_id, company_id, period_key, case_id, revision_no)
);

CREATE TABLE IF NOT EXISTS alert_decisions (
    decision_id TEXT PRIMARY KEY,
    mode_namespace TEXT NOT NULL CHECK(mode_namespace IN ('active','shadow')),
    tenant_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    period_key TEXT NOT NULL,
    case_id TEXT NOT NULL,
    revision_no INTEGER NOT NULL,
    material_fingerprint TEXT NOT NULL,
    decision TEXT NOT NULL CHECK(decision IN ('selected','below_threshold','need_evidence','budget_deferred','already_notified','unscorable','mandatory_route')),
    backlog_reason_code TEXT,
    reason_detail TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    request_idempotency_key TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS delivery_ledger (
    mode_namespace TEXT NOT NULL CHECK(mode_namespace IN ('active','shadow')),
    tenant_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    case_id TEXT NOT NULL,
    material_fingerprint TEXT NOT NULL,
    revision_no INTEGER NOT NULL,
    period_key TEXT NOT NULL,
    outbox_id TEXT NOT NULL,
    delivery_status TEXT NOT NULL CHECK(delivery_status IN ('pending','sent','failed')),
    queue_target TEXT NOT NULL CHECK(queue_target IN ('active_queue','shadow_queue')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (mode_namespace, tenant_id, company_id, policy_version, case_id, material_fingerprint)
);

CREATE TABLE IF NOT EXISTS delivery_outbox (
    outbox_id TEXT PRIMARY KEY,
    mode_namespace TEXT NOT NULL CHECK(mode_namespace IN ('active','shadow')),
    tenant_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    period_key TEXT NOT NULL,
    case_id TEXT NOT NULL,
    revision_no INTEGER NOT NULL,
    material_fingerprint TEXT NOT NULL,
    admission_decision TEXT NOT NULL CHECK(admission_decision IN ('selected','mandatory_route')),
    queue_target TEXT NOT NULL CHECK(queue_target IN ('active_queue','shadow_queue')),
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending_dispatch','dispatched_unacked','acked','failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS queue_items (
    queue_item_id TEXT PRIMARY KEY,
    mode_namespace TEXT NOT NULL CHECK(mode_namespace IN ('active','shadow')),
    tenant_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    period_key TEXT NOT NULL,
    case_id TEXT NOT NULL,
    revision_no INTEGER NOT NULL,
    material_fingerprint TEXT NOT NULL,
    admission_decision TEXT NOT NULL CHECK(admission_decision IN ('selected','mandatory_route')),
    queue_target TEXT NOT NULL CHECK(queue_target IN ('active_queue','shadow_queue')),
    outbox_id TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (mode_namespace, tenant_id, company_id, policy_version, case_id, material_fingerprint)
);

CREATE TABLE IF NOT EXISTS backlog_items (
    mode_namespace TEXT NOT NULL CHECK(mode_namespace IN ('active','shadow')),
    tenant_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    revision_no INTEGER NOT NULL,
    period_key TEXT NOT NULL,
    backlog_reason_code TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason_detail TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('waiting','promoted','closed')),
    expires_at TEXT CHECK(expires_at IS NULL),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (mode_namespace, tenant_id, company_id, case_id)
);

CREATE TABLE IF NOT EXISTS request_receipts (
    mode_namespace TEXT NOT NULL CHECK(mode_namespace IN ('active','shadow')),
    tenant_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (mode_namespace, tenant_id, company_id, operation, idempotency_key)
);

CREATE TABLE IF NOT EXISTS case_audit_events (
    event_id TEXT PRIMARY KEY,
    mode_namespace TEXT NOT NULL CHECK(mode_namespace IN ('active','shadow')),
    tenant_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    case_id TEXT,
    event_type TEXT NOT NULL,
    actor_id TEXT,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_outbox_pending ON delivery_outbox(mode_namespace, tenant_id, company_id, status);
CREATE INDEX IF NOT EXISTS idx_backlog_open ON backlog_items(mode_namespace, tenant_id, company_id, status);
CREATE INDEX IF NOT EXISTS idx_decisions_period ON alert_decisions(mode_namespace, tenant_id, company_id, period_key, case_id);
CREATE INDEX IF NOT EXISTS idx_audit_case ON case_audit_events(mode_namespace, tenant_id, company_id, case_id);
"""

_APPEND_ONLY_TRIGGERS = (
    ("case_revisions", "append-only case revision history"),
    ("alert_decisions", "append-only alert decision audit"),
    ("case_audit_events", "append-only case audit log"),
)


class CaseQueueStore:
    """ACID SQLite store for case coalescing, budget reservation, idempotency, crash recovery, and backlog."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._thread_lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA synchronous = FULL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._thread_lock:
            conn = self._connect()
            try:
                conn.execute("PRAGMA journal_mode = WAL")
                self._migrate_locked(conn)
            finally:
                conn.close()

    def _migrate_locked(self, conn: sqlite3.Connection) -> None:
        conn.execute("BEGIN IMMEDIATE")
        try:
            app_id = conn.execute("PRAGMA application_id").fetchone()[0]
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            if not tables and app_id == 0:
                conn.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                conn.executescript(_SCHEMA_V2_TABLES)
                now = _utc_now()
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at, note) VALUES (?, ?, ?)",
                    (1, now, "v1 baseline schema"),
                )
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at, note) VALUES (?, ?, ?)",
                    (CURRENT_SCHEMA_VERSION, now, "v2 complete case queue, budget, outbox, backlog"),
                )
            else:
                if app_id not in (0, APPLICATION_ID):
                    raise ValueError(f"Foreign database application_id={app_id}, expected {APPLICATION_ID}")
                if app_id == 0:
                    conn.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                if "schema_migrations" in tables:
                    versions = {
                        int(row["version"])
                        for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
                    }
                else:
                    versions = {1} if "cases" in tables else set()

                if 1 not in versions and "cases" in tables:
                    conn.execute(
                        "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, note TEXT NOT NULL)"
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO schema_migrations (version, applied_at, note) VALUES (?, ?, ?)",
                        (1, _utc_now(), "detected pre-existing v1 fixture database"),
                    )
                    versions.add(1)

                if CURRENT_SCHEMA_VERSION not in versions:
                    self._upgrade_v1_to_v2(conn, tables)
                    conn.execute(
                        "INSERT OR IGNORE INTO schema_migrations (version, applied_at, note) VALUES (?, ?, ?)",
                        (CURRENT_SCHEMA_VERSION, _utc_now(), "upgraded v1 -> v2 preserving existing rows"),
                    )

            for table_name, reason in _APPEND_ONLY_TRIGGERS:
                for op in ("UPDATE", "DELETE"):
                    conn.execute(
                        f"CREATE TRIGGER IF NOT EXISTS tr_{table_name}_{op.lower()} "
                        f"BEFORE {op} ON {table_name} "
                        f"BEGIN SELECT RAISE(ABORT, '{reason}'); END"
                    )
            conn.commit()
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise

    def _upgrade_v1_to_v2(self, conn: sqlite3.Connection, existing_tables: set[str]) -> None:
        """Non-destructive migration from v1 schema fixture to full v2 schema."""
        if "cases" in existing_tables:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(cases)").fetchall()}
            alter_defs = [
                ("reopen_count", "INTEGER NOT NULL DEFAULT 0"),
                ("manual_waiting_hold", "INTEGER NOT NULL DEFAULT 0"),
                ("last_delivered_fingerprint", "TEXT"),
                ("last_material_fingerprint", "TEXT"),
                ("workflow_history_json", "TEXT NOT NULL DEFAULT '[]'"),
            ]
            for col_name, col_def in alter_defs:
                if col_name not in cols:
                    conn.execute(f"ALTER TABLE cases ADD COLUMN {col_name} {col_def}")
        if "backlog_items" in existing_tables:
            bcols = {row["name"] for row in conn.execute("PRAGMA table_info(backlog_items)").fetchall()}
            if "expires_at" not in bcols:
                conn.execute("ALTER TABLE backlog_items ADD COLUMN expires_at TEXT CHECK(expires_at IS NULL)")
        conn.executescript(_SCHEMA_V2_TABLES)

    @contextmanager
    def _write_tx(self):
        attempt = 0
        while True:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
                return
            except sqlite3.OperationalError as exc:
                if conn.in_transaction:
                    conn.rollback()
                msg = str(exc).lower()
                if any(tok in msg for tok in _BUSY_ERRORS) and attempt < 25:
                    attempt += 1
                    conn.close()
                    time.sleep(min(0.15, 0.004 * (attempt + random.random())))
                    continue
                raise
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    @contextmanager
    def _read_conn(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def schema_versions(self) -> list[dict]:
        with self._read_conn() as conn:
            rows = conn.execute("SELECT version, applied_at, note FROM schema_migrations ORDER BY version").fetchall()
            return [dict(r) for r in rows]

    def _insert_audit(
        self,
        conn: sqlite3.Connection,
        *,
        mode: str,
        tenant_id: str,
        company_id: str,
        case_id: str | None,
        event_type: str,
        actor_id: str | None,
        detail: dict,
        now: str,
    ) -> None:
        conn.execute(
            "INSERT INTO case_audit_events (event_id, mode_namespace, tenant_id, company_id, case_id, event_type, actor_id, detail_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _new_id("aud", mode, tenant_id, company_id, case_id or "-", event_type, now),
                mode,
                tenant_id,
                company_id,
                case_id,
                event_type,
                actor_id,
                canonical(detail).decode("utf-8"),
                now,
            ),
        )

    def _resolve_bundle(
        self,
        bundle_or_analysis: dict,
        *,
        scope,
        raw_snapshot: dict | None,
        ml_method: str | None,
        extra_scores: dict[str, dict] | None,
        ml_candidate_min_score: float,
    ) -> dict:
        if not isinstance(bundle_or_analysis, dict):
            fail(422, "BUNDLE_INVALID", "Dữ liệu đánh giá hàng đợi phải là JSON object.", "Truyền case-queue-bundle/1.0.0 hoặc kết quả rule_snapshot.")
        ver = bundle_or_analysis.get("version")
        if ver == BUNDLE_VERSION:
            tenant_id = str(scope.tenant_id)
            company_id = next(iter(scope.company_ids))
            if bundle_or_analysis.get("tenant_id") != tenant_id or bundle_or_analysis.get("company_id") != company_id:
                fail(403, "SCOPE_MISMATCH", "tenant_id/company_id trong bundle không khớp quyền xác thực.", "Không truyền chéo công ty.")
            return bundle_or_analysis
        if isinstance(bundle_or_analysis.get("transactions"), list) and isinstance(bundle_or_analysis.get("rule_count"), int):
            return build_case_bundle_from_rule_analysis(
                bundle_or_analysis,
                raw_snapshot=raw_snapshot,
                scope=scope,
                ml_method=ml_method,
                extra_scores=extra_scores,
                ml_candidate_min_score=ml_candidate_min_score,
            )
        fail(
            422,
            "UNSUPPORTED_CASE_INPUT",
            "Không nhận diện được định dạng dữ liệu đầu vào hàng đợi vụ việc.",
            "Dùng case-queue-bundle/1.0.0 hoặc kết quả rule_snapshot.analyze.",
        )

    def _dispatch_outbox_ids(
        self,
        conn_owner_scope: tuple[str, str, str, str],
        outbox_ids: list[str],
        *,
        fault_injector=None,
        external_sink=None,
    ) -> dict:
        """Execute transactional 2-stage outbox dispatch -> external sink -> atomic ack."""
        mode, tenant_id, company_id, actor_id = conn_owner_scope
        if not outbox_ids:
            return {"dispatched": 0, "acked": 0, "already_acked": 0, "queue_item_ids": []}

        # Stage 2: Transition pending_dispatch -> dispatched_unacked and insert idempotent queue_items
        placeholders = ",".join("?" for _ in outbox_ids)
        batch_items: list[dict] = []

        def _stage_dispatch(conn: sqlite3.Connection) -> list[dict]:
            rows = conn.execute(
                f"SELECT * FROM delivery_outbox WHERE outbox_id IN ({placeholders}) "
                "AND mode_namespace = ? AND tenant_id = ? AND company_id = ? ORDER BY created_at, outbox_id",
                (*outbox_ids, mode, tenant_id, company_id),
            ).fetchall()
            to_deliver = []
            now = _utc_now()
            for r in rows:
                if r["status"] == "acked":
                    continue
                payload = json.loads(r["payload_json"])
                q_id = f"qi_{digest(canonical([mode, tenant_id, company_id, r['outbox_id']]))[:24]}"
                conn.execute(
                    "INSERT OR IGNORE INTO queue_items "
                    "(queue_item_id, mode_namespace, tenant_id, company_id, policy_version, period_key, case_id, revision_no, "
                    "material_fingerprint, admission_decision, queue_target, outbox_id, payload_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        q_id,
                        mode,
                        tenant_id,
                        company_id,
                        r["policy_version"],
                        r["period_key"],
                        r["case_id"],
                        r["revision_no"],
                        r["material_fingerprint"],
                        r["admission_decision"],
                        r["queue_target"],
                        r["outbox_id"],
                        r["payload_json"],
                        now,
                    ),
                )
                conn.execute(
                    "UPDATE delivery_outbox SET status = 'dispatched_unacked', attempts = attempts + 1, updated_at = ? "
                    "WHERE outbox_id = ? AND status != 'acked'",
                    (now, r["outbox_id"]),
                )
                to_deliver.append(
                    {
                        "outbox_id": r["outbox_id"],
                        "queue_item_id": q_id,
                        "mode_namespace": mode,
                        "tenant_id": tenant_id,
                        "company_id": company_id,
                        "policy_version": r["policy_version"],
                        "period_key": r["period_key"],
                        "case_id": r["case_id"],
                        "revision_no": r["revision_no"],
                        "material_fingerprint": r["material_fingerprint"],
                        "admission_decision": r["admission_decision"],
                        "queue_target": r["queue_target"],
                        "payload": payload,
                    }
                )
            return to_deliver

        with self._write_tx() as conn:
            batch_items = _stage_dispatch(conn)

        if external_sink is not None:
            for item in batch_items:
                external_sink(deepcopy(item))

        if fault_injector is not None:
            fault_injector("after_sink_before_ack", deepcopy(batch_items))

        # Stage 3: Atomically ack outbox, mark delivery_ledger='sent', commit budget_reservations, update cases.last_delivered_fingerprint
        acked_qids = []

        def _stage_ack(conn: sqlite3.Connection) -> list[str]:
            now = _utc_now()
            qids = []
            rows = conn.execute(
                f"SELECT * FROM delivery_outbox WHERE outbox_id IN ({placeholders}) "
                "AND mode_namespace = ? AND tenant_id = ? AND company_id = ?",
                (*outbox_ids, mode, tenant_id, company_id),
            ).fetchall()
            for r in rows:
                qid_row = conn.execute(
                    "SELECT queue_item_id FROM queue_items WHERE outbox_id = ?",
                    (r["outbox_id"],),
                ).fetchone()
                if qid_row:
                    qids.append(qid_row["queue_item_id"])
                if r["status"] == "acked":
                    continue
                conn.execute(
                    "UPDATE delivery_outbox SET status = 'acked', updated_at = ? WHERE outbox_id = ?",
                    (now, r["outbox_id"]),
                )
                conn.execute(
                    "UPDATE delivery_ledger SET delivery_status = 'sent', updated_at = ? "
                    "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND policy_version = ? AND case_id = ? AND material_fingerprint = ?",
                    (
                        now,
                        mode,
                        tenant_id,
                        company_id,
                        r["policy_version"],
                        r["case_id"],
                        r["material_fingerprint"],
                    ),
                )
                conn.execute(
                    "UPDATE budget_reservations SET status = 'committed' "
                    "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND period_key = ? AND case_id = ? AND revision_no = ?",
                    (mode, tenant_id, company_id, r["period_key"], r["case_id"], r["revision_no"]),
                )
                conn.execute(
                    "UPDATE cases SET last_delivered_fingerprint = ?, updated_at = ? "
                    "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND case_id = ?",
                    (r["material_fingerprint"], now, mode, tenant_id, company_id, r["case_id"]),
                )
                self._insert_audit(
                    conn,
                    mode=mode,
                    tenant_id=tenant_id,
                    company_id=company_id,
                    case_id=r["case_id"],
                    event_type="outbox_delivery_acked",
                    actor_id=actor_id,
                    detail={
                        "outbox_id": r["outbox_id"],
                        "period_key": r["period_key"],
                        "revision_no": r["revision_no"],
                        "material_fingerprint": r["material_fingerprint"],
                        "queue_target": r["queue_target"],
                    },
                    now=now,
                )
            return qids

        with self._write_tx() as conn:
            acked_qids = _stage_ack(conn)

        return {
            "dispatched": len(batch_items),
            "acked": len(acked_qids),
            "queue_item_ids": acked_qids,
        }

    def evaluate_and_enqueue(
        self,
        scope,
        bundle_or_analysis: dict,
        *,
        policy: dict | None = None,
        mode: str = "active",
        period_key: str,
        idempotency_key: str,
        recheck=None,
        raw_snapshot: dict | None = None,
        ml_method: str | None = None,
        extra_scores: dict[str, dict] | None = None,
        ml_candidate_min_score: float = 0.65,
        fault_injector=None,
        external_sink=None,
    ) -> dict:
        """Coalesce candidates into cases, apply threshold/evidence eligibility, reserve atomic budget, and enqueue via outbox."""
        tenant_id, company_id, actor_id = _require_scope(scope, recheck, "data.import")
        mode = _validate_mode(mode)
        if not isinstance(period_key, str) or not period_key.strip():
            fail(422, "PERIOD_KEY_INVALID", "Thiếu period_key hợp lệ.", "Cung cấp kỳ ngân sách (ví dụ 2026-W46).")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            fail(422, "IDEMPOTENCY_KEY_REQUIRED", "Bắt buộc có idempotency_key cho thao tác ghi hàng đợi.", "Truyền Idempotency-Key duy nhất cho mỗi yêu cầu.")

        effective_policy = validate_policy(policy if policy is not None else default_fixture_policy())
        pol_hash = policy_hash(effective_policy)
        pol_ver = effective_policy["policy_version"]
        budget_limit = int(effective_policy["budget"]["case_budget_limit"])
        q_target = _queue_target(mode)

        bundle = self._resolve_bundle(
            bundle_or_analysis,
            scope=scope,
            raw_snapshot=raw_snapshot,
            ml_method=ml_method,
            extra_scores=extra_scores,
            ml_candidate_min_score=ml_candidate_min_score,
        )
        coalesced = coalesce_cases(bundle, effective_policy)
        for case_obj in coalesced:
            validate_against_schema(case_obj, "coalesced_case")

        req_digest = digest(
            canonical(
                {
                    "op": "evaluate_and_enqueue",
                    "mode": mode,
                    "period_key": period_key,
                    "policy_hash": pol_hash,
                    "bundle": bundle,
                }
            )
        )

        # Stage 1: Check idempotency receipt OR atomically reserve budget & write outbox.
        outbox_ids_to_dispatch: list[str] = []
        tx_response: dict = {}
        idempotent_replay = False

        with self._write_tx() as conn:
            if recheck is not None and recheck() != scope:
                fail(409, "AUTH_CONTEXT_CHANGED", "Quyền đã thay đổi trước khi ghi DB.", "Gửi lại với quyền hiện hành.")

            existing_receipt = conn.execute(
                "SELECT request_hash, response_json FROM request_receipts "
                "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND operation = 'evaluate_and_enqueue' AND idempotency_key = ?",
                (mode, tenant_id, company_id, idempotency_key),
            ).fetchone()
            if existing_receipt is not None:
                if existing_receipt["request_hash"] != req_digest:
                    fail(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "Idempotency-Key đã được dùng cho payload khác.",
                        "Dùng Idempotency-Key mới cho dữ liệu hoặc cấu hình mới.",
                    )
                idempotent_replay = True
                tx_response = json.loads(existing_receipt["response_json"])
                outbox_ids_to_dispatch = list(tx_response.get("_pending_outbox_ids") or [])
            else:
                now = _utc_now()
                # Ensure period row exists atomically with CHECK(reserved_count <= budget_limit)
                period_row = conn.execute(
                    "SELECT * FROM budget_periods WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND period_key = ?",
                    (mode, tenant_id, company_id, period_key),
                ).fetchone()
                if period_row is None:
                    conn.execute(
                        "INSERT INTO budget_periods (mode_namespace, tenant_id, company_id, period_key, budget_limit, reserved_count, policy_hash, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)",
                        (mode, tenant_id, company_id, period_key, budget_limit, pol_hash, now, now),
                    )
                    reserved_so_far = 0
                    effective_limit = budget_limit
                else:
                    effective_limit = int(period_row["budget_limit"])
                    reserved_so_far = int(period_row["reserved_count"])
                    if effective_limit != budget_limit and reserved_so_far <= budget_limit:
                        conn.execute(
                            "UPDATE budget_periods SET budget_limit = ?, policy_hash = ?, updated_at = ? "
                            "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND period_key = ?",
                            (budget_limit, pol_hash, now, mode, tenant_id, company_id, period_key),
                        )
                        effective_limit = budget_limit

                # Phase 1a: Inspect each coalesced case, update revisions, assess eligibility
                assessed_cases: list[tuple[dict, dict, int, dict, bool]] = []
                for case_obj in coalesced:
                    cid = case_obj["case_id"]
                    case_row = conn.execute(
                        "SELECT * FROM cases WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND case_id = ?",
                        (mode, tenant_id, company_id, cid),
                    ).fetchone()
                    prev_rev_row = conn.execute(
                        "SELECT * FROM case_revisions WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND case_id = ? "
                        "ORDER BY revision_no DESC LIMIT 1",
                        (mode, tenant_id, company_id, cid),
                    ).fetchone()
                    prev_case = json.loads(prev_rev_row["case_json"]) if prev_rev_row else None
                    is_material, mat_diff = evaluate_material_change(prev_case, case_obj, effective_policy)
                    # Release/model/policy changes alone cannot re-notify the same
                    # candidates on identical immutable source. Keep policy/version
                    # in audit, but never use it as an automatic quota reset.
                    if prev_case:
                        before_binding=prev_case.get('snapshot_binding') or {};after_binding=case_obj.get('snapshot_binding') or {}
                        if (before_binding.get('bundle_id') and after_binding.get('bundle_id') and
                            before_binding['bundle_id']!=after_binding['bundle_id'] and
                            before_binding.get('data_checksum') and before_binding['data_checksum']==after_binding.get('data_checksum') and
                            prev_case.get('candidate_ids')==case_obj.get('candidate_ids')):
                            mat_diff=dict(mat_diff,is_material_change=False,reasons=['release_change_same_source_candidates'])

                    ledger_row = conn.execute(
                        "SELECT * FROM delivery_ledger "
                        "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND policy_version = ? AND case_id = ? AND material_fingerprint = ?",
                        (mode, tenant_id, company_id, pol_ver, cid, case_obj["material_fingerprint"]),
                    ).fetchone()

                    if case_row is None:
                        rev_no = 1
                        existing_state = None
                    else:
                        rev_no = int(case_row["current_revision"]) + 1
                        existing_state = {
                            "case_workflow_status": case_row["case_workflow_status"],
                            "case_resolution": case_row["case_resolution"],
                            "manual_waiting_hold": bool(case_row["manual_waiting_hold"]),
                            "last_delivered_fingerprint": case_row["last_delivered_fingerprint"],
                        }

                    admission = assess_case_eligibility(
                        case_obj,
                        existing_state=existing_state,
                        delivery_match=dict(ledger_row) if ledger_row else None,
                        material_eval=mat_diff,
                        policy=effective_policy,
                    )
                    assessed_cases.append((case_obj, mat_diff, rev_no, admission, case_row is not None))

                # Phase 1b: Sort eligible candidates deterministically and reserve budget atomically
                eligible_indices = [
                    idx for idx, (_, _, _, adm, _) in enumerate(assessed_cases) if adm["eligible_for_budget"]
                ]
                eligible_indices.sort(
                    key=lambda idx: case_priority_key(assessed_cases[idx][0], assessed_cases[idx][3])
                )

                remaining_budget = max(0, effective_limit - reserved_so_far)
                reserved_indices = set()
                deferred_indices = set()
                for idx in eligible_indices:
                    if remaining_budget > 0:
                        reserved_indices.add(idx)
                        remaining_budget -= 1
                    else:
                        deferred_indices.add(idx)

                # Phase 1c: Persist cases, revisions, budget_reservations, alert_decisions, ledger/outbox, backlog
                decision_records = []
                queued_outbox_refs = []
                backlog_records = []
                newly_reserved = 0

                for idx, (case_obj, mat_diff, rev_no, admission, had_case_row) in enumerate(assessed_cases):
                    cid = case_obj["case_id"]
                    snap = case_obj["snapshot_binding"]
                    case_json_str = canonical(case_obj).decode("utf-8")

                    if idx in reserved_indices:
                        final_decision = admission["initial_decision"]  # 'selected' or 'mandatory_route'
                        backlog_code = None
                        reason_detail = admission["reason_detail"]
                    elif idx in deferred_indices:
                        final_decision = "budget_deferred"
                        backlog_code = "budget_exhausted"
                        reason_detail = (
                            f"Vụ việc đủ điều kiện ({admission['reason_detail']}) nhưng đã hết ngân sách "
                            f"({effective_limit} case/kỳ {period_key}); chuyển hàng chờ xem xét."
                        )
                    else:
                        final_decision = admission["decision"]
                        backlog_code = admission["backlog_reason_code"]
                        reason_detail = admission["reason_detail"]

                    # Upsert cases table preserving closed/reopen history
                    if not had_case_row:
                        wf_status = "waiting_evidence" if final_decision == "need_evidence" else "new"
                        wf_hist = [
                            {
                                "event": "case_created",
                                "workflow_status": wf_status,
                                "resolution": None,
                                "revision_no": rev_no,
                                "at": now,
                            }
                        ]
                        conn.execute(
                            "INSERT INTO cases "
                            "(mode_namespace, tenant_id, company_id, case_id, problem_family, obligation_id, current_revision, "
                            "case_workflow_status, case_resolution, reopen_count, manual_waiting_hold, last_delivered_fingerprint, "
                            "last_material_fingerprint, latest_case_json, workflow_history_json, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, 0, NULL, ?, ?, ?, ?, ?)",
                            (
                                mode,
                                tenant_id,
                                company_id,
                                cid,
                                case_obj["problem_family"],
                                case_obj["obligation_id"],
                                rev_no,
                                wf_status,
                                case_obj["material_fingerprint"],
                                case_json_str,
                                canonical(wf_hist).decode("utf-8"),
                                now,
                                now,
                            ),
                        )
                    else:
                        prev_row = conn.execute(
                            "SELECT * FROM cases WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND case_id = ?",
                            (mode, tenant_id, company_id, cid),
                        ).fetchone()
                        wf_status = prev_row["case_workflow_status"]
                        wf_res = prev_row["case_resolution"]
                        reopen_cnt = int(prev_row["reopen_count"])
                        wf_hist = json.loads(prev_row["workflow_history_json"])
                        if admission.get("reopen_closed"):
                            reopen_cnt += 1
                            wf_hist.append(
                                {
                                    "event": "case_reopened_on_material_change",
                                    "previous_workflow_status": wf_status,
                                    "previous_resolution": wf_res,
                                    "workflow_status": "in_review",
                                    "resolution": None,
                                    "revision_no": rev_no,
                                    "reasons": mat_diff.get("reasons", []),
                                    "at": now,
                                }
                            )
                            wf_status = "in_review"
                            wf_res = None
                            self._insert_audit(
                                conn,
                                mode=mode,
                                tenant_id=tenant_id,
                                company_id=company_id,
                                case_id=cid,
                                event_type="case_reopened_on_material_change",
                                actor_id=actor_id,
                                detail={"revision_no": rev_no, "reasons": mat_diff.get("reasons", [])},
                                now=now,
                            )
                        elif wf_status == "waiting_evidence" and final_decision in ("selected", "mandatory_route", "budget_deferred"):
                            wf_status = "in_review"
                            wf_hist.append(
                                {
                                    "event": "evidence_sufficient_reopened",
                                    "workflow_status": wf_status,
                                    "resolution": None,
                                    "revision_no": rev_no,
                                    "at": now,
                                }
                            )
                        elif final_decision == "need_evidence" and wf_status == "new":
                            wf_status = "waiting_evidence"

                        conn.execute(
                            "UPDATE cases SET current_revision = ?, case_workflow_status = ?, case_resolution = ?, "
                            "reopen_count = ?, last_material_fingerprint = ?, latest_case_json = ?, workflow_history_json = ?, updated_at = ? "
                            "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND case_id = ?",
                            (
                                rev_no,
                                wf_status,
                                wf_res,
                                reopen_cnt,
                                case_obj["material_fingerprint"],
                                case_json_str,
                                canonical(wf_hist).decode("utf-8"),
                                now,
                                mode,
                                tenant_id,
                                company_id,
                                cid,
                            ),
                        )

                    conn.execute(
                        "INSERT INTO case_revisions "
                        "(mode_namespace, tenant_id, company_id, case_id, revision_no, material_fingerprint, "
                        "is_material_change, diff_json, snapshot_id, run_id, analysis_id, case_json, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            mode,
                            tenant_id,
                            company_id,
                            cid,
                            rev_no,
                            case_obj["material_fingerprint"],
                            1 if mat_diff.get("is_material_change") else 0,
                            canonical(mat_diff).decode("utf-8"),
                            snap.get("snapshot_id"),
                            snap.get("run_id"),
                            snap.get("analysis_id"),
                            case_json_str,
                            now,
                        ),
                    )

                    dec_id = _new_id("dec", mode, period_key, cid, rev_no)
                    conn.execute(
                        "INSERT INTO alert_decisions "
                        "(decision_id, mode_namespace, tenant_id, company_id, period_key, case_id, revision_no, "
                        "material_fingerprint, decision, backlog_reason_code, reason_detail, policy_hash, request_idempotency_key, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            dec_id,
                            mode,
                            tenant_id,
                            company_id,
                            period_key,
                            cid,
                            rev_no,
                            case_obj["material_fingerprint"],
                            final_decision,
                            backlog_code,
                            reason_detail,
                            pol_hash,
                            idempotency_key,
                            now,
                        ),
                    )

                    decision_records.append(
                        {
                            "decision_id": dec_id,
                            "case_id": cid,
                            "revision_no": rev_no,
                            "decision": final_decision,
                            "backlog_reason_code": backlog_code,
                            "reason_detail": reason_detail,
                            "material_fingerprint": case_obj["material_fingerprint"],
                            "is_material_change": bool(mat_diff.get("is_material_change")),
                            "problem_family": case_obj["problem_family"],
                            "obligation_id": case_obj["obligation_id"],
                        }
                    )

                    if idx in reserved_indices:
                        newly_reserved += 1
                        conn.execute(
                            "INSERT INTO budget_reservations "
                            "(mode_namespace, tenant_id, company_id, period_key, case_id, revision_no, "
                            "material_fingerprint, decision, status, request_idempotency_key, created_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'reserved', ?, ?)",
                            (
                                mode,
                                tenant_id,
                                company_id,
                                period_key,
                                cid,
                                rev_no,
                                case_obj["material_fingerprint"],
                                final_decision,
                                idempotency_key,
                                now,
                            ),
                        )
                        outbox_id = f"obx_{digest(canonical([mode, tenant_id, company_id, pol_ver, cid, case_obj['material_fingerprint'], period_key, rev_no]))[:24]}"
                        outbox_payload = {
                            "version": REPORT_VERSION,
                            "mode_namespace": mode,
                            "queue_target": q_target,
                            "period_key": period_key,
                            "policy_version": pol_ver,
                            "admission_decision": final_decision,
                            "reason_detail": reason_detail,
                            "revision_no": rev_no,
                            "case": case_obj,
                        }
                        conn.execute(
                            "INSERT INTO delivery_ledger "
                            "(mode_namespace, tenant_id, company_id, policy_version, case_id, material_fingerprint, "
                            "revision_no, period_key, outbox_id, delivery_status, queue_target, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
                            (
                                mode,
                                tenant_id,
                                company_id,
                                pol_ver,
                                cid,
                                case_obj["material_fingerprint"],
                                rev_no,
                                period_key,
                                outbox_id,
                                q_target,
                                now,
                                now,
                            ),
                        )
                        conn.execute(
                            "INSERT INTO delivery_outbox "
                            "(outbox_id, mode_namespace, tenant_id, company_id, policy_version, period_key, case_id, "
                            "revision_no, material_fingerprint, admission_decision, queue_target, payload_json, status, attempts, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_dispatch', 0, ?, ?)",
                            (
                                outbox_id,
                                mode,
                                tenant_id,
                                company_id,
                                pol_ver,
                                period_key,
                                cid,
                                rev_no,
                                case_obj["material_fingerprint"],
                                final_decision,
                                q_target,
                                canonical(outbox_payload).decode("utf-8"),
                                now,
                                now,
                            ),
                        )
                        conn.execute(
                            "UPDATE backlog_items SET status = 'promoted', updated_at = ? "
                            "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND case_id = ? AND status = 'waiting'",
                            (now, mode, tenant_id, company_id, cid),
                        )
                        outbox_ids_to_dispatch.append(outbox_id)
                        queued_outbox_refs.append({"outbox_id": outbox_id, "case_id": cid, "decision": final_decision})
                    elif backlog_code is not None and final_decision in ("budget_deferred", "need_evidence", "below_threshold", "unscorable"):
                        conn.execute(
                            "INSERT INTO backlog_items "
                            "(mode_namespace, tenant_id, company_id, case_id, revision_no, period_key, backlog_reason_code, "
                            "decision, reason_detail, status, expires_at, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'waiting', NULL, ?, ?) "
                            "ON CONFLICT(mode_namespace, tenant_id, company_id, case_id) DO UPDATE SET "
                            "revision_no=excluded.revision_no, period_key=excluded.period_key, "
                            "backlog_reason_code=excluded.backlog_reason_code, decision=excluded.decision, "
                            "reason_detail=excluded.reason_detail, status='waiting', expires_at=NULL, updated_at=excluded.updated_at",
                            (
                                mode,
                                tenant_id,
                                company_id,
                                cid,
                                rev_no,
                                period_key,
                                backlog_code,
                                final_decision,
                                reason_detail,
                                now,
                                now,
                            ),
                        )
                        backlog_records.append(
                            {"case_id": cid, "decision": final_decision, "backlog_reason_code": backlog_code}
                        )

                if newly_reserved > 0:
                    conn.execute(
                        "UPDATE budget_periods SET reserved_count = reserved_count + ?, updated_at = ? "
                        "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND period_key = ?",
                        (newly_reserved, now, mode, tenant_id, company_id, period_key),
                    )

                final_period = conn.execute(
                    "SELECT budget_limit, reserved_count FROM budget_periods "
                    "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND period_key = ?",
                    (mode, tenant_id, company_id, period_key),
                ).fetchone()

                tx_response = {
                    "version": REPORT_VERSION,
                    "mode_namespace": mode,
                    "queue_target": q_target,
                    "active_delivery": bool(mode == "active"),
                    "tenant_id": tenant_id,
                    "company_id": company_id,
                    "period_key": period_key,
                    "idempotency_key": idempotency_key,
                    "idempotent_replay": False,
                    "policy_summary": {
                        "policy_id": effective_policy["policy_id"],
                        "policy_version": pol_ver,
                        "policy_hash": pol_hash,
                        "approved_for_production": bool(effective_policy["fixture_declaration"]["approved_for_production"]),
                        "open_decision_gates": list(effective_policy["fixture_declaration"]["open_decision_gates"]),
                        "benchmark_transaction_cap_preserved": 5,
                    },
                    "budget_status": {
                        "unit": "case",
                        "period_key": period_key,
                        "budget_limit": int(final_period["budget_limit"]),
                        "reserved_count": int(final_period["reserved_count"]),
                        "remaining": int(final_period["budget_limit"]) - int(final_period["reserved_count"]),
                    },
                    "counts": {
                        "total_cases": len(coalesced),
                        "queued_or_reserved": len(queued_outbox_refs),
                        "backlog_waiting": len(backlog_records),
                        "already_notified": sum(1 for d in decision_records if d["decision"] == "already_notified"),
                    },
                    "decisions": decision_records,
                    "queued_outbox_refs": queued_outbox_refs,
                    "backlog_added_or_updated": backlog_records,
                    "_pending_outbox_ids": list(outbox_ids_to_dispatch),
                }
                conn.execute(
                    "INSERT INTO request_receipts "
                    "(mode_namespace, tenant_id, company_id, operation, idempotency_key, request_hash, response_json, created_at) "
                    "VALUES (?, ?, ?, 'evaluate_and_enqueue', ?, ?, ?, ?)",
                    (
                        mode,
                        tenant_id,
                        company_id,
                        idempotency_key,
                        req_digest,
                        canonical(tx_response).decode("utf-8"),
                        now,
                    ),
                )
                self._insert_audit(
                    conn,
                    mode=mode,
                    tenant_id=tenant_id,
                    company_id=company_id,
                    case_id=None,
                    event_type="evaluate_and_enqueue_committed",
                    actor_id=actor_id,
                    detail={
                        "period_key": period_key,
                        "idempotency_key": idempotency_key,
                        "total_cases": len(coalesced),
                        "reserved_now": newly_reserved,
                    },
                    now=now,
                )

                if fault_injector is not None:
                    fault_injector("before_reserve_commit", deepcopy(tx_response))

        if fault_injector is not None and not idempotent_replay:
            fault_injector("after_reserve_before_sink", deepcopy(tx_response))

        dispatch_res = self._dispatch_outbox_ids(
            (mode, tenant_id, company_id, actor_id),
            outbox_ids_to_dispatch,
            fault_injector=fault_injector if not idempotent_replay else None,
            external_sink=external_sink,
        )
        tx_response["idempotent_replay"] = idempotent_replay
        tx_response["dispatch_result"] = dispatch_res
        tx_response.pop("_pending_outbox_ids", None)
        return tx_response

    def recover_outbox(
        self,
        scope,
        *,
        mode: str = "active",
        recheck=None,
        fault_injector=None,
        external_sink=None,
    ) -> dict:
        """Scan pending_dispatch / dispatched_unacked outbox rows and finish delivery idempotently without extra budget."""
        tenant_id, company_id, actor_id = _require_scope(scope, recheck, "data.import")
        mode = _validate_mode(mode)
        with self._read_conn() as conn:
            rows = conn.execute(
                "SELECT outbox_id, status, case_id FROM delivery_outbox "
                "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? "
                "AND status IN ('pending_dispatch','dispatched_unacked') ORDER BY created_at, outbox_id",
                (mode, tenant_id, company_id),
            ).fetchall()
        outbox_ids = [r["outbox_id"] for r in rows]
        res = self._dispatch_outbox_ids(
            (mode, tenant_id, company_id, actor_id),
            outbox_ids,
            fault_injector=fault_injector,
            external_sink=external_sink,
        )
        return {
            "version": REPORT_VERSION,
            "mode_namespace": mode,
            "tenant_id": tenant_id,
            "company_id": company_id,
            "recovered_outbox_ids": outbox_ids,
            **res,
        }

    def reevaluate_backlog(
        self,
        scope,
        *,
        policy: dict | None = None,
        mode: str = "active",
        target_period_key: str,
        updated_bundle: dict | None = None,
        supplemental_sources: dict | None = None,
        idempotency_key: str,
        recheck=None,
        external_sink=None,
    ) -> dict:
        """Re-evaluate waiting backlog items when a new budget period opens or missing evidence arrives."""
        tenant_id, company_id, actor_id = _require_scope(scope, recheck, "data.import")
        mode = _validate_mode(mode)
        if not isinstance(target_period_key, str) or not target_period_key.strip():
            fail(422, "PERIOD_KEY_INVALID", "Thiếu target_period_key.", "Truyền kỳ mới để tái đánh giá backlog.")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            fail(422, "IDEMPOTENCY_KEY_REQUIRED", "Bắt buộc có idempotency_key.", "Truyền Idempotency-Key.")

        effective_policy = validate_policy(policy if policy is not None else default_fixture_policy())
        pol_hash = policy_hash(effective_policy)
        pol_ver = effective_policy["policy_version"]
        budget_limit = int(effective_policy["budget"]["case_budget_limit"])
        q_target = _queue_target(mode)

        updated_map: dict[str, dict] = {}
        if updated_bundle is not None:
            resolved = self._resolve_bundle(
                updated_bundle, scope=scope, raw_snapshot=None, ml_method=None, extra_scores=None, ml_candidate_min_score=0.65
            )
            for c in coalesce_cases(resolved, effective_policy):
                validate_against_schema(c, "coalesced_case")
                updated_map[c["case_id"]] = c

        supp_by_case = (supplemental_sources or {}).get("by_case_id") or {}
        supp_by_ob = (supplemental_sources or {}).get("by_obligation_id") or {}

        req_digest = digest(
            canonical(
                {
                    "op": "reevaluate_backlog",
                    "mode": mode,
                    "target_period_key": target_period_key,
                    "policy_hash": pol_hash,
                    "updated_case_ids": sorted(updated_map),
                    "supplemental_sources": supplemental_sources or {},
                }
            )
        )

        outbox_ids_to_dispatch: list[str] = []
        tx_response: dict = {}
        idempotent_replay = False

        with self._write_tx() as conn:
            if recheck is not None and recheck() != scope:
                fail(409, "AUTH_CONTEXT_CHANGED", "Quyền đã thay đổi.", "Gửi lại với quyền hiện hành.")

            existing_receipt = conn.execute(
                "SELECT request_hash, response_json FROM request_receipts "
                "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND operation = 'reevaluate_backlog' AND idempotency_key = ?",
                (mode, tenant_id, company_id, idempotency_key),
            ).fetchone()
            if existing_receipt is not None:
                if existing_receipt["request_hash"] != req_digest:
                    fail(409, "IDEMPOTENCY_CONFLICT", "Idempotency-Key đã dùng cho dữ liệu backlog khác.", "Dùng key mới.")
                idempotent_replay = True
                tx_response = json.loads(existing_receipt["response_json"])
                outbox_ids_to_dispatch = list(tx_response.get("_pending_outbox_ids") or [])
            else:
                now = _utc_now()
                period_row = conn.execute(
                    "SELECT * FROM budget_periods WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND period_key = ?",
                    (mode, tenant_id, company_id, target_period_key),
                ).fetchone()
                if period_row is None:
                    conn.execute(
                        "INSERT INTO budget_periods (mode_namespace, tenant_id, company_id, period_key, budget_limit, reserved_count, policy_hash, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)",
                        (mode, tenant_id, company_id, target_period_key, budget_limit, pol_hash, now, now),
                    )
                    effective_limit = budget_limit
                    reserved_so_far = 0
                else:
                    effective_limit = int(period_row["budget_limit"])
                    reserved_so_far = int(period_row["reserved_count"])
                    if effective_limit != budget_limit and reserved_so_far <= budget_limit:
                        conn.execute(
                            "UPDATE budget_periods SET budget_limit = ?, policy_hash = ?, updated_at = ? "
                            "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND period_key = ?",
                            (budget_limit, pol_hash, now, mode, tenant_id, company_id, target_period_key),
                        )
                        effective_limit = budget_limit

                waiting_rows = conn.execute(
                    "SELECT b.*, c.current_revision, c.case_workflow_status, c.case_resolution, c.manual_waiting_hold, "
                    "c.last_delivered_fingerprint, c.latest_case_json, c.workflow_history_json "
                    "FROM backlog_items b JOIN cases c "
                    "ON b.mode_namespace = c.mode_namespace AND b.tenant_id = c.tenant_id AND b.company_id = c.company_id AND b.case_id = c.case_id "
                    "WHERE b.mode_namespace = ? AND b.tenant_id = ? AND b.company_id = ? AND b.status = 'waiting' "
                    "ORDER BY b.created_at, b.case_id",
                    (mode, tenant_id, company_id),
                ).fetchall()

                candidates_for_eval = []
                for brow in waiting_rows:
                    cid = brow["case_id"]
                    base_case = json.loads(brow["latest_case_json"])
                    new_case = deepcopy(updated_map[cid]) if cid in updated_map else deepcopy(base_case)
                    supp = supp_by_case.get(cid) or supp_by_ob.get(new_case["obligation_id"])
                    supp_applied = False
                    if isinstance(supp, dict):
                        supp_applied = True
                        if "evidence_sufficient" in supp:
                            new_case["evidence_sufficient"] = bool(supp["evidence_sufficient"])
                        if "has_blocking_source_gap" in supp:
                            new_case["has_blocking_source_gap"] = bool(supp["has_blocking_source_gap"])
                        if "source_gaps" in supp:
                            new_case["source_gaps"] = deepcopy(supp["source_gaps"])
                        for k in ("evidence_tx_ids", "evidence_ids"):
                            if k in supp:
                                new_case[k] = sorted(set(new_case.get(k) or []) | set(supp[k]))
                        if isinstance(supp.get("source_links"), list):
                            existing_keys = {(lk["table"], lk["record_id"], lk["role"]) for lk in new_case["source_links"]}
                            for lk in supp["source_links"]:
                                key = (lk["table"], lk["record_id"], lk["role"])
                                if key not in existing_keys:
                                    existing_keys.add(key)
                                    new_case["source_links"].append(deepcopy(lk))
                        if "scorable" in supp:
                            new_case["scorable"] = bool(supp["scorable"])
                        if "case_score" in supp:
                            new_case["case_score"] = supp["case_score"]
                        # Recompute deterministic material_fingerprint preserving material fields
                        mat_core = {
                            "tenant_id": new_case["tenant_id"],
                            "company_id": new_case["company_id"],
                            "problem_family": new_case["problem_family"],
                            "obligation_id": new_case["obligation_id"],
                            "candidate_ids": new_case["candidate_ids"],
                            "evidence_tx_ids": new_case["evidence_tx_ids"],
                            "actionable_rule_ids": new_case["actionable_rule_ids"],
                            "hard_trigger": new_case["hard_trigger"],
                            "scorable": new_case["scorable"],
                            "evidence_sufficient": new_case["evidence_sufficient"],
                            "has_blocking_source_gap": new_case["has_blocking_source_gap"],
                            "financial_core": new_case["financial_summary"],
                            "case_score_value": round(float(new_case["case_score"]), 6)
                            if new_case.get("case_score") is not None
                            else None,
                        }
                        new_case["material_fingerprint"] = digest(canonical(mat_core))

                    is_mat, mat_diff = evaluate_material_change(base_case, new_case, effective_policy)
                    ledger_row = conn.execute(
                        "SELECT * FROM delivery_ledger "
                        "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND policy_version = ? AND case_id = ? AND material_fingerprint = ?",
                        (mode, tenant_id, company_id, pol_ver, cid, new_case["material_fingerprint"]),
                    ).fetchone()
                    existing_state = {
                        "case_workflow_status": brow["case_workflow_status"],
                        "case_resolution": brow["case_resolution"],
                        "manual_waiting_hold": bool(brow["manual_waiting_hold"]),
                        "supplemental_cleared": bool(supp_applied and not new_case.get("has_blocking_source_gap") and new_case.get("evidence_sufficient")),
                        "last_delivered_fingerprint": brow["last_delivered_fingerprint"],
                    }
                    adm = assess_case_eligibility(
                        new_case,
                        existing_state=existing_state,
                        delivery_match=dict(ledger_row) if ledger_row else None,
                        material_eval=mat_diff if (cid in updated_map or supp_applied) else {"is_material_change": True},
                        policy=effective_policy,
                    )
                    candidates_for_eval.append((brow, base_case, new_case, mat_diff, supp_applied or (cid in updated_map), adm))

                eligible_indices = [
                    idx for idx, (_, _, _, _, _, adm) in enumerate(candidates_for_eval) if adm["eligible_for_budget"]
                ]
                eligible_indices.sort(
                    key=lambda idx: case_priority_key(candidates_for_eval[idx][2], candidates_for_eval[idx][5])
                )

                remaining_budget = max(0, effective_limit - reserved_so_far)
                reserved_indices = set()
                deferred_indices = set()
                for idx in eligible_indices:
                    if remaining_budget > 0:
                        reserved_indices.add(idx)
                        remaining_budget -= 1
                    else:
                        deferred_indices.add(idx)

                promoted = []
                still_waiting = []
                newly_reserved = 0

                for idx, (brow, base_case, new_case, mat_diff, had_update, adm) in enumerate(candidates_for_eval):
                    cid = brow["case_id"]
                    rev_no = int(brow["current_revision"]) + (1 if had_update else 0)
                    if had_update:
                        new_json = canonical(new_case).decode("utf-8")
                        conn.execute(
                            "INSERT INTO case_revisions "
                            "(mode_namespace, tenant_id, company_id, case_id, revision_no, material_fingerprint, "
                            "is_material_change, diff_json, snapshot_id, run_id, analysis_id, case_json, created_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                mode,
                                tenant_id,
                                company_id,
                                cid,
                                rev_no,
                                new_case["material_fingerprint"],
                                1,
                                canonical(mat_diff).decode("utf-8"),
                                (new_case.get("snapshot_binding") or {}).get("snapshot_id"),
                                (new_case.get("snapshot_binding") or {}).get("run_id"),
                                (new_case.get("snapshot_binding") or {}).get("analysis_id"),
                                new_json,
                                now,
                            ),
                        )
                        conn.execute(
                            "UPDATE cases SET current_revision = ?, manual_waiting_hold = 0, last_material_fingerprint = ?, latest_case_json = ?, updated_at = ? "
                            "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND case_id = ?",
                            (rev_no, new_case["material_fingerprint"], new_json, now, mode, tenant_id, company_id, cid),
                        )

                    if idx in reserved_indices:
                        final_decision = adm["initial_decision"]
                        newly_reserved += 1
                        dec_id = _new_id("dec", mode, target_period_key, cid, rev_no)
                        conn.execute(
                            "INSERT INTO alert_decisions "
                            "(decision_id, mode_namespace, tenant_id, company_id, period_key, case_id, revision_no, "
                            "material_fingerprint, decision, backlog_reason_code, reason_detail, policy_hash, request_idempotency_key, created_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)",
                            (
                                dec_id,
                                mode,
                                tenant_id,
                                company_id,
                                target_period_key,
                                cid,
                                rev_no,
                                new_case["material_fingerprint"],
                                final_decision,
                                f"Chuyển từ backlog sang kỳ {target_period_key}: {adm['reason_detail']}",
                                pol_hash,
                                idempotency_key,
                                now,
                            ),
                        )
                        conn.execute(
                            "INSERT INTO budget_reservations "
                            "(mode_namespace, tenant_id, company_id, period_key, case_id, revision_no, "
                            "material_fingerprint, decision, status, request_idempotency_key, created_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'reserved', ?, ?)",
                            (
                                mode,
                                tenant_id,
                                company_id,
                                target_period_key,
                                cid,
                                rev_no,
                                new_case["material_fingerprint"],
                                final_decision,
                                idempotency_key,
                                now,
                            ),
                        )
                        outbox_id = f"obx_{digest(canonical([mode, tenant_id, company_id, pol_ver, cid, new_case['material_fingerprint'], target_period_key, rev_no]))[:24]}"
                        outbox_payload = {
                            "version": REPORT_VERSION,
                            "mode_namespace": mode,
                            "queue_target": q_target,
                            "period_key": target_period_key,
                            "policy_version": pol_ver,
                            "admission_decision": final_decision,
                            "promoted_from_backlog": True,
                            "revision_no": rev_no,
                            "case": new_case,
                        }
                        conn.execute(
                            "INSERT INTO delivery_ledger "
                            "(mode_namespace, tenant_id, company_id, policy_version, case_id, material_fingerprint, "
                            "revision_no, period_key, outbox_id, delivery_status, queue_target, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
                            (
                                mode,
                                tenant_id,
                                company_id,
                                pol_ver,
                                cid,
                                new_case["material_fingerprint"],
                                rev_no,
                                target_period_key,
                                outbox_id,
                                q_target,
                                now,
                                now,
                            ),
                        )
                        conn.execute(
                            "INSERT INTO delivery_outbox "
                            "(outbox_id, mode_namespace, tenant_id, company_id, policy_version, period_key, case_id, "
                            "revision_no, material_fingerprint, admission_decision, queue_target, payload_json, status, attempts, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_dispatch', 0, ?, ?)",
                            (
                                outbox_id,
                                mode,
                                tenant_id,
                                company_id,
                                pol_ver,
                                target_period_key,
                                cid,
                                rev_no,
                                new_case["material_fingerprint"],
                                final_decision,
                                q_target,
                                canonical(outbox_payload).decode("utf-8"),
                                now,
                                now,
                            ),
                        )
                        conn.execute(
                            "UPDATE backlog_items SET status = 'promoted', revision_no = ?, period_key = ?, updated_at = ? "
                            "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND case_id = ?",
                            (rev_no, target_period_key, now, mode, tenant_id, company_id, cid),
                        )
                        if brow["case_workflow_status"] == "waiting_evidence":
                            conn.execute(
                                "UPDATE cases SET case_workflow_status = 'in_review', updated_at = ? "
                                "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND case_id = ?",
                                (now, mode, tenant_id, company_id, cid),
                            )
                        self._insert_audit(
                            conn,
                            mode=mode,
                            tenant_id=tenant_id,
                            company_id=company_id,
                            case_id=cid,
                            event_type="backlog_promoted",
                            actor_id=actor_id,
                            detail={"target_period_key": target_period_key, "outbox_id": outbox_id},
                            now=now,
                        )
                        outbox_ids_to_dispatch.append(outbox_id)
                        promoted.append({"case_id": cid, "outbox_id": outbox_id, "decision": final_decision})
                    else:
                        if idx in deferred_indices:
                            w_decision = "budget_deferred"
                            w_reason = "budget_exhausted"
                            w_detail = f"Hết ngân sách trong kỳ {target_period_key}; giữ trong backlog (không tự hết hạn)."
                        else:
                            w_decision = adm["decision"]
                            w_reason = adm["backlog_reason_code"] or "pending_business_decision"
                            w_detail = adm["reason_detail"]

                        conn.execute(
                            "UPDATE backlog_items SET revision_no = ?, period_key = ?, backlog_reason_code = ?, decision = ?, reason_detail = ?, updated_at = ? "
                            "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND case_id = ?",
                            (rev_no, target_period_key, w_reason, w_decision, w_detail, now, mode, tenant_id, company_id, cid),
                        )
                        still_waiting.append({"case_id": cid, "decision": w_decision, "backlog_reason_code": w_reason})

                if newly_reserved > 0:
                    conn.execute(
                        "UPDATE budget_periods SET reserved_count = reserved_count + ?, updated_at = ? "
                        "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND period_key = ?",
                        (newly_reserved, now, mode, tenant_id, company_id, target_period_key),
                    )

                final_period = conn.execute(
                    "SELECT budget_limit, reserved_count FROM budget_periods "
                    "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND period_key = ?",
                    (mode, tenant_id, company_id, target_period_key),
                ).fetchone()
                tx_response = {
                    "version": REPORT_VERSION,
                    "mode_namespace": mode,
                    "target_period_key": target_period_key,
                    "idempotent_replay": False,
                    "budget_status": {
                        "unit": "case",
                        "period_key": target_period_key,
                        "budget_limit": int(final_period["budget_limit"]),
                        "reserved_count": int(final_period["reserved_count"]),
                        "remaining": int(final_period["budget_limit"]) - int(final_period["reserved_count"]),
                    },
                    "promoted": promoted,
                    "still_waiting": still_waiting,
                    "_pending_outbox_ids": list(outbox_ids_to_dispatch),
                }
                conn.execute(
                    "INSERT INTO request_receipts "
                    "(mode_namespace, tenant_id, company_id, operation, idempotency_key, request_hash, response_json, created_at) "
                    "VALUES (?, ?, ?, 'reevaluate_backlog', ?, ?, ?, ?)",
                    (mode, tenant_id, company_id, idempotency_key, req_digest, canonical(tx_response).decode("utf-8"), now),
                )

        dispatch_res = self._dispatch_outbox_ids((mode, tenant_id, company_id, actor_id), outbox_ids_to_dispatch, external_sink=external_sink)
        tx_response["idempotent_replay"] = idempotent_replay
        tx_response["dispatch_result"] = dispatch_res
        tx_response.pop("_pending_outbox_ids", None)
        return tx_response

    def update_case_workflow(
        self,
        scope,
        *,
        mode: str = "active",
        case_id: str,
        new_status: str,
        resolution: str | None = None,
        reason: str = "",
        recheck=None,
    ) -> dict:
        """Transition canonical Case workflow status and resolution, preserving full close/reopen history."""
        tenant_id, company_id, actor_id = _require_scope(scope, recheck, "data.import")
        mode = _validate_mode(mode)
        if new_status not in WORKFLOW_STATUSES:
            fail(422, "INVALID_WORKFLOW_STATUS", f"Trạng thái vụ việc không hợp lệ: {new_status}.", f"Chọn trong {WORKFLOW_STATUSES}.")
        if new_status == "closed":
            if resolution not in ("confirmed_risk", "legitimate", "inconclusive"):
                fail(
                    422,
                    "RESOLUTION_REQUIRED_FOR_CLOSE",
                    "Đóng vụ việc bắt buộc có resolution (confirmed_risk, legitimate hoặc inconclusive).",
                    "Truyền case_resolution hợp lệ khi chuyển sang closed.",
                )
        elif resolution is not None:
            fail(
                422,
                "RESOLUTION_ONLY_WHEN_CLOSED",
                "Chỉ gắn case_resolution khi trạng thái là closed.",
                "Để resolution=null khi vụ việc đang mở.",
            )

        with self._write_tx() as conn:
            if recheck is not None and recheck() != scope:
                fail(409, "AUTH_CONTEXT_CHANGED", "Quyền đã thay đổi.", "Gửi lại với quyền hiện hành.")
            row = conn.execute(
                "SELECT * FROM cases WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND case_id = ?",
                (mode, tenant_id, company_id, case_id),
            ).fetchone()
            if row is None:
                fail(404, "CASE_NOT_FOUND", f"Không tìm thấy vụ việc {case_id}.", "Kiểm tra lại case_id và doanh nghiệp.")

            now = _utc_now()
            prev_status = row["case_workflow_status"]
            prev_res = row["case_resolution"]
            reopen_cnt = int(row["reopen_count"])
            hist = json.loads(row["workflow_history_json"])
            manual_hold = int(row["manual_waiting_hold"])

            if prev_status == "closed" and new_status != "closed":
                reopen_cnt += 1
                ev_type = "case_reopened_manual"
            elif new_status == "closed":
                ev_type = "case_closed"
            else:
                ev_type = "case_workflow_updated"

            hist.append(
                {
                    "event": ev_type,
                    "from_status": prev_status,
                    "from_resolution": prev_res,
                    "to_status": new_status,
                    "to_resolution": resolution,
                    "reason": str(reason or ""),
                    "actor_id": actor_id,
                    "at": now,
                }
            )

            if new_status == "closed":
                manual_hold = 0
                conn.execute(
                    "UPDATE backlog_items SET status = 'closed', updated_at = ? "
                    "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND case_id = ?",
                    (now, mode, tenant_id, company_id, case_id),
                )
            elif new_status == "waiting_evidence":
                manual_hold = 1
                conn.execute(
                    "INSERT INTO backlog_items "
                    "(mode_namespace, tenant_id, company_id, case_id, revision_no, period_key, backlog_reason_code, "
                    "decision, reason_detail, status, expires_at, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 'manual', 'waiting_external_evidence', 'need_evidence', ?, 'waiting', NULL, ?, ?) "
                    "ON CONFLICT(mode_namespace, tenant_id, company_id, case_id) DO UPDATE SET "
                    "backlog_reason_code='waiting_external_evidence', decision='need_evidence', "
                    "reason_detail=excluded.reason_detail, status='waiting', expires_at=NULL, updated_at=excluded.updated_at",
                    (mode, tenant_id, company_id, case_id, row["current_revision"], str(reason or "Chuyển chờ bổ sung chứng từ."), now, now),
                )
            else:
                manual_hold = 0

            conn.execute(
                "UPDATE cases SET case_workflow_status = ?, case_resolution = ?, reopen_count = ?, manual_waiting_hold = ?, "
                "workflow_history_json = ?, updated_at = ? "
                "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND case_id = ?",
                (new_status, resolution, reopen_cnt, manual_hold, canonical(hist).decode("utf-8"), now, mode, tenant_id, company_id, case_id),
            )
            self._insert_audit(
                conn,
                mode=mode,
                tenant_id=tenant_id,
                company_id=company_id,
                case_id=case_id,
                event_type=ev_type,
                actor_id=actor_id,
                detail={
                    "from_status": prev_status,
                    "from_resolution": prev_res,
                    "to_status": new_status,
                    "to_resolution": resolution,
                    "reason": str(reason or ""),
                },
                now=now,
            )

        return {
            "version": REPORT_VERSION,
            "mode_namespace": mode,
            "tenant_id": tenant_id,
            "company_id": company_id,
            "case_id": case_id,
            "case_workflow_status": new_status,
            "case_resolution": resolution,
            "reopen_count": reopen_cnt,
            "workflow_history": hist,
        }

    def get_queue_state(
        self,
        scope,
        *,
        mode: str = "active",
        period_key: str | None = None,
        redaction: str = "review",
        recheck=None,
    ) -> dict:
        tenant_id, company_id, _ = _require_scope(scope, recheck, "data.import")
        mode = _validate_mode(mode)
        with self._read_conn() as conn:
            if period_key:
                qrows = conn.execute(
                    "SELECT q.*, c.case_workflow_status, c.case_resolution, c.reopen_count "
                    "FROM queue_items q JOIN cases c "
                    "ON q.mode_namespace = c.mode_namespace AND q.tenant_id = c.tenant_id AND q.company_id = c.company_id AND q.case_id = c.case_id "
                    "WHERE q.mode_namespace = ? AND q.tenant_id = ? AND q.company_id = ? AND q.period_key = ? "
                    "ORDER BY q.created_at, q.case_id",
                    (mode, tenant_id, company_id, period_key),
                ).fetchall()
                brows = conn.execute(
                    "SELECT * FROM budget_periods WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND period_key = ?",
                    (mode, tenant_id, company_id, period_key),
                ).fetchall()
            else:
                qrows = conn.execute(
                    "SELECT q.*, c.case_workflow_status, c.case_resolution, c.reopen_count "
                    "FROM queue_items q JOIN cases c "
                    "ON q.mode_namespace = c.mode_namespace AND q.tenant_id = c.tenant_id AND q.company_id = c.company_id AND q.case_id = c.case_id "
                    "WHERE q.mode_namespace = ? AND q.tenant_id = ? AND q.company_id = ? "
                    "ORDER BY q.created_at, q.case_id",
                    (mode, tenant_id, company_id),
                ).fetchall()
                brows = conn.execute(
                    "SELECT * FROM budget_periods WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? ORDER BY period_key",
                    (mode, tenant_id, company_id),
                ).fetchall()
            outbox_pending = conn.execute(
                "SELECT COUNT(*) AS n FROM delivery_outbox WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND status != 'acked'",
                (mode, tenant_id, company_id),
            ).fetchone()["n"]

        items = []
        for r in qrows:
            payload = json.loads(r["payload_json"])
            items.append(
                {
                    "queue_item_id": r["queue_item_id"],
                    "queue_target": r["queue_target"],
                    "period_key": r["period_key"],
                    "case_id": r["case_id"],
                    "revision_no": r["revision_no"],
                    "admission_decision": r["admission_decision"],
                    "case_workflow_status": r["case_workflow_status"],
                    "case_resolution": r["case_resolution"],
                    "reopen_count": r["reopen_count"],
                    "material_fingerprint": r["material_fingerprint"] if redaction == "technical" else None,
                    "view_redacted_for_role": redaction,
                    "technical_fields_redacted": bool(redaction != "technical"),
                    "case": redact_case_for_view(payload["case"], redaction),
                    "created_at": r["created_at"],
                }
            )
        return {
            "version": REPORT_VERSION,
            "mode_namespace": mode,
            "queue_target": _queue_target(mode),
            "tenant_id": tenant_id,
            "company_id": company_id,
            "redaction": redaction,
            "budget_periods": [
                {
                    "period_key": b["period_key"],
                    "budget_limit": b["budget_limit"],
                    "reserved_count": b["reserved_count"],
                    "remaining": int(b["budget_limit"]) - int(b["reserved_count"]),
                }
                for b in brows
            ],
            "unacked_outbox_count": int(outbox_pending),
            "items": items,
        }

    def get_backlog(self, scope, *, mode: str = "active", redaction: str = "review", recheck=None) -> dict:
        tenant_id, company_id, _ = _require_scope(scope, recheck, "data.import")
        mode = _validate_mode(mode)
        with self._read_conn() as conn:
            rows = conn.execute(
                "SELECT b.*, c.case_workflow_status, c.case_resolution, c.reopen_count, c.latest_case_json "
                "FROM backlog_items b JOIN cases c "
                "ON b.mode_namespace = c.mode_namespace AND b.tenant_id = c.tenant_id AND b.company_id = c.company_id AND b.case_id = c.case_id "
                "WHERE b.mode_namespace = ? AND b.tenant_id = ? AND b.company_id = ? AND b.status = 'waiting' "
                "ORDER BY b.created_at, b.case_id",
                (mode, tenant_id, company_id),
            ).fetchall()
        items = []
        for r in rows:
            case_obj = redact_case_for_view(json.loads(r["latest_case_json"]), redaction)
            items.append(
                {
                    "case_id": r["case_id"],
                    "revision_no": r["revision_no"],
                    "period_key": r["period_key"],
                    "backlog_reason_code": r["backlog_reason_code"],
                    "decision": r["decision"],
                    "reason_detail": r["reason_detail"],
                    "status": r["status"],
                    "expires_at": r["expires_at"],
                    "case_workflow_status": r["case_workflow_status"],
                    "case_resolution": r["case_resolution"],
                    "view_redacted_for_role": redaction,
                    "technical_fields_redacted": bool(redaction != "technical"),
                    "case": case_obj,
                    "updated_at": r["updated_at"],
                }
            )
        return {
            "version": REPORT_VERSION,
            "mode_namespace": mode,
            "tenant_id": tenant_id,
            "company_id": company_id,
            "redaction": redaction,
            "auto_expire": False,
            "items": items,
        }

    def get_case_detail(self, scope, case_id: str, *, mode: str = "active", redaction: str = "review", recheck=None) -> dict:
        tenant_id, company_id, _ = _require_scope(scope, recheck, "data.import")
        mode = _validate_mode(mode)
        with self._read_conn() as conn:
            crow = conn.execute(
                "SELECT * FROM cases WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND case_id = ?",
                (mode, tenant_id, company_id, case_id),
            ).fetchone()
            if crow is None:
                fail(404, "CASE_NOT_FOUND", f"Không tìm thấy vụ việc {case_id}.", "Kiểm tra case_id hoặc doanh nghiệp.")
            revs = conn.execute(
                "SELECT revision_no, material_fingerprint, is_material_change, diff_json, snapshot_id, run_id, analysis_id, created_at "
                "FROM case_revisions WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND case_id = ? ORDER BY revision_no",
                (mode, tenant_id, company_id, case_id),
            ).fetchall()
            decs = conn.execute(
                "SELECT decision_id, period_key, revision_no, decision, backlog_reason_code, reason_detail, created_at "
                "FROM alert_decisions WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND case_id = ? ORDER BY created_at",
                (mode, tenant_id, company_id, case_id),
            ).fetchall()
            audits = conn.execute(
                "SELECT event_id, event_type, actor_id, detail_json, created_at "
                "FROM case_audit_events WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND case_id = ? ORDER BY created_at",
                (mode, tenant_id, company_id, case_id),
            ).fetchall()
            backlog = conn.execute(
                "SELECT backlog_reason_code, decision, reason_detail, status, expires_at FROM backlog_items "
                "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? AND case_id = ?",
                (mode, tenant_id, company_id, case_id),
            ).fetchone()

        return {
            "version": REPORT_VERSION,
            "mode_namespace": mode,
            "tenant_id": tenant_id,
            "company_id": company_id,
            "redaction": redaction,
            "case_id": case_id,
            "case_workflow_status": crow["case_workflow_status"],
            "case_resolution": crow["case_resolution"],
            "reopen_count": crow["reopen_count"],
            "current_revision": crow["current_revision"],
            "workflow_history": json.loads(crow["workflow_history_json"]),
            "view_redacted_for_role": redaction,
            "technical_fields_redacted": bool(redaction != "technical"),
            "case": redact_case_for_view(json.loads(crow["latest_case_json"]), redaction),
            "backlog": dict(backlog) if backlog else None,
            "revisions": [
                {
                    "revision_no": r["revision_no"],
                    "is_material_change": bool(r["is_material_change"]),
                    "diff": json.loads(r["diff_json"]),
                    "snapshot_id": r["snapshot_id"],
                    "run_id": r["run_id"],
                    "analysis_id": r["analysis_id"],
                    "material_fingerprint": r["material_fingerprint"] if redaction == "technical" else None,
                    "created_at": r["created_at"],
                }
                for r in revs
            ],
            "decisions": [dict(d) for d in decs],
            "audit_events": [
                {
                    "event_id": a["event_id"],
                    "event_type": a["event_type"],
                    "actor_id": a["actor_id"],
                    "detail": json.loads(a["detail_json"]),
                    "created_at": a["created_at"],
                }
                for a in audits
            ],
        }

    def get_backlog_metrics(
        self,
        scope,
        *,
        mode: str = "active",
        period_key: str | None = None,
        as_of_now: str | None = None,
        recheck=None,
    ) -> dict:
        """Measure opening/generated/resolved/closing backlog counts and waiting age hours without expiring items."""
        tenant_id, company_id, _ = _require_scope(scope, recheck, "data.import")
        mode = _validate_mode(mode)
        ref_now = datetime.fromisoformat(as_of_now.replace("Z", "+00:00")) if as_of_now else datetime.now(timezone.utc)
        if ref_now.tzinfo is None:
            ref_now = ref_now.replace(tzinfo=timezone.utc)

        with self._read_conn() as conn:
            brows = conn.execute(
                "SELECT b.case_id, b.revision_no, b.period_key, b.backlog_reason_code, b.decision, b.status, "
                "b.created_at, b.updated_at, c.case_workflow_status "
                "FROM backlog_items b JOIN cases c "
                "ON b.mode_namespace = c.mode_namespace AND b.tenant_id = c.tenant_id AND b.company_id = c.company_id AND b.case_id = c.case_id "
                "WHERE b.mode_namespace = ? AND b.tenant_id = ? AND b.company_id = ? ORDER BY b.created_at, b.case_id",
                (mode, tenant_id, company_id),
            ).fetchall()
            drows = conn.execute(
                "SELECT case_id, period_key, decision, backlog_reason_code, created_at FROM alert_decisions "
                "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? ORDER BY created_at, rowid",
                (mode, tenant_id, company_id),
            ).fetchall()
            arows = conn.execute(
                "SELECT case_id, event_type, detail_json, created_at FROM case_audit_events "
                "WHERE mode_namespace = ? AND tenant_id = ? AND company_id = ? "
                "AND event_type IN ('backlog_promoted', 'case_closed', 'queued_deferred') ORDER BY created_at, rowid",
                (mode, tenant_id, company_id),
            ).fetchall()

        first_backlog_period: dict[str, str] = {}
        generated_periods: dict[str, set[str]] = {}
        for d in drows:
            if d["backlog_reason_code"]:
                cid = d["case_id"]
                pk = d["period_key"]
                first_backlog_period.setdefault(cid, pk)
                generated_periods.setdefault(pk, set()).add(cid)

        resolved_periods: dict[str, set[str]] = {}
        for a in arows:
            if a["event_type"] == "backlog_promoted" and a["case_id"]:
                det = json.loads(a["detail_json"])
                pk = det.get("target_period_key") or ""
                if pk:
                    resolved_periods.setdefault(pk, set()).add(a["case_id"])
        for b in brows:
            if b["status"] in ("promoted", "closed"):
                resolved_periods.setdefault(b["period_key"], set()).add(b["case_id"])

        waiting_rows = [b for b in brows if b["status"] == "waiting"]
        ages: list[float] = []
        waiting_details = []
        by_reason: dict[str, int] = {}
        by_period: dict[str, int] = {}
        for b in waiting_rows:
            created = datetime.fromisoformat(str(b["created_at"]).replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_h = round(max(0.0, (ref_now - created).total_seconds() / 3600.0), 3)
            ages.append(age_h)
            rc = str(b["backlog_reason_code"])
            by_reason[rc] = by_reason.get(rc, 0) + 1
            pk = str(b["period_key"])
            by_period[pk] = by_period.get(pk, 0) + 1
            waiting_details.append(
                {
                    "case_id": b["case_id"],
                    "origin_period_key": first_backlog_period.get(b["case_id"], pk),
                    "current_period_key": pk,
                    "backlog_reason_code": rc,
                    "decision": b["decision"],
                    "age_hours": age_h,
                    "created_at": b["created_at"],
                }
            )

        sorted_ages = sorted(ages)
        if not sorted_ages:
            age_stats = {"min_hours": None, "median_hours": None, "max_hours": None}
        else:
            mid = len(sorted_ages) // 2
            med = sorted_ages[mid] if len(sorted_ages) % 2 == 1 else (sorted_ages[mid - 1] + sorted_ages[mid]) / 2.0
            age_stats = {
                "min_hours": sorted_ages[0],
                "median_hours": round(med, 3),
                "max_hours": sorted_ages[-1],
            }

        target = period_key or (waiting_rows[-1]["period_key"] if waiting_rows else None)
        if target:
            gen_ids = {
                cid
                for cid in generated_periods.get(target, set())
                if first_backlog_period.get(cid) == target
            }
            prior_resolved = {
                cid
                for pk, cids in resolved_periods.items()
                if pk < target
                for cid in cids
            }
            opening_ids = {
                cid
                for cid, fpk in first_backlog_period.items()
                if fpk < target and cid not in prior_resolved
            }
            resolved_ids = resolved_periods.get(target, set()) & (opening_ids | gen_ids)
        else:
            opening_ids = set()
            gen_ids = set(first_backlog_period.keys())
            resolved_ids = {b["case_id"] for b in brows if b["status"] in ("promoted", "closed")}

        return {
            "mode_namespace": mode,
            "tenant_id": tenant_id,
            "company_id": company_id,
            "period_key": target,
            "as_of_now": ref_now.isoformat(),
            "opening_backlog_count": len(opening_ids),
            "generated_in_period_count": len(gen_ids),
            "resolved_in_period_count": len(resolved_ids),
            "closing_backlog_count": len(waiting_rows),
            "age_hours": age_stats,
            "waiting_by_reason": by_reason,
            "waiting_by_period": by_period,
            "waiting_items": waiting_details,
            "auto_expire": False,
        }
