#!/usr/bin/env python3
"""Nhãn mềm T9 — đo CHỈ TRÊN NGUỒN (DN giữ lại, 2024H1): độ phủ và sai số ngày của nhãn mềm so với ngày trả thật.

Đầu ra: outputs/t9/soft/source_soft_labels.csv
Chỉ số: share_paid_labelled (hoá đơn đã trả có nhãn, T9 v2 một mình vs + mềm), MAE ngày và tỉ lệ sai ≤ 3/7/14 ngày của riêng phần nhãn mềm.
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
from agent1.api_surface import build_bank_labels  # noqa: E402
from run_e2e_protocol import source_reconciler  # noqa: E402
from run_t9_hardcases import load_observed  # noqa: E402
from t9_guard import hazard_prior, prepare  # noqa: E402

RES = OUT / "t9" / "soft"


def main():
    RES.mkdir(parents=True, exist_ok=True)
    v2 = json.loads((OUT / "t9/v2/choice.json").read_text(encoding="utf-8"))
    source = fast_source(source_reconciler(OUT / "t9/sprint3/source_reconciler", require_training_firms=True))
    heldout = set(pd.read_parquet(SYNTH / "src/firms.parquet").firm_id) - set(source.provenance["training_firms"])
    model, label_end = hazard_prior()
    bank, inv, cust, _ = load_observed("src", "2024-01-01", "2024-06-30")
    bank = bank[bank.firm_id.isin(heldout)]; inv = inv[inv.firm_id.isin(heldout)]; cust = cust[cust.firm_id.isin(heldout)]
    prep = prepare(source, bank, inv, cust, model, label_end)
    links_parts, asg_parts = [], []
    for t, i, c, a, p in prep:
        links_parts.append(reconcile_arrays(source, t, i, c, assignments=a, tau_auto=.5, allocation_policy=p,
                                            max_guess_subset=v2["cap"], hazard_subsets=v2["hazard"], fifo_allocation=v2["fifo"])[0])
        asg_parts.append(a)
    links = concatenate_parts(links_parts); asg = pd.concat(asg_parts)
    truth_full = pd.read_parquet(SYNTH / "src/invoices.parquet", columns=["invoice_id", "paid_date_true"]).set_index("invoice_id").paid_date_true
    inv = inv.assign(true=inv.invoice_id.map(truth_full))
    # chỉ xét hoá đơn thật sự được trả TRONG cửa sổ giao dịch
    paid = inv[inv.true.between("2024-01-01", "2024-06-30")]
    t9 = build_bank_labels(inv, links).set_index("invoice_id").paid_date_est
    rows = []
    for conf in (0.5, 0.8, 0.95):
        soft = soft_fifo_labels(links, bank, inv, asg, min_confidence=conf)
        ids = paid.invoice_id
        has_t9 = ids.map(t9).notna(); has_soft = ids.map(soft).notna() & ~has_t9
        sel = ids[has_soft].to_numpy()
        err = pd.Series((pd.to_datetime(soft.reindex(sel).to_numpy()) - pd.to_datetime(paid.set_index("invoice_id").true.reindex(sel).to_numpy())).days).abs()
        rows.append(dict(min_confidence=conf, n_paid=len(ids), share_labelled_t9_only=float(has_t9.mean()),
                         share_labelled_t9_plus_soft=float((has_t9 | has_soft).mean()), n_soft=int(has_soft.sum()),
                         soft_MAE_days=float(err.mean()), soft_median_abs_days=float(err.median()),
                         soft_within_3d=float((err <= 3).mean()), soft_within_7d=float((err <= 7).mean()),
                         soft_within_14d=float((err <= 14).mean()), selection_domain="src_company_holdout", target_used=False,
                         measurement_version="t9-soft-fifo-source-v1"))
        print(rows[-1], flush=True)
    pd.DataFrame(rows).to_csv(RES / "source_soft_labels.csv", index=False)


if __name__ == "__main__":
    main()
