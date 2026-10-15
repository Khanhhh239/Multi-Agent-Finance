"""T1 — thời điểm thanh toán từng hoá đơn (phân phối theo tuần, 13 tuần) + T2 cure (xác suất không bao giờ trả).

Mô hình:
  B0  : trả đúng hạn (giả định của bảng tính)
  B1  : hạn + trung vị trễ của khách (co về điều khoản/công ty)            — mốc phải thắng (Phần 7)
  B1d : phân vị thực nghiệm của trễ theo khách (phân phối, không học)
  QLGBM : LightGBM hồi quy phân vị trên số ngày còn lại (chỉ hoá đơn đã đóng -> thiên lệch kiểm duyệt)
  AFT : XGBoost accelerated-failure-time (xử lý kiểm duyệt phải đúng cách)
  DH-LR : hàm nguy cơ thời gian rời rạc, hồi quy logistic (Singer & Willett 1993)
  DH-GBM : hàm nguy cơ rời rạc bằng LightGBM trên dữ liệu khai triển (hoá đơn x tuần) + biến lịch theo tuần
           biết trước (hạn rơi vào tuần k, ngày chạy thanh toán của khách rơi vào tuần k, số ngày làm việc, Tết,
           lời hứa rơi vào tuần k)  — mô hình chính
  + CQR : hiệu chỉnh conformal khoảng P10–P90 (Romano et al. 2019) trên cửa sổ hiệu chỉnh gần nhất.
"""
from __future__ import annotations

import numpy as np

from ..threads import NT
import pandas as pd
import lightgbm as lgb

from .. import calendar_vn as cal
from .features import FEATURES

K = 13
CAP = 120.0
QS = (0.1, 0.5, 0.9)

# --------------------------------------------------------------- lịch theo tuần (biến biết trước)
_BD = cal.business_day_index("2015-01-01", "2029-12-31")
_DAY0 = np.datetime64("2015-01-01")
_days = np.arange(_DAY0, np.datetime64("2030-01-01"))
_isbd = np.isin(_days, _BD.values.astype("datetime64[D]"))
_CUMBD = np.concatenate([[0], np.cumsum(_isbd)])
_tet = np.zeros(len(_days), bool)
for _a, _b in cal.TET_BREAK.values():
    _tet[(np.datetime64(_a) - _DAY0).astype(int):(np.datetime64(_b) - _DAY0).astype(int) + 1] = True
_CUMTET = np.concatenate([[0], np.cumsum(_tet)])
_DOM = pd.DatetimeIndex(_days).day.values.clip(max=30)


def _week_feats(df: pd.DataFrame, k: int) -> dict:
    T = df["cutoff"].values.astype("datetime64[D]")
    s = (T - _DAY0).astype(int) + 7 * (k - 1) + 1
    e = s + 7
    out = {"k": np.full(len(df), k, np.int16)}
    dtd = df["days_to_due"].values.astype(float)
    out["dtd_k"] = dtd - 7 * (k - 1)
    out["due_in_k"] = ((dtd >= 7 * (k - 1) + 1) & (dtd <= 7 * k)).astype(np.int8)
    out["bd_in_k"] = _CUMBD[e] - _CUMBD[s]
    out["tet_in_k"] = (_CUMTET[e] - _CUMTET[s] > 0).astype(np.int8)
    t1 = df["top1"].values.astype(float) if "top1" in df else np.full(len(df), np.nan)
    t2 = df["top2"].values.astype(float) if "top2" in df else np.full(len(df), np.nan)
    hit = np.zeros(len(df), bool)
    for j in range(7):
        dj = _DOM[s + j]
        hit |= (dj == t1) | (dj == t2)
    out["payrun_in_k"] = np.where(np.isnan(t1), np.nan, hit.astype(float))
    if "days_to_promised" in df:
        dp = df["days_to_promised"].values.astype(float)
        out["promised_in_k"] = np.where(np.isnan(dp), np.nan, ((dp >= 7 * (k - 1) + 1 - 3) & (dp <= 7 * k + 3)).astype(float))
    else:
        out["promised_in_k"] = np.full(len(df), np.nan)
    return out


WEEK_FEATS = ["k", "dtd_k", "due_in_k", "bd_in_k", "tet_in_k", "payrun_in_k", "promised_in_k"]


def expand(df: pd.DataFrame, train=True, feats=FEATURES):
    """Khai triển hoá đơn x tuần. train=True: chỉ tuần còn rủi ro & nhãn biết được; y = trả trong tuần k."""
    X0 = df[feats].astype("float32").values
    parts, ys, idx = [], [], []
    rem = df["remaining"].values if "remaining" in df else np.full(len(df), np.inf)
    tobs = df["time_obs"].values if "time_obs" in df else np.full(len(df), np.inf)
    ev = df["event"].values if "event" in df else np.zeros(len(df))
    for k in range(1, K + 1):
        if train:
            at_risk = tobs > 7 * (k - 1)
            evk = (ev == 1) & (np.ceil(rem / 7) == k)
            known = evk | (tobs >= 7 * k)
            m = at_risk & known
        else:
            m = np.ones(len(df), bool)
        if not m.any():
            continue
        wf = _week_feats(df.loc[m] if not m.all() else df, k)
        W = np.column_stack([wf[c] for c in WEEK_FEATS]).astype("float32")
        parts.append(np.hstack([X0[m], W]))
        idx.append(np.nonzero(m)[0])
        if train:
            ys.append(evk[m].astype(np.int8))
    X = np.vstack(parts)
    return X, (np.concatenate(ys) if train else None), np.concatenate(idx)


class HazardGBM:
    name = "DH-GBM"

    def __init__(self, params=None, rounds=600, feats=FEATURES):
        self.p = dict(objective="binary", learning_rate=0.05, num_leaves=63, min_data_in_leaf=200,
                      feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1,
                      num_threads=NT, seed=7)
        if params:
            self.p.update(params)
        self.rounds = rounds
        self.feats = feats
        self.booster = None

    def fit(self, df, weight=None, valid=None, init_model=None, rounds=None):
        X, y, ix = expand(df, True, self.feats)
        w = None if weight is None else np.asarray(weight)[ix]
        dtr = lgb.Dataset(X, y, weight=w, feature_name=self.feats + WEEK_FEATS, free_raw_data=True)
        cb, vs = [], []
        if valid is not None:
            Xv, yv, _ = expand(valid, True, self.feats)
            vs = [lgb.Dataset(Xv, yv, reference=dtr)]
            cb = [lgb.early_stopping(50, verbose=False)]
        self.booster = lgb.train(self.p, dtr, num_boost_round=rounds or self.rounds, valid_sets=vs, callbacks=cb,
                                 init_model=init_model)
        return self

    def hazards(self, df):
        X, _, ix = expand(df, False, self.feats)
        h = self.booster.predict(X)
        H = np.zeros((len(df), K))
        H[ix, np.repeat(np.arange(K), len(df))] = h
        return np.clip(H, 1e-5, 1 - 1e-5)


class HazardLR:
    name = "DH-LR"

    def __init__(self, feats=FEATURES):
        self.feats = feats

    def fit(self, df, weight=None, max_rows=600_000):
        from sklearn.linear_model import LogisticRegression
        X, y, _ = expand(df, True, self.feats)
        if len(y) > max_rows:
            s = np.random.default_rng(0).choice(len(y), max_rows, replace=False)
            X, y = X[s], y[s]
        X = self._prep(X, fit=True)
        self.m = LogisticRegression(C=0.5, max_iter=300).fit(X, y)
        return self

    def _prep(self, X, fit=False):
        X = X.astype(float)
        nan = np.isnan(X)
        if fit:
            self.med = np.nanmedian(X, axis=0)
            self.med = np.where(np.isnan(self.med), 0, self.med)
        X = np.where(nan, self.med, X)
        X = np.sign(X) * np.log1p(np.abs(X))
        if fit:
            self.mu, self.sd = X.mean(0), X.std(0) + 1e-6
        X = (X - self.mu) / self.sd
        kcol = len(self.feats)  # cột k -> one-hot
        oh = np.eye(K)[np.clip(np.round(X[:, kcol] * self.sd[kcol] + self.mu[kcol]).astype(int), 0, K - 1)] \
            if False else np.zeros((len(X), 0))
        return np.hstack([X, nan.astype(float), oh])

    def hazards(self, df):
        X, _, ix = expand(df, False, self.feats)
        h = self.m.predict_proba(self._prep(X))[:, 1]
        H = np.zeros((len(df), K))
        H[ix, np.repeat(np.arange(K), len(df))] = h
        return np.clip(H, 1e-5, 1 - 1e-5)


def pmf_from_hazard(H):
    S = np.cumprod(1 - H, axis=1)
    Sprev = np.hstack([np.ones((len(H), 1)), S[:, :-1]])
    P = Sprev * H
    return P, S


def quantiles_from_hazard(H, qs=QS, cap=CAP):
    P, S = pmf_from_hazard(H)
    F = np.hstack([np.zeros((len(H), 1)), 1 - S])  # F at 0,7,...,91
    htail = np.clip(H[:, -4:].mean(1), 0.02, 0.6)
    out = np.zeros((len(H), len(qs)))
    for j, q in enumerate(qs):
        res = np.full(len(H), cap)
        found = np.zeros(len(H), bool)
        for k in range(1, K + 1):
            m = ~found & (F[:, k] >= q)
            if m.any():
                lo, hi = F[m, k - 1], F[m, k]
                res[m] = 7 * (k - 1) + 7 * (q - lo) / np.maximum(hi - lo, 1e-9)
                found |= m
        m = ~found
        if m.any():  # đuôi hình học sau tuần 13
            SK = S[m, -1]
            wk = np.log(np.maximum((1 - q) / np.maximum(SK, 1e-9), 1e-9)) / np.log(1 - htail[m])
            res[m] = np.minimum(91 + 7 * np.maximum(wk, 0), cap)
        out[:, j] = np.maximum(res, 0.5)
    return out


def expected_days_from_hazard(H, cap=CAP):
    P, S = pmf_from_hazard(H)
    mid = 7 * np.arange(K) + 3.5
    return (P * mid).sum(1) + S[:, -1] * cap


# --------------------------------------------------------------- baselines
def b1_predict(df):
    """B1: hạn + trung vị trễ khách (backoff: công ty) -> số ngày còn lại (điểm)."""
    med = df["c_delay_med"].fillna(df["f_delay_mean"]).fillna(0.0)
    return np.maximum(df["days_to_due"].values + med.values, 1.0)


def b1_dist(df, hist_q=None):
    """B1d: phân vị trễ thực nghiệm theo khách (tính sẵn từ lịch sử)."""
    from .features import BASELINE_QUANTILES
    if all(c in df for c in BASELINE_QUANTILES):
        return np.clip(df[BASELINE_QUANTILES].to_numpy() + df['days_to_due'].to_numpy()[:, None], 1., CAP)
    if hist_q is None:
        raise ValueError('Thiếu lịch sử as-of cho B1d')
    q = df[["customer_id"]].merge(hist_q, on="customer_id", how="left")
    out = []
    for a in QS:
        col = q[f"q{int(a * 100)}"]
        v = col.fillna(float(col.median()) if col.notna().any() else 0.0).values
        out.append(np.clip(df["days_to_due"].values + v, 1.0, CAP))
    return np.column_stack(out)


def b0_predict(df):
    return np.maximum(df["days_to_due"].values, 1.0)


class QuantileLGBM:
    name = "QLGBM"

    def __init__(self, feats=FEATURES, rounds=350, alphas=(.05, .1, .2, .3, .5, .7, .8, .9, .95)):
        self.feats, self.rounds, self.models = feats, rounds, {}
        self.alphas = np.asarray(alphas, float)
        if not (np.all(np.diff(self.alphas) > 0) and np.all((self.alphas > 0) & (self.alphas < 1))):
            raise ValueError('alphas phải tăng nghiêm ngặt trong (0,1)')

    def fit(self, df, weight=None):
        d = df[df["event"] == 1]
        X = d[self.feats].astype("float32").values
        y = np.minimum(d["remaining"].values, CAP)
        for a in self.alphas:
            p = dict(objective="quantile", alpha=a, learning_rate=0.1, num_leaves=63, min_data_in_leaf=100,
                     feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, verbose=-1, seed=3, num_threads=NT)
            w = None if weight is None else np.asarray(weight)[(df['event'] == 1).to_numpy()]
            self.models[a] = lgb.train(p, lgb.Dataset(X, y, weight=w), num_boost_round=self.rounds)
        return self

    def predict_dense(self, df):
        X = df[self.feats].astype("float32").values
        Q = np.column_stack([self.models[a].predict(X) for a in self.alphas])
        return np.clip(np.sort(Q, axis=1), 0.5, CAP)

    def predict(self, df):
        dense = self.predict_dense(df)
        return np.column_stack([np.array([np.interp(a, self.alphas, row) for row in dense]) for a in QS])

    def cdf(self, df):
        return cdf_from_quantiles(self.predict_dense(df), self.alphas)


class AFT:
    name = "XGB-AFT"

    def __init__(self, feats=FEATURES, rounds=300, dist="normal", scale=0.3):
        self.feats, self.rounds, self.dist, self.scale = feats, rounds, dist, scale

    def fit(self, df, weight=None):
        import xgboost as xgb
        X = df[self.feats].astype("float32").values
        lo = np.minimum(df["time_obs"].values, 3650) + 0.5
        hi = np.where(df["event"].values == 1, lo, np.inf)
        d = xgb.DMatrix(X)
        d.set_float_info("label_lower_bound", lo)
        d.set_float_info("label_upper_bound", hi)
        p = dict(objective="survival:aft", eval_metric="aft-nloglik", aft_loss_distribution=self.dist,
                 aft_loss_distribution_scale=self.scale, tree_method="hist", learning_rate=0.1, max_depth=6,
                 min_child_weight=20, subsample=0.8, colsample_bytree=0.8, nthread=NT, seed=5,
                 base_score=float(np.log(np.median(lo))))  # AFT: base_score ở thang log thời gian
        self.m = xgb.train(p, d, num_boost_round=self.rounds)
        return self

    def predict(self, df):
        import xgboost as xgb
        from scipy.stats import norm, logistic
        t = self.m.predict(xgb.DMatrix(df[self.feats].astype("float32").values))
        z = norm.ppf if self.dist == "normal" else logistic.ppf
        Q = np.column_stack([t * np.exp(self.scale * z(a)) for a in QS])
        return np.clip(Q, 0.5, CAP)


# --------------------------------------------------------------- conformal (CQR)
def _conformal_quantile(scores, alpha):
    scores = np.asarray(scores, float)
    if not len(scores) or not np.isfinite(scores).all() or not 0 < alpha < 1:
        raise ValueError('Điểm conformal phải hữu hạn, không rỗng; alpha trong (0,1)')
    rank = int(np.ceil((len(scores) + 1) * (1 - alpha)))
    return float(np.sort(scores)[rank - 1]) if rank <= len(scores) else np.inf


def cqr_fit(y_cal, Q_cal, alpha=0.2, allow_shrink=True):
    y = np.minimum(np.asarray(y_cal, float), CAP)
    E = np.maximum(Q_cal[:, 0] - y, y - Q_cal[:, -1])
    qhat = _conformal_quantile(E, alpha)
    return qhat if allow_shrink else max(qhat, 0.)


def cqr_apply(Q, qhat):
    Q = Q.copy()
    Q[:, 0] = np.maximum(Q[:, 0] - qhat, 0.5)
    Q[:, -1] = np.minimum(Q[:, -1] + qhat, CAP)
    Q[:, 0] = np.minimum(Q[:, 0], Q[:, 1])
    Q[:, -1] = np.maximum(Q[:, -1], Q[:, 1])
    return Q


def cqr_fit_asym(y, Q, alpha_lo=.1, alpha_hi=.1, allow_shrink=True):
    """Hai phía với bậc hữu hạn mẫu; cho phép thu hẹp khoảng thừa phủ."""
    y = np.minimum(np.asarray(y, float), CAP)
    q = (_conformal_quantile(Q[:, 0] - y, alpha_lo), _conformal_quantile(y - Q[:, -1], alpha_hi))
    return q if allow_shrink else tuple(max(v, 0.) for v in q)


def cqr_apply_asym(Q, qhat):
    out = np.asarray(Q, float).copy()
    out[:, 0] = np.minimum(np.maximum(out[:, 0] - qhat[0], .5), out[:, 1])
    out[:, -1] = np.maximum(np.minimum(out[:, -1] + qhat[1], CAP), out[:, 1])
    return out


def cdf_from_quantiles(Q, alphas=QS, grid=None):
    """Nội suy PCHIP đơn điệu; gộp phân vị trùng để xử lý khối lượng điểm."""
    from scipy.interpolate import PchipInterpolator
    Q, alphas = np.asarray(Q, float), np.asarray(alphas, float)
    if Q.ndim != 2 or Q.shape[1] != len(alphas) or not np.isfinite(Q).all():
        raise ValueError('Kích thước hoặc giá trị phân vị không hợp lệ')
    if np.any(np.diff(alphas) <= 0) or np.any((alphas <= 0) | (alphas >= 1)):
        raise ValueError('alphas phải tăng trong (0,1)')
    grid = 7 * np.arange(1, K + 1) if grid is None else np.asarray(grid, float)
    out = np.empty((len(Q), len(grid)))
    for i, row in enumerate(np.sort(Q, axis=1)):
        x = np.r_[0., np.maximum(row, .5), max(CAP * 1.5, row[-1] + 1)]
        p = np.r_[0., alphas, .999]
        # Điểm trùng đại diện CDF liên tục phải tại phân vị cao nhất.
        keep = np.r_[np.diff(x) > 0, True]
        f = PchipInterpolator(x[keep], p[keep], extrapolate=False)
        out[i] = np.where(grid < 0, 0., np.where(grid > x[-1], 1., f(np.clip(grid, 0, x[-1]))))
    return np.clip(out, 0, 1)


# --------------------------------------------------------------- T2: cure (không bao giờ trả)
class CureGBM:
    name = "Cure-GBM"

    def __init__(self, feats=FEATURES, rounds=400):
        self.feats, self.rounds = feats, rounds

    def fit(self, df, weight=None, calibration=None):
        d = df[(df["event"] == 1) | (df["bad_known"] == 1)]
        X = d[self.feats].astype("float32").values
        y = d["bad_known"].values
        p = dict(objective="binary", learning_rate=0.04, num_leaves=31, min_data_in_leaf=200, feature_fraction=0.8,
                 bagging_fraction=0.8, bagging_freq=1, lambda_l2=10.0, verbose=-1, seed=11, num_threads=NT)
        w = None if weight is None else np.asarray(weight)[((df['event'] == 1) | (df['bad_known'] == 1)).to_numpy()]
        self.m = lgb.train(p, lgb.Dataset(X, y, weight=w), num_boost_round=self.rounds)
        self.calibrator = None
        if calibration is not None:
            self.calibrate(calibration)
        return self

    def predict(self, df):
        return self.m.predict(df[self.feats].astype("float32").values)

    def calibrate(self, df):
        from sklearn.isotonic import IsotonicRegression
        known = df[(df['event'] == 1) | (df['bad_known'] == 1)]
        if known.empty:
            raise ValueError('Không có nhãn đã chín để hiệu chỉnh cure')
        self.calibrator = IsotonicRegression(out_of_bounds='clip').fit(self.predict(known), known['bad_known'])
        return self

    def predict_proba_calibrated(self, df):
        if getattr(self, 'calibrator', None) is None:
            raise ValueError('Cure chưa được hiệu chỉnh trên cửa sổ riêng')
        return self.calibrator.predict(self.predict(df))


# --------------------------------------------------------------- đánh giá
def evaluate_quantiles(y_rem, Q):
    from ..eval.metrics import pinball, coverage, interval_score
    y = np.minimum(np.asarray(y_rem, float), CAP)
    return {
        "pinball_q10": pinball(y, Q[:, 0], .1), "pinball_q50": pinball(y, Q[:, 1], .5),
        "pinball_q90": pinball(y, Q[:, 2], .9),
        "pinball_avg": np.mean([pinball(y, Q[:, i], a) for i, a in enumerate(QS)]),
        "MAE_p50": float(np.mean(np.abs(y - Q[:, 1]))),
        "MAE_p50_paid": float(np.mean(np.abs(y - Q[:, 1])[np.asarray(y_rem) <= CAP])),
        "cov80": coverage(y, Q[:, 0], Q[:, 2]), "IS80": interval_score(y, Q[:, 0], Q[:, 2], 0.2),
    }


def weekly_cdf_from_quantiles(Q, qs=QS):
    """CDF tuần xấp xỉ từ 3 phân vị (nội suy tuyến tính, đuôi phẳng) — để so IBS với mô hình phân vị."""
    grid = 7 * np.arange(1, K + 1)
    xs = np.column_stack([np.zeros(len(Q)), Q, np.full(len(Q), CAP * 1.5)])
    ps = np.array([0.0, *qs, 0.999])
    out = np.zeros((len(Q), K))
    for i in range(len(Q)):
        out[i] = np.interp(grid, np.maximum.accumulate(xs[i]), ps)
    return out


def collections_by_week(df, P, amount_col="amount_open"):
    """Thu tiền kỳ vọng theo tuần cho từng (công ty, điểm cắt) vs thực tế -> WAPE (thứ người dùng cần)."""
    amt = df[amount_col].values
    rem = df["remaining"].values
    wk = np.ceil(rem / 7)
    rows = []
    keys = df["firm_id"].astype(str) + "|" + df["cutoff"].astype(str)
    for k in range(1, K + 1):
        pred = amt * P[:, k - 1]
        act = amt * (wk == k)
        g = pd.DataFrame({"key": keys, "pred": pred, "act": act}).groupby("key").sum()
        g["k"] = k
        rows.append(g)
    return pd.concat(rows)
