#!/usr/bin/env python3
"""Realism audit for invoice / receivables datasets (Agent 1).

Reads a CSV (local path or URL, held in memory only) and prints structural checks that separate
"looks like an ERP receivables ledger" from "generated with fixed random weights".
It does not prove that data is real. It reports evidence; interpretation is in the Part 7 document.

  python realism_audit.py --csv https://raw.githubusercontent.com/SkywalkerHub/Payment-Date-Prediction/main/Dataset.csv --profile highradius
  python realism_audit.py --csv my.csv --profile custom --invoice-date inv --due-date due --paid-date paid --amount amt --customer cid
"""
import argparse
import json

import numpy as np
import pandas as pd

PROFILES = {
    "highradius": dict(invoice_date="baseline_create_date", due_date="due_in_date", paid_date="clear_date",
                       amount="total_open_amount", customer="cust_number", name="name_customer",
                       terms="cust_payment_terms", currency="invoice_currency", status="isOpen"),
}


def to_date(s):
    s = pd.Series(s)
    if s.dtype.kind in "fi":
        s = s.dropna().astype("int64").astype(str).reindex(s.index)
        return pd.to_datetime(s, format="%Y%m%d", errors="coerce")
    return pd.to_datetime(s, errors="coerce")


def shares(x, edges, labels):
    c = pd.cut(x, edges, labels=labels)
    return (c.value_counts(normalize=True).reindex(labels)).round(4).to_dict()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--profile", default="custom")
    for k in ("invoice_date", "due_date", "paid_date", "amount", "customer", "name", "terms", "currency", "status"):
        ap.add_argument("--" + k.replace("_", "-"), default=None)
    a = ap.parse_args()
    cols = dict(PROFILES.get(a.profile, {}))
    for k in ("invoice_date", "due_date", "paid_date", "amount", "customer", "name", "terms", "currency", "status"):
        v = getattr(a, k)
        if v:
            cols[k] = v
    df = pd.read_csv(a.csv, low_memory=False)
    out = {"rows": len(df), "columns": list(df.columns)}
    out["duplicate_rows"] = int(df.duplicated().sum())
    out["missing_share"] = {c: round(float(df[c].isna().mean()), 4) for c in df.columns if df[c].isna().any()}

    inv = to_date(df[cols["invoice_date"]])
    due = to_date(df[cols["due_date"]])
    paid = to_date(df[cols["paid_date"]])
    amt = pd.to_numeric(df[cols["amount"]], errors="coerce")
    out["invoice_date_range"] = [str(inv.min().date()), str(inv.max().date())]
    out["weekend_share_invoice_date"] = round(float((inv.dt.dayofweek >= 5).mean()), 4)
    out["weekend_share_paid_date"] = round(float((paid.dt.dayofweek >= 5).dropna().mean()), 4)
    m = inv.dt.to_period("M").value_counts().sort_index()
    out["monthly_invoice_count_cv"] = round(float(m.iloc[1:-1].std() / m.iloc[1:-1].mean()), 4) if len(m) > 3 else None
    out["invoice_month_of_year_share"] = inv.dt.month.value_counts(normalize=True).sort_index().round(3).to_dict()

    a_pos = amt[amt > 0].dropna()
    out["amount"] = {
        "negative_share": round(float((amt < 0).mean()), 4),
        "median": round(float(a_pos.median()), 2), "mean": round(float(a_pos.mean()), 2),
        "p99": round(float(a_pos.quantile(0.99)), 2),
        "skew": round(float(a_pos.skew()), 2),
        "log_sd": round(float(np.log(a_pos).std()), 3),
        "round_100_share": round(float((a_pos % 100 == 0).mean()), 4),
        "top_1pct_amount_share": round(float(a_pos.nlargest(max(1, len(a_pos) // 100)).sum() / a_pos.sum()), 4),
    }
    first = a_pos.astype(str).str.replace(r"[^0-9]", "", regex=True).str.lstrip("0").str[0].astype(int)
    obs = first.value_counts(normalize=True).reindex(range(1, 10)).fillna(0)
    exp = pd.Series({d: np.log10(1 + 1 / d) for d in range(1, 10)})
    out["benford"] = {"observed": obs.round(3).to_dict(), "mean_abs_deviation": round(float((obs - exp).abs().mean()), 4)}

    closed = paid.notna()
    late = (paid - due).dt.days[closed]
    d2p = (paid - inv).dt.days[closed]
    out["closed_share"] = round(float(closed.mean()), 4)
    out["days_late_quantiles"] = late.quantile([0.05, 0.25, 0.5, 0.75, 0.95, 0.99]).round(1).to_dict()
    out["days_late_buckets"] = shares(late, [-10**6, -1, 0, 30, 60, 10**6], ["early", "on_due_day", "1-30", "31-60", "60+"])
    out["days_to_pay_median"] = float(d2p.median())

    if "customer" in cols:
        g = df[cols["customer"]]
        out["customers"] = int(g.nunique())
        vc = g.value_counts(normalize=True)
        out["top10_customer_invoice_share"] = round(float(vc.head(10).sum()), 4)
        if "name" in cols:
            npc = df.groupby(cols["customer"])[cols["name"]].nunique()
            out["names_per_customer_id"] = {"mean": round(float(npc.mean()), 2), "max": int(npc.max()),
                                            "share_ids_with_more_than_1_name": round(float((npc > 1).mean()), 4)}
        t = pd.DataFrame({"c": g[closed].values, "late": late.values, "half": (inv[closed] >= inv[closed].median()).values})
        pv = t.groupby(["c", "half"]).agg(n=("late", "size"), m=("late", "mean")).unstack()
        ok = pv[(pv["n"] >= 20).all(axis=1)]
        if len(ok) >= 5:
            out["customer_mean_delay_persistence_spearman"] = {"customers": int(len(ok)), "rho": round(float(ok["m"].corr(method="spearman").iloc[0, 1]), 3)}
        def between_share(x, keys):
            gm = x.mean()
            g = x.groupby(keys.values).agg(["size", "mean"])
            return float((g["size"] * (g["mean"] - gm) ** 2).sum() / len(x) / x.var())
        lt = late.reset_index(drop=True)
        ck = g[closed].reset_index(drop=True)
        wl = lt.clip(lt.quantile(0.01), lt.quantile(0.99))
        out["share_of_delay_variance_between_customers"] = {"raw": round(between_share(lt, ck), 3),
                                                            "winsorized_1_99": round(between_share(wl, ck), 3)}
    if "terms" in cols:
        span = (due - inv).dt.days
        z = pd.DataFrame({"t": df[cols["terms"]], "span": span}).dropna()
        gg = z.groupby("t")["span"].agg(["size", "median", lambda s: float(s.nunique())]).sort_values("size", ascending=False).head(8)
        gg.columns = ["n", "median_days_invoice_to_due", "distinct_values"]
        out["terms_top8"] = gg.round(1).to_dict("index")
    if "currency" in cols:
        out["currency_share"] = df[cols["currency"]].value_counts(normalize=True).round(4).to_dict()
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
