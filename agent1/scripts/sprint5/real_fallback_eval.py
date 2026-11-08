#!/usr/bin/env python3
"""Cổng thoái lui trên dữ liệu AR THẬT (Customer Invoices, BPI 2019) — nơi mô hình thuần có thể thua B1d.

Dùng lại đúng giao thức v2 (`scripts/sprint1/run_real_v2.py`): cùng snapshot, cùng mốc O, cùng tập huấn luyện cuối,
và trọng số w đã chọn trên cửa sổ hiệu chỉnh (`outputs/t1/real_v2/<name>_choice.json`). Không chọn lại gì trên test.
Cổng (`agent1/eval/fallback_gate.py`) chạy theo từng công ty; mất mát một dòng lộ diện ở tuần thanh toán thật
(chặn CAP); quyết định tuần t chỉ dùng mất mát đã lộ diện đến hết t−1.

  python scripts/sprint5/real_fallback_eval.py --data ci,bpi
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "scripts" / "sprint1"))
from agent1.models import t1  # noqa: E402
from agent1.eval import metrics as M  # noqa: E402
from agent1.eval.fallback_gate import fallback_states  # noqa: E402
import run_t1 as R1  # noqa: E402
from run_real_v2 import CFG, cap_rows, per_row_pinball, blend, log, OUT as V2  # noqa: E402

RES = ROOT / "outputs" / "sprint5"
VERSION = "real-fallback-gate-v1"


def gate(te, loss_model, loss_base):
    """Mất mát sau cổng + tỷ lệ dòng dùng B1d. Theo công ty, theo tuần lộ diện."""
    days = np.minimum(te["remaining"].to_numpy(float), t1.CAP)
    when = te["cutoff"] + pd.to_timedelta(days, unit="D")
    wk = ((when - when.min()).dt.days // 7).to_numpy()
    out = loss_model.copy()
    use = np.zeros(len(te), bool)
    for fid in te.firm_id.unique():
        m = (te.firm_id == fid).to_numpy()
        weekly = pd.DataFrame(dict(wk=wk[m], b=loss_model[m], r=loss_base[m])).groupby("wk")[["b", "r"]].mean()
        weeks = np.arange(weekly.index.min(), weekly.index.max() + 1)
        weekly = weekly.reindex(weeks).ffill()
        state = pd.Series(fallback_states(weekly.b, weekly.r), index=weeks)
        u = state.reindex(wk[m]).to_numpy()
        idx = np.nonzero(m)[0]
        use[idx[u]] = True
    out[use] = loss_base[use]
    return out, float(use.mean())


def run(name):
    loader, snap, O, test_days = CFG[name]
    inv = loader()
    end = inv["paid_date_true"].max()
    S = pd.read_parquet(ROOT / "data/processed" / snap)
    f64 = S.select_dtypes("float64").columns
    S[f64] = S[f64].astype("float32")
    O = min(pd.Timestamp(O), end - pd.Timedelta(days=int(t1.CAP) + test_days))
    te = R1.censor(S[S.cutoff >= O], end)
    te = te[te.cutoff <= end - pd.Timedelta(days=int(t1.CAP))].reset_index(drop=True)
    tr_final = cap_rows(R1.censor(S[S.cutoff < O], O))
    del S
    w = json.loads((V2 / f"{name}_choice.json").read_text(encoding="utf-8"))["DH-GBM"]["w"]
    log(name, "train", len(tr_final), "test", len(te), "w(from v2 calibration)", w)
    m = t1.HazardGBM(dict(min_data_in_leaf=100)).fit(tr_final)
    del tr_final
    Qm = np.vstack([t1.quantiles_from_hazard(m.hazards(te.iloc[i:i + 40_000])) for i in range(0, len(te), 40_000)])
    Qb = t1.b1_dist(te, None)
    y = te["remaining"].values
    loss = {"B1d": per_row_pinball(y, Qb), "DH-GBM": per_row_pinball(y, Qm),
            f"BLEND w={w}": per_row_pinball(y, blend(Qm, Qb, w))}
    share = {}
    loss["DH-GBM + fallback gate"], share["DH-GBM + fallback gate"] = gate(te, loss["DH-GBM"], loss["B1d"])
    loss[f"BLEND w={w} + fallback gate"], share[f"BLEND w={w} + fallback gate"] = gate(te, loss[f"BLEND w={w}"], loss["B1d"])
    groups = te["customer_id"].astype(str).values
    imp = lambda b, x: 100 * (b.mean() - x.mean()) / b.mean()  # noqa: E731
    rows = []
    for k, l in loss.items():
        lo, hi = M.bootstrap_ci(imp, loss["B1d"], l, n=300, seed=1, groups=groups)
        rows.append(dict(setting=name, model=k, n=len(te), n_firms=te.firm_id.nunique(), pinball=float(l.mean()),
                         improvement_vs_B1d_pct=imp(loss["B1d"], l), improvement_ci_low=lo, improvement_ci_high=hi,
                         share_rows_on_B1d=share.get(k, np.nan), w_from_v2_calibration=w,
                         bootstrap_groups="customer_id", measurement_version=VERSION))
    out = pd.DataFrame(rows)
    log("\n" + out[["model", "pinball", "improvement_vs_B1d_pct", "improvement_ci_low", "improvement_ci_high",
                    "share_rows_on_B1d"]].round(3).to_string(index=False))
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--data", default="ci,bpi"); a = ap.parse_args()
    RES.mkdir(parents=True, exist_ok=True)
    res = []
    for name in a.data.split(","):
        res.append(run(name))
        pd.concat(res).to_csv(RES / "real_fallback_gate.csv", index=False)


if __name__ == "__main__":
    main()
