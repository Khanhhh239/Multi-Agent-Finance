"""Corrected v2 lifecycle: lock, accounting, learning curve, source selection, test."""
from __future__ import annotations

import argparse
import gc
import numpy as np
import pandas as pd
import lightgbm as lgb

from agent1.paths import ROOT,SYNTH
from agent1.models import t4_revenue as T4
from agent1.data.world_manifest import sha256_file,verify_world_manifest
from .lifecycle import fresh_worlds
from .scoring import research_decision
from .artifacts import verify_saved_run
from .data import PROTOCOL,read_json,prepare,build_caches,verify_preserved,write_json,write_csv,write_bytes_once,source_hashes
from .features import SnapshotBuilder,model_view
from .cash import revenue_history
from .train import train_candidates,load_model
from .evaluate import select_on_source,source_dependence,evaluate_bank
from .rollout import simulate_receipts
from .performance import MemoryMeter
from .verify import regression_audit


def train_t4(out,cohort,p):
    meta_file = out/"t4.json"
    if not meta_file.exists():
        xs,ys = [],[]
        for entry in cohort["worlds"]:
            if entry["role"]!="train":
                continue
            inv = pd.read_parquet(SYNTH/entry["name"]/"invoices.parquet")
            source = pd.read_parquet(out/"cache"/f"fit_{entry['name']}_anchors.parquet")
            for fid in sorted(source.firm_id.unique()):
                s = revenue_history(inv[inv.firm_id.eq(fid)],pd.Timestamp(p["t4"]["fit_end"]))
                x,y,_ = T4.make_rows(s.to_numpy(),s.index,True,range(20,len(s)-13,p["t4"]["origin_stride_weeks"]))
                if len(x):
                    xs.append(x)
                    ys.append(y)
        x,y = np.concatenate(xs),np.concatenate(ys)
        hashes = {}
        for q in T4.QS:
            model = lgb.train({"objective":"quantile","alpha":q,"learning_rate":.04,"num_leaves":31,
                "min_data_in_leaf":50,"verbose":-1,"seed":p["seed"],"num_threads":4,"deterministic":True,"force_col_wise":True},
                lgb.Dataset(x,y,feature_name=T4.FEATS),p["t4"]["rounds"])
            file = out/f"t4_q{int(q*100)}.txt"
            write_bytes_once(file,model.model_to_string().encode("utf-8"))
            hashes[file.name] = sha256_file(file)
        write_json(meta_file,{"rows":len(y),"fit_end":p["t4"]["fit_end"],"hashes":hashes,
                             "week_contract":"Tuesday-Monday, consistent train and inference"})
    meta = read_json(meta_file)
    if any(sha256_file(out/name)!=value for name,value in meta["hashes"].items()):
        raise ValueError("Changed shared T4 model")
    return {q:lgb.Booster(model_file=str(out/f"t4_q{int(q*100)}.txt")) for q in T4.QS}


def benchmark(out,cohort,p,selection):
    file = out/"latency.json"
    if file.exists():
        return read_json(file)
    model,_ = load_model(out,selection["anchor_budget"])
    world = next(e["name"] for e in cohort["worlds"] if e["role"]=="train")
    inv,pay,prom = (pd.read_parquet(SYNTH/world/f"{name}.parquet") for name in ("invoices","payments","promises"))
    cutoff = pd.Timestamp(p["evaluation_cutoffs"][0])
    view = model_view(SnapshotBuilder(inv,pay,prom).snapshot(cutoff),cutoff).sort_values("invoice_id")
    count = p["simulation"]["max_invoices"]
    if len(view)<count:
        raise ValueError("Not enough source origin invoices for benchmark")
    view = view.iloc[:count].reset_index(drop=True)
    del inv,pay,prom
    gc.collect()
    runs = []
    for mc in p["simulation"]["mc_seeds"]:
        with MemoryMeter() as meter:
            result = simulate_receipts(model,view,n=p["simulation"]["paths"],seed=mc,case="full_budget_benchmark",
                rho_firm=selection["rho"][0],rho_customer=selection["rho"][1],max_invoices=count,batch_rows=p["simulation"]["batch_rows"])
        runs.append({"mc_seed":mc,**meter.result(),"predicted_rows":result["predicted_rows"],"active_rows":result["active_rows"],
                     "max_feature_batch_rows":max((a["max_feature_batch_rows"] for a in result["audit"]),default=0)})
        print(f"benchmark seed {mc}: {meter.seconds:.2f}s, incremental RSS {(meter.peak-meter.baseline)/2**20:.1f} MiB",flush=True)
    value = {"paths":p["simulation"]["paths"],"invoices":count,"replicates":runs,
        "max_seconds":max(r["seconds"] for r in runs),"median_seconds":float(np.median([r["seconds"] for r in runs])),
        "empirical_p95_seconds_three_replicates":float(np.quantile([r["seconds"] for r in runs],.95)),
        "max_sampled_rss_increment_mib":max(r["rss_increment_sampled_mib"] for r in runs),
        "scope":"full 13-step collection; data loading/T4/T5 excluded; RSS sampled every 50ms, not a hard peak bound"}
    value["passed"] = value["max_seconds"]<=p["acceptance"]["max_latency_seconds_1000x2000"] and value["max_sampled_rss_increment_mib"]<=p["acceptance"]["max_rss_increment_mib"]
    write_json(file,value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage",choices=["prepare","cache","train","select","benchmark","source","fresh","all","saved"],default="all")
    args = parser.parse_args()
    p = read_json(PROTOCOL)
    existing = ROOT/p["output_directory"]
    if args.stage=="saved" or (args.stage=="all" and (existing/"decision.json").exists()
                                and source_hashes()!=read_json(existing/"source_hashes.json")):
        print(verify_saved_run(existing),flush=True)
        return
    out,cohort = prepare(p)
    regression_audit(out)
    if args.stage=="prepare":
        return
    build_caches(out,cohort,p)
    if args.stage=="cache":
        return
    train_candidates(out,cohort,p)
    if args.stage=="train":
        return
    selection = select_on_source(out,cohort,p)
    source_dependence(out,cohort,p,selection)
    if args.stage=="select":
        return
    timing = benchmark(out,cohort,p,selection)
    if args.stage=="benchmark":
        return
    if not timing["passed"] or not selection["source_gate_passed"]:
        integrity = verify_preserved(out)
        write_json(out/"verification.json",integrity)
        write_json(out/"decision.json",{"research_passed":False,"decision":"stop_before_fresh_test",
            "reason":"source AR gate or full-budget performance failed","source_gate":selection["source_gate_passed"],
            "performance_gate":timing["passed"],"service_changed":False,"product_gates_changed":False})
        return
    t4 = train_t4(out,cohort,p)
    if args.stage in ("source","all"):
        evaluate_bank(out,[e for e in cohort["worlds"] if e["role"]=="train"],p,selection,t4,"source_bank")
        if args.stage=="source":
            return
    # Model/parameters are selected and performance verified before test Worlds exist.
    entries = fresh_worlds(out,cohort,p)
    for entry in entries:
        verify_world_manifest(SYNTH/entry["name"])
        if sha256_file(SYNTH/entry["name"]/"manifest.json")!=entry["manifest_sha256"]:
            raise ValueError("Fresh registry manifest changed")
    summary = evaluate_bank(out,entries,p,selection,t4,"fresh_test")
    audit = pd.read_csv(out/"fresh_test/rollout_audit.csv")
    ar = pd.read_csv(out/"fresh_test/ar_summary.csv")
    money_ok = audit.max_bank_ledger_error_vnd.le(p["acceptance"]["money_tolerance_vnd"]).all() and audit.max_ar_accounting_error_vnd.dropna().le(p["acceptance"]["money_tolerance_vnd"]).all()
    decision = research_decision(summary,p,timing["passed"],bool(money_ok))
    ar_pivot = ar.pivot(index="world",columns="model",values="ar_crps_normalized")
    decision["ar_crps_not_worse_each_world"] = bool(ar_pivot.unified.le(ar_pivot.v6).all())
    decision["research_passed"] &= decision["ar_crps_not_worse_each_world"]
    if not decision["research_passed"]:
        decision["decision"] = "insufficient_evidence_to_replace_v6"
    integrity = verify_preserved(out)
    integrity.update(final_worlds=len(entries),final_firms=sum(e["n_firms"] for e in p["fresh_holdouts"]),
                     scope="synthetic corrected prototype; four economic Worlds; no real-SME/product acceptance")
    write_json(out/"verification.json",integrity)
    write_json(out/"decision.json",decision)
    print(decision,flush=True)


if __name__=="__main__":
    main()
