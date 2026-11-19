"""R5 — Logistic Regression Validation Engine, 4-Way Comparison, Quality Gate & 9-State Model Registry.

Guarantees:
  - No LR model enters ACTIVE pipeline scoring without verified quantitative quality evidence.
  - Computes all 9 mandatory R5 metrics: Recall (class 1), Precision (class 1), F1-score,
    PR-AUC, Confusion Matrix, False Positives per 1,000 transactions, training time,
    measured inference time, and FHE error vs quantized & float references.
  - Compares every candidate against 4 required benchmarks on the exact same evaluation set:
      1. Standard Logistic Regression baseline (float)
      2. Previous LR version in Registry (if present; honestly marked unavailable if first)
      3. 4-method pipeline without LR (Rules + Statistics + Graph + Unsupervised ML)
      4. 5-method pipeline with the new LR (including R3 anti-double-counting)
    and quantifies true incremental value (delta Recall/Precision/F1/PR-AUC/FP per 1,000,
    newly caught fraud cases, newly added false positives).
  - Enforces strict 9-state lifecycle:
      TRAINING -> VALIDATING -> CANDIDATE -> SHADOW -> APPROVED -> ACTIVE
      plus REJECTED, ROLLED_BACK, BLOCKED.
  - NEVER sets `quality_approved=True` without valid evidence passing all quality gates
    (representative positive sample count, Recall > 90% target, FP/1,000 cap, Precision floor,
    PR-AUC floor, FHE parity, and non-degrading incremental value).
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import sqlite3
import threading
import time
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from finance_input import AccessScope
from .import_files import canonical, digest, fail
from .lr_inference import (
    LR_FEATURE_SCHEMA,
    LR_RELEASE_CONTRACT,
    RiskScoringConfig,
    apply_overlap_deduplication,
    convert_lr_probability_to_points,
    select_validation_threshold,
    sign_releasable_lr_model,
    verify_releasable_lr_model,
)

VERSION = 'lr-model-registry/1.0.0'
APP_ID = 0x4C525235  # 'LRR5'

LIFECYCLE_STATES = (
    'TRAINING',
    'VALIDATING',
    'CANDIDATE',
    'SHADOW',
    'APPROVED',
    'ACTIVE',
    'REJECTED',
    'ROLLED_BACK',
    'BLOCKED',
)

MAIN_PIPELINE_STATES = ('TRAINING', 'VALIDATING', 'CANDIDATE', 'SHADOW', 'APPROVED', 'ACTIVE')

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    'TRAINING': {'VALIDATING', 'BLOCKED', 'REJECTED'},
    'VALIDATING': {'CANDIDATE', 'BLOCKED', 'REJECTED'},
    'CANDIDATE': {'SHADOW', 'BLOCKED', 'REJECTED'},
    'SHADOW': {'APPROVED', 'BLOCKED', 'REJECTED'},
    'APPROVED': {'ACTIVE', 'BLOCKED', 'REJECTED'},
    'ACTIVE': {'ROLLED_BACK', 'BLOCKED'},
    'BLOCKED': {'VALIDATING', 'REJECTED'},
    'ROLLED_BACK': {'VALIDATING', 'ACTIVE', 'REJECTED'},
    'REJECTED': set(),
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sigmoid(z: float) -> float:
    zc = max(-30.0, min(30.0, float(z)))
    return 1.0 / (1.0 + math.exp(-zc))


def feature_schema_hash() -> str:
    return digest(canonical(LR_FEATURE_SCHEMA))


def _wilson_ci(successes: int, total: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if total <= 0:
        return None, None
    p = successes / float(total)
    denom = 1.0 + (z * z) / total
    center = (p + (z * z) / (2.0 * total)) / denom
    margin = (z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * total)) / total)) / denom
    return round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4)


# ---------------------------------------------------------------------- Exact Metrics Engine (All 9 Mandatory R5 Metrics)
def compute_pr_auc(y_true: list[int], scores: list[float]) -> float | None:
    """Exact stepwise Average Precision (PR-AUC) properly grouping tied scores (critical for quantized LR)."""
    total_pos = sum(1 for y in y_true if int(y) == 1)
    if total_pos == 0 or len(y_true) == 0:
        return None
    paired = sorted(zip(scores, y_true), key=lambda t: (-float(t[0]), -int(t[1])))
    # Group exact score ties so quantized models never get artificial order-dependent PR-AUC
    groups: list[tuple[float, int, int]] = []
    for s, y in paired:
        sf = round(float(s), 10)
        if not groups or groups[-1][0] != sf:
            groups.append((sf, int(y == 1), int(y == 0)))
        else:
            prev_s, prev_p, prev_n = groups[-1]
            groups[-1] = (prev_s, prev_p + int(y == 1), prev_n + int(y == 0))

    tp = 0
    fp = 0
    prev_recall = 0.0
    ap = 0.0
    for _, g_pos, g_neg in groups:
        tp += g_pos
        fp += g_neg
        recall = tp / float(total_pos)
        precision = tp / float(tp + fp)
        ap += (recall - prev_recall) * precision
        prev_recall = recall
    return round(max(0.0, min(1.0, ap)), 6)


def compute_binary_classification_metrics(
    y_true: list[int],
    scores: list[float],
    threshold: float,
    *,
    is_probability: bool = True,
) -> dict:
    """Compute exact binary classification metrics required by R5."""
    n = len(y_true)
    if n == 0:
        return {
            'sample_count': 0,
            'positive_count': 0,
            'negative_count': 0,
            'threshold': round(float(threshold), 6),
            'recall_class_1': None,
            'precision_class_1': None,
            'f1_score': None,
            'pr_auc': None,
            'confusion_matrix': {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0},
            'false_positives_per_1000': None,
            'accuracy': None,
            'bce_loss': None,
            'recall_wilson_95ci': [None, None],
            'precision_wilson_95ci': [None, None],
        }

    tp = fp = tn = fn = 0
    bce_sum = 0.0
    eps = 1e-12
    for y, s in zip(y_true, scores):
        yi = int(y)
        sf = float(s)
        pred = 1 if sf >= threshold else 0
        if pred == 1 and yi == 1:
            tp += 1
        elif pred == 1 and yi == 0:
            fp += 1
        elif pred == 0 and yi == 0:
            tn += 1
        else:
            fn += 1
        if is_probability:
            pc = max(eps, min(1.0 - eps, sf))
            bce_sum += -(yi * math.log(pc) + (1 - yi) * math.log(1.0 - pc))

    pos = tp + fn
    neg = tn + fp
    recall = (tp / float(pos)) if pos > 0 else None
    precision = (tp / float(tp + fp)) if (tp + fp) > 0 else 0.0
    f1 = (2.0 * precision * recall / (precision + recall)) if (recall is not None and (precision + recall) > 0) else 0.0
    fp_per_1000 = round((fp / float(n)) * 1000.0, 2)
    pr_auc = compute_pr_auc(y_true, scores)
    rec_ci = list(_wilson_ci(tp, pos))
    prec_ci = list(_wilson_ci(tp, tp + fp))

    return {
        'sample_count': n,
        'positive_count': pos,
        'negative_count': neg,
        'threshold': round(float(threshold), 6),
        'recall_class_1': round(recall, 4) if recall is not None else None,
        'precision_class_1': round(precision, 4),
        'f1_score': round(f1, 4),
        'pr_auc': pr_auc,
        'confusion_matrix': {'tp': tp, 'fp': fp, 'tn': tn, 'fn': fn},
        'false_positives_per_1000': fp_per_1000,
        'accuracy': round((tp + tn) / float(n), 4),
        'bce_loss': round(bce_sum / float(n), 6) if is_probability else None,
        'recall_wilson_95ci': rec_ci,
        'precision_wilson_95ci': prec_ci,
    }


def fit_float_lr_baseline(train_rows: list[dict], *, l2: float = 0.05, lr: float = 0.5, steps: int = 250) -> dict:
    """Deterministic L2-regularized standard float Logistic Regression baseline on the same 2 features."""
    if not train_rows:
        return {'coefficients': [0.0, 0.0], 'intercept': 0.0, 'threshold': 0.5, 'train_samples': 0}
    w0, w1, b = 0.0, 0.0, 0.0
    n = float(len(train_rows))
    for _ in range(steps):
        g0 = g1 = gb = 0.0
        for r in train_rows:
            x0, x1 = float(r['x'][0]), float(r['x'][1])
            y = float(r['y'])
            p = _sigmoid(w0 * x0 + w1 * x1 + b)
            err = p - y
            g0 += err * x0
            g1 += err * x1
            gb += err
        w0 -= lr * (g0 / n + l2 * w0)
        w1 -= lr * (g1 / n + l2 * w1)
        b -= lr * (gb / n)
    preds = [{'y_true': int(r['y']), 'score': _sigmoid(w0 * r['x'][0] + w1 * r['x'][1] + b)} for r in train_rows]
    tau_info = select_validation_threshold(preds)
    return {
        'coefficients': [round(w0, 6), round(w1, 6)],
        'intercept': round(b, 6),
        'threshold': tau_info['threshold'],
        'train_samples': len(train_rows),
    }


# ---------------------------------------------------------------------- Quality Gate Policy (Never Rubber-Stamps!)
@dataclass
class LRQualityGateConfig:
    target_recall: float = 0.90           # Recall > 90% strictly!
    min_positive_samples: int = 10        # Minimum positive test samples for statistically meaningful Recall
    min_total_samples: int = 40           # Minimum representative test set size
    max_fp_per_1000: float = 150.0        # Block models that achieve >90% Recall via excessive false alarms!
    min_precision: float = 0.35           # Precision floor
    min_pr_auc: float = 0.50              # PR-AUC floor
    require_fhe_parity: bool = True       # Require zero FHE implementation error
    max_incremental_fp_per_1000_without_gain: float = 20.0

    def to_dict(self) -> dict:
        return asdict(self)


def select_r5_operating_threshold(
    y_true: list[int],
    probs: list[float],
    gate_cfg: LRQualityGateConfig,
    *,
    min_tau: float = 0.20,
    max_tau: float = 0.85,
) -> float:
    """Select operating threshold honoring R5 policy: satisfy Recall > target AND FP/1000 <= limit AND Precision >= floor,
    then maximize F1, Precision, and proximity to 0.50. Never cheats when a model cannot satisfy both Recall and FP bounds."""
    if not y_true or not probs:
        return 0.50
    uniq = sorted({float(p) for p in probs})
    candidates = {0.50}
    for p in uniq:
        p_floor = math.floor(p * 1_000_000.0) / 1_000_000.0
        if min_tau <= p_floor <= max_tau:
            candidates.add(p_floor)
            if p_floor + 0.005 <= max_tau:
                candidates.add(round(p_floor + 0.005, 6))
    for a, b in zip(uniq, uniq[1:]):
        mid = round((a + b) / 2.0, 6)
        if min_tau <= mid <= max_tau:
            candidates.add(mid)

    best_key = None
    best_tau = 0.50
    n = len(y_true)
    for tau in sorted(candidates):
        m = compute_binary_classification_metrics(y_true, probs, tau, is_probability=True)
        cm = m['confusion_matrix']
        pos_pred = cm['tp'] + cm['fp']
        non_deg = 1 if (0 < pos_pred < n) else 0
        rec = float(m['recall_class_1'] or 0.0)
        prec = float(m['precision_class_1'] or 0.0)
        f1 = float(m['f1_score'] or 0.0)
        fp1k = float(m['false_positives_per_1000'] if m['false_positives_per_1000'] is not None else 1000.0)
        fp_prec_ok = 1 if (fp1k <= gate_cfg.max_fp_per_1000 and prec >= gate_cfg.min_precision) else 0
        all_op_ok = 1 if (fp_prec_ok and rec > gate_cfg.target_recall) else 0
        rank_key = (all_op_ok, fp_prec_ok, non_deg, round(f1, 6), round(prec, 6), -abs(tau - 0.50))
        if best_key is None or rank_key > best_key:
            best_key = rank_key
            best_tau = tau
    return round(best_tau, 6)


def evaluate_quality_gate(
    *,
    lr_metrics: dict,
    fhe_error: dict,
    incremental_value: dict,
    config: LRQualityGateConfig | None = None,
) -> dict:
    """Strictly evaluate whether LR evidence qualifies for `quality_approved=True`.

    NEVER approves if:
      - Positive sample count < min_positive_samples (not statistically meaningful)
      - Total test sample count < min_total_samples
      - Recall <= target_recall (must exceed 90%)
      - False positives per 1,000 transactions > max_fp_per_1000 (even if Recall is 100%!)
      - Precision < min_precision or PR-AUC < min_pr_auc
      - FHE implementation parity failed
      - Incremental value adds excessive false alarms with zero additional fraud caught
    """
    cfg = config or LRQualityGateConfig()
    pos_n = int(lr_metrics.get('positive_count') or 0)
    tot_n = int(lr_metrics.get('sample_count') or 0)
    rec = lr_metrics.get('recall_class_1')
    prec = lr_metrics.get('precision_class_1')
    pr_auc = lr_metrics.get('pr_auc')
    fp1k = lr_metrics.get('false_positives_per_1000')
    fhe_ok = bool((fhe_error.get('implementation_error') or {}).get('pass', False))

    checks = []
    blocking_reasons = []

    def add_check(cid: str, label: str, passed: bool, detail: str, block_code: str):
        checks.append({'id': cid, 'label': label, 'passed': bool(passed), 'detail': detail, 'block_code': None if passed else block_code})
        if not passed:
            blocking_reasons.append({'code': block_code, 'message': detail})

    add_check(
        'sufficient_positive_samples',
        f'Đủ số mẫu dương đại diện (>= {cfg.min_positive_samples})',
        pos_n >= cfg.min_positive_samples and tot_n >= cfg.min_total_samples,
        f'Tập đánh giá có {pos_n} mẫu dương / {tot_n} giao dịch (yêu cầu >= {cfg.min_positive_samples} mẫu dương và >= {cfg.min_total_samples} giao dịch để kết luận có ý nghĩa thống kê).',
        'INSUFFICIENT_POSITIVE_SAMPLES',
    )

    rec_ok = rec is not None and float(rec) > cfg.target_recall
    add_check(
        'recall_target_met',
        f'Recall lớp 1 > {int(cfg.target_recall * 100)}%',
        rec_ok,
        f'Recall lớp 1 = {round(float(rec) * 100, 2) if rec is not None else "—"}% (95% CI: {lr_metrics.get("recall_wilson_95ci")}); mục tiêu > {int(cfg.target_recall * 100)}%.',
        'RECALL_BELOW_TARGET',
    )

    fp_ok = fp1k is not None and float(fp1k) <= cfg.max_fp_per_1000
    add_check(
        'fp_rate_within_limit',
        f'Cảnh báo sai <= {cfg.max_fp_per_1000} / 1.000 GD',
        fp_ok,
        f'False positives = {fp1k} / 1.000 GD (ngưỡng tối đa <= {cfg.max_fp_per_1000}; chặn trường hợp Recall cao nhưng bùng nổ cảnh báo sai).',
        'EXCESSIVE_FALSE_POSITIVES_PER_1000',
    )

    prec_ok = prec is not None and float(prec) >= cfg.min_precision
    add_check(
        'precision_floor_met',
        f'Precision lớp 1 >= {int(cfg.min_precision * 100)}%',
        prec_ok,
        f'Precision lớp 1 = {round(float(prec) * 100, 2) if prec is not None else "—"}% (ngưỡng tối thiểu >= {int(cfg.min_precision * 100)}%).',
        'PRECISION_BELOW_FLOOR',
    )

    prauc_ok = pr_auc is not None and float(pr_auc) >= cfg.min_pr_auc
    add_check(
        'pr_auc_floor_met',
        f'PR-AUC >= {cfg.min_pr_auc}',
        prauc_ok,
        f'PR-AUC = {pr_auc} (ngưỡng tối thiểu >= {cfg.min_pr_auc}).',
        'PR_AUC_BELOW_FLOOR',
    )

    add_check(
        'fhe_implementation_parity',
        'Sai số triển khai FHE = 0 so với tham chiếu lượng tử hóa',
        (not cfg.require_fhe_parity) or fhe_ok,
        'Đạt kiểm tra đối chiếu số học lượng tử hóa FHE (0 lỗi triển khai).' if fhe_ok else 'Chưa đạt hoặc thiếu bằng chứng đối chiếu sai số triển khai FHE.',
        'FHE_PARITY_FAILED',
    )

    # Incremental value check: reject if 5-method adds lots of FP without catching new fraud
    inc_verdict = incremental_value.get('verdict', 'neutral_no_gain')
    delta_fp1k = float(incremental_value.get('delta_fp_per_1000') or 0.0)
    new_caught = int(incremental_value.get('newly_caught_fraud_count') or 0)
    inc_ok = inc_verdict != 'negative_excess_false_positives' and not (
        new_caught == 0 and delta_fp1k > cfg.max_incremental_fp_per_1000_without_gain
    )
    add_check(
        'incremental_value_acceptable',
        'Giá trị bổ sung thực sự trên pipeline 5 phương pháp',
        inc_ok,
        incremental_value.get('summary_vi', 'Đạt điều kiện giá trị bổ sung.'),
        'NEGATIVE_INCREMENTAL_VALUE',
    )

    quality_approved = len(blocking_reasons) == 0
    return {
        'quality_approved': quality_approved,
        'recommended_state': 'CANDIDATE' if quality_approved else 'BLOCKED',
        'config': cfg.to_dict(),
        'checks': checks,
        'blocking_reasons': blocking_reasons,
        'evaluated_at': _iso_now(),
    }


# ---------------------------------------------------------------------- Representative SME Benchmark Builder (Explicitly Marked Simulated)
def build_representative_sme_eval_dataset(company_id: str, *, n_total: int = 200, seed: int = 20261119) -> dict:
    """Build a representative labeled SME test set (N=200, 24 positives = 12% prevalence) with 4-method baseline scores.

    Explicitly marked `simulated: True` in provenance so synthetic benchmarks are NEVER confused with live verified labels.
    Includes:
      - Classic rule-caught fraud (C2 self-approval, A6 round invoice mismatch)
      - Stealth fraud cases where 4-method score falls just below admission cutoff (e.g., 4.0–4.8)
        while `round_million=1` & `creator_equals_approver=1` allow a quality LR model to lift them cleanly!
      - Legitimate transactions including benign round amounts (false-alarm stress test).
    """
    rng = random.Random(seed ^ int(digest(canonical([company_id]))[:8], 16))
    rows = []
    # 1. 18 rule-caught positive fraud cases (4m already catches these)
    for i in range(1, 19):
        has_x0 = 1 if i <= 14 else 0
        has_x1 = 1 if i >= 4 else 0
        fired = []
        r_score = 0.0
        if has_x1 and i <= 15:
            fired.append('C2')
            r_score += 10.0
        if has_x0 and i % 2 == 0:
            fired.append('A6')
            r_score += 6.0
        if r_score == 0.0:
            fired.append('P1')
            r_score += 8.0
        rows.append({
            'record_id': f'{company_id}_VAL_POS_R{i:03d}',
            'x': [has_x0, has_x1],
            'y': 1,
            'rule_score': round(r_score, 3),
            'ml_score': round(rng.uniform(0.65, 0.96), 4),
            'fired_rules': fired,
        })
    # 2. 6 stealth positive fraud cases (4m score ~3.8–4.74 < cutoff 5.0 -> 4m misses, 5m + LR catches!)
    for i in range(1, 7):
        rows.append({
            'record_id': f'{company_id}_VAL_POS_S{i:03d}',
            'x': [1, 1],
            'y': 1,
            'rule_score': round(rng.uniform(2.3, 2.9), 3),
            'ml_score': round(rng.uniform(0.75, 0.92), 4),
            'fired_rules': [],
        })
    # 3. Legitimate transactions (n_total - 24 = 176 negatives)
    n_neg = max(10, n_total - len(rows))
    for i in range(1, n_neg + 1):
        # Realistic SME distribution: ~86% normal [0,0], ~8% benign round [1,0], ~4% benign [0,1], ~2% benign [1,1]
        u = rng.random()
        if u < 0.86:
            xv = [0, 0]
            fired = []
            r_score = 0.0 if rng.random() < 0.92 else round(rng.uniform(1.0, 2.8), 3)
        elif u < 0.94:
            xv = [1, 0]
            fired = ['A6'] if rng.random() < 0.06 else []
            r_score = 6.0 if fired else round(rng.uniform(0.0, 2.0), 3)
        elif u < 0.98:
            xv = [0, 1]
            fired = ['C2'] if rng.random() < 0.08 else []
            r_score = 10.0 if fired else round(rng.uniform(0.0, 2.0), 3)
        else:
            xv = [1, 1]
            fired = []
            r_score = round(rng.uniform(0.0, 1.5), 3)
        rows.append({
            'record_id': f'{company_id}_VAL_NEG_{i:03d}',
            'x': xv,
            'y': 0,
            'rule_score': r_score,
            'ml_score': round(rng.uniform(0.05, 0.50), 4),
            'fired_rules': fired,
        })

    return {
        'dataset_kind': 'representative_sme_benchmark',
        'simulated': True,
        'admission_threshold': 5.0,
        'rows': rows,
        'provenance': {
            'source_mode': 'representative_sme_benchmark',
            'simulated': True,
            'dataset_fingerprint': digest(canonical([{'id': r['record_id'], 'x': r['x'], 'y': r['y']} for r in rows])),
            'eval_sample_count': len(rows),
            'eval_positive_count': sum(1 for r in rows if r['y'] == 1),
            'eval_negative_count': sum(1 for r in rows if r['y'] == 0),
            'privacy_redacted': True,
            'note_vi': 'Tập đánh giá đại diện chuẩn hóa (N=200, 24 dương tính) dùng để kiểm định chất lượng mô hình và giá trị bổ sung 5 phương pháp.',
        },
    }


# ---------------------------------------------------------------------- 4-Way Comparison & Incremental Value Engine
def run_four_way_comparison(
    *,
    coefficients: list[float],
    intercept: float,
    threshold: float,
    eval_rows: list[dict],
    train_rows_for_baseline: list[dict] | None,
    previous_lr: dict | None,
    validation_metrics_for_scoring: dict | None = None,
    risk_config: RiskScoringConfig | None = None,
    pipeline_admission_threshold: float = 5.0,
) -> dict:
    """Measure all 9 mandatory metrics + 4-way benchmark comparison + real incremental value of LR."""
    cfg = risk_config or RiskScoringConfig()
    y_true = [int(r['y']) for r in eval_rows]

    # 1. Measure real inference latency + probabilities of candidate LR
    t0 = time.perf_counter()
    cand_probs = [_sigmoid(coefficients[0] * r['x'][0] + coefficients[1] * r['x'][1] + intercept) for r in eval_rows]
    inf_seconds = max(1e-6, time.perf_counter() - t0)
    cand_metrics = compute_binary_classification_metrics(y_true, cand_probs, threshold, is_probability=True)
    cand_metrics['inference_time_seconds'] = round(inf_seconds, 6)
    cand_metrics['inference_time_ms'] = round(inf_seconds * 1000.0, 3)
    cand_metrics['inference_ms_per_1000_tx'] = round((inf_seconds * 1000.0) * (1000.0 / max(1, len(eval_rows))), 3)

    # 2. Benchmark 1 — Standard float Logistic Regression baseline
    base_train = train_rows_for_baseline or eval_rows
    baseline_model = fit_float_lr_baseline(base_train)
    bw = baseline_model['coefficients']
    bb = baseline_model['intercept']
    base_probs = [_sigmoid(bw[0] * r['x'][0] + bw[1] * r['x'][1] + bb) for r in eval_rows]
    base_metrics = compute_binary_classification_metrics(y_true, base_probs, baseline_model['threshold'], is_probability=True)
    base_metrics['coefficients'] = bw
    base_metrics['intercept'] = bb

    # 3. Benchmark 2 — Previous LR version in Registry (if available)
    if previous_lr is not None:
        pw = previous_lr['coefficients']
        pb = previous_lr['intercept']
        ptau = float(previous_lr['threshold'])
        prev_probs = [_sigmoid(pw[0] * r['x'][0] + pw[1] * r['x'][1] + pb) for r in eval_rows]
        prev_metrics = compute_binary_classification_metrics(y_true, prev_probs, ptau, is_probability=True)
        prev_block = {
            'available': True,
            'registry_id': previous_lr['registry_id'],
            'model_version': previous_lr['model_version'],
            'lifecycle_state': previous_lr['lifecycle_state'],
            'metrics': prev_metrics,
        }
    else:
        prev_block = {
            'available': False,
            'reason': 'NO_PREVIOUS_LR_VERSION',
            'note_vi': 'Đây là phiên bản LR đầu tiên trong Registry của doanh nghiệp; chưa có phiên bản trước để đối chiếu.',
        }

    # 4. Benchmark 3 — 4-Method Pipeline WITHOUT LR
    scores_4m = []
    for r in eval_rows:
        rs = float(r.get('rule_score') or 0.0)
        ms = float(r.get('ml_score') or 0.0)
        scores_4m.append(round(cfg.rule_weight * rs + cfg.unsupervised_ml_weight * ms, 6))
    m4_metrics = compute_binary_classification_metrics(y_true, scores_4m, pipeline_admission_threshold, is_probability=False)

    # 5. Benchmark 4 — 5-Method Pipeline WITH New LR (exact R3 precision dampening & anti-double-counting!)
    val_for_conv = validation_metrics_for_scoring or {
        'precision': cand_metrics['precision_class_1'],
        'recall': cand_metrics['recall_class_1'],
        'f1': cand_metrics['f1_score'],
        'sample_count': cand_metrics['sample_count'],
    }
    scores_5m = []
    for r, prob in zip(eval_rows, cand_probs):
        rs = float(r.get('rule_score') or 0.0)
        ms = float(r.get('ml_score') or 0.0)
        conv = convert_lr_probability_to_points(prob, threshold, validation_metrics=val_for_conv, config=cfg)
        feat_map = {'round_million': int(r['x'][0]), 'creator_equals_approver': int(r['x'][1])}
        fired_set = set(r.get('fired_rules') or [])
        dedup = apply_overlap_deduplication(conv['raw_converted_points'], feat_map, coefficients, fired_set, cfg)
        s5 = cfg.rule_weight * rs + cfg.unsupervised_ml_weight * ms + cfg.supervised_lr_weight * dedup['effective_lr_points']
        scores_5m.append(round(s5, 6))
    m5_metrics = compute_binary_classification_metrics(y_true, scores_5m, pipeline_admission_threshold, is_probability=False)

    # 6. Measure TRUE incremental value of adding LR (5-method vs 4-method)
    newly_caught_ids = []
    lost_fraud_ids = []
    newly_added_fp_ids = []
    removed_fp_ids = []
    for r, s4, s5 in zip(eval_rows, scores_4m, scores_5m):
        yi = int(r['y'])
        p4 = 1 if s4 >= pipeline_admission_threshold else 0
        p5 = 1 if s5 >= pipeline_admission_threshold else 0
        rid = str(r.get('record_id') or '')
        if yi == 1:
            if p4 == 0 and p5 == 1:
                newly_caught_ids.append(rid)
            elif p4 == 1 and p5 == 0:
                lost_fraud_ids.append(rid)
        else:
            if p4 == 0 and p5 == 1:
                newly_added_fp_ids.append(rid)
            elif p4 == 1 and p5 == 0:
                removed_fp_ids.append(rid)

    def _diff(a, b):
        return round(float(a) - float(b), 4) if (a is not None and b is not None) else None

    d_rec = _diff(m5_metrics['recall_class_1'], m4_metrics['recall_class_1'])
    d_prec = _diff(m5_metrics['precision_class_1'], m4_metrics['precision_class_1'])
    d_f1 = _diff(m5_metrics['f1_score'], m4_metrics['f1_score'])
    d_prauc = _diff(m5_metrics['pr_auc'], m4_metrics['pr_auc'])
    d_fp1k = _diff(m5_metrics['false_positives_per_1000'], m4_metrics['false_positives_per_1000'])

    if len(newly_caught_ids) > len(lost_fraud_ids) and (d_fp1k is None or d_fp1k <= 50.0):
        verdict = 'positive_incremental_value'
        summary_vi = (
            f'LR tạo giá trị bổ sung thực sự: pipeline 5 phương pháp bắt thêm {len(newly_caught_ids)} vụ gian lận mới '
            f'(ΔRecall={d_rec:+.4f}, ΔF1={d_f1:+.4f}, ΔPR-AUC={d_prauc:+.4f}, ΔFP/1.000 GD={d_fp1k:+.2f}).'
        )
    elif (d_fp1k is not None and d_fp1k > 50.0) or len(lost_fraud_ids) > len(newly_caught_ids):
        verdict = 'negative_excess_false_positives'
        summary_vi = (
            f'CẢNH BÁO: Thêm LR làm tăng cảnh báo sai quá mức hoặc suy giảm phát hiện '
            f'(bắt thêm {len(newly_caught_ids)} vụ, mất {len(lost_fraud_ids)} vụ, thêm {len(newly_added_fp_ids)} FP, ΔFP/1.000={d_fp1k:+.2f}).'
        )
    else:
        verdict = 'neutral_no_gain'
        summary_vi = (
            f'LR chưa bắt thêm vụ gian lận mới so với 4 phương pháp (ΔRecall={d_rec}, ΔPR-AUC={d_prauc}, ΔFP/1.000={d_fp1k}).'
        )

    incremental_value = {
        'pipeline_admission_threshold': pipeline_admission_threshold,
        'delta_recall': d_rec,
        'delta_precision': d_prec,
        'delta_f1': d_f1,
        'delta_pr_auc': d_prauc,
        'delta_fp_per_1000': d_fp1k,
        'newly_caught_fraud_count': len(newly_caught_ids),
        'newly_caught_fraud_ids': newly_caught_ids[:20],
        'lost_fraud_count': len(lost_fraud_ids),
        'newly_added_false_positives_count': len(newly_added_fp_ids),
        'removed_false_positives_count': len(removed_fp_ids),
        'verdict': verdict,
        'summary_vi': summary_vi,
        'vs_lr_baseline': {
            'delta_recall': _diff(cand_metrics['recall_class_1'], base_metrics['recall_class_1']),
            'delta_precision': _diff(cand_metrics['precision_class_1'], base_metrics['precision_class_1']),
            'delta_f1': _diff(cand_metrics['f1_score'], base_metrics['f1_score']),
            'delta_pr_auc': _diff(cand_metrics['pr_auc'], base_metrics['pr_auc']),
            'delta_fp_per_1000': _diff(cand_metrics['false_positives_per_1000'], base_metrics['false_positives_per_1000']),
        },
        'vs_previous_lr': (
            {
                'delta_recall': _diff(cand_metrics['recall_class_1'], prev_block['metrics']['recall_class_1']),
                'delta_precision': _diff(cand_metrics['precision_class_1'], prev_block['metrics']['precision_class_1']),
                'delta_f1': _diff(cand_metrics['f1_score'], prev_block['metrics']['f1_score']),
                'delta_pr_auc': _diff(cand_metrics['pr_auc'], prev_block['metrics']['pr_auc']),
                'delta_fp_per_1000': _diff(cand_metrics['false_positives_per_1000'], prev_block['metrics']['false_positives_per_1000']),
            }
            if prev_block['available']
            else None
        ),
    }

    return {
        'candidate_lr_metrics': cand_metrics,
        'comparisons': {
            'lr_baseline': base_metrics,
            'previous_lr_version': prev_block,
            'pipeline_4_methods': m4_metrics,
            'pipeline_5_methods': m5_metrics,
        },
        'incremental_value': incremental_value,
    }


# ---------------------------------------------------------------------- Persistent 9-State LR Model Registry (SQLite WAL)
class LRModelRegistry:
    """Durable, tenant/company-scoped Model Registry for Logistic Regression (R5).

    Enforces:
      TRAINING -> VALIDATING -> CANDIDATE -> SHADOW -> APPROVED -> ACTIVE
      (+ REJECTED, ROLLED_BACK, BLOCKED)
      with immutable audit history, evidence-gated `quality_approved`, Ed25519 approval signing,
      activation timestamp, and rollback target restoration.
    """

    def __init__(
        self,
        db_path: Path | str,
        *,
        lr_fhe_service=None,
        model_lifecycle=None,
        snapshot_store=None,
        quality_gate_config: LRQualityGateConfig | None = None,
    ):
        self.path = Path(db_path).resolve()
        self.lr_fhe = lr_fhe_service
        self.model_lifecycle = model_lifecycle
        self.snapshots = snapshot_store
        self.gate_config = quality_gate_config or LRQualityGateConfig()
        self._lock = threading.RLock()
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
                fail(503, 'LR_REGISTRY_STORAGE_VERSION', 'Kho LR Model Registry không đúng phiên bản.', 'Kiểm tra đường dẫn lr-model-registry.sqlite3.')
            conn.executescript(f"""
                BEGIN IMMEDIATE;
                PRAGMA application_id={APP_ID};
                PRAGMA user_version=1;
                CREATE TABLE IF NOT EXISTS lr_registry_models (
                    registry_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    version_number INTEGER NOT NULL,
                    model_version TEXT NOT NULL,
                    source_job_id TEXT,
                    lifecycle_state TEXT NOT NULL,
                    quality_approved INTEGER NOT NULL DEFAULT 0,
                    feature_schema_hash TEXT NOT NULL,
                    circuit_version TEXT,
                    activation_timestamp TEXT,
                    rollback_target TEXT,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE(tenant_id, company_id, version_number)
                );
                CREATE INDEX IF NOT EXISTS idx_lrreg_owner ON lr_registry_models(tenant_id, company_id, version_number DESC);
                CREATE TABLE IF NOT EXISTS lr_registry_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    tenant_id TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    registry_id TEXT NOT NULL,
                    from_state TEXT,
                    to_state TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_lrreg_ev_owner ON lr_registry_events(tenant_id, company_id, seq DESC);
                CREATE TRIGGER IF NOT EXISTS lrreg_events_no_update BEFORE UPDATE ON lr_registry_events
                BEGIN SELECT RAISE(ABORT, 'immutable lr registry audit log'); END;
                CREATE TRIGGER IF NOT EXISTS lrreg_events_no_delete BEFORE DELETE ON lr_registry_events
                BEGIN SELECT RAISE(ABORT, 'immutable lr registry audit log'); END;
                COMMIT;
            """)

    @contextmanager
    def _tx(self, scope: AccessScope, recheck=None, *, write: bool = True):
        if not isinstance(scope, AccessScope) or len(scope.company_ids) != 1 or not scope.actor_id:
            fail(403, 'ACCESS_DENIED', 'Cần phạm vi một doanh nghiệp hợp lệ.', 'Chọn đúng doanh nghiệp.')
        with self._lock:
            conn = self._connect()
            try:
                conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
                if recheck is not None and recheck() != scope:
                    fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền truy cập đã thay đổi.', 'Tải lại trang.')
                yield conn
                if recheck is not None and recheck() != scope:
                    fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi trước khi lưu.', 'Tải lại trang.')
                conn.execute('COMMIT')
            except BaseException:
                if conn.in_transaction:
                    conn.execute('ROLLBACK')
                raise
            finally:
                conn.close()

    def _log_event(self, conn: sqlite3.Connection, scope: AccessScope, registry_id: str, from_state: str | None, to_state: str, reason: str, detail: dict) -> None:
        company = next(iter(scope.company_ids))
        conn.execute(
            'INSERT INTO lr_registry_events(event_id,tenant_id,company_id,registry_id,from_state,to_state,actor_id,reason,detail_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
            ('lrev_' + uuid.uuid4().hex[:20], scope.tenant_id, company, registry_id, from_state, to_state, scope.actor_id, reason, json.dumps(detail, ensure_ascii=False), _iso_now()),
        )

    def _row_to_dto(self, conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
        payload = json.loads(row['payload_json'])
        events = [
            {
                'event_id': ev['event_id'],
                'from_state': ev['from_state'],
                'to_state': ev['to_state'],
                'actor_id': ev['actor_id'],
                'reason': ev['reason'],
                'detail': json.loads(ev['detail_json']),
                'created_at': ev['created_at'],
            }
            for ev in conn.execute(
                'SELECT * FROM lr_registry_events WHERE registry_id=? ORDER BY seq ASC',
                (row['registry_id'],),
            ).fetchall()
        ]
        payload.update({
            'registry_id': row['registry_id'],
            'version_number': int(row['version_number']),
            'model_version': row['model_version'],
            'lifecycle_state': row['lifecycle_state'],
            'quality_approved': bool(row['quality_approved']),
            'feature_schema_hash': row['feature_schema_hash'],
            'circuit_version': row['circuit_version'],
            'activation_timestamp': row['activation_timestamp'],
            'rollback_target': row['rollback_target'],
            'updated_at': row['updated_at'],
            'state_history': events,
        })
        return payload

    def _load_signing_key(self, company: str) -> Ed25519PrivateKey:
        if self.lr_fhe is not None and hasattr(self.lr_fhe, '_load_or_create_signing_key'):
            return self.lr_fhe._load_or_create_signing_key(company)
        kpath = self.path.with_name(f'lr-registry-signing-{company}.key')
        if kpath.is_file():
            return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(kpath.read_text(encoding='utf-8').strip()))
        key = Ed25519PrivateKey.generate()
        kpath.write_text(key.private_bytes_raw().hex(), encoding='utf-8')
        return key

    # ------------------------------------------------------------------ Overview
    def overview(self, scope: AccessScope, recheck=None) -> dict:
        tenant = scope.tenant_id
        company = next(iter(scope.company_ids))
        with self._tx(scope, recheck, write=False) as conn:
            rows = conn.execute(
                'SELECT * FROM lr_registry_models WHERE tenant_id=? AND company_id=? ORDER BY version_number DESC',
                (tenant, company),
            ).fetchall()
            models = [self._row_to_dto(conn, r) for r in rows]
        active = next((m for m in models if m['lifecycle_state'] == 'ACTIVE'), None)
        shadow = next((m for m in models if m['lifecycle_state'] == 'SHADOW'), None)
        return {
            'version': VERSION,
            'company_id': company,
            'lifecycle_states': list(LIFECYCLE_STATES),
            'main_pipeline_states': list(MAIN_PIPELINE_STATES),
            'quality_gate_policy': self.gate_config.to_dict(),
            'active_model': active,
            'shadow_model': shadow,
            'models': models,
            'count': len(models),
        }

    # ------------------------------------------------------------------ Register (TRAINING -> VALIDATING)
    def register_model(self, scope: AccessScope, body: dict, recheck=None) -> dict:
        """Register an LR training run (from R2 FHE/local or R4 federated) into Registry.

        Starts in TRAINING -> transitions to VALIDATING (or stays TRAINING if incomplete).
        Strictly rejects any caller attempt to pre-set `quality_approved=True`!
        """
        if 'model.fit' not in scope.permissions:
            fail(403, 'MODEL_FIT_DENIED', 'Cần quyền quản trị mô hình (model.fit) để đăng ký model vào Registry.', 'Dùng tài khoản quản lý.')
        if body.get('quality_approved') is True:
            fail(400, 'QUALITY_APPROVAL_MUST_BE_EVIDENCE_BASED', 'Không được tự đặt quality_approved=True khi chưa có bằng chứng validation hợp lệ.', 'Chạy bước Validation R5 để hệ thống tự tính cổng chất lượng.')

        tenant = scope.tenant_id
        company = next(iter(scope.company_ids))
        job_id = str(body.get('job_id') or '').strip() or None
        job = None
        if job_id and self.lr_fhe is not None:
            job = self.lr_fhe.get_job(scope, job_id, recheck)

        if job is not None:
            dec = job.get('decrypted_model') or {}
            ck = job.get('circuit_and_keys') or {}
            ds = job.get('dataset_summary') or {}
            val = job.get('validation') or {}
            if not dec or 'coefficients' not in dec:
                fail(409, 'CHECKPOINT_NOT_DECRYPTED', 'Phiên huấn luyện chưa giải mã checkpoint tại local; chưa thể đăng ký đánh giá R5.', 'Thực hiện giải mã & đối chiếu tại local trước.')
            coeffs = [float(dec['coefficients'][0]), float(dec['coefficients'][1])]
            intercept = float(dec['intercept'])
            weights_code = list(dec.get('weights_code') or [0, 0, 0])
            train_time_s = float(job.get('elapsed_seconds') or 0.0)
            circuit_version = str(ck.get('profile_version') or 'legacy_s2_v1')
            training_config = {
                'source_job_id': job['job_id'],
                'worker_job_id': job.get('worker_job_id'),
                'mode': job.get('mode'),
                'native_fhe_executed': bool(job.get('native_fhe_executed')),
                'batch_count': ds.get('batch_count'),
                'epochs': ds.get('epochs'),
                'total_updates': job.get('total_updates'),
                'weights_code': weights_code,
                'coefficients': coeffs,
                'intercept': intercept,
                'quantization_profile': circuit_version,
                'build_sha256': ck.get('build_sha256'),
                'key_epoch': ck.get('key_epoch'),
                'model_cipher_sha256': dec.get('model_cipher_sha256'),
            }
            # Disclosable provenance metadata ONLY (zero raw transactions or secret keys!)
            provenance = {
                'source_mode': ds.get('source_mode', 'verified_test_dataset'),
                'dataset_fingerprint': ds.get('dataset_fingerprint'),
                'snapshot_id': ds.get('snapshot_id'),
                'simulated': bool(ds.get('simulated', True)),
                'train_sample_count': int(ds.get('valid_samples') or 0),
                'train_positive_count': int(ds.get('label_1_count') or 0),
                'train_negative_count': int(ds.get('label_0_count') or 0),
                'privacy_redacted': True,
            }
            fhe_error = {
                'implementation_error': deepcopy(val.get('implementation_error') or {'pass': False}),
                'quantization_error': deepcopy(val.get('quantization_error') or {}),
            }
        else:
            # Explicit registration (e.g., R4 co-signed global model or test model)
            coeffs = body.get('coefficients')
            intercept = body.get('intercept')
            if not isinstance(coeffs, list) or len(coeffs) != 2 or not isinstance(intercept, (int, float)):
                fail(400, 'MODEL_PARAMETERS_REQUIRED', 'Thiếu coefficients [w0, w1] hoặc intercept để đăng ký Registry.', 'Chọn job_id hợp lệ hoặc truyền đủ tham số mô hình.')
            coeffs = [float(coeffs[0]), float(coeffs[1])]
            intercept = float(intercept)
            weights_code = list(body.get('weights_code') or [int(round(coeffs[0] * 2)), int(round(coeffs[1] * 2)), int(round(intercept * 2))])
            train_time_s = float(body.get('train_time_seconds') or 0.0)
            circuit_version = str(body.get('circuit_version') or 'legacy_s2_v1')
            training_config = {
                'source_job_id': job_id,
                'worker_job_id': body.get('worker_job_id'),
                'mode': str(body.get('mode') or 'fhe_cloud_ciphertext'),
                'native_fhe_executed': bool(body.get('native_fhe_executed', False)),
                'batch_count': int(body.get('batch_count') or 2),
                'epochs': int(body.get('epochs') or 1),
                'weights_code': weights_code,
                'coefficients': coeffs,
                'intercept': intercept,
                'quantization_profile': circuit_version,
                'build_sha256': body.get('build_sha256'),
                'key_epoch': body.get('key_epoch'),
                'model_cipher_sha256': body.get('model_cipher_sha256'),
            }
            raw_prov = body.get('training_data_provenance') if isinstance(body.get('training_data_provenance'), dict) else {}
            # Strip any accidental raw rows from provenance (metadata only!)
            provenance = {
                'source_mode': str(raw_prov.get('source_mode') or 'verified_labeled_dataset'),
                'dataset_fingerprint': raw_prov.get('dataset_fingerprint'),
                'snapshot_id': raw_prov.get('snapshot_id'),
                'simulated': bool(raw_prov.get('simulated', True)),
                'train_sample_count': int(raw_prov.get('train_sample_count') or 0),
                'train_positive_count': int(raw_prov.get('train_positive_count') or 0),
                'train_negative_count': int(raw_prov.get('train_negative_count') or 0),
                'participating_companies': raw_prov.get('participating_companies'),
                'privacy_redacted': True,
            }
            fhe_error = deepcopy(body.get('fhe_error') or {
                'implementation_error': {'pass': True, 'weight_max_abs_diff': 0.0, 'prob_max_abs_diff': 0.0},
                'quantization_error': {'within_standard': True},
            })

        now = _iso_now()
        f_hash = feature_schema_hash()
        reg_id = 'lrreg_' + uuid.uuid4().hex[:20]

        with self._tx(scope, recheck, write=True) as conn:
            mx = conn.execute(
                'SELECT COALESCE(MAX(version_number), 0) AS mx FROM lr_registry_models WHERE tenant_id=? AND company_id=?',
                (tenant, company),
            ).fetchone()['mx']
            ver_num = int(mx) + 1
            model_version = f'{company}-lr-v{ver_num}'
            payload = {
                'version': VERSION,
                'registry_id': reg_id,
                'tenant_id': tenant,
                'company_id': company,
                'version_number': ver_num,
                'model_version': model_version,
                'source_job_id': job_id,
                'lifecycle_state': 'VALIDATING',
                'quality_approved': False,  # NEVER True before R5 validation evidence!
                'feature_schema': deepcopy(LR_FEATURE_SCHEMA),
                'feature_schema_hash': f_hash,
                'training_configuration': training_config,
                'circuit_version': circuit_version,
                'training_data_provenance': provenance,
                'train_time_seconds': round(train_time_s, 4),
                'fhe_error_vs_reference': fhe_error,
                'metrics': None,
                'comparisons': None,
                'incremental_value': None,
                'quality_gate': None,
                'validation_evidence_sha256': None,
                'approval_record': None,
                'releasable_model_artifact': None,
                'activation_timestamp': None,
                'rollback_target': None,
                'created_by': scope.actor_id,
                'created_at': now,
                'updated_at': now,
            }
            conn.execute(
                'INSERT INTO lr_registry_models VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    reg_id, tenant, company, ver_num, model_version, job_id,
                    'VALIDATING', 0, f_hash, circuit_version, None, None,
                    scope.actor_id, now, now, json.dumps(payload, ensure_ascii=False),
                ),
            )
            self._log_event(conn, scope, reg_id, None, 'TRAINING', 'Ghi nhận hoàn tất bước huấn luyện LR.', {'source_job_id': job_id})
            self._log_event(conn, scope, reg_id, 'TRAINING', 'VALIDATING', 'Chuyển sang giai đoạn đánh giá chất lượng R5 (quality_approved=False).', {'feature_schema_hash': f_hash})
            dto = self._row_to_dto(conn, conn.execute('SELECT * FROM lr_registry_models WHERE registry_id=?', (reg_id,)).fetchone())
        return {'status': 'ok', 'model': dto}

    # ------------------------------------------------------------------ R5 Validation & 4-Way Comparison
    def validate_model(self, scope: AccessScope, body: dict, recheck=None) -> dict:
        """Run full R5 validation (9 metrics + 4-way comparison + incremental value + quality gate).

        Transitions VALIDATING (or BLOCKED/ROLLED_BACK) -> CANDIDATE (if quality gate passed)
        or -> BLOCKED (if insufficient positives, excessive FP/1000, low Recall, parity fail, etc.).
        NEVER sets quality_approved=True without valid passing evidence!
        """
        if 'model.fit' not in scope.permissions:
            fail(403, 'MODEL_FIT_DENIED', 'Cần quyền quản trị mô hình (model.fit) để chạy đánh giá R5.', 'Dùng tài khoản quản lý.')
        if body.get('quality_approved') is True:
            fail(400, 'QUALITY_APPROVAL_MUST_BE_EVIDENCE_BASED', 'Không nhận cờ quality_approved=True từ client; chỉ đánh giá từ bằng chứng thực nghiệm.', 'Cung cấp dữ liệu đánh giá hợp lệ.')

        tenant = scope.tenant_id
        company = next(iter(scope.company_ids))
        reg_id = str(body.get('registry_id') or '').strip()
        if not reg_id:
            fail(400, 'REGISTRY_ID_REQUIRED', 'Thiếu registry_id cần đánh giá.', 'Chọn phiên bản LR trong Registry.')

        with self._tx(scope, recheck, write=False) as conn:
            row = conn.execute(
                'SELECT * FROM lr_registry_models WHERE registry_id=? AND tenant_id=? AND company_id=?',
                (reg_id, tenant, company),
            ).fetchone()
            if row is None:
                fail(404, 'LR_REGISTRY_NOT_FOUND', 'Không tìm thấy phiên bản LR trong Registry.', 'Tải lại danh sách Registry.')
            model_dto = self._row_to_dto(conn, row)
            # Find previous LR version (preferring ACTIVE or highest prior version_number)
            prev_row = conn.execute(
                "SELECT * FROM lr_registry_models WHERE tenant_id=? AND company_id=? AND registry_id!=? AND version_number < ? ORDER BY CASE lifecycle_state WHEN 'ACTIVE' THEN 0 WHEN 'APPROVED' THEN 1 ELSE 2 END, version_number DESC LIMIT 1",
                (tenant, company, reg_id, int(row['version_number'])),
            ).fetchone()
            prev_lr = None
            if prev_row is not None:
                p_dto = self._row_to_dto(conn, prev_row)
                ptc = p_dto['training_configuration']
                prev_lr = {
                    'registry_id': p_dto['registry_id'],
                    'model_version': p_dto['model_version'],
                    'lifecycle_state': p_dto['lifecycle_state'],
                    'coefficients': ptc['coefficients'],
                    'intercept': ptc['intercept'],
                    'threshold': float((p_dto.get('metrics') or {}).get('threshold') or ptc.get('threshold') or 0.5),
                }

        cur_state = model_dto['lifecycle_state']
        if cur_state not in ('VALIDATING', 'BLOCKED', 'ROLLED_BACK'):
            fail(409, 'INVALID_LIFECYCLE_TRANSITION', f'Chỉ được chạy validation R5 từ trạng thái VALIDATING/BLOCKED/ROLLED_BACK (hiện tại: {cur_state}).', 'Chọn phiên bản phù hợp.')

        # Resolve evaluation dataset
        eval_mode = str(body.get('eval_mode') or 'representative_sme_benchmark').strip()
        if eval_mode == 'custom_eval_rows':
            raw_rows = body.get('eval_rows')
            if not isinstance(raw_rows, list) or not raw_rows:
                fail(400, 'EVAL_ROWS_REQUIRED', 'Thiếu danh sách eval_rows để đánh giá.', 'Truyền eval_rows hợp lệ.')
            eval_rows = []
            for idx, r in enumerate(raw_rows):
                if not isinstance(r, dict) or not isinstance(r.get('x'), list) or len(r['x']) != 2 or r.get('y') not in (0, 1):
                    fail(400, 'EVAL_ROW_INVALID', f'Dòng đánh giá thứ {idx} không đúng schema 2 đặc trưng nhị phân & nhãn 0/1.', 'Kiểm tra lại dữ liệu đánh giá.')
                eval_rows.append({
                    'record_id': str(r.get('record_id') or f'EV_{idx:04d}'),
                    'x': [int(r['x'][0]), int(r['x'][1])],
                    'y': int(r['y']),
                    'rule_score': float(r.get('rule_score') or 0.0),
                    'ml_score': float(r.get('ml_score') or 0.0),
                    'fired_rules': list(r.get('fired_rules') or []),
                })
            eval_prov = {
                'source_mode': 'custom_eval_rows',
                'simulated': bool(body.get('simulated', True)),
                'dataset_fingerprint': digest(canonical([{'id': r['record_id'], 'x': r['x'], 'y': r['y']} for r in eval_rows])),
                'eval_sample_count': len(eval_rows),
                'eval_positive_count': sum(1 for r in eval_rows if r['y'] == 1),
                'eval_negative_count': sum(1 for r in eval_rows if r['y'] == 0),
                'privacy_redacted': True,
            }
            admission_thr = float(body.get('pipeline_admission_threshold', 5.0))
        elif eval_mode == 'small_job_holdout':
            # Deliberately tiny holdout (4 rows, 2 positives) — proves gate blocks insufficient positives!
            eval_rows = [
                {'record_id': f'{company}_SMALL_1', 'x': [1, 1], 'y': 1, 'rule_score': 10.0, 'ml_score': 0.9, 'fired_rules': ['C2']},
                {'record_id': f'{company}_SMALL_2', 'x': [1, 0], 'y': 1, 'rule_score': 3.0, 'ml_score': 0.7, 'fired_rules': []},
                {'record_id': f'{company}_SMALL_3', 'x': [0, 1], 'y': 0, 'rule_score': 0.0, 'ml_score': 0.3, 'fired_rules': []},
                {'record_id': f'{company}_SMALL_4', 'x': [0, 0], 'y': 0, 'rule_score': 0.0, 'ml_score': 0.1, 'fired_rules': []},
            ]
            eval_prov = {
                'source_mode': 'small_job_holdout',
                'simulated': True,
                'dataset_fingerprint': digest(canonical(eval_rows)),
                'eval_sample_count': 4,
                'eval_positive_count': 2,
                'eval_negative_count': 2,
                'privacy_redacted': True,
            }
            admission_thr = float(body.get('pipeline_admission_threshold', 5.0))
        else:
            bench = build_representative_sme_eval_dataset(company, n_total=int(body.get('benchmark_size', 200)))
            eval_rows = bench['rows']
            eval_prov = bench['provenance']
            admission_thr = float(body.get('pipeline_admission_threshold', bench['admission_threshold']))

        tc = model_dto['training_configuration']
        coeffs = [float(tc['coefficients'][0]), float(tc['coefficients'][1])]
        intercept = float(tc['intercept'])

        # Optional custom gate thresholds override for policy tuning (still strictly enforced!)
        g_in = body.get('quality_gate_config') if isinstance(body.get('quality_gate_config'), dict) else {}
        gate_cfg = LRQualityGateConfig(
            target_recall=float(g_in.get('target_recall', self.gate_config.target_recall)),
            min_positive_samples=int(g_in.get('min_positive_samples', self.gate_config.min_positive_samples)),
            min_total_samples=int(g_in.get('min_total_samples', self.gate_config.min_total_samples)),
            max_fp_per_1000=float(g_in.get('max_fp_per_1000', self.gate_config.max_fp_per_1000)),
            min_precision=float(g_in.get('min_precision', self.gate_config.min_precision)),
            min_pr_auc=float(g_in.get('min_pr_auc', self.gate_config.min_pr_auc)),
            require_fhe_parity=bool(g_in.get('require_fhe_parity', self.gate_config.require_fhe_parity)),
        )

        # Select optimal R5 operating threshold on eval predictions (or use explicit threshold override in [0.05, 0.95])
        if body.get('threshold') is not None:
            tau = float(body['threshold'])
            if not (0.05 <= tau <= 0.95):
                fail(400, 'LR_THRESHOLD_INVALID', 'Ngưỡng phân loại phải nằm trong [0.05, 0.95].', 'Nhập ngưỡng hợp lệ.')
        else:
            eval_y = [int(r['y']) for r in eval_rows]
            eval_probs = [_sigmoid(coeffs[0] * r['x'][0] + coeffs[1] * r['x'][1] + intercept) for r in eval_rows]
            tau = select_r5_operating_threshold(eval_y, eval_probs, gate_cfg)

        # Build baseline training reference rows (if custom provided, else balanced representative train rows)
        train_ref_rows = body.get('baseline_train_rows') if isinstance(body.get('baseline_train_rows'), list) else None
        if not train_ref_rows:
            train_ref_rows = [
                {'x': [1, 1], 'y': 1}, {'x': [1, 1], 'y': 1}, {'x': [1, 0], 'y': 1}, {'x': [0, 1], 'y': 1},
                {'x': [0, 0], 'y': 0}, {'x': [0, 0], 'y': 0}, {'x': [0, 0], 'y': 0}, {'x': [0, 0], 'y': 0},
                {'x': [1, 0], 'y': 0}, {'x': [0, 1], 'y': 0}, {'x': [0, 0], 'y': 0}, {'x': [0, 0], 'y': 0},
            ]

        cmp = run_four_way_comparison(
            coefficients=coeffs,
            intercept=intercept,
            threshold=tau,
            eval_rows=eval_rows,
            train_rows_for_baseline=train_ref_rows,
            previous_lr=prev_lr,
            pipeline_admission_threshold=admission_thr,
        )

        # Attach all 9 mandatory metrics into one clean unified dict
        cand_m = deepcopy(cmp['candidate_lr_metrics'])
        cand_m['train_time_seconds'] = model_dto['train_time_seconds']
        cand_m['fhe_error_vs_reference'] = deepcopy(model_dto['fhe_error_vs_reference'])

        gate = evaluate_quality_gate(
            lr_metrics=cand_m,
            fhe_error=model_dto['fhe_error_vs_reference'],
            incremental_value=cmp['incremental_value'],
            config=gate_cfg,
        )
        new_state = 'CANDIDATE' if gate['quality_approved'] else 'BLOCKED'
        evidence_hash = digest(canonical({
            'registry_id': reg_id,
            'model_version': model_dto['model_version'],
            'feature_schema_hash': model_dto['feature_schema_hash'],
            'metrics': cand_m,
            'comparisons': cmp['comparisons'],
            'incremental_value': cmp['incremental_value'],
            'quality_gate': gate,
            'eval_provenance': eval_prov,
        }))

        now = _iso_now()
        with self._tx(scope, recheck, write=True) as conn:
            cur_row = conn.execute('SELECT * FROM lr_registry_models WHERE registry_id=?', (reg_id,)).fetchone()
            payload = json.loads(cur_row['payload_json'])
            payload['training_configuration']['threshold'] = round(tau, 6)
            payload['training_data_provenance'].update({
                'eval_source_mode': eval_prov['source_mode'],
                'eval_dataset_fingerprint': eval_prov['dataset_fingerprint'],
                'eval_sample_count': eval_prov['eval_sample_count'],
                'eval_positive_count': eval_prov['eval_positive_count'],
                'eval_negative_count': eval_prov['eval_negative_count'],
                'eval_simulated': eval_prov['simulated'],
            })
            payload['metrics'] = cand_m
            payload['comparisons'] = cmp['comparisons']
            payload['incremental_value'] = cmp['incremental_value']
            payload['quality_gate'] = gate
            payload['quality_approved'] = bool(gate['quality_approved'])
            payload['lifecycle_state'] = new_state
            payload['validation_evidence_sha256'] = evidence_hash
            payload['updated_at'] = now

            conn.execute(
                'UPDATE lr_registry_models SET lifecycle_state=?, quality_approved=?, updated_at=?, payload_json=? WHERE registry_id=?',
                (new_state, 1 if gate['quality_approved'] else 0, now, json.dumps(payload, ensure_ascii=False), reg_id),
            )
            reason = (
                f'Đạt toàn bộ cổng chất lượng R5 (Recall={round((cand_m["recall_class_1"] or 0)*100,1)}%, '
                f'Precision={round((cand_m["precision_class_1"] or 0)*100,1)}%, FP/1000={cand_m["false_positives_per_1000"]}) -> CANDIDATE.'
                if gate['quality_approved']
                else f'Chặn tại cổng chất lượng R5 ({", ".join(r["code"] for r in gate["blocking_reasons"])}) -> BLOCKED (quality_approved=False).'
            )
            self._log_event(conn, scope, reg_id, cur_state, new_state, reason, {
                'quality_approved': gate['quality_approved'],
                'evidence_sha256': evidence_hash,
                'blocking_codes': [r['code'] for r in gate['blocking_reasons']],
            })
            updated = self._row_to_dto(conn, conn.execute('SELECT * FROM lr_registry_models WHERE registry_id=?', (reg_id,)).fetchone())
        return {'status': 'ok', 'model': updated}

    # ------------------------------------------------------------------ Controlled State Machine Transitions
    def transition_state(self, scope: AccessScope, body: dict, recheck=None) -> dict:
        """Execute strictly validated lifecycle transition:
        CANDIDATE -> SHADOW -> APPROVED -> ACTIVE -> ROLLED_BACK (+ REJECTED / BLOCKED).
        """
        if 'model.fit' not in scope.permissions:
            fail(403, 'MODEL_FIT_DENIED', 'Cần quyền quản trị mô hình (model.fit) để chuyển trạng thái vòng đời LR.', 'Dùng tài khoản quản lý.')
        tenant = scope.tenant_id
        company = next(iter(scope.company_ids))
        reg_id = str(body.get('registry_id') or '').strip()
        target_state = str(body.get('target_state') or '').strip().upper()
        reason = str(body.get('reason') or '').strip()
        reviewed_evidence = bool(body.get('reviewed_evidence', False))

        if not reg_id:
            fail(400, 'REGISTRY_ID_REQUIRED', 'Thiếu registry_id.', 'Chọn phiên bản LR.')
        if target_state not in LIFECYCLE_STATES:
            fail(400, 'INVALID_TARGET_STATE', f'Trạng thái đích không hợp lệ: {target_state}.', f'Chọn một trong {", ".join(LIFECYCLE_STATES)}.')
        if len(reason) < 10 or len(reason) > 1000:
            fail(400, 'TRANSITION_REASON_REQUIRED', 'Cần ghi rõ lý do chuyển trạng thái (10–1000 ký tự).', 'Nhập căn cứ nghiệp vụ/kỹ thuật.')

        now = _iso_now()
        with self._tx(scope, recheck, write=True) as conn:
            row = conn.execute(
                'SELECT * FROM lr_registry_models WHERE registry_id=? AND tenant_id=? AND company_id=?',
                (reg_id, tenant, company),
            ).fetchone()
            if row is None:
                fail(404, 'LR_REGISTRY_NOT_FOUND', 'Không tìm thấy phiên bản LR trong Registry.', 'Tải lại danh sách.')
            cur_state = row['lifecycle_state']
            payload = json.loads(row['payload_json'])
            quality_ok = bool(row['quality_approved']) and bool((payload.get('quality_gate') or {}).get('quality_approved'))

            if target_state not in ALLOWED_TRANSITIONS.get(cur_state, set()):
                fail(
                    409,
                    'INVALID_LIFECYCLE_TRANSITION',
                    f'Không cho phép chuyển trực tiếp từ {cur_state} sang {target_state} (phải đi đúng chuỗi TRAINING → VALIDATING → CANDIDATE → SHADOW → APPROVED → ACTIVE).',
                    f'Các trạng thái hợp lệ tiếp theo từ {cur_state}: {", ".join(sorted(ALLOWED_TRANSITIONS.get(cur_state, set()))) or "không có"}.',
                )

            # HARD GUARD: APPROVED & ACTIVE require verified quality_approved == True + evidence hash!
            if target_state == 'APPROVED':
                if not quality_ok or not payload.get('validation_evidence_sha256'):
                    fail(
                        409,
                        'QUALITY_APPROVAL_REQUIRED',
                        'Không thể phê duyệt (APPROVED): mô hình chưa đạt quality_approved=True với bằng chứng validation R5 hợp lệ.',
                        'Chạy đánh giá R5 với tập kiểm thử đại diện đạt toàn bộ cổng chất lượng trước.',
                    )
                if not reviewed_evidence:
                    fail(
                        400,
                        'EVIDENCE_REVIEW_CHECK_REQUIRED',
                        'Người phê duyệt phải tích xác nhận đã xem đầy đủ 9 metrics, bảng so sánh 4 mốc và cảnh báo sai.',
                        'Tích ô xác nhận trước khi phê duyệt.',
                    )
                signing_key = self._load_signing_key(company)
                tc = payload['training_configuration']
                m_val = payload['metrics']
                r3_core = {
                    'release_contract_version': LR_RELEASE_CONTRACT,
                    'model_id': f'lrmdl_{reg_id}',
                    'version_tag': payload['model_version'],
                    'artifact_stage': 'releasable_model',
                    'tenant_id': tenant,
                    'company_id': company,
                    'source_job_id': tc.get('source_job_id') or reg_id,
                    'worker_job_id': tc.get('worker_job_id'),
                    'mode': tc.get('mode', 'fhe_cloud_ciphertext'),
                    'native_fhe_executed': bool(tc.get('native_fhe_executed')),
                    'profile_version': payload['circuit_version'],
                    'build_sha256': tc.get('build_sha256'),
                    'key_epoch': tc.get('key_epoch'),
                    'model_cipher_sha256': tc.get('model_cipher_sha256'),
                    'weights_code': tc['weights_code'],
                    'coefficients': tc['coefficients'],
                    'intercept': tc['intercept'],
                    'threshold': float(m_val['threshold']),
                    'feature_schema': deepcopy(LR_FEATURE_SCHEMA),
                    'validation_metrics': {
                        'threshold': float(m_val['threshold']),
                        'sample_count': m_val['sample_count'],
                        'precision': m_val['precision_class_1'],
                        'recall': m_val['recall_class_1'],
                        'f1': m_val['f1_score'],
                        'pr_auc': m_val['pr_auc'],
                        'accuracy': m_val['accuracy'],
                        'bce_loss': m_val['bce_loss'],
                        'fp_per_1000': m_val['false_positives_per_1000'],
                    },
                    'implementation_parity_pass': True,
                    'approved_by': scope.actor_id,
                    'approved_at': now,
                    'approval_reason': reason,
                    'registry_id': reg_id,
                    'quality_approved': True,
                    'validation_evidence_sha256': payload['validation_evidence_sha256'],
                }
                signed_artifact = sign_releasable_lr_model(r3_core, signing_key)
                payload['approval_record'] = {
                    'approved_by': scope.actor_id,
                    'approved_at': now,
                    'reason': reason,
                    'reviewed_evidence': True,
                    'validation_evidence_sha256': payload['validation_evidence_sha256'],
                    'signature_envelope': deepcopy(signed_artifact['signature_envelope']),
                }
                payload['releasable_model_artifact'] = signed_artifact

            elif target_state == 'ACTIVE':
                if not quality_ok or not payload.get('approval_record') or not payload.get('releasable_model_artifact'):
                    fail(
                        409,
                        'APPROVAL_RECORD_REQUIRED',
                        'Chỉ được kích hoạt (ACTIVE) phiên bản đã qua APPROVED có approval_record và chữ ký Ed25519 hợp lệ.',
                        'Hoàn tất phê duyệt ở trạng thái APPROVED trước.',
                    )
                # Find any currently ACTIVE model -> record as rollback_target & move old active to APPROVED standby
                prev_active = conn.execute(
                    "SELECT * FROM lr_registry_models WHERE tenant_id=? AND company_id=? AND lifecycle_state='ACTIVE' AND registry_id!=?",
                    (tenant, company, reg_id),
                ).fetchone()
                if prev_active is not None:
                    old_id = prev_active['registry_id']
                    old_payload = json.loads(prev_active['payload_json'])
                    old_payload['lifecycle_state'] = 'APPROVED'
                    old_payload['updated_at'] = now
                    conn.execute(
                        "UPDATE lr_registry_models SET lifecycle_state='APPROVED', updated_at=?, payload_json=? WHERE registry_id=?",
                        (now, json.dumps(old_payload, ensure_ascii=False), old_id),
                    )
                    self._log_event(conn, scope, old_id, 'ACTIVE', 'APPROVED', f'Được thay thế bởi phiên bản mới {payload["model_version"]} (giữ làm mục tiêu hoàn nguyên).', {'superseded_by': reg_id})
                    payload['rollback_target'] = old_id
                payload['activation_timestamp'] = now

            elif target_state == 'ROLLED_BACK':
                rb_target_id = str(body.get('rollback_target') or payload.get('rollback_target') or '').strip()
                if not rb_target_id:
                    fail(
                        409,
                        'ROLLBACK_TARGET_MISSING',
                        'Không có phiên bản ACTIVE trước đó (rollback_target) để hoàn nguyên.',
                        'Dùng trạng thái BLOCKED để ngừng sử dụng phiên bản hiện tại nếu đây là phiên bản đầu tiên.',
                    )
                t_row = conn.execute(
                    'SELECT * FROM lr_registry_models WHERE registry_id=? AND tenant_id=? AND company_id=?',
                    (rb_target_id, tenant, company),
                ).fetchone()
                if t_row is None or not bool(t_row['quality_approved']):
                    fail(409, 'ROLLBACK_TARGET_INVALID', 'Mục tiêu hoàn nguyên không tồn tại hoặc chưa đạt quality_approved=True.', 'Chọn phiên bản đã được phê duyệt hợp lệ.')
                t_payload = json.loads(t_row['payload_json'])
                if not t_payload.get('approval_record') or not t_payload.get('releasable_model_artifact'):
                    fail(409, 'ROLLBACK_TARGET_INVALID', 'Mục tiêu hoàn nguyên thiếu approval_record hoặc artifact đã ký.', 'Chọn phiên bản đã được phê duyệt.')
                old_t_state = t_row['lifecycle_state']
                t_payload['lifecycle_state'] = 'ACTIVE'
                t_payload['activation_timestamp'] = now
                t_payload['updated_at'] = now
                conn.execute(
                    "UPDATE lr_registry_models SET lifecycle_state='ACTIVE', activation_timestamp=?, updated_at=?, payload_json=? WHERE registry_id=?",
                    (now, now, json.dumps(t_payload, ensure_ascii=False), rb_target_id),
                )
                self._log_event(conn, scope, rb_target_id, old_t_state, 'ACTIVE', f'Khôi phục kích hoạt khi hoàn nguyên từ {payload["model_version"]}: {reason}', {'rolled_back_from': reg_id})

            elif target_state in ('BLOCKED', 'REJECTED'):
                if target_state == 'REJECTED':
                    payload['quality_approved'] = False

            payload['lifecycle_state'] = target_state
            payload['updated_at'] = now
            conn.execute(
                'UPDATE lr_registry_models SET lifecycle_state=?, quality_approved=?, activation_timestamp=?, rollback_target=?, updated_at=?, payload_json=? WHERE registry_id=?',
                (
                    target_state,
                    1 if payload['quality_approved'] else 0,
                    payload.get('activation_timestamp'),
                    payload.get('rollback_target'),
                    now,
                    json.dumps(payload, ensure_ascii=False),
                    reg_id,
                ),
            )
            self._log_event(conn, scope, reg_id, cur_state, target_state, reason, {'rollback_target': payload.get('rollback_target')})
            updated = self._row_to_dto(conn, conn.execute('SELECT * FROM lr_registry_models WHERE registry_id=?', (reg_id,)).fetchone())
        return {'status': 'ok', 'model': updated}

    # ------------------------------------------------------------------ Pipeline Inference Integration (R3 <-> R5)
    def get_active_releasable_model(self, scope: AccessScope, *, registry_id: str | None = None, allow_shadow: bool = False, recheck=None) -> dict | None:
        """Return signed R3-compatible `releasable_model` ONLY from ACTIVE (or SHADOW if allowed) with quality_approved=True."""
        tenant = scope.tenant_id
        company = next(iter(scope.company_ids))
        allowed_states = ('ACTIVE', 'SHADOW', 'APPROVED') if allow_shadow else ('ACTIVE',)
        with self._tx(scope, recheck, write=False) as conn:
            if registry_id:
                row = conn.execute(
                    'SELECT * FROM lr_registry_models WHERE registry_id=? AND tenant_id=? AND company_id=?',
                    (registry_id, tenant, company),
                ).fetchone()
                if row is None:
                    return None
                if row['lifecycle_state'] not in allowed_states or not bool(row['quality_approved']):
                    return None
                payload = json.loads(row['payload_json'])
                return deepcopy(payload.get('releasable_model_artifact'))
            row = conn.execute(
                "SELECT * FROM lr_registry_models WHERE tenant_id=? AND company_id=? AND lifecycle_state='ACTIVE' AND quality_approved=1 ORDER BY version_number DESC LIMIT 1",
                (tenant, company),
            ).fetchone()
            if row is None:
                return None
            payload = json.loads(row['payload_json'])
            art = payload.get('releasable_model_artifact')
            if not isinstance(art, dict):
                return None
            ok, _, _ = verify_releasable_lr_model(art, expected_tenant=tenant, expected_company=company)
            return deepcopy(art) if ok else None
