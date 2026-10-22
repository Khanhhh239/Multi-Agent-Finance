#!/usr/bin/env python3
"""T9 — phân tích liên kết sai CHỈ TRÊN NGUỒN (DN giữ lại, 2024H1) để thiết kế biến thể trước khi có tgt3.

Với các liên kết do phương pháp "đoán" (ML_subset, hazard_weighted_subset), tính precision theo tầng:
  số HĐ trong tổ hợp, điểm tên người chuyển, nội dung CK có chuỗi số, số HĐ đang mở của khách được gán.
Đầu ra: outputs/t9/sprint5/source_strata.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "scripts" / "sprint5"))
from agent1.paths import OUT, SYNTH  # noqa: E402
from agent1.models.t9_fast import fast_source, reconcile_arrays, concatenate_parts  # noqa: E402
from agent1.models.t9_recon import memo_numbers  # noqa: E402
from run_e2e_protocol import source_reconciler  # noqa: E402
from run_t9_hardcases import load_observed  # noqa: E402
from t9_guard import hazard_prior, prepare  # noqa: E402


def main():
    source = fast_source(source_reconciler(OUT / "t9/sprint3/source_reconciler", require_training_firms=True))
    heldout = set(pd.read_parquet(SYNTH / "src/firms.parquet").firm_id) - set(source.provenance["training_firms"])
    model, label_end = hazard_prior()
    bank, inv, cust, pay = load_observed("src", "2024-01-01", "2024-06-30")
    bank = bank[bank.firm_id.isin(heldout)]; inv = inv[inv.firm_id.isin(heldout)]; cust = cust[cust.firm_id.isin(heldout)]
    pay = pay[pay.txn_id.isin(bank.txn_id)]
    prep = prepare(source, bank, inv, cust, model, label_end)
    links = concatenate_parts([reconcile_arrays(source, t, i, c, assignments=a, tau_auto=.5, allocation_policy=p)[0]
                               for t, i, c, a, p in prep])
    truth = set(zip(pay.txn_id, pay.invoice_id))
    links["correct"] = [(t, i) in truth for t, i in zip(links.txn_id, links.invoice_id)]
    assign = pd.concat([a for *_, a, _ in prep]).set_index("txn_id")
    memo = bank.set_index("txn_id").memo.fillna("")
    links["subset_size"] = links.groupby("txn_id").invoice_id.transform("size").clip(upper=3)
    links["name_score"] = links.txn_id.map(assign.name_score).fillna(0)
    links["name_band"] = pd.cut(links.name_score, [-1, 60, 80, 90, 101], labels=["<60", "60-80", "80-90", ">=90"])
    links["memo_has_number"] = links.txn_id.map(lambda t: len(memo_numbers(memo.get(t, ""))) > 0)
    links["memo_n_no_hit"] = links.txn_id.map(assign.n_no_hit).fillna(0) > 0 if "n_no_hit" in assign else False
    rows = []
    guess = links[links.method.isin(["ML_subset", "hazard_weighted_subset"])]
    for method, g in guess.groupby("method"):
        for col in ("subset_size", "name_band", "memo_has_number", "memo_n_no_hit"):
            for level, h in g.groupby(col, observed=True):
                rows.append(dict(method=method, stratum=col, level=str(level), n_links=len(h), precision=h.correct.mean()))
        rows.append(dict(method=method, stratum="all", level="all", n_links=len(g), precision=g.correct.mean()))
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "t9/sprint5/source_strata.csv", index=False)
    print(out.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
