#!/usr/bin/env python3
"""Chẩn đoán (KHÔNG chọn tham số): precision theo phương pháp tạo liên kết của cấu hình T9 đang triển khai, trên src giữ lại và tgt.

Trả lời: liên kết sai đến từ quy tắc R1 (số tiền duy nhất), R2 (số HĐ), nhánh ML hay chính sách phân bổ?
Đầu ra: outputs/t9/sprint5/method_breakdown.csv
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "scripts" / "sprint5"))
from agent1.paths import OUT, SYNTH  # noqa: E402
from agent1.models.t9_fast import fast_source, reconcile_arrays, concatenate_parts  # noqa: E402
from run_e2e_protocol import source_reconciler  # noqa: E402
from run_t9_hardcases import load_observed  # noqa: E402
from t9_guard import hazard_prior, prepare  # noqa: E402


def breakdown(world, links, pay, assignments):
    truth = set(zip(pay.txn_id, pay.invoice_id))
    true_cust = pay.drop_duplicates("txn_id").set_index("txn_id").invoice_id
    links = links.assign(correct=[(t, i) in truth for t, i in zip(links.txn_id, links.invoice_id)])
    conf = pd.concat(assignments).set_index("txn_id").confidence if assignments else pd.Series(dtype=float)
    links["cust_conf"] = links.txn_id.map(conf)
    rows = []
    for method, g in links.groupby("method"):
        rows.append(dict(world=world, method=method, n_links=len(g), precision=g.correct.mean(),
                         share_of_false=(~g.correct).sum() / max((~links.correct).sum(), 1),
                         median_customer_conf=g.cust_conf.median(), share_conf_below_95=(g.cust_conf < .95).mean()))
    return rows


def main():
    choice = json.loads((OUT / "t9/sprint5/choice.json").read_text(encoding="utf-8"))
    source = fast_source(source_reconciler(OUT / "t9/sprint3/source_reconciler", require_training_firms=True))
    heldout = set(pd.read_parquet(SYNTH / "src/firms.parquet").firm_id) - set(source.provenance["training_firms"])
    model, label_end = hazard_prior()
    rows = []
    for world, lo, hi in (("src", "2024-01-01", "2024-06-30"), ("tgt", "2024-07-01", "2025-06-29")):
        bank, inv, cust, pay = load_observed(world, lo, hi)
        if world == "src":
            bank = bank[bank.firm_id.isin(heldout)]; inv = inv[inv.firm_id.isin(heldout)]; cust = cust[cust.firm_id.isin(heldout)]
        pay = pay[pay.txn_id.isin(bank.txn_id)]
        prep = prepare(source, bank, inv, cust, model, label_end)
        links = concatenate_parts([reconcile_arrays(source, t, i, c, assignments=a, tau_auto=choice["tau"], allocation_policy=p,
                                                    corroborate_below=choice["guard"])[0] for t, i, c, a, p in prep])
        rows += breakdown(world, links, pay, [a for *_, a, _ in prep])
        print(pd.DataFrame(rows).round(3).to_string(index=False), flush=True)
    pd.DataFrame(rows).to_csv(OUT / "t9/sprint5/method_breakdown.csv", index=False)


if __name__ == "__main__":
    main()
