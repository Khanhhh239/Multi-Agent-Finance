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
from agent1.models.t6_cash import simulate, collection_kernel, ACI, K, conditional_payment_pmf  # noqa: E402
from agent1.models.features import FEATURES  # noqa: E402
from agent1.eval import metrics as M  # noqa: E402
from agent1.eval.cluster import mean_ci
from agent1.eval.alerts import choose_threshold, event_metrics
import run_t1 as R1  # noqa: E402

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
    fixed_categories={'payroll_net','social_insurance','rent','loan_service','license_fee'}
    known = o[o["category"].isin(fixed_categories)].groupby("date")["amount"].sum()
    sup = o[o["category"] == "supplier"].groupby("date")["amount"].sum()
    capex = o[o["category"] == "capex"]
    d = daily[daily["firm_id"] == fid].set_index("date")
    net = d["inflow_ar"] + d["inflow_other"] - d["outflow"] - d['owner_draw']
    scheduled=o[o.category.isin(KNOWN-fixed_categories)]
    return dict(known=known, sup=sup, capex=capex, net=net, bal=d["balance"], inv=inv[inv["firm_id"] == fid], outflows=o,scheduled=scheduled,owner_draw=d.owner_draw)


def known_outflows(ctx, T):
    ko = weekly(ctx["known"], T)
    scheduled=ctx.get('scheduled')
    if scheduled is not None:
        for category,g in scheduled.groupby('category'):
            history=g[g.date<=T]
            estimate=float(history.amount.tail(4).mean()) if len(history) else 0.
            future=g[g.date>T].copy()
            if category in {'vat','cit_provisional'}:
                # Nghĩa vụ của kỳ đã đóng được biết từ đầu tháng kê khai.
                known_at=future.date.dt.to_period('M').dt.start_time
                future['forecast_amount']=np.where(known_at<=T,future.amount,estimate)
            else:
                future['forecast_amount']=estimate
            ko+=weekly(future.groupby('date').forecast_amount.sum(),T)
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


def draw_policy(ctx,T):
    """Học chính sách rút vốn từ quý đã qua; không đọc buffer_days/cash_cap_days tiềm ẩn."""
    history=ctx['bal'][(ctx['bal'].index<=T)&(ctx['bal'].index>T-pd.Timedelta(days=365))]
    dates=history.index[history.index.is_quarter_end]
    if not len(dates):return {}
    observed_draw=ctx['owner_draw'].reindex(dates).fillna(0.)
    positive=observed_draw>0
    if not positive.any():return {}
    target=float(history.reindex(dates[positive]).median())
    pre=history.reindex(dates)+observed_draw
    upper=float(pre[positive].min())
    lower=max(target,float(pre[~positive].max())) if (~positive).any() else target
    cap=max(target,(lower+upper)/2)
    future=pd.date_range(T+pd.Timedelta(days=1),T+pd.Timedelta(days=91))
    quarter_ends=future[future.is_quarter_end]
    mask=np.array([((quarter_ends>T+pd.Timedelta(days=7*k))&(quarter_ends<=T+pd.Timedelta(days=7*(k+1)))).any() for k in range(K)])
    return dict(draw_cap=cap,draw_target=target,draw_weeks=mask)


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


def cash_revenue_series(inv, world):
    data = inv.assign(week=inv.issue_date.dt.to_period('W-MON').dt.start_time)
    result = {}
    for fid, g in data.groupby('firm_id'):
        s = g.groupby('week').amount_gross.sum()
        result[f'{world}:{fid}'] = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq='7D'), fill_value=0.)
    return result


def main(*,target_world='tgt',evaluation_world=None,result_dir=None,source_budget=None,n_weeks=52,label_mode='oracle_bank'):
    global RES
    if result_dir is not None:
        RES=Path(result_dir);RES.mkdir(parents=True,exist_ok=True)
    evaluation_world=evaluation_world or target_world
    version=f'cash-e2e-{label_mode}-v1' if target_world!=evaluation_world else 'cash-asof-outflows-owner-tcopula-v5-true-labels'
    version+='-fullweek'
    inv_s = pd.read_parquet(SYNTH / "src" / "invoices.parquet")
    inv_t = pd.read_parquet(SYNTH / target_world / "invoices.parquet")
    out_s, out_t = (pd.read_parquet(SYNTH / w / "outflows.parquet") for w in ("src", target_world))
    day_s, day_t = (pd.read_parquet(SYNTH / w / "daily_cash.parquet") for w in ("src", evaluation_world))
    # ---------------- T1: src -> fine-tune tgt (12 tháng)
    source_cut=pd.date_range('2019-07-01','2025-09-29',freq='7D')
    if source_budget:
        source_cut=sorted(set(pd.date_range('2019-07-01',O-pd.Timedelta(days=7),freq='14D')) |
            set(pd.date_range(O-pd.Timedelta(days=183),O-pd.Timedelta(days=120),freq='7D')) |
            set(pd.date_range(O-pd.Timedelta(days=210),O-pd.Timedelta(days=98),freq='14D')) |
            set(pd.date_range('2020-01-06',O-pd.Timedelta(days=98),freq='28D')))
    Ssrc = R1.snapshots('src',source_cut,tag='cash_budget' if source_budget else 'weekly')
    tr = R1.censor(Ssrc[Ssrc["cutoff"].isin(pd.date_range("2019-07-01", O - pd.Timedelta(days=7), freq="14D"))], O)
    if source_budget:tr=tr.sample(min(source_budget,len(tr)),random_state=7)
    log("T1 src fit", len(tr))
    m_src = t1.HazardGBM().fit(tr)
    Tt = R1.censor(R1.snapshots(target_world, pd.date_range(VIS + pd.Timedelta(days=28), O - pd.Timedelta(days=7), freq="7D"),
                                visible_from=VIS, tag="adapt_M12"), O)
    m_ft = t1.HazardGBM(dict(learning_rate=0.02), rounds=150)
    m_ft.fit(Tt, init_model=m_src.booster)
    test_cut = pd.date_range(O, periods=n_weeks, freq='7D')
    Ste = R1.snapshots(target_world, test_cut, visible_from=VIS, tag="test_M12")
    Ste = Ste.assign(amount_open=Ste["amount_open"].fillna(Ste["amount_gross"]))
    log("predict hazards", len(Ste))
    H = m_ft.hazards(Ste)
    P_all, _ = t1.pmf_from_hazard(H)
    cure_split=O-pd.Timedelta(days=183)
    cure_train=R1.censor(Ssrc[Ssrc.cutoff<cure_split],cure_split)
    cure_cal=R1.censor(Ssrc[Ssrc.cutoff.between(cure_split,O-pd.Timedelta(days=120))],O)
    if source_budget:
        cure_train=cure_train.sample(min(source_budget,len(cure_train)),random_state=11)
        cure_cal=cure_cal.sample(min(10000,len(cure_cal)),random_state=11)
    log('T2 cure source fit/calibrate',len(cure_train),len(cure_cal))
    cure=t1.CureGBM().fit(cure_train,calibration=cure_cal)
    bad_all=cure.predict_proba_calibrated(Ste)
    conditional_all,cure_conflicts=conditional_payment_pmf(P_all,bad_all)
    pd.DataFrame([dict(n=len(Ste),mean_p_bad=float(bad_all.mean()),
                      incompatible_cure_share=float(cure_conflicts.mean()),seed=11)]).to_csv(RES/'cure_diagnostics.csv',index=False)
    b1w = np.clip(np.ceil(t1.b1_predict(Ste) / 7).astype(int) - 1, 0, K)      # tuần trả theo B1 (K = ngoài)
    P_b1 = np.zeros_like(P_all)
    inside = b1w < K
    P_b1[np.nonzero(inside)[0], b1w[inside]] = 1.0
    # ---------------- T4
    ss = cash_revenue_series(inv_s, 'src')
    from run_t4 import build
    rho_cal_start = O - pd.Timedelta(days=7 * 30)
    ss_train = {key: values[values.index + pd.Timedelta(days=6) < rho_cal_start] for key, values in ss.items()}
    Xr, Yr, _, _ = build(ss_train, True, lambda n: list(range(20, n - K)))
    m4 = T4.GlobalQuantileLGBM().fit(Xr, Yr)
    st = cash_revenue_series(inv_t, 'tgt')
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
    tr_tune = R1.censor(tr[tr.cutoff < rho_cal_start], rho_cal_start)
    m_tune = t1.HazardGBM().fit(tr_tune)
    Ht = m_tune.hazards(Stune)
    Pt, _ = t1.pmf_from_hazard(Ht)
    score_rho = {r: [] for r in rho_grid}
    alerts_cal = []
    for fid in inv_s["firm_id"].unique()[:16]:
        ctx = firm_context("src", fid, inv_s, out_s, day_s)
        for T in tune_cut:
            msk = ((Stune["firm_id"] == fid) & (Stune["cutoff"] == T)).values
            B0, tp = truth_path(ctx, T)
            ko = known_outflows(ctx, T)
            rq = rev_quantiles(m4, ss[f"src:{fid}"], T)
            ker = collection_kernel(ctx["inv"][ctx["inv"]["issue_date"] < T], T)
            for r in rho_grid:
                bal, _ = simulate(Stune[msk], Pt[msk], B0, ko, rq, ker, 0.0, [], n=400, rho=r, seed=1,**draw_policy(ctx,T))
                lo, hi = np.quantile(bal, .1, axis=0), np.quantile(bal, .9, axis=0)
                sc = max(ko.mean(), 1.0)
                score_rho[r].append(M.interval_score(tp / sc, lo / sc, hi / sc))
                alerts_cal.append(dict(rho=r, y4=float(tp[:4].min() < 0), y13=float(tp.min() < 0),
                                       p4=float((bal[:, :4].min(1) < 0).mean()), p13=float((bal.min(1) < 0).mean())))
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
            policy=draw_policy(ctx,T)
            bal, _ = simulate(snap, P_all[msk], B0, ko, rq, ker, cap_rate, cap_sz, n=1000, rho=rho, seed=int(T.value % 1e6),**policy)
            res["MC-copula-t (T1+T4+T5)"] = bal
            res['MC-copula-t + calibrated cure'] = simulate(snap,conditional_all[msk],B0,ko,rq,ker,cap_rate,cap_sz,
                n=1000,rho=rho,seed=int(T.value%1e6),p_bad=bad_all[msk],**policy)[0]
            res["MC-independent (rho=0)"] = simulate(snap, P_all[msk], B0, ko, rq, ker, cap_rate, cap_sz, n=1000, rho=0.0, seed=2,**policy)[0]
            res["MC with B1 point dates"] = simulate(snap, P_b1[msk], B0, ko, rq, ker, cap_rate, cap_sz, n=1000, rho=0.0, seed=3,**policy)[0]
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
                demo = (fid, T, snap, P_all[msk], H[msk], B0, ko, rq, ker, cap_rate, cap_sz, bal, tp,policy)
    df = pd.DataFrame(rows)
    df.to_parquet(RES / "t6_predictions.parquet", index=False)
    summ = []
    for (n_, grp), g in df.assign(grp=np.where(df["k"] <= 4, "w1-4", "w5-13")).groupby(["model", "grp"]):
        row = dict(model=n_, horizon=grp, cov80=M.coverage(g["y"], g["lo"], g["hi"]),
                         IS80=M.interval_score(g["y"], g["lo"], g["hi"]),
                         pinball=np.mean([M.pinball(g["y"], g[c], a) for c, a in (("lo", .1), ("med", .5), ("hi", .9))]),
                         MAE_p50=float(np.mean(np.abs(g["y"] - g["med"]))), seed=7,
                         measurement_version=version)
        ci = mean_ci(((g.y >= g.lo) & (g.y <= g.hi)).astype(float), g.firm_id)
        row.update(cov80_ci_low=ci['ci_low'], cov80_ci_high=ci['ci_high'], bootstrap_n=ci['bootstrap_n'])
        summ.append(row)
    sf = pd.DataFrame(shortfall_rows)
    sf.to_csv(RES / 't6_shortfall_predictions.csv', index=False)
    cal_alerts = pd.DataFrame(alerts_cal)
    cal_alerts = cal_alerts[cal_alerts.rho == rho]
    policy_rows = []
    for cost_ratio in (2, 5, 10):
        for horizon in (4, 13):
            tau, cost = choose_threshold(cal_alerts[f'y{horizon}'], cal_alerts[f'p{horizon}'], cost_ratio)
            for name, g in sf.groupby('model'):
                policy_rows.append(dict(model=name, cost_ratio=cost_ratio, horizon=horizon, threshold=tau,
                    calibration_cost=cost, threshold_selected_on='source_only',
                    **event_metrics(g, day_t, threshold=tau, probability=f'p{horizon}', horizon_days=7*horizon)))
    pd.DataFrame(policy_rows).to_csv(RES / 'alert_policy.csv', index=False)
    from sklearn.metrics import roc_auc_score
    srows = []
    for n_, g in sf.groupby("model"):
        r = dict(model=n_, measurement_version=version, seed=7)
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
    (RES/'run_metadata.json').write_text(json.dumps(dict(
        origin=str(O.date()),visible_from=str(VIS.date()),n_paths=1000,nu=4,rho=rho,
        bootstrap_seed=7,source_t1_seed=7,cure_seed=11,
        simulation_seed_policy={'copula':'cutoff_timestamp_ns_mod_1000000','independent':2,'point_dates':3},
        target_used_for_hyperparameter_selection=False,labels=label_mode,
        target_world=target_world,evaluation_world=evaluation_world,source_budget=source_budget,n_weeks=n_weeks,
        measurement_version=version),indent=2),encoding='utf-8')
    if demo is not None:
        t10_demo(demo, m_ft, rho)


def t10_demo(demo, model, rho=.2):
    """T10: dải xác suất, danh sách HĐ nên đòi trước kèm lý do SHAP, kịch bản 'nếu như'."""
    fid, T, snap, P, H, B0, ko, rq, ker, cr, cs, bal, tp,policy = demo
    from agent1.models.t10 import rank_collections, what_if, explain_invoice, scenario_library
    args = dict(open_df=snap, P=P, B0=B0, known_out=ko, rev_q=rq, kernel=ker,
                capex_rate=cr, capex_sizes=cs, n=1000, rho=rho, seed=int(T.value % 1e6))
    args.update(policy)
    top = rank_collections(snap, P, args, top_n=10)
    reasons = {row.invoice_id: explain_invoice(model, snap[snap.invoice_id == row.invoice_id].iloc[:1]) for row in top.itertuples()}
    top['reasons'] = top.invoice_id.map(lambda iid: json.dumps(reasons[iid], ensure_ascii=False))
    band = pd.DataFrame(np.quantile(bal, [.1, .5, .9], axis=0).T, columns=['P10', 'P50', 'P90'])
    band.insert(0, 'week', np.arange(1, 14))
    band['actual_no_action'] = tp
    band.to_csv(RES / 'demo_band.csv', index=False)
    top.to_csv(RES / 'demo_collect_first.csv', index=False)
    big = snap.groupby('customer_id').amount_open.sum().idxmax()
    scen = what_if(args, delay_customer=big, delay_weeks=2)
    (RES / 'demo_whatif.json').write_text(json.dumps(dict(firm=fid, cutoff=str(T.date()), customer=big,
        baseline_risk=float((bal.min(1) < 0).mean()), scenario_risk=scen['shortfall_probability']), indent=2), encoding='utf-8')
    scenario_library(args).to_csv(RES / 'stress_scenarios.csv', index=False)
    return


if __name__ == "__main__":
    main()
