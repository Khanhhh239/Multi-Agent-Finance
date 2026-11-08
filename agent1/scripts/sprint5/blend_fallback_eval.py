#!/usr/bin/env python3
"""Tiêu chí 1 (GO_NO_GO mục 4) + cổng thoái lui: luồng triển khai T1 trên thế giới đích chưa dùng để chọn.

Luồng (giống hệt khi triển khai cho một doanh nghiệp mới có 12 tháng lịch sử):
  1. DH-GBM học trên src trước O (kiểm duyệt tại O).
  2. Chọn w của BLEND = w·FT + (1−w)·B1d trên cửa sổ hiệu chỉnh [O−183, O−120] của CHÍNH doanh nghiệp,
     bằng mô hình tinh chỉnh chỉ trên dữ liệu trước cửa sổ đó (không nhìn sau O).
  3. Tinh chỉnh lại trên toàn bộ 12 tháng trước O; dự báo hoá đơn phát hành sau O, gốc cắt hằng tuần 52 tuần.
  4. Cổng thoái lui (agent1/eval/fallback_gate.py) mô phỏng theo từng công ty: mất mát của một dòng chỉ "lộ diện"
     ở tuần thanh toán thực tế (hoặc tuần CAP), cổng ở tuần t chỉ dùng mất mát đã lộ diện đến hết tuần t−1.
Đầu ra: outputs/sprint5/blend_fallback_<world>.csv và blend_fallback_summary.csv.

  python scripts/sprint5/blend_fallback_eval.py --worlds tgt2,hc_supply_shock,hc_retention
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "scripts" / "sprint1"))
from agent1.paths import OUT  # noqa: E402
from agent1.models import t1  # noqa: E402
from agent1.eval import metrics as M  # noqa: E402
from agent1.eval.fallback_gate import fallback_states  # noqa: E402
import run_t1 as R1  # noqa: E402
from run_real_v2 import per_row_pinball, blend, W_GRID  # noqa: E402

O = pd.Timestamp("2024-07-01")
VIS = O - pd.DateOffset(months=12)
VERSION = "blend-fallback-deploy-flow-v1"
RES = OUT / "sprint5"


def log(*a):
    print(pd.Timestamp.now().strftime("%H:%M:%S"), *a, flush=True)


def source_model():
    cut_src = pd.date_range("2019-07-01", O - pd.Timedelta(days=7), freq="14D")
    S = R1.censor(R1.snapshots("src", pd.date_range("2019-07-01", "2025-09-29", freq="7D"), tag="weekly")
                  .pipe(lambda d: d[d["cutoff"].isin(cut_src)]), O)
    log("src rows", len(S))
    return t1.HazardGBM().fit(S)


def fine_tune(m_src, rows):
    ft = t1.HazardGBM(dict(learning_rate=0.02), rounds=150)
    ft.fit(rows, init_model=m_src.booster)
    return ft


def realised_week(te):
    """Tuần (tính từ O) mà mất mát của dòng lộ diện: ngày thanh toán thật, chặn ở CAP."""
    days = np.minimum(te["remaining"].to_numpy(float), t1.CAP)
    when = te["cutoff"] + pd.to_timedelta(days, unit="D")
    return ((when - O).dt.days // 7).to_numpy()


def run_world(world, m_src):
    inv, _, _ = R1.load_world(world)
    end = inv["paid_date_true"].max().normalize()
    tr_cut = pd.date_range(VIS + pd.Timedelta(days=28), O - pd.Timedelta(days=7), freq="7D")
    Tt = R1.censor(R1.snapshots(world, tr_cut, visible_from=VIS, tag="adapt_M12"), O)
    cal_lo, cal_hi = O - pd.Timedelta(days=183), O - pd.Timedelta(days=120)
    sel = R1.censor(Tt[Tt.cutoff < cal_lo], cal_lo)
    cal = R1.censor(Tt[Tt.cutoff.between(cal_lo, cal_hi)], O)
    log(world, "adapt rows", len(Tt), "sel", len(sel), "cal", len(cal))
    # (a) chọn w trên cửa sổ hiệu chỉnh của chính doanh nghiệp
    Qc = t1.quantiles_from_hazard(fine_tune(m_src, sel).hazards(cal))
    Bc = t1.b1_dist(cal, None)
    yc = cal["remaining"].values
    cal_scores = {w: float(per_row_pinball(yc, blend(Qc, Bc, w)).mean()) for w in W_GRID}
    w = min(cal_scores, key=cal_scores.get)
    # (b) tinh chỉnh lại trên toàn bộ lịch sử trước O, kiểm tra sau O
    ft = fine_tune(m_src, Tt)
    test_cut = pd.date_range(O, O + pd.Timedelta(days=357), freq="7D")
    test_cut = test_cut[test_cut <= end - pd.Timedelta(days=int(t1.CAP))]
    te = R1.censor(R1.snapshots(world, test_cut, visible_from=VIS, tag="test_M12"), end)
    te = te[te.issue_date >= O].reset_index(drop=True)
    y = te["remaining"].values
    Q = {"B1d": t1.b1_dist(te, None), "FT DH-GBM": t1.quantiles_from_hazard(ft.hazards(te))}
    Q[f"BLEND w={w}"] = blend(Q["FT DH-GBM"], Q["B1d"], w)
    loss = {k: per_row_pinball(y, v) for k, v in Q.items()}
    # (c) cổng thoái lui theo công ty, theo tuần lộ diện
    wk = realised_week(te)
    gated = loss[f"BLEND w={w}"].copy()
    switched = []
    for fid in te.firm_id.unique():
        m = (te.firm_id == fid).to_numpy()
        frame = pd.DataFrame(dict(wk=wk[m], b=loss[f"BLEND w={w}"][m], r=loss["B1d"][m]))
        weekly = frame.groupby("wk")[["b", "r"]].mean()
        weeks = np.arange(weekly.index.min(), weekly.index.max() + 1)
        weekly = weekly.reindex(weeks)
        state = pd.Series(fallback_states(weekly.b.ffill().bfill(), weekly.r.ffill().bfill()), index=weeks)
        use_b1 = state.reindex(frame.wk).to_numpy()
        idx = np.nonzero(m)[0]
        gated[idx[use_b1]] = loss["B1d"][idx[use_b1]]
        switched.append(float(use_b1.mean()))
    loss["BLEND + fallback gate"] = gated
    groups = te["firm_id"].astype(str).values
    base = loss["B1d"]
    rows = []
    for name, l in loss.items():
        imp = lambda b, x: 100 * (b.mean() - x.mean()) / b.mean()  # noqa: E731
        lo, hi = M.bootstrap_ci(imp, base, l, n=300, seed=1, groups=groups)
        r = dict(world=world, model=name, w_selected=w, n=len(te), n_firms=te.firm_id.nunique(), pinball=float(l.mean()),
                 improvement_vs_B1d_pct=imp(base, l), improvement_ci_low=lo, improvement_ci_high=hi,
                 selected_on="own_pre_O_calibration_window", target_test_used_for_selection=False,
                 measurement_version=VERSION)
        if name in Q:
            r.update({k: v for k, v in t1.evaluate_quantiles(y, Q[name]).items() if k in ("cov80", "MAE_p50")})
        if name == "BLEND + fallback gate":
            r["share_rows_on_B1d"] = float(np.mean(switched))
        rows.append(r)
    out = pd.DataFrame(rows)
    out.to_csv(RES / f"blend_fallback_{world}.csv", index=False)
    log(world, "w", w, "cal", {k: round(v, 3) for k, v in cal_scores.items()})
    log("\n" + out[["model", "pinball", "improvement_vs_B1d_pct", "improvement_ci_low", "improvement_ci_high"]].round(3).to_string(index=False))
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--worlds", default="tgt2,hc_supply_shock,hc_retention")
    a = ap.parse_args()
    RES.mkdir(parents=True, exist_ok=True)
    m_src = source_model()
    allres = []
    for world in a.worlds.split(","):
        allres.append(run_world(world, m_src))
        pd.concat(allres).to_csv(RES / "blend_fallback_summary.csv", index=False)


if __name__ == "__main__":
    main()
