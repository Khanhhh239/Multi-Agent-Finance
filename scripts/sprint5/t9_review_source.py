#!/usr/bin/env python3
"""B1 — hàng chờ duyệt: chọn chính sách CHỈ TRÊN NGUỒN (DN giữ lại, 2024H1). Không đụng thế giới đích.

Luồng sản phẩm: T9 v2 → kế toán duyệt b giao dịch/DN/tuần theo chính sách → nhãn mềm cho phần còn thiếu.
Đo: độ phủ hoá đơn đã trả có nhãn, sai số nhãn, số lượt duyệt thực tế.
Đầu ra: outputs/t9/review/source_review.csv
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "scripts" / "sprint5"))
from agent1.paths import OUT, SYNTH  # noqa: E402
from agent1.models.t9_fast import fast_source, reconcile_arrays, concatenate_parts  # noqa: E402
from agent1.models.t9_soft_labels import soft_fifo_labels  # noqa: E402
from agent1.models.t9_review_queue import simulate_review, POLICIES  # noqa: E402
from agent1.api_surface import build_bank_labels  # noqa: E402
from run_e2e_protocol import source_reconciler  # noqa: E402
from run_t9_hardcases import load_observed  # noqa: E402
from t9_guard import hazard_prior, prepare  # noqa: E402

RES = OUT / "t9" / "review"
BUDGETS = (0, 2, 5, 10)
SOFT_CONFIDENCE = 0.8


def main():
    RES.mkdir(parents=True, exist_ok=True)
    v2 = json.loads((OUT / "t9/v2/choice.json").read_text(encoding="utf-8"))
    source = fast_source(source_reconciler(OUT / "t9/sprint3/source_reconciler", require_training_firms=True))
    heldout = set(pd.read_parquet(SYNTH / "src/firms.parquet").firm_id) - set(source.provenance["training_firms"])
    model, label_end = hazard_prior()
    bank, inv, cust, _ = load_observed("src", "2024-01-01", "2024-06-30")
    bank = bank[bank.firm_id.isin(heldout)]; inv = inv[inv.firm_id.isin(heldout)]; cust = cust[cust.firm_id.isin(heldout)]
    prep = prepare(source, bank, inv, cust, model, label_end)
    links = concatenate_parts([reconcile_arrays(source, t, i, c, assignments=a, tau_auto=.5, allocation_policy=p,
                                                max_guess_subset=v2["cap"], hazard_subsets=v2["hazard"], fifo_allocation=v2["fifo"])[0]
                               for t, i, c, a, p in prep])
    asg = pd.concat([a for *_, a, _ in prep])
    truth = pd.read_parquet(SYNTH / "src/payments.parquet", columns=["txn_id", "invoice_id", "amount", "pay_date_true"])
    truth = truth[truth.txn_id.isin(bank.txn_id)]
    true_paid = pd.read_parquet(SYNTH / "src/invoices.parquet", columns=["invoice_id", "paid_date_true"]).set_index("invoice_id").paid_date_true
    paid = inv[inv.invoice_id.map(true_paid).between("2024-01-01", "2024-06-30")]
    weeks = max(len(pd.date_range("2024-01-01", "2024-06-30", freq="W")), 1)
    rows = []
    for policy in POLICIES:
        for b in BUDGETS:
            if b == 0 and policy != POLICIES[0]:
                continue
            rl, st = simulate_review(links, bank, truth, per_week=b, policy=policy)
            lab = build_bank_labels(inv, rl).set_index("invoice_id").paid_date_est
            soft = soft_fifo_labels(rl, bank, inv, asg, min_confidence=SOFT_CONFIDENCE)
            est = lab.combine_first(soft)
            ids = paid.invoice_id
            e = est.reindex(ids.to_numpy()); t = true_paid.reindex(ids.to_numpy())
            has = e.notna().to_numpy()
            err = np.abs(np.asarray((pd.to_datetime(e[has].to_numpy()) - pd.to_datetime(t[has].to_numpy())).days, float))
            amt = paid.set_index("invoice_id").amount_gross.reindex(ids.to_numpy()).to_numpy()
            rows.append(dict(policy="none" if b == 0 else policy, reviews_per_firm_week=b, n_queued=st["n_queued"],
                             n_reviewed=st["n_reviewed"], share_queue_reviewed=st["share_reviewed"],
                             reviews_per_firm_week_actual=st["n_reviewed"] / (len(heldout) * weeks),
                             coverage_paid=float(has.mean()), coverage_paid_amount=float(amt[has].sum() / amt.sum()),
                             label_MAE_days=float(err.mean()), label_within_7d=float((err <= 7).mean()),
                             selection_domain="src_company_holdout", target_used=False, measurement_version="t9-review-source-v1"))
            print(rows[-1], flush=True)
    pd.DataFrame(rows).to_csv(RES / "source_review.csv", index=False)


if __name__ == "__main__":
    main()
