#!/usr/bin/env python3
"""G17 — sáu đặc trưng lời hứa mới (đăng ký trước: docs/03_Evaluation/G17_T8_PREREG.md). Không sửa features.py:
đặc trưng tính ngoài, nối vào snapshot theo (invoice_id, cutoff) bằng merge_asof (chỉ dữ liệu <= cutoff).
Đầu ra: outputs/sprint5/g17_promise_features.csv"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from agent1.paths import SYNTH, OUT  # noqa: E402
from agent1.models import t1  # noqa: E402
from agent1.eval import metrics as M  # noqa: E402
import run_t1 as R1  # noqa: E402

O = pd.Timestamp("2024-07-01")
VERSION = "g17-promise-features-v1"
NEW = ["prom_width_days", "prom_fraction", "prom_n_inv", "prom_n_broken_inv", "prom_age_days", "c_prom_lag"]
PROMISE_COLS = ("has_promise", "days_to_promised", "promise_overdue", "c_promise_rel", "c_promise_n")
SHRINK = 6.0


def add_features(S, world):
    prom = pd.read_parquet(SYNTH / world / "promises.parquet")
    inv = pd.read_parquet(SYNTH / world / "invoices.parquet", columns=["invoice_id", "paid_date_true"])
    for c in ("made_date", "promised_date", "promised_date_lo", "promised_date_hi"):
        prom[c] = pd.to_datetime(prom[c])
    prom = prom.merge(inv, on="invoice_id", how="left")
    S = S.copy().reset_index(drop=True)
    S["_row"] = np.arange(len(S))
    left = S[["_row", "invoice_id", "cutoff", "customer_id"]].sort_values("cutoff")
    # (1) lời hứa gần nhất có made_date <= T, kèm số lời hứa tích luỹ trên hoá đơn
    pm = prom.sort_values(["invoice_id", "made_date"]).copy()
    pm["n_so_far"] = pm.groupby("invoice_id").cumcount() + 1
    pm["width"] = (pm.promised_date_hi - pm.promised_date_lo).dt.days.astype(float)
    last = pd.merge_asof(left, pm.sort_values("made_date")[["invoice_id", "made_date", "width", "promised_fraction", "n_so_far"]],
                         left_on="cutoff", right_on="made_date", by="invoice_id", direction="backward")
    # (2) số lời hứa đã tới hạn xác minh và thất bại, tích luỹ theo ngày xác minh
    br = prom[~prom.kept.astype(bool)].copy()
    br["resolve"] = br.promised_date + pd.Timedelta(days=3)
    br = br.sort_values(["invoice_id", "resolve"])
    br["broken_so_far"] = br.groupby("invoice_id").cumcount() + 1
    brk = pd.merge_asof(left, br.sort_values("resolve")[["invoice_id", "resolve", "broken_so_far"]],
                        left_on="cutoff", right_on="resolve", by="invoice_id", direction="backward")
    # (3) độ lệch (ngày trả thật - ngày hứa) của khách, tích luỹ theo ngày trả thật (chỉ lời hứa đã có ngày trả <= T)
    lag = prom.dropna(subset=["paid_date_true"]).copy()
    lag = lag[lag.paid_date_true >= lag.made_date]
    lag["lag"] = (lag.paid_date_true - lag.promised_date).dt.days.astype(float).clip(-60, 120)
    lag = lag.sort_values(["customer_id", "paid_date_true"])
    lag["cum_lag"] = lag.groupby("customer_id").lag.cumsum()
    lag["cum_n"] = lag.groupby("customer_id").cumcount() + 1
    cl = pd.merge_asof(left, lag.sort_values("paid_date_true")[["customer_id", "paid_date_true", "cum_lag", "cum_n"]],
                       left_on="cutoff", right_on="paid_date_true", by="customer_id", direction="backward")
    feat = pd.DataFrame({"_row": last["_row"].to_numpy(),
                         "prom_width_days": last["width"].to_numpy(),
                         "prom_fraction": last["promised_fraction"].to_numpy(),
                         "prom_n_inv": last["n_so_far"].fillna(0).to_numpy(),
                         "prom_age_days": (last["cutoff"] - last["made_date"]).dt.days.to_numpy()})
    b = pd.DataFrame({"_row": brk["_row"].to_numpy(), "prom_n_broken_inv": brk["broken_so_far"].fillna(0).to_numpy()})
    c = pd.DataFrame({"_row": cl["_row"].to_numpy(),
                      "c_prom_lag": (cl["cum_lag"].fillna(0) / (cl["cum_n"].fillna(0) + SHRINK)).to_numpy()})
    feat = feat.merge(b, on="_row").merge(c, on="_row")
    S = S.merge(feat, on="_row", how="left").drop(columns="_row")
    has = S["has_promise"] == 1
    for col in ("prom_width_days", "prom_fraction", "prom_age_days"):
        S.loc[~has, col] = np.nan
    return S


def run(world):
    all_cut = pd.date_range("2019-07-01", O + pd.Timedelta(days=175), freq="7D")
    cut = [T for T in all_cut if T >= O or T.isocalendar().week % 2 == 0]
    S = R1.snapshots(world, cut, tag="weekly")
    S = add_features(S, world)
    tr = R1.censor(S[S["cutoff"] < O], O)
    tr = tr[tr["cutoff"].dt.isocalendar().week.astype(int) % 2 == 0]
    te = R1.censor(S[(S["cutoff"] >= O) & (S["cutoff"] < O + pd.Timedelta(days=182))], "2025-12-31")
    base = list(R1.FEATURES)
    models = {"B without promises": [f for f in base if f not in PROMISE_COLS],
              "A current promise features": base, "C current + 6 new": base + NEW}
    sub = (te["has_promise"] == 1).to_numpy()
    y = np.minimum(te.loc[sub, "remaining"].to_numpy(float), t1.CAP)
    groups = te.loc[sub, "firm_id"].astype(str).to_numpy()
    err = {}
    for name, feats in models.items():
        R1.log("G17 fit", world, name, len(tr))
        m = t1.HazardGBM(feats=feats).fit(tr)
        H = m.hazards(te)
        err[name] = np.abs(y - t1.quantiles_from_hazard(H[sub])[:, 1])
    rows = []
    imp = lambda b, x: 100 * (b.mean() - x.mean()) / b.mean()  # noqa: E731
    for name, e in err.items():
        lo, hi = M.bootstrap_ci(imp, err["B without promises"], e, n=300, seed=1, groups=groups)
        rows.append(dict(world=world, model=name, n_promised=int(sub.sum()), MAE_p50_promised_only=float(e.mean()),
                         improvement_vs_no_promises_pct=imp(err["B without promises"], e), ci_low=lo, ci_high=hi,
                         measurement_version=VERSION))
    out = pd.DataFrame(rows)
    print(out.round(3).to_string(index=False), flush=True)
    return out


def main():
    res = []
    for world in ("src", "src_noisy_promises"):
        res.append(run(world))
        (OUT / "sprint5").mkdir(exist_ok=True)
        pd.concat(res).to_csv(OUT / "sprint5" / "g17_promise_features.csv", index=False)


if __name__ == "__main__":
    main()
