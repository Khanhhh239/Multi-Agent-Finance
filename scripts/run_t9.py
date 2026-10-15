#!/usr/bin/env python3
"""T9 — khớp sao kê: học trên miền nguồn (src, một phần công ty), đánh giá trên miền đích (tgt).
So với mốc quy tắc R1 (đúng số tiền) và R2 (regex số HĐ); đo sai số ngày trả so với ngày ghi sổ."""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH, OUT  # noqa: E402
from agent1.models import t9_recon as T9  # noqa: E402

RES = OUT / "t9"
RES.mkdir(parents=True, exist_ok=True)


def load(name, firms=None, since="2024-01-01", until="2024-12-31"):
    d = SYNTH / name
    bank = pd.read_parquet(d / "bank_txns.parquet")
    inv = pd.read_parquet(d / "invoices.parquet")
    cust = pd.read_parquet(d / "customers.parquet")
    pay = pd.read_parquet(d / "payments.parquet")
    if firms is not None:
        bank, inv, cust, pay = (x[x["firm_id"].isin(firms)] for x in (bank, inv, cust, pay))
    bank = bank[(bank["value_date"] >= since) & (bank["value_date"] <= until)]
    pay = pay[pay["txn_id"].isin(bank["txn_id"])]
    inv = inv[inv["issue_date"] <= until]
    return bank, inv, cust, pay


def evaluate(name, links, bank, inv, pay):
    r = T9.score_links(links, pay)
    noise = bank[bank["txn_type"] != "customer_payment"]["txn_id"]
    r["false_match_noise_txn_rate"] = float(links["txn_id"].isin(noise).groupby(links["txn_id"]).first().sum() / max(len(noise), 1))
    full = pay[pay["kind"].isin(["full", "final"])]
    truth = full.groupby("invoice_id")["pay_date_true"].max()
    led = inv.set_index("invoice_id")["ledger_clear_date"]
    est = links.groupby("invoice_id")["est_pay_date"].max()
    common = est.index.intersection(truth.index)
    r["pay_date_MAE_est_days"] = float((est[common] - truth[common]).dt.days.abs().mean())
    r["pay_date_exact_share"] = float(((est[common] - truth[common]).dt.days == 0).mean())
    cl = truth.index.intersection(led.dropna().index)
    r["pay_date_MAE_ledger_days"] = float((led[cl] - truth[cl]).dt.days.abs().mean())
    r["method"] = name
    return r


def main():
    t0 = time.time()
    src_firms = [f"F{i:03d}" for i in range(0, 12)]
    bs, is_, cs, ps = load("src", src_firms, "2023-01-01", "2023-12-31")
    rec = T9.Reconciler()
    cs_p, ct_p = RES / "cand_src.parquet", RES / "cand_tgt.parquet"
    cand_s = pd.read_parquet(cs_p) if cs_p.exists() else rec.candidates(bs, is_, cs)
    cand_s.to_parquet(cs_p, index=False)
    rec.fit(cand_s)
    print("trained on src candidates", cand_s.shape, round(time.time() - t0), "s", flush=True)
    bt, it, ct, pt = load("tgt")
    cand_t = pd.read_parquet(ct_p) if ct_p.exists() else rec.candidates(bt, it, ct)
    cand_t.to_parquet(ct_p, index=False)
    best = rec.assign_customers(cand_t)
    is_pay = bt.set_index("txn_id")["txn_type"].eq("customer_payment")
    acc = best.assign(true=best["txn_id"].map(bt.set_index("txn_id")["true_customer_id"]))
    cust_acc = float(((acc["customer_id"] == acc["true"]) & acc["matched"]).sum() / is_pay.sum())
    links = rec.allocate(best, bt, it)
    rows = [dict(evaluate("ML reconciler (src->tgt)", links, bt, it, pt), txn_customer_recall=cust_acc),
            evaluate("R1 exact-amount rule", T9.rule_exact_amount(bt, it), bt, it, pt),
            evaluate("R2 memo-regex rule", T9.rule_memo_regex(bt, it), bt, it, pt)]
    out = pd.DataFrame(rows)
    print(out.round(4).to_string(), flush=True)
    out.to_csv(RES / "t9_reconciliation_tgt.csv", index=False)
    links.to_parquet(RES / "t9_links_tgt.parquet", index=False)


if __name__ == "__main__":
    main()
