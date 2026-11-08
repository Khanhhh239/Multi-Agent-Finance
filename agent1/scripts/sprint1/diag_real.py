#!/usr/bin/env python3
"""Sprint 1 — chẩn đoán T1 trên dữ liệu thật (DH-LR hỏng, BPI hồi quy). Tái hiện đúng cách chia của exp_C.

  python scripts/sprint1/diag_real.py --data ci|bpi --step lr|gbm|labels
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from agent1.models import t1  # noqa: E402
from agent1.models.features import FEATURES  # noqa: E402
import run_t1 as R1  # noqa: E402

SNAP = {"ci": ("snap_real_customer_invoices_5c1226fdb988.parquet", "2019-10-01", 63),
        "bpi": ("snap_real_bpi2019_5c1226fdb988.parquet", "2018-09-03", 56)}


def split(name):
    f, O, test_days = SNAP[name]
    S = pd.read_parquet(ROOT / "data/processed" / f)
    from agent1.data import real_loaders as RL
    inv = (RL.customer_invoices if name == "ci" else RL.bpi2019)()
    label_end = inv["paid_date_true"].max()
    O = min(pd.Timestamp(O), label_end - pd.Timedelta(days=int(t1.CAP) + test_days))
    cal_lo, cal_hi = O - pd.Timedelta(days=183), O - pd.Timedelta(days=120)
    cal = R1.censor(S[S.cutoff.between(cal_lo, cal_hi)], O)
    if len(cal) > 100 and (S.cutoff < cal_lo).sum() > 100:
        tr = R1.censor(S[S.cutoff < cal_lo], cal_lo)
    else:
        tr = R1.censor(S[S.cutoff < O], O); cal = cal.iloc[:0]
    if len(tr) > 400_000:
        tr = tr[tr["cutoff"].dt.isocalendar().week.astype(int) % 2 == 0].sample(400_000, random_state=0)
    te = R1.censor(S[S.cutoff >= O], label_end)
    te = te[te.cutoff <= label_end - pd.Timedelta(days=int(t1.CAP))]
    return S, tr, cal, te, O, label_end


def describe(tr, te):
    rows = []
    for c in FEATURES:
        a, b = tr[c].astype(float), te[c].astype(float)
        rows.append(dict(f=c, tr_nan=a.isna().mean(), te_nan=b.isna().mean(), tr_std=a.std(), tr_mu=a.mean(),
                         te_mu=b.mean(), te_std=b.std()))
    d = pd.DataFrame(rows)
    d["shift_sd"] = (d.te_mu - d.tr_mu).abs() / d.tr_std.replace(0, np.nan)
    return d


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="ci")
    ap.add_argument("--step", default="lr")
    a = ap.parse_args()
    S, tr, cal, te, O, end = split(a.data)
    print(a.data, "train", len(tr), "cal", len(cal), "test", len(te), "O", O.date(), "end", end.date())
    if a.step == "labels":
        for n, d in (("train", tr), ("test", te)):
            r = d.remaining.replace(np.inf, np.nan)
            print(n, "event", round(float(d.event.mean()),3), "inf", round(float(np.isinf(d.remaining).mean()),3), "cutoffs", d.cutoff.nunique(), d.cutoff.min().date(), d.cutoff.max().date(),
                  "rem q", r.quantile([.1, .5, .9, .99]).round(1).to_dict(), "time_obs med", d.time_obs.median())
        print(describe(tr, te).sort_values("shift_sd", ascending=False).head(15).round(3).to_string())
    if a.step == "lr":
        m = t1.HazardLR().fit(tr)
        X, _, ix = t1.expand(te, False, m.feats)
        Z = m._prep(X)
        print("max |z| per col (top):")
        names = m.feats + t1.WEEK_FEATS
        zmax = np.abs(Z[:, :len(names)]).max(0)
        for i in np.argsort(-zmax)[:10]:
            print("  ", names[i], round(float(zmax[i]), 1), "sd_train", round(float(m.sd[i]), 6))
        H = m.hazards(te)
        print("hazard mean by k", H.mean(0).round(3))
        Q = t1.quantiles_from_hazard(H)
        print(t1.evaluate_quantiles(te.remaining.values, Q))
    if a.step == "gbm":
        m = t1.HazardGBM(dict(min_data_in_leaf=100)).fit(tr)
        H = m.hazards(te)
        Q = t1.quantiles_from_hazard(H)
        print("hazard mean by k", H.mean(0).round(3), "S13 mean", np.prod(1 - H, 1).mean().round(3))
        print("pred q50 quantiles", np.quantile(Q[:, 1], [.1, .5, .9]).round(1), "true rem q50",
              np.nanmedian(np.minimum(te.remaining, 120)))
        print(t1.evaluate_quantiles(te.remaining.values, Q))
        Qb = t1.b1_dist(te, None)
        print("B1d", t1.evaluate_quantiles(te.remaining.values, Qb))
