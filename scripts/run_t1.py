#!/usr/bin/env python3
"""T1 (+T2 cure, T8, T9 ảnh hưởng nhãn) — thí nghiệm theo giao thức T11.

  A. rolling-origin trên miền nguồn (src): mọi mô hình so với B0/B1/B1d
  B. domain adaptation sang miền đích niêm phong (tgt): M tháng lịch sử sau onboard
  C. dữ liệu THẬT tương tự: Customer Invoices (AR giống ERP), BPI 2019 (P2P)
  D. T2 cure: P(không bao giờ trả | còn mở) — so với quy tắc tuổi nợ TT48 và logistic
  E. T8: giá trị của lời hứa trả; F. T9: học từ ngày ghi sổ (nhiễu lô) vs ngày ngân hàng

  python scripts/run_t1.py --exp A,B,C,D,E,F
"""
import argparse
import json
import sys
import time
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH, PROCESSED, OUT  # noqa: E402
from agent1.threads import NT  # noqa: E402
from agent1.models.features import SnapshotBuilder, add_labels, FEATURES, BASELINE_QUANTILES  # noqa: E402
from agent1.eval.cluster import mean_ci  # noqa: E402
from agent1.eval.strata import assign_strata  # noqa: E402
from agent1.models import t1  # noqa: E402
from agent1.eval import metrics as M  # noqa: E402
from agent1.data import real_loaders as R  # noqa: E402

RES = OUT / "t1"
RES.mkdir(parents=True, exist_ok=True)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def load_world(name):
    d = SYNTH / name
    inv = pd.read_parquet(d / "invoices.parquet")
    pay = pd.read_parquet(d / "payments.parquet")
    prom = pd.read_parquet(d / "promises.parquet") if (d / "promises.parquet").exists() else None
    return inv, pay, prom


def snapshots(name, cutoffs, label_col="paid_date_true", visible_from=None, tag="", use_promises=True,
              use_payments=True, firms=None):
    cutoffs = list(cutoffs)
    source_files = [SYNTH / name / f'{table}.parquet' for table in ('invoices', 'payments', 'promises')]
    signature = dict(cutoffs=[str(pd.Timestamp(t)) for t in cutoffs], visible_from=str(visible_from),
                     firms=sorted(map(str, firms)) if firms is not None else None,
                     use_promises=use_promises, use_payments=use_payments, label_col=label_col,
                     features=FEATURES,
                     builder=hashlib.sha256((Path(__file__).resolve().parents[1] / 'agent1/models/features.py').read_bytes()).hexdigest(),
                     sources=[(str(f), f.stat().st_size, f.stat().st_mtime_ns) for f in source_files if f.exists()])
    key = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()[:16]
    p = PROCESSED / f"snap_{name}_{label_col}_{tag}_{key}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    inv, pay, prom = load_world(name)
    sb = SnapshotBuilder(inv, pay if use_payments else None, prom if use_promises else None, label_col=label_col)
    df = sb.build(cutoffs, label_end=None, visible_from=visible_from, firms=firms)
    df["amount_open"] = df["amount_gross"] * (1 - df["paid_frac_so_far"].fillna(0))
    keep = list(dict.fromkeys(["invoice_id", "firm_id", "customer_id", "cutoff", "issue_date", "due_date", "label_date",
                               "writeoff_date", "amount_gross", "amount_open", "is_bad_debt", "top1", "top2"] + FEATURES + BASELINE_QUANTILES))
    df = df[[c for c in keep if c in df]]
    f64 = df.select_dtypes("float64").columns
    df[f64] = df[f64].astype("float32")
    df.to_parquet(p, index=False)
    return df


def censor(df, label_end):
    df = df.copy()
    return add_labels(df, label_end)


def fully_observed(df, end):
    return df[df["cutoff"] <= pd.Timestamp(end) - pd.Timedelta(days=int(t1.CAP))]


# ------------------------------------------------------------------------------------------------
def fit_all(train, cal=None, include=("B1", "QLGBM", "AFT", "DH-LR", "DH-GBM"), hazard_params=None):
    models = {}
    if "DH-GBM" in include:
        models["DH-GBM"] = t1.HazardGBM(hazard_params).fit(train)
    if "DH-LR" in include:
        models["DH-LR"] = t1.HazardLR().fit(train)
    if "QLGBM" in include:
        models["QLGBM"] = t1.QuantileLGBM().fit(train)
    if "AFT" in include:
        models["AFT"] = t1.AFT().fit(train)
    return models


def predict_all(models, test, hist_q=None):
    out = {}
    out["B0-due"] = {"Q": np.column_stack([t1.b0_predict(test)] * 3)}
    b1 = t1.b1_predict(test)
    out["B1-cust-median"] = {"Q": np.column_stack([b1] * 3)}
    if hist_q is not None or all(c in test for c in BASELINE_QUANTILES):
        out["B1d-cust-quantiles"] = {"Q": t1.b1_dist(test, hist_q)}
    for n, m in models.items():
        if n.startswith("DH"):
            H = m.hazards(test)
            P, S = t1.pmf_from_hazard(H)
            out[n] = {"Q": t1.quantiles_from_hazard(H), "P": P, "cdf": 1 - S, "exp": t1.expected_days_from_hazard(H)}
        elif isinstance(m, t1.QuantileLGBM):
            dense = m.predict_dense(test)
            out[n] = {'Q': np.column_stack([np.array([np.interp(a, m.alphas, row) for row in dense]) for a in t1.QS]),
                      'dense_Q': dense, 'alphas': m.alphas, 'cdf': t1.cdf_from_quantiles(dense, m.alphas)}
            out[n]['P'] = np.diff(np.c_[np.zeros(len(test)), out[n]['cdf']], axis=1)
        else:
            out[n] = {"Q": m.predict(test)}
    if "DH-GBM" in out and "QLGBM" in out:
        # trung bình phân vị (Vincentization) — kết hợp phân phối có kiểm duyệt đúng + độ phân giải ngày của QLGBM
        # Phân phối ensemble phải khớp chính phân vị của ensemble.
        out["ENS DH-GBM+QLGBM"] = {'Q': np.sort((out["DH-GBM"]["Q"] + out["QLGBM"]["Q"]) / 2, axis=1)}
    return out


def score(preds, test, tag, extra=None, strata_rows=None):
    rows = []
    y = test["remaining"].values
    capped = np.minimum(y, t1.CAP)
    base_name = 'B1d-cust-quantiles' if 'B1d-cust-quantiles' in preds else 'B1-cust-median'
    def pinball_rows(Q):
        err = capped[:, None] - Q
        return np.maximum(np.array(t1.QS) * err, (np.array(t1.QS) - 1) * err).mean(1)
    base_loss = pinball_rows(preds[base_name]['Q']) if base_name in preds else None
    for n, d in preds.items():
        r = {"setting": tag, "model": n, "n": len(test), 'seed': 7, 'measurement_version': 'asof-pchip-v2'}
        r.update(t1.evaluate_quantiles(y, d["Q"]))
        cdf = d.get("cdf")
        if cdf is None:
            cdf = t1.cdf_from_quantiles(d["Q"])
            P = np.diff(np.hstack([np.zeros((len(cdf), 1)), cdf]), axis=1)
        else:
            P = d["P"]
        r["IBS_13w"], _ = M.ibs_weekly(y, cdf)
        r['IBS_13w_fair'] = r['IBS_13w']
        losses = pinball_rows(d['Q'])
        ci = mean_ci(losses, test['firm_id'], baseline=base_loss)
        r.update({('pinball_' + k if k in ('ci_low', 'ci_high') else k): v for k, v in ci.items()})
        r['baseline_model'] = base_name if base_loss is not None else ''
        cov = ((capped >= d['Q'][:, 0]) & (capped <= d['Q'][:, -1])).astype(float)
        ci_cov = mean_ci(cov, test['firm_id'])
        r['cov80_ci_low'], r['cov80_ci_high'] = ci_cov['ci_low'], ci_cov['ci_high']
        if strata_rows is not None:
            strata = assign_strata(test)
            ibs = ((y[:, None] <= 7 * np.arange(1, 14)) - cdf) ** 2
            for dimension in strata:
                for group in strata[dimension].unique():
                    mask = (strata[dimension] == group).to_numpy()
                    strata_rows.append(dict(setting=tag, model=n, dimension=dimension, group=group, n=int(mask.sum()),
                                            pinball_avg=float(losses[mask].mean()), cov80=float(cov[mask].mean()),
                                            IBS_13w=float(ibs[mask].mean()), seed=7))
        r["Brier_4w"] = M.brier((y <= 28).astype(float), cdf[:, 3])
        r["ECE_4w"] = M.ece((y <= 28).astype(float), cdf[:, 3])
        risk = -(d["exp"] if "exp" in d else d["Q"][:, 1])
        r["C_index"] = M.c_index(np.minimum(y, 1e4), (y < 1e4).astype(int), risk)
        if "amount_open" in test:
            cw = t1.collections_by_week(test, P)
            r["WAPE_collect_w1_4"] = M.wape(cw[cw.k <= 4]["act"], cw[cw.k <= 4]["pred"])
            r["WAPE_collect_w5_13"] = M.wape(cw[cw.k > 4]["act"], cw[cw.k > 4]["pred"])
        if extra:
            r.update(extra)
        rows.append(r)
    return pd.DataFrame(rows)


def hist_quantiles(inv, end, label_col="paid_date_true", visible_from=None):
    h = inv[(inv[label_col].notna()) & (inv[label_col] <= end)]
    if visible_from is not None:
        h = h[h["issue_date"] >= visible_from]
    d = (h[label_col] - h["due_date"]).dt.days.clip(-60, 240)
    g = d.groupby(h["customer_id"])
    return pd.DataFrame({"customer_id": g.size().index, "q10": g.quantile(.1).values, "q50": g.quantile(.5).values,
                         "q90": g.quantile(.9).values})


# ------------------------------------------------------------------------------------------------
def exp_A(origins=("2023-07-03", "2024-07-01")):
    log("A: build src snapshots")
    cut = pd.date_range("2019-07-01", "2025-09-29", freq="7D")
    S = snapshots("src", cut, tag="weekly")
    log("A: snapshots", S.shape)
    inv, _, _ = load_world("src")
    res, strata_rows = [], []
    for O in map(pd.Timestamp, origins):
        cal_lo, cal_hi = O - pd.Timedelta(days=int(t1.CAP) + 63), O - pd.Timedelta(days=int(t1.CAP))
        tr = censor(S[S["cutoff"] < cal_lo], cal_lo)
        tr = tr[tr["cutoff"].dt.isocalendar().week.astype(int) % 2 == 0]  # mỗi 2 tuần để gọn
        cal = censor(S[S["cutoff"].between(cal_lo, cal_hi)], O)
        te = censor(S[(S["cutoff"] >= O) & (S["cutoff"] < O + pd.Timedelta(days=182))], "2025-12-31")
        log(f"A origin {O.date()} train={len(tr)} cal={len(cal)} test={len(te)}")
        models = fit_all(tr)
        hq = hist_quantiles(inv, O)
        P_te = predict_all(models, te, hq)
        P_cal = predict_all(models, cal, hq)
        for n in list(P_te):
            if n in ("DH-GBM", "QLGBM", "AFT", "B1d-cust-quantiles", "ENS DH-GBM+QLGBM"):
                qhat = t1.cqr_fit_asym(cal["remaining"].values, P_cal[n]["Q"])
                log('CQR', n, 'q_lo/q_hi=', qhat)
                P_te[n + "+CQR"] = {"Q": t1.cqr_apply_asym(P_te[n]["Q"], qhat)}
        sc = score(P_te, te, f"A_src_origin_{O.date()}", strata_rows=strata_rows)
        res.append(sc)
        log(sc[["model", "MAE_p50", "pinball_avg", "cov80", "IBS_13w", "WAPE_collect_w1_4", "C_index"]].round(4).to_string())
        if O == pd.Timestamp(origins[-1]):
            imp = pd.Series(models["DH-GBM"].booster.feature_importance("gain"),
                            index=models["DH-GBM"].booster.feature_name()).sort_values(ascending=False)
            imp.to_csv(RES / "dh_gbm_feature_importance.csv")
    out = pd.concat(res)
    pd.DataFrame(strata_rows).to_csv(RES / 'A_strata.csv', index=False)
    out.to_csv(RES / "A_rolling_origin_src.csv", index=False)
    return out


def domain_weights(src, tgt, feats=FEATURES):
    """Trọng số tỷ lệ mật độ p(tgt|x)/p(src|x) bằng bộ phân loại miền (Shimodaira 2000; Bickel 2009)."""
    import lightgbm as lgb
    X = np.vstack([src[feats].astype("float32").values, tgt[feats].astype("float32").values])
    y = np.r_[np.zeros(len(src)), np.ones(len(tgt))]
    m = lgb.train(dict(objective="binary", learning_rate=0.05, num_leaves=31, min_data_in_leaf=200, verbose=-1, num_threads=NT),
                  lgb.Dataset(X, y), 200)
    p = np.clip(m.predict(src[feats].astype("float32").values), 0.01, 0.99)
    w = p / (1 - p) * (len(src) / len(tgt))
    return np.clip(w / w.mean(), 0.05, 20)


def exp_B(O="2024-07-01", months=(0, 3, 6, 12, 24)):
    O = pd.Timestamp(O)
    log("B: src training snapshots")
    cut_src = pd.date_range("2019-07-01", O - pd.Timedelta(days=7), freq="14D")
    Ssrc = censor(snapshots("src", pd.date_range("2019-07-01", "2025-09-29", freq="7D"), tag="weekly")
                  .pipe(lambda d: d[d["cutoff"].isin(cut_src)]), O)
    log("B: fit source models", len(Ssrc))
    m_src = t1.HazardGBM().fit(Ssrc)
    q_src = t1.QuantileLGBM().fit(Ssrc)
    inv_t, _, _ = load_world("tgt")
    res = []
    for Mm in months:
        vis = O - pd.DateOffset(months=Mm) if Mm > 0 else O
        test_cut = pd.date_range(O, O + pd.Timedelta(days=357), freq="7D")
        te = censor(snapshots("tgt", test_cut, visible_from=vis, tag=f"test_M{Mm}"), "2025-12-31")
        hq = hist_quantiles(inv_t, O, visible_from=vis)
        preds = {}
        preds["B1-cust-median"] = {"Q": np.column_stack([t1.b1_predict(te)] * 3)}
        if Mm > 0:
            preds["B1d-cust-quantiles"] = {"Q": t1.b1_dist(te, hq)}
        H = m_src.hazards(te)
        P, S = t1.pmf_from_hazard(H)
        preds["SRC-only DH-GBM (zero-shot)"] = {"Q": t1.quantiles_from_hazard(H), "P": P, "cdf": 1 - S,
                                               "exp": t1.expected_days_from_hazard(H)}
        preds["SRC-only QLGBM"] = {"Q": q_src.predict(te)}
        if Mm >= 3:
            tr_cut = pd.date_range(vis + pd.Timedelta(days=28), O - pd.Timedelta(days=7), freq="7D")
            Tt = censor(snapshots("tgt", tr_cut, visible_from=vis, tag=f"adapt_M{Mm}"), O)
            log(f"B M={Mm}: target adapt rows={len(Tt)}")
            variants = {}
            variants["TGT-only DH-GBM"] = t1.HazardGBM(dict(min_data_in_leaf=50, num_leaves=31), rounds=300).fit(Tt)
            pooled = pd.concat([Ssrc, Tt], ignore_index=True)
            w = np.r_[np.ones(len(Ssrc)), np.full(len(Tt), max(1.0, 0.3 * len(Ssrc) / max(len(Tt), 1)))]
            variants["POOLED (tgt-upweighted)"] = t1.HazardGBM().fit(pooled, weight=w)
            ft = t1.HazardGBM(dict(learning_rate=0.02), rounds=150)
            ft.fit(Tt, init_model=m_src.booster)
            variants["FINE-TUNE src->tgt"] = ft
            wsrc = domain_weights(Ssrc, Tt)
            variants["IW-POOLED (density-ratio)"] = t1.HazardGBM().fit(
                pooled, weight=np.r_[wsrc, np.full(len(Tt), max(1.0, 0.3 * len(Ssrc) / max(len(Tt), 1)))])
            for n, m in variants.items():
                H = m.hazards(te)
                P, S = t1.pmf_from_hazard(H)
                preds[n] = {"Q": t1.quantiles_from_hazard(H), "P": P, "cdf": 1 - S, "exp": t1.expected_days_from_hazard(H)}
            # conformal hiệu chỉnh trên cửa sổ đích gần nhất đã quan sát đủ
            calw = Tt[Tt["cutoff"] <= O - pd.Timedelta(days=int(t1.CAP))]
            if len(calw) > 200:
                calw = censor(calw, O)
                for n in ("FINE-TUNE src->tgt", "POOLED (tgt-upweighted)"):
                    Hc = variants[n].hazards(calw)
                    qhat = t1.cqr_fit(np.minimum(calw["time_obs"].values, t1.CAP), t1.quantiles_from_hazard(Hc))
                    preds[n + "+CQR"] = dict(preds[n], Q=t1.cqr_apply(preds[n]["Q"], qhat))
        sc = score(preds, te, f"B_tgt_M{Mm}", extra={"months_history": Mm})
        res.append(sc)
        log(sc[["model", "MAE_p50", "pinball_avg", "cov80", "IBS_13w", "WAPE_collect_w1_4"]].round(4).to_string())
    out = pd.concat(res)
    out.to_csv(RES / "B_domain_adaptation_tgt.csv", index=False)
    return out


def exp_C():
    res = []
    for name, loader, O, test_days, start in (
            ("real_customer_invoices", R.customer_invoices, "2019-12-01", 63, "2019-03-01"),
            ("real_bpi2019", R.bpi2019, "2018-09-03", 56, "2018-03-05")):
        inv = loader()
        inv = inv.copy()
        if "due_date" not in inv:
            inv["due_date"] = pd.NaT
        inv["writeoff_date"] = pd.NaT
        inv["is_bad_debt"] = False
        O = pd.Timestamp(O)
        cut = pd.date_range(start, O + pd.Timedelta(days=test_days), freq="7D")
        p = PROCESSED / f"snap_{name}.parquet"
        if p.exists():
            S = pd.read_parquet(p)
        else:
            sb = SnapshotBuilder(inv, None, None, label_col="paid_date_true")
            S = sb.build(cut)
            S = S[[c for c in dict.fromkeys(["invoice_id", "firm_id", "customer_id", "cutoff", "issue_date", "due_date",
                                             "label_date", "writeoff_date", "amount_gross", "top1", "top2"] + FEATURES)
                   if c in S]]
            S.to_parquet(p, index=False)
        f64 = S.select_dtypes("float64").columns
        S[f64] = S[f64].astype("float32")
        data_end = inv["paid_date_true"].max()
        tr = censor(S[S["cutoff"] < O], O)
        if len(tr) > 400_000:   # BPI: mỗi 2 tuần + lấy mẫu để vừa RAM
            tr = tr[tr["cutoff"].dt.isocalendar().week.astype(int) % 2 == 0]
            tr = tr.sample(min(len(tr), 400_000), random_state=0)
        te = censor(S[S["cutoff"] >= O], data_end)
        te = te[te["cutoff"] <= data_end - pd.Timedelta(days=int(t1.CAP))] if (te["cutoff"] <= data_end - pd.Timedelta(days=int(t1.CAP))).any() else te
        te = te.assign(amount_open=te["amount_gross"])
        log(f"C {name}: train={len(tr)} test={len(te)} data_end={data_end.date()}")
        models = fit_all(tr, hazard_params=dict(min_data_in_leaf=100))
        hq = hist_quantiles(inv.assign(due_date=inv["due_date"].fillna(inv["issue_date"])), O)
        preds = predict_all(models, te, hq)
        sc = score(preds, te, f"C_{name}")
        res.append(sc)
        log(sc[["model", "MAE_p50", "pinball_avg", "cov80", "IBS_13w", "C_index"]].round(4).to_string())
    out = pd.concat(res)
    out.to_csv(RES / "C_real_domains.csv", index=False)
    return out


def exp_D(O="2024-07-01"):
    """T2: P(không bao giờ trả | còn mở tại T) trên src (rolling) và tgt (zero-shot + pooled)."""
    from sklearn.metrics import average_precision_score, roc_auc_score
    O = pd.Timestamp(O)
    S = snapshots("src", pd.date_range("2019-07-01", "2025-09-29", freq="7D"), tag="weekly")
    tr = censor(S[S["cutoff"] < O - pd.Timedelta(days=0)], O)
    tr = tr[tr["cutoff"].dt.isocalendar().week.astype(int) % 2 == 0]
    rows = []
    cure = t1.CureGBM().fit(tr)
    from sklearn.linear_model import LogisticRegression
    d = tr[(tr["event"] == 1) | (tr["bad_known"] == 1)]
    lr_f = ["days_past_due", "c_late30_share", "c_delay_eb", "c_open_overdue_n", "c_max_dpd", "log_amount_rel",
            "c_n_hist", "f_resid_28d", "paid_frac_so_far", "c_promise_rel"]
    Xl = d[lr_f].fillna(0).values
    mu, sd = Xl.mean(0), Xl.std(0) + 1e-6
    lr = LogisticRegression(max_iter=500).fit((Xl - mu) / sd, d["bad_known"].values)
    for wname in ("src", "tgt"):
        Sx = S if wname == "src" else snapshots("tgt", pd.date_range(O, O + pd.Timedelta(days=357), freq="7D"),
                                                visible_from="2019-01-01", tag="test_full")
        te = Sx[(Sx["cutoff"] >= O) & (Sx["cutoff"] < O + pd.Timedelta(days=364))]
        te = te[te["days_past_due"] > 0]  # câu hỏi T2 có ý nghĩa với khoản đã quá hạn
        y = te["is_bad_debt"].astype(int).values
        # quy tắc TT48/2019: trích lập theo tuổi quá hạn (6-12 tháng 30%, 1-2 năm 50%, 2-3 năm 70%, >3 năm 100%)
        dpd = te["days_past_due"].values
        rule = np.select([dpd > 1095, dpd > 730, dpd > 365, dpd > 180], [1.0, .7, .5, .3], 0.0)
        p_aging = te.groupby(pd.cut(te["days_past_due"], [0, 30, 60, 90, 180, 365, 1e5]), observed=False)["is_bad_debt"].transform("mean")
        cand = {"TT48 aging rule": rule, "Logistic": lr.predict_proba((te[lr_f].fillna(0).values - mu) / sd)[:, 1],
                "Cure-GBM": cure.predict(te)}
        for n, p in cand.items():
            amt = te["amount_open"].values
            rows.append({"world": wname, "model": n, "n": len(te), "base_rate": y.mean(),
                         "PR_AUC": average_precision_score(y, p), "ROC_AUC": roc_auc_score(y, p),
                         "Brier": M.brier(y, p), "ECE": M.ece(y, p),
                         "expected_loss_vs_actual": float((p * amt).sum() / max((y * amt).sum(), 1))})
    out = pd.DataFrame(rows)
    log(out.round(4).to_string())
    out.to_csv(RES / "D_t2_cure.csv", index=False)
    return out


def exp_EF(O="2024-07-01"):
    """E: T8 lời hứa trả (có/không đặc trưng lời hứa).  F: T9 học từ ngày ghi sổ vs ngày ngân hàng."""
    O = pd.Timestamp(O)
    cut = pd.date_range("2019-07-01", "2025-09-29", freq="7D")
    S = snapshots("src", cut, tag="weekly")
    tr = censor(S[S["cutoff"] < O], O)
    tr = tr[tr["cutoff"].dt.isocalendar().week.astype(int) % 2 == 0]
    te = censor(S[(S["cutoff"] >= O) & (S["cutoff"] < O + pd.Timedelta(days=182))], "2025-12-31")
    res = []
    no_prom = [f for f in FEATURES if f not in ("has_promise", "days_to_promised", "promise_overdue", "c_promise_rel",
                                                "c_promise_n")]
    for n, feats in (("DH-GBM with promises (T8)", FEATURES), ("DH-GBM without promises", no_prom)):
        m = t1.HazardGBM(feats=feats).fit(tr)
        H = m.hazards(te)
        P, Sv = t1.pmf_from_hazard(H)
        sc = score({n: {"Q": t1.quantiles_from_hazard(H), "P": P, "cdf": 1 - Sv, "exp": t1.expected_days_from_hazard(H)}},
                   te, "E_T8")
        sub = te["has_promise"] == 1
        sc["MAE_p50_promised_only"] = float(np.mean(np.abs(np.minimum(te.loc[sub, "remaining"], t1.CAP) -
                                                         t1.quantiles_from_hazard(H[sub.values])[:, 1])))
        res.append(sc)
    # F: nhãn từ sổ cái (ngày ghi sổ theo lô) -> đánh giá trên ngày tiền về thật
    SL = snapshots("src", cut, label_col="ledger_clear_date", tag="weekly")
    trL = censor(SL[SL["cutoff"] < O], O)
    trL = trL[trL["cutoff"].dt.isocalendar().week.astype(int) % 2 == 0]
    mL = t1.HazardGBM().fit(trL)
    mB = t1.HazardGBM().fit(tr)
    for n, m in (("DH-GBM trained on LEDGER dates", mL), ("DH-GBM trained on BANK dates (T9)", mB)):
        H = m.hazards(te)
        P, Sv = t1.pmf_from_hazard(H)
        res.append(score({n: {"Q": t1.quantiles_from_hazard(H), "P": P, "cdf": 1 - Sv,
                              "exp": t1.expected_days_from_hazard(H)}}, te, "F_T9_label_source"))
    out = pd.concat(res)
    log(out[["setting", "model", "MAE_p50", "IBS_13w", "WAPE_collect_w1_4", "cov80"]].round(4).to_string())
    out.to_csv(RES / "EF_t8_t9.csv", index=False)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="A,B,C,D,E")
    a = ap.parse_args()
    ex = set(a.exp.split(","))
    if "A" in ex:
        exp_A()
    if "B" in ex:
        exp_B()
    if "C" in ex:
        exp_C()
    if "D" in ex:
        exp_D()
    if "E" in ex or "F" in ex:
        exp_EF()
