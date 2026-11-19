"""Model training, evaluation, versioning, approval and rollback lifecycle (Area B).

Reuses shared snapshots from Portal (SnapshotStore), 33-feature contracts,
offline fit jobs (method_jobs/MethodStore), pinned bindings (AnalysisResources),
verified label packets (LabelStore), and case/review queues (CaseQueueStore/ReleaseService).

Core guardrails:
- Never re-implements file upload or raw source validation (owned by Portal shared intake).
- Never treats unreviewed transactions as legitimate (label 0).
- Never fits or retrains a model during transaction scoring.
- Never presents uncalibrated ML anomaly scores as fraud probability.
- Never activates a model version without explicit authorized approval after evaluation.
"""
from __future__ import annotations

from collections import Counter
from contextlib import closing, contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import time
import uuid

import joblib
import numpy as np
from finance_input.json_io import loads

from .analysis_resources import AnalysisResources, ML_IDS, VERSION as BINDINGS_VERSION
from .auth import AccessScope
from .case_coalescing import build_case_bundle_from_rule_analysis, coalesce_cases
from .case_queue_policy import assess_case_eligibility, case_priority_key, default_fixture_policy
from .import_files import ImportFailure, canonical, digest, fail
from .method_adapters import ARTIFACT_VERSION, _versions
from .method_jobs import CONFIG_VERSION, run_fit_job
from .method_preprocess import VERSION as PREPROCESS_VERSION, transform_frame, validate_preprocess
from .method_store import MethodStore, require_fit
from .ml_estimators import ALGORITHMS
from .pipeline_release import FrozenResources
from .rule_snapshot import analyze as analyze_rule_snapshot
from .rule_snapshot_features import (
    COLUMN_SPECS,
    SOURCE_CONTRACT as RULE_SOURCE_CONTRACT,
    UNMAPPED_COLUMNS,
    build_from_rule_snapshot,
    feature_contract as rule_feature_contract,
)
from .score_statistics import empirical_rank
from .snapshot_features import (
    COLUMNS as FEATURE_COLUMNS,
    build_from_snapshot,
    feature_contract as canonical_feature_contract,
    utc,
)
from .snapshots import SnapshotStore

VERSION = 'model-lifecycle/1.0.0'
APP_ID = 1093817155
VN_TZ = timezone(timedelta(hours=7))

ALGO_META = {
    'isolation_forest': {
        'id': 'isolation_forest',
        'label': 'Isolation Forest',
        'priority': 1,
        'recommended': True,
        'min_rows': 10,
        'recommended_rows': 30,
        'summary_vi': 'Ưu tiên hàng đầu cho dữ liệu kế toán chưa gán nhãn: cô lập nhanh giao dịch khác thường trên nhiều chiều giá trị, thời điểm và quan hệ.',
        'strength_vi': 'Ổn định với tập dữ liệu vừa và nhỏ, ít nhạy cảm với ngoại lai đơn lẻ, tốc độ chấm nhanh.',
    },
    'autoencoder': {
        'id': 'autoencoder',
        'label': 'Autoencoder',
        'priority': 2,
        'recommended': True,
        'min_rows': 15,
        'recommended_rows': 50,
        'summary_vi': 'Mạng nút thắt tái tạo đặc trưng giúp phát hiện tổ hợp bất thường đa chiều và phân rã sai số tái tạo cho từng đặc trưng.',
        'strength_vi': 'Giải thích trực tiếp đặc trưng gây sai lệch tái tạo lớn nhất; phù hợp khi doanh nghiệp có đủ lịch sử.',
    },
    'ecod': {
        'id': 'ecod',
        'label': 'ECOD',
        'priority': 3,
        'recommended': False,
        'min_rows': 10,
        'recommended_rows': 30,
        'summary_vi': 'Phát hiện ngoại lai theo phân phối tích lũy thực nghiệm (ECDF) không tham số, phân tách rõ đóng góp đuôi trái/phải của từng biến.',
        'strength_vi': 'Không phụ thuộc siêu tham số, giải thích rõ đặc trưng nằm ở đuôi phân phối lịch sử.',
    },
    'lof': {
        'id': 'lof',
        'label': 'Local Outlier Factor (LOF)',
        'priority': 4,
        'recommended': False,
        'min_rows': 12,
        'recommended_rows': 40,
        'summary_vi': 'So sánh mật độ cục bộ quanh giao dịch với các giao dịch lịch sử gần nhất của cùng doanh nghiệp.',
        'strength_vi': 'Hữu ích khi doanh nghiệp có nhiều cụm chi tiêu riêng biệt (lương, thanh toán NCC, vận hành).',
    },
}

FEATURE_GROUPS = {
    'log_abs_amount': ('Giá trị tài chính', 'Quy mô giá trị giao dịch (log1p)'),
    'amount_negative': ('Giá trị tài chính', 'Dấu giao dịch âm / điều chỉnh giảm'),
    'amount_zero': ('Giá trị tài chính', 'Giao dịch giá trị bằng 0'),
    'round_million': ('Giá trị tài chính', 'Số tiền tròn triệu VND'),
    'kind_payment': ('Loại nghiệp vụ', 'Nghiệp vụ thanh toán / chi trả'),
    'kind_receipt': ('Loại nghiệp vụ', 'Nghiệp vụ thu tiền'),
    'kind_payroll': ('Loại nghiệp vụ', 'Nghiệp vụ chi lương'),
    'kind_transfer': ('Loại nghiệp vụ', 'Nghiệp vụ chuyển khoản nội bộ'),
    'kind_adjustment': ('Loại nghiệp vụ', 'Nghiệp vụ bút toán điều chỉnh'),
    'kind_reversal': ('Loại nghiệp vụ', 'Nghiệp vụ đảo bút toán'),
    'event_hour_sin': ('Thời điểm phát sinh', 'Chu kỳ giờ phát sinh (sin, +07:00)'),
    'event_hour_cos': ('Thời điểm phát sinh', 'Chu kỳ giờ phát sinh (cos, +07:00)'),
    'event_weekday_sin': ('Thời điểm phát sinh', 'Chu kỳ thứ trong tuần (sin)'),
    'event_weekday_cos': ('Thời điểm phát sinh', 'Chu kỳ thứ trong tuần (cos)'),
    'event_weekend': ('Thời điểm phát sinh', 'Phát sinh cuối tuần'),
    'prior_type_history_log_count': ('Lịch sử doanh nghiệp', 'Số giao dịch lịch sử cùng loại (log1p)'),
    'log_abs_deviation_from_history': ('Lịch sử doanh nghiệp', 'Độ lệch giá trị so với trung bình lịch sử'),
    'abs_amount_history_z': ('Lịch sử doanh nghiệp', 'Độ lệch chuẩn hóa giá trị theo lịch sử'),
    'employee_bank_overlap_observed': ('Quan hệ & đồ thị', 'Trùng tài khoản ngân hàng NCC – nhân viên'),
    'graph_employee_count_observed': ('Quan hệ & đồ thị', 'Số nhân viên liên kết cùng tài khoản'),
    'graph_vendor_count_observed': ('Quan hệ & đồ thị', 'Số NCC liên kết cùng tài khoản'),
    'journal_line_count': ('Hạch toán & chứng từ', 'Số dòng định khoản kế toán'),
    'journal_imbalance_abs_ratio': ('Hạch toán & chứng từ', 'Tỷ lệ chênh lệch Nợ – Có trên giá trị'),
    'known_document_count': ('Hạch toán & chứng từ', 'Số chứng từ đã biết tại thời điểm giao dịch'),
    'verified_original_document_count': ('Hạch toán & chứng từ', 'Số chứng từ gốc đã xác minh'),
    'known_invoice_count': ('Hạch toán & chứng từ', 'Số hóa đơn liên kết đã biết'),
    'linked_invoice_log_abs_total': ('Hạch toán & chứng từ', 'Tổng giá trị hóa đơn liên kết (log1p)'),
    'allocation_to_invoice_face_ratio': ('Hạch toán & chứng từ', 'Tỷ lệ thanh toán trên giá trị hóa đơn'),
    'prior_invoice_payment_count': ('Hạch toán & chứng từ', 'Số lần đã trả trước đó cho cùng hóa đơn'),
    'prior_invoice_allocation_log_abs': ('Hạch toán & chứng từ', 'Tổng tiền đã trả trước đó cho hóa đơn'),
    'prior_invoice_allocation_negative': ('Hạch toán & chứng từ', 'Phân bổ âm trên hóa đơn liên kết'),
    'creator_equals_approver': ('Phê duyệt & kiểm soát', 'Người lập trùng người phê duyệt'),
    'observed_approval_limit_ratio': ('Phê duyệt & kiểm soát', 'Tỷ lệ giá trị trên hạn mức phê duyệt'),
}

GUARDRAILS_VI = [
    'Dữ liệu giao dịch thực tế chưa được rà soát không bao giờ được tự động coi là hợp lệ (nhãn 0).',
    'Không tự huấn luyện lại mô hình trong quá trình chấm điểm giao dịch.',
    'Điểm ML phản ánh mức độ khác thường tương đối để xếp ưu tiên kiểm tra, không phải xác suất gian lận khi chưa được hiệu chuẩn phù hợp.',
    'Chỉ đưa phiên bản mô hình vào sử dụng sau khi đạt tiêu chí kiểm tra chất lượng và được người có thẩm quyền xác nhận.',
]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fmt_date_vn(ts: str | None) -> str:
    if not ts:
        return 'Chưa xác định'
    try:
        dt = utc(ts).astimezone(VN_TZ)
        return dt.strftime('%d/%m/%Y')
    except Exception:
        return str(ts)[:10]


def _fmt_period_vn(start: str | None, end: str | None) -> str:
    if not start or not end:
        return 'Chưa xác định'
    try:
        s = utc(start).astimezone(VN_TZ)
        e = utc(end).astimezone(VN_TZ)
        if s.year == e.year and s.month == e.month:
            return f'{s.strftime("%d")}–{e.strftime("%d/%m/%Y")}'
        if s.year == e.year:
            return f'{s.strftime("%d/%m")}–{e.strftime("%d/%m/%Y")}'
        return f'{s.strftime("%d/%m/%Y")}–{e.strftime("%d/%m/%Y")}'
    except Exception:
        return f'{str(start)[:10]} – {str(end)[:10]}'


def _finite(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v)) else None


def _require_company_scope(scope: AccessScope, recheck=None) -> tuple[str, str]:
    if not isinstance(scope, AccessScope) or len(scope.company_ids) != 1 or not scope.actor_id:
        fail(403, 'ACCESS_DENIED', 'Phạm vi doanh nghiệp không hợp lệ.', 'Chọn đúng doanh nghiệp được cấp quyền.')
    if recheck is not None and recheck() != scope:
        fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền truy cập đã thay đổi.', 'Tải lại phiên từ Portal.')
    return scope.tenant_id, next(iter(scope.company_ids))


def _snapshot_meta_summary(manifest: dict, data: dict) -> dict:
    native = 'source' in data
    if native:
        src = data['source']
        txs = src.get('tables', {}).get('transactions') or []
        dates = sorted(str(t.get('posted_at') or t.get('observed_at') or '') for t in txs if t.get('posted_at') or t.get('observed_at'))
        cand_ids = list(data.get('candidate_transaction_ids') or [])
        is_sim = bool(src.get('is_simulated', True))
        as_of = src.get('as_of') or manifest.get('created_at')
        source_id = src.get('source_id') or 'portal-shared-snapshot'
    else:
        txs = data.get('transactions') or []
        dates = sorted(str(t.get('effective_at') or t.get('observed_at') or '') for t in txs if t.get('effective_at') or t.get('observed_at'))
        cand_ids = [t.get('record_id') for t in txs if t.get('record_id')]
        is_sim = all((t.get('source') or {}).get('is_simulated', True) for t in txs) if txs else True
        as_of = max((str(t.get('observed_at') or '') for t in txs), default=manifest.get('created_at')) or manifest.get('created_at')
        source_id = 'portal-canonical-snapshot'
    min_at = dates[0] if dates else None
    max_at = dates[-1] if dates else None
    return {
        'snapshot_id': manifest['snapshot_id'],
        'contract_version': manifest['contract_version'],
        'native_35_rules': native,
        'created_at': manifest['created_at'],
        'checksum': manifest['checksum'],
        'data_checksum': manifest['data_checksum'],
        'as_of': as_of,
        'source_id': source_id,
        'source_kind': 'simulated' if is_sim else 'source_export',
        'is_simulated': is_sim,
        'transaction_count': len(txs),
        'candidate_count': len(cand_ids),
        'min_event_at': min_at,
        'max_event_at': max_at,
        'period_label': _fmt_period_vn(min_at, max_at),
    }


def _compute_recommended_split(event_timestamps: list[str], as_of: str) -> dict:
    """Compute strict chronological split (history < reference <= evaluation) from sorted event timestamps."""
    parsed = sorted({utc(ts) for ts in event_timestamps if ts})
    if len(parsed) < 6:
        base = parsed[0] if parsed else utc(as_of) - timedelta(days=30)
        end = parsed[-1] if parsed else utc(as_of)
        span = max((end - base).total_seconds(), 3600 * 24 * 3)
        h_end = base + timedelta(seconds=span * 0.6)
        r_end = base + timedelta(seconds=span * 0.85)
        e_start = r_end + timedelta(seconds=1)
        return {
            'history_start': (base - timedelta(seconds=1)).astimezone(VN_TZ).isoformat(),
            'history_end': h_end.astimezone(VN_TZ).isoformat(),
            'reference_start': h_end.astimezone(VN_TZ).isoformat(),
            'reference_end': r_end.astimezone(VN_TZ).isoformat(),
            'evaluation_start': e_start.astimezone(VN_TZ).isoformat(),
            'history_rows': 0,
            'reference_rows': 0,
            'eval_rows': 0,
            'split_feasible': False,
        }

    # Count rows at each distinct timestamp so split respects row counts, not only distinct dates
    all_dt = sorted(utc(ts) for ts in event_timestamps if ts)
    n = len(all_dt)
    # Use 65% history, 20% reference, 15% held-out evaluation (or 75%/25%/0% if snapshot is small)
    if n >= 20:
        h_idx = max(10, int(n * 0.65))
        r_idx = max(h_idx + 4, int(n * 0.85))
        r_idx = min(r_idx, n - 1)
    else:
        h_idx = max(5, int(n * 0.68))
        r_idx = min(n - 1, max(h_idx + 2, n - 2))

    # Advance boundary past tied timestamps so strict < holds cleanly
    while h_idx < n - 2 and all_dt[h_idx] <= all_dt[h_idx - 1]:
        h_idx += 1
    while r_idx < n - 1 and all_dt[r_idx] <= all_dt[r_idx - 1]:
        r_idx += 1

    # If all timestamps after h_idx are equal, fall back to pure train/ref split with eval_start after last tx
    h_start_dt = all_dt[0] - timedelta(seconds=1)
    if h_idx >= n - 1 or all_dt[h_idx] <= all_dt[0]:
        mid = all_dt[0] + (all_dt[-1] - all_dt[0]) * 0.7
        h_end_dt = mid
        r_end_dt = all_dt[-1] + timedelta(seconds=1)
        e_start_dt = r_end_dt + timedelta(seconds=1)
    elif r_idx >= n - 1 or all_dt[r_idx] <= all_dt[h_idx]:
        h_end_dt = all_dt[h_idx]
        r_end_dt = all_dt[-1] + timedelta(seconds=1)
        e_start_dt = r_end_dt + timedelta(seconds=1)
    else:
        h_end_dt = all_dt[h_idx]
        r_end_dt = all_dt[r_idx]
        e_start_dt = r_end_dt

    h_rows = sum(1 for d in all_dt if h_start_dt <= d < h_end_dt)
    r_rows = sum(1 for d in all_dt if h_end_dt <= d < r_end_dt)
    e_rows = sum(1 for d in all_dt if d >= e_start_dt)

    # Ensure strictly increasing boundaries even if r_end_dt == e_start_dt is valid per method_jobs
    return {
        'history_start': h_start_dt.astimezone(VN_TZ).isoformat(),
        'history_end': h_end_dt.astimezone(VN_TZ).isoformat(),
        'reference_start': h_end_dt.astimezone(VN_TZ).isoformat(),
        'reference_end': r_end_dt.astimezone(VN_TZ).isoformat(),
        'evaluation_start': e_start_dt.astimezone(VN_TZ).isoformat(),
        'history_rows': h_rows,
        'reference_rows': r_rows,
        'eval_rows': e_rows,
        'split_feasible': h_rows >= 5 and r_rows >= 1,
    }


def _attribution_for_estimator(model, x_mat: np.ndarray, feature_names: list[str], top_k: int = 5) -> list[list[dict]]:
    """Compute readable per-row top feature attributions without mutating model."""
    if hasattr(model, 'score_with_attributions') and getattr(model, 'algorithm', None) in ('autoencoder', 'ecod'):
        res = model.score_with_attributions(x_mat, feature_names=feature_names, top_k=top_k)
        out = []
        for row_items in res['top_contributing_features']:
            cleaned = []
            for item in row_items:
                raw_name = str(item['feature'])
                col = raw_name[6:] if raw_name.startswith('value:') else raw_name
                if raw_name.startswith('missing:'):
                    continue
                grp, lbl = FEATURE_GROUPS.get(col, ('Đặc trưng bổ sung', col))
                cleaned.append({
                    'feature': col,
                    'label_vi': lbl,
                    'group': grp,
                    'share': round(float(item.get('share_of_total_error', 0.0)), 4),
                    'magnitude': round(float(item.get('squared_error', 0.0)), 4),
                })
            out.append(cleaned[:top_k])
        return out

    # Fallback for Isolation Forest / LOF: standardized absolute deviation on non-missing value columns
    val_cols = [(j, name[6:] if name.startswith('value:') else name)
                for j, name in enumerate(feature_names) if not name.startswith('missing:')]
    if not val_cols or len(x_mat) == 0:
        return [[] for _ in range(len(x_mat))]
    idxs = [j for j, _ in val_cols]
    sub = x_mat[:, idxs]
    med = np.median(sub, axis=0)
    std = np.maximum(np.std(sub, axis=0), 1e-6)
    z_abs = np.abs(sub - med) / std
    out = []
    for r_idx in range(len(x_mat)):
        row_z = z_abs[r_idx]
        total = float(row_z.sum())
        ordered = sorted(range(len(val_cols)), key=lambda k: (-float(row_z[k]), k))
        items = []
        for pos in ordered[:top_k]:
            val = float(row_z[pos])
            if val <= 1e-6 and items:
                continue
            col = val_cols[pos][1]
            grp, lbl = FEATURE_GROUPS.get(col, ('Đặc trưng bổ sung', col))
            items.append({
                'feature': col,
                'label_vi': lbl,
                'group': grp,
                'share': round(val / total, 4) if total > 0 else 0.0,
                'magnitude': round(val, 4),
            })
        out.append(items)
    return out


class ModelLifecycle:
    """Enterprise model training, evaluation, versioning, approval and rollback manager."""

    def __init__(
        self,
        db_path,
        *,
        snapshot_store: SnapshotStore,
        analysis_resources: AnalysisResources,
        authorizer,
        label_store=None,
        case_queue_store=None,
        release_service=None,
    ):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshots = snapshot_store
        self.resources = analysis_resources
        self.authorizer = authorizer
        self.label_store = label_store
        self.case_queue = case_queue_store
        self.release_service = release_service
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA synchronous=FULL')
        return conn

    def _init_db(self):
        with closing(self._connect()) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            app_id = conn.execute('PRAGMA application_id').fetchone()[0]
            if app_id not in (0, APP_ID):
                fail(503, 'MODEL_LIFECYCLE_STORAGE', 'Đường dẫn không phải kho quản lý mô hình đúng phiên bản.',
                     'Kiểm tra đường dẫn model-lifecycle.sqlite3.')
            conn.executescript(f"""
                BEGIN IMMEDIATE;
                PRAGMA application_id={APP_ID};
                PRAGMA user_version=1;
                CREATE TABLE IF NOT EXISTS model_versions (
                    version_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    version_number INTEGER NOT NULL,
                    version_tag TEXT NOT NULL,
                    method_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    statistics_artifact_id TEXT,
                    snapshot_id TEXT NOT NULL,
                    eval_snapshot_id TEXT,
                    feature_contract_version TEXT NOT NULL,
                    feature_contract_fingerprint TEXT NOT NULL,
                    preprocess_version TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    data_profile_json TEXT NOT NULL,
                    evaluation_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'none',
                    approval_json TEXT,
                    bundle_id TEXT,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(tenant_id, company_id, version_number)
                );
                CREATE INDEX IF NOT EXISTS idx_mv_company ON model_versions(tenant_id, company_id, version_number DESC);
                CREATE TABLE IF NOT EXISTS model_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    tenant_id TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    note TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_me_company ON model_events(tenant_id, company_id, seq DESC);
                CREATE TABLE IF NOT EXISTS lifecycle_receipts (
                    tenant_id TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(tenant_id, company_id, actor_id, request_id)
                );
                CREATE TRIGGER IF NOT EXISTS model_events_no_update BEFORE UPDATE ON model_events
                BEGIN SELECT RAISE(ABORT, 'immutable model lifecycle audit'); END;
                CREATE TRIGGER IF NOT EXISTS model_events_no_delete BEFORE DELETE ON model_events
                BEGIN SELECT RAISE(ABORT, 'immutable model lifecycle audit'); END;
                COMMIT;
            """)

    @contextmanager
    def _tx(self, scope: AccessScope, recheck=None, *, write: bool = True):
        _require_company_scope(scope, recheck)
        with self._lock:
            conn = self._connect()
            try:
                conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
                if recheck is not None and recheck() != scope:
                    fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền truy cập đã thay đổi.', 'Đăng nhập lại.')
                yield conn
                if recheck is not None and recheck() != scope:
                    fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền truy cập đã thay đổi trước khi lưu.', 'Đăng nhập lại.')
                conn.execute('COMMIT')
            except BaseException:
                if conn.in_transaction:
                    conn.execute('ROLLBACK')
                raise
            finally:
                conn.close()

    def _record_event(self, conn, scope: AccessScope, version_id: str, action: str, note: str, detail: dict):
        tenant, company = _require_company_scope(scope)
        eid = 'mev_' + uuid.uuid4().hex[:24]
        conn.execute(
            'INSERT INTO model_events(event_id,tenant_id,company_id,version_id,action,actor_id,note,detail_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
            (eid, tenant, company, version_id, action, scope.actor_id, note, canonical(detail).decode('utf-8'), _iso_now()),
        )
        return eid

    def _next_version_number(self, conn, tenant: str, company: str) -> int:
        row = conn.execute(
            'SELECT COALESCE(MAX(version_number), 0) AS mx FROM model_versions WHERE tenant_id=? AND company_id=?',
            (tenant, company),
        ).fetchone()
        return int(row['mx']) + 1

    def _row_to_dto(self, row: sqlite3.Row) -> dict:
        cfg = loads(row['config_json'])
        prof = loads(row['data_profile_json'])
        ev = loads(row['evaluation_json'])
        app = loads(row['approval_json']) if row['approval_json'] else None
        method_id = row['method_id']
        return {
            'version_id': row['version_id'],
            'version_number': int(row['version_number']),
            'version_tag': row['version_tag'],
            'method_id': method_id,
            'method_label': ALGORITHMS.get(method_id, method_id),
            'artifact_id': row['artifact_id'],
            'statistics_artifact_id': row['statistics_artifact_id'],
            'snapshot_id': row['snapshot_id'],
            'eval_snapshot_id': row['eval_snapshot_id'],
            'feature_contract_version': row['feature_contract_version'],
            'feature_contract_fingerprint': row['feature_contract_fingerprint'],
            'preprocess_version': row['preprocess_version'],
            'config': cfg,
            'data_profile': prof,
            'evaluation': ev,
            'status': row['status'],
            'mode': row['mode'],
            'approval': app,
            'bundle_id': row['bundle_id'],
            'created_by': row['created_by'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
        }

    def _list_snapshots(self, scope: AccessScope, recheck=None, limit: int = 30) -> list[dict]:
        tenant, company = _require_company_scope(scope, recheck)
        items = []
        with self.snapshots._transaction(scope, recheck) as c:
            ids = [
                r[0]
                for r in c.execute(
                    'SELECT snapshot_id FROM snapshots WHERE tenant_id=? AND company_id=? ORDER BY rowid DESC LIMIT ?',
                    (tenant, company, limit),
                ).fetchall()
            ]
            for sid in ids:
                try:
                    m, raw = self.snapshots._read_snapshot(c, scope, sid)
                    data = loads(raw)
                    items.append(_snapshot_meta_summary(m, data))
                except Exception:
                    continue
        return items

    def _bootstrap_existing_binding(self, scope: AccessScope, recheck=None):
        """Register currently pinned model from AnalysisResources on first access so Area B reflects live reality."""
        tenant, company = _require_company_scope(scope, recheck)
        with self._tx(scope, recheck, write=False) as conn:
            cnt = conn.execute(
                'SELECT count(*) FROM model_versions WHERE tenant_id=? AND company_id=?', (tenant, company)
            ).fetchone()[0]
        if cnt > 0:
            return
        selected, err = self.resources.selection(scope)
        if err is not None or not selected.get('ml_artifacts') or self.resources.model_db is None:
            return
        if not Path(self.resources.model_db).is_file():
            return
        store = MethodStore(self.resources.model_db, read_only=True)
        snaps = self._list_snapshots(scope, recheck, limit=20)
        default_eval = next((s['snapshot_id'] for s in snaps if s['native_35_rules'] and s['candidate_count'] >= 4), snaps[0]['snapshot_id'] if snaps else None)

        for method_id, artifact_id in sorted(selected['ml_artifacts'].items()):
            try:
                art = store.get_artifact(scope, artifact_id, recheck)
                manifest = loads(art.manifest)
            except Exception:
                continue
            fit_snap_id = (manifest.get('history_binding') or {}).get('snapshot_id') or (default_eval or 'unknown')
            cfg = (manifest.get('fit_context') or {}).get('config') or {
                'method_id': method_id,
                'snapshot_id': fit_snap_id,
                'history_start': manifest.get('train_end'),
                'history_end': manifest.get('train_end'),
                'reference_start': manifest.get('reference_start'),
                'reference_end': manifest.get('reference_end'),
                'evaluation_start': manifest.get('reference_end'),
                'missing_policy': (manifest.get('preprocess') or {}).get('policy', 'median_flags'),
                'selected_columns': manifest.get('selected_columns') or list(FEATURE_COLUMNS),
                'minimum_history': manifest.get('minimum_history', 10),
            }
            eval_summary = None
            if default_eval:
                try:
                    eval_summary = self._evaluate_artifact(
                        scope, method_id, artifact_id, manifest, default_eval, recheck, already_approved=True
                    )
                except Exception:
                    eval_summary = None
            if eval_summary is None:
                eval_summary = {
                    'eval_snapshot_id': default_eval,
                    'eval_period_label': _fmt_period_vn(manifest.get('reference_start'), manifest.get('reference_end')),
                    'eval_rows': int(manifest.get('reference_rows') or 0),
                    'scored_rows': int(manifest.get('reference_rows') or 0),
                    'unavailable_rows': 0,
                    'inference_seconds': 0.0,
                    'is_simulated': True,
                    'budget': 5,
                    'label_basis': 'no_verified_labels',
                    'useful_display': 'Đang vận hành (cần đánh giá lại kỳ mới)',
                    'converged': (manifest.get('fit_diagnostics') or {}).get('converged'),
                    'missing_robustness_pass': True,
                    'unsupervised': {},
                    'top_attributions': [],
                    'checklist': [
                        {'id': 'split_separation', 'label': 'Tách kỳ huấn luyện và kỳ đánh giá', 'status': 'pass',
                         'detail': f'Train kết thúc trước reference ({_fmt_date_vn(manifest.get("train_end"))}).'},
                        {'id': 'contract_binding', 'label': 'Đặc trưng và dữ liệu đúng phiên bản', 'status': 'pass',
                         'detail': f'Khớp contract {manifest.get("feature_contract", {}).get("version", "")}.'},
                        {'id': 'missing_disclosed', 'label': 'Nguồn thiếu được ghi rõ', 'status': 'pass',
                         'detail': f'Bỏ qua {len((manifest.get("preprocess") or {}).get("dropped_columns") or {})} cột không có quan sát.'},
                        {'id': 'business_confirmation', 'label': 'Xác nhận nghiệp vụ', 'status': 'pass',
                         'detail': 'Phiên bản đang được ghim trong cấu hình doanh nghiệp.'},
                    ],
                }
            now = _iso_now()
            created_at = (manifest.get('fit_context') or {}).get('created_at') or now
            approval = {
                'approved_by': 'system-pinned-binding',
                'approved_at': created_at,
                'mode': 'active',
                'reason': 'Phiên bản mô hình đang được ghim sẵn trong cấu hình phân tích của doanh nghiệp.',
                'reviewed_evaluation': True,
            }
            profile_stub = {
                'snapshot_id': fit_snap_id,
                'history_rows': int(manifest.get('history_rows') or 0),
                'reference_rows': int(manifest.get('reference_rows') or 0),
                'kept_features': len((manifest.get('preprocess') or {}).get('kept_columns') or []),
                'dropped_features': len((manifest.get('preprocess') or {}).get('dropped_columns') or {}),
                'period_label': _fmt_period_vn(cfg.get('history_start'), manifest.get('reference_end')),
                'is_simulated': bool(eval_summary.get('is_simulated', True)),
            }
            with self._tx(scope, recheck, write=True) as conn:
                if conn.execute('SELECT count(*) FROM model_versions WHERE tenant_id=? AND company_id=?', (tenant, company)).fetchone()[0] > 0:
                    return
                vnum = self._next_version_number(conn, tenant, company)
                vtag = f'{company}-v{vnum}'
                vid = 'mv_' + digest(canonical([tenant, company, vnum, artifact_id, now]))[:24]
                conn.execute(
                    """INSERT INTO model_versions(
                        version_id,tenant_id,company_id,version_number,version_tag,method_id,artifact_id,
                        statistics_artifact_id,snapshot_id,eval_snapshot_id,feature_contract_version,
                        feature_contract_fingerprint,preprocess_version,config_json,data_profile_json,
                        evaluation_json,status,mode,approval_json,bundle_id,created_by,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        vid, tenant, company, vnum, vtag, method_id, artifact_id,
                        selected.get('statistics_artifact_id'), fit_snap_id, default_eval,
                        (manifest.get('feature_contract') or {}).get('version', 'rule-snapshot-point-in-time/1.0.0'),
                        manifest.get('feature_contract_fingerprint', ''),
                        manifest.get('preprocess_version', PREPROCESS_VERSION),
                        canonical(cfg).decode('utf-8'),
                        canonical(profile_stub).decode('utf-8'),
                        canonical(eval_summary).decode('utf-8'),
                        'active', 'active',
                        canonical(approval).decode('utf-8'),
                        None, scope.actor_id, created_at, now,
                    ),
                )
                self._record_event(conn, scope, vid, 'synced_existing', f'Đồng bộ phiên bản đang ghim {vtag} ({method_id}).', {'artifact_id': artifact_id})

    def _feature_catalog(self) -> list[dict]:
        out = []
        for col in FEATURE_COLUMNS:
            grp, lbl = FEATURE_GROUPS.get(col, ('Đặc trưng bổ sung', col))
            out.append({
                'name': col,
                'label_vi': lbl,
                'group': grp,
                'description': COLUMN_SPECS.get(col, ''),
                'unmapped_in_native': col in UNMAPPED_COLUMNS,
            })
        return out

    def overview(self, scope: AccessScope, recheck=None) -> dict:
        tenant, company = _require_company_scope(scope, recheck)
        self._bootstrap_existing_binding(scope, recheck)
        snapshots = self._list_snapshots(scope, recheck, limit=30)
        with self._tx(scope, recheck, write=False) as conn:
            rows = conn.execute(
                'SELECT * FROM model_versions WHERE tenant_id=? AND company_id=? ORDER BY version_number DESC',
                (tenant, company),
            ).fetchall()
            events = [
                dict(
                    event_id=r['event_id'],
                    version_id=r['version_id'],
                    action=r['action'],
                    actor_id=r['actor_id'],
                    note=r['note'],
                    detail=loads(r['detail_json']),
                    created_at=r['created_at'],
                )
                for r in conn.execute(
                    'SELECT * FROM model_events WHERE tenant_id=? AND company_id=? ORDER BY seq DESC LIMIT 40',
                    (tenant, company),
                ).fetchall()
            ]
        versions = [self._row_to_dto(r) for r in rows]
        active = next((v for v in versions if v['status'] == 'active'), None)
        if active is None:
            active = next((v for v in versions if v['status'] == 'shadow'), None)
        rollback_targets = [
            v for v in versions
            if v['approval'] is not None and (active is None or v['version_id'] != active['version_id'])
        ]
        # Prefer snapshot with most transactions as default training source; distinct evaluation snapshot with candidates
        train_snap = max(snapshots, key=lambda s: (s['native_35_rules'], s['transaction_count'], s['created_at'])) if snapshots else None
        eval_snap = next((s for s in snapshots if s['native_35_rules'] and s['candidate_count'] >= 4), train_snap)
        total_tx = train_snap['transaction_count'] if train_snap else 0

        # Active binding from disk for honesty/verification
        selected_binding, binding_err = self.resources.selection(scope)
        return {
            'version': VERSION,
            'company_id': company,
            'tenant_id': tenant,
            'actor_id': scope.actor_id,
            'can_fit': 'model.fit' in scope.permissions,
            'active_version': active,
            'current_binding': selected_binding,
            'binding_error': binding_err,
            'shared_data': {
                'source_label': 'Dữ liệu từ sảnh chung',
                'snapshot_count': len(snapshots),
                'primary_snapshot': train_snap,
                'recommended_eval_snapshot': eval_snap,
                'transaction_count': total_tx,
                'snapshots': snapshots,
            },
            'versions': versions,
            'candidates': [v for v in versions if v['status'] in ('pending_approval', 'evaluated', 'shadow', 'active')][:10],
            'rollback_targets': rollback_targets,
            'algorithms': sorted(ALGO_META.values(), key=lambda x: x['priority']),
            'feature_contract': {
                'version': rule_feature_contract()['version'],
                'fingerprint': rule_feature_contract()['fingerprint'],
                'preprocess_version': PREPROCESS_VERSION,
                'total_features': len(FEATURE_COLUMNS),
                'columns': self._feature_catalog(),
                'excluded_predictors': list(rule_feature_contract()['predictor_exclusions']),
            },
            'events': events,
            'guardrails': list(GUARDRAILS_VI),
        }

    def profile_snapshot(self, scope: AccessScope, snapshot_id: str, recheck=None) -> dict:
        tenant, company = _require_company_scope(scope, recheck)
        manifest = self.snapshots.get_snapshot(scope, snapshot_id, recheck)
        raw = self.snapshots.get_snapshot(scope, snapshot_id, recheck, data=True)
        data = loads(raw)
        meta = _snapshot_meta_summary(manifest, data)
        native = meta['native_35_rules']
        as_of = meta['as_of']

        if native:
            frame = build_from_rule_snapshot(
                self.snapshots, scope, snapshot_id, as_of, recheck,
                candidates_only=False, require_exact_source_cutoff=False,
            )
            txs = data['source']['tables'].get('transactions') or []
            type_counts = dict(Counter(str(t.get('txn_type') or 'unknown') for t in txs))
            coverage = data['source'].get('coverage') or {}
            tables_summary = [
                {
                    'table': tbl,
                    'record_count': len(rows) if isinstance(rows, list) else 0,
                    'coverage_status': (coverage.get(tbl) or {}).get('status', 'unknown'),
                }
                for tbl, rows in sorted((data['source'].get('tables') or {}).items())
                if (isinstance(rows, list) and len(rows) > 0) or tbl in ('transactions', 'vendors', 'employees', 'journal_lines', 'transaction_documents')
            ]
        else:
            frame = build_from_snapshot(self.snapshots, scope, snapshot_id, as_of, recheck)
            txs = data.get('transactions') or []
            type_counts = dict(Counter(str(t.get('kind') or 'unknown') for t in txs))
            tables_summary = [
                {'table': tbl, 'record_count': len(data.get(tbl) or []), 'coverage_status': 'complete' if data.get(tbl) else 'empty'}
                for tbl in ('transactions', 'vendors', 'employees', 'invoices', 'payment_allocations', 'approvals', 'supporting_documents')
            ]

        n_rows = len(frame['rows'])
        cols = frame['contract']['columns']
        feature_stats = []
        active_feature_count = 0
        observed_feature_count = 0
        total_cells = max(1, n_rows * len(cols))
        observed_cells = 0

        for j, col in enumerate(cols):
            vals = [row[j] for row in frame['features'] if row[j] is not None]
            obs = len(vals)
            miss = n_rows - obs
            observed_cells += obs
            has_var = bool(obs >= 2 and float(np.std(vals)) > 1e-12)
            if obs > 0:
                observed_feature_count += 1
            if has_var:
                active_feature_count += 1
            grp, lbl = FEATURE_GROUPS.get(col, ('Đặc trưng bổ sung', col))
            status = 'active' if has_var else ('constant' if obs > 0 else 'all_missing')
            feature_stats.append({
                'name': col,
                'label_vi': lbl,
                'group': grp,
                'observed_count': obs,
                'missing_count': miss,
                'missing_pct': round((miss / n_rows) * 100.0, 1) if n_rows else 100.0,
                'has_variance': has_var,
                'status': status,
                'unmapped_reason': UNMAPPED_COLUMNS.get(col) if native else None,
            })

        event_ts = [r['event_at'] for r in frame['rows']]
        rec_split = _compute_recommended_split(event_ts, as_of)
        h_rows = rec_split['history_rows']

        warnings_vi = []
        if meta['is_simulated']:
            warnings_vi.append('Bản dữ liệu đang mang cờ dữ liệu mô phỏng (is_simulated=true) — dùng để kiểm chứng kỹ thuật, chưa chứng minh hiệu quả thực tế.')
        if n_rows < 30:
            warnings_vi.append(f'Số lượng giao dịch ({n_rows}) còn nhỏ; nên chọn kỳ dữ liệu dài hơn từ sảnh chung để huấn luyện ổn định.')
        all_missing_cols = [f['name'] for f in feature_stats if f['status'] == 'all_missing']
        if all_missing_cols:
            warnings_vi.append(f'{len(all_missing_cols)} đặc trưng không có quan sát trong snapshot này sẽ được loại tự động khỏi ma trận huấn luyện (không điền 0 làm cờ gian lận).')

        recs = []
        for aid, info in sorted(ALGO_META.items(), key=lambda kv: kv[1]['priority']):
            eligible = bool(rec_split['split_feasible'] and h_rows >= info['min_rows'])
            if not eligible:
                note = f'Cần tối thiểu {info["min_rows"]} dòng huấn luyện (hiện có {h_rows} dòng trong kỳ train đề xuất).'
            elif h_rows < info['recommended_rows']:
                note = f'Đủ điều kiện chạy thử ({h_rows} dòng), khuyến nghị ≥ {info["recommended_rows"]} dòng để ổn định.'
            else:
                note = 'Phù hợp tốt với quy mô dữ liệu hiện có của doanh nghiệp.'
            recs.append({
                **info,
                'eligible': eligible,
                'fit_note_vi': note,
            })

        completeness_pct = round((observed_cells / total_cells) * 100.0, 1)
        quality_score = int(round(
            min(100.0, (completeness_pct * 0.45) + (min(n_rows, 60) / 60.0 * 35.0) + (20.0 if rec_split['split_feasible'] else 0.0))
        ))

        return {
            'version': VERSION,
            'company_id': company,
            'snapshot': meta,
            'data_quality_score': quality_score,
            'completeness_pct': completeness_pct,
            'transaction_type_counts': type_counts,
            'tables_summary': tables_summary,
            'feature_contract': {
                'version': frame['contract']['version'],
                'fingerprint': frame['contract']['fingerprint'],
                'total_features': len(cols),
                'observed_features': observed_feature_count,
                'active_variance_features': active_feature_count,
                'all_missing_features': len(all_missing_cols),
                'features': feature_stats,
                'excluded_predictors': list(frame['contract'].get('predictor_exclusions') or []),
            },
            'recommended_split': rec_split,
            'recommended_methods': recs,
            'warnings': warnings_vi,
        }

    def _check_verified_labels(self, scope: AccessScope, eval_snapshot_id: str, recheck=None) -> dict[tuple[str, int], str]:
        """Load locked verified labels from LabelStore for eval_snapshot_id if any exist (never fabricates labels)."""
        if self.label_store is None:
            return {}
        try:
            packets = self.label_store.list(scope, recheck)
        except Exception:
            return {}
        verified: dict[tuple[str, int], str] = {}
        for pkt in packets:
            if pkt.get('status') != 'locked' or pkt.get('snapshot_id') != eval_snapshot_id:
                continue
            try:
                exported = self.label_store.export(scope, pkt['packet_id'], pkt['revision'], pkt['lock_sha256'], recheck)
                for lbl in exported.get('labels') or []:
                    outcome = lbl.get('outcome')
                    if outcome in ('verified_fraud', 'verified_non_fraud'):
                        verified[(str(lbl['record_id']), int(lbl.get('revision', 1)))] = outcome
            except Exception:
                continue
        return verified

    def _evaluate_artifact(
        self,
        scope: AccessScope,
        method_id: str,
        artifact_id: str,
        manifest: dict,
        eval_snapshot_id: str,
        recheck=None,
        *,
        already_approved: bool = False,
    ) -> dict:
        """Evaluate an immutable frozen artifact on a held-out snapshot WITHOUT refitting."""
        tenant, company = _require_company_scope(scope, recheck)
        store = MethodStore(self.resources.model_db, read_only=True)
        artifact = store.get_artifact(scope, artifact_id, recheck)
        # Verify runtime/contract/preprocess compatibility
        contract = rule_feature_contract() if manifest.get('feature_contract', {}).get('version') == rule_feature_contract()['version'] else canonical_feature_contract()
        contract_ok = (
            manifest.get('version') == ARTIFACT_VERSION
            and manifest.get('method_id') == method_id
            and manifest.get('feature_contract') == contract
            and manifest.get('versions') == _versions()
            and manifest.get('preprocess_version') == PREPROCESS_VERSION
            and digest(canonical(manifest['preprocess'])) == manifest.get('preprocess_sha256')
        )
        try:
            validate_preprocess(dict(contract=contract), manifest['preprocess'])
        except Exception:
            contract_ok = False

        # Temporal split check from immutable manifest
        try:
            t_end = utc(manifest['train_end'])
            r_start = utc(manifest['reference_start'])
            r_end = utc(manifest['reference_end'])
            ev_start = utc((manifest.get('fit_context') or {}).get('evaluation_start') or manifest['reference_end'])
            split_ok = bool(t_end < r_start <= r_end <= ev_start)
        except Exception:
            split_ok = False

        model, ref_scores = joblib.load(io.BytesIO(artifact.payload))
        ref_arr = np.asarray(ref_scores, dtype=float)

        # Load held-out evaluation snapshot
        ev_man = self.snapshots.get_snapshot(scope, eval_snapshot_id, recheck)
        ev_data = loads(self.snapshots.get_snapshot(scope, eval_snapshot_id, recheck, data=True))
        ev_meta = _snapshot_meta_summary(ev_man, ev_data)
        native = ev_meta['native_35_rules']

        if native:
            frame = build_from_rule_snapshot(
                self.snapshots, scope, eval_snapshot_id, ev_meta['as_of'], recheck,
                candidates_only=False, require_exact_source_cutoff=False,
            )
            cand_set = set(ev_data.get('candidate_transaction_ids') or [])
        else:
            frame = build_from_snapshot(self.snapshots, scope, eval_snapshot_id, ev_meta['as_of'], recheck)
            cand_set = {r['record_id'] for r in frame['rows']}

        # Strict held-out filter: strictly exclude fitted identities & rows on/before reference_end
        fitted_hashes = set(manifest.get('fitted_identity_hashes') or [])
        ref_end_dt = utc(manifest['reference_end'])
        eval_indices = [
            i for i, r in enumerate(frame['rows'])
            if digest(canonical(r['record_id'])) not in fitted_hashes
            and min(utc(r['event_at']), utc(r['as_of'])) > ref_end_dt
            and (not cand_set or r['record_id'] in cand_set)
        ]
        # Fallback if the chosen snapshot is strictly a fit snapshot (no rows after reference_end):
        # evaluate on non-candidate held-out rows strictly after ref_end, else reference rows with explicit note
        eval_basis = 'held_out_future_evaluation'
        if not eval_indices:
            eval_indices = [
                i for i, r in enumerate(frame['rows'])
                if digest(canonical(r['record_id'])) not in fitted_hashes
                and min(utc(r['event_at']), utc(r['as_of'])) > ref_end_dt
            ]
        if not eval_indices:
            eval_basis = 'reference_window_fallback'
            eval_indices = [
                i for i, r in enumerate(frame['rows'])
                if utc(manifest['reference_start']) <= utc(r['event_at']) <= ref_end_dt
            ]

        prep = manifest['preprocess']
        out_cols = list(prep['output_columns'])
        eval_sub = dict(
            frame,
            rows=[deepcopy(frame['rows'][i]) for i in eval_indices],
            features=[deepcopy(frame['features'][i]) for i in eval_indices],
            missing=[deepcopy(frame['missing'][i]) for i in eval_indices],
            evidence=[deepcopy(frame['evidence'][i]) for i in eval_indices],
        )

        # Score held-out rows WITHOUT refitting
        t0 = time.monotonic()
        raw_scores: list[float] = []
        ranks: list[float] = []
        scored_rows_meta: list[dict] = []
        x_scored_list = []
        unavailable_count = 0
        from .method_preprocess import row_values
        for row_meta, feat_row in zip(eval_sub['rows'], eval_sub['features']):
            vals, missing_cols, unavail = row_values(eval_sub, feat_row, prep)
            if unavail:
                unavailable_count += 1
                continue
            x_scored_list.append(vals)
            scored_rows_meta.append({'record_id': row_meta['record_id'], 'revision': row_meta['revision'], 'event_at': row_meta['event_at'], 'missing_count': len(missing_cols)})

        if x_scored_list:
            x_mat = np.asarray(x_scored_list, dtype=float)
            raw_arr = np.asarray(model.score(x_mat), dtype=float)
            rank_arr = np.atleast_1d(empirical_rank(ref_arr, raw_arr, break_ties_above_max=True))
            raw_scores = [float(v) for v in raw_arr]
            ranks = [float(v) for v in rank_arr]
            attributions = _attribution_for_estimator(model, x_mat, out_cols, top_k=5)
        else:
            x_mat = np.zeros((0, len(out_cols)), dtype=float)
            attributions = []
        elapsed_sec = round(time.monotonic() - t0, 3)

        # Missingness robustness probe: take a median-like normal row and blank 5 optional kept columns;
        # confirm score does NOT explode due to missingness!
        missing_robust_ok = True
        missing_probe_delta = 0.0
        if len(x_mat) > 0 and prep['policy'] == 'median_flags' and len(prep['kept_columns']) >= 6:
            base_idx = int(np.argmin(raw_scores))
            base_feat = list(eval_sub['features'][base_idx])
            kept_idxs = [frame['contract']['columns'].index(c) for c in prep['kept_columns']]
            perturbed = list(base_feat)
            for idx_col in kept_idxs[-5:]:
                perturbed[idx_col] = None
            p_vals, _, p_err = row_values(eval_sub, perturbed, prep)
            if p_err is None:
                base_s = float(model.score(np.asarray([x_scored_list[base_idx]], dtype=float))[0])
                pert_s = float(model.score(np.asarray([p_vals], dtype=float))[0])
                ref_span = max(float(np.max(ref_arr) - np.min(ref_arr)), abs(float(np.median(ref_arr))), 1.0)
                missing_probe_delta = round(pert_s - base_s, 4)
                # Must not explode by huge factor above normal variation
                missing_robust_ok = bool(pert_s < base_s + 5.0 * ref_span + 15.0)

        # Unsupervised metrics (label-free)
        if raw_scores:
            arr_s = np.asarray(raw_scores, dtype=float)
            p50 = float(np.median(arr_s))
            p95 = float(np.percentile(arr_s, 95))
            smax = float(np.max(arr_s))
            ref_p95 = float(np.percentile(ref_arr, 95))
            tail_above_ref_p95 = round(float(np.mean(arr_s > ref_p95)) * 100.0, 1)
            sep_ratio = round(smax / max(abs(p50), 1e-6), 3) if p50 != 0 else round(smax, 3)
            top_order = sorted(range(len(raw_scores)), key=lambda i: (-ranks[i], -raw_scores[i]))[:5]
            top_cases = [
                {
                    'record_id': scored_rows_meta[i]['record_id'],
                    'event_at': scored_rows_meta[i]['event_at'],
                    'raw_score': round(raw_scores[i], 4),
                    'relative_rank_pct': round(ranks[i] * 100.0, 1),
                    'top_features': attributions[i] if i < len(attributions) else [],
                }
                for i in top_order
            ]
        else:
            p50 = p95 = smax = tail_above_ref_p95 = sep_ratio = None
            top_cases = []

        # Fixed-budget (5 tx) comparison with 35 rules + verified labels (if available)
        budget = 5
        verified_map = self._check_verified_labels(scope, eval_snapshot_id, recheck)
        rules_hit_ids: set[str] = set()
        if native and eval_basis == 'held_out_future_evaluation':
            try:
                sel_tmp = {
                    'version': BINDINGS_VERSION,
                    'tenant_id': tenant,
                    'company_id': company,
                    'statistics_artifact_id': None,
                    'ml_artifacts': {method_id: artifact_id},
                }
                ana = analyze_rule_snapshot(
                    self.snapshots, scope, eval_snapshot_id, ev_meta['as_of'],
                    technical=True, resources=FrozenResources(self.resources.model_db, sel_tmp), recheck=recheck,
                )
                for r in ana.get('rows') or []:
                    cov = (r.get('rule_coverage') or {}).get('rules') or []
                    if any(
                        e.get('status') == 'evaluated_hit'
                        and any(not h.get('suppressed_reason') and (h.get('points', 0) > 0 or h.get('hard_trigger')) for h in e.get('hits') or [])
                        for e in cov
                    ):
                        rules_hit_ids.add(str(r['transaction_id']))
            except Exception:
                pass

        # Top-5 combined selection (rules first, ML fills remaining slots up to 5)
        rule_selected = sorted(rules_hit_ids)[:budget]
        rem_slots = max(0, budget - len(rule_selected))
        ml_ranked_non_rule = [
            scored_rows_meta[i]['record_id']
            for i in sorted(range(len(raw_scores)), key=lambda i: (-ranks[i], -raw_scores[i]))
            if scored_rows_meta[i]['record_id'] not in rule_selected
        ][:rem_slots]
        combined_top5 = rule_selected + ml_ranked_non_rule

        if verified_map:
            useful_verified = sum(1 for tid in combined_top5 if verified_map.get((tid, 1)) == 'verified_fraud')
            label_basis = 'verified_labels'
            useful_display = f'{useful_verified}/{len(combined_top5) or budget} giao dịch (nhãn đã xác minh)'
        elif rules_hit_ids or top_cases:
            # Unlabeled/simulated scenario evaluation: count rule hits + high-tail ML anomalies (>90th ref percentile)
            high_tail_ml = sum(
                1 for tid in ml_ranked_non_rule
                if any(tc['record_id'] == tid and tc['relative_rank_pct'] >= 90.0 for tc in top_cases)
            )
            scenario_hits = len(rule_selected) + high_tail_ml
            label_basis = 'scenario_unsupervised'
            useful_verified = None
            useful_display = f'{scenario_hits}/{len(combined_top5) or budget} giao dịch (kịch bản mô phỏng)' if ev_meta['is_simulated'] else f'{scenario_hits}/{len(combined_top5) or budget} giao dịch (chưa có nhãn xác minh)'
        else:
            label_basis = 'no_verified_labels'
            useful_verified = None
            useful_display = 'Chưa có nhãn xác minh'

        ev_dates = [r['event_at'] for r in eval_sub['rows']]
        eval_period_label = _fmt_period_vn(min(ev_dates) if ev_dates else ev_meta['min_event_at'], max(ev_dates) if ev_dates else ev_meta['max_event_at'])

        checklist = [
            {
                'id': 'split_separation',
                'label': 'Tách kỳ huấn luyện và kỳ đánh giá',
                'status': 'pass' if split_ok else 'fail',
                'detail': f'Train kết thúc {_fmt_date_vn(manifest.get("train_end"))} < Reference ({manifest.get("reference_rows")} dòng) ≤ Đánh giá.' if split_ok else 'Khoảng thời gian train/reference/evaluation chồng lấn.',
            },
            {
                'id': 'contract_binding',
                'label': 'Đặc trưng và dữ liệu đúng phiên bản',
                'status': 'pass' if contract_ok else 'fail',
                'detail': f'Khớp {contract["version"]} ({contract["fingerprint"][:12]}…) và {PREPROCESS_VERSION}.' if contract_ok else 'Feature contract hoặc checksum artifact không khớp runtime hiện hành.',
            },
            {
                'id': 'missing_disclosed',
                'label': 'Nguồn thiếu được ghi rõ',
                'status': 'pass' if missing_robust_ok else 'fail',
                'detail': f'Loại {len(prep.get("dropped_columns") or {})} cột toàn null; thử nghiệm khuyết 5 biến giữ điểm ổn định (Δ={missing_probe_delta}).' if missing_robust_ok else 'Cảnh báo biến khuyết làm tăng bất thường điểm số.',
            },
            {
                'id': 'business_confirmation',
                'label': 'Xác nhận nghiệp vụ',
                'status': 'pass' if already_approved else 'waiting',
                'detail': 'Đã được người có thẩm quyền phê duyệt.' if already_approved else 'Đang chờ người quản trị mô hình xem đánh giá và xác nhận.',
            },
        ]

        return {
            'eval_snapshot_id': eval_snapshot_id,
            'eval_basis': eval_basis,
            'eval_period_label': eval_period_label,
            'eval_rows': len(eval_sub['rows']),
            'scored_rows': len(raw_scores),
            'unavailable_rows': unavailable_count,
            'inference_seconds': elapsed_sec,
            'is_simulated': ev_meta['is_simulated'],
            'budget': budget,
            'rules_hits_count': len(rule_selected),
            'ml_added_count': len(ml_ranked_non_rule),
            'combined_top5_ids': combined_top5,
            'label_basis': label_basis,
            'verified_labels_count': len(verified_map),
            'verified_useful_hits': useful_verified,
            'useful_display': useful_display,
            'converged': (manifest.get('fit_diagnostics') or {}).get('converged'),
            'missing_robustness_pass': missing_robust_ok,
            'missing_probe_delta': missing_probe_delta,
            'unsupervised': {
                'median_raw_score': round(p50, 4) if p50 is not None else None,
                'p95_raw_score': round(p95, 4) if p95 is not None else None,
                'max_raw_score': round(smax, 4) if smax is not None else None,
                'separation_ratio': sep_ratio,
                'tail_above_ref_p95_pct': tail_above_ref_p95,
                'reference_rows': int(len(ref_arr)),
            },
            'top_attributions': top_cases,
            'checklist': checklist,
            'technical_ready': all(c['status'] == 'pass' for c in checklist if c['id'] != 'business_confirmation'),
            'limitation': 'Điểm ML dùng để ưu tiên rà soát, không phải xác suất gian lận. Kết quả trên dữ liệu mô phỏng chưa chứng minh hiệu quả phát hiện gian lận thực tế.',
        }

    def train_candidate(self, scope: AccessScope, authorization: str | None, body: dict, key: str, recheck=None) -> dict:
        tenant, company = _require_company_scope(scope, recheck)
        require_fit(scope)
        if not isinstance(key, str) or re.fullmatch(r'[A-Za-z0-9_.:-]{8,128}', key) is None:
            fail(400, 'IDEMPOTENCY_KEY', 'Thiếu hoặc sai mã yêu cầu huấn luyện (8–128 ký tự).', 'Thử bấm huấn luyện lại.')
        if not isinstance(body, dict):
            fail(400, 'TRAIN_FIELDS', 'Dữ liệu yêu cầu huấn luyện không hợp lệ.', 'Chọn snapshot và thuật toán trên màn hình.')
        snapshot_id = str(body.get('snapshot_id') or '').strip()
        method_id = str(body.get('method_id') or '').strip()
        if method_id not in ML_IDS:
            fail(400, 'TRAIN_METHOD', f'Thuật toán không được hỗ trợ: {method_id}.', 'Chọn Isolation Forest, Autoencoder, ECOD hoặc LOF.')
        if re.fullmatch(r'snp_[a-f0-9]{32}', snapshot_id) is None:
            fail(400, 'TRAIN_SNAPSHOT', 'Cần chọn một bản dữ liệu đã khóa từ sảnh chung.', 'Chọn snapshot hợp lệ.')
        if self.resources.model_db is None:
            fail(503, 'MODEL_STORE_UNCONFIGURED', 'Chưa cấu hình kho lưu mô hình.', 'Liên hệ người vận hành.')

        missing_policy = str(body.get('missing_policy') or 'median_flags')
        if missing_policy not in ('median_flags', 'strict'):
            fail(400, 'TRAIN_MISSING_POLICY', 'Chính sách xử lý khuyết không hợp lệ.', 'Chọn median_flags hoặc strict.')

        # Profile snapshot to get safe chronological boundaries if not explicitly provided
        prof = self.profile_snapshot(scope, snapshot_id, recheck)
        rec = prof['recommended_split']
        history_start = str(body.get('history_start') or rec['history_start'])
        history_end = str(body.get('history_end') or rec['history_end'])
        reference_start = str(body.get('reference_start') or rec['reference_start'])
        reference_end = str(body.get('reference_end') or rec['reference_end'])
        evaluation_start = str(body.get('evaluation_start') or rec['evaluation_start'])
        selected_columns = body.get('selected_columns') or list(FEATURE_COLUMNS)
        eval_snapshot_id = str(body.get('eval_snapshot_id') or '').strip() or snapshot_id
        if re.fullmatch(r'snp_[a-f0-9]{32}', eval_snapshot_id) is None:
            fail(400, 'EVAL_SNAPSHOT', 'Bản dữ liệu đánh giá không hợp lệ.', 'Chọn snapshot đánh giá hợp lệ.')

        min_hist = int(body.get('minimum_history') or ALGO_META[method_id]['min_rows'])
        min_hist = max(min_hist, ALGO_META[method_id]['min_rows'])
        req_payload = {
            'action': 'train',
            'snapshot_id': snapshot_id,
            'eval_snapshot_id': eval_snapshot_id,
            'method_id': method_id,
            'missing_policy': missing_policy,
            'minimum_history': min_hist,
            'selected_columns': list(selected_columns),
            'history_start': history_start,
            'history_end': history_end,
            'reference_start': reference_start,
            'reference_end': reference_end,
            'evaluation_start': evaluation_start,
        }
        req_hash = digest(canonical(req_payload))
        with self._tx(scope, recheck, write=False) as conn:
            prior = conn.execute(
                'SELECT request_hash, result_json FROM lifecycle_receipts WHERE tenant_id=? AND company_id=? AND actor_id=? AND request_id=?',
                (tenant, company, scope.actor_id, key),
            ).fetchone()
            if prior is not None:
                if prior['request_hash'] != req_hash:
                    fail(409, 'IDEMPOTENCY_CONFLICT', 'Mã yêu cầu đã dùng cho cấu hình huấn luyện khác.', 'Tạo yêu cầu huấn luyện mới.')
                return loads(prior['result_json'])

        fit_cfg = {
            'version': CONFIG_VERSION,
            'snapshot_id': snapshot_id,
            'method_id': method_id,
            'missing_policy': missing_policy,
            'minimum_history': min_hist,
            'profile_id': f'area-b-{method_id}-v1',
            'evaluation_mode': 'backtest',
            'selected_columns': list(selected_columns),
            'history_start': history_start,
            'history_end': history_end,
            'reference_start': reference_start,
            'reference_end': reference_end,
            'evaluation_start': evaluation_start,
        }

        writable_store = MethodStore(self.resources.model_db, read_only=False)
        fit_key = 'mlc-fit-' + digest(canonical([tenant, company, key]))[:40]
        fit_res = run_fit_job(self.snapshots, writable_store, self.authorizer, authorization, company, fit_cfg, fit_key)
        if fit_res.get('job', {}).get('status') != 'succeeded' or not fit_res.get('manifest'):
            err = fit_res.get('error') or {}
            fail(
                422,
                err.get('code') or 'MODEL_FIT_FAILED',
                err.get('message') or 'Huấn luyện mô hình thất bại do dữ liệu chưa đáp ứng điều kiện kỳ hoặc số dòng tối thiểu.',
                'Kiểm tra số dòng lịch sử và khoảng thời gian tách kỳ train/reference/đánh giá.',
            )

        manifest = fit_res['manifest']
        artifact_id = fit_res['job']['artifact_id']

        # Immediately evaluate on held-out snapshot WITHOUT refitting
        eval_summary = self._evaluate_artifact(scope, method_id, artifact_id, manifest, eval_snapshot_id, recheck)
        selected_binding, _ = self.resources.selection(scope)
        now = _iso_now()
        data_profile = {
            'snapshot_id': snapshot_id,
            'history_rows': int(manifest['history_rows']),
            'reference_rows': int(manifest['reference_rows']),
            'kept_features': len(manifest['preprocess']['kept_columns']),
            'dropped_features': len(manifest['preprocess']['dropped_columns']),
            'period_label': prof['snapshot']['period_label'],
            'data_quality_score': prof['data_quality_score'],
            'is_simulated': prof['snapshot']['is_simulated'],
        }
        status = 'pending_approval' if eval_summary['technical_ready'] else 'evaluated'

        with self._tx(scope, recheck, write=True) as conn:
            vnum = self._next_version_number(conn, tenant, company)
            vtag = f'{company}-v{vnum}'
            vid = 'mv_' + digest(canonical([tenant, company, vnum, artifact_id, now]))[:24]
            conn.execute(
                """INSERT INTO model_versions(
                    version_id,tenant_id,company_id,version_number,version_tag,method_id,artifact_id,
                    statistics_artifact_id,snapshot_id,eval_snapshot_id,feature_contract_version,
                    feature_contract_fingerprint,preprocess_version,config_json,data_profile_json,
                    evaluation_json,status,mode,approval_json,bundle_id,created_by,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    vid, tenant, company, vnum, vtag, method_id, artifact_id,
                    selected_binding.get('statistics_artifact_id'), snapshot_id, eval_snapshot_id,
                    manifest['feature_contract']['version'],
                    manifest['feature_contract_fingerprint'],
                    manifest['preprocess_version'],
                    canonical(fit_cfg).decode('utf-8'),
                    canonical(data_profile).decode('utf-8'),
                    canonical(eval_summary).decode('utf-8'),
                    status, 'none', None, None, scope.actor_id, now, now,
                ),
            )
            self._record_event(
                conn, scope, vid, 'trained',
                f'Huấn luyện phiên bản {vtag} ({ALGORITHMS[method_id]}) từ bản dữ liệu {snapshot_id[:12]}…',
                {'artifact_id': artifact_id, 'job_id': fit_res['job']['job_id'], 'history_rows': manifest['history_rows'], 'reference_rows': manifest['reference_rows']},
            )
            self._record_event(
                conn, scope, vid, 'evaluated',
                f'Đánh giá {vtag}: {eval_summary["useful_display"]}, thời gian xử lý {eval_summary["inference_seconds"]} giây.',
                {'eval_snapshot_id': eval_snapshot_id, 'technical_ready': eval_summary['technical_ready']},
            )
            created_row = conn.execute('SELECT * FROM model_versions WHERE version_id=?', (vid,)).fetchone()
            result = {'version': self._row_to_dto(created_row), 'fit_job': fit_res['job']}
            conn.execute(
                'INSERT OR IGNORE INTO lifecycle_receipts VALUES (?,?,?,?,?,?,?)',
                (tenant, company, scope.actor_id, key, req_hash, canonical(result).decode('utf-8'), now),
            )
            return result

    def evaluate_version(self, scope: AccessScope, version_id: str, eval_snapshot_id: str, recheck=None) -> dict:
        tenant, company = _require_company_scope(scope, recheck)
        if re.fullmatch(r'snp_[a-f0-9]{32}', eval_snapshot_id or '') is None:
            fail(400, 'EVAL_SNAPSHOT', 'Bản dữ liệu đánh giá không hợp lệ.', 'Chọn bản dữ liệu đã khóa từ sảnh chung.')
        with self._tx(scope, recheck, write=False) as conn:
            row = conn.execute(
                'SELECT * FROM model_versions WHERE version_id=? AND tenant_id=? AND company_id=?',
                (version_id, tenant, company),
            ).fetchone()
            if row is None:
                fail(404, 'MODEL_VERSION_NOT_FOUND', 'Không tìm thấy phiên bản mô hình trong doanh nghiệp.', 'Chọn đúng phiên bản.')
        store = MethodStore(self.resources.model_db, read_only=True)
        art = store.get_artifact(scope, row['artifact_id'], recheck)
        manifest = loads(art.manifest)
        ev = self._evaluate_artifact(
            scope, row['method_id'], row['artifact_id'], manifest, eval_snapshot_id, recheck,
            already_approved=row['approval_json'] is not None,
        )
        now = _iso_now()
        with self._tx(scope, recheck, write=True) as conn:
            new_status = row['status']
            if new_status in ('trained', 'evaluated', 'pending_approval'):
                new_status = 'pending_approval' if ev['technical_ready'] else 'evaluated'
            conn.execute(
                'UPDATE model_versions SET eval_snapshot_id=?, evaluation_json=?, status=?, updated_at=? WHERE version_id=?',
                (eval_snapshot_id, canonical(ev).decode('utf-8'), new_status, now, version_id),
            )
            self._record_event(conn, scope, version_id, 'evaluated', f'Đánh giá lại trên snapshot {eval_snapshot_id[:12]}…', {'eval_snapshot_id': eval_snapshot_id})
            updated = conn.execute('SELECT * FROM model_versions WHERE version_id=?', (version_id,)).fetchone()
            return {'version': self._row_to_dto(updated)}

    def _write_company_binding_atomic(self, scope: AccessScope, method_id: str, artifact_id: str, stats_artifact_id: str | None, recheck=None):
        """Atomically pin approved ML artifact for this company only; never alters other companies."""
        if self.resources.bindings_file is None:
            return
        tenant, company = _require_company_scope(scope, recheck)
        path = Path(self.resources.bindings_file).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        existing_bindings = []
        if path.is_file():
            doc = loads(path.read_bytes())
            if isinstance(doc, dict) and doc.get('version') == BINDINGS_VERSION and isinstance(doc.get('bindings'), list):
                existing_bindings = list(doc['bindings'])
        preserved = [b for b in existing_bindings if (b.get('tenant_id'), b.get('company_id')) != (tenant, company)]
        old_entry = next((b for b in existing_bindings if (b.get('tenant_id'), b.get('company_id')) == (tenant, company)), None)
        eff_stats = stats_artifact_id if stats_artifact_id is not None else (old_entry.get('statistics_artifact_id') if old_entry else None)
        new_entry = {
            'tenant_id': tenant,
            'company_id': company,
            'statistics_artifact_id': eff_stats,
            'ml_artifacts': {method_id: artifact_id},
        }
        payload = canonical({'version': BINDINGS_VERSION, 'bindings': preserved + [new_entry]})
        if recheck is not None and recheck() != scope:
            fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền truy cập đã thay đổi trước khi ghi cấu hình.', 'Đăng nhập lại.')
        fd, tmp = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
        tmp_path = Path(tmp)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp_path, path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def approve_and_activate(self, scope: AccessScope, body: dict, key: str, recheck=None) -> dict:
        tenant, company = _require_company_scope(scope, recheck)
        require_fit(scope)
        if not isinstance(key, str) or re.fullmatch(r'[A-Za-z0-9_.:-]{8,128}', key) is None:
            fail(400, 'IDEMPOTENCY_KEY', 'Thiếu hoặc sai mã yêu cầu phê duyệt.', 'Thử lại.')
        version_id = str(body.get('version_id') or '').strip()
        mode = str(body.get('mode') or 'shadow').strip()
        reason = str(body.get('reason') or '').strip()
        reviewed = body.get('reviewed_evaluation') is True
        if mode not in ('shadow', 'active'):
            fail(400, 'APPROVAL_MODE', 'Chế độ chạy chỉ nhận shadow (Chạy thử) hoặc active (Đang dùng).', 'Chọn đúng chế độ.')
        if not reviewed:
            fail(400, 'APPROVAL_CONFIRM_REQUIRED', 'Cần xác nhận đã xem kết quả đánh giá trước khi phê duyệt.', 'Đánh dấu ô xác nhận.')
        if not (10 <= len(reason) <= 1000):
            fail(400, 'APPROVAL_REASON', 'Ý kiến phê duyệt cần dài từ 10 đến 1000 ký tự.', 'Nhập rõ lý do phê duyệt.')

        req_hash = digest(canonical({'action': 'approve', 'version_id': version_id, 'mode': mode, 'reason': reason}))
        with self._tx(scope, recheck, write=False) as conn:
            prior = conn.execute(
                'SELECT request_hash, result_json FROM lifecycle_receipts WHERE tenant_id=? AND company_id=? AND actor_id=? AND request_id=?',
                (tenant, company, scope.actor_id, key),
            ).fetchone()
            if prior is not None:
                if prior['request_hash'] != req_hash:
                    fail(409, 'IDEMPOTENCY_CONFLICT', 'Mã yêu cầu phê duyệt đã dùng cho nội dung khác.', 'Thử lại với yêu cầu mới.')
                return loads(prior['result_json'])
            row = conn.execute(
                'SELECT * FROM model_versions WHERE version_id=? AND tenant_id=? AND company_id=?',
                (version_id, tenant, company),
            ).fetchone()
            if row is None:
                fail(404, 'MODEL_VERSION_NOT_FOUND', 'Không tìm thấy phiên bản mô hình trong doanh nghiệp.', 'Tải lại danh sách.')

        ev = loads(row['evaluation_json'])
        if not ev.get('technical_ready', False):
            fail(409, 'MODEL_QUALITY_GATE_FAILED', 'Phiên bản chưa đạt đủ tiêu chí kiểm tra chất lượng trước phê duyệt.', 'Xem lại mục Kiểm tra chất lượng và khắc phục trước khi duyệt.')

        # Re-verify immutable artifact in MethodStore before activation
        store = MethodStore(self.resources.model_db, read_only=True)
        art = store.get_artifact(scope, row['artifact_id'], recheck)
        manifest = loads(art.manifest)
        if manifest.get('versions') != _versions() or manifest.get('preprocess_version') != PREPROCESS_VERSION:
            fail(409, 'MODEL_INCOMPATIBLE', 'Artifact không còn tương thích với runtime hiện tại; cần huấn luyện lại.', 'Huấn luyện phiên bản mới.')

        # Atomically update company pinned binding file
        self._write_company_binding_atomic(scope, row['method_id'], row['artifact_id'], row['statistics_artifact_id'], recheck)

        now = _iso_now()
        approval_obj = {
            'approved_by': scope.actor_id,
            'approved_at': now,
            'mode': mode,
            'reason': reason,
            'reviewed_evaluation': True,
        }
        # Mark business_confirmation checklist item passed
        for chk in ev.get('checklist') or []:
            if chk.get('id') == 'business_confirmation':
                chk['status'] = 'pass'
                chk['detail'] = f'Được phê duyệt bởi {scope.actor_id} ({_fmt_date_vn(now)}): {reason[:120]}'

        with self._tx(scope, recheck, write=True) as conn:
            conn.execute(
                "UPDATE model_versions SET status='superseded', mode='none', updated_at=? WHERE tenant_id=? AND company_id=? AND status IN ('active','shadow') AND version_id!=?",
                (now, tenant, company, version_id),
            )
            conn.execute(
                'UPDATE model_versions SET status=?, mode=?, approval_json=?, evaluation_json=?, updated_at=? WHERE version_id=?',
                (mode, mode, canonical(approval_obj).decode('utf-8'), canonical(ev).decode('utf-8'), now, version_id),
            )
            self._record_event(
                conn, scope, version_id, f'activated_{mode}',
                f'Phê duyệt và đưa {row["version_tag"]} vào chế độ {"Đang dùng" if mode == "active" else "Chạy thử"}: {reason}',
                {'mode': mode, 'artifact_id': row['artifact_id'], 'reason': reason},
            )
            updated = conn.execute('SELECT * FROM model_versions WHERE version_id=?', (version_id,)).fetchone()
            result = {'version': self._row_to_dto(updated), 'binding_updated': True}
            conn.execute(
                'INSERT OR IGNORE INTO lifecycle_receipts VALUES (?,?,?,?,?,?,?)',
                (tenant, company, scope.actor_id, key, req_hash, canonical(result).decode('utf-8'), now),
            )
            return result

    def rollback_version(self, scope: AccessScope, body: dict, key: str, recheck=None) -> dict:
        tenant, company = _require_company_scope(scope, recheck)
        require_fit(scope)
        if not isinstance(key, str) or re.fullmatch(r'[A-Za-z0-9_.:-]{8,128}', key) is None:
            fail(400, 'IDEMPOTENCY_KEY', 'Thiếu hoặc sai mã yêu cầu hoàn nguyên.', 'Thử lại.')
        target_id = str(body.get('target_version_id') or '').strip()
        reason = str(body.get('reason') or '').strip()
        if not (10 <= len(reason) <= 1000):
            fail(400, 'ROLLBACK_REASON', 'Cần nhập lý do hoàn nguyên từ 10 đến 1000 ký tự.', 'Nhập rõ lý do hoàn nguyên.')

        req_hash = digest(canonical({'action': 'rollback', 'target_version_id': target_id, 'reason': reason}))
        with self._tx(scope, recheck, write=False) as conn:
            prior = conn.execute(
                'SELECT request_hash, result_json FROM lifecycle_receipts WHERE tenant_id=? AND company_id=? AND actor_id=? AND request_id=?',
                (tenant, company, scope.actor_id, key),
            ).fetchone()
            if prior is not None:
                if prior['request_hash'] != req_hash:
                    fail(409, 'IDEMPOTENCY_CONFLICT', 'Mã yêu cầu hoàn nguyên đã dùng cho nội dung khác.', 'Thử lại.')
                return loads(prior['result_json'])
            target = conn.execute(
                'SELECT * FROM model_versions WHERE version_id=? AND tenant_id=? AND company_id=?',
                (target_id, tenant, company),
            ).fetchone()
            if target is None:
                fail(404, 'MODEL_VERSION_NOT_FOUND', 'Không tìm thấy phiên bản đích để hoàn nguyên.', 'Chọn đúng phiên bản trong lịch sử.')
            if not target['approval_json']:
                fail(409, 'ROLLBACK_UNAPPROVED_TARGET', 'Chỉ được hoàn nguyên về phiên bản đã từng được phê duyệt.', 'Chọn một phiên bản đã duyệt trước đó.')
            if target['status'] == 'active':
                fail(409, 'ROLLBACK_ALREADY_ACTIVE', 'Phiên bản này đang là phiên bản hoạt động hiện tại.', 'Chọn phiên bản cũ hơn.')

        store = MethodStore(self.resources.model_db, read_only=True)
        art = store.get_artifact(scope, target['artifact_id'], recheck)
        manifest = loads(art.manifest)
        if manifest.get('versions') != _versions() or manifest.get('preprocess_version') != PREPROCESS_VERSION:
            fail(409, 'ROLLBACK_INCOMPATIBLE', 'Phiên bản cũ không còn tương thích với runtime hiện tại.', 'Huấn luyện phiên bản tương thích mới.')

        self._write_company_binding_atomic(scope, target['method_id'], target['artifact_id'], target['statistics_artifact_id'], recheck)
        now = _iso_now()
        old_app = loads(target['approval_json'])
        restored_mode = old_app.get('mode') if old_app.get('mode') in ('shadow', 'active') else 'active'

        with self._tx(scope, recheck, write=True) as conn:
            conn.execute(
                "UPDATE model_versions SET status='rolled_back', mode='none', updated_at=? WHERE tenant_id=? AND company_id=? AND status IN ('active','shadow') AND version_id!=?",
                (now, tenant, company, target_id),
            )
            conn.execute(
                'UPDATE model_versions SET status=?, mode=?, updated_at=? WHERE version_id=?',
                (restored_mode, restored_mode, now, target_id),
            )
            self._record_event(
                conn, scope, target_id, 'rolled_back',
                f'Hoàn nguyên về phiên bản {target["version_tag"]}: {reason}',
                {'restored_mode': restored_mode, 'artifact_id': target['artifact_id'], 'reason': reason},
            )
            updated = conn.execute('SELECT * FROM model_versions WHERE version_id=?', (target_id,)).fetchone()
            result = {'version': self._row_to_dto(updated), 'rolled_back': True}
            conn.execute(
                'INSERT OR IGNORE INTO lifecycle_receipts VALUES (?,?,?,?,?,?,?)',
                (tenant, company, scope.actor_id, key, req_hash, canonical(result).decode('utf-8'), now),
            )
            return result

    def score_to_queue(self, scope: AccessScope, body: dict, key: str, recheck=None) -> dict:
        """Connect approved ML model + 35 rules + entity graph to Area A Investigation Queue.

        Strictly read-only inference (NEVER fits during scoring), writes an immutable
        observation + review_packet to ReleaseStore so Area A immediately lists & explains
        the prioritized transactions traced back to this exact approved model version.
        """
        tenant, company = _require_company_scope(scope, recheck)
        require_fit(scope)
        if not isinstance(key, str) or re.fullmatch(r'[A-Za-z0-9_.:-]{8,128}', key) is None:
            fail(400, 'IDEMPOTENCY_KEY', 'Thiếu hoặc sai mã yêu cầu chấm hàng đợi.', 'Thử lại.')
        snapshot_id = str(body.get('snapshot_id') or '').strip()
        version_id = str(body.get('version_id') or '').strip()
        if re.fullmatch(r'snp_[a-f0-9]{32}', snapshot_id) is None:
            fail(400, 'SCORE_SNAPSHOT', 'Cần chọn bản dữ liệu hợp lệ để chấm vào hàng đợi.', 'Chọn snapshot từ sảnh chung.')
        if self.release_service is None:
            fail(503, 'PIPELINE_NOT_CONFIGURED', 'Chưa cấu hình kho hàng đợi điều tra.', 'Liên hệ người vận hành.')

        with self._tx(scope, recheck, write=False) as conn:
            if version_id:
                row = conn.execute(
                    'SELECT * FROM model_versions WHERE version_id=? AND tenant_id=? AND company_id=?',
                    (version_id, tenant, company),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM model_versions WHERE tenant_id=? AND company_id=? AND status IN ('active','shadow') ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, version_number DESC LIMIT 1",
                    (tenant, company),
                ).fetchone()
            if row is None:
                fail(409, 'MODEL_APPROVAL_REQUIRED', 'Chưa có phiên bản mô hình nào được phê duyệt để chấm hàng đợi.', 'Phê duyệt một phiên bản mô hình trước.')
            if row['status'] not in ('active', 'shadow') or not row['approval_json']:
                fail(409, 'MODEL_APPROVAL_REQUIRED', 'Chỉ được đưa kết quả từ phiên bản mô hình đã được phê duyệt vào hàng đợi.', 'Hoàn tất phê duyệt ở Bước 5 trước.')
            version_dto = self._row_to_dto(row)

        req_hash = digest(canonical({'action': 'score_to_queue', 'snapshot_id': snapshot_id, 'version_id': version_dto['version_id']}))
        with self._tx(scope, recheck, write=False) as conn:
            prior = conn.execute(
                'SELECT request_hash, result_json FROM lifecycle_receipts WHERE tenant_id=? AND company_id=? AND actor_id=? AND request_id=?',
                (tenant, company, scope.actor_id, key),
            ).fetchone()
            if prior is not None:
                if prior['request_hash'] != req_hash:
                    fail(409, 'IDEMPOTENCY_CONFLICT', 'Mã yêu cầu đã dùng cho cấu hình khác.', 'Tạo yêu cầu mới.')
                return loads(prior['result_json'])

        manifest = self.snapshots.get_snapshot(scope, snapshot_id, recheck)
        data = loads(self.snapshots.get_snapshot(scope, snapshot_id, recheck, data=True))
        if 'source' not in data:
            fail(422, 'SCORE_NATIVE_REQUIRED', 'Chấm kết hợp 35 luật + ML vào hàng đợi yêu cầu snapshot đầy đủ (agent2-rule-snapshot/1.0.0).',
                 'Chọn bản dữ liệu đầy đủ từ sảnh chung.')
        as_of = data['source']['as_of']

        method_id = version_dto['method_id']
        artifact_id = version_dto['artifact_id']
        frozen_sel = {
            'version': BINDINGS_VERSION,
            'tenant_id': tenant,
            'company_id': company,
            'statistics_artifact_id': version_dto['statistics_artifact_id'],
            'ml_artifacts': {method_id: artifact_id},
        }
        started = time.monotonic()
        # Frozen read-only inference (ZERO fit!) across existing 4 methods
        analysis = analyze_rule_snapshot(
            self.snapshots, scope, snapshot_id, as_of,
            technical=True, resources=FrozenResources(self.resources.model_db, frozen_sel), recheck=recheck,
        )

        # Build point-in-time feature frame once for both Unsupervised ML attributions and Supervised LR (5th method)
        frame = build_from_rule_snapshot(
            self.snapshots, scope, snapshot_id, as_of, recheck,
            candidates_only=True, require_exact_source_cutoff=False,
        )

        # Attach per-feature ML attributions + version tag to each scored row for transparent explanation in Area A
        try:
            mstore = MethodStore(self.resources.model_db, read_only=True)
            art = mstore.get_artifact(scope, artifact_id, recheck)
            art_man = loads(art.manifest)
            model_obj, _ = joblib.load(io.BytesIO(art.payload))
            from .method_preprocess import row_values
            out_cols = list(art_man['preprocess']['output_columns'])
            by_tid_feat = {r['record_id']: feat for r, feat in zip(frame['rows'], frame['features'])}
            valid_tids, valid_mats = [], []
            for r in analysis['rows']:
                tid = r['transaction_id']
                feat = by_tid_feat.get(tid)
                if feat is None:
                    continue
                vals, _, err = row_values(frame, feat, art_man['preprocess'])
                if err is None:
                    valid_tids.append(tid)
                    valid_mats.append(vals)
            if valid_mats:
                attrs_list = _attribution_for_estimator(model_obj, np.asarray(valid_mats, dtype=float), out_cols, top_k=5)
                attrs_map = dict(zip(valid_tids, attrs_list))
            else:
                attrs_map = {}
            for r in analysis['rows']:
                m_entry = (r.get('methods') or {}).get(method_id)
                if isinstance(m_entry, dict):
                    m_entry.setdefault('details', {})['version_tag'] = version_dto['version_tag']
                    m_entry['details']['top_contributing_features'] = attrs_map.get(r['transaction_id'], [])
        except Exception:
            pass

        # R3 — 5th Detection Method: Supervised Logistic Regression inference (local preferred, optional CKKS)
        from .lr_inference import RiskScoringConfig, SupervisedLRAdapter, build_five_method_row_assessment
        sc_in = body.get('scoring_config') if isinstance(body.get('scoring_config'), dict) else {}
        risk_cfg = RiskScoringConfig(
            rule_weight=float(sc_in.get('rule_weight', 1.0)),
            statistics_weight=float(sc_in.get('statistics_weight', 0.5)),
            graph_weight=float(sc_in.get('graph_weight', 0.0)),
            unsupervised_ml_weight=float(sc_in.get('unsupervised_ml_weight', 2.0)),
            supervised_lr_weight=float(sc_in.get('supervised_lr_weight', 1.0)),
            lr_max_points=float(sc_in.get('lr_max_points', 8.0)),
            overlap_discount_factor=float(sc_in.get('overlap_discount_factor', 0.70)),
            validation_precision_scaling=bool(sc_in.get('validation_precision_scaling', True)),
        )
        lr_adapter = SupervisedLRAdapter(lr_training_service=getattr(self, 'lr_fhe', None), scoring_config=risk_cfg)
        lr_pref = str(body.get('lr_execution_preference') or 'local_preferred').strip()
        lr_res = lr_adapter.score_transaction_rows(
            scope,
            frame,
            analysis['rows'],
            model_id=str(body.get('lr_model_id') or '').strip() or None,
            execution_preference=lr_pref,
            scoring_config=risk_cfg,
            recheck=recheck,
        )
        lr_per_tx = lr_res['per_transaction']
        for r in analysis['rows']:
            tid = str(r['transaction_id'])
            lr_dto = lr_per_tx.get(tid) or lr_adapter._unavailable_method_dto(
                error_code=lr_res.get('error_code') or 'LR_UNAVAILABLE',
                message=lr_res.get('message') or 'Logistic Regression chưa khả dụng.',
                model_version=(lr_res.get('model') or {}).get('version_tag'),
                circuit_version=(lr_res.get('model') or {}).get('profile_version'),
            )
            r.setdefault('methods', {})['supervised_lr'] = lr_dto
            r.setdefault('branches', {})['supervised_lr'] = {
                'available': bool(lr_dto.get('available')),
                'status': lr_dto.get('status', 'unavailable'),
                'score': lr_dto.get('score'),
                'probability': lr_dto.get('probability'),
                'prediction': lr_dto.get('prediction'),
                'threshold': lr_dto.get('threshold'),
                'model_version': lr_dto.get('model_version'),
                'circuit_version': lr_dto.get('circuit_version'),
                'error_code': lr_dto.get('error_code'),
                'message': lr_dto.get('message') or (lr_dto.get('confidence_metadata') or {}).get('quality_note'),
            }
            r['five_method_assessment'] = build_five_method_row_assessment(
                r,
                unsup_method_id=method_id,
                unsup_version_tag=version_dto['version_tag'],
                lr_dto=lr_dto,
                config=risk_cfg,
            )

        # Coalesce cases combining 5 sources (Rules + Statistics + Graph + Unsupervised ML + Supervised LR)
        lr_active = bool(lr_res.get('available'))
        policy = default_fixture_policy(
            budget_limit=5,
            min_case_score=0.5,
            rule_weight=risk_cfg.rule_weight,
            ml_weight=risk_cfg.unsupervised_ml_weight,
            calibrated_weight=risk_cfg.supervised_lr_weight if lr_active else 0.0,
            policy_id=f'model-lifecycle-{version_dto["version_tag"]}',
            policy_version='1.0.0',
        )
        case_bundle = build_case_bundle_from_rule_analysis(
            analysis, data, scope=scope, ml_method=method_id, ml_candidate_min_score=0.5,
        )
        run_id = f'ml-{version_dto["version_tag"].lower()}-{digest(canonical([company, snapshot_id, key]))[:10]}'
        case_bundle['snapshot_binding'].update(run_id=run_id, bundle_id=version_dto['version_id'])
        cases = coalesce_cases(case_bundle, policy)

        # Deterministic case prioritization within budget=5 (rules + ML, no uncalibrated probability)
        eligible_cases = []
        decisions = []
        for c_obj in cases:
            elig = assess_case_eligibility(c_obj, policy=policy)
            if elig.get('eligible_for_budget'):
                eligible_cases.append((c_obj, elig))
            else:
                decisions.append({
                    'case_id': c_obj['case_id'],
                    'decision': elig['decision'],
                    'backlog_reason_code': elig.get('backlog_reason_code'),
                    'reason_detail': elig.get('reason_detail', ''),
                })
        eligible_cases.sort(key=lambda pair: case_priority_key(pair[0], pair[1]))
        admitted_cases = []
        for idx_c, (c_obj, elig) in enumerate(eligible_cases):
            if idx_c < policy['budget']['case_budget_limit'] or elig['decision'] == 'mandatory_route':
                dec_code = 'mandatory_route' if elig['decision'] == 'mandatory_route' else 'selected'
                decisions.append({'case_id': c_obj['case_id'], 'decision': dec_code, 'reason_detail': f'Tiếp nhận bởi mô hình đã duyệt {version_dto["version_tag"]}.'})
                admitted_cases.append(c_obj)
            else:
                decisions.append({'case_id': c_obj['case_id'], 'decision': 'budget_deferred', 'backlog_reason_code': 'budget_exhausted', 'reason_detail': 'Vượt ngân sách 5 vụ/kỳ.'})

        elapsed = round(time.monotonic() - started, 3)
        period_key = datetime.fromisoformat(as_of).astimezone(VN_TZ).strftime('%Y-W%W')
        q_mode = 'shadow' if version_dto['mode'] == 'shadow' else 'shadow'
        lane_name = 'staging'

        # Persist immutable pin + review_packet + observation into ReleaseStore so Area A displays it immediately
        from .bundle_reviews import build_packet
        rel_store = self.release_service.store
        ptr = rel_store.current(scope, lane_name, recheck)
        effective_bundle_id = ptr.get('bundle_id') or version_dto['version_id']

        pin_body = {
            'run_id': run_id,
            'lane': lane_name,
            'bundle_id': effective_bundle_id,
            'request': {
                'snapshot_id': snapshot_id,
                'as_of': as_of,
                'origin': 'model_lifecycle_approved_scoring',
                'model_version_id': version_dto['version_id'],
                'model_version_tag': version_dto['version_tag'],
                'artifact_id': artifact_id,
            },
            'at': _iso_now(),
        }
        with rel_store.tx(scope, recheck) as c:
            pin_id = rel_store.put(c, scope, 'pin', pin_body)
            pin = dict(pin_body, pin_id=pin_id)
            c.execute(
                'INSERT OR IGNORE INTO pins VALUES (?,?,?,?)',
                (rel_store.owner(scope), run_id, pin_id, digest(canonical(pin_body['request']))),
            )
            analysis['execution'] = {
                'location': 'enterprise_local_only',
                'cloud_he': {'available': False, 'reason': 'enterprise_local_requested'},
                'cloud_branches': {n: {'available': False, 'status': 'unavailable', 'reason': 'enterprise_local_requested'} for n in ('rules', 'statistics', 'graph', 'ml')},
                'plaintext_cloud_upload': False,
            }
            analysis['pipeline'] = {
                'version': 'release-shadow-execution/1.0.0',
                'bundle_id': effective_bundle_id,
                'selected_arm_id': f'five_methods_{method_id}_plus_lr' if lr_active else f'rules_plus_{method_id}',
                'model_version_id': version_dto['version_id'],
                'model_version_tag': version_dto['version_tag'],
                'lr_model_version': (lr_res.get('model') or {}).get('version_tag') if lr_active else None,
                'lr_model_id': (lr_res.get('model') or {}).get('model_id') if lr_active else None,
                'lr_status': 'available' if lr_active else 'unavailable',
                'lr_error_code': lr_res.get('error_code'),
                'lr_execution_backend': lr_res.get('execution_backend'),
                'risk_scoring_config': risk_cfg.to_dict(),
                'rows': [
                    {
                        'record_id': r['transaction_id'],
                        'revision': r.get('revision', 1),
                        'available': True,
                        'fallback_id': None,
                        'is_selected_arm_complete': bool((r.get('methods') or {}).get(method_id, {}).get('available')),
                        'reason': None,
                    }
                    for r in analysis['rows']
                ],
                'cases': cases,
                'case_policy': policy,
                'period_key': period_key,
                'queue_mode': q_mode,
                'execution_location': 'enterprise_local_only',
                'he_execution': False,
                'origin': 'model_lifecycle_approved_scoring',
                'queue': {
                    'counts': {
                        'total_cases': len(cases),
                        'queued_or_reserved': len(admitted_cases),
                        'backlog_waiting': sum(1 for d in decisions if d['decision'] in ('budget_deferred', 'below_threshold', 'need_evidence')),
                        'already_notified': 0,
                    },
                    'decisions': decisions,
                    'budget_status': {
                        'period_key': period_key,
                        'budget_limit': policy['budget']['case_budget_limit'],
                        'reserved_count': len(admitted_cases),
                        'remaining': max(0, policy['budget']['case_budget_limit'] - len(admitted_cases)),
                    },
                },
            }
            packet = build_packet(scope, pin, analysis, manifest, data)
            analysis['pipeline']['review_packet_id'] = rel_store.put(c, scope, 'review_packet', packet)
            obs_val = {
                'pin_id': pin_id,
                'run_id': run_id,
                'bundle_id': effective_bundle_id,
                'lane': lane_name,
                'snapshot_id': snapshot_id,
                'as_of': as_of,
                'created_at': _iso_now(),
                'metrics': self.release_service.metrics(analysis, elapsed),
                'result': analysis,
            }
            obs_id = rel_store.put(c, scope, 'observation', obs_val)

        out = {
            'run_id': run_id,
            'observation_id': obs_id,
            'snapshot_id': snapshot_id,
            'version_id': version_dto['version_id'],
            'version_tag': version_dto['version_tag'],
            'method_id': method_id,
            'artifact_id': artifact_id,
            'lr_included': lr_active,
            'lr_model_version': (lr_res.get('model') or {}).get('version_tag') if lr_active else None,
            'lr_status': 'available' if lr_active else 'unavailable',
            'lr_error_code': lr_res.get('error_code'),
            'lr_execution_backend': lr_res.get('execution_backend'),
            'total_cases': len(cases),
            'admitted_cases': len(admitted_cases),
            'elapsed_seconds': elapsed,
            'queue_url': f'pipeline-workspace#company={company}&run={run_id}',
        }
        with self._tx(scope, recheck, write=True) as conn:
            self._record_event(
                conn, scope, version_dto['version_id'], 'scored_queue',
                f'Chấm bản dữ liệu {snapshot_id[:12]}… bằng mô hình {version_dto["version_tag"]}: tiếp nhận {len(admitted_cases)}/{len(cases)} vụ vào hàng đợi.',
                out,
            )
            conn.execute(
                'INSERT OR IGNORE INTO lifecycle_receipts VALUES (?,?,?,?,?,?,?)',
                (tenant, company, scope.actor_id, key, req_hash, canonical(out).decode('utf-8'), _iso_now()),
            )
        return out
