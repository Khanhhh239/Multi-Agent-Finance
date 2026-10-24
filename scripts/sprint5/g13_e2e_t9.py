#!/usr/bin/env python3
"""G13 trên tgt3 với nhãn T9 ước lượng (đăng ký trước: docs/03_Evaluation/G13_E2E_T9V2_PREREG.md).

  python scripts/sprint5/g13_e2e_t9.py --build    # dựng thế giới quan sát cho T9 sprint3 và T9 v2 (nhanh)
  python scripts/sprint5/g13_e2e_t9.py --run v2   # chạy T6 cho một nhánh: v2 | sprint3 | oracle (~30-45 phút mỗi nhánh)
  python scripts/sprint5/g13_e2e_t9.py --score    # chấm chính sách ĐÓNG BĂNG trên các nhánh đã chạy
Đầu ra: outputs/g13/e2e_tgt3/<nhánh>/..., outputs/g13/e2e_tgt3/alert_policy_tgt3.csv
"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "scripts" / "sprint5"))
from agent1.paths import OUT, SYNTH  # noqa: E402
from agent1.eval.alert_policy import fit_isotonic, policy_metrics, firm_bootstrap  # noqa: E402

WORLD = os.environ.get("G13_WORLD", "tgt3")          # tgt3 (mặc định) hoặc tgt5 (docs/03_Evaluation/G13_SOFT_LABELS_PREREG.md)
RES = OUT / "g13" / f"e2e_{WORLD}"
MODEL = "MC-copula-t (T1+T4+T5)"
VISIBLE = pd.Timestamp("2023-07-01")
VERSION = "g13-e2e-t9v2-tgt3-v1"
SOFT_CONFIDENCE = 0.8     # đăng ký trước (G13_SOFT_LABELS_PREREG.md mục 1)
REVIEW_POLICY = "leftover"  # chọn trên nguồn (G13_REVIEW_QUEUE_PREREG.md mục 1)
VARIANTS = {"v2rev5": "T9 v2 + duyệt 5/tuần + nhãn mềm", "v2rev2": "T9 v2 + duyệt 2/tuần + nhãn mềm", "v2soft": "T9 v2 + nhãn mềm", "v2": "T9 v2", "sprint3": "T9 sprint3", "oracle": "nhãn thật", "v2fill": "T9 v2 + nhãn thật cho phần thiếu (ablation)",
            "v2fill50": "T9 v2 + nhãn thật cho 50% phần thiếu", "v2fill80": "T9 v2 + nhãn thật cho 80% phần thiếu"}


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
    cfg = dict(cap=v2["cap"], hazard=v2["hazard"], fifo=v2["fifo"]) if variant.startswith("v2") else dict(cap=None, hazard=True, fifo=False)
    source = fast_source(source_reconciler(OUT / "t9/sprint3/source_reconciler", require_training_firms=True))
    model, label_end = hazard_prior()
    end = str(pd.read_parquet(SYNTH / WORLD / "bank_txns.parquet", columns=["value_date"]).value_date.max().date())
    bank, inv, cust, _ = load_observed(WORLD, str(VISIBLE.date()), end)
    inv = inv[inv.issue_date >= VISIBLE]
    prep = prepare(source, bank, inv, cust, model, label_end)
    links = links_for(source, prep, cfg)
    asg = pd.concat([a for *_, a, _ in prep])
    review_stats = None
    if variant.startswith("v2rev"):
        # B1: kế toán duyệt b giao dịch/DN/tuần theo chính sách đã chọn trên nguồn (leftover), người duyệt hoàn hảo (cận trên).
        from agent1.models.t9_review_queue import simulate_review
        truth = pd.read_parquet(SYNTH / WORLD / "payments.parquet", columns=["txn_id", "invoice_id", "amount", "pay_date_true"])
        truth = truth[truth.txn_id.isin(bank.txn_id)]
        links, review_stats = simulate_review(links, bank, truth, per_week=int(variant[len("v2rev"):]), policy=REVIEW_POLICY)
        print(variant, "review", review_stats, flush=True)
    original = SYNTH / WORLD
    invoices = pd.read_parquet(original / "invoices.parquet")
    invoices = invoices[invoices.issue_date >= VISIBLE].copy()
    labelled = build_bank_labels(invoices, links)
    labelled["paid_date_true"] = labelled.pop("paid_date_est")      # tên cột nội bộ T1; giá trị là nhãn ƯỚC LƯỢNG
    if variant == "v2soft" or variant.startswith("v2rev"):
        # Nhãn mềm: chỉ cho hoá đơn T9 bỏ sót; không thay liên kết T9. Ngày = ngày giao dịch tất toán theo phân bổ FIFO theo khách.
        from agent1.models.t9_soft_labels import soft_fifo_labels
        soft = soft_fifo_labels(links, bank, inv, asg, min_confidence=SOFT_CONFIDENCE)
        missing = labelled.paid_date_true.isna()
        labelled.loc[missing, "paid_date_true"] = labelled.loc[missing, "invoice_id"].map(soft)
        print("soft labels added", int(labelled.loc[missing, "paid_date_true"].notna().sum()), flush=True)
    if variant.startswith("v2fill"):
        # ABLATION chẩn đoán (ghi thêm sau khi có kết quả, không phải cổng): giữ nhãn T9 v2, điền ngày trả THẬT vào một phần
        # hoá đơn đang thiếu nhãn (v2fill = tất cả; v2fill50 = ngẫu nhiên 50% phần thiếu, seed 7). Mô phỏng kế toán duyệt hàng chờ.
        frac = int(variant[len("v2fill"):] or 100) / 100
        truth = invoices.set_index("invoice_id").paid_date_true
        missing = labelled.paid_date_true.isna() & labelled.invoice_id.map(truth).notna()
        pick = missing & (np.random.default_rng(7).random(len(labelled)) < frac)
        labelled.loc[pick, "paid_date_true"] = labelled.loc[pick, "invoice_id"].map(truth)
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


def build_world():
    """Sinh bộ đích niêm phong mới (chỉ sau khi đăng ký trước đã commit). Cấu hình = tgt, seed theo G13_SEED."""
    from agent1.synth.world import WorldConfig, generate
    from dataclasses import fields
    if (SYNTH / WORLD / "invoices.parquet").exists():
        raise SystemExit(f"{WORLD} đã tồn tại — không sinh lại")
    base = json.loads((SYNTH / "tgt" / "config.json").read_text(encoding="utf-8"))
    allowed = {f.name for f in fields(WorldConfig)}
    cfg = {k: v for k, v in base.items() if k in allowed}
    cfg.update(name=WORLD, seed=int(os.environ["G13_SEED"]), n_firms=30, write_xml=0)
    for key in ("posting_mode_p", "payrun_p", "memo_invoice_no_p"):
        if key in cfg:
            cfg[key] = tuple(cfg[key])
    generate(WorldConfig(**cfg), verbose=False)
    (SYNTH / WORLD / "SEALED.txt").write_text(f"{WORLD} niêm phong 23/10/2026; đo một lần (G13_SOFT_LABELS_PREREG.md).\n", encoding="utf-8")


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
    out = pd.DataFrame(rows); out.to_csv(RES / f"alert_policy_{WORLD}.csv", index=False)
    print(out[["variant", "n_events", "detected_at_least_4w", "detected_ci_low", "detected_ci_high", "median_lead_weeks",
               "false_alarms_per_firm_year", "fa_ci_low", "fa_ci_high", "brier_13w"]].round(3).to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true"); ap.add_argument("--run", default=""); ap.add_argument("--score", action="store_true")
    ap.add_argument("--build-variant", default=""); ap.add_argument("--build-world", action="store_true")
    a = ap.parse_args()
    RES.mkdir(parents=True, exist_ok=True)
    if a.build_world:
        build_world()
    if a.build_variant:
        build(a.build_variant)
    if a.build:
        for v in (os.environ.get("G13_BUILD", "v2,sprint3").split(",")):
            build(v)
    if a.run:
        run(a.run)
    if a.score:
        score()


if __name__ == "__main__":
    main()
