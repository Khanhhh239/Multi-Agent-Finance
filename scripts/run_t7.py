#!/usr/bin/env python3
"""T7 — phát hiện điểm gãy cấp khách hàng (trực tuyến) trên thế giới tổng hợp có nhãn điểm gãy chèn sẵn.

Giao thức trung thực: tham số ngưỡng mỗi bộ phát hiện được CHỌN trên miền nguồn (src) với ràng buộc
báo động giả <= 0.5 / khách-năm (tối đa hoá tỷ lệ phát hiện), rồi ĐÁNH GIÁ nguyên trạng trên miền đích (tgt).
Chỉ tính khách có >= 5 lần trả trong 180 ngày sau điểm gãy (có đủ quan sát để phát hiện).
Báo động trong giai đoạn sốc vĩ mô (COVID, đóng băng tín dụng) báo cáo riêng: đó là thay đổi thật toàn thị trường."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH, OUT  # noqa: E402
from agent1.models.t7_changepoint import residual_stream, run_detector, GRIDS  # noqa: E402

RES = OUT / "t7"
RES.mkdir(parents=True, exist_ok=True)
FA_TARGET = 0.5


def streams(world, method):
    d = SYNTH / world
    inv = pd.read_parquet(d / "invoices.parquet")
    ev = pd.read_parquet(d / "events.parquet")
    macro = pd.read_parquet(d / "macro.parquet")
    stress = set(macro.loc[(macro["covid_stress"] > 0.25) | (macro["credit_crunch"] > 0.3), "week"])
    inv = inv[inv["paid_date_true"].notna() & (inv["term_days"] > 0)].sort_values("paid_date_true")
    brk = ev[ev["type"] == "customer_delay_shift"].set_index("customer_id")["date"]
    out = []
    for cid, g in inv.groupby("customer_id"):
        if len(g) < 15:
            continue
        dates = pd.DatetimeIndex(g["paid_date_true"].values)
        z, raw = residual_stream(g["days_late_true"].values.astype(float), method=method)
        b = brk.get(cid, pd.NaT)
        n_after = int(((dates >= b) & (dates <= b + pd.Timedelta(days=180))).sum()) if pd.notna(b) else 0
        in_stress = np.array([(x - pd.Timedelta(days=x.weekday())).normalize() in stress for x in dates])
        out.append(dict(cid=cid, z=z, raw=raw, dates=dates, brk=b, n_after=n_after, stress=in_stress))
    return out


def evaluate(S, name, kw):
    det, lags, fa, fy, macro = [], [], 0, 0.0, 0
    for s in S:
        al = run_detector(name, s["z"], s["raw"], **kw)
        al_d = s["dates"][al] if len(al) else pd.DatetimeIndex([])
        st = s["stress"][al] if len(al) else np.array([], bool)
        macro += int(st.sum())
        other = al_d[~st] if len(al) else al_d
        b = s["brk"]
        if pd.notna(b):
            span = max((b - s["dates"][0]).days / 365, 0.1)
            fa += int((other < b).sum())
            fy += span
            if s["n_after"] >= 5:
                post = al_d[(al_d >= b) & (al_d <= b + pd.Timedelta(days=180))]
                det.append(len(post) > 0)
                if len(post):
                    lags.append((post[0] - b).days)
        else:
            fa += len(other)
            fy += max((s["dates"][-1] - s["dates"][0]).days / 365, 0.1)
    return dict(detection_rate_180d=float(np.mean(det)) if det else np.nan, median_lag_days=float(np.median(lags)) if lags else np.nan,
                false_alarms_per_cust_year=fa / fy, macro_alarms_per_cust_year=macro / fy, n_eligible_shifted=len(det))


def main():
    rows = []
    for method in ("pit", "mad"):
        Ssrc = streams("src", method)
        Stgt = streams("tgt", method) + streams("sens_uk", method) + streams("sens_coface", method)
        for name, grid in GRIDS.items():
            if method == "mad" and name != "CUSUM":
                continue
            best, best_r = None, None
            for kw in grid:
                r = evaluate(Ssrc, name, kw)
                ok = r["false_alarms_per_cust_year"] <= FA_TARGET
                if ok and (best_r is None or r["detection_rate_180d"] > best_r["detection_rate_180d"]):
                    best, best_r = kw, r
            if best is None:
                continue
            rt = evaluate(Stgt, name, best)
            label = f"{name} [{method}]"
            rows.append(dict(detector=label, params=str(best), world="src (tuned)", **best_r))
            rows.append(dict(detector=label, params=str(best), world="held-out (tgt+sens_uk+sens_coface)", **rt))
            print(rows[-2], "\n", rows[-1], flush=True)
    out = pd.DataFrame(rows)
    print(out.round(3).to_string(), flush=True)
    out.to_csv(RES / "t7_changepoint.csv", index=False)


if __name__ == "__main__":
    main()
