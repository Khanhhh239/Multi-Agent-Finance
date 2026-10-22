#!/usr/bin/env python3
"""G13 trên tgt3 với nhãn T9 ước lượng (đăng ký trước: docs/03_Evaluation/G13_E2E_T9V2_PREREG.md).

  python scripts/sprint5/g13_e2e_t9.py --build    # dựng thế giới quan sát cho T9 sprint3 và T9 v2 (nhanh)
  python scripts/sprint5/g13_e2e_t9.py --run v2   # chạy T6 cho một nhánh: v2 | sprint3 | oracle (~30-45 phút mỗi nhánh)
  python scripts/sprint5/g13_e2e_t9.py --score    # chấm chính sách ĐÓNG BĂNG trên các nhánh đã chạy
Đầu ra: outputs/g13/e2e_tgt3/<nhánh>/..., outputs/g13/e2e_tgt3/alert_policy_tgt3.csv
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "scripts" / "sprint5"))
from agent1.paths import OUT, SYNTH  # noqa: E402
from agent1.eval.alert_policy import fit_isotonic, policy_metrics, firm_bootstrap  # noqa: E402

WORLD = "tgt3"
RES = OUT / "g13" / "e2e_tgt3"
MODEL = "MC-copula-t (T1+T4+T5)"
VISIBLE = pd.Timestamp("2023-07-01")
VERSION = "g13-e2e-t9v2-tgt3-v1"
VARIANTS = {"v2": "T9 v2", "sprint3": "T9 sprint3", "oracle": "nhãn thật", "v2fill": "T9 v2 + nhãn thật cho phần thiếu (ablation)"}


def obs_name(variant):
    return f"g13obs_{WORLD}_{variant}"


def build(variant):
    from agent1.api_surface import build_bank_labels
    from agent1.models.t9_fast import fast_source
    from run_e2e_protocol import source_reconciler, observed_promises
    from run_t9_hardcases import load_observed
    from t9_guard import hazard_prior, prepare
    from t9_v2 import links_for
    v2 = json.loads((OUT / "t9/v2/choice.json").read_text(encoding="utf-8"))
    cfg = dict(cap=v2["cap"], hazard=v2["hazard"], fifo=v2["fifo"]) if variant in ("v2", "v2fill") else dict(cap=None, hazard=True, fifo=False)
    source = fast_source(source_reconciler(OUT / "t9/sprint3/source_reconciler", require_training_firms=True))
    model, label_end = hazard_prior()
    end = str(pd.read_parquet(SYNTH / WORLD / "bank_txns.parquet", columns=["value_date"]).value_date.max().date())
    bank, inv, cust, _ = load_observed(WORLD, str(VISIBLE.date()), end)
    inv = inv[inv.issue_date >= VISIBLE]
    prep = prepare(source, bank, inv, cust, model, label_end)
    links = links_for(source, prep, cfg)
    original = SYNTH / WORLD
    invoices = pd.read_parquet(original / "invoices.parquet")
    invoices = invoices[invoices.issue_date >= VISIBLE].copy()
    labelled = build_bank_labels(invoices, links)
    labelled["paid_date_true"] = labelled.pop("paid_date_est")      # tên cột nội bộ T1; giá trị là nhãn ƯỚC LƯỢNG
    if variant == "v2fill":
        # ABLATION chẩn đoán (ghi thêm sau khi có kết quả, không phải cổng): giữ nhãn T9 v2, điền ngày trả THẬT vào hoá đơn đang thiếu nhãn.
        truth = invoices.set_index("invoice_id").paid_date_true
        missing = labelled.paid_date_true.isna()
        labelled.loc[missing, "paid_date_true"] = labelled.loc[missing, "invoice_id"].map(truth)
    labelled["writeoff_date"] = pd.NaT; labelled["ledger_clear_date"] = pd.NaT
    labelled["is_bad_debt"] = False; labelled["credit_note"] = 0.; labelled["dispute"] = False; labelled["partial"] = False
    target = SYNTH / obs_name(variant); target.mkdir(exist_ok=True)
    labelled.to_parquet(target / "invoices.parquet", index=False)
    payments = links.rename(columns={"est_pay_date": "pay_date_true"}).copy()
    payments["firm_id"] = payments.txn_id.map(bank.set_index("txn_id").firm_id)
    payments["ledger_post_date"] = payments.pay_date_true; payments["ledger_invoice_id"] = payments.invoice_id
    payments["payment_id"] = [f"EST{i:08d}" for i in range(len(payments))]
    payments.to_parquet(target / "payments.parquet", index=False)
    promises = pd.read_parquet(original / "promises.parquet")
    promises = promises[promises.invoice_id.isin(labelled.invoice_id)]
    observed_promises(promises, labelled, links).to_parquet(target / "promises.parquet", index=False)
    bank.to_parquet(target / "bank_txns.parquet", index=False)
    firms = pd.read_parquet(original / "firms.parquet")
    for table in ("outflows", "daily_cash"):
        d = pd.read_parquet(original / f"{table}.parquet"); d[d.firm_id.isin(firms.firm_id)].to_parquet(target / f"{table}.parquet", index=False)
    pd.read_parquet(original / "customers.parquet")[["customer_id", "firm_id", "name", "short", "mst"]].to_parquet(target / "customers.parquet", index=False)
    firms[["firm_id", "name", "mst"]].to_parquet(target / "firms.parquet", index=False)
    n_true = int(labelled.paid_date_true.notna().sum())
    print(variant, "links", len(links), "invoices with estimated label", n_true, "of", len(labelled), flush=True)


def run(variant):
    import run_t6
    d = RES / variant; d.mkdir(parents=True, exist_ok=True)
    if variant == "oracle":
        run_t6.main(target_world=WORLD, evaluation_world=WORLD, result_dir=d, source_budget=40000, n_weeks=52, label_mode="oracle_bank")
    else:
        run_t6.main(target_world=obs_name(variant), evaluation_world=WORLD, result_dir=d, source_budget=40000, n_weeks=52,
                    label_mode=f"estimated_T9_{variant}")


def score():
    ch = json.loads((OUT / "g13/policy_choice.json").read_text(encoding="utf-8"))[f"{MODEL}|isotonic"]
    src = pd.read_csv(OUT / "g13/src_backtest/t6_shortfall_predictions.csv", parse_dates=["cutoff"])
    s = src[src.model == MODEL]; iso = fit_isotonic(s["y13"], s["p13"])
    cash = pd.read_parquet(SYNTH / WORLD / "daily_cash.parquet", columns=["firm_id", "date", "balance"])
    rows = []
    for v, label in VARIANTS.items():
        f = RES / v / "t6_shortfall_predictions.csv"
        if not f.exists():
            continue
        t = pd.read_csv(f, parse_dates=["cutoff"]); t = t[t.model == MODEL].reset_index(drop=True)
        t = t.assign(q=np.asarray(iso.predict(t["p13"]), float))
        m = policy_metrics(t, cash, "q", ch["tau"], ch["k"], 91)
        ci = firm_bootstrap(t, cash, "q", ch["tau"], ch["k"], 91)
        rows.append(dict(variant=label, world=WORLD, tau=ch["tau"], k=ch["k"], brier_13w=float(((t.q - t.y13) ** 2).mean()),
                         **m, **ci, policy_frozen_on="src", measurement_version=VERSION))
    out = pd.DataFrame(rows); out.to_csv(RES / "alert_policy_tgt3.csv", index=False)
    print(out[["variant", "n_events", "detected_at_least_4w", "detected_ci_low", "detected_ci_high", "median_lead_weeks",
               "false_alarms_per_firm_year", "fa_ci_low", "fa_ci_high", "brier_13w"]].round(3).to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true"); ap.add_argument("--run", default=""); ap.add_argument("--score", action="store_true")
    ap.add_argument("--build-variant", default="")
    a = ap.parse_args()
    RES.mkdir(parents=True, exist_ok=True)
    if a.build_variant:
        build(a.build_variant)
    if a.build:
        for v in ("v2", "sprint3"):
            build(v)
    if a.run:
        run(a.run)
    if a.score:
        score()


if __name__ == "__main__":
    main()
