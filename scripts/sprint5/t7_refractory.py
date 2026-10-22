#!/usr/bin/env python3
"""G14 — bộ phát hiện đổi hành vi với KHOẢNG NGHỈ sau báo động (một đợt cảnh báo = một sự kiện).

  python scripts/sprint5/t7_refractory.py --source-only   # lưới trên src, KHÔNG đụng thế giới đích
  python scripts/sprint5/t7_refractory.py --measure       # đọc choice.json đã đóng băng, đo trên thế giới đích (một lần)

Đăng ký trước: docs/03_Evaluation/G14_T7_PREREG.md. Dùng lại `streams`, `run_detector`, `GRIDS` của T7 (không sửa chúng).
Đầu ra: outputs/t7/sprint5/{source_grid.csv, choice.json, target_metrics.csv}
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from agent1.paths import OUT  # noqa: E402
from agent1.models.t7_changepoint import run_detector, GRIDS  # noqa: E402
from run_t7 import streams  # noqa: E402

RES = OUT / "t7" / "sprint5"
VERSION = "changepoint-refractory-v1"
REFRACTORY = (0, 30, 60, 90, 120, 180)
DETECTORS = ("CUSUM", "Page-Hinkley")
FA_TARGET = 0.5
FA_MARGIN = 0.35          # đăng ký trước: chọn trên nguồn với báo giả <= 0,35 (chừa biên chuyển miền)
MIN_AFTER = 5


def thin(dates, alarms, refractory):
    """Giữ báo động đầu tiên của mỗi đợt: bỏ báo động cách báo động đã giữ < `refractory` ngày."""
    kept, last = [], None
    for a in alarms:
        d = dates[a]
        if last is None or (d - last).days >= refractory:
            kept.append(a); last = d
    return kept


def evaluate(S, name, kw, refractory):
    det, lags, fa, fy, macro = [], [], 0, 0.0, 0
    for s in S:
        al = thin(s["dates"], run_detector(name, s["z"], s["raw"], **kw), refractory)
        al_d = s["dates"][al] if len(al) else pd.DatetimeIndex([])
        st = s["stress"][al] if len(al) else np.array([], bool)
        macro += int(st.sum())
        other = al_d[~st] if len(al) else al_d
        b = s["brk"]
        if pd.notna(b):
            fa += int((other < b).sum()); fy += max((b - s["dates"][0]).days / 365, 0.1)
            if s["n_after"] >= MIN_AFTER:
                post = al_d[(al_d >= b) & (al_d <= b + pd.Timedelta(days=180))]
                det.append(len(post) > 0)
                if len(post):
                    lags.append((post[0] - b).days)
        else:
            fa += len(other); fy += max((s["dates"][-1] - s["dates"][0]).days / 365, 0.1)
    return dict(detection_rate_180d=float(np.mean(det)) if det else np.nan,
                median_lag_days=float(np.median(lags)) if lags else np.nan,
                false_alarms_per_cust_year=fa / fy, macro_alarms_per_cust_year=macro / fy, n_eligible_shifted=len(det))


def source_grid():
    S = streams("src", "pit")
    rows = []
    for name in DETECTORS:
        for kw in GRIDS[name]:
            for R in REFRACTORY:
                r = evaluate(S, name, kw, R)
                rows.append(dict(detector=name, params=json.dumps(kw), refractory_days=R, **r))
        print(name, "done", flush=True)
        pd.DataFrame(rows).to_csv(RES / "source_grid.csv", index=False)
    return pd.DataFrame(rows)


def choose(grid, fa_cap):
    ok = grid[grid.false_alarms_per_cust_year <= fa_cap]
    return None if ok.empty else ok.sort_values(["detection_rate_180d", "median_lag_days"], ascending=[False, True]).iloc[0]


def measure():
    choice = json.loads((RES / "choice.json").read_text(encoding="utf-8"))
    worlds = [w for w in choice["worlds"] if (ROOT / "data/synthetic" / w / "events.parquet").exists()]
    rows = []
    for label, group in choice["groups"].items():
        S = sum((streams(w, "pit") for w in group if w in worlds), [])
        if not S:
            continue
        for tag, c in (("baseline (refractory 0, FA<=0.5 on src)", choice["baseline"]), ("chosen", choice["chosen"])):
            r = evaluate(S, c["detector"], json.loads(c["params"]), int(c["refractory_days"]))
            rows.append(dict(group=label, worlds="+".join(group), variant=tag, detector=c["detector"], params=c["params"],
                             refractory_days=c["refractory_days"], selected_on="src", target_used=False,
                             measurement_version=VERSION, **r))
            print(label, tag, {k: round(v, 3) for k, v in r.items() if isinstance(v, float)}, flush=True)
            pd.DataFrame(rows).to_csv(RES / "target_metrics.csv", index=False)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--source-only", action="store_true"); ap.add_argument("--measure", action="store_true")
    a = ap.parse_args()
    RES.mkdir(parents=True, exist_ok=True)
    if a.source_only:
        g = source_grid()
        base = choose(g[g.refractory_days == 0], FA_TARGET)
        pick = choose(g, FA_MARGIN)
        print("\nBASELINE (R=0, FA<=0.5):", None if base is None else base.to_dict())
        print("CHOSEN  (any R, FA<=%.2f):" % FA_MARGIN, None if pick is None else pick.to_dict())
        if pick is not None and base is not None:
            keys = ("detector", "params", "refractory_days")
            choice = dict(baseline={k: (base[k].item() if hasattr(base[k], "item") else base[k]) for k in keys},
                          chosen={k: (pick[k].item() if hasattr(pick[k], "item") else pick[k]) for k in keys},
                          source_baseline=base.to_dict(), source_chosen=pick.to_dict(), fa_margin=FA_MARGIN,
                          groups=dict(old_heldout=["tgt", "sens_uk", "sens_coface"], new_tgt2_tgt3=["tgt2", "tgt3"]),
                          worlds=["tgt", "sens_uk", "sens_coface", "tgt2", "tgt3"])
            (RES / "choice_candidate.json").write_text(json.dumps(choice, indent=2, default=float), encoding="utf-8")
    if a.measure:
        measure()


if __name__ == "__main__":
    main()
