#!/usr/bin/env python3
"""Sprint 1 — T1 trên dữ liệu THẬT, giao thức v2 (20/10/2026).

Khác exp_C (v1 của phiên trước):
  1. Khai triển hazard chỉ dùng tuần đã quan sát đủ (sửa thiên lệch trong `t1.expand`, cờ FULL_WEEK_ONLY).
  2. Hai giai đoạn, không bỏ đói dữ liệu:
     (a) mô hình CHỌN = học trên cutoff < cal_lo (nhãn kiểm duyệt tại cal_lo) → dự báo cửa sổ hiệu chỉnh
         [cal_lo, cal_hi] (nhãn tới O) → chọn trọng số trộn w và q̂ của CQR;
     (b) mô hình CUỐI = học lại trên mọi cutoff < O (nhãn kiểm duyệt tại O) → áp w, q̂ đã chọn lên test.
     Test không bao giờ dùng để chọn.
  3. BLEND = w·Q_model + (1−w)·Q_B1d (Vincentization), w ∈ {0, .25, .5, .75, 1} theo pinball trên cửa sổ hiệu chỉnh.
  4. CI 95% của chênh lệch pinball so với B1d: bootstrap theo cụm (khách hàng; BPI chỉ có 3 công ty).

  python scripts/sprint1/run_real_v2.py [--data ci,bpi]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from agent1.models import t1  # noqa: E402
from agent1.eval import metrics as M  # noqa: E402
from agent1.data import real_loaders as RL  # noqa: E402
import run_t1 as R1  # noqa: E402

OUT = ROOT / "outputs" / "t1" / "real_v2"
OUT.mkdir(parents=True, exist_ok=True)
VERSION = "C-real-fullweek-refit-blend-v2"
CFG = {"ci": (RL.customer_invoices, "snap_real_customer_invoices_5c1226fdb988.parquet", "2019-10-01", 63),
       "bpi": (RL.bpi2019, "snap_real_bpi2019_5c1226fdb988.parquet", "2018-09-03", 56)}
W_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def cap_rows(d, n=400_000):
    if len(d) > n:
        d = d[d["cutoff"].dt.isocalendar().week.astype(int) % 2 == 0]
        d = d.sample(min(len(d), n), random_state=0)
    return d


def pin(y, Q):
    return t1.evaluate_quantiles(y, Q)["pinball_avg"]


def per_row_pinball(y, Q):
    y = np.minimum(np.asarray(y, float), t1.CAP)[:, None]
    a = np.array(t1.QS)[None, :]
    d = y - Q
    return np.maximum(a * d, (a - 1) * d).mean(1)


def fit_models(tr):
    return {"DH-GBM": t1.HazardGBM(dict(min_data_in_leaf=100)).fit(tr),
            "DH-LR": t1.HazardLR().fit(tr),
            "QLGBM": t1.QuantileLGBM().fit(tr)}


def predict(models, d, chunk=40_000):
    """Dự đoán theo khối để vừa RAM (BPI: 353k hàng × 13 tuần)."""
    if len(d) > chunk:
        parts = [predict(models, d.iloc[i:i + chunk], chunk) for i in range(0, len(d), chunk)]
        return {k: np.vstack([p[k] for p in parts]) for k in parts[0]}
    out = {"B1d": t1.b1_dist(d, None)}
    for n, m in models.items():
        if n.startswith("DH"):
            out[n] = t1.quantiles_from_hazard(m.hazards(d))
        else:
            dense = m.predict_dense(d)
            out[n] = np.column_stack([np.array([np.interp(a, m.alphas, r) for r in dense]) for a in t1.QS])
    out["ENS"] = np.sort((out["DH-GBM"] + out["QLGBM"]) / 2, axis=1)
    return out


def blend(Qm, Qb, w):
    return np.sort(w * Qm + (1 - w) * Qb, axis=1)


def run(name):
    loader, snap, O, test_days = CFG[name]
    inv = loader()
    end = inv["paid_date_true"].max()
    S = pd.read_parquet(ROOT / "data/processed" / snap)
    f64 = S.select_dtypes("float64").columns
    S[f64] = S[f64].astype("float32")
    O = min(pd.Timestamp(O), end - pd.Timedelta(days=int(t1.CAP) + test_days))
    cal_lo, cal_hi = O - pd.Timedelta(days=183), O - pd.Timedelta(days=120)
    te = R1.censor(S[S.cutoff >= O], end)
    te = te[te.cutoff <= end - pd.Timedelta(days=int(t1.CAP))]
    tr_final = cap_rows(R1.censor(S[S.cutoff < O], O))
    has_cal = (S.cutoff < cal_lo).sum() > 1000 and S.cutoff.between(cal_lo, cal_hi).sum() > 1000
    if has_cal:
        tr_sel = cap_rows(R1.censor(S[S.cutoff < cal_lo], cal_lo))
        cal = R1.censor(S[S.cutoff.between(cal_lo, cal_hi)], O)
    else:  # dữ liệu quá ngắn: cửa sổ hiệu chỉnh = 4 cutoff cuối có nhãn chín trước O, chọn bằng mô hình học trước đó
        cuts = np.sort(S.cutoff[S.cutoff <= O - pd.Timedelta(days=int(t1.CAP))].unique())
        c_lo = pd.Timestamp(cuts[-4]) if len(cuts) >= 6 else pd.Timestamp(cuts[len(cuts) // 2])
        tr_sel = cap_rows(R1.censor(S[S.cutoff < c_lo], c_lo))
        cal = R1.censor(S[S.cutoff.between(c_lo, O - pd.Timedelta(days=int(t1.CAP)))], O)
    log(f"{name}: O={O.date()} end={end.date()} sel_train={len(tr_sel)} cal={len(cal)} final_train={len(tr_final)} test={len(te)}")
    # (a) chọn trên cửa sổ hiệu chỉnh
    m_sel = fit_models(tr_sel)
    Pc = predict(m_sel, cal)
    yc = cal["remaining"].values
    choice = {}
    for base in ("DH-GBM", "ENS"):
        scores = {w: pin(yc, blend(Pc[base], Pc["B1d"], w)) for w in W_GRID}
        w = min(scores, key=scores.get)
        Qc = blend(Pc[base], Pc["B1d"], w)
        choice[base] = dict(w=w, cal_scores=scores, qhat=t1.cqr_fit(yc, Qc))
    choice["B1d"] = dict(qhat=t1.cqr_fit(yc, Pc["B1d"]))
    # (b) huấn luyện lại đầy đủ, áp lựa chọn lên test
    m_fin = fit_models(tr_final)
    P = predict(m_fin, te)
    for base in ("DH-GBM", "ENS"):
        P[f"BLEND({base},B1d) w={choice[base]['w']}"] = blend(P[base], P["B1d"], choice[base]["w"])
        P[f"BLEND({base},B1d)+CQR"] = t1.cqr_apply(P[f"BLEND({base},B1d) w={choice[base]['w']}"], choice[base]["qhat"])
    P["B1d+CQR"] = t1.cqr_apply(P["B1d"], choice["B1d"]["qhat"])
    y = te["remaining"].values
    groups = te["customer_id"].astype(str).values
    base_loss = per_row_pinball(y, P["B1d"])
    rows = []
    for n, Q in P.items():
        r = dict(setting=name, model=n, n=len(te), measurement_version=VERSION, **t1.evaluate_quantiles(y, Q))
        loss = per_row_pinball(y, Q)
        imp = lambda b, m: 100 * (b.mean() - m.mean()) / b.mean()  # noqa: E731
        r["improvement_vs_B1d_pct"] = imp(base_loss, loss)
        lo, hi = M.bootstrap_ci(imp, base_loss, loss, n=300, seed=1, groups=groups)
        r["improvement_ci_low"], r["improvement_ci_high"] = lo, hi
        r["bootstrap_groups"] = "customer_id"
        rows.append(r)
    res = pd.DataFrame(rows)
    log("\n" + res[["model", "pinball_avg", "MAE_p50", "cov80", "improvement_vs_B1d_pct", "improvement_ci_low",
                    "improvement_ci_high"]].round(4).to_string(index=False))
    res.to_csv(OUT / f"C_real_v2_{name}.csv", index=False)
    (OUT / f"{name}_choice.json").write_text(json.dumps(
        {k: {kk: (vv if not isinstance(vv, dict) else {str(a): float(b) for a, b in vv.items()}) for kk, vv in v.items()}
         for k, v in choice.items()}, indent=2, default=float), encoding="utf-8")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="ci,bpi")
    a = ap.parse_args()
    out = pd.concat([run(d) for d in a.data.split(",")]
                    + [pd.read_csv(OUT / f"C_real_v2_{x}.csv") for x in ("ci", "bpi")
                       if x not in a.data.split(",") and (OUT / f"C_real_v2_{x}.csv").exists()])
    out["expand_full_week_only"] = t1.FULL_WEEK_ONLY
    out.to_csv(OUT / "C_real_v2.csv", index=False)
    log("wrote", OUT / "C_real_v2.csv")
