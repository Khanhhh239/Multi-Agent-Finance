"""From scores to what an accountant opens: budgeted alerts, entity cases, calibrated confidence, Vietnamese reasons.

* Alert budget: at most B rows per company-week (default 3), never below a conformal floor.
* Conformal p-values against a calibration period + Benjamini-Hochberg: controls how many alerts are
  merely 'unusual but normal for this firm' (Bates et al., Annals of Statistics 2023). The guarantee is on
  statistical outlier-ness, NOT on fraud precision; the calibration period may itself contain unlabelled fraud.
* Cases: alerted rows are merged per (entity, week); one case = one item in the queue.
* Confidence: isotonic map from fused score to observed hit rate on the validation period (labels from
  simulation only; on real data it is replaced by reviewer feedback).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .metrics import entity_key, tie_break, weekly_alerts

ENTITY_REASONS = {
    "price_logratio": "Đơn giá hóa đơn cao hơn {pct:.0%} so với trung vị các lần mua gần nhất của chính nhà cung cấp",
    "price_logz": "Đơn giá lệch xa biến động thường lệ của nhà cung cấp này",
    "price_shift3": "Ba lần mua gần nhất cùng nhà cung cấp có đơn giá tăng {pct:.0%} so với lịch sử",
    "p_logratio": "Khoản chi lương cao hơn {pct:.0%} so với mức thường lệ của chính nhân viên (ngoài tháng thưởng)",
    "p_logratio_bonus": "Khoản chi lương trong tháng thưởng cao bất thường so với mức thường lệ của nhân viên",
    "cu_logratio": "Số tiền cao bất thường so với loại nghiệp vụ người lập thường làm",
    "near_dup_other_invoice_30d": "Có khoản thanh toán số tiền gần giống (sai lệch dưới 3%) cho cùng nhà cung cấp trong 30 ngày nhưng khác số hóa đơn",
    "near_dup_30d": "Có khoản thanh toán số tiền gần giống cho cùng nhà cung cấp trong 30 ngày",
    "creator_cash_near_selflimit_30d": "Người chi tiền mặt lặp lại nhiều khoản sát hạn mức tự duyệt trong 30 ngày",
    "amount_selflimit_ratio": "Khoản chi tiền mặt tự duyệt ở mức sát hạn mức tự duyệt",
    "creator_unsupported_selfcash_30d": "Người lập tự duyệt chi tiền mặt thiếu chứng từ nhiều lần trong 30 ngày",
    "v_days_dormant_amount": "Nhà cung cấp không phát sinh từ 180 ngày trước, nay có khoản thanh toán lớn",
}
ACTIONS = {
    "cao_nhat": "Dừng chi/kiểm tra ngay trong 24 giờ: đối chiếu hợp đồng, hóa đơn, người nhận tiền.",
    "cao": "Kiểm tra trong 48 giờ: yêu cầu chứng từ gốc, hỏi người lập và người duyệt.",
    "trung_binh": "Rà soát trong tuần: đối chiếu hóa đơn điện tử và sao kê, ghi kết luận.",
}


def conformal_pvalues(calibration: np.ndarray, scores: np.ndarray) -> np.ndarray:
    cal = np.sort(np.asarray(calibration, dtype=float))
    n = len(cal)
    ge = n - np.searchsorted(cal, scores, side="left")
    return (1.0 + ge) / (n + 1.0)


def benjamini_hochberg(p: np.ndarray, q: float) -> np.ndarray:
    m = len(p)
    order = np.argsort(p)
    passed = p[order] <= q * (np.arange(1, m + 1) / m)
    keep = np.zeros(m, dtype=bool)
    if passed.any():
        keep[order[: np.max(np.where(passed)[0]) + 1]] = True
    return keep


def select_alerts(df: pd.DataFrame, score: np.ndarray, per_week=3, calibration: np.ndarray | None = None, q: float | None = None):
    """Top `per_week` per company-week; if `calibration` and `q` are given, also require BH significance."""
    s = np.asarray(score, dtype=float) + tie_break(len(df), 1)
    alerts = weekly_alerts(df, s, per_week)
    if calibration is not None and q is not None:
        alerts &= benjamini_hochberg(conformal_pvalues(calibration, s), q)
    return alerts


class Confidence:
    """Isotonic map score -> observed hit rate (entity-week level) fitted on a labelled validation slice."""

    def fit(self, score: np.ndarray, y: np.ndarray):
        from sklearn.isotonic import IsotonicRegression
        self.iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(score, y)
        return self

    def __call__(self, score):
        return self.iso.predict(score)


def priority(rank_fraction: float, hard: bool) -> str:
    if hard or rank_fraction <= .1:
        return "cao_nhat"
    return "cao" if rank_fraction <= .5 else "trung_binh"


def reasons_for_row(row: pd.Series, entity_parts: dict[str, float], rule_weights: dict[str, float] | None = None, top=2) -> list[str]:
    """Plain-Vietnamese reasons, strongest first. Rule reasons are ordered by their learned weight so a weak,
    noisy rule (round amounts, late hour) never headlines a case that also carries a strong one."""
    out = []
    ids = [x for x in str(row.get("rule_ids", "") or "").split("|") if x]
    if rule_weights and ids:
        from sme_fraud.rules import RULE_NAMES
        ranked_ids = sorted(ids, key=lambda r: -rule_weights.get(r, 0.0))
        out += [RULE_NAMES.get(r, r) for r in ranked_ids[:top] if rule_weights.get(r, 0.0) > 0]
    elif isinstance(row.get("explanation_vi"), str) and row["explanation_vi"]:
        out.append(row["explanation_vi"])
    ranked = sorted(entity_parts.items(), key=lambda kv: -kv[1])
    for name, value in ranked[:top]:
        if value < 4.0 or name not in ENTITY_REASONS:
            continue
        pct = float(np.expm1(max(0.0, row.get(EntityLookup.get(name, name), 0.0)))) if "logratio" in name or "shift" in name else 0.0
        out.append(ENTITY_REASONS[name].format(pct=pct))
    return out


EntityLookup = {"p_logratio_bonus": "p_logratio", "v_days_dormant_amount": "v_logratio"}


def build_cases(df: pd.DataFrame, alerts: np.ndarray, score: np.ndarray, parts: dict[str, np.ndarray] | None = None,
                confidence: Confidence | None = None) -> pd.DataFrame:
    """One row per (company, entity, week): the queue the accountant works through."""
    key = entity_key(df)
    frame = df.loc[alerts, ["transaction_id", "company_id", "week", "t", "txn_type", "amount_vnd"]].copy()
    frame["entity"] = key[alerts].values
    frame["score"] = np.asarray(score)[alerts]
    frame["explanation_vi"] = df.loc[alerts, "explanation_vi"].values if "explanation_vi" in df else ""
    if parts:
        names = list(parts)
        mat = np.vstack([parts[n][alerts] for n in names]).T
        frame["top_signal"] = [names[i] if mat[k, i] > 0 else "" for k, i in enumerate(mat.argmax(axis=1))]
    g = frame.groupby(["company_id", "entity", "week"], sort=False)
    cases = g.agg(case_score=("score", "max"), opened_at=("t", "min"), rows=("transaction_id", "size"),
                  transaction_ids=("transaction_id", list), total_amount_vnd=("amount_vnd", lambda s: int(pd.to_numeric(s).sum())),
                  reason=("explanation_vi", lambda s: next((x for x in s if isinstance(x, str) and x), "")),
                  top_signal=("top_signal", "first") if parts else ("score", "size")).reset_index()
    cases = cases.sort_values("case_score", ascending=False, kind="stable").reset_index(drop=True)
    cases["rank_fraction"] = (cases.index + 1) / max(1, len(cases))
    cases["priority"] = [priority(f, False) for f in cases["rank_fraction"]]
    cases["action_vi"] = cases["priority"].map(ACTIONS)
    if confidence is not None:
        cases["estimated_hit_rate"] = confidence(cases["case_score"].to_numpy())
    cases.insert(0, "case_id", [f"AG2_{i+1:06d}" for i in range(len(cases))])
    return cases


def select_mixed(df: pd.DataFrame, exploit: np.ndarray, explore: np.ndarray, exploit_slots=2, explore_slots=1) -> np.ndarray:
    """Per company-week: top `exploit_slots` by the calibrated stack, then `explore_slots` more by the label-free
    novelty channel (rules + entity deviations ranked without learned weights).

    Why: a stack trained on past schemes learns to ignore detectors that never helped before; a scheme nobody has
    seen is then invisible. Reserving slots for the label-free channel keeps a door open for new schemes.
    """
    a = np.asarray(exploit, dtype=float) + tie_break(len(df), 3)
    first = weekly_alerts(df, a, exploit_slots)
    b = np.asarray(explore, dtype=float) + tie_break(len(df), 4)
    b = np.where(first, -np.inf, b)
    second = weekly_alerts(df, b, explore_slots) & ~first
    return first | second
