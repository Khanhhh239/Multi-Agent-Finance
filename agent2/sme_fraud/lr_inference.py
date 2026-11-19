"""R3 — Supervised Logistic Regression Inference Adapter, 5-Method Bundle & Risk Scoring.

Integrates approved releasable LR models from R2 into Agent2 as the 5th detection method
alongside Rules, Statistics, Graph, and Unsupervised ML without breaking existing methods.

Design invariants:
  - Only loads explicitly promoted `releasable_model` artifacts with valid Ed25519
    signature, contract version, company scope, feature schema, and validation threshold.
  - Never collapses `unavailable` into score `0` (always `score=None` + structured `error_code`).
  - Prefers local inference for approved releasable models; supports real TenSEAL CKKS
    encrypted 2-column quadratic-equivalent evaluation (`x^2 == x` for binary x in {0,1})
    and honestly probes CKKS worker 8868 capability without silent plaintext fallback.
  - Converts LR probability P(y=1) smoothly using validation threshold & validation
    precision dampening (NEVER flat +10 points merely because Recall > 90%).
  - Applies explicit anti-double-counting overlap discount when LR features overlap
    already-fired actionable rules (`C2 <-> creator_equals_approver`, `A6 <-> round_million`).
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .import_files import canonical, digest

try:
    import tenseal as ts
except ImportError:
    ts = None

LR_RELEASE_CONTRACT = 'lr-releasable-model/1.0.0'
LR_FEATURE_SCHEMA = {
    'version': 'existing-binary-pair/1.0.0',
    'columns': ['round_million', 'creator_equals_approver'],
    'domains': [[0, 1], [0, 1]],
    'missing_policy': 'unavailable_never_zero',
}
LR_FEATURE_LABELS_VI = {
    'round_million': 'Số tiền làm tròn bội số triệu đồng',
    'creator_equals_approver': 'Người lập đồng thời là người phê duyệt',
}
# Exact rule-to-LR-feature overlap mapping for anti-double-counting
LR_RULE_OVERLAP_MAP = {
    'round_million': frozenset({'A6'}),
    'creator_equals_approver': frozenset({'C2'}),
}

FIVE_METHOD_LABELS_VI = {
    'rules': 'Luật nghiệp vụ (35 luật)',
    'statistics': 'Thống kê lịch sử (RobustZ)',
    'graph': 'Đồ thị quan hệ (PIT)',
    'unsupervised_ml': 'ML không giám sát',
    'supervised_lr': 'Logistic Regression có giám sát',
}


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, float(z)))))


def _is_finite(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(float(val))


def select_validation_threshold(predictions: list[dict], *, min_tau: float = 0.30, max_tau: float = 0.85) -> dict:
    """Select an operating threshold on validation predictions maximizing (F1, Youden-J, Precision)."""
    if not predictions:
        return {
            'threshold': 0.50,
            'selection_basis': 'default_no_validation_rows',
            'sample_count': 0,
            'precision': None,
            'recall': None,
            'f1': None,
            'accuracy': None,
            'brier_score': None,
            'bce_loss': None,
            'positive_rate': None,
            'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0,
        }

    probs = [float(p['score']) for p in predictions]
    ys = [int(p['y_true']) for p in predictions]
    n = len(ys)
    eps = 1e-12
    brier = sum((p - y) ** 2 for p, y in zip(probs, ys)) / n
    bce = sum(-(y * math.log(max(eps, min(1.0 - eps, p))) + (1 - y) * math.log(max(eps, min(1.0 - eps, 1.0 - p)))) for p, y in zip(probs, ys)) / n

    unique_probs = sorted(set(probs))
    candidates = {0.50}
    for p in unique_probs:
        if min_tau <= p <= max_tau:
            candidates.add(round(p, 6))
            # Slightly above p to cleanly separate boundary ties
            if p + 0.01 <= max_tau:
                candidates.add(round(p + 0.01, 6))
    for a, b in zip(unique_probs, unique_probs[1:]):
        mid = round((a + b) / 2.0, 6)
        if min_tau <= mid <= max_tau:
            candidates.add(mid)

    best_key = None
    best_stats = None
    for tau in sorted(candidates):
        tp = fp = tn = fn = 0
        for p, y in zip(probs, ys):
            pred = 1 if p >= tau else 0
            if pred == 1 and y == 1:
                tp += 1
            elif pred == 1 and y == 0:
                fp += 1
            elif pred == 0 and y == 0:
                tn += 1
            else:
                fn += 1
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        spec = tn / (tn + fp) if (tn + fp) > 0 else 0.0
        f1 = (2.0 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        youden = rec + spec - 1.0
        acc = (tp + tn) / n
        pos_rate = (tp + fp) / n
        # Penalize degenerate all-positive / all-negative thresholds
        non_degenerate = 1 if (0 < tp + fp < n) else 0
        rank_key = (non_degenerate, round(f1, 6), round(youden, 6), round(prec, 6), round(acc, 6), -abs(tau - 0.50))
        if best_key is None or rank_key > best_key:
            best_key = rank_key
            best_stats = {
                'threshold': round(tau, 6),
                'selection_basis': 'validation_f1_youden_precision',
                'sample_count': n,
                'precision': round(prec, 4),
                'recall': round(rec, 4),
                'f1': round(f1, 4),
                'accuracy': round(acc, 4),
                'brier_score': round(brier, 6),
                'bce_loss': round(bce, 6),
                'positive_rate': round(pos_rate, 4),
                'tp': tp, 'fp': fp, 'tn': tn, 'fn': fn,
            }
    assert best_stats is not None
    return best_stats


# ---------------------------------------------------------------------- Cryptographic Signing & Verification
_SIGNED_FIELDS = (
    'release_contract_version',
    'model_id',
    'version_tag',
    'artifact_stage',
    'tenant_id',
    'company_id',
    'source_job_id',
    'worker_job_id',
    'mode',
    'native_fhe_executed',
    'profile_version',
    'build_sha256',
    'key_epoch',
    'model_cipher_sha256',
    'weights_code',
    'coefficients',
    'intercept',
    'threshold',
    'feature_schema',
    'validation_metrics',
    'implementation_parity_pass',
    'approved_by',
    'approved_at',
    'approval_reason',
)


def _canonical_signed_payload(record: dict) -> bytes:
    core = {k: record.get(k) for k in _SIGNED_FIELDS}
    return canonical(core)


def sign_releasable_lr_model(record: dict, signing_key: Ed25519PrivateKey) -> dict:
    """Attach an Ed25519 cryptographic signature envelope over the canonical releasable LR artifact."""
    signed = deepcopy(record)
    signed['release_contract_version'] = LR_RELEASE_CONTRACT
    signed['feature_schema'] = deepcopy(LR_FEATURE_SCHEMA)
    raw = _canonical_signed_payload(signed)
    payload_sha = digest(raw)
    sig_hex = signing_key.sign(raw).hex()
    pub_hex = signing_key.public_key().public_bytes_raw().hex()
    signed['signature_envelope'] = {
        'algorithm': 'ed25519',
        'verify_key_hex': pub_hex,
        'payload_sha256': payload_sha,
        'signature_hex': sig_hex,
        'signed_at': datetime.now(timezone.utc).isoformat(),
    }
    return signed


def verify_releasable_lr_model(
    record: dict | None,
    *,
    expected_tenant: str,
    expected_company: str,
    expected_verify_key: str | None = None,
) -> tuple[bool, str | None, str]:
    """Strictly verify approval stage, contract version, company scope, Ed25519 signature, schema, and parameters."""
    if not isinstance(record, dict):
        return False, 'LR_NO_APPROVED_MODEL', 'Chưa có mô hình Logistic Regression được phê duyệt phát hành.'
    if record.get('artifact_stage') != 'releasable_model':
        return False, 'LR_MODEL_NOT_APPROVED', 'Chỉ được dùng mô hình LR đã phê duyệt phát hành (không dùng train checkpoint).'
    if record.get('release_contract_version') != LR_RELEASE_CONTRACT:
        return False, 'LR_CONTRACT_VERSION_UNSUPPORTED', f'Phiên bản hợp đồng LR không hợp lệ: {record.get("release_contract_version")}.'
    if record.get('tenant_id') != expected_tenant or record.get('company_id') != expected_company:
        return False, 'LR_COMPANY_SCOPE_MISMATCH', 'Mô hình LR không thuộc phạm vi doanh nghiệp đang chấm điểm.'
    if record.get('implementation_parity_pass') is not True:
        return False, 'LR_PARITY_NOT_VERIFIED', 'Mô hình LR chưa đạt kiểm tra đối chiếu số học lượng tử hóa.'

    # Signature check
    env = record.get('signature_envelope')
    if not isinstance(env, dict) or env.get('algorithm') != 'ed25519':
        return False, 'LR_SIGNATURE_MISSING', 'Thiếu chữ ký điện tử Ed25519 của mô hình LR.'
    pub_hex = str(env.get('verify_key_hex') or '')
    sig_hex = str(env.get('signature_hex') or '')
    if expected_verify_key and pub_hex != expected_verify_key:
        return False, 'LR_SIGNATURE_KEY_MISMATCH', 'Khóa xác thực chữ ký của mô hình LR không khớp khóa doanh nghiệp.'
    raw = _canonical_signed_payload(record)
    if env.get('payload_sha256') != digest(raw):
        return False, 'LR_SIGNATURE_INVALID', 'Mã băm nội dung mô hình LR không khớp chữ ký (có dấu hiệu bị sửa đổi).'
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
        pub.verify(bytes.fromhex(sig_hex), raw)
    except (ValueError, InvalidSignature):
        return False, 'LR_SIGNATURE_INVALID', 'Chữ ký Ed25519 của mô hình LR không hợp lệ.'

    # Feature schema check
    schema = record.get('feature_schema')
    if (
        not isinstance(schema, dict)
        or schema.get('version') != LR_FEATURE_SCHEMA['version']
        or list(schema.get('columns') or []) != LR_FEATURE_SCHEMA['columns']
    ):
        return False, 'LR_FEATURE_SCHEMA_MISMATCH', 'Feature schema của mô hình LR không khớp hợp đồng 2 đặc trưng nhị phân.'

    # Parameters & validation threshold check
    coeffs = record.get('coefficients')
    intercept = record.get('intercept')
    threshold = record.get('threshold')
    if (
        not isinstance(coeffs, list)
        or len(coeffs) != 2
        or not all(_is_finite(c) for c in coeffs)
        or not _is_finite(intercept)
    ):
        return False, 'LR_PARAMETERS_INVALID', 'Trọng số mô hình LR không hợp lệ.'
    if not _is_finite(threshold) or not (0.0 < float(threshold) < 1.0):
        return False, 'LR_THRESHOLD_INVALID', 'Ngưỡng phân loại (threshold) từ validation không hợp lệ.'

    return True, None, 'Hợp lệ'


# ---------------------------------------------------------------------- Risk Scoring Configuration & Conversion
@dataclass
class RiskScoringConfig:
    """Configurable 5-method risk scoring & validation-calibrated anti-double-counting weights."""
    rule_weight: float = 1.0
    statistics_weight: float = 0.5
    graph_weight: float = 0.0                # Context-only by default; does not auto-add points
    unsupervised_ml_weight: float = 2.0
    supervised_lr_weight: float = 1.0
    lr_max_points: float = 8.0               # Maximum LR contribution before overlap & precision dampening
    overlap_discount_factor: float = 0.70    # Discount overlapping LR feature share when same rule already fired
    validation_precision_scaling: bool = True
    min_quality_factor: float = 0.25
    uncalibrated_quality_cap: float = 0.50
    calibration_source: str = 'default_config'

    def to_dict(self) -> dict:
        return asdict(self)


def convert_lr_probability_to_points(
    probability: float,
    threshold: float,
    *,
    validation_metrics: dict | None,
    config: RiskScoringConfig,
) -> dict:
    """Convert LR P(y=1) into a bounded, validation-calibrated risk score.

    Explicitly prevents assigning flat +10 points to all transactions merely
    because a model achieves high Recall (>90%) with mediocre Precision.
    """
    p = max(0.0, min(1.0, float(probability)))
    tau = max(0.05, min(0.95, float(threshold)))
    prediction = 1 if p >= tau else 0

    vm = validation_metrics or {}
    val_prec = vm.get('precision')
    val_rec = vm.get('recall')
    val_n = int(vm.get('sample_count') or 0)

    # Quality scaling grounded in validation precision (NOT raw recall!)
    if config.validation_precision_scaling and _is_finite(val_prec) and val_n > 0:
        quality_factor = max(config.min_quality_factor, min(1.0, float(val_prec)))
        quality_note = (
            f'Hiệu chỉnh theo Precision tập validation ({round(float(val_prec) * 100, 1)}%, '
            f'Recall={round(float(val_rec) * 100, 1) if _is_finite(val_rec) else "—"}%); '
            'không cộng cố định 10 điểm chỉ vì Recall cao.'
        )
    else:
        quality_factor = config.uncalibrated_quality_cap
        quality_note = f'Giới hạn thận trọng (hệ số {quality_factor}) do chưa có đủ chỉ số Precision validation.'

    floor_p = 0.5 * tau
    if p <= floor_p:
        base_fraction = 0.0
    elif p < tau:
        # Smooth graded ramp below threshold: 0 -> 0.20
        base_fraction = 0.20 * ((p - floor_p) / max(1e-6, tau - floor_p))
    else:
        # Smooth margin-above-threshold scaling: 0.20 -> 1.00
        base_fraction = 0.20 + 0.80 * ((p - tau) / max(1e-6, 1.0 - tau))

    raw_converted = round(config.lr_max_points * base_fraction * quality_factor, 4)
    return {
        'probability': round(p, 6),
        'threshold': round(tau, 6),
        'prediction': prediction,
        'base_fraction': round(base_fraction, 6),
        'quality_factor': round(quality_factor, 4),
        'raw_converted_points': raw_converted,
        'quality_note': quality_note,
    }


def apply_overlap_deduplication(
    raw_lr_points: float,
    feature_values: dict[str, int],
    coefficients: list[float],
    fired_actionable_rules: set[str],
    config: RiskScoringConfig,
) -> dict:
    """Prevent double-counting the same risk indicator across Rules and Supervised LR."""
    pos_contribs: dict[str, float] = {}
    for col, coeff in zip(LR_FEATURE_SCHEMA['columns'], coefficients):
        val = int(feature_values.get(col, 0))
        contrib = max(0.0, float(coeff) * val)
        pos_contribs[col] = contrib

    total_pos = sum(pos_contribs.values())
    overlaps = []
    overlap_share = 0.0
    if total_pos > 1e-12 and raw_lr_points > 0:
        for col, contrib in pos_contribs.items():
            if contrib <= 0:
                continue
            matched_rules = sorted(LR_RULE_OVERLAP_MAP.get(col, frozenset()) & fired_actionable_rules)
            if matched_rules:
                share = contrib / total_pos
                overlap_share += share
                overlaps.append({
                    'feature': col,
                    'feature_label_vi': LR_FEATURE_LABELS_VI.get(col, col),
                    'overlapping_rules': matched_rules,
                    'positive_logit_share': round(share, 4),
                })

    overlap_share = min(1.0, overlap_share)
    discount_ratio = round(config.overlap_discount_factor * overlap_share, 4)
    effective_points = round(raw_lr_points * (1.0 - discount_ratio), 4)
    discounted_points = round(raw_lr_points - effective_points, 4)

    if overlaps:
        pairs = ', '.join(f'{o["feature"]} ↔ {"/".join(o["overlapping_rules"])}' for o in overlaps)
        note = (
            f'Áp dụng giảm trùng lắp {round(discount_ratio * 100, 1)}% (-{discounted_points} điểm) '
            f'vì dấu hiệu đã được luật nghiệp vụ tính điểm ({pairs}).'
        )
    else:
        note = 'Không có dấu hiệu trùng lắp giữa đặc trưng LR và luật nghiệp vụ đã kích hoạt.'

    return {
        'raw_lr_points': round(raw_lr_points, 4),
        'overlap_applied': bool(overlaps),
        'overlapping_rules': sorted({r for o in overlaps for r in o['overlapping_rules']}),
        'overlap_share': round(overlap_share, 4),
        'discount_ratio': discount_ratio,
        'discounted_points': discounted_points,
        'overlap_discount_points': discounted_points,
        'effective_lr_points': effective_points,
        'overlaps': overlaps,
        'note': note,
    }


def calibrate_risk_scoring_on_validation(
    validation_records: list[dict],
    base_config: RiskScoringConfig | None = None,
) -> tuple[RiskScoringConfig, dict]:
    """Calibrate LR risk weight & overlap discount on labeled validation records (no model refit).

    Each item in `validation_records` has:
      {rule_score, ml_score, lr_raw_points, lr_overlap_share, y_true in {0, 1}}.
    Maximizes validation risk separation (mean score gap between y=1 and y=0 normalized by std,
    plus pairwise ranking AUC).
    """
    cfg = deepcopy(base_config) if base_config is not None else RiskScoringConfig()
    valid = [r for r in validation_records if r.get('y_true') in (0, 1) and _is_finite(r.get('lr_raw_points'))]
    pos = [r for r in valid if r['y_true'] == 1]
    neg = [r for r in valid if r['y_true'] == 0]
    if not pos or not neg:
        return cfg, {
            'calibrated': False,
            'reason': 'Cần đủ cả hai lớp nhãn (0 và 1) trong tập validation để hiệu chỉnh trọng số rủi ro.',
            'selected_config': cfg.to_dict(),
        }

    best_obj = None
    best_pair = (cfg.supervised_lr_weight, cfg.overlap_discount_factor)
    best_auc = 0.0
    for w_lr in (0.5, 0.75, 1.0, 1.25, 1.5):
        for disc in (0.5, 0.7, 0.85, 1.0):
            scored = []
            for r in valid:
                eff_lr = float(r['lr_raw_points']) * (1.0 - disc * float(r.get('lr_overlap_share') or 0.0))
                tot = (
                    cfg.rule_weight * float(r.get('rule_score') or 0.0)
                    + cfg.unsupervised_ml_weight * float(r.get('ml_score') or 0.0)
                    + w_lr * eff_lr
                )
                scored.append((tot, int(r['y_true'])))
            pos_s = [s for s, y in scored if y == 1]
            neg_s = [s for s, y in scored if y == 0]
            wins = sum(1.0 if ps > ns else (0.5 if ps == ns else 0.0) for ps in pos_s for ns in neg_s)
            auc = wins / (len(pos_s) * len(neg_s))
            gap = (sum(pos_s) / len(pos_s)) - (sum(neg_s) / len(neg_s))
            # Mild preference for stronger deduplication when ranking ties
            obj = (round(auc, 6), round(gap, 4), round(disc, 2), -abs(w_lr - 1.0))
            if best_obj is None or obj > best_obj:
                best_obj = obj
                best_pair = (w_lr, disc)
                best_auc = auc

    cfg.supervised_lr_weight = float(best_pair[0])
    cfg.overlap_discount_factor = float(best_pair[1])
    cfg.calibration_source = 'validation_ranking_calibrated'
    return cfg, {
        'calibrated': True,
        'validation_samples': len(valid),
        'validation_auc': round(best_auc, 4),
        'selected_supervised_lr_weight': cfg.supervised_lr_weight,
        'selected_overlap_discount_factor': cfg.overlap_discount_factor,
        'selected_config': cfg.to_dict(),
    }


# ---------------------------------------------------------------------- CKKS Worker 8868 Probe & TenSEAL Evaluation
def probe_ckks_8868_capability(worker_url: str = 'http://127.0.0.1:8868', *, timeout: float = 1.2) -> dict:
    """Honestly inspect CKKS worker 8868 health and LR protocol compatibility."""
    url = worker_url.rstrip('/')
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(Request(url + '/health'), timeout=timeout) as resp:
            data = json.loads(resp.read(4096))
        reachable = isinstance(data, dict) and data.get('role') == 'ciphertext_worker'
        return {
            'reachable': reachable,
            'url': url,
            'protocol': data.get('protocol') if isinstance(data, dict) else None,
            'worker_profile': 'ckks_2col_quadratic_mahalanobis',
            'tenseal_local_available': ts is not None,
            'cloud_lr_policy_registered': False,
            'mathematical_compatibility': 'binary_quadratic_equivalent (w0*x0^2 + 0*x0*x1 + w1*x1^2 == w0*x0 + w1*x1 for x in {0,1})',
            'note': (
                'Worker CKKS 8868 đang chạy (hỗ trợ đa thức bậc 2 trên 2 cột mã hóa); '
                'model LR đã phê duyệt ưu tiên suy luận local và hỗ trợ kiểm chứng mã hóa CKKS TenSEAL tương đương.'
                if reachable
                else 'Worker CKKS 8868 chưa phản hồi.'
            ),
        }
    except (HTTPError, URLError, OSError, ValueError) as exc:
        return {
            'reachable': False,
            'url': url,
            'protocol': None,
            'worker_profile': 'ckks_2col_quadratic_mahalanobis',
            'tenseal_local_available': ts is not None,
            'cloud_lr_policy_registered': False,
            'error': str(exc),
            'note': 'Worker CKKS 8868 hiện không kết nối được.',
        }


def _evaluate_ckks_linear_terms(coefficients: list[float], x_matrix: list[list[int]]) -> tuple[list[float], dict]:
    """Compute exact w0*x0 + w1*x1 using TenSEAL CKKS 2-column quadratic layout (matching worker 8868).

    Because x_j in {0, 1}, x_j^2 == x_j, so `w0*x0^2 + 0*(x0*x1) + w1*x1^2` evaluates the exact
    linear dot product on CKKS ciphertext using the identical 2-column quadratic primitive as worker 8868.
    """
    if ts is None:
        raise RuntimeError('TENSEAL_UNAVAILABLE')
    if not x_matrix:
        return [], {'rows': 0, 'max_abs_ckks_error': 0.0}
    n = len(x_matrix)
    w0, w1 = float(coefficients[0]), float(coefficients[1])
    ctx = ts.context(ts.SCHEME_TYPE.CKKS, poly_modulus_degree=8192, coeff_mod_bit_sizes=[60, 40, 40, 60])
    ctx.global_scale = 2 ** 40
    ctx.generate_galois_keys()
    ctx.generate_relin_keys()

    col0 = [float(r[0]) for r in x_matrix]
    col1 = [float(r[1]) for r in x_matrix]
    enc_x0 = ts.ckks_vector(ctx, col0)
    enc_x1 = ts.ckks_vector(ctx, col1)
    enc_w0 = ts.ckks_vector(ctx, [w0] * n)
    enc_w1 = ts.ckks_vector(ctx, [w1] * n)
    enc_w01 = ts.ckks_vector(ctx, [0.0] * n)

    # Identical quadratic ciphertext evaluation as cloud_worker.py PAIRS = ((0,0), (0,1), (1,1))
    enc_dot = (enc_x0 * enc_x0 * enc_w0) + (enc_x0 * enc_x1 * enc_w01) + (enc_x1 * enc_x1 * enc_w1)
    dec = enc_dot.decrypt()[:n]
    clear = [w0 * float(r[0]) + w1 * float(r[1]) for r in x_matrix]
    max_err = max((abs(a - b) for a, b in zip(dec, clear)), default=0.0)
    return [float(v) for v in dec], {'rows': n, 'max_abs_ckks_error': round(max_err, 9)}


# ---------------------------------------------------------------------- Supervised LR Inference Adapter
class SupervisedLRAdapter:
    """Inference adapter for approved releasable Logistic Regression models (5th Agent2 method)."""

    def __init__(
        self,
        *,
        lr_training_service=None,
        lr_registry=None,
        ckks_worker_url: str = 'http://127.0.0.1:8868',
        scoring_config: RiskScoringConfig | None = None,
    ):
        self.lr_service = lr_training_service
        self.lr_registry = lr_registry
        self.ckks_worker_url = ckks_worker_url
        self.config = scoring_config or RiskScoringConfig()

    def load_approved_model(
        self,
        scope,
        *,
        model_id: str | None = None,
        explicit_model: dict | None = None,
        expected_verify_key: str | None = None,
        recheck=None,
    ) -> dict:
        """Load and cryptographically verify an approved releasable LR model.

        Never raises silently into score=0; returns `{available: bool, model, error_code, message}`.
        """
        tenant = scope.tenant_id
        company = next(iter(scope.company_ids))
        record = explicit_model
        reg = self.lr_registry or getattr(self.lr_service, 'lr_registry', None)
        if record is None and reg is not None:
            if model_id and str(model_id).startswith('lrreg_'):
                record = reg.get_active_releasable_model(scope, registry_id=str(model_id), recheck=recheck)
                if record is None:
                    return {
                        'available': False,
                        'status': 'unavailable',
                        'model': None,
                        'error_code': 'LR_MODEL_NOT_ACTIVE_OR_UNAPPROVED',
                        'message': 'Phiên bản LR trong Registry chưa ở trạng thái ACTIVE hoặc chưa đạt quality_approved=True.',
                    }
            elif not model_id:
                record = reg.get_active_releasable_model(scope, recheck=recheck)
        if record is None and self.lr_service is not None:
            record = self.lr_service.get_latest_releasable_model(scope, model_id=model_id, recheck=recheck)
        ok, err_code, msg = verify_releasable_lr_model(
            record,
            expected_tenant=tenant,
            expected_company=company,
            expected_verify_key=expected_verify_key,
        )
        if not ok:
            return {
                'available': False,
                'status': 'unavailable',
                'model': None,
                'error_code': err_code,
                'message': msg,
            }
        return {
            'available': True,
            'status': 'available',
            'model': deepcopy(record),
            'error_code': None,
            'message': f'Đã xác thực chữ ký Ed25519 và schema cho mô hình LR {record["version_tag"]}.',
        }

    def score_transaction_rows(
        self,
        scope,
        feature_frame: dict,
        analysis_rows: list[dict],
        *,
        model_id: str | None = None,
        explicit_model: dict | None = None,
        expected_verify_key: str | None = None,
        execution_preference: str = 'local_preferred',
        scoring_config: RiskScoringConfig | None = None,
        recheck=None,
    ) -> dict:
        """Score every transaction row with the approved LR model and return standardized method DTOs.

        `execution_preference`:
          - 'local_preferred' (default): fast verified local inference for approved releasable models.
          - 'ckks_encrypted': real TenSEAL CKKS encrypted evaluation (equivalent to worker 8868 2-col layout).
          - 'cloud_ckks_8868_strict': requires registered LR grant on worker 8868; returns unavailable if absent.
        """
        cfg = scoring_config or self.config
        loaded = self.load_approved_model(
            scope,
            model_id=model_id,
            explicit_model=explicit_model,
            expected_verify_key=expected_verify_key,
            recheck=recheck,
        )
        ckks_info = probe_ckks_8868_capability(self.ckks_worker_url) if execution_preference != 'local_preferred' else None

        if not loaded['available']:
            per_tx = {
                str(r['transaction_id']): self._unavailable_method_dto(
                    error_code=loaded['error_code'],
                    message=loaded['message'],
                    model_version=None,
                    circuit_version=None,
                )
                for r in analysis_rows
            }
            return {
                'available': False,
                'execution_backend': 'none',
                'model': None,
                'error_code': loaded['error_code'],
                'message': loaded['message'],
                'ckks_8868': ckks_info,
                'per_transaction': per_tx,
            }

        model = loaded['model']
        if execution_preference == 'cloud_ckks_8868_strict':
            # Worker 8868 currently pins Mahalanobis quadratic policies only -> honest unavailable, zero plaintext fallback
            err_code = 'CKKS_WORKER_8868_UNAVAILABLE' if not (ckks_info and ckks_info['reachable']) else 'CKKS_WORKER_8868_LR_POLICY_NOT_REGISTERED'
            msg = (
                'Worker CKKS 8868 không kết nối được; không tự rơi về suy luận dữ liệu rõ.'
                if err_code == 'CKKS_WORKER_8868_UNAVAILABLE'
                else 'Worker CKKS 8868 hiện chưa có policy đăng ký cho mô hình LR này; không tự rơi về dữ liệu rõ.'
            )
            per_tx = {
                str(r['transaction_id']): self._unavailable_method_dto(
                    error_code=err_code,
                    message=msg,
                    model_version=model['version_tag'],
                    circuit_version=model.get('profile_version'),
                )
                for r in analysis_rows
            }
            return {
                'available': False,
                'execution_backend': 'cloud_ckks_8868_strict',
                'model': model,
                'error_code': err_code,
                'message': msg,
                'ckks_8868': ckks_info,
                'per_transaction': per_tx,
            }

        # Verify feature frame schema contains required 2 columns
        frame_cols = list((feature_frame.get('contract') or {}).get('columns') or [])
        if not all(col in frame_cols for col in LR_FEATURE_SCHEMA['columns']):
            err_code = 'LR_FEATURE_SCHEMA_MISMATCH'
            msg = 'Khung đặc trưng đầu vào thiếu cột bắt buộc cho mô hình Logistic Regression.'
            per_tx = {
                str(r['transaction_id']): self._unavailable_method_dto(
                    error_code=err_code,
                    message=msg,
                    model_version=model['version_tag'],
                    circuit_version=model.get('profile_version'),
                )
                for r in analysis_rows
            }
            return {
                'available': False,
                'execution_backend': 'none',
                'model': model,
                'error_code': err_code,
                'message': msg,
                'ckks_8868': ckks_info,
                'per_transaction': per_tx,
            }

        col_indices = [frame_cols.index(c) for c in LR_FEATURE_SCHEMA['columns']]
        frame_by_tid = {
            str(fr['record_id']): (int(fr['row_index']) if 'row_index' in fr else idx)
            for idx, fr in enumerate(feature_frame.get('rows') or [])
        }
        features_mat = feature_frame.get('features') or []
        missing_mat = feature_frame.get('missing') or []

        coeffs = [float(model['coefficients'][0]), float(model['coefficients'][1])]
        intercept = float(model['intercept'])
        threshold = float(model['threshold'])
        val_metrics = model.get('validation_metrics') or {}

        scorable_tids = []
        scorable_x = []
        per_tx: dict[str, dict] = {}
        fired_rules_by_tid: dict[str, set[str]] = {}

        for row in analysis_rows:
            tid = str(row['transaction_id'])
            fired = {
                str(entry['rule_id'])
                for entry in ((row.get('rule_coverage') or {}).get('rules') or [])
                if entry.get('status') == 'evaluated_hit' and entry.get('matched') is True and float(entry.get('score') or 0) > 0
            }
            fired_rules_by_tid[tid] = fired

            if not (row.get('availability') or {}).get('available', True):
                per_tx[tid] = self._unavailable_method_dto(
                    error_code='TX_NOT_KNOWN_AT_CUTOFF',
                    message='Giao dịch chưa khả dụng tại mốc thời gian chốt.',
                    model_version=model['version_tag'],
                    circuit_version=model.get('profile_version'),
                )
                continue

            r_idx = frame_by_tid.get(tid)
            if r_idx is None:
                per_tx[tid] = self._unavailable_method_dto(
                    error_code='LR_FEATURE_ROW_MISSING',
                    message='Không tìm thấy hàng đặc trưng cho giao dịch này.',
                    model_version=model['version_tag'],
                    circuit_version=model.get('profile_version'),
                )
                continue
            x_vals = []
            missing_cols = []
            for col_name, ci in zip(LR_FEATURE_SCHEMA['columns'], col_indices):
                is_miss = bool(missing_mat[r_idx][ci]) if r_idx < len(missing_mat) else True
                raw_v = features_mat[r_idx][ci] if r_idx < len(features_mat) else None
                if is_miss or raw_v is None or isinstance(raw_v, bool) or not _is_finite(raw_v) or float(raw_v) not in (0.0, 1.0):
                    missing_cols.append(col_name)
                else:
                    x_vals.append(int(raw_v))

            if missing_cols:
                per_tx[tid] = self._unavailable_method_dto(
                    error_code='LR_FEATURE_MISSING_OR_OUT_OF_DOMAIN',
                    message=f'Thiếu hoặc ngoài miền nhị phân {{0, 1}} cho đặc trưng: {", ".join(missing_cols)}. Không điền 0 thay thế.',
                    model_version=model['version_tag'],
                    circuit_version=model.get('profile_version'),
                )
                continue

            scorable_tids.append(tid)
            scorable_x.append(x_vals)

        # Compute linear dot products (local preferred, or real TenSEAL CKKS when requested)
        ckks_meta = None
        if execution_preference == 'ckks_encrypted':
            if ts is None:
                for tid in scorable_tids:
                    per_tx[tid] = self._unavailable_method_dto(
                        error_code='TENSEAL_UNAVAILABLE',
                        message='Thư viện TenSEAL CKKS không khả dụng trong môi trường hiện tại.',
                        model_version=model['version_tag'],
                        circuit_version=model.get('profile_version'),
                    )
                return {
                    'available': False,
                    'execution_backend': 'ckks_encrypted',
                    'model': model,
                    'error_code': 'TENSEAL_UNAVAILABLE',
                    'message': 'TenSEAL CKKS không khả dụng.',
                    'ckks_8868': ckks_info,
                    'per_transaction': per_tx,
                }
            dot_values, ckks_meta = _evaluate_ckks_linear_terms(coeffs, scorable_x)
            backend_name = 'ckks_tenseal_2col_quadratic_equivalent'
        else:
            dot_values = [coeffs[0] * x[0] + coeffs[1] * x[1] for x in scorable_x]
            backend_name = 'local_approved_model'

        for tid, x_vals, dot in zip(scorable_tids, scorable_x, dot_values):
            logit = float(dot) + intercept
            prob = _sigmoid(logit)
            conv = convert_lr_probability_to_points(prob, threshold, validation_metrics=val_metrics, config=cfg)
            feat_map = {col: val for col, val in zip(LR_FEATURE_SCHEMA['columns'], x_vals)}
            dedup = apply_overlap_deduplication(
                conv['raw_converted_points'],
                feat_map,
                coeffs,
                fired_rules_by_tid.get(tid, set()),
                cfg,
            )

            ev_items = [
                {
                    'feature': col,
                    'label_vi': LR_FEATURE_LABELS_VI[col],
                    'value': val,
                    'weight': round(w, 6),
                    'logit_contribution': round(w * val, 6),
                }
                for col, val, w in zip(LR_FEATURE_SCHEMA['columns'], x_vals, coeffs)
            ]
            ev_items.append({
                'feature': 'intercept',
                'label_vi': 'Hệ số chặn (intercept b)',
                'value': 1,
                'weight': round(intercept, 6),
                'logit_contribution': round(intercept, 6),
            })

            per_tx[tid] = {
                'method_id': 'supervised_lr',
                'method_label_vi': FIVE_METHOD_LABELS_VI['supervised_lr'],
                'available': True,
                'status': 'available',
                'score': dedup['effective_lr_points'],
                'raw_score': conv['probability'],
                'probability': conv['probability'],
                'logit': round(logit, 6),
                'threshold': conv['threshold'],
                'prediction': conv['prediction'],
                'raw_converted_points': conv['raw_converted_points'],
                'deduplication': dedup,
                'confidence_metadata': {
                    'basis': 'validation_metrics' if val_metrics.get('sample_count') else 'conservative_uncalibrated',
                    'validation_samples': val_metrics.get('sample_count'),
                    'validation_precision': val_metrics.get('precision'),
                    'validation_recall': val_metrics.get('recall'),
                    'validation_f1': val_metrics.get('f1'),
                    'validation_accuracy': val_metrics.get('accuracy'),
                    'validation_bce_loss': val_metrics.get('bce_loss'),
                    'quality_factor': conv['quality_factor'],
                    'quality_note': conv['quality_note'],
                    'inference_backend': backend_name,
                    'ckks_encrypted': backend_name.startswith('ckks_'),
                    'ckks_max_abs_error': ckks_meta['max_abs_ckks_error'] if ckks_meta else None,
                },
                'model_version': model['version_tag'],
                'model_id': model['model_id'],
                'artifact_id': model['model_id'],
                'circuit_version': model.get('profile_version'),
                'build_sha256': model.get('build_sha256'),
                'key_epoch': model.get('key_epoch'),
                'native_fhe_trained': bool(model.get('native_fhe_executed')),
                'signature_verified': True,
                'feature_schema_version': LR_FEATURE_SCHEMA['version'],
                'explanation_evidence': ev_items,
                'error_code': None,
            }

        return {
            'available': True,
            'execution_backend': backend_name,
            'model': model,
            'error_code': None,
            'message': f'Đã chấm {len(scorable_tids)}/{len(analysis_rows)} giao dịch bằng mô hình LR {model["version_tag"]}.',
            'ckks_8868': ckks_info,
            'ckks_meta': ckks_meta,
            'per_transaction': per_tx,
        }

    @staticmethod
    def _unavailable_method_dto(*, error_code: str, message: str, model_version: str | None, circuit_version: str | None) -> dict:
        return {
            'method_id': 'supervised_lr',
            'method_label_vi': FIVE_METHOD_LABELS_VI['supervised_lr'],
            'available': False,
            'status': 'unavailable',
            'score': None,               # NEVER 0 when unavailable!
            'raw_score': None,
            'probability': None,
            'logit': None,
            'threshold': None,
            'prediction': None,
            'raw_converted_points': None,
            'deduplication': None,
            'confidence_metadata': {
                'basis': 'unavailable',
                'note': message,
            },
            'model_version': model_version,
            'model_id': None,
            'artifact_id': None,
            'circuit_version': circuit_version,
            'signature_verified': False,
            'feature_schema_version': LR_FEATURE_SCHEMA['version'],
            'explanation_evidence': [],
            'error_code': error_code,
            'message': message,
        }


# ---------------------------------------------------------------------- Unified 5-Method Bundle Integrator
def build_five_method_row_assessment(
    row: dict,
    *,
    unsup_method_id: str | None,
    unsup_version_tag: str | None,
    lr_dto: dict,
    config: RiskScoringConfig | None = None,
) -> dict:
    """Unify all 5 Agent2 detection sources (Rules, Statistics, Graph, Unsupervised ML, Supervised LR).

    Strictly preserves `unavailable -> score=None` (never converted to 0) and computes
    a transparent weighted risk breakdown with anti-double-counting metadata.
    """
    cfg = config or RiskScoringConfig()
    branches = row.get('branches') or {}
    methods = row.get('methods') or {}
    rule_cov = row.get('rule_coverage') or {}
    rules_list = rule_cov.get('rules') or []

    # 1. Rules
    r_branch = branches.get('rules') or {}
    r_hits = [e for e in rules_list if e.get('status') == 'evaluated_hit' and e.get('matched') is True]
    r_actionable_pts = sum(float(e.get('score') or 0) for e in r_hits if float(e.get('score') or 0) > 0)
    r_available = bool(r_branch.get('available')) or r_branch.get('status') in ('available', 'partial')
    rules_entry = {
        'method_id': 'rules',
        'method_label_vi': FIVE_METHOD_LABELS_VI['rules'],
        'score': round(r_actionable_pts, 4) if r_available else None,
        'raw_score': round(r_actionable_pts, 4) if r_available else None,
        'probability': None,
        'prediction': None,
        'threshold': None,
        'confidence_metadata': {
            'basis': 'deterministic_rule_coverage',
            'evaluated_count': r_branch.get('evaluated_count', len(rules_list)),
            'total_count': r_branch.get('total_count', 35),
            'hit_count': len(r_hits),
        },
        'status': r_branch.get('status') or ('available' if r_available else 'unavailable'),
        'model_version': 'rules-35/1.0.0',
        'circuit_version': None,
        'explanation_evidence': [
            {
                'rule_id': e['rule_id'],
                'name': e.get('name', e['rule_id']),
                'points': e.get('score'),
                'context_only': float(e.get('score') or 0) <= 0,
            }
            for e in r_hits
        ],
        'error_code': None if r_available else 'RULES_UNAVAILABLE',
    }

    # 2. Statistics (RobustZ)
    stat_m = methods.get('robust_z') or {}
    stat_b = branches.get('statistics') or {}
    stat_avail = bool(stat_m.get('available') is True and _is_finite(stat_m.get('score')))
    stat_err = None
    if not stat_avail:
        rc = stat_m.get('reason') or stat_b.get('reason') or 'STATISTICS_UNAVAILABLE'
        stat_err = rc.get('code') if isinstance(rc, dict) else str(rc)
    stat_entry = {
        'method_id': 'statistics',
        'method_label_vi': FIVE_METHOD_LABELS_VI['statistics'],
        'score': round(float(stat_m['score']), 4) if stat_avail else None,
        'raw_score': round(float(stat_m['raw_score']), 4) if (stat_avail and _is_finite(stat_m.get('raw_score'))) else None,
        'probability': None,
        'prediction': None,
        'threshold': None,
        'confidence_metadata': {
            'basis': 'empirical_midrank_reference' if stat_avail else 'unavailable',
            'reference_version': stat_m.get('reference_version'),
            'missing_features_count': len(stat_m.get('missing_features') or []),
        },
        'status': 'available' if stat_avail else 'unavailable',
        'model_version': stat_m.get('artifact_id') or 'robust_z',
        'circuit_version': None,
        'explanation_evidence': [
            {'detail': f'Hạng tương đối RobustZ: {round(float(stat_m["score"]) * 100, 1)}% (raw={round(float(stat_m.get("raw_score") or 0), 3)})'}
        ] if stat_avail else [],
        'error_code': stat_err,
    }

    # 3. Graph (Point-in-Time Entity Graph — context-only unless graph_weight > 0)
    g_branch = branches.get('graph') or {}
    g_data = row.get('graph') or {}
    g_links = list(g_data.get('links') or [])
    g_findings = list(g_data.get('findings') or [])
    g_avail = bool(g_branch.get('available') or g_data.get('available') or g_branch.get('status') in ('available', 'partial'))
    graph_entry = {
        'method_id': 'graph',
        'method_label_vi': FIVE_METHOD_LABELS_VI['graph'],
        'score': 0.0 if (g_avail and cfg.graph_weight == 0.0) else (float(len(g_findings)) if g_avail else None),
        'raw_score': float(len(g_links)) if g_avail else None,
        'probability': None,
        'prediction': None,
        'threshold': None,
        'confidence_metadata': {
            'basis': 'context_only_pit_graph',
            'link_count': len(g_links),
            'finding_count': len(g_findings),
            'adds_points': cfg.graph_weight > 0.0,
        },
        'status': g_branch.get('status') or ('partial' if g_avail else 'unavailable'),
        'model_version': 'pit-graph/1.0.0',
        'circuit_version': None,
        'explanation_evidence': [
            {'link': str(lk)} for lk in g_links[:5]
        ],
        'error_code': None if g_avail else 'GRAPH_UNAVAILABLE',
    }

    # 4. Unsupervised ML (Isolation Forest / Autoencoder / ECOD / LOF)
    ml_key = unsup_method_id
    if not ml_key:
        for cand_k in ('isolation_forest', 'autoencoder', 'ecod', 'lof'):
            if cand_k in methods:
                ml_key = cand_k
                break
    ml_m = methods.get(ml_key) if ml_key else {}
    ml_m = ml_m if isinstance(ml_m, dict) else {}
    ml_avail = bool(ml_m.get('available') is True and (_is_finite(ml_m.get('score')) or _is_finite(ml_m.get('raw_score'))))
    ml_score_val = (
        round(float(ml_m['score']), 4) if (ml_avail and _is_finite(ml_m.get('score')))
        else (round(float(ml_m['raw_score']), 4) if (ml_avail and _is_finite(ml_m.get('raw_score'))) else None)
    )
    ml_err = None
    if not ml_avail:
        rc = ml_m.get('reason') or (branches.get('ml') or {}).get('reason') or 'UNSUPERVISED_ML_UNAVAILABLE'
        ml_err = rc.get('code') if isinstance(rc, dict) else str(rc)
    ml_details = ml_m.get('details') or {}
    unsup_entry = {
        'method_id': 'unsupervised_ml',
        'method_label_vi': f'{FIVE_METHOD_LABELS_VI["unsupervised_ml"]} ({ml_key or "chưa cấu hình"})',
        'algorithm_id': ml_key,
        'score': ml_score_val,
        'raw_score': round(float(ml_m['raw_score']), 4) if (ml_avail and _is_finite(ml_m.get('raw_score'))) else None,
        'probability': None,
        'prediction': None,
        'threshold': None,
        'confidence_metadata': {
            'basis': 'empirical_midrank_not_probability' if ml_avail else 'unavailable',
            'score_kind': ml_m.get('score_kind'),
            'calibrated_for_probability': False,
        },
        'status': 'available' if ml_avail else 'unavailable',
        'model_version': ml_details.get('version_tag') or unsup_version_tag or ml_m.get('artifact_id'),
        'artifact_id': ml_m.get('artifact_id'),
        'circuit_version': None,
        'explanation_evidence': deepcopy(ml_details.get('top_contributing_features') or []),
        'error_code': ml_err,
    }

    # 5. Supervised LR (already conforms strictly to R3 schema)
    lr_entry = deepcopy(lr_dto)

    five_methods = [rules_entry, stat_entry, graph_entry, unsup_entry, lr_entry]

    # Weighted Risk Aggregation: SKIP any unavailable method (NEVER treat unavailable as 0!)
    weights_map = {
        'rules': cfg.rule_weight,
        'statistics': cfg.statistics_weight,
        'graph': cfg.graph_weight,
        'unsupervised_ml': cfg.unsupervised_ml_weight,
        'supervised_lr': cfg.supervised_lr_weight,
    }
    contributions = []
    total_score = 0.0
    any_scored = False
    unavailable_methods = []
    for entry in five_methods:
        mid = entry['method_id']
        w = float(weights_map[mid])
        is_unavail = entry['status'] == 'unavailable' or entry['score'] is None
        if is_unavail:
            unavailable_methods.append({
                'method_id': mid,
                'method_label_vi': entry['method_label_vi'],
                'status': entry['status'],
                'error_code': entry.get('error_code') or 'METHOD_UNAVAILABLE',
                'message': (entry.get('confidence_metadata') or {}).get('note') or entry.get('message') or 'Phương pháp chưa khả dụng.',
            })
            contributions.append({
                'method_id': mid,
                'name': entry['method_label_vi'],
                'status': entry['status'],
                'raw_score': None,
                'weight': w,
                'contribution': None,
                'error_code': entry.get('error_code'),
            })
        else:
            contrib = round(float(entry['score']) * w, 4)
            total_score += contrib
            any_scored = True
            contributions.append({
                'method_id': mid,
                'name': entry['method_label_vi'],
                'status': entry['status'],
                'raw_score': entry['score'],
                'weight': w,
                'contribution': contrib,
                'error_code': None,
            })

    return {
        'version': 'five-method-assessment/1.0.0',
        'five_methods': five_methods,
        'total_risk_score': round(total_score, 4) if any_scored else None,
        'contributions': contributions,
        'unavailable_methods': unavailable_methods,
        'unavailable_treated_as_zero': False,
        'scoring_config': cfg.to_dict(),
        'lr_deduplication': lr_entry.get('deduplication'),
    }
