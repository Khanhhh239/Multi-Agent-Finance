"""Read frozen v2 artifacts, verify cohorts and summarize source/fresh evidence."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from agent1.paths import ROOT
from agent1.data.world_manifest import sha256_file
from experiments.unified_collection_v2.data import PROTOCOL,read_json,write_csv,write_json
from experiments.unified_collection_v2.artifacts import verify_source_snapshot

OUTPUT = ROOT/"outputs/analysis/unified_collection_v2_20261104_after_cleanup"


def main():
    p = read_json(PROTOCOL)
    source = ROOT/p["output_directory"]
    verification = read_json(source/"verification.json")
    decision = read_json(source/"decision.json")
    if not verification["protected_files_unchanged"] or not verification["locked_source_unchanged"]:
        raise ValueError("v2 preservation failed")
    source_integrity = verify_source_snapshot(source)
    curve = pd.read_csv(source/"source_learning_curve_scores.csv")
    means = curve.groupby("variant").ar_crps_normalized.mean()
    baseline = float(means["v6"])
    rows,bands = [],[]
    for budget in p["candidate_anchor_budgets"]:
        directory = source/"candidates"/str(budget)
        meta = read_json(directory/"train.json")
        quantization = read_json(directory/"discretization.json")
        model_hash = sha256_file(directory/"model.txt")
        if model_hash!=meta["model_sha256"]:
            raise ValueError("Candidate model changed")
        score = float(means[f"budget_{budget}"])
        rows.append({"anchors":budget,"rounds":meta["rounds"],"transition_rows":meta["transition_rows"],
            "classes":len(meta["vocabulary"]),"source_ar_crps":score,"v6_source_ar_crps":baseline,
            "relative_ar_crps_improvement":1-score/baseline,"train_seconds":meta["performance"]["seconds"],
            "train_peak_rss_mib":meta["performance"]["rss_peak_sampled_mib"],
            "source_class_replay_cash_wape":quantization["source_recursive_class_replay"]["cash_wape"],
            "source_unsupported_rows":meta["unsupported_source_calibration_rows"]})
        for band,value in read_json(directory/"calibration.json").items():
            selected = value["source_after_candidate"] if value["selected"]=="calibrated" else value["source_before"]
            bands.append({"anchors":budget,"band":band,"selected":value["selected"],
                          "monetary_guard_passed":value["monetary_and_brier_guards"],**selected})
    write_csv(OUTPUT/"learning_curve_summary.csv",pd.DataFrame(rows))
    write_csv(OUTPUT/"calibration_summary.csv",pd.DataFrame(bands))
    counts,score_rows,ar_ci = {},[],[]
    rng = np.random.default_rng(p["seed"])
    for scope,expected in (("source_bank",64),("fresh_test",128)):
        directory = source/scope
        if not (directory/"company_scores.csv").exists():
            continue
        company = pd.read_csv(directory/"company_scores.csv")
        weekly = pd.read_csv(directory/"weekly_predictions.csv")
        mc = pd.read_csv(directory/"mc_scores.csv")
        audit = pd.read_csv(directory/"rollout_audit.csv")
        ar = pd.read_csv(directory/"ar_company_scores.csv")
        keys = ["world","firm_id","cutoff","model"]
        if len(company)!=expected or len(weekly)!=expected*13 or len(mc)!=expected*len(p["simulation"]["mc_seeds"]):
            raise ValueError("Incomplete evaluation cohort")
        if company.duplicated(keys).any() or weekly.duplicated(keys+["week"]).any() or not weekly.groupby(keys).size().eq(13).all():
            raise ValueError("Duplicate or missing company/week prediction")
        counts[scope] = {"company_model_origins":len(company),"weekly_rows":len(weekly),"mc_rows":len(mc),
                        "max_bank_identity_error_vnd":float(audit.max_bank_ledger_error_vnd.max()),
                        "max_ar_identity_error_vnd":float(audit.max_ar_accounting_error_vnd.max()),
                        "max_end_to_end_seconds":float(audit.end_to_end_seconds.max()),
                        "max_case_rss_sampled_mib":float(audit.rss_peak_sampled_mib.max())}
        if counts[scope]["max_bank_identity_error_vnd"]>1 or counts[scope]["max_ar_identity_error_vnd"]>1:
            raise ValueError("Accounting identity failed")
        combined = company.merge(ar,on=keys+["role"],validate="one_to_one")
        for world,g in combined.groupby("world"):
            old,new = g[g.model.eq("v6")],g[g.model.eq("unified")]
            score_rows.append({"scope":scope,"world":world,
                "bank_crps_v6":float(old.crps_normalized.mean()),"bank_crps_unified":float(new.crps_normalized.mean()),
                "bank_crps_relative_improvement":float(1-new.crps_normalized.mean()/old.crps_normalized.mean()),
                "ar_crps_v6":float(old.ar_crps_normalized.mean()),"ar_crps_unified":float(new.ar_crps_normalized.mean()),
                "brier13_v6":float(old.brier_13.mean()),"brier13_unified":float(new.brier_13.mean()),
                "coverage_v6":float(old.coverage_80.mean()),"coverage_unified":float(new.coverage_80.mean())})
            pivot = ar[ar.world.eq(world)].pivot(index=["firm_id","cutoff"],columns="model",values="ar_crps_normalized")
            delta = (pivot.unified-pivot.v6).groupby(level="firm_id").mean().to_numpy()
            draws = delta[rng.integers(0,len(delta),(p["bootstrap_replicates"],len(delta)))].mean(1)
            ar_ci.append({"scope":scope,"world":world,"unified_minus_v6":float(delta.mean()),
                          "ci_low":float(np.quantile(draws,.025)),"ci_high":float(np.quantile(draws,.975)),
                          "company_clusters":len(delta),"scope_of_ci":"companies within this World only"})
        slices = weekly.merge(company[keys+["scale"]],on=keys,validate="many_to_one")
        slices["covered"] = slices.balance_true.between(slices.p10,slices.p90)
        slices["interval_score"] = (slices.p90-slices.p10+10*np.maximum(slices.p10-slices.balance_true,0)+
                                     10*np.maximum(slices.balance_true-slices.p90,0))/slices.scale
        write_csv(OUTPUT/f"{scope}_shock_slices.csv",slices.groupby(["world","model","scheduled_shock"],as_index=False).agg(
            company_weeks=("week","size"),coverage=("covered","mean"),interval_score=("interval_score","mean")))
    write_csv(OUTPUT/"paired_score_summary.csv",pd.DataFrame(score_rows))
    write_csv(OUTPUT/"ar_company_bootstrap.csv",pd.DataFrame(ar_ci))
    write_json(OUTPUT/"verification.json",{"source_sha256":sha256_file(Path(__file__)),"cohort_checks":counts,
        **source_integrity,"historical_protected_files_at_measurement":verification["protected_files"],
        "decision":decision["decision"],"scope":"read saved results only; no model fitting, selection or holdout forecasts"})
    print(pd.DataFrame(rows).to_string(index=False))
    print(pd.DataFrame(score_rows).to_string(index=False))
    print(decision)


if __name__=="__main__":
    main()
