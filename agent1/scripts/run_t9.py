#!/usr/bin/env python3
"""T9 — khớp sao kê: học trên miền nguồn (src, một phần công ty), đánh giá trên miền đích (tgt).
So với mốc quy tắc R1 (đúng số tiền) và R2 (regex số HĐ); đo sai số ngày trả so với ngày ghi sổ."""
import sys
import time
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH, OUT  # noqa: E402
from agent1.models import t9_recon as T9  # noqa: E402
from agent1.eval.cluster import ratio_ci

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


def evaluate(name, links, bank, inv, pay, bootstrap=True):
    r = T9.score_links(links, pay)
    noise = bank[bank["txn_type"] != "customer_payment"]["txn_id"]
    r["false_match_noise_txn_rate"] = float(links["txn_id"].isin(noise).groupby(links["txn_id"]).first().sum() / max(len(noise), 1))
    full = pay[pay["kind"].isin(["full", "final"])]
    truth = pd.to_datetime(full.groupby("invoice_id")["pay_date_true"].max())
    led = inv.set_index("invoice_id")["ledger_clear_date"]
    est = pd.to_datetime(links[links['kind']=='full'].groupby("invoice_id")["est_pay_date"].max())
    common = est.index.intersection(truth.index)
    r["pay_date_MAE_est_days"] = float((est[common] - truth[common]).dt.days.abs().mean())
    r["pay_date_exact_share"] = float(((est[common] - truth[common]).dt.days == 0).mean())
    r['settled_invoice_coverage']=len(common)/max(len(truth),1)
    cl = truth.index.intersection(led.dropna().index)
    r["pay_date_MAE_ledger_days"] = float((led[cl] - truth[cl]).dt.days.abs().mean())
    r["method"] = name
    if bootstrap:
        stats = []
        for firm, transactions in bank.groupby('firm_id'):
            ids = set(transactions.txn_id)
            p = links[links.txn_id.isin(ids)]
            t = pay[pay.txn_id.isin(ids)]
            metric = T9.score_links(p, t)
            dates = evaluate(name, p, transactions, inv[inv.firm_id == firm], t, bootstrap=False)
            n_dates = int(round(dates['settled_invoice_coverage'] * t[t.kind.isin(['full','final'])].invoice_id.nunique()))
            stats.append(dict(tp=metric['link_precision']*metric['n_pred'],pred=metric['n_pred'],truth=metric['n_true'],
                date_error_sum=dates['pay_date_MAE_est_days']*n_dates if n_dates else 0.,date_count=n_dates,
                auto=p.txn_id.nunique(),bank=len(transactions)))
        stats = pd.DataFrame(stats)
        for label, numerator, denominator in [('link_precision',stats.tp,stats.pred),
                ('link_recall',stats.tp,stats.truth),('link_f1',2*stats.tp,stats.pred+stats.truth),
                ('pay_date_MAE',stats.date_error_sum,stats.date_count),('auto_coverage',stats.auto,stats.bank)]:
            ci = ratio_ci(numerator, denominator)
            r.update({label+'_ci_low':ci['ci_low'],label+'_ci_high':ci['ci_high']})
        r.update(bootstrap_n=300,n_firms=len(stats))
    return r


def main():
    t0 = time.time()
    src_firms = [f"F{i:03d}" for i in range(0, 12)]
    bs, is_, cs, ps = load("src", src_firms, "2023-01-01", "2023-12-31")
    rec = T9.Reconciler()
    digest = hashlib.sha256(Path(T9.__file__).read_bytes()).hexdigest()[:12]
    cs_p, ct_p = RES / f"cand_src_{digest}.parquet", RES / f"cand_tgt_{digest}.parquet"
    cand_s = pd.read_parquet(cs_p) if cs_p.exists() else rec.candidates(bs, is_, cs)
    cand_s.to_parquet(cs_p, index=False)
    rec.fit(cand_s)
    bc, ic, cc, pc = load('src', src_firms, '2024-01-01', '2024-06-30')
    # Hiệu chỉnh trên miền nguồn, không lấy nhãn đích để chọn ngưỡng.
    source_candidates = rec.candidates(bc, ic, cc)
    rec.calibrate(source_candidates)
    rec.save(RES/'source_reconciler',dict(training_world='src',training_period=['2023-01-01','2023-12-31'],
        calibration_period=['2024-01-01','2024-06-30'],target_used=False))
    from agent1.models.reconciliation_pipeline import reconcile, build_bank_labels
    # Chẩn đoán nguồn riêng; ngưỡng .9 đã cố định trước khi đọc tgt.
    source_best = rec.assign_customers(source_candidates)
    source_rows = []
    for policy in ['opening_only', 'asof']:
        source_links, source_queue = reconcile(rec, bc, ic, cc, assignments=source_best, ledger_policy=policy)
        source_rows.append(dict(evaluate('Hybrid '+policy,source_links,bc,ic,pc),n_review=len(source_queue),
            measurement_version='t9-asof-known-customers-v5',split='source_calibration_diagnostic_not_independent_test',tau_auto=.9))
    pd.DataFrame(source_rows).to_csv(RES/'source_allocation_diagnostics.csv',index=False)
    print("trained on src candidates", cand_s.shape, round(time.time() - t0), "s", flush=True)
    bt, it, ct, pt = load("tgt")
    cand_t = pd.read_parquet(ct_p) if ct_p.exists() else rec.candidates(bt, it, ct)
    cand_t.to_parquet(ct_p, index=False)
    best = rec.assign_customers(cand_t)
    is_pay = bt.set_index("txn_id")["txn_type"].eq("customer_payment")
    acc = best.assign(true=best["txn_id"].map(bt.set_index("txn_id")["true_customer_id"]))
    cust_acc = float(((acc["customer_id"] == acc["true"]) & acc["matched"]).sum() / is_pay.sum())
    links, _ = reconcile(rec, bt, it, ct, assignments=best, rules_first=False)
    r1, _ = reconcile(T9.Reconciler(), bt, it, ct, rule_mode='amount')
    r2, _ = reconcile(T9.Reconciler(), bt, it, ct, rule_mode='memo')
    hybrid, queue = reconcile(rec, bt, it, ct, tau_auto=.9, assignments=best)
    oracle = bt[bt.true_customer_id.notna()][['txn_id', 'true_customer_id']].rename(columns={'true_customer_id': 'customer_id'})
    oracle['confidence'], oracle['matched'] = 1., True
    oracle_links, _ = reconcile(rec, bt, it, ct, assignments=oracle, rules_first=False)
    rows = [dict(evaluate("ML customer + subset (src->tgt)", links, bt, it, pt), txn_customer_recall=cust_acc),
            evaluate("R1 observed unique-amount rule", r1, bt, it, pt),
            evaluate("R2 observed memo rule", r2, bt, it, pt),
            dict(evaluate('Hybrid rules+ML auto (tau=.9)', hybrid, bt, it, pt),
                 auto_txn_coverage=hybrid.txn_id.nunique()/max(len(bt),1), n_review=len(queue)),
            evaluate('Oracle customer / subset allocation', oracle_links, bt, it, pt)]
    out = pd.DataFrame(rows)
    out['measurement_version'], out['seed'] = 't9-asof-known-customers-v5', 1
    print(out.round(4).to_string(), flush=True)
    out.to_csv(RES / "t9_reconciliation_tgt.csv", index=False)
    links.to_parquet(RES / "t9_links_tgt.parquet", index=False)
    hybrid.to_parquet(RES / 't9_auto_links_tgt.parquet', index=False)
    queue.to_parquet(RES / 't9_review_queue_tgt.parquet', index=False)
    build_bank_labels(it, hybrid).to_parquet(RES / 't9_bank_labels_tgt.parquet', index=False)
    curve = []
    for tau in (.5, .7, .8, .9, .95, .99):
        a, q = reconcile(rec, bt, it, ct, tau_auto=tau, assignments=best)
        curve.append(dict(tau=tau, threshold_chosen=(tau == .9), n_auto_txns=a.txn_id.nunique(),
                          auto_coverage=a.txn_id.nunique()/max(len(bt),1), **T9.score_links(a, pt)))
    pd.DataFrame(curve).to_csv(RES / 'precision_coverage.csv', index=False)


if __name__ == "__main__":
    main()
