#!/usr/bin/env python3
"""G15 — lớp chặn "cần bằng chứng độc lập" cho liên kết qua mô hình khách có độ tin cậy thấp.

Chẩn đoán (docs/03_Evaluation/T9_RECALL_DIAGNOSIS.md): trên tgt precision 0,925 < 0,95; nguồn mất precision chính là
`wrong_customer`. Ý tưởng: dưới ngưỡng g, chỉ tự động ghép khi số HĐ đã chọn có trong nội dung CK hoặc tên người chuyển khớp
tên khách (≥ 90); còn lại vào hàng chờ.

Giao thức (giống `scripts/sprint1/t9_source_diagnostics.py`, cùng DN nguồn giữ lại, cùng giai đoạn 2024H1):
  - lưới: biến thể candidate (chính sách đang triển khai) × g ∈ {none, .7, .8, .9, .95} × τ ∈ {.5, .6, .7, .8, .9}
  - chọn trên NGUỒN: precision ≥ .95 và tự động ≥ .6, tối đa F1 (giống quy tắc cũ, đăng ký trước)
  - đo MỘT LẦN trên tgt, hc_retention, hc_cod_realistic với lựa chọn đã đóng băng.
Đầu ra: outputs/t9/sprint5/{source_grid.csv, choice.json, target_metrics.csv}
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from agent1.paths import OUT, SYNTH  # noqa: E402
from agent1.models.t9_fast import fast_source, reconcile_arrays, concatenate_parts  # noqa: E402
from agent1.models.t9_source_policy import ObservedAllocationPolicy, LedgerHazardPrior  # noqa: E402
from run_e2e_protocol import source_reconciler  # noqa: E402
from run_t9_hardcases import load_observed  # noqa: E402
from run_t9 import evaluate  # noqa: E402

TAUS = (.5, .6, .7, .8, .9)
GUARDS = (None, .7, .8, .9, .95)
RES = OUT / "t9" / "sprint5"
VERSION = "T9-corroboration-guard-v1"


def hazard_prior():
    import lightgbm as lgb
    from agent1.models import t1
    model_dir = OUT / "t1/fullweek_A/2023-07-03"
    protocol = json.loads((model_dir / "protocol.json").read_text(encoding="utf-8"))
    model = t1.HazardGBM(); model.booster = lgb.Booster(model_file=str(model_dir / "model.txt"))
    return model, protocol["training_label_end"]


def prepare(source, bank, inv, cust, model, label_end):
    out = []
    for fid, transactions in bank.groupby("firm_id"):
        invoices = inv[inv.firm_id == fid]; customers = cust[cust.firm_id == fid]
        assignments = source.assign_customers(source.candidates(transactions, invoices, customers))
        out.append((transactions, invoices, customers, assignments,
                    ObservedAllocationPolicy(LedgerHazardPrior(invoices, model, label_end))))
    return out


def run(source, prepared, bank, inv, pay, tau, guard):
    links = concatenate_parts([reconcile_arrays(source, t, i, c, assignments=a, tau_auto=tau, allocation_policy=p,
                                                corroborate_below=guard)[0] for t, i, c, a, p in prepared])
    m = evaluate("Deployment + guard" if guard else "Deployment", links, bank, inv, pay)
    m.update(tau=tau, guard=guard if guard is not None else "none", auto_txn_coverage=links.txn_id.nunique() / len(bank))
    return m


def main():
    RES.mkdir(parents=True, exist_ok=True)
    source = fast_source(source_reconciler(OUT / "t9/sprint3/source_reconciler", require_training_firms=True))
    heldout = set(pd.read_parquet(SYNTH / "src/firms.parquet").firm_id) - set(source.provenance["training_firms"])
    model, label_end = hazard_prior()
    bank, inv, cust, pay = load_observed("src", "2024-01-01", "2024-06-30")
    bank = bank[bank.firm_id.isin(heldout)]; inv = inv[inv.firm_id.isin(heldout)]
    cust = cust[cust.firm_id.isin(heldout)]; pay = pay[pay.txn_id.isin(bank.txn_id)]
    prepared = prepare(source, bank, inv, cust, model, label_end)
    rows = []
    for guard in GUARDS:
        for tau in TAUS:
            if guard is not None and guard < tau:
                continue
            rows.append(dict(run(source, prepared, bank, inv, pay, tau, guard), selection_domain="src_company_holdout",
                             target_used=False, measurement_version=VERSION))
            r = rows[-1]
            print("src guard", r["guard"], "tau", tau, "P", round(r["link_precision"], 3), "F1", round(r["link_f1"], 3),
                  "auto", round(r["auto_txn_coverage"], 3), flush=True)
            pd.DataFrame(rows).to_csv(RES / "source_grid.csv", index=False)
    grid = pd.DataFrame(rows)
    ok = grid[(grid.link_precision >= .95) & (grid.auto_txn_coverage >= .6)]
    if ok.empty:
        print("Không có cấu hình đạt precision>=.95 và tự động>=.6 trên nguồn; dừng, không đo đích.")
        (RES / "choice.json").write_text(json.dumps(dict(selected=None)), encoding="utf-8")
        return
    best = ok.sort_values(["link_f1", "auto_txn_coverage"], ascending=False).iloc[0]
    guard = None if best.guard == "none" else float(best.guard)
    choice = dict(tau=float(best.tau), guard=guard, source_precision=float(best.link_precision),
                  source_f1=float(best.link_f1), source_auto=float(best.auto_txn_coverage), target_used=False)
    (RES / "choice.json").write_text(json.dumps(choice, indent=2), encoding="utf-8")
    print("chosen on source:", choice, flush=True)
    targets = []
    for world in ("tgt", "hc_retention", "hc_cod_realistic"):
        bt, it, ct, pt = load_observed(world, "2024-07-01", "2025-06-29")
        prep = prepare(source, bt, it, ct, model, label_end)
        for g in ([None, guard] if guard is not None else [None]):
            m = run(source, prep, bt, it, pt, choice["tau"], g)
            m.update(world=world, selected_on="src_company_holdout", test_used_for_selection=False, measurement_version=VERSION)
            targets.append(m)
            print(world, "guard", m["guard"], "P", round(m["link_precision"], 3), "R", round(m["link_recall"], 3),
                  "F1", round(m["link_f1"], 3), "auto", round(m["auto_txn_coverage"], 3),
                  "MAE", round(m["pay_date_MAE_est_days"], 2), flush=True)
            pd.DataFrame(targets).to_csv(RES / "target_metrics.csv", index=False)


if __name__ == "__main__":
    main()
