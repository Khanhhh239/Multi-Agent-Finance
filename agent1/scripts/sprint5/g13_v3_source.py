#!/usr/bin/env python3
"""G13 v3 — chỉ trên NGUỒN: đường biên phát hiện / báo giả khi thêm 'lấp khoảng trống' (fill) vào chính sách isotonic + xác nhận k.

Đọc outputs/g13/src_backtest (backtest T6 của src, đã có). Không đụng thế giới đích.
Đầu ra: outputs/g13/v3/source_grid.csv, source_frontier.csv
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1.paths import OUT, SYNTH  # noqa: E402
from agent1.eval.alert_policy import oof_calibrate, select_policy  # noqa: E402

MODEL = "MC-copula-t (T1+T4+T5)"
FILLS = (0, 1, 2, 3, 4, 6)
BUDGETS = (0.8, 0.5, 0.3, 0.2)
RES = OUT / "g13" / "v3"


def main():
    RES.mkdir(parents=True, exist_ok=True)
    src = pd.read_csv(OUT / "g13" / "src_backtest" / "t6_shortfall_predictions.csv", parse_dates=["cutoff"])
    s = src[src.model == MODEL].reset_index(drop=True)
    cash = pd.read_parquet(SYNTH / "src" / "daily_cash.parquet", columns=["firm_id", "date", "balance"])
    s = s.assign(q=oof_calibrate(s, "p13", "y13"))
    _, grid = select_policy(s, cash, "q", horizon_days=91, fa_budget=9, fills=FILLS)
    grid.to_csv(RES / "source_grid.csv", index=False)
    rows = []
    for fill in FILLS:
        g = grid[grid.fill == fill]
        for b in BUDGETS:
            ok = g[(g.false_alarms_per_firm_year <= b) & (g.n_events > 0)]
            if ok.empty:
                rows.append(dict(fill=fill, fa_budget=b, feasible=False)); continue
            r = ok.sort_values(["detected_at_least_4w", "median_lead_weeks"], ascending=False).iloc[0]
            rows.append(dict(fill=fill, fa_budget=b, feasible=True, tau=r.tau, k=int(r.k), detected=r.detected_at_least_4w,
                             lead_weeks=r.median_lead_weeks, fa=r.false_alarms_per_firm_year, n_events=int(r.n_events)))
    f = pd.DataFrame(rows)
    f.to_csv(RES / "source_frontier.csv", index=False)
    print(f.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
