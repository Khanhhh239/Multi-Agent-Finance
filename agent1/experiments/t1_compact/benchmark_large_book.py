"""Technical load fixture above the 512-invoice SHAP sampling boundary."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import numpy as np
from threadpoolctl import threadpool_limits
from agent1.adaptive.compact_t1 import load_workspace_bundle,workspace_context,sha256
from experiments.t1_compact.aligned_data import write
from experiments.t1_compact.refit_landmark import contexts,load_role
from experiments.t1_compact.train_ensemble import benchmark_ensemble
from experiments.t1_compact.train import world_ledgers
from agent1.adaptive.ledger_bridge import workspace_data
from agent1.adaptive.methods import forecast
from experiments.t1_compact.compare_workspace_worlds import past_data


def replicate(data,count):
    result={"invoices":[],"payments":[],"actions":[],"outflows":[],"record_history":{"invoices":[]}}
    for copy in range(count):
        prefix=f"LOAD{copy}_"
        def invoice(row):
            row=dict(row,invoice_id=prefix+row["invoice_id"],customer_id=prefix+row["customer_id"])
            row["amount"]=int(row["amount"])*(copy+1)
            return row
        result["invoices"].extend(invoice(r) for r in data["invoices"])
        result["record_history"]["invoices"].extend(invoice(r) for r in data["record_history"]["invoices"])
        result["payments"].extend(dict(r,payment_id=prefix+r["payment_id"],invoice_id=prefix+r["invoice_id"],amount=int(r["amount"])*(copy+1)) for r in data["payments"])
        result["actions"].extend(dict(r,event_id=prefix+r["event_id"],invoice_id=prefix+r["invoice_id"]) for r in data["actions"])
    return result


def run(output):
    destination=output/"large_book_runtime.json"
    if destination.exists():return json.loads(destination.read_text(encoding="utf-8"))
    frame=load_role(output,"fresh_test")
    entry=next(e for e in json.loads((output/"fresh_inventory.json").read_text(encoding="utf-8")) if e["name"]=="refit_04_fresh_test")
    origin=frame.origin.max()
    firm="F019"
    ledger=next(l for f,l in world_ledgers(Path(entry["directory"])) if f==firm)
    source=past_data(workspace_data(ledger),origin)
    history=workspace_context(source,origin)
    population=int(((history.remaining_amount>.01)&history.written_off_at.isna()).sum())
    factor=math.ceil(1000/population)
    data=replicate(source,factor)
    history=workspace_context(data,origin)
    opened=history[(history.remaining_amount>.01)&history.written_off_at.isna()].copy()
    opened.attrs["compact_context"]=history
    if len(opened)<1000:raise ValueError("Large-book fixture too small")
    release=json.loads((output/"release.json").read_text(encoding="utf-8"))
    bundle=load_workspace_bundle(output/release["artifact_directory"],origin)
    latency=benchmark_ensemble(bundle["model"],[dict(name="large_book",origin=origin,opened=opened)],repetitions=20)
    settings=[(400,30),(1000,30),(1000,10)]
    reference=forecast(data,str(origin.date()),0.,bundle,simulation_paths=1000,shap_limit=0)
    expected=np.array([[r[k] for k in ("cash_in","cash_out","balance")] for r in reference["weeks"]])
    queue=[(r["invoice_id"],r["payment_probability_4w"]) for r in reference["collections"]]
    records=[]
    for repeat in range(3):
        for paths,limit in settings[repeat:]+settings[:repeat]:
            started=time.perf_counter()
            plan=forecast(data,str(origin.date()),0.,bundle,simulation_paths=paths,shap_limit=limit)
            elapsed=time.perf_counter()-started
            assert plan["open_invoices"]==len(opened)
            np.testing.assert_allclose(np.array([[r[k] for k in ("cash_in","cash_out","balance")] for r in plan["weeks"]]),expected,atol=.01,rtol=0)
            assert [(r["invoice_id"],r["payment_probability_4w"]) for r in plan["collections"]]==queue
            records.append(dict(simulation_paths=paths,shap_limit=limit,repeat=repeat,seconds=elapsed))
    result=dict(passed=True,open_invoices=len(opened),history_invoices=len(history),source_open_invoices=population,
                replication_factor=factor,amount_scale_factors=list(range(1,factor+1)),
                fixture="Replicated dated ledger with distinct invoice/customer IDs and integer monetary scales; technical load only, not new accuracy data.",
                shap=latency,runs=records,all_expected_cash_and_queue_invariant=True)
    write(destination,result)
    release["large_book_shap_pass"]=latency["passed"]
    release["research_integration_accepted"]=bool(release["research_integration_accepted"] and latency["passed"])
    release["required_hashes"]["large_book_runtime.json"]=sha256(destination)
    write(output/"release.json",release)
    print(f"Large book verified: {len(opened)} open invoices, SHAP p95={latency['p95_seconds']:.3f}s",flush=True)
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    with threadpool_limits(limits=2),threadpool_limits(limits=1,user_api="blas"):run(args.output.resolve())
