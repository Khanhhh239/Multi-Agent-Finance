#!/usr/bin/env python3
"""T6 (+T5, T10) — dự báo số dư tiền 13 tuần cho các công ty miền ĐÍCH (tgt), onboard 2024-07-01 với 12 tháng lịch sử.

Phương pháp chính: MC-copula-t (T1 fine-tune src->tgt + T4 + T5) + ACI.
Đối chứng: MC độc lập (rho=0), MC với ngày trả điểm B1, LightGBM phân vị trực tiếp trên dòng tiền ròng
(học trên src), naive (chi biết trước + thu trung bình 13 tuần + phần dư thực nghiệm).
Chỉ số: độ phủ 80%, interval score, pinball, sai số P50 (chuẩn hoá theo chi tuần), Brier/AUC xác suất thiếu hụt,
thời gian báo trước. Kèm demo T10: dải P10/P50/P90, hoá đơn nên đòi trước (lý do SHAP), kịch bản "nếu như".
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent1.paths import SYNTH, OUT  # noqa: E402
from agent1.threads import NT  # noqa: E402
from agent1.models import t1, t4_revenue as T4  # noqa: E402
from agent1.models.t6_cash import simulate, collection_kernel, ACI, K  # noqa: E402
from agent1.models.features import FEATURES  # noqa: E402
from agent1.eval import metrics as M  # noqa: E402
import run_t1 as R1  # noqa: E402
from run_t4 import synth_series  # noqa: E402

RES = OUT / "t6"
RES.mkdir(parents=True, exist_ok=True)
O = pd.Timestamp("2024-07-01")
VIS = O - pd.DateOffset(months=12)
KNOWN = {"payroll_net", "social_insurance", "rent", "loan_service", "vat", "cit_provisional", "license_fee",
         "tet_bonus", "utilities"}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def weekly(series_daily, T, k_weeks=K):
    """Tổng theo tuần (T+7(k-1), T+7k]; snapshot và B0 đều biết tới hết ngày T."""
    out = np.zeros(k_weeks)
    for k in range(k_weeks):
        a, b = T + pd.Timedelta(days=7 * k), T + pd.Timedelta(days=7 * (k + 1))
        out[k] = series_daily[(series_daily.index > a) & (series_daily.index <= b)].sum()
    return out


def firm_context(world, fid, inv, out, daily):
    o = out[out["firm_id"] == fid]
    known = o[o["category"].isin(KNOWN)].groupby("date")["amount"].sum()
    sup = o[o["category"] == "supplier"].groupby("date")["amount"].sum()
    capex = o[o["category"] == "capex"]
    d = daily[daily["firm_id"] == fid].set_index("date")
    net = d["inflow_ar"] + d["inflow_other"] - d["outflow"] - d['owner_draw']
    return dict(known=known, sup=sup, capex=capex, net=net, bal=d["balance"], inv=inv[inv["firm_id"] == fid], outflows=o)


def known_outflows(ctx, T):
    ko = weekly(ctx["known"], T)
    sup_hist = ctx["sup"][(ctx["sup"].index < T) & (ctx["sup"].index >= T - pd.Timedelta(days=91))].sum() / 13
    # Bộ cũ thiếu incurred_date: không thể lấy chi NCC tương lai làm thông tin đã biết.
    sup = np.full(K, sup_hist)
    observed = ctx.get('outflows')
    if observed is not None and 'known_at' in observed:
        known_sup = observed[(observed.category == 'supplier') & (observed.known_at <= T)].groupby('date').amount.sum()
        sup[:4] = weekly(known_sup, T)[:4]
    return ko + sup


def truth_path(ctx, T):
    B0 = float(ctx["bal"][ctx["bal"].index <= T].iloc[-1])
    return B0, B0 + np.cumsum(weekly(ctx["net"], T))


def direct_features(ctx, snap_f, T, ko):
    scale = max(ctx["known"][(ctx["known"].index < T) & (ctx["known"].index >= T - pd.Timedelta(days=91))].sum() / 13
                + ctx["sup"][(ctx["sup"].index < T) & (ctx["sup"].index >= T - pd.Timedelta(days=91))].sum() / 13, 1.0)
    inflow13 = ctx["net"][(ctx["net"].index < T) & (ctx["net"].index >= T - pd.Timedelta(days=91))]
    a = snap_f["amount_open"].values if len(snap_f) else np.array([])
    dtd = snap_f["days_to_due"].values if len(snap_f) else np.array([])
    buckets = [(-1e9, 0), (1, 7), (8, 14), (15, 28), (29, 56), (57, 1e9)]
    ar = [a[(dtd >= lo) & (dtd <= hi)].sum() / scale for lo, hi in buckets]
    in4 = (ctx["inv"]["amount_gross"][(ctx["inv"]["paid_date_true"] < T) & (ctx["inv"]["paid_date_true"] >= T - pd.Timedelta(days=28))].sum()) / 4 / scale
    in13 = (ctx["inv"]["amount_gross"][(ctx["inv"]["paid_date_true"] < T) & (ctx["inv"]["paid_date_true"] >= T - pd.Timedelta(days=91))].sum()) / 13 / scale
    rows = []
    cko = np.cumsum(ko) / scale
    for k in range(K):
        rows.append(ar + [in4, in13, cko[k], k + 1, T.month, inflow13.sum() / scale / 13])
    return np.array(rows, dtype="float32"), scale


def rev_quantiles(model, ser, T):
    s = ser[ser.index < T]
    if len(s) < 30:
        return None
    weeks = pd.date_range(s.index[0], periods=len(s) + K, freq="7D")
    X, _, meta = T4.make_rows(s.values.astype(float), weeks, True, [len(s) - 1], with_target=False)
    if not len(X):
        return None
    return model.predict(X) * meta[:, 2:3]


def main():
    inv_s = pd.read_parquet(SYNTH / "src" / "invoices.parquet")
    inv_t = pd.read_parquet(SYNTH / "tgt" / "invoices.parquet")
    out_s, out_t = (pd.read_parquet(SYNTH / w / "outflows.parquet") for w in ("src", "tgt"))
    day_s, day_t = (pd.read_parquet(SYNTH / w / "daily_cash.parquet") for w in ("src", "tgt"))
    # ---------------- T1: src -> fine-tune tgt (12 tháng)
    Ssrc = R1.snapshots("src", pd.date_range("2019-07-01", "2025-09-29", freq="7D"), tag="weekly")
    tr = R1.censor(Ssrc[Ssrc["cutoff"].isin(pd.date_range("2019-07-01", O - pd.Timedelta(days=7), freq="14D"))], O)
    log("T1 src fit", len(tr))
    m_src = t1.HazardGBM().fit(tr)
    Tt = R1.censor(R1.snapshots("tgt", pd.date_range(VIS + pd.Timedelta(days=28), O - pd.Timedelta(days=7), freq="7D"),
                                visible_from=VIS, tag="adapt_M12"), O)
    m_ft = t1.HazardGBM(dict(learning_rate=0.02), rounds=150)
    m_ft.fit(Tt, init_model=m_src.booster)
    test_cut = pd.date_range(O, O + pd.Timedelta(days=357), freq="7D")
    Ste = R1.snapshots("tgt", test_cut, visible_from=VIS, tag="test_M12")
    Ste = Ste.assign(amount_open=Ste["amount_open"].fillna(Ste["amount_gross"]))
    log("predict hazards", len(Ste))
    H = m_ft.hazards(Ste)
    P_all, _ = t1.pmf_from_hazard(H)
    b1w = np.clip(np.ceil(t1.b1_predict(Ste) / 7).astype(int) - 1, 0, K)      # tuần trả theo B1 (K = ngoài)
    P_b1 = np.zeros_like(P_all)
    inside = b1w < K
    P_b1[np.nonzero(inside)[0], b1w[inside]] = 1.0
    # ---------------- T4
    ss = synth_series("src")
    from run_t4 import build
    Xr, Yr, _, _ = build(ss, True, lambda n: list(range(20, n - 13 - 13 - 70)))
    m4 = T4.GlobalQuantileLGBM().fit(Xr, Yr)
    st = synth_series("tgt")
    # ---------------- Direct LGBM-Q trên src
    log("direct model on src")
    Sdir = Ssrc[Ssrc["cutoff"].isin(pd.date_range("2020-01-06", O - pd.Timedelta(days=7 * 14), freq="28D"))]
    Sdir = Sdir.assign(amount_open=Sdir["amount_open"].fillna(Sdir["amount_gross"]))
    Xd, Yd = [], []
    for fid in inv_s["firm_id"].unique():
        ctx = firm_context("src", fid, inv_s, out_s, day_s)
        for T in sorted(Sdir["cutoff"].unique()):
            T = pd.Timestamp(T)
            if T - pd.Timedelta(days=91) < ctx["bal"].index.min():
                continue
            ko = known_outflows(ctx, T)
            X, scale = direct_features(ctx, Sdir[(Sdir["firm_id"] == fid) & (Sdir["cutoff"] == T)], T, ko)
            B0, tp = truth_path(ctx, T)
            Xd.append(X)
            Yd.append((tp - B0) / scale)
    Xd, Yd = np.vstack(Xd), np.concatenate(Yd)
    md = {q: lgb.train(dict(objective="quantile", alpha=q, learning_rate=0.05, num_leaves=31, min_data_in_leaf=50,
                            verbose=-1, num_threads=NT), lgb.Dataset(Xd, Yd), 400) for q in (0.1, 0.5, 0.9)}
    # ---------------- chọn rho trên src (cửa sổ trước O) bằng interval score
    log("tune rho on src")
    rho_grid = (0.0, 0.1, 0.2, 0.35, 0.5)
    tune_cut = pd.date_range(O - pd.Timedelta(days=7 * 30), O - pd.Timedelta(days=7 * 14), freq="14D")
    Stune = Ssrc[Ssrc["cutoff"].isin(tune_cut)]
    Stune = Stune.assign(amount_open=Stune["amount_open"].fillna(Stune["amount_gross"]))
    Ht = m_src.hazards(Stune)
    Pt, _ = t1.pmf_from_hazard(Ht)
    score_rho = {r: [] for r in rho_grid}
    for fid in inv_s["firm_id"].unique()[:16]:
        ctx = firm_context("src", fid, inv_s, out_s, day_s)
        for T in tune_cut:
            msk = ((Stune["firm_id"] == fid) & (Stune["cutoff"] == T)).values
            B0, tp = truth_path(ctx, T)
            ko = known_outflows(ctx, T)
            rq = rev_quantiles(m4, ss[f"src:{fid}"], T)
            ker = collection_kernel(ctx["inv"][ctx["inv"]["issue_date"] < T], T)
            for r in rho_grid:
                bal, _ = simulate(Stune[msk], Pt[msk], B0, ko, rq, ker, 0.0, [], n=400, rho=r, seed=1)
                lo, hi = np.quantile(bal, .1, axis=0), np.quantile(bal, .9, axis=0)
                sc = max(ko.mean(), 1.0)
                score_rho[r].append(M.interval_score(tp / sc, lo / sc, hi / sc))
    rho = min(score_rho, key=lambda r: np.mean(score_rho[r]))
    log("rho scores", {r: round(float(np.mean(v)), 3) for r, v in score_rho.items()}, "-> rho", rho)
    # ---------------- vòng test trên tgt
    aci = ACI()
    pending = []
    rows = []
    shortfall_rows = []
    demo = None
    for T in test_cut:
        for fid in inv_t["firm_id"].unique():
            ctx = firm_context("tgt", fid, inv_t, out_t, day_t)
            msk = ((Ste["firm_id"] == fid) & (Ste["cutoff"] == T)).values
            snap = Ste[msk]
            B0, tp = truth_path(ctx, T)
            ko = known_outflows(ctx, T)
            rq = rev_quantiles(m4, st[f"tgt:{fid}"], T)
            hist = ctx["inv"][(ctx["inv"]["issue_date"] < T) & (ctx["inv"]["issue_date"] >= VIS)]
            ker = collection_kernel(hist, T)
            cap_h = ctx["capex"][(ctx["capex"]["date"] < T) & (ctx["capex"]["date"] >= VIS)]
            cap_rate = len(cap_h) / max((T - VIS).days / 7, 1)
            cap_sz = cap_h["amount"].values
            sc = max(ko.mean(), 1.0)
            res = {}
            bal, _ = simulate(snap, P_all[msk], B0, ko, rq, ker, cap_rate, cap_sz, n=1000, rho=rho, seed=int(T.value % 1e6))
            res["MC-copula-t (T1+T4+T5)"] = bal
            res["MC-independent (rho=0)"] = simulate(snap, P_all[msk], B0, ko, rq, ker, cap_rate, cap_sz, n=1000, rho=0.0, seed=2)[0]
            res["MC with B1 point dates"] = simulate(snap, P_b1[msk], B0, ko, rq, ker, cap_rate, cap_sz, n=1000, rho=0.0, seed=3)[0]
            Xq, scale_d = direct_features(ctx, snap, T, ko)
            Qd = np.sort(np.column_stack([md[q].predict(Xq) for q in (0.1, 0.5, 0.9)]), axis=1) * scale_d + B0
            # naive: chi biết trước + thu trung bình 13 tuần; phần dư từ lịch sử nhìn thấy của chính công ty
            inn = ctx["net"]
            in13 = (inn[(inn.index < T) & (inn.index >= T - pd.Timedelta(days=91))] + 0).sum()
            out13 = ko.mean()
            avg_in = (in13 / 13) + out13
            pt_naive = B0 + np.cumsum(avg_in - ko)
            resid = []
            for Tb in pd.date_range(VIS + pd.Timedelta(days=91), T - pd.Timedelta(days=7 * K), freq="14D"):
                B0b, tpb = truth_path(ctx, Tb)
                kob = known_outflows(ctx, Tb)
                in13b = inn[(inn.index < Tb) & (inn.index >= Tb - pd.Timedelta(days=91))].sum()
                resid.append(tpb - (B0b + np.cumsum(in13b / 13 + kob.mean() - kob)))
            resid = np.array(resid) if resid else np.zeros((1, K))
            Qn = np.column_stack([pt_naive + np.quantile(resid, q, axis=0) for q in (0.1, 0.5, 0.9)])
            quant = {"Direct LGBM-Q (src)": Qd, "Naive (known out + avg in)": Qn}
            # ---- ACI: cập nhật bằng các dự báo đã lộ diện (trễ k tuần)
            for (Tp, k, lo_a, hi_a, y) in [p for p in pending if p[0] + pd.Timedelta(days=7 * (p[1] + 1)) <= T]:
                aci.update(k, not (lo_a <= y <= hi_a))
            pending = [p for p in pending if p[0] + pd.Timedelta(days=7 * (p[1] + 1)) > T]
            Qaci = np.zeros((K, 3))
            for k in range(K):
                lo, hi = aci.interval(bal[:, k], k)
                Qaci[k] = (lo, np.median(bal[:, k]), hi)
                pending.append((T, k, lo, hi, tp[k]))
            quant["MC-copula-t + ACI"] = Qaci
            for n_, S in res.items():
                quant[n_] = np.column_stack([np.quantile(S, q, axis=0) for q in (0.1, 0.5, 0.9)])
            for n_, Q in quant.items():
                for k in range(K):
                    rows.append(dict(model=n_, firm_id=fid, cutoff=T, k=k + 1, y=tp[k] / sc, lo=Q[k, 0] / sc,
                                     med=Q[k, 1] / sc, hi=Q[k, 2] / sc))
            # ---- xác suất thiếu hụt trong 4 và 13 tuần
            ev4, ev13 = float(tp[:4].min() < 0), float(tp.min() < 0)
            for n_, S in res.items():
                mn = np.minimum.accumulate(S, axis=1)
                shortfall_rows.append(dict(model=n_, firm_id=fid, cutoff=T, y4=ev4, y13=ev13,
                                           p4=float((mn[:, 3] < 0).mean()), p13=float((mn[:, -1] < 0).mean())))
            for n_, Q in (("Direct LGBM-Q (src)", Qd), ("Naive (known out + avg in)", Qn)):
                pk = [np.interp(0.0, Q[k], [0.1, 0.5, 0.9], left=0.0, right=1.0) for k in range(K)]
                shortfall_rows.append(dict(model=n_, firm_id=fid, cutoff=T, y4=ev4, y13=ev13, p4=max(pk[:4]),
                                           p13=max(pk)))
            if demo is None and T >= O + pd.Timedelta(days=7 * 20) and (np.quantile(bal, .1, axis=0) < 0).any():
                demo = (fid, T, snap, P_all[msk], H[msk], B0, ko, rq, ker, cap_rate, cap_sz, bal, tp)
    df = pd.DataFrame(rows)
    df.to_parquet(RES / "t6_predictions.parquet", index=False)
    summ = []
    for (n_, grp), g in df.assign(grp=np.where(df["k"] <= 4, "w1-4", "w5-13")).groupby(["model", "grp"]):
        summ.append(dict(model=n_, horizon=grp, cov80=M.coverage(g["y"], g["lo"], g["hi"]),
                         IS80=M.interval_score(g["y"], g["lo"], g["hi"]),
                         pinball=np.mean([M.pinball(g["y"], g[c], a) for c, a in (("lo", .1), ("med", .5), ("hi", .9))]),
                         MAE_p50=float(np.mean(np.abs(g["y"] - g["med"])))))
    sf = pd.DataFrame(shortfall_rows)
    from sklearn.metrics import roc_auc_score
    srows = []
    for n_, g in sf.groupby("model"):
        r = dict(model=n_)
        for h in ("4", "13"):
            y, p = g[f"y{h}"].values, g[f"p{h}"].values
            r[f"shortfall_rate_{h}w"] = y.mean()
            r[f"Brier_{h}w"] = M.brier(y, p)
            r[f"AUC_{h}w"] = roc_auc_score(y, p) if 0 < y.mean() < 1 else np.nan
        srows.append(r)
    S1, S2 = pd.DataFrame(summ), pd.DataFrame(srows)
    log("\n" + S1.round(3).to_string() + "\n" + S2.round(3).to_string())
    S1.to_csv(RES / "t6_interval_metrics.csv", index=False)
    S2.to_csv(RES / "t6_shortfall_metrics.csv", index=False)
    json.dump({"rho_selected": rho, "rho_scores": {str(k): float(np.mean(v)) for k, v in score_rho.items()}},
              open(RES / "t6_rho.json", "w"), indent=2)
    if demo is not None:
        t10_demo(demo, m_ft)


def t10_demo(demo, model):
    """T10: dải xác suất, danh sách HĐ nên đòi trước kèm lý do SHAP, kịch bản 'nếu như'."""
    fid, T, snap, P, H, B0, ko, rq, ker, cr, cs, bal, tp = demo
    band = pd.DataFrame({"week": np.arange(1, K + 1), "P10": np.quantile(bal, .1, 0), "P50": np.quantile(bal, .5, 0),
                         "P90": np.quantile(bal, .9, 0), "P_shortfall_by_week": (np.minimum.accumulate(bal, 1) < 0).mean(0),
                         "actual_no_action": tp})
    base_p = float((bal.min(1) < 0).mean())
    # giá trị đòi sớm: chuyển HĐ i về tuần 1 -> giảm P(thiếu hụt)
    gains = []
    for j in range(len(snap)):
        P2 = P.copy()
        P2[j] = 0
        P2[j, 0] = 1.0
        b2, _ = simulate(snap, P2, B0, ko, rq, ker, cr, cs, n=600, rho=0.2, seed=9)
        gains.append(base_p - float((b2.min(1) < 0).mean()))
    snap = snap.assign(p_paid_4w=P[:, :4].sum(1), exp_week=(P * np.arange(1, K + 1)).sum(1) + (1 - P.sum(1)) * 15,
                       shortfall_reduction_if_collected_now=gains)
    X, _, ix = t1.expand(snap, False)
    contrib = model.booster.predict(X, pred_contrib=True)
    names = FEATURES + t1.WEEK_FEATS
    first = ix[:len(snap)] if False else None
    reasons = []
    wk1 = np.arange(len(snap))  # hàng tuần 1 nằm ở block đầu tiên của expand(train=False)
    for j in wk1:
        c = contrib[j, :-1]
        top = np.argsort(c)[:3]  # đóng góp âm nhất vào hazard tuần 1 = lý do khiến khả năng trả sớm thấp
        reasons.append("; ".join(f"{names[t]}={snap.iloc[j].get(names[t], np.nan) if names[t] in snap else X[j, t]:.3g}"
                                 for t in top))
    snap["why_late (SHAP top-3)"] = reasons
    top = snap.sort_values("shortfall_reduction_if_collected_now", ascending=False).head(10)[
        ["invoice_id", "customer_id", "amount_open", "days_to_due", "p_paid_4w", "exp_week",
         "shortfall_reduction_if_collected_now", "why_late (SHAP top-3)"]]
    # kịch bản: khách lớn nhất trả chậm thêm 2 tuần
    big = snap.groupby("customer_id")["amount_open"].sum().idxmax()
    P3 = P.copy()
    m = (snap["customer_id"] == big).values
    P3[m] = np.hstack([np.zeros((m.sum(), 2)), P[m, :-2]])
    b3, _ = simulate(snap, P3, B0, ko, rq, ker, cr, cs, n=1000, rho=0.2, seed=4)
    scen = {"firm": fid, "cutoff": str(T.date()), "P_shortfall_13w_base": base_p,
            "scenario": f"khách lớn nhất {big} trả chậm thêm 2 tuần",
            "P_shortfall_13w_scenario": float((b3.min(1) < 0).mean()),
            "P10_min_balance_base": float(np.quantile(bal.min(1), .1)),
            "P10_min_balance_scenario": float(np.quantile(b3.min(1), .1))}
    band.to_csv(RES / "demo_band.csv", index=False)
    top.to_csv(RES / "demo_collect_first.csv", index=False)
    json.dump(scen, open(RES / "demo_whatif.json", "w"), indent=2, ensure_ascii=False)
    log("demo", scen)


if __name__ == "__main__":
    main()
