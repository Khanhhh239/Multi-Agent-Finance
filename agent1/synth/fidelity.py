"""T12 — Hiệu chỉnh và kiểm định độ trung thực của thế giới tổng hợp.

Tách hai loại kiểm tra (quy tắc chống ảo tưởng, Phần 5 mục 3.2):
  (A) calibration_targets: đích đã DÙNG để chỉnh (Atradius) -> chỉ chứng minh máy phát chạy đúng.
  (B) independent_checks: dấu hiệu KHÔNG dùng để chỉnh -> bằng chứng về cấu trúc:
      - so với bộ AR giống ERP thật (Customer Invoices / HighRadius): tỷ lệ trả cuối tuần, độ lệch số tiền,
        phương sai trễ giải thích bởi khách, độ bền hành vi khách giữa hai nửa thời gian, Benford;
      - so với JPMorgan Chase Institute: đệm tiền mặt (đã dùng để khởi tạo số dư — ghi rõ là A);
      - các dấu hiệu "bộ sinh với trọng số cố định" phải KHÔNG xuất hiện: khối lượng phẳng theo tháng,
        cuối tuần = ngày thường, tỷ lệ trạng thái tròn số.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def _between_share(x: pd.Series, keys: pd.Series) -> float:
    gm = x.mean()
    g = x.groupby(keys.values).agg(["size", "mean"])
    return float((g["size"] * (g["mean"] - gm) ** 2).sum() / len(x) / x.var())


def value_outcomes(inv: pd.DataFrame) -> pd.DataFrame:
    """Tỷ trọng theo GIÁ TRỊ: đúng hạn / quá hạn / nợ xấu (định nghĩa Atradius), chỉ hoá đơn bán chịu."""
    d = inv[inv["term_days"] > 0].copy()
    if 'outcome_status_at_end' in d:
        d = d[d['outcome_status_at_end'] != 'censored']
    d["late"] = (d["days_late_true"] > 0) & ~d["is_bad_debt"]
    d["ontime"] = ~d["late"] & ~d["is_bad_debt"]
    d["v"] = d["amount_gross"]
    g = d.groupby("industry").apply(lambda x: pd.Series({
        "ontime": (x["v"] * x["ontime"]).sum() / x["v"].sum(),
        "overdue": (x["v"] * x["late"]).sum() / x["v"].sum(),
        "bad_debt": (x["v"] * x["is_bad_debt"]).sum() / x["v"].sum(),
        "avg_term_days": np.average(x["term_days"], weights=x["v"]),
    }), include_groups=False)
    allr = pd.Series({"ontime": (d["v"] * d["ontime"]).sum() / d["v"].sum(),
                      "overdue": (d["v"] * d["late"]).sum() / d["v"].sum(),
                      "bad_debt": (d["v"] * d["is_bad_debt"]).sum() / d["v"].sum(),
                      "avg_term_days": np.average(d["term_days"], weights=d["v"])}, name="ALL")
    return pd.concat([g, allr.to_frame().T])


def structural_signature(inv: pd.DataFrame, paid_col="paid_date_true") -> dict:
    out = {}
    paid = inv[paid_col]
    closed = paid.notna()
    late = (paid - inv["due_date"]).dt.days[closed]
    out["n_invoices"] = int(len(inv))
    out["closed_share"] = round(float(closed.mean()), 4)
    out["weekend_share_issue"] = round(float((inv["issue_date"].dt.dayofweek >= 5).mean()), 4)
    out["weekend_share_paid"] = round(float((paid[closed].dt.dayofweek >= 5).mean()), 4)
    a = inv["amount_gross"] if "amount_gross" in inv else inv["amount"]
    a = a[a > 0]
    out["amount_skew"] = round(float(a.skew()), 2)
    out["amount_log_sd"] = round(float(np.log(a).std()), 3)
    first = pd.Series(np.floor(a.values / 10 ** np.floor(np.log10(a.values))).astype(int))
    obs = first.value_counts(normalize=True).reindex(range(1, 10)).fillna(0)
    exp = pd.Series({d: np.log10(1 + 1 / d) for d in range(1, 10)})
    out["benford_mad"] = round(float((obs - exp).abs().mean()), 4)
    m = inv["issue_date"].dt.to_period("M").value_counts().sort_index()
    out["monthly_count_cv"] = round(float(m.iloc[1:-1].std() / m.iloc[1:-1].mean()), 3)
    out["days_late_q"] = {str(k): float(v) for k, v in late.quantile([.05, .25, .5, .75, .95, .99]).round(1).items()}
    out["late_buckets"] = {k: round(float(v), 4) for k, v in pd.cut(late, [-1e6, -1, 0, 30, 60, 1e6],
                           labels=["early", "on_due", "1_30", "31_60", "60p"]).value_counts(normalize=True).items()}
    c = inv["customer_id"][closed].reset_index(drop=True)
    lt = late.reset_index(drop=True)
    wl = lt.clip(lt.quantile(0.01), lt.quantile(0.99))
    out["delay_var_share_customer"] = round(_between_share(wl, c), 3)
    half = (inv["issue_date"][closed] >= inv["issue_date"][closed].median()).values
    t = pd.DataFrame({"c": c.values, "late": lt.values, "half": half})
    pv = t.groupby(["c", "half"]).agg(n=("late", "size"), m=("late", "mean")).unstack()
    ok = pv[(pv["n"] >= 20).all(axis=1)]
    out["customer_persistence_spearman"] = round(float(ok["m"].corr(method="spearman").iloc[0, 1]), 3) if len(ok) >= 5 else None
    vc = inv["customer_id"].value_counts(normalize=True)
    out["top10_customer_share"] = round(float(vc.head(10).sum()), 3)
    return out


def load_customer_invoices_reference(path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)

    def d(s):
        s = pd.to_numeric(s, errors="coerce")
        return pd.to_datetime(s.dropna().astype("int64").astype(str), format="%Y%m%d", errors="coerce").reindex(s.index)
    out = pd.DataFrame({"customer_id": df["cust_number"].astype(str), "issue_date": d(df["baseline_create_date"]),
                        "due_date": d(df["due_in_date"]), "paid_date_true": pd.to_datetime(df["clear_date"], errors="coerce"),
                        "amount_gross": pd.to_numeric(df["total_open_amount"], errors="coerce")})
    return out.dropna(subset=["issue_date", "due_date"])


def report(world_dir: Path, reference_csv: Path | None = None) -> dict:
    world_dir = Path(world_dir)
    inv = pd.read_parquet(world_dir / "invoices.parquet")
    firms = pd.read_parquet(world_dir / "firms.parquet")
    inv = inv.merge(firms[["firm_id", "industry"]], on="firm_id")
    calib = json.loads((Path(__file__).parent / "calibration_vn.json").read_text(encoding="utf-8"))
    vo = value_outcomes(inv)
    res = {"A_calibration_targets": {
        "target_overall": calib["overall"]["invoice_value_outcome"],
        "achieved": vo.round(4).to_dict("index"),
        "credit_share_by_value": round(float(inv.loc[inv["term_days"] > 0, "amount_gross"].sum() / inv["amount_gross"].sum()), 4),
        "target_credit_share": calib["overall"]["share_of_b2b_sales_on_credit"],
    }}
    sig = {}
    for fid, g in inv.groupby("firm_id"):
        sig[fid] = structural_signature(g)
    keys = ["weekend_share_paid", "amount_skew", "delay_var_share_customer", "customer_persistence_spearman",
            "benford_mad", "monthly_count_cv", "top10_customer_share"]
    agg = {k: float(np.nanmedian([s[k] for s in sig.values() if s[k] is not None])) for k in keys}
    res["B_independent_checks"] = {"synthetic_median_over_firms": agg,
                                   "pooled_late_buckets": structural_signature(inv)["late_buckets"]}
    if reference_csv and Path(reference_csv).exists():
        ref = load_customer_invoices_reference(reference_csv)
        res["B_independent_checks"]["reference_customer_invoices"] = {k: structural_signature(ref)[k] for k in keys}
    daily = pd.read_parquet(world_dir / "daily_cash.parquet")
    res["cash"] = {"share_firm_days_negative_balance": round(float((daily["balance"] < 0).mean()), 4),
                   "firms_with_any_shortfall": int(daily.groupby("firm_id")["balance"].min().lt(0).sum()),
                   "n_firms": int(daily["firm_id"].nunique()),
                   "median_buffer_days": float(firms["buffer_days"].median())}
    return res
