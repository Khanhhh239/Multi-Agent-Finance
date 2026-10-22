"""G13: chính sách cảnh báo thiếu hụt — hiệu chỉnh isotonic + xác nhận k tuần liên tiếp, chọn hoàn toàn trên nguồn.

Định nghĩa sự kiện, độ sớm và báo động giả dùng lại `alerts.event_metrics` (không đổi thước đo của cổng).
"""
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from .alerts import event_metrics

TAUS = tuple(np.round(np.arange(0.05, 0.96, 0.05), 2))
CONFIRM = (1, 2, 3)
FA_BUDGET = 0.8          # biên dưới mức cổng 1,0/công ty-năm


def fit_isotonic(y, p):
    return IsotonicRegression(y_min=0, y_max=1, out_of_bounds='clip').fit(np.asarray(p, float), np.asarray(y, float))


def oof_calibrate(pred, probability, label, n_folds=5, seed=7):
    """Xác suất hiệu chỉnh ngoài-fold theo công ty (để chọn chính sách trên nguồn không lạc quan)."""
    firms = np.array(sorted(pred.firm_id.unique()))
    np.random.default_rng(seed).shuffle(firms)
    fold = {f: i % n_folds for i, f in enumerate(firms)}
    k = pred.firm_id.map(fold).to_numpy()
    out = np.empty(len(pred))
    for i in range(n_folds):
        tr, te = k != i, k == i
        if te.any():
            out[te] = fit_isotonic(pred[label].to_numpy()[tr], pred[probability].to_numpy()[tr]).predict(
                pred[probability].to_numpy()[te])
    return out


def confirmed_alarm(pred, probability, tau, k):
    """Báo động tại tuần t nếu xác suất >= tau trong k tuần liên tiếp kết thúc ở t (theo từng công ty)."""
    pred = pred.sort_values(['firm_id', 'cutoff'])
    hit = (pred[probability] >= tau).astype(int)
    run = hit.groupby((hit != hit.groupby(pred.firm_id).shift()).cumsum()).cumsum() * hit
    return pd.Series((run >= k).to_numpy(), index=pred.index).reindex(pred.index)


def fill_gaps(pred, alarm, gap_weeks):
    """Lấp khoảng trống <= gap_weeks tuần giữa hai báo động của cùng công ty ⇒ một đợt cảnh báo không bị tách đôi.
    Chỉ thêm tuần báo động SAU báo động đầu của đợt: không làm mất phát hiện, không tăng số đợt (báo giả không tăng)."""
    if not gap_weeks:
        return alarm
    out = alarm.copy()
    p = pred.assign(_a=alarm.to_numpy().astype(bool))
    for _, g in p.sort_values(['firm_id', 'cutoff']).groupby('firm_id'):
        on = g[g._a]
        for (i0, d0), (_, d1) in zip(on.cutoff.items(), list(on.cutoff.items())[1:]):
            if 0 < (d1 - d0).days <= 7 * gap_weeks:
                between = g.index[(g.cutoff > d0) & (g.cutoff < d1)]
                out.loc[between] = True
    return out


def policy_metrics(pred, daily_cash, probability, tau, k, horizon_days=91, fill=0):
    alarm = fill_gaps(pred, confirmed_alarm(pred, probability, tau, k), fill)
    scored = pred.assign(_alarm=alarm.astype(float).reindex(pred.index).to_numpy())
    return event_metrics(scored, daily_cash, threshold=0.5, probability='_alarm', horizon_days=horizon_days)


def select_policy(pred, daily_cash, probability, horizon_days=91, fa_budget=FA_BUDGET, fills=(0,)):
    rows = [dict(tau=t, k=k, fill=f, **policy_metrics(pred, daily_cash, probability, t, k, horizon_days, fill=f))
            for t in TAUS for k in CONFIRM for f in fills]
    grid = pd.DataFrame(rows)
    ok = grid[(grid.false_alarms_per_firm_year <= fa_budget) & (grid.n_events > 0)]
    if len(ok):
        best = ok.sort_values(['detected_at_least_4w', 'median_lead_weeks', 'false_alarms_per_firm_year'],
                              ascending=[False, False, True]).iloc[0]
        feasible = True
    else:
        best = grid.sort_values(['false_alarms_per_firm_year', 'detected_at_least_4w'], ascending=[True, False]).iloc[0]
        feasible = False
    return dict(tau=float(best.tau), k=int(best.k), fill=int(best.fill), feasible_on_source=feasible), grid


def firm_bootstrap(pred, daily_cash, probability, tau, k, horizon_days=91, n=200, seed=7):
    firms = pred.firm_id.unique()
    rng = np.random.default_rng(seed)
    det, fa = [], []
    for _ in range(n):
        pick = rng.choice(firms, len(firms), replace=True)
        parts = [pred[pred.firm_id == f].assign(firm_id=f'{f}#{i}') for i, f in enumerate(pick)]
        cash = pd.concat([daily_cash[daily_cash.firm_id == f].assign(firm_id=f'{f}#{i}') for i, f in enumerate(pick)])
        m = policy_metrics(pd.concat(parts, ignore_index=True), cash, probability, tau, k, horizon_days)
        det.append(m['detected_at_least_4w']); fa.append(m['false_alarms_per_firm_year'])
    q = lambda v: (float(np.nanquantile(v, .025)), float(np.nanquantile(v, .975)))  # noqa: E731
    (dl, dh), (fl, fh) = q(det), q(fa)
    return dict(detected_ci_low=dl, detected_ci_high=dh, fa_ci_low=fl, fa_ci_high=fh, bootstrap_n=n)
