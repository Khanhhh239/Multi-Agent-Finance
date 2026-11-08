#!/usr/bin/env python3
"""G15 — T9 v2 theo đăng ký trước `docs/03_Evaluation/G15_T9_V2_PREREG.md`.

  python scripts/sprint5/t9_v2.py --build-tgt3   # sinh tgt3 (chỉ sau khi tài liệu đăng ký trước đã commit)
  python scripts/sprint5/t9_v2.py                # chọn trên nguồn, đo một lần trên tgt3 + bộ phụ
Đầu ra: outputs/t9/v2/{source_grid.csv, source_methods.csv, choice.json, target_metrics.csv}
"""
import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "scripts" / "sprint5"))
from agent1.paths import OUT, SYNTH  # noqa: E402
from agent1.models.t9_fast import fast_source, reconcile_arrays, concatenate_parts  # noqa: E402
from agent1.models.t9_recon import Reconciler  # noqa: E402
from run_e2e_protocol import source_reconciler  # noqa: E402
from run_t9_hardcases import load_observed  # noqa: E402
from run_t9 import evaluate  # noqa: E402
from t9_guard import hazard_prior, prepare  # noqa: E402

RES = OUT / "t9" / "v2"
VERSION = "T9-v2-prereg-subsetcap-fifo"
TAU = .5
VARIANTS = [dict(cap=c, hazard=h, fifo=f) for c in (None, 2, 1) for h in (True, False) for f in (False, True)]
P_ELIGIBLE, P_METHOD, AUTO_MIN, MIN_LINKS = .975, .95, .6, 30
TARGETS = ("tgt3", "tgt2", "hc_retention", "hc_cod_realistic", "tgt")


def name(v):
    return f"cap={v['cap'] or 'none'}|hazard={'on' if v['hazard'] else 'off'}|fifo={'on' if v['fifo'] else 'off'}"


def build_tgt3():
    from agent1.synth.world import WorldConfig, generate
    if (SYNTH / "tgt3" / "invoices.parquet").exists():
        raise SystemExit("tgt3 đã tồn tại — không sinh lại")
    base = json.loads((SYNTH / "tgt" / "config.json").read_text(encoding="utf-8"))
    allowed = {f.name for f in fields(WorldConfig)}
    cfg = {k: v for k, v in base.items() if k in allowed}
    cfg.update(name="tgt3", seed=7310, n_firms=30, write_xml=0)
    for key in ("posting_mode_p", "payrun_p", "memo_invoice_no_p"):
        if key in cfg:
            cfg[key] = tuple(cfg[key])
    generate(WorldConfig(**cfg), verbose=False)
    (SYNTH / "tgt3" / "SEALED.txt").write_text(
        "tgt3 niêm phong 22/10/2026 cho G15 T9 v2 (docs/03_Evaluation/G15_T9_V2_PREREG.md); đo một lần.\n", encoding="utf-8")


def links_for(source, prepared, v):
    return concatenate_parts([reconcile_arrays(source, t, i, c, assignments=a, tau_auto=TAU, allocation_policy=p,
                                               max_guess_subset=v["cap"], hazard_subsets=v["hazard"], fifo_allocation=v["fifo"])[0]
                              for t, i, c, a, p in prepared])


def per_method(links, pay):
    truth = set(zip(pay.txn_id, pay.invoice_id))
    ok = pd.Series([(t, i) in truth for t, i in zip(links.txn_id, links.invoice_id)], index=links.index)
    return links.assign(ok=ok).groupby("method").ok.agg(["size", "mean"]).rename(columns={"size": "n_links", "mean": "precision"})


def select(source, model, label_end):
    heldout = set(pd.read_parquet(SYNTH / "src/firms.parquet").firm_id) - set(source.provenance["training_firms"])
    bank, inv, cust, pay = load_observed("src", "2024-01-01", "2024-06-30")
    bank = bank[bank.firm_id.isin(heldout)]; inv = inv[inv.firm_id.isin(heldout)]; cust = cust[cust.firm_id.isin(heldout)]
    pay = pay[pay.txn_id.isin(bank.txn_id)]
    prepared = prepare(source, bank, inv, cust, model, label_end)
    rows, methods = [], []
    for v in VARIANTS:
        links = links_for(source, prepared, v)
        m = evaluate(name(v), links, bank, inv, pay)
        pm = per_method(links, pay)
        worst = pm[pm.n_links >= MIN_LINKS].precision.min()
        m.update(variant=name(v), auto_txn_coverage=links.txn_id.nunique() / len(bank), worst_method_precision=worst,
                 eligible=bool(m["link_precision"] >= P_ELIGIBLE and worst >= P_METHOD and links.txn_id.nunique() / len(bank) >= AUTO_MIN),
                 selection_domain="src_company_holdout", target_used=False, measurement_version=VERSION)
        rows.append(m); methods.append(pm.reset_index().assign(variant=name(v)))
        print("src", name(v), "P", round(m["link_precision"], 3), "R", round(m["link_recall"], 3), "F1", round(m["link_f1"], 3),
              "auto", round(m["auto_txn_coverage"], 3), "worst", round(worst, 3), "eligible", m["eligible"], flush=True)
        pd.DataFrame(rows).to_csv(RES / "source_grid.csv", index=False)
        pd.concat(methods).to_csv(RES / "source_methods.csv", index=False)
    grid = pd.DataFrame(rows)
    ok = grid[grid.eligible]
    fallback = ok.empty
    if fallback:
        ok = grid[(grid.link_precision >= .95) & (grid.auto_txn_coverage >= AUTO_MIN)]
    best = ok.sort_values(["link_f1", "auto_txn_coverage"], ascending=False).iloc[0]
    chosen = VARIANTS[[name(v) for v in VARIANTS].index(best.variant)]
    choice = dict(variant=best.variant, **chosen, tau=TAU, fallback_rule=fallback, source_precision=float(best.link_precision),
                  source_f1=float(best.link_f1), source_auto=float(best.auto_txn_coverage), target_used=False)
    (RES / "choice.json").write_text(json.dumps(choice, indent=2), encoding="utf-8")
    print("CHOSEN ON SOURCE:", choice, flush=True)
    return chosen


def measure(source, model, label_end, chosen):
    rows = []
    for world in TARGETS:
        if not (SYNTH / world / "invoices.parquet").exists():
            print("bỏ qua", world, "(chưa có)"); continue
        bt, it, ct, pt = load_observed(world, "2024-07-01", "2025-06-29")
        prep = prepare(source, bt, it, ct, model, label_end)
        runs = {"R1": None, "R2": None, "Deployment sprint3": dict(cap=None, hazard=True, fifo=False), "T9 v2 (source-selected)": chosen}
        for label, v in runs.items():
            if v is None:
                links = concatenate_parts([reconcile_arrays(Reconciler(), t, i, c, tau_auto=.9,
                                                            rule_mode="amount" if label == "R1" else "memo")[0] for t, i, c, *_ in prep])
            else:
                links = links_for(source, prep, v)
            m = evaluate(label, links, bt, it, pt)
            m.update(world=world, variant=name(v) if v else label, auto_txn_coverage=links.txn_id.nunique() / len(bt),
                     selected_on="src_company_holdout", test_used_for_selection=False, measurement_version=VERSION)
            rows.append(m)
            print(world, label, "P", round(m["link_precision"], 3), "R", round(m["link_recall"], 3), "F1", round(m["link_f1"], 3),
                  "auto", round(m["auto_txn_coverage"], 3), "MAE", round(m["pay_date_MAE_est_days"], 2), flush=True)
            pd.DataFrame(rows).to_csv(RES / "target_metrics.csv", index=False)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--build-tgt3", action="store_true"); a = ap.parse_args()
    RES.mkdir(parents=True, exist_ok=True)
    if a.build_tgt3:
        build_tgt3(); return
    source = fast_source(source_reconciler(OUT / "t9/sprint3/source_reconciler", require_training_firms=True))
    model, label_end = hazard_prior()
    chosen = select(source, model, label_end)
    measure(source, model, label_end, chosen)


if __name__ == "__main__":
    main()
