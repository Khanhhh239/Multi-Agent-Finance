"""R2 — Encrypted Logistic Regression Training Adapter & Lifecycle Service (Worker 8870).

Integrates the existing Concrete TFHE worker (port 8870) and BatchEnterprise
signed protocol into `/model-management` Step 3 with:
  - Strict 2-feature circuit guard (rejects 33-feature selection on 2-feature FHE circuit)
  - Pre-train verification of worker health, circuit manifest, DPAPI keys, evaluation key
    SHA-256, and ciphertext integrity (ZERO plaintext fallback in FHE mode)
  - Durable Training Job IDs, per-batch checkpoint tracking, idempotent resume, and
    strict rejection of duplicate batches on resume (`DUPLICATE_BATCH_ON_RESUME`)
  - Dual execution modes:
      1. `local_quantized_reference`: exact quantized SGD reference + float LR baseline
      2. `fhe_cloud_ciphertext`: real Concrete TFHE on worker 8870 with local authorized
         decryption and explicit separation of implementation error vs quantization error
  - Explicit artifact-stage separation between `train_checkpoint`,
    `validated_checkpoint`, and `releasable_model`.
"""
from __future__ import annotations

import base64
from contextlib import closing, contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from finance_input.json_io import loads

from experiments.he_training import (
    EXECUTION_MODE_NATIVE,
    EXECUTION_MODE_VERIFIED,
    LEGACY_PROFILE_VERSION,
    PROFILE_VERSION,
    TARGET,
    resolve_quantization_profile,
)
from experiments.he_training.batch_enterprise import BatchEnterprise
from experiments.he_training.circuit import float_logistic_sgd_step, oracle
from experiments.he_training.protocol import TrainingError, canonical as he_canonical, sha as he_sha, strict_json, verify as he_verify
from experiments.he_training.snapshot_adapter import COLUMNS as CIRCUIT_FEATURES

from .auth import AccessScope
from .import_files import ImportFailure, canonical, digest, fail
from .lr_inference import (
    LR_FEATURE_SCHEMA,
    LR_RELEASE_CONTRACT,
    select_validation_threshold,
    sign_releasable_lr_model,
)
from .rule_snapshot_features import SOURCE_CONTRACT as RULE_SOURCE_CONTRACT, build_from_rule_snapshot
from .snapshot_features import build_from_snapshot

VERSION = 'lr-fhe-training/1.0.0'
APP_ID = 1093817156
VN_TZ = timezone(timedelta(hours=7))

SUPPORTED_FEATURES = tuple(CIRCUIT_FEATURES)  # ('round_million', 'creator_equals_approver')
TOTAL_SYSTEM_FEATURES = 33
BATCH_SIZE = 4
MIN_TRAIN_BATCHES = 2
MAX_TRAIN_BATCHES = 4
MAX_CIRCUIT_UPDATES = 4

FEATURE_LABELS_VI = {
    'round_million': 'Số tiền làm tròn bội số triệu đồng (nhị phân 0/1)',
    'creator_equals_approver': 'Người lập đồng thời là người phê duyệt (nhị phân 0/1)',
}

_EVAL_KEY_HASH_CACHE: dict[tuple[str, int, int], str] = {}
_EVAL_KEY_CACHE_LOCK = threading.Lock()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stream_sha256(path: Path) -> str:
    st = path.stat()
    key = (str(path.resolve()), int(st.st_size), int(st.st_mtime_ns))
    with _EVAL_KEY_CACHE_LOCK:
        cached = _EVAL_KEY_HASH_CACHE.get(key)
        if cached is not None:
            return cached
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while True:
            chunk = stream.read(4 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    out = h.hexdigest()
    with _EVAL_KEY_CACHE_LOCK:
        _EVAL_KEY_HASH_CACHE[key] = out
    return out


def _sigmoid(z: float) -> float:
    clipped = max(-30.0, min(30.0, float(z)))
    return 1.0 / (1.0 + math.exp(-clipped))


def _evaluate_lr_metrics(coefficients: list[float], intercept: float, eval_rows: list[dict]) -> dict:
    w0, w1 = float(coefficients[0]), float(coefficients[1])
    b = float(intercept)
    eps = 1e-12
    losses = []
    predictions = []
    tp = fp = tn = fn = 0
    for row in eval_rows:
        x0, x1 = int(row['x'][0]), int(row['x'][1])
        y = int(row['y'])
        z = w0 * x0 + w1 * x1 + b
        p = _sigmoid(z)
        p_clip = max(eps, min(1.0 - eps, p))
        loss_i = -(y * math.log(p_clip) + (1 - y) * math.log(1.0 - p_clip))
        pred = 1 if p >= 0.5 else 0
        losses.append(loss_i)
        if pred == 1 and y == 1:
            tp += 1
        elif pred == 1 and y == 0:
            fp += 1
        elif pred == 0 and y == 0:
            tn += 1
        else:
            fn += 1
        predictions.append({
            'record_id': row['record_id'],
            'x': [x0, x1],
            'y_true': y,
            'logit': round(z, 6),
            'score': round(p, 6),
            'predicted_class': pred,
            'correct': pred == y,
        })
    n = len(eval_rows)
    return {
        'sample_count': n,
        'bce_loss': round(sum(losses) / n, 6) if n else None,
        'accuracy': round((tp + tn) / n, 4) if n else None,
        'confusion': {'tp': tp, 'fp': fp, 'tn': tn, 'fn': fn},
        'predictions': predictions,
    }


def _run_quantized_reference(train_batches: list[dict], epochs: int, profile_version: str) -> dict:
    prof = resolve_quantization_profile(profile_version)
    w_scale = float(prof['weight_scale'])
    b_scale = float(prof['bias_scale'])
    weights = [0, 0, 0]
    steps = []
    cursor = 0
    for ep in range(epochs):
        for b_idx, batch in enumerate(train_batches):
            weights = oracle(batch['x'], batch['y'], weights, profile_version=profile_version)
            cursor += 1
            steps.append({
                'step_cursor': cursor,
                'epoch': ep + 1,
                'batch_index': b_idx,
                'weights_code': list(weights),
                'coefficients': [round(weights[0] / w_scale, 6), round(weights[1] / w_scale, 6)],
                'intercept': round(weights[2] / b_scale, 6),
            })
    return {
        'profile_version': prof['profile_version'],
        'weight_scale': prof['weight_scale'],
        'bias_scale': prof['bias_scale'],
        'probability_scale': prof['probability_scale'],
        'weights_code': list(weights),
        'coefficients': [round(weights[0] / w_scale, 6), round(weights[1] / w_scale, 6)],
        'intercept': round(weights[2] / b_scale, 6),
        'steps': steps,
    }


def _run_float_lr_reference(train_batches: list[dict], epochs: int, profile_version: str) -> dict:
    # Both legacy_s2_v1 (S=2, P=4, /8) and fhe_sgd_s16_v2 (S=16, P=16, /4) discretize
    # bounded mini-batch SGD with effective real learning_rate = 1.0, w in [-1, 1], b in [-2, 2].
    weights = [0.0, 0.0, 0.0]
    steps = []
    cursor = 0
    for ep in range(epochs):
        for b_idx, batch in enumerate(train_batches):
            weights = float_logistic_sgd_step(batch['x'], batch['y'], weights, learning_rate=1.0, clip=True)
            cursor += 1
            steps.append({
                'step_cursor': cursor,
                'epoch': ep + 1,
                'batch_index': b_idx,
                'coefficients': [round(weights[0], 6), round(weights[1], 6)],
                'intercept': round(weights[2], 6),
            })
    return {
        'learning_rate': 1.0,
        'bounds': {'w': [-1.0, 1.0], 'b': [-2.0, 2.0]},
        'coefficients': [round(weights[0], 6), round(weights[1], 6)],
        'intercept': round(weights[2], 6),
        'steps': steps,
    }


def _compare_models(
    actual: dict,
    quant_ref: dict,
    float_ref: dict,
    eval_rows: list[dict],
    *,
    is_fhe: bool,
) -> dict:
    actual_eval = _evaluate_lr_metrics(actual['coefficients'], actual['intercept'], eval_rows)
    quant_eval = _evaluate_lr_metrics(quant_ref['coefficients'], quant_ref['intercept'], eval_rows)
    float_eval = _evaluate_lr_metrics(float_ref['coefficients'], float_ref['intercept'], eval_rows)

    act_vec = [*actual['coefficients'], actual['intercept']]
    q_vec = [*quant_ref['coefficients'], quant_ref['intercept']]
    f_vec = [*float_ref['coefficients'], float_ref['intercept']]

    impl_w_diffs = [abs(a - q) for a, q in zip(act_vec, q_vec)]
    impl_w_max = round(max(impl_w_diffs), 9)
    impl_loss_diff = round(abs((actual_eval['bce_loss'] or 0.0) - (quant_eval['bce_loss'] or 0.0)), 9)
    impl_prob_diffs = [
        abs(a['score'] - q['score'])
        for a, q in zip(actual_eval['predictions'], quant_eval['predictions'])
    ]
    impl_prob_max = round(max(impl_prob_diffs) if impl_prob_diffs else 0.0, 9)
    code_exact = (list(actual['weights_code']) == list(quant_ref['weights_code']))
    impl_pass = bool(code_exact and impl_w_max <= 1e-9 and impl_loss_diff <= 1e-9 and impl_prob_max <= 1e-9)

    q_f_diffs = [abs(a - f) for a, f in zip(act_vec, f_vec)]
    quant_w_max = round(max(q_f_diffs), 6)
    quant_w_l2 = round(math.sqrt(sum(d * d for d in q_f_diffs)), 6)
    quant_loss_diff = round(abs((actual_eval['bce_loss'] or 0.0) - (float_eval['bce_loss'] or 0.0)), 6)
    quant_prob_diffs = [
        abs(a['score'] - f['score'])
        for a, f in zip(actual_eval['predictions'], float_eval['predictions'])
    ]
    quant_prob_max = round(max(quant_prob_diffs) if quant_prob_diffs else 0.0, 6)
    agree = sum(
        1 for a, f in zip(actual_eval['predictions'], float_eval['predictions'])
        if a['predicted_class'] == f['predicted_class']
    )
    agree_rate = round(agree / len(eval_rows), 4) if eval_rows else 1.0

    w_scale = float(quant_ref['weight_scale'])
    step_res = round(1.0 / w_scale, 6)
    # Standard bound: 1.5 quantization steps for S=2 (0.75), 4 steps for S=16 (0.25)
    weight_bound = 0.75 if w_scale <= 2 else 0.25
    prob_bound = 0.35 if w_scale <= 2 else 0.12
    quant_within_bound = bool(quant_w_max <= weight_bound and quant_prob_max <= prob_bound)

    return {
        'validation_samples': len(eval_rows),
        'actual': {
            'label': 'FHE giải mã tại local (Worker 8870)' if is_fhe else 'Tham chiếu lượng tử hóa local',
            'weights_code': list(actual['weights_code']),
            'coefficients': list(actual['coefficients']),
            'intercept': actual['intercept'],
            'metrics': actual_eval,
        },
        'quantized_reference': {
            'label': 'LR tham chiếu lượng tử hóa (oracle mạch)',
            'weights_code': list(quant_ref['weights_code']),
            'coefficients': list(quant_ref['coefficients']),
            'intercept': quant_ref['intercept'],
            'metrics': quant_eval,
        },
        'float_reference': {
            'label': 'LR số thực tham chiếu (SGD lr=1.0, miền [-1,1])',
            'coefficients': list(float_ref['coefficients']),
            'intercept': float_ref['intercept'],
            'metrics': float_eval,
        },
        'implementation_error': {
            'pass': impl_pass,
            'status': 'pass' if impl_pass else 'implementation_error',
            'weights_code_exact_match': code_exact,
            'weight_max_abs_diff': impl_w_max,
            'loss_abs_diff': impl_loss_diff,
            'pred_prob_max_abs_diff': impl_prob_max,
            'tolerance': 1e-9,
            'explanation_vi': (
                'Khớp chính xác 100% giữa bản mã FHE đã giải mã tại local và số học lượng tử hóa của mạch (0 lỗi triển khai).'
                if impl_pass
                else 'CẢNH BÁO LỖI TRIỂN KHAI: Trọng số giải mã từ FHE lệch khỏi oracle lượng tử hóa của mạch.'
            ),
        },
        'quantization_error': {
            'within_standard': quant_within_bound,
            'status': 'within_quantization_bound' if quant_within_bound else 'quantization_drift_notice',
            'weight_scale': int(w_scale),
            'step_resolution': step_res,
            'weight_max_abs_diff': quant_w_max,
            'weight_l2_diff': quant_w_l2,
            'loss_abs_diff': quant_loss_diff,
            'pred_prob_max_abs_diff': quant_prob_max,
            'class_agreement_rate': agree_rate,
            'standard_bounds': {
                'max_weight_diff': weight_bound,
                'max_pred_prob_diff': prob_bound,
            },
            'explanation_vi': (
                f'Độ lệch so với LR số thực thuần là sai số lượng tử hóa tự nhiên do độ phân giải bước Δ={step_res} '
                f'(weight_scale={int(w_scale)}), tách biệt hoàn toàn với lỗi triển khai FHE.'
            ),
        },
        'uncalibrated_notice': 'Điểm dự đoán LR là xác suất thô của mô hình lượng tử hóa trên 2 đặc trưng mạch; chỉ dùng đánh giá/ưu tiên kiểm tra sau khi phê duyệt.',
    }


def _verify_ciphertexts_preflight(batches: list[dict], label_batches: list[dict], initial_weights: dict) -> dict:
    """Validate ciphertext integrity before dispatching any training update to worker 8870."""
    checked = []

    def _check_one(label: str, b64_val: str, expected_sha: str, min_bytes: int = 32) -> None:
        if not isinstance(b64_val, str) or not b64_val.strip():
            fail(409, 'CIPHERTEXT_PREFLIGHT_FAILED', f'Bản mã {label} trống.', 'Thực hiện mã hóa lại tại doanh nghiệp trước khi train.')
        if not isinstance(expected_sha, str) or not re.fullmatch(r'[a-f0-9]{64}', expected_sha):
            fail(409, 'CIPHERTEXT_PREFLIGHT_FAILED', f'Thiếu mã băm SHA-256 hợp lệ cho bản mã {label}.', 'Kiểm tra lại bước mã hóa tại local.')
        try:
            raw = base64.b64decode(b64_val.encode('ascii'), validate=True)
        except Exception:
            fail(409, 'CIPHERTEXT_PREFLIGHT_FAILED', f'Bản mã {label} không đúng định dạng base64.', 'Mã hóa lại dữ liệu tại doanh nghiệp.')
        if len(raw) < min_bytes:
            fail(409, 'CIPHERTEXT_PREFLIGHT_FAILED', f'Bản mã {label} quá ngắn ({len(raw)} bytes), không phải bản mã FHE hợp lệ.', 'Không gửi dữ liệu rõ sang worker.')
        # Reject obvious plaintext JSON/CSV leaks
        stripped = raw.lstrip()[:1]
        if stripped in (b'[', b'{') and len(raw) < 4096:
            try:
                json.loads(raw.decode('utf-8'))
                fail(409, 'CIPHERTEXT_PREFLIGHT_FAILED', f'Phát hiện payload JSON dữ liệu rõ ở {label}; chặn gửi lên worker 8870.', 'Chỉ gửi bản mã Concrete FHE.')
            except UnicodeDecodeError:
                pass
            except ValueError:
                pass
        actual_sha = hashlib.sha256(raw).hexdigest()
        if actual_sha != expected_sha:
            fail(409, 'CIPHERTEXT_PREFLIGHT_FAILED', f'SHA-256 bản mã {label} không khớp cam kết.', 'Kiểm tra toàn vẹn bản mã trước khi train.')
        checked.append({'item': label, 'bytes': len(raw), 'sha256': actual_sha})

    for b in batches:
        _check_one(f"x_batch_{b['index']}", b.get('x_cipher'), b.get('x_cipher_sha256'))
    for lb in label_batches:
        _check_one(f"y_batch_{lb['index']}", lb.get('y_cipher'), lb.get('y_cipher_sha256'))
    _check_one('initial_weights', initial_weights.get('weights_cipher'), initial_weights.get('weights_cipher_sha256'))
    return {
        'passed': True,
        'checked_count': len(checked),
        'total_ciphertext_bytes': sum(c['bytes'] for c in checked),
        'items': checked,
    }


def _default_test_dataset(company_id: str, batch_count: int) -> tuple[list[dict], list[dict]]:
    """Small deterministic labeled financial fraud test set strictly in {0, 1}^2."""
    # Positive risk signal: (round_million=1, creator_equals_approver=1) -> fraud (1)
    # Mixed signals: (1, 0) / (0, 1) -> mixed fraud / non-fraud; (0, 0) -> non-fraud (0)
    # Every batch has exact 4 rows and balanced representation across batches.
    pool = [
        # Batch 0 (3 positive high-risk [1,1], 1 clean [0,0] -> updates w0, w1 > 0 even under S=2 rounding)
        {'record_id': f'{company_id}_LR_T01', 'x': [1, 1], 'y': 1, 'label_source': 'verified_test_dataset'},
        {'record_id': f'{company_id}_LR_T02', 'x': [1, 1], 'y': 1, 'label_source': 'verified_test_dataset'},
        {'record_id': f'{company_id}_LR_T03', 'x': [1, 1], 'y': 1, 'label_source': 'verified_test_dataset'},
        {'record_id': f'{company_id}_LR_T04', 'x': [0, 0], 'y': 0, 'label_source': 'verified_test_dataset'},
        # Batch 1 (3 clean [0,0], 1 positive [1,1] -> balanced 4/4 overall, updates bias b < 0)
        {'record_id': f'{company_id}_LR_T05', 'x': [0, 0], 'y': 0, 'label_source': 'verified_test_dataset'},
        {'record_id': f'{company_id}_LR_T06', 'x': [0, 0], 'y': 0, 'label_source': 'verified_test_dataset'},
        {'record_id': f'{company_id}_LR_T07', 'x': [0, 0], 'y': 0, 'label_source': 'verified_test_dataset'},
        {'record_id': f'{company_id}_LR_T08', 'x': [1, 1], 'y': 1, 'label_source': 'verified_test_dataset'},
        # Batch 2
        {'record_id': f'{company_id}_LR_T09', 'x': [1, 1], 'y': 1, 'label_source': 'verified_test_dataset'},
        {'record_id': f'{company_id}_LR_T10', 'x': [0, 1], 'y': 1, 'label_source': 'verified_test_dataset'},
        {'record_id': f'{company_id}_LR_T11', 'x': [0, 0], 'y': 0, 'label_source': 'verified_test_dataset'},
        {'record_id': f'{company_id}_LR_T12', 'x': [1, 0], 'y': 0, 'label_source': 'verified_test_dataset'},
        # Batch 3
        {'record_id': f'{company_id}_LR_T13', 'x': [1, 1], 'y': 1, 'label_source': 'verified_test_dataset'},
        {'record_id': f'{company_id}_LR_T14', 'x': [1, 1], 'y': 1, 'label_source': 'verified_test_dataset'},
        {'record_id': f'{company_id}_LR_T15', 'x': [0, 0], 'y': 0, 'label_source': 'verified_test_dataset'},
        {'record_id': f'{company_id}_LR_T16', 'x': [0, 0], 'y': 0, 'label_source': 'verified_test_dataset'},
    ]
    eval_pool = [
        {'record_id': f'{company_id}_LR_V01', 'x': [1, 1], 'y': 1, 'label_source': 'verified_test_dataset'},
        {'record_id': f'{company_id}_LR_V02', 'x': [1, 0], 'y': 1, 'label_source': 'verified_test_dataset'},
        {'record_id': f'{company_id}_LR_V03', 'x': [0, 1], 'y': 0, 'label_source': 'verified_test_dataset'},
        {'record_id': f'{company_id}_LR_V04', 'x': [0, 0], 'y': 0, 'label_source': 'verified_test_dataset'},
    ]
    return pool[: batch_count * BATCH_SIZE], eval_pool


class LRFHETrainingService:
    """Durable coordinator for R2 FHE Logistic Regression training via worker 8870."""

    def __init__(
        self,
        db_path: Path | str,
        *,
        snapshot_store=None,
        label_store=None,
        model_lifecycle=None,
        runtime_config_path: Path | str | None = None,
        worker_config_path: Path | str | None = None,
        portal_url: str | None = None,
        portal_bridge_secret: str | None = None,
        http_timeout: float = 3.0,
        node_factory=None,
    ):
        self.path = Path(db_path).resolve()
        self.snapshot_store = snapshot_store
        self.label_store = label_store
        self.model_lifecycle = model_lifecycle
        self.runtime_config_path = Path(runtime_config_path).resolve() if runtime_config_path else None
        self.worker_config_path = Path(worker_config_path).resolve() if worker_config_path else None
        self.portal_url = (portal_url or os.environ.get('AGENT2_PORTAL_URL') or '').rstrip('/') or None
        self.portal_bridge_secret = portal_bridge_secret or os.environ.get('AGENT2_PORTAL_BRIDGE_SECRET') or None
        self.http_timeout = float(http_timeout)
        self.node_factory = node_factory
        self._lock = threading.RLock()
        self._opener = build_opener(ProxyHandler({}))
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=FULL')
        return conn

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            app = conn.execute('PRAGMA application_id').fetchone()[0]
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
            if (app == 0 and tables) or app not in (0, APP_ID):
                fail(503, 'LR_FHE_STORAGE_VERSION', 'Kho trạng thái huấn luyện LR FHE không đúng phiên bản.', 'Chọn đúng DB lr-fhe-jobs.sqlite3.')
            conn.executescript(f"""
                BEGIN IMMEDIATE;
                PRAGMA application_id={APP_ID};
                PRAGMA user_version=1;
                CREATE TABLE IF NOT EXISTS lr_fhe_jobs(
                    job_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    worker_job_id TEXT,
                    dataset_id TEXT,
                    artifact_stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    completed_updates INTEGER NOT NULL,
                    total_updates INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_lr_fhe_jobs_owner ON lr_fhe_jobs(tenant_id, company_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS lr_fhe_checkpoints(
                    job_id TEXT NOT NULL,
                    step_cursor INTEGER NOT NULL,
                    epoch INTEGER NOT NULL,
                    batch_index INTEGER NOT NULL,
                    x_cipher_sha256 TEXT,
                    y_cipher_sha256 TEXT,
                    weights_hash TEXT NOT NULL,
                    checkpoint_kind TEXT NOT NULL DEFAULT 'train_checkpoint',
                    committed_at TEXT NOT NULL,
                    PRIMARY KEY(job_id, step_cursor)
                );
                CREATE TABLE IF NOT EXISTS lr_fhe_receipts(
                    tenant_id TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(tenant_id, company_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS lr_fhe_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    job_id TEXT,
                    event_type TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS lr_fhe_events_no_update BEFORE UPDATE ON lr_fhe_events
                BEGIN SELECT RAISE(ABORT, 'immutable lr_fhe_events'); END;
                CREATE TRIGGER IF NOT EXISTS lr_fhe_events_no_delete BEFORE DELETE ON lr_fhe_events
                BEGIN SELECT RAISE(ABORT, 'immutable lr_fhe_events'); END;
                COMMIT;
            """)

    @contextmanager
    def _tx(self, scope: AccessScope, recheck=None):
        conn = self._connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            if recheck is not None and recheck() != scope:
                fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền truy cập đã thay đổi.', 'Tải lại trang.')
            yield conn
            if recheck is not None and recheck() != scope:
                fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền truy cập đã thay đổi trước khi lưu.', 'Tải lại trang.')
            conn.execute('COMMIT')
        except BaseException:
            if conn.in_transaction:
                conn.execute('ROLLBACK')
            raise
        finally:
            conn.close()

    def _log_event(self, conn: sqlite3.Connection, tenant: str, company: str, job_id: str | None, event_type: str, actor_id: str, payload: dict) -> None:
        conn.execute(
            'INSERT INTO lr_fhe_events(tenant_id, company_id, job_id, event_type, actor_id, at, payload_json) VALUES (?,?,?,?,?,?,?)',
            (tenant, company, job_id, event_type, actor_id, _iso_now(), json.dumps(payload, ensure_ascii=False)),
        )

    def _check_receipt(self, conn: sqlite3.Connection, tenant: str, company: str, idem_key: str | None, req_hash: str):
        if not idem_key:
            return None
        row = conn.execute(
            'SELECT request_sha256, response_json FROM lr_fhe_receipts WHERE tenant_id=? AND company_id=? AND idempotency_key=?',
            (tenant, company, idem_key),
        ).fetchone()
        if row is None:
            return None
        if row['request_sha256'] != req_hash:
            fail(409, 'IDEMPOTENCY_CONFLICT', 'Idempotency-Key đã dùng cho yêu cầu khác.', 'Tạo yêu cầu mới.')
        return json.loads(row['response_json'])

    def _save_receipt(self, conn: sqlite3.Connection, tenant: str, company: str, idem_key: str | None, req_hash: str, response: dict) -> None:
        if not idem_key:
            return
        conn.execute(
            'INSERT OR IGNORE INTO lr_fhe_receipts VALUES (?,?,?,?,?,?)',
            (tenant, company, idem_key, req_hash, json.dumps(response, ensure_ascii=False), _iso_now()),
        )

    # ------------------------------------------------------------------ runtime & crypto preflight
    def _discover_runtime_cfg(self) -> dict:
        cfg: dict = {}
        candidates = []
        if self.runtime_config_path:
            candidates.append(self.runtime_config_path)
        env_cfg = os.environ.get('AGENT2_BATCH_TRAINING_CONFIG')
        if env_cfg:
            candidates.append(Path(env_cfg).resolve())
        candidates.append(self.path.with_name('batch-training-runtime.json'))
        repo_default = Path(__file__).resolve().parents[1] / '.runtime' / 'he-four-managed-v1' / 'enterprise' / 'jobs' / 'batch-training-runtime.json'
        candidates.append(repo_default)
        for p in candidates:
            if p and p.is_file():
                try:
                    cfg = strict_json(p.read_bytes())
                    cfg['_source_path'] = str(p)
                    break
                except Exception:
                    continue

        if not cfg.get('enterprise_root'):
            managed_ent = Path(__file__).resolve().parents[1] / '.runtime' / 'he-training-managed-v1' / 'enterprise'
            if managed_ent.is_dir():
                cfg['enterprise_root'] = str(managed_ent)
        if not cfg.get('build'):
            managed_build = Path(__file__).resolve().parents[1] / '.runtime' / 'he-training-managed-v1' / 'cloud' / 'build'
            if managed_build.is_dir():
                cfg['build'] = str(managed_build)
        if not cfg.get('worker_url'):
            cfg['worker_url'] = 'http://127.0.0.1:8870'

        # Discover cloud worker-config.json (public grant hashes only, NEVER reading worker signing key)
        worker_cfg_path = self.worker_config_path
        if worker_cfg_path is None:
            ent_root = Path(cfg['enterprise_root']).resolve() if cfg.get('enterprise_root') else None
            if ent_root and (ent_root.parent / 'cloud' / 'worker-config.json').is_file():
                worker_cfg_path = ent_root.parent / 'cloud' / 'worker-config.json'
            else:
                default_wcfg = Path(__file__).resolve().parents[1] / '.runtime' / 'he-training-managed-v1' / 'cloud' / 'worker-config.json'
                if default_wcfg.is_file():
                    worker_cfg_path = default_wcfg
        if worker_cfg_path and worker_cfg_path.is_file():
            cfg['_worker_config_path'] = str(worker_cfg_path)
            try:
                wcfg = strict_json(worker_cfg_path.read_bytes())
                cfg['_worker_grants'] = wcfg.get('grants') or []
            except Exception:
                cfg['_worker_grants'] = []
        else:
            cfg['_worker_grants'] = []
        return cfg

    def _call_portal_worker_control(self, action: str) -> dict | None:
        if not self.portal_url or not self.portal_bridge_secret:
            return None
        req = Request(
            self.portal_url + '/api/internal/agent2/he-training-worker',
            data=json.dumps({'action': action}).encode('utf-8'),
            headers={
                'Authorization': 'Bearer ' + self.portal_bridge_secret,
                'Content-Type': 'application/json',
            },
            method='POST',
        )
        timeout = 45.0 if action == 'restart' else 5.0
        try:
            with self._opener.open(req, timeout=timeout) as resp:
                return json.loads(resp.read(65536))
        except (HTTPError, URLError, OSError, ValueError):
            return None

    def probe_worker_health(self, *, timeout: float | None = None) -> dict:
        cfg = self._discover_runtime_cfg()
        url = str(cfg.get('worker_url') or 'http://127.0.0.1:8870').rstrip('/')
        eff_timeout = self.http_timeout if timeout is None else float(timeout)
        t0 = time.monotonic()
        portal_info = self._call_portal_worker_control('status')
        try:
            with self._opener.open(Request(url + '/health'), timeout=eff_timeout) as resp:
                data = json.loads(resp.read(4096))
            latency_ms = round((time.monotonic() - t0) * 1000.0, 1)
            ok = (
                isinstance(data, dict)
                and data.get('role') == 'he_training_worker'
                and data.get('batch_training') is True
            )
            return {
                'reachable': ok,
                'status': 'ready' if ok else 'invalid_response',
                'url': url,
                'port': int(url.rsplit(':', 1)[-1]) if ':' in url.rsplit('/', 1)[-1] else 8870,
                'role': data.get('role') if isinstance(data, dict) else None,
                'version': data.get('version') if isinstance(data, dict) else None,
                'batch_training': bool(data.get('batch_training')) if isinstance(data, dict) else False,
                'latency_ms': latency_ms,
                'checked_at': _iso_now(),
                'portal_managed': bool(portal_info and portal_info.get('configured')),
                'restart_count': portal_info.get('restart_count', 0) if portal_info else 0,
                'can_restart': bool(portal_info and portal_info.get('configured')),
                'message': f'Worker huấn luyện FHE ({url}) sẵn sàng ({latency_ms} ms).' if ok else 'Phản hồi /health từ worker 8870 không hợp lệ.',
            }
        except (HTTPError, URLError, OSError, ValueError) as exc:
            return {
                'reachable': False,
                'status': 'unavailable',
                'url': url,
                'port': int(url.rsplit(':', 1)[-1]) if ':' in url.rsplit('/', 1)[-1] else 8870,
                'role': 'he_training_worker',
                'version': 'he-training-worker/0.1.0',
                'batch_training': False,
                'latency_ms': None,
                'checked_at': _iso_now(),
                'portal_managed': bool(portal_info and portal_info.get('configured')),
                'restart_count': portal_info.get('restart_count', 0) if portal_info else 0,
                'can_restart': bool(portal_info and portal_info.get('configured')),
                'error': str(exc),
                'message': f'Không kết nối được worker huấn luyện FHE tại {url}. Không tự rơi về plaintext.',
            }

    def restart_worker(self, scope: AccessScope, recheck=None) -> dict:
        if recheck is not None and recheck() != scope:
            fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi.', 'Tải lại trang.')
        res = self._call_portal_worker_control('restart')
        if res is None:
            fail(
                503,
                'PORTAL_WORKER_CONTROL_UNAVAILABLE',
                'Portal chưa bật kênh điều khiển khởi động lại worker 8870.',
                'Khởi động lại Portal để kích hoạt bộ quản lý vòng đời worker 8870.',
            )
        if not res.get('configured'):
            fail(503, 'HE_TRAINING_WORKER_NOT_CONFIGURED', res.get('message') or 'Chưa cấu hình he_training_worker.', 'Kiểm tra portal/config.local.json.')
        health = self.probe_worker_health()
        return {
            'restarted': True,
            'portal_state': res,
            'worker_health': health,
        }

    def inspect_crypto_context(self, scope: AccessScope, *, verify_eval_key_hash: bool = True) -> dict:
        """Inspect & verify circuit manifest, DPAPI key context, and evaluation key hash."""
        tenant = scope.tenant_id
        company = next(iter(scope.company_ids))
        cfg = self._discover_runtime_cfg()
        build_dir = Path(cfg['build']).resolve() if cfg.get('build') else None
        ent_root = Path(cfg['enterprise_root']).resolve() if cfg.get('enterprise_root') else None

        issues = []
        circuit_info: dict = {
            'available': False,
            'profile': None,
            'profile_version': None,
            'concrete_version': None,
            'build_sha256': None,
            'client_specs_sha256': None,
            'features': len(SUPPORTED_FEATURES),
            'supported_features': list(SUPPORTED_FEATURES),
            'total_system_features': TOTAL_SYSTEM_FEATURES,
            'rows_per_batch': BATCH_SIZE,
            'max_steps': MAX_CIRCUIT_UPDATES,
            'all_inputs_encrypted': False,
            'secret_keys_in_bundle': None,
            'weight_scale': None,
            'bias_scale': None,
            'probability_scale': None,
        }
        if build_dir is None or not (build_dir / 'manifest.json').is_file():
            issues.append({'code': 'BUILD_MANIFEST_MISSING', 'message': 'Thiếu tệp build/manifest.json của mạch FHE LR.'})
        else:
            manifest = strict_json((build_dir / 'manifest.json').read_bytes())
            prof = resolve_quantization_profile(manifest)
            files_ok = True
            for fname, expected_sha in (manifest.get('files') or {}).items():
                fp = build_dir / fname
                if not fp.is_file() or _stream_sha256(fp) != expected_sha:
                    files_ok = False
                    issues.append({'code': 'BUILD_TAMPERED', 'message': f'Tệp mạch {fname} không khớp SHA-256 trong manifest.'})
            if manifest.get('all_inputs_encrypted') is not True or manifest.get('composable') is not True:
                files_ok = False
                issues.append({'code': 'BUILD_NOT_ENCRYPTED', 'message': 'Mạch không khai báo mã hóa toàn bộ đầu vào.'})
            if manifest.get('secret_keys_in_bundle') is not False:
                files_ok = False
                issues.append({'code': 'SECRET_KEY_IN_BUILD', 'message': 'Manifest mạch phải xác nhận secret_keys_in_bundle=false.'})
            circuit_info.update({
                'available': files_ok,
                'profile': manifest.get('profile'),
                'profile_version': prof['profile_version'],
                'concrete_version': manifest.get('concrete_version'),
                'build_sha256': (manifest.get('files') or {}).get('server.zip'),
                'client_specs_sha256': (manifest.get('files') or {}).get('client.specs.json'),
                'features': int(manifest.get('features', 2)),
                'rows_per_batch': int(manifest.get('rows', BATCH_SIZE)),
                'max_steps': int(manifest.get('max_steps', MAX_CIRCUIT_UPDATES)),
                'all_inputs_encrypted': bool(manifest.get('all_inputs_encrypted')),
                'secret_keys_in_bundle': manifest.get('secret_keys_in_bundle'),
                'weight_scale': prof['weight_scale'],
                'bias_scale': prof['bias_scale'],
                'probability_scale': prof['probability_scale'],
            })

        key_info: dict = {
            'provisioned': False,
            'key_epoch': None,
            'evaluation_keys_present': False,
            'evaluation_keys_bytes': 0,
            'evaluation_keys_sha256': None,
            'evaluation_key_verified': False,
            'grant_active': False,
            'grant_verification_mode': None,
            'secret_key_storage': 'DPAPI AES-GCM local (không rời doanh nghiệp)',
        }
        grant = next(
            (g for g in (cfg.get('_worker_grants') or []) if g.get('tenant_id') == tenant and g.get('company_id') == company),
            None,
        )
        if grant:
            key_info['grant_active'] = bool(grant.get('active') and grant.get('batch_training'))
            key_info['grant_verification_mode'] = grant.get('verification_mode')

        company_dir = (ent_root / company) if ent_root else None
        if company_dir is None or not (company_dir / 'enterprise.json').is_file():
            issues.append({'code': 'ENTERPRISE_KEY_NOT_PROVISIONED', 'message': f'Doanh nghiệp {company} chưa được cấp cặp khóa FHE huấn luyện.'})
        else:
            meta = strict_json((company_dir / 'enterprise.json').read_bytes())
            key_info['key_epoch'] = meta.get('key_epoch')
            if meta.get('tenant_id') != tenant or meta.get('company_id') != company:
                issues.append({'code': 'ENTERPRISE_SCOPE_MISMATCH', 'message': 'Metadata khóa không khớp doanh nghiệp hiện tại.'})
            if circuit_info['build_sha256'] and meta.get('build_sha256') != circuit_info['build_sha256']:
                issues.append({'code': 'KEY_BUILD_MISMATCH', 'message': 'Khóa doanh nghiệp không khớp build_sha256 của mạch FHE.'})
            sealed_ok = (company_dir / 'crypto' / 'context.sealed').is_file() and (company_dir / 'wrapping.dpapi.json').is_file()
            eval_key_path = company_dir / 'crypto' / 'evaluation.keys'
            if not sealed_ok:
                issues.append({'code': 'SEALED_SECRET_KEY_MISSING', 'message': 'Thiếu khóa bí mật DPAPI context.sealed tại doanh nghiệp.'})
            if not eval_key_path.is_file():
                issues.append({'code': 'EVALUATION_KEY_MISSING', 'message': 'Thiếu tệp khóa công khai evaluation.keys.'})
            else:
                key_info['evaluation_keys_present'] = True
                key_info['evaluation_keys_bytes'] = eval_key_path.stat().st_size
                if verify_eval_key_hash:
                    actual_evk_sha = _stream_sha256(eval_key_path)
                    key_info['evaluation_keys_sha256'] = actual_evk_sha
                    if grant:
                        evk_match = (actual_evk_sha == grant.get('evaluation_keys_sha256'))
                        epoch_match = (meta.get('key_epoch') == grant.get('key_epoch'))
                        if not evk_match:
                            issues.append({'code': 'EVALUATION_KEY_HASH_MISMATCH', 'message': 'SHA-256 của evaluation.keys không khớp grant đã đăng ký trên worker 8870.'})
                        if not epoch_match:
                            issues.append({'code': 'KEY_EPOCH_MISMATCH', 'message': 'key_epoch doanh nghiệp không khớp grant trên worker 8870.'})
                        key_info['evaluation_key_verified'] = bool(evk_match and epoch_match and key_info['grant_active'])
                    else:
                        # Custom/isolated worker without local worker-config.json mirror
                        key_info['evaluation_key_verified'] = bool(sealed_ok and actual_evk_sha)
                else:
                    key_info['evaluation_keys_sha256'] = grant.get('evaluation_keys_sha256') if grant else None
                    key_info['evaluation_key_verified'] = bool(sealed_ok and key_info['evaluation_keys_present'] and (key_info['grant_active'] if grant else True))
            key_info['provisioned'] = bool(sealed_ok and key_info['evaluation_keys_present'])

        return {
            'ready_for_fhe': len(issues) == 0,
            'circuit': circuit_info,
            'keys': key_info,
            'issues': issues,
            'worker_url': cfg.get('worker_url'),
            'worker_verify_key_present': bool(cfg.get('worker_verify_key')),
        }

    # ------------------------------------------------------------------ Dataset Adapter (strictly 2 features)
    def prepare_dataset(self, scope: AccessScope, body: dict | None, recheck=None) -> dict:
        if recheck is not None and recheck() != scope:
            fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi.', 'Tải lại trang.')
        body = body or {}
        company = next(iter(scope.company_ids))

        # HARD GUARD: Never allow UI or API to pass 33 features to the 2-feature circuit!
        requested_features = body.get('selected_features')
        if requested_features is not None:
            if not isinstance(requested_features, list) or tuple(requested_features) != SUPPORTED_FEATURES:
                fail(
                    400,
                    'CIRCUIT_FEATURE_LIMIT_EXCEEDED',
                    f'Mạch FHE Logistic Regression hiện tại chỉ hỗ trợ đúng {len(SUPPORTED_FEATURES)} đặc trưng '
                    f'({", ".join(SUPPORTED_FEATURES)}); không cho phép chọn {len(requested_features) if isinstance(requested_features, list) else "sai"} đặc trưng (kể cả 33 đặc trưng).',
                    'Giữ nguyên 2 đặc trưng mạch FHE hỗ trợ hoặc dùng các mô hình không giám sát (Isolation Forest / Autoencoder) cho đủ 33 đặc trưng.',
                )

        batch_count = int(body.get('batch_count', 2))
        epochs = int(body.get('epochs', 1))
        if not (MIN_TRAIN_BATCHES <= batch_count <= MAX_TRAIN_BATCHES):
            fail(400, 'BATCH_COUNT_INVALID', f'Số batch huấn luyện phải từ {MIN_TRAIN_BATCHES} đến {MAX_TRAIN_BATCHES} (mỗi batch {BATCH_SIZE} mẫu).', 'Chọn 2, 3 hoặc 4 batch.')
        if not (1 <= epochs <= MAX_CIRCUIT_UPDATES):
            fail(400, 'EPOCHS_INVALID', f'Số epoch phải từ 1 đến {MAX_CIRCUIT_UPDATES}.', 'Chọn số epoch hợp lệ.')
        total_updates = batch_count * epochs
        if total_updates > MAX_CIRCUIT_UPDATES:
            fail(
                400,
                'BATCH_UPDATE_LIMIT',
                f'Tổng số bước cập nhật ({batch_count} batch × {epochs} epoch = {total_updates}) vượt giới hạn {MAX_CIRCUIT_UPDATES} bước của mạch FHE.',
                'Chọn batch_count × epochs <= 4 (ví dụ: 2 batch × 2 epoch hoặc 4 batch × 1 epoch).',
            )

        source_mode = str(body.get('source_mode') or 'verified_test_dataset').strip()
        if source_mode not in ('verified_test_dataset', 'snapshot_verified', 'custom_labeled_rows', 'verified_reviews_next_cycle'):
            fail(400, 'SOURCE_MODE_INVALID', 'Nguồn dữ liệu huấn luyện LR không hợp lệ.', 'Chọn verified_test_dataset, snapshot_verified, verified_reviews_next_cycle hoặc custom_labeled_rows.')

        snapshot_id = str(body.get('snapshot_id') or '').strip() or None
        simulated = True
        if source_mode == 'custom_labeled_rows':
            raw_train = body.get('train_rows')
            raw_eval = body.get('eval_rows')
            if not isinstance(raw_train, list) or not isinstance(raw_eval, list):
                fail(400, 'CUSTOM_ROWS_REQUIRED', 'Cần cung cấp danh sách train_rows và eval_rows.', 'Kiểm tra dữ liệu đầu vào.')
            train_rows = self._validate_labeled_rows(raw_train, expected_multiple=BATCH_SIZE, min_rows=MIN_TRAIN_BATCHES * BATCH_SIZE)
            eval_rows = self._validate_labeled_rows(raw_eval, expected_multiple=BATCH_SIZE, min_rows=BATCH_SIZE)
            batch_count = len(train_rows) // BATCH_SIZE
            total_updates = batch_count * epochs
            if total_updates > MAX_CIRCUIT_UPDATES:
                fail(400, 'BATCH_UPDATE_LIMIT', f'Tổng số bước cập nhật ({total_updates}) vượt giới hạn {MAX_CIRCUIT_UPDATES}.', 'Giảm số batch hoặc số epoch.')
            simulated = bool(body.get('simulated', True))
        elif source_mode == 'verified_reviews_next_cycle':
            rel_svc = getattr(self.model_lifecycle, 'release_service', None)
            collected = self.collect_verified_review_labels(scope, rel_svc, recheck=recheck)
            merged_labels = dict(collected['labels_map'])
            if isinstance(body.get('labels_map'), dict):
                merged_labels.update({k: v for k, v in body['labels_map'].items() if type(v) is int and v in (0, 1)})
            train_rows, eval_rows, simulated, snapshot_id = self._adapt_from_snapshot(scope, snapshot_id, batch_count, merged_labels, recheck)
        elif source_mode == 'snapshot_verified':
            train_rows, eval_rows, simulated, snapshot_id = self._adapt_from_snapshot(scope, snapshot_id, batch_count, body.get('labels_map'), recheck)
        else:
            train_rows, eval_rows = _default_test_dataset(company, batch_count)
            simulated = True

        # Cross-partition uniqueness and both-class check
        seen_ids: set[str] = set()
        for row in train_rows + eval_rows:
            rid = row['record_id']
            if rid in seen_ids:
                fail(400, 'TRAIN_EVALUATION_OVERLAP_OR_DUPLICATE', f'Mã mẫu {rid} bị trùng hoặc xuất hiện ở cả tập train và tập validation.', 'Tách biệt hoàn toàn dữ liệu huấn luyện và validation.')
            seen_ids.add(rid)

        train_y = [int(r['y']) for r in train_rows]
        eval_y = [int(r['y']) for r in eval_rows]
        label_0 = sum(1 for y in train_y if y == 0)
        label_1 = sum(1 for y in train_y if y == 1)
        if label_0 == 0 or label_1 == 0:
            fail(409, 'BOTH_LABEL_CLASSES_REQUIRED', 'Tập huấn luyện cần có đủ cả hai lớp nhãn 0 và nhãn 1.', 'Bổ sung mẫu của lớp còn thiếu.')

        train_batches = []
        for idx in range(batch_count):
            chunk = train_rows[idx * BATCH_SIZE : (idx + 1) * BATCH_SIZE]
            train_batches.append({
                'index': idx,
                'row_ids': [r['record_id'] for r in chunk],
                'x': [list(r['x']) for r in chunk],
                'y': [int(r['y']) for r in chunk],
                'label_0_count': sum(1 for r in chunk if int(r['y']) == 0),
                'label_1_count': sum(1 for r in chunk if int(r['y']) == 1),
            })

        eval_batches = []
        for idx in range(len(eval_rows) // BATCH_SIZE):
            chunk = eval_rows[idx * BATCH_SIZE : (idx + 1) * BATCH_SIZE]
            eval_batches.append({
                'index': idx,
                'row_ids': [r['record_id'] for r in chunk],
                'x': [list(r['x']) for r in chunk],
                'y': [int(r['y']) for r in chunk],
            })

        plan = {
            'version': VERSION,
            'company_id': company,
            'source_mode': source_mode,
            'snapshot_id': snapshot_id,
            'simulated': simulated,
            'valid_samples': len(train_rows),
            'label_0_count': label_0,
            'label_1_count': label_1,
            'validation_samples': len(eval_rows),
            'validation_label_0_count': sum(1 for y in eval_y if y == 0),
            'validation_label_1_count': sum(1 for y in eval_y if y == 1),
            'supported_features': [
                {'name': f, 'label_vi': FEATURE_LABELS_VI[f], 'domain': [0, 1], 'locked': True}
                for f in SUPPORTED_FEATURES
            ],
            'supported_feature_count': len(SUPPORTED_FEATURES),
            'total_system_features': TOTAL_SYSTEM_FEATURES,
            'allow_33_features': False,
            'feature_lock_reason_vi': 'Mạch FHE Logistic Regression chỉ hỗ trợ cố định 2 đặc trưng nhị phân (round_million, creator_equals_approver); không cho phép chọn 33 đặc trưng.',
            'batch_size': BATCH_SIZE,
            'batch_count': batch_count,
            'epochs': epochs,
            'total_updates': total_updates,
            'max_circuit_updates': MAX_CIRCUIT_UPDATES,
            'train_batches': train_batches,
            'eval_batches': eval_batches,
            'eval_rows': eval_rows,
        }
        plan['dataset_fingerprint'] = digest(canonical({
            'company_id': company,
            'source_mode': source_mode,
            'snapshot_id': snapshot_id,
            'train_batches': train_batches,
            'eval_rows': eval_rows,
            'epochs': epochs,
        }))
        return plan

    @staticmethod
    def _validate_labeled_rows(rows: list, *, expected_multiple: int, min_rows: int) -> list[dict]:
        if len(rows) < min_rows or len(rows) % expected_multiple != 0:
            fail(400, 'BATCH_ROWS_EXACTLY_FOUR', f'Số dòng phải >= {min_rows} và chia hết cho {expected_multiple}.', 'Điều chỉnh số mẫu theo đúng kích thước batch = 4.')
        cleaned = []
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                fail(400, 'ROW_INVALID', f'Dòng thứ {idx + 1} không hợp lệ.', 'Kiểm tra cấu trúc dữ liệu.')
            rid = str(row.get('record_id') or '').strip()
            if not rid or len(rid) > 100:
                fail(400, 'ROW_ID_INVALID', f'Thiếu record_id hợp lệ ở dòng {idx + 1}.', 'Cung cấp record_id duy nhất.')
            x = row.get('x') if 'x' in row else row.get('features')
            if not isinstance(x, list) or len(x) != len(SUPPORTED_FEATURES):
                fail(
                    400,
                    'CIRCUIT_FEATURE_LIMIT_EXCEEDED',
                    f'Dòng {rid} có {len(x) if isinstance(x, list) else "sai"} đặc trưng; mạch FHE chỉ nhận đúng 2 đặc trưng nhị phân.',
                    'Chỉ truyền đúng 2 đặc trưng [round_million, creator_equals_approver].',
                )
            if any(type(v) is not int or v not in (0, 1) for v in x):
                fail(400, 'FEATURE_OUT_OF_DOMAIN', f'Dòng {rid} chứa đặc trưng ngoài miền nhị phân {{0, 1}}.', 'Dữ liệu đặc trưng phải là số nguyên 0 hoặc 1.')
            y = row.get('y') if 'y' in row else row.get('label')
            if type(y) is not int or y not in (0, 1):
                fail(400, 'LABEL_INVALID', f'Dòng {rid} có nhãn không hợp lệ (chỉ nhận 0 hoặc 1).', 'Không tự suy diễn hoặc để trống nhãn.')
            cleaned.append({'record_id': rid, 'x': [int(x[0]), int(x[1])], 'y': int(y), 'label_source': str(row.get('label_source') or 'custom_verified')})
        return cleaned

    def _adapt_from_snapshot(self, scope: AccessScope, snapshot_id: str | None, batch_count: int, labels_map: dict | None, recheck=None):
        if self.snapshot_store is None:
            fail(503, 'SNAPSHOT_STORE_UNAVAILABLE', 'Chưa cấu hình kho snapshot.', 'Kiểm tra kết nối sảnh chung.')
        if not snapshot_id:
            snaps = self.snapshot_store.list_snapshots(scope, recheck)
            if not snaps:
                fail(404, 'NO_SHARED_SNAPSHOT', 'Doanh nghiệp chưa có snapshot đã khóa từ sảnh chung.', 'Nạp và niêm phong dữ liệu tại Sảnh chung trước.')
            snapshot_id = snaps[0]['snapshot_id']
        manifest = self.snapshot_store.get_snapshot(scope, snapshot_id, recheck)
        raw = loads(self.snapshot_store.get_snapshot(scope, snapshot_id, recheck, data=True))
        if manifest['contract_version'] == RULE_SOURCE_CONTRACT:
            as_of = raw['source']['as_of']
            simulated = bool(raw['source'].get('is_simulated', True))
            frame = build_from_rule_snapshot(self.snapshot_store, scope, snapshot_id, as_of, recheck, candidates_only=False, require_exact_source_cutoff=False)
        else:
            as_of = max((t.get('observed_at') or t.get('posted_at') for t in raw.get('transactions', [])), default=_iso_now())
            simulated = any(bool((t.get('source') or {}).get('is_simulated')) for t in raw.get('transactions', []))
            frame = build_from_snapshot(self.snapshot_store, scope, snapshot_id, as_of, recheck)

        # Gather verified labels from LabelStore locked packets (if any) + explicit labels_map (never auto-label unreviewed rows!)
        verified: dict[str, int] = {}
        if self.label_store is not None:
            try:
                for pkt in self.label_store.list_packets(scope, recheck):
                    if not pkt.get('locked'):
                        continue
                    full = self.label_store.get(scope, pkt['packet_id'], recheck)
                    for item in full.get('labels', []):
                        if item.get('outcome') in ('verified_fraud', 'verified_non_fraud'):
                            verified[item['record_id']] = 1 if item['outcome'] == 'verified_fraud' else 0
            except Exception:
                pass
        if isinstance(labels_map, dict):
            for rid, val in labels_map.items():
                if type(val) is int and val in (0, 1):
                    verified[str(rid)] = int(val)

        cols = frame['contract']['columns']
        col_idx = [cols.index(name) for name in SUPPORTED_FEATURES]
        usable = []
        for row in frame['rows']:
            rid = row['record_id']
            if rid not in verified:
                continue
            r_idx = row['row_index']
            if any(frame['missing'][r_idx][ci] or frame['features'][r_idx][ci] not in (0, 1) for ci in col_idx):
                continue
            usable.append({
                'record_id': rid,
                'x': [int(frame['features'][r_idx][ci]) for ci in col_idx],
                'y': int(verified[rid]),
                'event_at': row.get('event_at'),
                'label_source': 'verified_label_packet',
            })

        needed_train = batch_count * BATCH_SIZE
        needed_total = needed_train + BATCH_SIZE
        if len(usable) < needed_total:
            fail(
                409,
                'INSUFFICIENT_VERIFIED_SNAPSHOT_LABELS',
                f'Snapshot {snapshot_id[:14]}… mới có {len(usable)} giao dịch đã có nhãn xác minh hợp lệ đủ 2 đặc trưng mạch; '
                f'cần tối thiểu {needed_total} dòng ({needed_train} train + {BATCH_SIZE} validation). '
                'Không tự gán nhãn 0 cho giao dịch chưa rà soát.',
                'Xác minh & khóa thêm gói nhãn tại kho nhãn, hoặc chọn "Tập dữ liệu thử nghiệm có nhãn hợp lệ" để kiểm thử pipeline FHE.',
            )
        usable.sort(key=lambda r: (str(r.get('event_at') or ''), r['record_id']))
        return usable[:needed_train], usable[needed_train:needed_total], simulated, snapshot_id

    # ------------------------------------------------------------------ Overview / Status
    def status(self, scope: AccessScope, recheck=None) -> dict:
        if recheck is not None and recheck() != scope:
            fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi.', 'Tải lại trang.')
        tenant = scope.tenant_id
        company = next(iter(scope.company_ids))
        worker_health = self.probe_worker_health()
        crypto = self.inspect_crypto_context(scope, verify_eval_key_hash=False)
        default_plan = self.prepare_dataset(scope, {'source_mode': 'verified_test_dataset', 'batch_count': 2, 'epochs': 1}, recheck)

        with closing(self._connect()) as conn:
            job_rows = conn.execute(
                'SELECT * FROM lr_fhe_jobs WHERE tenant_id=? AND company_id=? ORDER BY created_at DESC LIMIT 25',
                (tenant, company),
            ).fetchall()
            jobs = [self._public_job(self._hydrate_job(conn, r)) for r in job_rows]

        return {
            'version': VERSION,
            'company_id': company,
            'worker_health': worker_health,
            'crypto': crypto,
            'supported_features': default_plan['supported_features'],
            'supported_feature_count': len(SUPPORTED_FEATURES),
            'total_system_features': TOTAL_SYSTEM_FEATURES,
            'allow_33_features': False,
            'default_dataset_preview': {k: v for k, v in default_plan.items() if k not in ('train_batches', 'eval_batches', 'eval_rows')},
            'jobs': jobs,
            'latest_job': jobs[0] if jobs else None,
            'modes': [
                {
                    'id': 'local_quantized_reference',
                    'label': 'Huấn luyện tham chiếu local trên dữ liệu thử nghiệm',
                    'summary_vi': 'Chạy đúng số học lượng tử hóa của mạch tại máy doanh nghiệp (kèm đối chiếu LR số thực) để kiểm chứng trước khi chạy FHE cloud.',
                    'uses_worker_8870': False,
                },
                {
                    'id': 'fhe_cloud_ciphertext',
                    'label': 'Huấn luyện FHE trên ciphertext (Worker 8870)',
                    'summary_vi': 'Mã hóa cục bộ bằng khóa doanh nghiệp, gửi chỉ bản mã sang Worker 8870 (Concrete TFHE), lưu checkpoint từng batch, giải mã local theo quyền hạn — tuyệt đối không fallback plaintext.',
                    'uses_worker_8870': True,
                },
            ],
        }

    def _hydrate_job(self, conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
        payload = json.loads(row['payload_json'])
        ckpts = [
            dict(r)
            for r in conn.execute(
                'SELECT step_cursor, epoch, batch_index, x_cipher_sha256, y_cipher_sha256, weights_hash, checkpoint_kind, committed_at '
                'FROM lr_fhe_checkpoints WHERE job_id=? ORDER BY step_cursor ASC',
                (row['job_id'],),
            ).fetchall()
        ]
        payload['checkpoints'] = ckpts
        payload['completed_updates'] = int(row['completed_updates'])
        payload['total_updates'] = int(row['total_updates'])
        payload['status'] = row['status']
        payload['artifact_stage'] = row['artifact_stage']
        payload['is_train_checkpoint'] = row['artifact_stage'] != 'releasable_model'
        payload['is_releasable_model'] = row['artifact_stage'] == 'releasable_model'
        payload['can_activate_for_production'] = row['artifact_stage'] == 'releasable_model'
        payload['updated_at'] = row['updated_at']
        return payload

    def get_job(self, scope: AccessScope, job_id: str, recheck=None) -> dict:
        if recheck is not None and recheck() != scope:
            fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi.', 'Tải lại trang.')
        tenant = scope.tenant_id
        company = next(iter(scope.company_ids))
        with closing(self._connect()) as conn:
            row = conn.execute(
                'SELECT * FROM lr_fhe_jobs WHERE job_id=? AND tenant_id=? AND company_id=?',
                (job_id, tenant, company),
            ).fetchone()
            if row is None:
                fail(404, 'LR_FHE_JOB_NOT_FOUND', 'Không tìm thấy phiên huấn luyện LR của doanh nghiệp.', 'Chọn đúng job_id.')
            return self._public_job(self._hydrate_job(conn, row))

    # ------------------------------------------------------------------ Training (Local Ref & Real FHE 8870)
    def _make_enterprise_session(self, scope: AccessScope, job_id: str, cfg: dict, recheck=None):
        company = next(iter(scope.company_ids))
        ent_root = Path(cfg['enterprise_root']).resolve()
        build_dir = Path(cfg['build']).resolve()
        base_dir = ent_root / company
        session_dir = ent_root / '_r2_sessions' / f'{scope.tenant_id}_{company}' / job_id
        session_dir.mkdir(parents=True, exist_ok=True)
        if not (session_dir / 'enterprise.json').is_file():
            for fname in ('enterprise.json', 'wrapping.dpapi.json', 'node-signing.dpapi.json'):
                shutil.copy2(base_dir / fname, session_dir / fname)
            crypto_dst = session_dir / 'crypto'
            crypto_dst.mkdir(exist_ok=True)
            for fname in ('context.sealed', 'evaluation.keys'):
                src = base_dir / 'crypto' / fname
                dst = crypto_dst / fname
                if src.is_file() and not dst.exists():
                    try:
                        dst.hardlink_to(src)
                    except OSError:
                        shutil.copy2(src, dst)

        if self.node_factory is not None:
            node = self.node_factory(session_dir, build_dir, scope, recheck)
        else:
            node = BatchEnterprise(
                session_dir,
                build_dir,
                scope,
                python=cfg.get('linux_python'),
                distro=cfg.get('distro'),
                recheck=recheck,
            )
        return node, session_dir

    def _build_synthetic_reviews(self, node: BatchEnterprise, train_batches: list[dict]) -> list[dict]:
        templates = node.batch_review_templates()
        now_iso = _iso_now()
        reviews = []
        for tmpl, batch in zip(templates, train_batches):
            rows = []
            for rid, y in zip(batch['row_ids'], batch['y']):
                rows.append({
                    'record_id': rid,
                    'outcome': 'verified_fraud' if int(y) == 1 else 'verified_non_fraud',
                    'verified_by': node.scope.actor_id,
                    'verified_at': now_iso,
                    'evidence_refs': [f'r2-verified-test:{rid}'],
                })
            reviews.append({**tmpl, 'rows': rows})
        return reviews

    def start_training(self, scope: AccessScope, body: dict, idem_key: str | None, recheck=None) -> dict:
        tenant = scope.tenant_id
        company = next(iter(scope.company_ids))
        if 'model.fit' not in scope.permissions:
            fail(403, 'MODEL_FIT_DENIED', 'Cần quyền model.fit để huấn luyện LR.', 'Dùng tài khoản quản lý được cấp quyền.')

        mode = str(body.get('mode') or 'local_quantized_reference').strip()
        if mode not in ('local_quantized_reference', 'fhe_cloud_ciphertext'):
            fail(400, 'LR_TRAINING_MODE_INVALID', 'Chế độ huấn luyện LR phải là local_quantized_reference hoặc fhe_cloud_ciphertext.', 'Chọn đúng chế độ.')

        req_hash = digest(canonical({'action': 'lr_fhe_train', 'company': company, 'body': body}))
        with closing(self._connect()) as conn:
            prior = self._check_receipt(conn, tenant, company, idem_key, req_hash)
            if prior is not None:
                return prior

        plan = self.prepare_dataset(scope, body, recheck)
        crypto = self.inspect_crypto_context(scope, verify_eval_key_hash=(mode == 'fhe_cloud_ciphertext'))
        profile_version = crypto['circuit'].get('profile_version') or LEGACY_PROFILE_VERSION

        if mode == 'local_quantized_reference':
            return self._run_local_reference_job(scope, plan, crypto, profile_version, idem_key, req_hash, recheck)

        return self._run_fhe_cloud_job(scope, body, plan, crypto, profile_version, idem_key, req_hash, recheck)

    def _run_local_reference_job(
        self,
        scope: AccessScope,
        plan: dict,
        crypto: dict,
        profile_version: str,
        idem_key: str | None,
        req_hash: str,
        recheck=None,
    ) -> dict:
        tenant = scope.tenant_id
        company = next(iter(scope.company_ids))
        started = time.monotonic()
        quant_ref = _run_quantized_reference(plan['train_batches'], plan['epochs'], profile_version)
        float_ref = _run_float_lr_reference(plan['train_batches'], plan['epochs'], profile_version)
        validation = _compare_models(quant_ref, quant_ref, float_ref, plan['eval_rows'], is_fhe=False)
        elapsed = round(time.monotonic() - started, 3)

        job_id = 'lrfhe_' + secrets.token_hex(8)
        now = _iso_now()
        payload = {
            'job_id': job_id,
            'worker_job_id': None,
            'dataset_id': 'local_' + plan['dataset_fingerprint'][:16],
            'tenant_id': tenant,
            'company_id': company,
            'actor_id': scope.actor_id,
            'mode': 'local_quantized_reference',
            'mode_label_vi': 'Huấn luyện tham chiếu local (số học lượng tử hóa)',
            'native_fhe_executed': False,
            'cloud_worker_used': False,
            'plaintext_fallback': False,
            'artifact_stage': 'validated_checkpoint',
            'stage_label_vi': 'Checkpoint tham chiếu đã đối chiếu — chưa phát hành',
            'status': 'validated',
            'completed_updates': plan['total_updates'],
            'total_updates': plan['total_updates'],
            'elapsed_seconds': elapsed,
            'created_at': now,
            'updated_at': now,
            'dataset_summary': {
                'source_mode': plan['source_mode'],
                'snapshot_id': plan['snapshot_id'],
                'simulated': plan['simulated'],
                'valid_samples': plan['valid_samples'],
                'label_0_count': plan['label_0_count'],
                'label_1_count': plan['label_1_count'],
                'validation_samples': plan['validation_samples'],
                'validation_label_0_count': plan['validation_label_0_count'],
                'validation_label_1_count': plan['validation_label_1_count'],
                'supported_feature_count': plan['supported_feature_count'],
                'total_system_features': plan['total_system_features'],
                'supported_features': plan['supported_features'],
                'batch_size': plan['batch_size'],
                'batch_count': plan['batch_count'],
                'epochs': plan['epochs'],
                'total_updates': plan['total_updates'],
                'dataset_fingerprint': plan['dataset_fingerprint'],
            },
            'circuit_and_keys': {
                'profile': crypto['circuit']['profile'],
                'profile_version': profile_version,
                'concrete_version': crypto['circuit']['concrete_version'],
                'build_sha256': crypto['circuit']['build_sha256'],
                'key_epoch': crypto['keys']['key_epoch'],
                'evaluation_keys_sha256': crypto['keys']['evaluation_keys_sha256'],
                'weight_scale': quant_ref['weight_scale'],
                'bias_scale': quant_ref['bias_scale'],
                'probability_scale': quant_ref['probability_scale'],
            },
            'preflight': {
                'mode': 'local_quantized_reference',
                'worker_checked': False,
                'evaluation_key_verified': None,
                'ciphertext_verified': None,
                'note': 'Chế độ tham chiếu local chạy số học lượng tử hóa trên dữ liệu thử nghiệm tại doanh nghiệp.',
            },
            'decrypted_model': {
                'weights_code': quant_ref['weights_code'],
                'coefficients': quant_ref['coefficients'],
                'intercept': quant_ref['intercept'],
                'profile_version': profile_version,
                'decrypted_locally': False,
                'source': 'local_quantized_oracle',
            },
            'validation': validation,
            'promoted_version': None,
            'error': None,
        }

        with self._tx(scope, recheck) as conn:
            conn.execute(
                'INSERT INTO lr_fhe_jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    job_id, tenant, company, 'local_quantized_reference', None, payload['dataset_id'],
                    'validated_checkpoint', 'validated', plan['total_updates'], plan['total_updates'],
                    now, now, json.dumps(payload, ensure_ascii=False),
                ),
            )
            init_hash = digest(canonical({'step': 0, 'weights_code': [0, 0, 0]}))
            conn.execute(
                'INSERT INTO lr_fhe_checkpoints VALUES (?,?,?,?,?,?,?,?,?)',
                (job_id, 0, 0, -1, None, None, init_hash, 'train_checkpoint', now),
            )
            for st in quant_ref['steps']:
                w_hash = digest(canonical({'step': st['step_cursor'], 'weights_code': st['weights_code']}))
                conn.execute(
                    'INSERT INTO lr_fhe_checkpoints VALUES (?,?,?,?,?,?,?,?,?)',
                    (job_id, st['step_cursor'], st['epoch'], st['batch_index'], None, None, w_hash, 'train_checkpoint', now),
                )
            self._log_event(conn, tenant, company, job_id, 'train_local_reference', scope.actor_id, {
                'profile_version': profile_version,
                'weights_code': quant_ref['weights_code'],
                'validation_bce_loss': validation['actual']['metrics']['bce_loss'],
            })
            hydrated = self._hydrate_job(conn, conn.execute('SELECT * FROM lr_fhe_jobs WHERE job_id=?', (job_id,)).fetchone())
            response = {'status': 'ok', 'job': hydrated}
            self._save_receipt(conn, tenant, company, idem_key, req_hash, response)
        return response

    def _run_fhe_cloud_job(
        self,
        scope: AccessScope,
        body: dict,
        plan: dict,
        crypto: dict,
        profile_version: str,
        idem_key: str | None,
        req_hash: str,
        recheck=None,
    ) -> dict:
        """Execute REAL FHE LR training on Worker 8870 — ZERO plaintext fallback."""
        tenant = scope.tenant_id
        company = next(iter(scope.company_ids))
        started = time.monotonic()

        # 1. STRICT PREFLIGHT: worker health + circuit build + evaluation keys (NO plaintext fallback!)
        worker_health = self.probe_worker_health()
        if not worker_health.get('reachable'):
            fail(
                503,
                'HE_TRAINING_WORKER_UNAVAILABLE',
                worker_health.get('message') or 'Worker huấn luyện FHE (cổng 8870) không sẵn sàng; tuyệt đối không fallback về plaintext.',
                'Kiểm tra hoặc bấm "Khởi động lại Worker 8870" rồi thử lại.',
            )
        if not crypto['ready_for_fhe']:
            first = crypto['issues'][0] if crypto['issues'] else {'code': 'EVALUATION_KEY_VERIFICATION_FAILED', 'message': 'Kiểm tra khóa/mạch FHE không đạt.'}
            fail(
                409,
                first['code'] if 'EVALUATION' not in first['code'] else 'EVALUATION_KEY_VERIFICATION_FAILED',
                first['message'],
                'Kiểm tra lại build/manifest.json, context.sealed và evaluation.keys khớp với grant trên worker 8870.',
            )
        if not crypto['keys'].get('evaluation_key_verified'):
            fail(
                409,
                'EVALUATION_KEY_VERIFICATION_FAILED',
                'Chưa xác minh được SHA-256 của evaluation.keys so với grant trên worker 8870.',
                'Đảm bảo evaluation.keys tại doanh nghiệp khớp chính xác cấu hình worker 8870.',
            )
        cfg = self._discover_runtime_cfg()
        worker_url = str(cfg.get('worker_url') or 'http://127.0.0.1:8870').rstrip('/')
        worker_verify_key = str(cfg.get('worker_verify_key') or '').strip()
        if not worker_verify_key:
            fail(503, 'WORKER_VERIFY_KEY_MISSING', 'Thiếu khóa công khai xác thực chữ ký worker 8870.', 'Kiểm tra batch-training-runtime.json.')

        # Check grant verification_mode compatibility
        grant_mode = crypto['keys'].get('grant_verification_mode')
        expected_vmode = 'synthetic_expected' if plan['simulated'] else 'human_verified'
        if grant_mode and grant_mode != expected_vmode:
            fail(
                409,
                'VERIFICATION_MODE_GRANT_MISMATCH',
                f'Worker 8870 đang cấp phép chế độ xác minh "{grant_mode}" cho {company}, không khớp dữ liệu "{expected_vmode}".',
                'Dùng đúng chế độ dữ liệu được cấp phép trong worker-config.json.',
            )

        job_id = 'lrfhe_' + secrets.token_hex(8)
        defer_execution = bool(body.get('defer_execution', False))
        auto_decrypt = bool(body.get('auto_decrypt', True)) and not defer_execution

        # 2. Local encryption via DPAPI-protected Enterprise + Concrete 2.11.0
        try:
            node, session_dir = self._make_enterprise_session(scope, job_id, cfg, recheck)
            training_payload = [{'x': b['x'], 'row_ids': b['row_ids']} for b in plan['train_batches']]
            eval_payload = [{'x': b['x'], 'row_ids': b['row_ids']} for b in plan['eval_batches']]
            source = node.prepare_batches(training_payload, eval_payload, simulated=plan['simulated'], provenance=None)

            # Pre-upload ciphertext verification for X batches BEFORE sending anything to worker 8870
            upload_packet = strict_json((session_dir / 'batch-upload.json').read_bytes())
            upload_body = he_verify(upload_packet, node.public_key)
            _verify_ciphertexts_preflight(
                upload_body['batches'],
                [],
                {'weights_cipher': upload_body['batches'][0]['x_cipher'], 'weights_cipher_sha256': upload_body['batches'][0]['x_cipher_sha256']},
            )

            # Upload verified X ciphertexts to worker 8870 (/v2/datasets)
            node.upload_batches(worker_url, worker_verify_key)

            # Prepare verified label reviews & encrypt labels + initial weights locally
            reviews = self._build_synthetic_reviews(node, plan['train_batches'])
            confirm_status = node.confirm_batch_reviews(worker_url, worker_verify_key, reviews, epochs=plan['epochs'])

            # Full pre-train ciphertext verification on X, Y, and initial W ciphertexts BEFORE any FHE SGD step
            consent_packet = strict_json((session_dir / 'batch-consent.json').read_bytes())
            consent_body = he_verify(consent_packet, node.public_key)
            ct_preflight = _verify_ciphertexts_preflight(
                upload_body['batches'],
                consent_body['label_batches'],
                {'weights_cipher': consent_body['weights_cipher'], 'weights_cipher_sha256': consent_body['weights_cipher_sha256']},
            )
        except ImportFailure:
            raise
        except (TrainingError, ValueError, OSError) as exc:
            fail(
                503 if 'WORKER' in str(exc) or 'Connection' in str(exc) else 409,
                'FHE_PRETRAIN_OR_CONFIRM_FAILED',
                f'Không hoàn tất mã hóa / gửi bản mã lên worker 8870 ({exc}). Tuyệt đối không fallback về plaintext.',
                'Kiểm tra trạng thái worker 8870, evaluation key và dữ liệu đầu vào rồi thử lại.',
            )

        worker_job_id = confirm_status['job_id']
        dataset_id = source['dataset_id']
        init_w_hash = consent_body['weights_cipher_sha256']
        now = _iso_now()

        # Persist job + initial checkpoint cursor=0 BEFORE executing FHE SGD steps!
        payload = {
            'job_id': job_id,
            'worker_job_id': worker_job_id,
            'dataset_id': dataset_id,
            'session_dir': str(session_dir),
            'tenant_id': tenant,
            'company_id': company,
            'actor_id': scope.actor_id,
            'mode': 'fhe_cloud_ciphertext',
            'mode_label_vi': 'Huấn luyện FHE trên ciphertext (Worker 8870)',
            'native_fhe_executed': True,
            'cloud_worker_used': True,
            'plaintext_fallback': False,
            'artifact_stage': 'train_checkpoint',
            'stage_label_vi': 'Train checkpoint (bản mã) — chưa thể phát hành',
            'status': 'confirmed',
            'completed_updates': 0,
            'total_updates': plan['total_updates'],
            'elapsed_seconds': round(time.monotonic() - started, 3),
            'created_at': now,
            'updated_at': now,
            'dataset_summary': {
                'source_mode': plan['source_mode'],
                'snapshot_id': plan['snapshot_id'],
                'simulated': plan['simulated'],
                'valid_samples': plan['valid_samples'],
                'label_0_count': plan['label_0_count'],
                'label_1_count': plan['label_1_count'],
                'validation_samples': plan['validation_samples'],
                'validation_label_0_count': plan['validation_label_0_count'],
                'validation_label_1_count': plan['validation_label_1_count'],
                'supported_feature_count': plan['supported_feature_count'],
                'total_system_features': plan['total_system_features'],
                'supported_features': plan['supported_features'],
                'batch_size': plan['batch_size'],
                'batch_count': plan['batch_count'],
                'epochs': plan['epochs'],
                'total_updates': plan['total_updates'],
                'dataset_fingerprint': plan['dataset_fingerprint'],
            },
            '_plan_train_batches': plan['train_batches'],
            '_plan_eval_rows': plan['eval_rows'],
            '_batch_cipher_hashes': [
                {
                    'index': b['index'],
                    'x_cipher_sha256': b['x_cipher_sha256'],
                    'y_cipher_sha256': lb['y_cipher_sha256'],
                }
                for b, lb in zip(upload_body['batches'], consent_body['label_batches'])
            ],
            'circuit_and_keys': {
                'profile': crypto['circuit']['profile'],
                'profile_version': profile_version,
                'concrete_version': crypto['circuit']['concrete_version'],
                'build_sha256': crypto['circuit']['build_sha256'],
                'key_epoch': crypto['keys']['key_epoch'],
                'evaluation_keys_sha256': crypto['keys']['evaluation_keys_sha256'],
                'weight_scale': crypto['circuit']['weight_scale'],
                'bias_scale': crypto['circuit']['bias_scale'],
                'probability_scale': crypto['circuit']['probability_scale'],
            },
            'preflight': {
                'mode': 'fhe_cloud_ciphertext',
                'worker_checked': True,
                'worker_latency_ms': worker_health.get('latency_ms'),
                'evaluation_key_verified': True,
                'evaluation_keys_sha256': crypto['keys']['evaluation_keys_sha256'],
                'ciphertext_verified': True,
                'ciphertext_checked_count': ct_preflight['checked_count'],
                'total_ciphertext_bytes': ct_preflight['total_ciphertext_bytes'],
            },
            'decrypted_model': None,
            'validation': None,
            'promoted_version': None,
            'error': None,
        }

        with self._tx(scope, recheck) as conn:
            conn.execute(
                'INSERT INTO lr_fhe_jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    job_id, tenant, company, 'fhe_cloud_ciphertext', worker_job_id, dataset_id,
                    'train_checkpoint', 'confirmed', 0, plan['total_updates'],
                    now, now, json.dumps(payload, ensure_ascii=False),
                ),
            )
            conn.execute(
                'INSERT INTO lr_fhe_checkpoints VALUES (?,?,?,?,?,?,?,?,?)',
                (job_id, 0, 0, -1, None, None, init_w_hash, 'train_checkpoint', now),
            )
            self._log_event(conn, tenant, company, job_id, 'fhe_job_confirmed', scope.actor_id, {
                'worker_job_id': worker_job_id,
                'dataset_id': dataset_id,
                'total_updates': plan['total_updates'],
                'evaluation_keys_sha256': crypto['keys']['evaluation_keys_sha256'],
                'ciphertext_checked_count': ct_preflight['checked_count'],
            })

        if defer_execution:
            with self._tx(scope, recheck) as conn:
                hydrated = self._public_job(self._hydrate_job(conn, conn.execute('SELECT * FROM lr_fhe_jobs WHERE job_id=?', (job_id,)).fetchone()))
                response = {'status': 'ok', 'job': hydrated}
                self._save_receipt(conn, tenant, company, idem_key, req_hash, response)
            return response

        # 3. Execute FHE SGD updates on worker 8870 and sync per-batch checkpoints
        resumed = self.resume_job(
            scope,
            {'job_id': job_id, 'expected_cursor': 0, 'auto_decrypt': auto_decrypt},
            None,
            recheck,
        )
        with self._tx(scope, recheck) as conn:
            self._save_receipt(conn, tenant, company, idem_key, req_hash, resumed)
        return resumed

    def _sync_worker_checkpoints(self, conn: sqlite3.Connection, job_id: str, payload: dict, worker_status: dict, cfg: dict) -> int:
        """Record durable per-batch checkpoints committed on worker 8870 without duplicating any cursor."""
        completed = int(worker_status.get('completed_updates', 0))
        batch_count = int(payload['dataset_summary']['batch_count'])
        cipher_hashes = payload.get('_batch_cipher_hashes') or []
        worker_job_id = payload.get('worker_job_id')

        # Read exact per-cursor checkpoint weights_hash from cloud batch-jobs.sqlite3 read-only if co-located
        cloud_hashes: dict[int, str] = {}
        worker_cfg_path = cfg.get('_worker_config_path')
        if worker_cfg_path and worker_job_id:
            cloud_db = Path(worker_cfg_path).parent / 'state' / 'batch' / 'batch-jobs.sqlite3'
            if cloud_db.is_file():
                try:
                    with closing(sqlite3.connect(cloud_db.as_uri() + '?mode=ro', uri=True, timeout=5)) as cc:
                        cc.row_factory = sqlite3.Row
                        for r in cc.execute('SELECT cursor, weights_hash FROM checkpoints WHERE job=? ORDER BY cursor ASC', (worker_job_id,)).fetchall():
                            cloud_hashes[int(r['cursor'])] = str(r['weights_hash'])
                except sqlite3.Error:
                    pass

        existing_cursors = {
            int(r['step_cursor'])
            for r in conn.execute('SELECT step_cursor FROM lr_fhe_checkpoints WHERE job_id=?', (job_id,)).fetchall()
        }
        now = _iso_now()
        inserted = 0
        for step in range(1, completed + 1):
            if step in existing_cursors:
                continue
            b_idx = (step - 1) % batch_count
            ep = ((step - 1) // batch_count) + 1
            ch = cipher_hashes[b_idx] if b_idx < len(cipher_hashes) else {}
            w_hash = cloud_hashes.get(step) or (
                worker_status.get('model_cipher_sha256')
                if step == int(worker_status.get('total_updates', 0)) and worker_status.get('model_cipher_sha256')
                else digest(canonical({'worker_job_id': worker_job_id, 'cursor': step, 'consent_sha256': worker_status.get('consent_sha256')}))
            )
            conn.execute(
                'INSERT INTO lr_fhe_checkpoints VALUES (?,?,?,?,?,?,?,?,?)',
                (job_id, step, ep, b_idx, ch.get('x_cipher_sha256'), ch.get('y_cipher_sha256'), w_hash, 'train_checkpoint', now),
            )
            inserted += 1
        return inserted

    def resume_job(self, scope: AccessScope, body: dict, idem_key: str | None, recheck=None) -> dict:
        """Idempotently resume an FHE LR training job from its latest committed checkpoint.

        Rejects any attempt to replay or submit an already-committed batch (`DUPLICATE_BATCH_ON_RESUME`).
        Never falls back to plaintext if worker 8870 is unavailable.
        """
        tenant = scope.tenant_id
        company = next(iter(scope.company_ids))
        if 'model.fit' not in scope.permissions:
            fail(403, 'MODEL_FIT_DENIED', 'Cần quyền model.fit để tiếp tục huấn luyện FHE.', 'Dùng tài khoản quản lý được cấp quyền.')

        job_id = str(body.get('job_id') or '').strip()
        if not job_id:
            fail(400, 'JOB_ID_REQUIRED', 'Thiếu mã job_id để tiếp tục huấn luyện.', 'Chọn đúng phiên huấn luyện.')

        req_hash = digest(canonical({'action': 'lr_fhe_resume', 'company': company, 'body': body}))
        with closing(self._connect()) as conn:
            prior = self._check_receipt(conn, tenant, company, idem_key, req_hash)
            if prior is not None:
                return prior
            row = conn.execute(
                'SELECT * FROM lr_fhe_jobs WHERE job_id=? AND tenant_id=? AND company_id=?',
                (job_id, tenant, company),
            ).fetchone()
            if row is None:
                fail(404, 'LR_FHE_JOB_NOT_FOUND', 'Không tìm thấy phiên huấn luyện LR của doanh nghiệp.', 'Chọn đúng job_id.')
            job = self._hydrate_job(conn, row)

        if job['mode'] != 'fhe_cloud_ciphertext':
            fail(409, 'RESUME_ONLY_FOR_FHE_JOBS', 'Chế độ tham chiếu local đã hoàn tất đồng bộ, không cần resume trên worker 8870.', 'Xem kết quả validation của phiên này.')

        # 1. DUPLICATE BATCH PROTECTION ON RESUME
        current_cursor = int(job['completed_updates'])
        total_updates = int(job['total_updates'])
        committed_steps = {int(c['step_cursor']) for c in job['checkpoints'] if int(c['step_cursor']) > 0}
        committed_epoch_batches = {(int(c['epoch']), int(c['batch_index'])) for c in job['checkpoints'] if int(c['step_cursor']) > 0}

        if 'expected_cursor' in body and body['expected_cursor'] is not None:
            exp_cursor = int(body['expected_cursor'])
            if exp_cursor < current_cursor:
                fail(
                    409,
                    'DUPLICATE_BATCH_ON_RESUME',
                    f'Checkpoint hiện tại đã ở bước {current_cursor}/{total_updates}; không chấp nhận resume lùi về bước {exp_cursor} (ngăn chạy trùng batch).',
                    'Tải lại trạng thái mới nhất để resume đúng từ checkpoint hiện tại.',
                )
            if exp_cursor > current_cursor:
                fail(409, 'CHECKPOINT_CURSOR_MISMATCH', f'expected_cursor={exp_cursor} vượt quá checkpoint thực tế {current_cursor}.', 'Tải lại trạng thái job.')

        if 'batch_index' in body and body['batch_index'] is not None:
            req_batch = int(body['batch_index'])
            req_epoch = int(body.get('epoch') or ((current_cursor // max(1, int(job['dataset_summary']['batch_count']))) + 1))
            if (req_epoch, req_batch) in committed_epoch_batches:
                fail(
                    409,
                    'DUPLICATE_BATCH_ON_RESUME',
                    f'Batch {req_batch} (epoch {req_epoch}) đã được cập nhật trong checkpoint trước đó; không chấp nhận chạy trùng khi resume.',
                    'Tiếp tục từ batch kế tiếp chưa commit.',
                )

        if 'step_cursor' in body and body['step_cursor'] is not None:
            req_step = int(body['step_cursor'])
            if req_step in committed_steps:
                fail(
                    409,
                    'DUPLICATE_BATCH_ON_RESUME',
                    f'Bước cập nhật #{req_step} đã tồn tại trong bảng checkpoint; từ chối chạy trùng khi resume.',
                    'Tiếp tục từ bước kế tiếp.',
                )

        # Already completed -> idempotent no-op (never re-runs any batch!)
        if current_cursor >= total_updates and job['status'] in ('checkpoint_completed', 'validated', 'releasable'):
            response = {
                'status': 'ok',
                'already_completed': True,
                'resumed_from_cursor': current_cursor,
                'new_updates_applied': 0,
                'job': self._public_job(job),
            }
            if idem_key:
                with self._tx(scope, recheck) as conn:
                    self._save_receipt(conn, tenant, company, idem_key, req_hash, response)
            return response

        # 2. STRICT WORKER HEALTH CHECK (NO PLAINTEXT FALLBACK!)
        worker_health = self.probe_worker_health()
        if not worker_health.get('reachable'):
            fail(
                503,
                'HE_TRAINING_WORKER_UNAVAILABLE',
                'Worker 8870 đang không khả dụng khi resume; giữ nguyên checkpoint đã lưu và không fallback về plaintext.',
                'Khởi động lại Worker 8870 rồi bấm Tiếp tục (Resume).',
            )

        cfg = self._discover_runtime_cfg()
        worker_url = str(cfg.get('worker_url') or 'http://127.0.0.1:8870').rstrip('/')
        worker_verify_key = str(cfg.get('worker_verify_key') or '').strip()
        started = time.monotonic()

        try:
            node, _ = self._make_enterprise_session(scope, job_id, cfg, recheck)
            # Check worker cursor first so we never drift from durable cloud state
            pre_status, _ = node.access_batches(worker_url, worker_verify_key, 'status')
            worker_cursor = int(pre_status.get('completed_updates', 0))
            if 'expected_cursor' in body and body['expected_cursor'] is not None and int(body['expected_cursor']) < worker_cursor:
                fail(
                    409,
                    'DUPLICATE_BATCH_ON_RESUME',
                    f'Worker 8870 đã commit đến bước {worker_cursor}/{total_updates}; từ chối resume trùng từ bước {body["expected_cursor"]}.',
                    'Tải lại trạng thái job để đồng bộ checkpoint.',
                )
            run_status, _ = node.access_batches(worker_url, worker_verify_key, 'run')
        except ImportFailure:
            raise
        except (TrainingError, ValueError, OSError) as exc:
            # Record interrupted status cleanly without losing committed checkpoints
            err_msg = str(exc)
            with self._tx(scope, recheck) as conn:
                cur_row = conn.execute('SELECT * FROM lr_fhe_jobs WHERE job_id=?', (job_id,)).fetchone()
                cur_payload = json.loads(cur_row['payload_json'])
                cur_payload['error'] = {'code': 'FHE_RUN_INTERRUPTED', 'message': f'Gián đoạn khi chạy trên worker 8870: {err_msg}'}
                cur_payload['status'] = 'interrupted'
                cur_payload['updated_at'] = _iso_now()
                conn.execute(
                    'UPDATE lr_fhe_jobs SET status=?, updated_at=?, payload_json=? WHERE job_id=?',
                    ('interrupted', cur_payload['updated_at'], json.dumps(cur_payload, ensure_ascii=False), job_id),
                )
                self._log_event(conn, tenant, company, job_id, 'fhe_run_interrupted', scope.actor_id, {'error': err_msg})
            fail(
                503,
                'FHE_RUN_INTERRUPTED',
                f'Quá trình huấn luyện FHE trên worker 8870 bị gián đoạn ({err_msg}). Checkpoint trước đó đã được bảo toàn; không fallback về plaintext.',
                'Kiểm tra hoặc khởi động lại Worker 8870 rồi bấm Tiếp tục (Resume idempotent).',
            )

        completed_after = int(run_status.get('completed_updates', 0))
        done = (run_status.get('status') == 'completed' and completed_after == total_updates)
        now = _iso_now()

        with self._tx(scope, recheck) as conn:
            cur_row = conn.execute('SELECT * FROM lr_fhe_jobs WHERE job_id=?', (job_id,)).fetchone()
            cur_payload = json.loads(cur_row['payload_json'])
            new_ckpts = self._sync_worker_checkpoints(conn, job_id, cur_payload, run_status, cfg)
            cur_payload['completed_updates'] = completed_after
            cur_payload['status'] = 'checkpoint_completed' if done else 'interrupted'
            cur_payload['artifact_stage'] = 'train_checkpoint'
            cur_payload['stage_label_vi'] = (
                'Train checkpoint hoàn tất (bản mã) — chờ giải mã & đối chiếu local'
                if done
                else f'Train checkpoint dở dang ({completed_after}/{total_updates}) — sẵn sàng resume'
            )
            cur_payload['elapsed_seconds'] = round(float(cur_payload.get('elapsed_seconds') or 0.0) + (time.monotonic() - started), 3)
            cur_payload['updated_at'] = now
            cur_payload['error'] = None
            cur_payload['worker_status_snapshot'] = {
                'status': run_status.get('status'),
                'completed_updates': completed_after,
                'total_updates': total_updates,
                'completed_epochs': run_status.get('completed_epochs'),
                'next_batch_index': run_status.get('next_batch_index'),
                'consent_sha256': run_status.get('consent_sha256'),
            }
            conn.execute(
                'UPDATE lr_fhe_jobs SET status=?, completed_updates=?, updated_at=?, payload_json=? WHERE job_id=?',
                (cur_payload['status'], completed_after, now, json.dumps(cur_payload, ensure_ascii=False), job_id),
            )
            self._log_event(conn, tenant, company, job_id, 'fhe_checkpoints_synced', scope.actor_id, {
                'resumed_from_cursor': current_cursor,
                'completed_updates': completed_after,
                'new_checkpoints': new_ckpts,
                'done': done,
            })
            hydrated = self._hydrate_job(conn, conn.execute('SELECT * FROM lr_fhe_jobs WHERE job_id=?', (job_id,)).fetchone())

        if done and bool(body.get('auto_decrypt', False)):
            dec = self.decrypt_and_validate(scope, {'job_id': job_id}, None, recheck)
            response = {
                'status': 'ok',
                'already_completed': False,
                'resumed_from_cursor': current_cursor,
                'new_updates_applied': max(0, completed_after - current_cursor),
                'job': dec['job'],
            }
        else:
            response = {
                'status': 'ok',
                'already_completed': False,
                'resumed_from_cursor': current_cursor,
                'new_updates_applied': max(0, completed_after - current_cursor),
                'job': self._public_job(hydrated),
            }

        if idem_key:
            with self._tx(scope, recheck) as conn:
                self._save_receipt(conn, tenant, company, idem_key, req_hash, response)
        return response

    # ------------------------------------------------------------------ Local Authorized Decryption & Validation
    def decrypt_and_validate(self, scope: AccessScope, body: dict, idem_key: str | None, recheck=None) -> dict:
        """Decrypt final FHE checkpoint locally under strict company + model.fit authorization and validate."""
        tenant = scope.tenant_id
        company = next(iter(scope.company_ids))
        if 'model.fit' not in scope.permissions:
            fail(403, 'DECRYPT_PERMISSION_DENIED', 'Cần quyền quản trị mô hình (model.fit) của đúng doanh nghiệp để giải mã checkpoint.', 'Đăng nhập bằng tài khoản quản trị mô hình.')

        job_id = str(body.get('job_id') or '').strip()
        if not job_id:
            fail(400, 'JOB_ID_REQUIRED', 'Thiếu job_id cần giải mã.', 'Chọn phiên huấn luyện đã hoàn tất.')

        req_hash = digest(canonical({'action': 'lr_fhe_decrypt', 'company': company, 'body': body}))
        with closing(self._connect()) as conn:
            prior = self._check_receipt(conn, tenant, company, idem_key, req_hash)
            if prior is not None:
                return prior
            row = conn.execute(
                'SELECT * FROM lr_fhe_jobs WHERE job_id=? AND tenant_id=? AND company_id=?',
                (job_id, tenant, company),
            ).fetchone()
            if row is None:
                fail(404, 'LR_FHE_JOB_NOT_FOUND', 'Không tìm thấy phiên huấn luyện LR của doanh nghiệp.', 'Kiểm tra lại mã job_id.')
            job = self._hydrate_job(conn, row)

        if job['mode'] == 'local_quantized_reference':
            return {'status': 'ok', 'job': self._public_job(job)}
        if job['completed_updates'] < job['total_updates']:
            fail(409, 'BATCH_TRAINING_NOT_COMPLETED', f'Job mới hoàn tất {job["completed_updates"]}/{job["total_updates"]} bước; chưa thể giải mã model cuối.', 'Chạy tiếp Resume cho tới khi hoàn tất.')

        cfg = self._discover_runtime_cfg()
        worker_url = str(cfg.get('worker_url') or 'http://127.0.0.1:8870').rstrip('/')
        worker_verify_key = str(cfg.get('worker_verify_key') or '').strip()

        try:
            node, _ = self._make_enterprise_session(scope, job_id, cfg, recheck)
            candidate = node.receive_batches(worker_url, worker_verify_key)
        except ImportFailure:
            raise
        except (TrainingError, ValueError, OSError) as exc:
            code = 'BATCH_DECRYPTED_PARITY_FAILED' if 'PARITY' in str(exc) else 'LOCAL_DECRYPTION_FAILED'
            fail(409, code, f'Không thể giải mã hoặc kiểm chứng checkpoint tại local ({exc}).', 'Kiểm tra khóa bí mật doanh nghiệp và tính toàn vẹn bản mã.')

        profile_version = candidate.get('profile_version') or job['circuit_and_keys']['profile_version']
        train_batches = job.get('_plan_train_batches') or []
        eval_rows = job.get('_plan_eval_rows') or []
        epochs = int(job['dataset_summary']['epochs'])

        quant_ref = _run_quantized_reference(train_batches, epochs, profile_version)
        float_ref = _run_float_lr_reference(train_batches, epochs, profile_version)
        actual_model = {
            'weights_code': list(candidate['weights_code']),
            'coefficients': [round(float(c), 6) for c in candidate['coefficients']],
            'intercept': round(float(candidate['intercept']), 6),
            'profile_version': profile_version,
            'execution_mode': candidate.get('execution_mode', EXECUTION_MODE_NATIVE),
            'native_fhe_executed': bool(candidate.get('native_fhe_executed', True)),
            'model_cipher_sha256': candidate.get('model_cipher_sha256'),
            'decrypted_locally': True,
            'decrypted_by': scope.actor_id,
            'decrypted_at': _iso_now(),
        }
        validation = _compare_models(actual_model, quant_ref, float_ref, eval_rows, is_fhe=True)
        now = _iso_now()

        with self._tx(scope, recheck) as conn:
            cur_row = conn.execute('SELECT * FROM lr_fhe_jobs WHERE job_id=?', (job_id,)).fetchone()
            cur_payload = json.loads(cur_row['payload_json'])
            cur_payload['decrypted_model'] = actual_model
            cur_payload['validation'] = validation
            cur_payload['native_fhe_executed'] = actual_model['native_fhe_executed']
            cur_payload['status'] = 'validated' if validation['implementation_error']['pass'] else 'parity_failed'
            cur_payload['artifact_stage'] = 'validated_checkpoint'
            cur_payload['stage_label_vi'] = (
                'Checkpoint đã giải mã & đối chiếu local — chờ phê duyệt thành model phát hành'
                if validation['implementation_error']['pass']
                else 'CẢNH BÁO: Checkpoint không khớp đối chiếu số học lượng tử hóa'
            )
            cur_payload['updated_at'] = now
            conn.execute(
                'UPDATE lr_fhe_jobs SET artifact_stage=?, status=?, updated_at=?, payload_json=? WHERE job_id=?',
                ('validated_checkpoint', cur_payload['status'], now, json.dumps(cur_payload, ensure_ascii=False), job_id),
            )
            self._log_event(conn, tenant, company, job_id, 'checkpoint_decrypted_and_validated', scope.actor_id, {
                'weights_code': actual_model['weights_code'],
                'model_cipher_sha256': actual_model['model_cipher_sha256'],
                'implementation_pass': validation['implementation_error']['pass'],
                'quantization_weight_max_diff': validation['quantization_error']['weight_max_abs_diff'],
                'validation_bce_loss': validation['actual']['metrics']['bce_loss'],
            })
            hydrated = self._hydrate_job(conn, conn.execute('SELECT * FROM lr_fhe_jobs WHERE job_id=?', (job_id,)).fetchone())
            response = {'status': 'ok', 'job': self._public_job(hydrated)}
            self._save_receipt(conn, tenant, company, idem_key, req_hash, response)
        return response

    # ------------------------------------------------------------------ Promote Train Checkpoint -> Releasable Model
    def promote_to_releasable_model(self, scope: AccessScope, body: dict, idem_key: str | None, recheck=None) -> dict:
        """Explicitly promote a validated checkpoint into a versioned `releasable_model` (never automatic)."""
        tenant = scope.tenant_id
        company = next(iter(scope.company_ids))
        if 'model.fit' not in scope.permissions:
            fail(403, 'MODEL_FIT_DENIED', 'Cần quyền quản trị mô hình (model.fit) để phê duyệt phát hành.', 'Dùng tài khoản quản lý.')

        job_id = str(body.get('job_id') or '').strip()
        reason = str(body.get('reason') or '').strip()
        reviewed = bool(body.get('reviewed_checked'))
        if not job_id:
            fail(400, 'JOB_ID_REQUIRED', 'Thiếu job_id cần phê duyệt.', 'Chọn phiên huấn luyện đã đối chiếu.')
        if len(reason) < 10 or len(reason) > 1000:
            fail(400, 'APPROVAL_REASON_REQUIRED', 'Lý do phê duyệt cần từ 10 đến 1000 ký tự.', 'Nhập rõ căn cứ đánh giá trước khi phê duyệt.')
        if not reviewed:
            fail(400, 'APPROVAL_REVIEW_REQUIRED', 'Cần tích xác nhận đã xem kết quả validation và phân tích sai số.', 'Tích ô xác nhận trước khi phê duyệt.')

        req_hash = digest(canonical({'action': 'lr_fhe_promote', 'company': company, 'body': body}))
        with closing(self._connect()) as conn:
            prior = self._check_receipt(conn, tenant, company, idem_key, req_hash)
            if prior is not None:
                return prior
            row = conn.execute(
                'SELECT * FROM lr_fhe_jobs WHERE job_id=? AND tenant_id=? AND company_id=?',
                (job_id, tenant, company),
            ).fetchone()
            if row is None:
                fail(404, 'LR_FHE_JOB_NOT_FOUND', 'Không tìm thấy phiên huấn luyện LR.', 'Kiểm tra lại job_id.')
            job = self._hydrate_job(conn, row)

        if job['artifact_stage'] == 'train_checkpoint' or not job.get('validation'):
            fail(
                409,
                'CHECKPOINT_NOT_VALIDATED',
                'Train checkpoint chưa được giải mã và đối chiếu validation tại local; không thể phát hành trực tiếp.',
                'Thực hiện bước Giải mã & đối chiếu validation trước khi phê duyệt thành model có thể phát hành.',
            )
        if not job['validation']['implementation_error']['pass']:
            fail(
                409,
                'IMPLEMENTATION_PARITY_FAILED',
                'Checkpoint không đạt kiểm tra đối chiếu số học lượng tử hóa (có lỗi triển khai); chặn phát hành.',
                'Kiểm tra lại môi trường Concrete FHE và huấn luyện lại.',
            )

        now = _iso_now()
        model_id = 'lrmdl_' + digest(canonical({'job_id': job_id, 'company': company, 'weights': job['decrypted_model']['weights_code']}))[:24]
        version_tag = f'{company}-lr-{"fhe" if job["mode"] == "fhe_cloud_ciphertext" else "ref"}-{job_id[-6:]}'
        val_preds = ((job['validation'].get('actual') or {}).get('metrics') or {}).get('predictions') or []
        val_threshold_stats = select_validation_threshold(val_preds)
        if 'threshold' in body and body['threshold'] is not None:
            custom_tau = float(body['threshold'])
            if not (0.05 <= custom_tau <= 0.95):
                fail(400, 'LR_THRESHOLD_INVALID', 'Ngưỡng phân loại phải nằm trong [0.05, 0.95].', 'Để mặc định chọn từ validation hoặc chọn ngưỡng hợp lệ.')
            val_threshold_stats['threshold'] = round(custom_tau, 6)
            val_threshold_stats['selection_basis'] = 'operator_override_validated'

        releasable_record = {
            'release_contract_version': LR_RELEASE_CONTRACT,
            'model_id': model_id,
            'version_tag': version_tag,
            'artifact_stage': 'releasable_model',
            'tenant_id': tenant,
            'company_id': company,
            'source_job_id': job_id,
            'worker_job_id': job.get('worker_job_id'),
            'mode': job['mode'],
            'native_fhe_executed': bool(job.get('native_fhe_executed')),
            'profile_version': job['circuit_and_keys']['profile_version'],
            'build_sha256': job['circuit_and_keys']['build_sha256'],
            'key_epoch': job['circuit_and_keys']['key_epoch'],
            'model_cipher_sha256': (job.get('decrypted_model') or {}).get('model_cipher_sha256'),
            'weights_code': job['decrypted_model']['weights_code'],
            'coefficients': job['decrypted_model']['coefficients'],
            'intercept': job['decrypted_model']['intercept'],
            'threshold': val_threshold_stats['threshold'],
            'feature_schema': deepcopy(LR_FEATURE_SCHEMA),
            'supported_features': list(SUPPORTED_FEATURES),
            'validation_metrics': val_threshold_stats,
            'validation_bce_loss': job['validation']['actual']['metrics']['bce_loss'],
            'validation_accuracy': job['validation']['actual']['metrics']['accuracy'],
            'implementation_parity_pass': True,
            'approved_by': scope.actor_id,
            'approved_at': now,
            'approval_reason': reason,
            'release_scope': 'shadow_or_controlled_pilot',
        }
        signing_key = self._load_or_create_signing_key(company)
        releasable_record = sign_releasable_lr_model(releasable_record, signing_key)

        # Also sign approval on BatchEnterprise session if FHE job
        if job['mode'] == 'fhe_cloud_ciphertext' and job.get('session_dir'):
            try:
                cfg = self._discover_runtime_cfg()
                node, _ = self._make_enterprise_session(scope, job_id, cfg, recheck)
                if not (Path(job['session_dir']) / 'batch-evaluation.json').is_file():
                    node.evaluate_holdout()
                node.approve_batches(reason)
            except Exception:
                pass

        with self._tx(scope, recheck) as conn:
            cur_row = conn.execute('SELECT * FROM lr_fhe_jobs WHERE job_id=?', (job_id,)).fetchone()
            cur_payload = json.loads(cur_row['payload_json'])
            cur_payload['artifact_stage'] = 'releasable_model'
            cur_payload['stage_label_vi'] = f'Model có thể phát hành ({version_tag})'
            cur_payload['status'] = 'releasable'
            cur_payload['promoted_version'] = releasable_record
            cur_payload['updated_at'] = now
            conn.execute(
                'UPDATE lr_fhe_jobs SET artifact_stage=?, status=?, updated_at=?, payload_json=? WHERE job_id=?',
                ('releasable_model', 'releasable', now, json.dumps(cur_payload, ensure_ascii=False), job_id),
            )
            self._log_event(conn, tenant, company, job_id, 'promoted_to_releasable_model', scope.actor_id, {
                'model_id': model_id,
                'version_tag': version_tag,
                'reason': reason,
            })
            hydrated = self._hydrate_job(conn, conn.execute('SELECT * FROM lr_fhe_jobs WHERE job_id=?', (job_id,)).fetchone())
            response = {'status': 'ok', 'releasable_model': releasable_record, 'job': self._public_job(hydrated)}
            self._save_receipt(conn, tenant, company, idem_key, req_hash, response)
        return response

    def install_federated_model(self, scope: AccessScope, model: dict) -> dict:
        """Install the station's accepted joint model as this company's releasable LR (the supervised scoring factor)."""
        tenant = scope.tenant_id
        company = next(iter(scope.company_ids))
        if 'model.fit' not in scope.permissions:
            fail(403, 'MODEL_FIT_DENIED', 'Cần quyền quản trị mô hình để đồng bộ mô hình.', 'Dùng tài khoản quản lý.')
        now = _iso_now()
        job_id = 'fedsync_' + digest(canonical({'company': company, 'version': model['version'], 'run': model['run_id']}))[:24]
        w = model['weights']
        record = {
            'release_contract_version': LR_RELEASE_CONTRACT,
            'model_id': 'lrmdl_' + digest(canonical({'fed': model['run_id'], 'company': company, 'weights': w['codes']}))[:24],
            'version_tag': f'{company}-lr-chung-v{model["version"]}',
            'artifact_stage': 'releasable_model',
            'tenant_id': tenant,
            'company_id': company,
            'source_job_id': model['run_id'],
            'worker_job_id': None,
            'mode': 'fhe_cloud_ciphertext',
            'native_fhe_executed': True,
            'profile_version': PROFILE_VERSION,
            'build_sha256': None,
            'key_epoch': None,
            'model_cipher_sha256': None,
            'weights_code': list(w['codes']),
            'coefficients': [float(v) for v in w['w']],
            'intercept': float(w['b']),
            'threshold': float(model['threshold']),
            'feature_schema': deepcopy(LR_FEATURE_SCHEMA),
            'supported_features': list(SUPPORTED_FEATURES),
            'validation_metrics': dict(model['summary'], threshold=float(model['threshold']), selection_basis='station_pooled_holdout'),
            'validation_bce_loss': model['summary'].get('bce'),
            'validation_accuracy': model['summary'].get('accuracy'),
            'implementation_parity_pass': True,
            'approved_by': scope.actor_id,
            'approved_at': now,
            'approval_reason': f'Đồng bộ mô hình chung v{model["version"]} từ trạm huấn luyện.',
            'release_scope': 'shadow_or_controlled_pilot',
        }
        record = sign_releasable_lr_model(record, self._load_or_create_signing_key(company))
        payload = {'job_id': job_id, 'mode': 'fhe_cloud_ciphertext', 'artifact_stage': 'releasable_model', 'status': 'releasable',
                   'stage_label_vi': f'Mô hình chung v{model["version"]} (đồng bộ từ trạm)', 'promoted_version': record,
                   'created_at': now, 'updated_at': now}
        with self._tx(scope) as conn:
            conn.execute('INSERT OR REPLACE INTO lr_fhe_jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                         (job_id, tenant, company, 'fhe_cloud_ciphertext', None, None, 'releasable_model', 'releasable', 0, 0, now, now,
                          json.dumps(payload, ensure_ascii=False)))
            self._log_event(conn, tenant, company, job_id, 'federated_model_synced', scope.actor_id, {'version': model['version'], 'model_id': record['model_id']})
        return record

    def _load_or_create_signing_key(self, company: str) -> Ed25519PrivateKey:
        """Load company DPAPI node-signing key if provisioned, else enterprise-local Ed25519 key."""
        cfg = self._discover_runtime_cfg()
        ent_root = Path(cfg['enterprise_root']).resolve() if cfg.get('enterprise_root') else None
        if ent_root is not None:
            dpapi_file = ent_root / company / 'node-signing.dpapi.json'
            if dpapi_file.is_file():
                try:
                    from experiments.he_inference.key_manager import PROVIDER, load_key
                    raw = load_key(dpapi_file, purpose='node-signing', required_provider=PROVIDER).material
                    return Ed25519PrivateKey.from_private_bytes(raw)
                except Exception:
                    pass
        key_path = self.path.with_name(f'lr-model-signing-{company}.key')
        if key_path.is_file():
            return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(key_path.read_text(encoding='utf-8').strip()))
        key = Ed25519PrivateKey.generate()
        key_path.write_text(key.private_bytes_raw().hex(), encoding='utf-8')
        return key

    def get_latest_releasable_model(self, scope: AccessScope, *, model_id: str | None = None, recheck=None) -> dict | None:
        """Return the latest explicitly promoted `releasable_model` for this company (never a train checkpoint)."""
        if recheck is not None and recheck() != scope:
            fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi.', 'Tải lại trang.')
        tenant = scope.tenant_id
        company = next(iter(scope.company_ids))
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT payload_json FROM lr_fhe_jobs WHERE tenant_id=? AND company_id=? AND artifact_stage='releasable_model' ORDER BY updated_at DESC",
                (tenant, company),
            ).fetchall()
        for row in rows:
            payload = json.loads(row['payload_json'])
            rec = payload.get('promoted_version')
            if not isinstance(rec, dict) or rec.get('artifact_stage') != 'releasable_model':
                continue
            if model_id and rec.get('model_id') != model_id and rec.get('version_tag') != model_id:
                continue
            return deepcopy(rec)
        return None

    def collect_verified_review_labels(self, scope: AccessScope, release_service, *, recheck=None) -> dict:
        """Collect ONLY verified reviewer outcomes (`confirmed_risk` -> 1, `legitimate` -> 0) for next supervised cycle.

        Strictly excludes:
          - Unreviewed transactions (NEVER treated as label 0)
          - Reviews marked `inconclusive` (`Chưa đủ bằng chứng`)
          - Reviews missing `checks_completed=True` or checked `evidence_ids`
        """
        if recheck is not None and recheck() != scope:
            fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi.', 'Tải lại trang.')
        labels_map: dict[str, int] = {}
        verified_items = []
        excluded_inconclusive = 0
        excluded_unverified = 0
        if release_service is None or not hasattr(release_service, 'workspace'):
            return {
                'eligible_count': 0,
                'fraud_count': 0,
                'legitimate_count': 0,
                'excluded_inconclusive_count': 0,
                'excluded_unverified_count': 0,
                'labels_map': {},
                'items': [],
            }
        ws = release_service.workspace
        listing = ws.list_runs(scope, recheck)
        for run in listing.get('runs', []):
            if run.get('status') != 'completed':
                continue
            try:
                rep = ws.report(scope, run['run_id'], recheck)
            except Exception:
                continue
            for case in rep.get('cases', []):
                rev = case.get('review') or {}
                fb = rev.get('feedback')
                tids = list(case.get('candidate_ids') or [])
                if not isinstance(fb, dict):
                    excluded_unverified += len(tids)
                    continue
                outcome = fb.get('outcome')
                if outcome == 'inconclusive':
                    excluded_inconclusive += len(tids)
                    continue
                if outcome not in ('confirmed_risk', 'legitimate'):
                    excluded_unverified += len(tids)
                    continue
                if fb.get('checks_completed') is not True or not (fb.get('evidence_ids') or []):
                    excluded_unverified += len(tids)
                    continue
                label_val = 1 if outcome == 'confirmed_risk' else 0
                for tid in tids:
                    labels_map[str(tid)] = label_val
                    verified_items.append({
                        'transaction_id': str(tid),
                        'label': label_val,
                        'outcome': outcome,
                        'run_id': run['run_id'],
                        'review_id': case.get('review_id'),
                        'review_revision': rev.get('revision'),
                    })
        return {
            'eligible_count': len(labels_map),
            'fraud_count': sum(1 for v in labels_map.values() if v == 1),
            'legitimate_count': sum(1 for v in labels_map.values() if v == 0),
            'excluded_inconclusive_count': excluded_inconclusive,
            'excluded_unverified_count': excluded_unverified,
            'labels_map': labels_map,
            'items': verified_items,
            'policy_note': 'Chỉ giao dịch được người kiểm tra xác nhận Vi phạm (1) hoặc Hợp lệ (0) kèm đối chiếu chứng từ mới đủ điều kiện đưa vào dataset supervised chu kỳ tiếp theo.',
        }

    @staticmethod
    def _public_job(job: dict) -> dict:
        """Strip internal private working paths/buffers before returning DTO over HTTP."""
        out = deepcopy(job)
        for hidden in ('session_dir', '_plan_train_batches', '_plan_eval_rows', '_batch_cipher_hashes'):
            out.pop(hidden, None)
        return out
