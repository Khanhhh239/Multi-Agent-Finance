#!/usr/bin/env python3
"""T4 — doanh thu mới theo tuần, đánh giá rolling-origin (26 tuần cuối, mỗi 4 tuần) trên:
  (1) miền đích tổng hợp tgt (học từ src -> chuyển miền),  (2) Online Retail II (dữ liệu THẬT, Anh).
So sánh: Global-LGBM-Q (+CQR), Seasonal-naive, Mean-13w, Chronos-Bolt zero-shot, Ensemble(LGBM, Chronos)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH, OUT  # noqa: E402
from agent1.models import t4_revenue as T4  # noqa: E402
from agent1.data import real_loaders as R  # noqa: E402
from agent1.eval.metrics import coverage  # noqa: E402

RES = OUT / "t4"
RES.mkdir(parents=True, exist_ok=True)


def synth_series(world):
    inv = pd.read_parquet(SYNTH / world / "invoices.parquet")
    inv["week"] = inv["issue_date"].dt.to_period("W-SUN").dt.start_time
    g = inv.groupby(["firm_id", "week"])["amount_gross"].sum()
    out = {}
    for fid, s in g.groupby(level=0):
        s = s.droplevel(0)
        w = pd.date_range(s.index.min(), s.index.max(), freq="7D")
        out[f"{world}:{fid}"] = s.reindex(w, fill_value=0.0)
    return out


def real_series():
    df = R.online_retail_weekly()
    out = {}
    for sid, g in df.groupby("series_id"):
        s = g.set_index("week")["y"].clip(lower=0)
        if (s > 0).mean() > 0.5:
            out[f"oretail:{sid}"] = s
    return out


def build(series, vn, origin_sel):
    Xs, Ys, metas, ids = [], [], [], []
    for sid, s in series.items():
        y = s.values.astype(float)
        origins = origin_sel(len(y))
        X, Y, meta = T4.make_rows(y, s.index, vn, origins)
        if len(X):
            Xs.append(X)
            Ys.append(Y)
            metas.append(meta)
            ids += [sid] * len(X)
    return np.vstack(Xs), np.concatenate(Ys), np.vstack(metas), np.array(ids)


def evaluate(test_series, model, vn, tag, use_chronos=True, cal=None):
    rows = []
    origins_fn = lambda n: list(range(n - 26 - T4.H, n - T4.H, 4))  # noqa: E731
    X, Y, meta, ids = build(test_series, vn, origins_fn)
    pred = {"Global-LGBM-Q": model.predict(X) * meta[:, 2:3]}
    if cal is not None:
        Qc = pred["Global-LGBM-Q"].copy()
        Qc[:, 0] = np.clip(Qc[:, 0] - cal * meta[:, 2], 0, None)
        Qc[:, 2] = Qc[:, 2] + cal * meta[:, 2]
        pred["Global-LGBM-Q+CQR"] = Qc
    yt = Y * meta[:, 2]
    sn, mn = [], []
    for sid in np.unique(ids):
        m = ids == sid
        y = test_series[sid].values.astype(float)
        sn.append((m, T4.baseline_rows(y, meta[m], "snaive")))
        mn.append((m, T4.baseline_rows(y, meta[m], "mean")))
    for name, parts in (("Seasonal-naive", sn), ("Mean-13w", mn)):
        Q = np.zeros((len(meta), 3))
        for m, q in parts:
            Q[m] = q
        pred[name] = Q
    if use_chronos:
        ctx, keys = [], []
        for sid in np.unique(ids):
            y = test_series[sid].values.astype(float)
            for t in sorted(set(meta[ids == sid][:, 0].astype(int))):
                ctx.append(y[:t + 1])
                keys.append((sid, t))
        cq = T4.chronos_predict(ctx)
        if cq is not None:
            lut = {k: q for k, q in zip(keys, cq)}
            Qc = np.array([lut[(sid, int(t))][int(h) - 1, :] for sid, (t, h, s) in zip(ids, meta)])
            pred["Chronos-Bolt (zero-shot)"] = np.sort(Qc, axis=1)
            pred["Ensemble LGBM+Chronos"] = np.sort((pred["Global-LGBM-Q"] + pred["Chronos-Bolt (zero-shot)"]) / 2, axis=1)
    scale = np.array([np.mean(np.abs(np.diff(test_series[sid].values[:int(t) + 1]))) for sid, (t, h, s) in zip(ids, meta)])
    for n, Q in pred.items():
        sp = T4.spl(yt, Q, scale)
        rows.append({"setting": tag, "model": n, "SPL": float(sp.mean()), "SPL_h1_4": float(sp[meta[:, 1] <= 4].mean()),
                     "SPL_h5_13": float(sp[meta[:, 1] > 4].mean()), "cov80": coverage(yt, Q[:, 0], Q[:, 2]),
                     "WAPE_p50": float(np.abs(yt - Q[:, 1]).sum() / np.abs(yt).sum()), "n": len(yt)})
    return pd.DataFrame(rows)


# Ba cửa sổ rời nhau theo thời gian: train (mục tiêu kết thúc trước cal) | cal (CQR) | test (26 tuần cuối)
CAL_LO = 26 + 2 * T4.H + 13      # origin hiệu chỉnh: n-CAL_LO .. n-26-2H (mục tiêu kết thúc trước origin test đầu)
train_fn = lambda n: list(range(20, n - CAL_LO - T4.H))  # noqa: E731


def cqr_scale(model, series, vn):
    """Hệ số CQR (đơn vị đã chuẩn hoá) trên cửa sổ hiệu chỉnh rời khỏi train và test."""
    fn = lambda n: list(range(n - CAL_LO, n - 26 - 2 * T4.H + 1, 2))  # noqa: E731
    X, Y, meta, _ = build(series, vn, fn)
    Q = model.predict(X)
    E = np.maximum(Q[:, 0] - Y, Y - Q[:, 2])
    return float(np.quantile(E, 0.8))


def main():
    res = []
    # (1) tổng hợp: học trên src (đến trước giai đoạn test), test trên tgt (miền đích) và src (trong miền)
    src = synth_series("src")
    tgt = synth_series("tgt")
    X, Y, _, _ = build(src, True, train_fn)
    m = T4.GlobalQuantileLGBM().fit(X, Y)
    c = cqr_scale(m, src, True)
    res.append(evaluate(src, m, True, "synthetic src (in-domain)", cal=c))
    res.append(evaluate(tgt, m, True, "synthetic tgt (zero-shot transfer from src)", cal=c))
    print(pd.concat(res).round(4).to_string(), flush=True)
    # (2) thật: Online Retail II — học trên phần đầu của chính các chuỗi này (+ tổng hợp như tiền huấn luyện)
    real = real_series()
    Xr, Yr, _, _ = build(real, False, train_fn)
    mr = T4.GlobalQuantileLGBM().fit(Xr, Yr)
    res.append(evaluate(real, mr, False, "real Online Retail II (trained on own past)", cal=cqr_scale(mr, real, False)))
    mp = T4.GlobalQuantileLGBM().fit(np.vstack([Xr, X]), np.r_[Yr, Y])
    r2 = evaluate(real, mp, False, "real Online Retail II (pretrain synthetic + own past)",
                  cal=cqr_scale(mp, real, False))
    res.append(r2[~r2["model"].isin(["Seasonal-naive", "Mean-13w", "Chronos-Bolt (zero-shot)"])])
    out = pd.concat(res)
    print(out.round(4).to_string(), flush=True)
    out.to_csv(RES / "t4_revenue_forecast.csv", index=False)


if __name__ == "__main__":
    main()
