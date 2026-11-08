#!/usr/bin/env python3
"""Phép tính ROI trước/sau cho SME mẫu (docs/03_Evaluation/06). Mọi tham số GIẢ ĐỊNH nằm ở đầu file; chạy để in bảng."""
import json

BASE = dict(
    revenue=40e9, credit_share=0.65, margin=0.045, lateness_days_overdue=30, overdue_share=0.39,
    bad_debt_share=0.03, buffer_days=27, cost_of_funds=0.09,
    episodes_per_year=2, episode_cost=17.5e6, emerg_to_planned=0.25, tail_prob=0.03, tail_cost=300e6,
    recon_hours_month=30, forecast_hours_week=4, hourly=80_000,
)
SCEN = {
    "thap":  dict(buffer_cut=0.10, late_days_cut=1, catch=0.40, episodes=1, tail_cut=0.0, bad_cut=0.05, recon_auto=0.40, fc_auto=0.50, tail_prob=0.03),
    "co_so": dict(buffer_cut=0.20, late_days_cut=2, catch=0.70, episodes=2, tail_cut=0.5, bad_cut=0.10, recon_auto=0.60, fc_auto=0.70, tail_prob=0.03),
    "cao":   dict(buffer_cut=0.30, late_days_cut=3, catch=0.80, episodes=3, tail_cut=0.7, bad_cut=0.20, recon_auto=0.80, fc_auto=0.80, tail_prob=0.05),
}


def run(b, s):
    credit = b["revenue"] * b["credit_share"]
    per_day = credit / 365
    late_avg = b["overdue_share"] * b["lateness_days_overdue"]
    costs = b["revenue"] * (1 - b["margin"])
    out_day = costs / 365
    buffer = b["buffer_days"] * out_day
    r = {"credit_sales": credit, "per_day": per_day, "late_avg_days": late_avg, "wc_held": per_day * late_avg,
         "outflow_day": out_day, "buffer": buffer, "bad_debt": credit * b["bad_debt_share"]}
    r["B1_buffer_release"] = buffer * s["buffer_cut"] * b["cost_of_funds"]
    r["B2_dso"] = per_day * s["late_days_cut"] * b["cost_of_funds"]
    ep = s["episodes"] * b["episode_cost"]
    r["B3a_episodes"] = ep * s["catch"] * (1 - b["emerg_to_planned"])
    r["B3b_tail"] = s["tail_prob"] * b["tail_cost"] * s["tail_cut"]
    r["B4_bad_debt"] = r["bad_debt"] * s["bad_cut"]
    hrs_before = b["recon_hours_month"] * 12 + b["forecast_hours_week"] * 52
    saved = b["recon_hours_month"] * 12 * s["recon_auto"] + b["forecast_hours_week"] * 52 * s["fc_auto"]
    r["hours_before"], r["hours_saved"] = hrs_before, saved
    r["B5_labour"] = saved * b["hourly"]
    keys = ["B1_buffer_release", "B2_dso", "B3a_episodes", "B3b_tail", "B4_bad_debt", "B5_labour"]
    r["total"] = sum(r[k] for k in keys)
    return r


if __name__ == "__main__":
    out = {k: run(BASE, s) for k, s in SCEN.items()}
    for k, r in out.items():
        print(k, {a: round(v / 1e6, 1) if abs(v) > 1e5 else round(v, 2) for a, v in r.items()})
    price = {"Starter": 9e6, "Growth": 18e6}
    for k, r in out.items():
        print(k, "BCR Growth", round(r["total"] / price["Growth"], 1), "net", round((r["total"] - price["Growth"]) / 1e6, 1))
    # độ nhạy một chiều quanh kịch bản cơ sở
    base = run(BASE, SCEN["co_so"])["total"]
    print("base", round(base / 1e6, 1))
    for name, lo, hi in [("buffer_cut", .1, .3), ("late_days_cut", 1, 3), ("bad_cut", .05, .2), ("catch", .4, .8), ("episodes", 1, 3)]:
        a = run(BASE, {**SCEN["co_so"], name: lo})["total"]; c = run(BASE, {**SCEN["co_so"], name: hi})["total"]
        print("sens", name, round(a / 1e6, 1), round(c / 1e6, 1), "swing", round((c - a) / 1e6, 1))
    for name, lo, hi in [("cost_of_funds", .06, .14), ("credit_share", .5, .75), ("bad_debt_share", .02, .04)]:
        a = run({**BASE, name: lo}, SCEN["co_so"])["total"]; c = run({**BASE, name: hi}, SCEN["co_so"])["total"]
        print("sens", name, round(a / 1e6, 1), round(c / 1e6, 1), "swing", round((c - a) / 1e6, 1))
    json.dump(out, open("outputs/roi_scenarios.json", "w"), indent=1)
