"""
survival_utils.py — thư viện dùng chung cho notebook 11 (Đ2) và 12 (Đ15).

Chứa đúng ba thứ, và không chứa gì khác:
  1. Bộ dựng snapshot trên LƯỚI CUTOFF MỞ RỘNG (Đ1/Đ2) — bản sao logic `build_snapshot`
     của `08_discrete_time_survival.ipynb`, mở rộng thêm các cột mà bộ feature LightGBM Tầng 5 cần
     (`payment_terms_imputed`, `issue_month`, `issue_dayofweek`, `due_month`, `amount_log1p`).
  2. Hạ tầng survival (person-period, hazard → S(t), feature survival) — cũng lấy từ 08.
  3. Hàm mất mát pinball CÓ XỬ LÝ CENSORING + các hàm đo lường dùng chung.

Lý do tách file: notebook 11 và 12 phải dựng CÙNG một snapshot. Nếu chép code hai lần,
hai notebook sẽ trôi khỏi nhau và mọi so sánh giữa chúng mất hiệu lực.

Nguồn logic gốc: reference_notebooks/08_discrete_time_survival.ipynb (D45–D53).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent.parent
PROC = BASE / "data" / "processed"
MODEL_DIR = BASE / "models"

# ── Hằng số (giữ nguyên giá trị của 08_discrete_time_survival để hai notebook so sánh được) ──
SEED = 42
BIN_DAYS = 7
MAX_BINS = 26
GUARD_DAYS = 7                                # Đ1: dải bảo vệ 7 ngày thay vì 91
MIN_HISTORY = 250
HALF_LIFE_WEEKS = 8                           # D53
POST_TRAIN_END = pd.Timestamp("2020-04-10")   # D52
AGING_ORDER = {"not_due": 0, "1_30": 1, "31_60": 2, "61_90": 3, "90_plus": 4}
WINDOW_ORDER = ["train_pre", "test_legacy", "train_post", "test_post"]

# ── Bộ feature ────────────────────────────────────────────────────────────────
# Bộ feature Tầng 5 — giống hệt `03_lightgbm_payment_quantiles.ipynb` cell 7 (31 feature).
FEATURE_COLS_LGBM = [
    "days_until_due_at_T", "days_past_due_at_T", "is_overdue_at_T", "observed_age_days",
    "aging_bucket_ord", "amount_log1p", "amount_percentile_hist",
    "amount_vs_customer_median_hist", "payment_terms", "payment_terms_imputed",
    "cutoff_month", "cutoff_quarter", "issue_month", "issue_dayofweek", "due_month",
    "customer_invoice_count_hist", "customer_has_history", "customer_history_sufficient",
    "customer_median_delay_hist", "customer_recency_delay_median_hist",
    "customer_mean_delay_hist", "customer_median_life_hist",
    "customer_recency_life_median_hist", "customer_last_paid_age_days",
    "term_invoice_count_hist", "term_has_history", "term_median_delay_hist",
    "term_mean_delay_hist", "global_median_delay_hist", "global_mean_delay_hist",
    "pred_b1_remaining_days",
]

# Bộ feature Tầng 5 KHÔNG có feature lịch (D53) — dùng cho biến thể chống học quy tắc theo tháng.
FEATURE_COLS_NOCAL = [c for c in FEATURE_COLS_LGBM
                      if c not in ("cutoff_month", "cutoff_quarter", "issue_month",
                                   "issue_dayofweek", "due_month")]

# Bộ feature hazard — giống hệt `08_discrete_time_survival.ipynb` cell 12.
HAZARD_FEATURES = [
    "bin_index", "days_past_due_at_bin", "age_at_bin", "days_until_due_at_bin",
    "is_overdue_at_T", "aging_bucket_ord", "amount_log1p", "amount_percentile_hist",
    "amount_vs_customer_median_hist", "payment_terms",
    "customer_invoice_count_hist", "customer_has_history", "customer_history_sufficient",
    "customer_median_delay_hist", "customer_recency_delay_median_hist",
    "customer_mean_delay_hist", "customer_median_life_hist",
    "customer_recency_life_median_hist", "customer_last_paid_age_days",
    "term_invoice_count_hist", "term_median_delay_hist", "term_mean_delay_hist",
    "global_median_delay_hist", "global_mean_delay_hist",
]

SURV_BOOST_FEATS = ["S_7", "S_30", "S_60", "S_90", "rmst_91d", "median_remaining_days"]


# ══════════════════════════════════════════════════════════════════════════════
# 1. Dựng snapshot trên lưới cutoff mở rộng
# ══════════════════════════════════════════════════════════════════════════════
def load_pools():
    """Trả về (clean, pool, closed, DATA_END, old_summary)."""
    clean = pd.read_csv(PROC / "invoices_ar_clean.csv",
                        parse_dates=["issue_date", "due_date", "paid_date"], low_memory=False)
    old_summary = pd.read_csv(PROC / "rolling_snapshot_summary.csv", parse_dates=["cutoff_date"])
    data_end = clean["paid_date"].max()

    pool = clean[(clean["amount"] > 0) & clean["issue_date"].notna() & clean["due_date"].notna()
                 & clean["payment_terms"].notna() & (clean["payment_terms"] > 0)
                 & (clean["payment_terms_invalid_after_fallback"] == 0)].copy()
    closed = pool[(pool["is_open"] == 0) & pool["paid_date"].notna()
                  & (pool["invoice_life_days"] >= 0) & (pool["due_before_issue"] == 0)].copy()
    closed["delay_days"] = (closed["paid_date"] - closed["due_date"]).dt.days
    return clean, pool, closed, data_end, old_summary


def build_cutoff_plan(old_summary, data_end):
    """Lưới 4 cửa sổ: train_pre · test_legacy (lưới cũ) + train_post · test_post (lưới mở rộng)."""
    old_last = old_summary["cutoff_date"].max()
    old_cutoffs = old_summary[["time_split", "cutoff_date"]].drop_duplicates()
    new_cutoffs = pd.date_range(old_last + pd.Timedelta(days=7),
                                data_end - pd.Timedelta(days=GUARD_DAYS), freq="W-FRI")
    return pd.concat([
        old_cutoffs.assign(window=np.where(old_cutoffs["time_split"] == "test",
                                           "test_legacy", "train_pre")),
        pd.DataFrame({"time_split": "post_shock", "cutoff_date": new_cutoffs,
                      "window": np.where(new_cutoffs <= POST_TRAIN_END, "train_post", "test_post")}),
    ], ignore_index=True).sort_values("cutoff_date").reset_index(drop=True)


def build_snapshot(T, window, pool, closed, data_end):
    """Snapshot tại T gồm MỌI hoá đơn đang mở tại T, kèm cờ censoring và feature as-of T."""
    hist = closed[closed["paid_date"] <= T]
    if len(hist) < MIN_HISTORY:
        return None
    at_risk = pool[(pool["issue_date"] <= T) &
                   ((pool["paid_date"] > T) | (pool["is_open"] == 1))].copy()
    if at_risk.empty:
        return None

    cust = hist.groupby("customer_id").agg(
        customer_invoice_count_hist=("invoice_id", "count"),
        customer_median_delay_hist=("delay_days", "median"),
        customer_mean_delay_hist=("delay_days", "mean"),
        customer_median_life_hist=("invoice_life_days", "median"),
        customer_median_amount_hist=("amount", "median"),
        customer_last_paid_date=("paid_date", "max"))
    rec = (hist.sort_values("paid_date").groupby("customer_id").tail(5).groupby("customer_id")
           .agg(customer_recency_delay_median_hist=("delay_days", "median"),
                customer_recency_life_median_hist=("invoice_life_days", "median")))
    term = hist.groupby("payment_terms").agg(
        term_invoice_count_hist=("invoice_id", "count"),
        term_median_delay_hist=("delay_days", "median"),
        term_mean_delay_hist=("delay_days", "mean"))
    g = {"global_median_delay_hist": float(hist["delay_days"].median()),
         "global_mean_delay_hist": float(hist["delay_days"].mean()),
         "global_median_life_hist": float(hist["invoice_life_days"].median())}
    amount_sorted = np.sort(hist["amount"].to_numpy(float))

    f = (at_risk.merge(cust, on="customer_id", how="left")
         .merge(rec, on="customer_id", how="left")
         .merge(term, on="payment_terms", how="left"))
    for k, v in g.items():
        f[k] = v
    f["customer_invoice_count_hist"] = f["customer_invoice_count_hist"].fillna(0)
    f["term_invoice_count_hist"] = f["term_invoice_count_hist"].fillna(0)
    f["term_median_delay_hist"] = f["term_median_delay_hist"].fillna(g["global_median_delay_hist"])
    f["term_mean_delay_hist"] = f["term_mean_delay_hist"].fillna(g["global_mean_delay_hist"])
    f["customer_median_delay_hist"] = f["customer_median_delay_hist"].fillna(f["term_median_delay_hist"])
    f["customer_mean_delay_hist"] = f["customer_mean_delay_hist"].fillna(f["term_mean_delay_hist"])
    f["customer_median_life_hist"] = f["customer_median_life_hist"].fillna(g["global_median_life_hist"])
    f["customer_recency_delay_median_hist"] = f["customer_recency_delay_median_hist"].fillna(
        f["customer_median_delay_hist"])
    f["customer_recency_life_median_hist"] = f["customer_recency_life_median_hist"].fillna(
        f["customer_median_life_hist"])
    f["customer_median_amount_hist"] = f["customer_median_amount_hist"].fillna(float(hist["amount"].median()))
    f["customer_has_history"] = (f["customer_invoice_count_hist"] > 0).astype(int)
    f["customer_history_sufficient"] = (f["customer_invoice_count_hist"] >= 3).astype(int)
    f["term_has_history"] = (f["term_invoice_count_hist"] > 0).astype(int)
    f["customer_last_paid_age_days"] = (T - f["customer_last_paid_date"]).dt.days

    f["cutoff_date"] = T
    f["window"] = window
    f["cutoff_month"] = T.month
    f["cutoff_quarter"] = T.quarter
    f["observed_age_days"] = (T - f["issue_date"]).dt.days.clip(lower=0)
    f["days_until_due_at_T"] = (f["due_date"] - T).dt.days
    f["days_past_due_at_T"] = (-(f["due_date"] - T).dt.days).clip(lower=0)
    f["is_overdue_at_T"] = (f["days_past_due_at_T"] > 0).astype(int)
    f["aging_bucket_at_T"] = pd.cut(f["days_past_due_at_T"], bins=[-1, 0, 30, 60, 90, np.inf],
                                    labels=["not_due", "1_30", "31_60", "61_90", "90_plus"]).astype(str)
    f["aging_bucket_ord"] = f["aging_bucket_at_T"].map(AGING_ORDER).fillna(0).astype(int)
    f["amount_percentile_hist"] = np.searchsorted(amount_sorted, f["amount"].to_numpy(float),
                                                  side="right") / max(len(amount_sorted), 1)
    f["amount_vs_customer_median_hist"] = f["amount"] / f["customer_median_amount_hist"].replace(0, np.nan)
    f["pred_b1_remaining_days"] = np.maximum(1.0, f["days_until_due_at_T"] + f["customer_median_delay_hist"])

    f["event"] = np.where(f["paid_date"].notna() & (f["paid_date"] > T), 1, 0)
    f["duration_days"] = np.where(f["event"] == 1, (f["paid_date"] - T).dt.days, (data_end - T).days)
    f["duration_days"] = f["duration_days"].clip(lower=1)
    f["followup_days"] = (data_end - T).days
    return f


def build_extended_snapshot(verbose=True):
    """Dựng toàn bộ snapshot 4 cửa sổ. Trả về (snap, cutoff_plan, data_end, clean)."""
    clean, pool, closed, data_end, old_summary = load_pools()
    plan = build_cutoff_plan(old_summary, data_end)
    frames = [s for s in (build_snapshot(T, w, pool, closed, data_end)
                          for w, T in plan[["window", "cutoff_date"]].itertuples(index=False))
              if s is not None]
    snap = pd.concat(frames, ignore_index=True)

    cap = MAX_BINS * BIN_DAYS
    snap.loc[(snap["duration_days"] > cap) & (snap["event"] == 1), "event"] = 0
    snap["duration_days"] = snap["duration_days"].clip(upper=cap)

    if verbose:
        print(f"Snapshot mở rộng: {len(snap):,} dòng · {snap['cutoff_date'].nunique()} cutoff")
        print(snap.groupby("window").agg(
            dong=("event", "size"), cutoff=("cutoff_date", "nunique"),
            ty_le_censored=("event", lambda s: 1 - s.mean()),
            du_no_musd=("amount", lambda s: s.sum() / 1e6)).reindex(WINDOW_ORDER).to_string())
    return snap, plan, data_end, clean


# ══════════════════════════════════════════════════════════════════════════════
# 2. Hạ tầng survival (person-period → hazard → S(t) → feature)
# ══════════════════════════════════════════════════════════════════════════════
def expand_person_period(frame, bin_days=BIN_DAYS, max_bins=MAX_BINS):
    n_bins = np.clip(np.ceil(frame["duration_days"].to_numpy(float) / bin_days).astype(int), 1, max_bins)
    idx = np.repeat(np.arange(len(frame)), n_bins)
    bin_no = np.concatenate([np.arange(1, k + 1) for k in n_bins])
    out = frame.iloc[idx].reset_index(drop=True)
    out["bin_index"] = bin_no
    out["is_last_bin"] = (bin_no == np.repeat(n_bins, n_bins)).astype(int)
    out["hazard_event"] = (out["is_last_bin"] & (out["event"] == 1)).astype(int)
    out["days_past_due_at_bin"] = out["days_past_due_at_T"] + bin_days * (out["bin_index"] - 1)
    out["age_at_bin"] = out["observed_age_days"] + bin_days * (out["bin_index"] - 1)
    out["days_until_due_at_bin"] = out["days_until_due_at_T"] - bin_days * (out["bin_index"] - 1)
    return out


def survival_matrix(frame, model, max_bins=MAX_BINS):
    """Ma trận S(t) — dòng = hoá đơn-cutoff, cột = bin tuần."""
    n = len(frame)
    haz = np.empty((n, max_bins))
    b = frame.copy()
    for j in range(1, max_bins + 1):
        b["bin_index"] = j
        b["days_past_due_at_bin"] = frame["days_past_due_at_T"].to_numpy() + BIN_DAYS * (j - 1)
        b["age_at_bin"] = frame["observed_age_days"].to_numpy() + BIN_DAYS * (j - 1)
        b["days_until_due_at_bin"] = frame["days_until_due_at_T"].to_numpy() - BIN_DAYS * (j - 1)
        haz[:, j - 1] = model.predict_proba(b[HAZARD_FEATURES].to_numpy(float))[:, 1]
    return np.cumprod(1.0 - haz, axis=1)


def survival_features(S, prefix="", horizons=(7, 14, 30, 60, 90), bin_days=BIN_DAYS):
    out = {}
    for h in horizons:
        j = min(int(np.ceil(h / bin_days)), S.shape[1])
        out[f"{prefix}S_{h}"] = S[:, j - 1]
        out[f"{prefix}prob_paid_{h}d"] = 1.0 - S[:, j - 1]
    below = S < 0.5
    first = np.where(below.any(axis=1), below.argmax(axis=1) + 1, S.shape[1] + 1)
    med = np.empty(len(S))
    for i, j in enumerate(first):
        if j > S.shape[1]:
            med[i] = S.shape[1] * bin_days
            continue
        s_prev = 1.0 if j == 1 else S[i, j - 2]
        s_cur = S[i, j - 1]
        frac = 0.5 if s_prev == s_cur else (s_prev - 0.5) / (s_prev - s_cur)
        med[i] = (j - 1) * bin_days + frac * bin_days
    out[f"{prefix}median_remaining_days"] = np.maximum(med, 1.0)
    out[f"{prefix}rmst_91d"] = S[:, :int(91 / bin_days)].sum(axis=1) * bin_days
    return out


def recency_weights(cutoffs, ref, half_life_weeks=HALF_LIFE_WEEKS):
    """Trọng số mũ theo độ mới (D53): w = 0.5 ** (tuần cách `ref` / nửa đời sống)."""
    weeks = (pd.Timestamp(ref) - pd.to_datetime(cutoffs)).dt.days / 7.0
    return np.power(0.5, weeks / half_life_weeks)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Pinball có xử lý censoring (biến thể M3 — xem notebook 11 §4)
# ══════════════════════════════════════════════════════════════════════════════
def censored_pinball_objective(alpha, is_censored):
    """
    Objective LightGBM cho quantile hồi quy khi một phần quan sát bị RIGHT-CENSORED.

    Quan sát không bị cắt cụt (biết y):      gradient pinball chuẩn.
    Quan sát bị cắt cụt (chỉ biết y >= c):
        · nếu pred <  c  → chắc chắn đang dự báo THIẾU → gradient = -alpha (như y > pred)
        · nếu pred >= c  → không có thông tin (y có thể lớn hoặc nhỏ hơn pred) → gradient = 0

    Đây là dạng "lower-bound pinball": chỉ dùng phần thông tin thật sự quan sát được, không
    gán nhãn giả cho quan sát bị cắt cụt. Hess = 1 (giống objective quantile nội bộ của LightGBM).

    Lưu ý kỹ thuật: với objective tự viết, LightGBM KHÔNG tự nhân trọng số mẫu vào gradient —
    nó truyền `weight` vào hàm và để hàm tự xử lý. Vì vậy phải nhân tay ở đây, nếu không thì
    `sample_weight` bị bỏ qua im lặng.

    Hạn chế phải khai báo: objective nội bộ `quantile` của LightGBM có thêm bước làm mới giá trị
    lá (renew tree output) bằng quantile của residual trong lá; objective tự viết không có bước
    đó nên hội tụ chậm hơn và cần `init_score`. Xem §4b của notebook 11 để biết bảng độ nhạy
    theo số cây.
    """
    cens = np.asarray(is_censored, dtype=bool)

    def _obj(y_true, y_pred, weight=None):
        resid = y_true - y_pred                      # với dòng censored: y_true = mốc theo dõi c
        grad = np.where(resid > 0, -alpha, 1.0 - alpha)
        grad = np.where(cens & (resid <= 0), 0.0, grad)   # censored & pred >= c → không phạt
        hess = np.ones_like(grad)
        if weight is not None:
            grad, hess = grad * weight, hess * weight
        return grad, hess

    return _obj


def ipcw_weights(frame, target_col="duration_days", cap=0.05):
    """
    Trọng số IPCW (inverse probability of censoring weighting).

    Ở đây censoring là HÀNH CHÍNH: mỗi dòng bị cắt cụt tại `followup_days = DATA_END − T`, biết
    trước theo cutoff và không phụ thuộc hành vi khách hàng. Vì vậy `G(t) = P(C > t)` ước lượng
    được bằng phân phối thực nghiệm của `followup_days`.

    Dòng đã có kết cục nhận trọng số `1/G(y)` (dòng trả càng muộn càng hiếm được quan sát → càng
    nặng); dòng bị cắt cụt nhận 0. `cap` chặn dưới G để trọng số không nổ.
    """
    c = np.sort(frame["followup_days"].to_numpy(float))
    y = frame[target_col].to_numpy(float)
    ev = frame["event"].to_numpy(int)
    G = np.maximum(1.0 - np.searchsorted(c, y, side="right") / len(c), cap)
    return np.where(ev == 1, 1.0 / G, 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# 4. Đo lường dùng chung
# ══════════════════════════════════════════════════════════════════════════════
def pinball(y, pred, alpha):
    r = np.asarray(y, float) - np.asarray(pred, float)
    return float(np.where(r >= 0, alpha * r, (alpha - 1) * r).mean())


def prob_paid_from_quantiles(q10, q50, q90, horizon):
    """
    P(remaining_days <= H) suy ra trực tiếp từ 3 quantile của chính model, bằng nội suy
    tuyến tính hàm phân phối qua 3 điểm (q10, 0.10) · (q50, 0.50) · (q90, 0.90).

    Vì sao không dùng "pool residual" như 08_discrete_time_survival: pool residual đến từ tập calibration
    của MODEL CŨ, nên nếu dùng lại cho model mới thì phần chênh lệch đo được lẫn cả hiệu ứng
    calibration cũ. Nội suy quantile chỉ dùng đầu ra của chính model → mọi biến thể được đo
    bằng cùng một thủ tục.
    """
    q10, q50, q90 = (np.asarray(x, float) for x in (q10, q50, q90))
    xs = np.column_stack([np.zeros_like(q10), q10, q50, q90])
    xs = np.maximum.accumulate(xs, axis=1)                     # đảm bảo không cắt nhau
    ys = np.array([0.0, 0.10, 0.50, 0.90])
    out = np.empty(len(q10))
    for i in range(len(q10)):
        out[i] = np.interp(horizon, xs[i], ys, left=0.0, right=0.90)
        if horizon > xs[i, 3]:                                  # ngoại suy đuôi phải dạng mũ
            out[i] = 1.0 - 0.10 * np.exp(-(horizon - xs[i, 3]) / max(xs[i, 3] - xs[i, 1], 1.0))
    return np.clip(out, 0.0, 1.0)


def money_check(frame, prob_cols, horizons=(7, 14, 30), window_col="window"):
    """
    Kiểm chứng bằng tiền (D49): trong H ngày kể từ T, thực tế thu được bao nhiêu % giá trị AR,
    và mỗi model dự báo bao nhiêu. Chỉ tính trên cutoff đã theo dõi đủ H ngày → không bị
    thiên lệch bởi censoring.

    `prob_cols`: dict {tên model: hàm(frame, H) -> mảng xác suất trả trong H ngày}.
    """
    rows = []
    for window, part in frame.groupby(window_col):
        for H in horizons:
            elig = part[part["followup_days"] >= H]
            if elig.empty:
                continue
            amt = elig["amount"].to_numpy(float)
            actual = float((amt * ((elig["event"] == 1) & (elig["duration_days"] <= H))).sum() / amt.sum())
            row = {"window": window, "horizon_days": H, "cutoffs": elig["cutoff_date"].nunique(),
                   "n": len(elig), "amount_musd": amt.sum() / 1e6, "thuc_te": actual}
            for name, fn in prob_cols.items():
                p = np.asarray(fn(elig, H), float)
                row[name] = float((amt * p).sum() / amt.sum())
                row[f"lech_{name}"] = row[name] - actual
            rows.append(row)
    return pd.DataFrame(rows)


def mae_by_cutoff(frame, y_col, pred_col):
    """MAE tổng hợp theo mean-of-cutoffs (Đ9) — mỗi cutoff một phiếu bầu, không phải mỗi dòng."""
    ae = np.abs(np.asarray(frame[y_col], float) - np.asarray(frame[pred_col], float))
    return float(pd.Series(ae).groupby(frame["cutoff_date"].to_numpy()).mean().mean())
