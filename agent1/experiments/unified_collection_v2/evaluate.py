"""Source-only selection followed by a single predeclared fresh evaluation."""
from __future__ import annotations

import gc
import numpy as np
import pandas as pd
import lightgbm as lgb

from agent1.paths import ROOT,SYNTH
from agent1.data.world_manifest import sha256_file
from experiments.t1_competing_v6.core import predict_hazards,cumulative_states
from experiments.t1_competing_v6.calibration import transform as calibrate_v6
from .core import LabelIndex,observed_rows,encode
from .cash import build_context,simulate_bank,truth_from_daily,weekly_sum,v6_receipts
from .data import read_json,write_json,write_csv,world_tables,dataset
from .features import SnapshotBuilder,model_view
from .metrics import score_ar,score_paths,paired_summary
from .model import TransitionModel
from .train import load_model
from .rollout import simulate_receipts
from .randomness import seed_for
from .performance import MemoryMeter


def baseline_model(p):
    directory = ROOT/p["v6_directory"]
    meta,calibration = read_json(directory/"train.json"),read_json(directory/"calibration.json")
    if sha256_file(directory/"model.txt")!=meta["model_sha256"]:
        raise ValueError("Changed fixed v6 baseline")
    return lgb.Booster(model_file=str(directory/"model.txt")),meta,calibration


def baseline_pmf(frame,baseline):
    if not len(frame):
        return np.empty((0,13))
    model,meta,calibration = baseline
    hazard = calibrate_v6(predict_hazards(model,frame,meta["features"],meta["active_causes"]),calibration)
    cdf = cumulative_states(hazard)[:,:13,1]
    return np.diff(np.column_stack((np.zeros(len(frame)),cdf)),axis=1)


def replicate_seed(p,case,mc):
    return seed_for(p["seed"],case,f"replicate_{mc}")


def source_ar_set(out,cohort,p,variants,label):
    file = out/f"{label}_scores.csv"
    if file.exists():
        return pd.read_csv(file)
    baseline = baseline_model(p)
    models = {budget:load_model(out,budget)[0] for budget in set(v[1] for v in variants)}
    rows,replicates = [],[]
    for entry in cohort["worlds"]:
        if entry["role"]!="train":
            continue
        world = entry["name"]
        inv,pay = (pd.read_parquet(SYNTH/world/f"{n}.parquet") for n in ("invoices","payments"))
        labels = LabelIndex(inv,pay)
        anchors = pd.read_parquet(out/"cache"/f"calibration_select_{world}_anchors.parquet")
        for (cutoff,fid),frame in anchors.groupby(["cutoff","firm_id"],sort=True):
            frame = frame.reset_index(drop=True)
            if len(frame)>p["simulation"]["max_invoices"]:
                raise ValueError("Source selection company exceeds protocol budget; do not truncate")
            case = f"{world}:{fid}:{pd.Timestamp(cutoff).date()}"
            key = {"world":world,"firm_id":fid,"cutoff":str(pd.Timestamp(cutoff).date())}
            _,actual,_,_ = labels.weekly(frame,p["source_label_end"])
            truth = actual.sum(0)
            pmf = baseline_pmf(frame,baseline)
            old = []
            for mc in p["source_mc_seeds"]:
                seed = replicate_seed(p,case,mc)
                old.append(v6_receipts(frame,pmf,p["source_paths"],seed_for(seed,case,"baseline_collection"),.15,.15))
            rows.append({**key,"variant":"v6","budget":0,"rho_firm":.15,"rho_customer":.15,
                         **score_ar(np.concatenate(old),truth,frame.amount_open.sum())})
            for name,budget,rho in variants:
                samples = []
                for mc in p["source_mc_seeds"]:
                    seed = replicate_seed(p,case,mc)
                    result = simulate_receipts(models[budget],frame,n=p["source_paths"],seed=seed,case=case,
                        rho_firm=rho[0],rho_customer=rho[1],batch_rows=p["simulation"]["batch_rows"])
                    samples.append(result["cash"])
                    replicates.append({**key,"variant":name,"mc_seed":mc,**score_ar(result["cash"],truth,frame.amount_open.sum())})
                rows.append({**key,"variant":name,"budget":budget,"rho_firm":rho[0],"rho_customer":rho[1],
                             **score_ar(np.concatenate(samples),truth,frame.amount_open.sum())})
            print(f"{label}: {case}, {len(frame)} invoices",flush=True)
        del inv,pay,labels,anchors
        gc.collect()
    write_csv(file,pd.DataFrame(rows))
    write_csv(out/f"{label}_mc.csv",pd.DataFrame(replicates))
    return pd.DataFrame(rows)


def select_on_source(out,cohort,p):
    file = out/"selection.json"
    if file.exists():
        return read_json(file)
    default = p["rho_grid"][1]
    variants = [(f"budget_{budget}",budget,default) for budget in p["candidate_anchor_budgets"]]
    frame = source_ar_set(out,cohort,p,variants,"source_learning_curve")
    score = frame.groupby("variant").ar_crps_normalized.mean()
    best = min(variants,key=lambda item:score[item[0]])
    rho_variants = [(f"rho_{i}",best[1],rho) for i,rho in enumerate(p["rho_grid"])]
    sensitivity = source_ar_set(out,cohort,p,rho_variants,"source_rho_selection")
    rho_score = sensitivity.groupby("variant").ar_crps_normalized.mean()
    selected = min(rho_variants,key=lambda item:rho_score[item[0]])
    baseline = float(rho_score["v6"])
    chosen = float(rho_score[selected[0]])
    result = {"anchor_budget":selected[1],"rho":selected[2],"source_ar_crps":chosen,"v6_source_ar_crps":baseline,
              "source_gate_passed":bool(chosen<=baseline*(1+p["acceptance"]["source_ar_crps_relative_worsening_stop"])),
              "candidate_scores":{str(k):float(v) for k,v in score.items()},
              "rho_scores":{str(k):float(v) for k,v in rho_score.items()},
              "selection_scope":"disjoint source train-World calibration_select firms only; no old/fresh holdout scores"}
    write_json(file,result)
    return result


def source_dependence(out,cohort,p,selection):
    file = out/"source_dependence.csv"
    if file.exists():
        return
    model,_ = load_model(out,selection["anchor_budget"])
    x,keys,pairs,detail = dataset(out,cohort,p,"calibration_select")
    probability = model.predict(x)
    zero = np.array([v["cash_fraction"]==0 for v in model.vocabulary])
    detail = detail.copy()
    detail["zero_residual"] = (pairs[:,0]==0)-probability[:,zero].sum(1)
    detail["week_start"] = detail.cutoff+pd.to_timedelta((detail.week-1)*7,unit="D")
    rows,company_week = [],[]
    for (world,fid,date),g in detail.groupby(["world","firm_id","week_start"]):
        r = g.zero_residual.to_numpy()
        if len(r)>1:
            rows.append({"world":world,"firm_id":fid,"week_start":str(date.date()),"group":"firm",
                         "at_risk_invoices":len(r),"pair_zero_residual_product":float((r.sum()**2-(r*r).sum())/(len(r)*(len(r)-1)))})
        company_week.append({"world":world,"firm_id":fid,"week_start":date,"mean_residual":float(r.mean())})
        for customer,part in g.groupby("customer_id"):
            r = part.zero_residual.to_numpy()
            if len(r)>1:
                rows.append({"world":world,"firm_id":fid,"week_start":str(date.date()),"group":"customer",
                             "at_risk_invoices":len(r),"pair_zero_residual_product":float((r.sum()**2-(r*r).sum())/(len(r)*(len(r)-1)))})
    write_csv(file,pd.DataFrame(rows))
    weekly = pd.DataFrame(company_week).sort_values(["world","firm_id","week_start"])
    serial = []
    for world,g in weekly.groupby("world"):
        previous = g.groupby("firm_id").mean_residual.shift(1)
        previous_date = g.groupby("firm_id").week_start.shift(1)
        keep = (g.week_start-previous_date).dt.days.eq(7)&previous.notna()
        serial.append({"world":world,"adjacent_company_weeks":int(keep.sum()),
                       "lag1_residual_correlation":float(np.corrcoef(previous[keep],g.loc[keep,"mean_residual"])[0,1]) if keep.sum()>2 else None,
                       "scope":"descriptive conditional residual diagnostic on at-risk invoices; no persistent factor silently added"})
    write_csv(out/"source_serial_dependence.csv",pd.DataFrame(serial))


def evaluate_bank(out,entries,p,selection,t4,scope):
    destination = out/scope
    if (destination/"summary.csv").exists():
        return pd.read_csv(destination/"summary.csv")
    model,meta = load_model(out,selection["anchor_budget"])
    baseline = baseline_model(p)
    bank_rows,weekly_rows,ar_rows,mc_rows,audit_rows,support_rows,component_rows = [],[],[],[],[],[],[]
    for entry in entries:
        world = entry["name"]
        tables = world_tables(world)
        inv,pay = tables["invoices"],tables["payments"]
        builder = SnapshotBuilder(inv,pay,tables["promises"])
        labels = LabelIndex(inv,pay)
        cutoffs = p["evaluation_cutoffs"] if scope=="fresh_test" else p["bank_diagnostic_cutoffs"]
        if scope=="source_bank":
            source = pd.read_parquet(out/"cache"/f"calibration_select_{world}_anchors.parquet")
            firms = sorted(source.firm_id.unique())
        else:
            firms = sorted(inv.firm_id.unique())
        config = read_json(SYNTH/world/"config.json")
        for cutoff in map(pd.Timestamp,cutoffs):
            view = model_view(builder.snapshot(cutoff,firms=firms),cutoff)
            for fid in firms:
                frame = view[view.firm_id.eq(fid)].reset_index(drop=True)
                if len(frame)>p["simulation"]["max_invoices"]:
                    raise ValueError("Company exceeds declared invoice budget")
                case = f"{world}:{fid}:{cutoff.date()}"
                key = {"world":world,"role":entry["role"],"firm_id":fid,"cutoff":str(cutoff.date())}
                company = {name:t[t.firm_id.eq(fid)] for name,t in tables.items() if "firm_id" in t}
                company_inv = inv[inv.firm_id.eq(fid)]
                company_pay = pay[pay.firm_id.eq(fid)]
                b0,truth = truth_from_daily(company["daily_cash"],cutoff)
                if len(frame):
                    _,actual_invoice,_,_ = labels.weekly(frame,"2025-12-31")
                    actual_ar = actual_invoice.sum(0)
                    customer = frame.groupby("customer_id").amount_open.sum().sort_values(ascending=False)
                    top = frame.customer_id.isin(customer.head(max(1,int(np.ceil(len(customer)*.2)))).index).to_numpy()
                else:
                    actual_invoice,actual_ar,top = np.empty((0,13)),np.zeros(13),np.zeros(0,bool)
                pmf = baseline_pmf(frame,baseline)
                bank_samples = {"v6":[],"unified":[]}
                ar_samples = {"v6":[],"unified":[]}
                top_new,scales = [],[]
                for mc in p["simulation"]["mc_seeds"]:
                    seed = replicate_seed(p,case,mc)
                    with MemoryMeter() as meter:
                        context = build_context(company_inv,company_pay,company["bank_txns"],company["outflows"],company["daily_cash"],
                                                cutoff,t4,n=p["simulation"]["paths"],seed=seed,case=case)
                        new = simulate_receipts(model,frame,n=p["simulation"]["paths"],seed=seed,case=case,
                            rho_firm=selection["rho"][0],rho_customer=selection["rho"][1],batch_rows=p["simulation"]["batch_rows"],return_invoice_cash=True)
                        old_cash = v6_receipts(frame,pmf,p["simulation"]["paths"],seed_for(seed,case,"baseline_collection"),.15,.15)
                        for name,cash in (("v6",old_cash),("unified",new["cash"])):
                            bank = simulate_bank(cash,context)
                            bank_samples[name].append(bank["balance"])
                            ar_samples[name].append(cash)
                            mc_rows.append({**key,"model":name,"mc_seed":mc,**score_paths(bank["balance"],truth,context["scale"]),
                                            **score_ar(cash,actual_ar,frame.amount_open.sum())})
                            audit_rows.append({**key,"model":name,"mc_seed":mc,"max_bank_ledger_error_vnd":bank["max_ledger_error_vnd"],
                                               "draw_policy_identified":context["draw_audit"]["identified"]})
                        top_new.append(new["invoice_cash"][:,top].sum(1) if len(frame) else np.zeros_like(new["cash"]))
                        scales.append(context["scale"])
                        component_rows.append({**key,"mc_seed":mc,"forecast_other_inflow":float(context["other_daily"].sum()/len(old_cash)),
                            "forecast_outflow":float(context["outflow_daily"].sum()/len(old_cash)),"forecast_new_bank_cash":float(context["new_bank_daily"].sum()/len(old_cash)),
                            "fee_rate":context["fee_rate"],"draw_audit":str(context["draw_audit"])})
                    audit_rows[-1].update(end_to_end_seconds=meter.seconds,rss_peak_sampled_mib=meter.peak/2**20,
                        max_ar_accounting_error_vnd=max((a["max_accounting_error_vnd"] for a in new["audit"]),default=0))
                scale = float(np.mean(scales))
                for name in ("v6","unified"):
                    samples = np.concatenate(bank_samples[name])
                    applied = np.concatenate(ar_samples[name])
                    bank_rows.append({**key,"model":name,"invoices":len(frame),"scale":scale,
                                      **score_paths(samples,truth,scale)})
                    ar_rows.append({**key,"model":name,**score_ar(applied,actual_ar,frame.amount_open.sum())})
                    q = np.quantile(samples,[.1,.5,.9],axis=0)
                    arq = np.quantile(np.cumsum(applied,axis=1),[.1,.5,.9],axis=0)
                    top_mean = np.concatenate(top_new).mean(0) if name=="unified" else (pmf[top]*frame.amount_open.to_numpy()[top,None]).sum(0)
                    for week in range(13):
                        left,right = cutoff+pd.Timedelta(days=7*week),cutoff+pd.Timedelta(days=7*(week+1))
                        shock = any(pd.Timestamp(e["start"])<right and pd.Timestamp(e["start"])+pd.Timedelta(weeks=e["rise_weeks"]+e["peak_weeks"]+e["recovery_weeks"])>left for e in config["shock_schedule"])
                        weekly_rows.append({**key,"model":name,"week":week+1,"balance_true":float(truth[week]),
                            "p10":float(q[0,week]),"p50":float(q[1,week]),"p90":float(q[2,week]),
                            "ar_applied_actual":float(actual_ar[week]),"ar_applied_mean":float(applied[:,week].mean()),
                            "ar_cumulative_p10":float(arq[0,week]),"ar_cumulative_p90":float(arq[2,week]),
                            "top_customer_actual":float(actual_invoice[top,week].sum()),"top_customer_mean":float(top_mean[week]),"scheduled_shock":shock})
                if len(frame):
                    x,keys,_,detail = observed_rows(frame,labels,"2025-12-31",p["partial_fraction_edges"])
                    y = encode(keys,meta["vocabulary"],allow_unknown=True)
                    support_rows.append({**key,"observed_rows":len(y),"unsupported_outcomes":int((y<0).sum())})
                print(f"{scope}: {case}, {len(frame)} invoices, pooled {len(p['simulation']['mc_seeds'])*p['simulation']['paths']} paths",flush=True)
        del tables,builder,labels
        gc.collect()
    company = pd.DataFrame(bank_rows)
    summary,ci = paired_summary(company,p)
    ar = pd.DataFrame(ar_rows)
    write_csv(destination/"company_scores.csv",company)
    write_csv(destination/"weekly_predictions.csv",pd.DataFrame(weekly_rows))
    write_csv(destination/"ar_company_scores.csv",ar)
    write_csv(destination/"ar_summary.csv",ar.groupby(["world","model"],as_index=False).mean(numeric_only=True))
    write_csv(destination/"mc_scores.csv",pd.DataFrame(mc_rows))
    write_csv(destination/"rollout_audit.csv",pd.DataFrame(audit_rows))
    write_csv(destination/"outcome_support.csv",pd.DataFrame(support_rows))
    write_csv(destination/"common_components.csv",pd.DataFrame(component_rows))
    write_csv(destination/"company_bootstrap.csv",ci)
    write_csv(destination/"summary.csv",summary)
    return summary
