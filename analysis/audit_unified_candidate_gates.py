"""Audit saved evidence for a coherent v6 candidate; never promote or refit it.

Mapped gate diagnostics are kept separate from the official product verdicts.
Run with: python -B -m analysis.audit_unified_candidate_gates
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from agent1.eval.metrics import ece
from agent1.paths import ROOT
from agent1.data.world_manifest import sha256_file
from experiments.unified_collection_v2.artifacts import verify_source_snapshot


OUTPUT = ROOT / "outputs/analysis/unified_candidate_gates_20261104_after_cleanup"
V6 = ROOT / "outputs/data/t1_competing_v6_20261101"
V2 = ROOT / "outputs/data/unified_collection_v2_20261104_r3"
OFFICIAL_REQUIRED = {"G1", "G2", "G5", "G9", "G11", "G12", "G13", "G15", "G16"}


def main():
    inputs = {}

    def track(path):
        path = Path(path)
        inputs[path.relative_to(ROOT).as_posix()] = sha256_file(path)
        return path

    def read_json(path):
        return json.loads(track(path).read_text(encoding="utf-8"))

    def read_csv(path):
        return pd.read_csv(track(path))

    metadata = read_json(V6 / "train.json")
    calibration = read_json(V6 / "calibration.json")
    if sha256_file(track(V6 / "model.txt")) != metadata["model_sha256"]:
        raise ValueError("v6 weights differ from the measured model")
    for name, digest in metadata["source_hashes"].items():
        if sha256_file(track(ROOT / name)) != digest:
            raise ValueError(f"Changed v6 source: {name}")
    track(V2 / "source_hashes.json")
    track(V2 / "source_snapshot.zip")
    source_integrity = verify_source_snapshot(V2)
    protocol = read_json(V2 / "protocol.lock.json")
    t4_metadata = read_json(V2 / "t4.json")
    for name, digest in t4_metadata["hashes"].items():
        if sha256_file(track(V2 / name)) != digest:
            raise ValueError(f"Changed T4 weights: {name}")
    integrity = read_json(ROOT / "outputs/analysis/unified_collection_v2_20261104/final_integrity.json")
    for name, digest in integrity["input_csv_sha256"].items():
        if sha256_file(track(ROOT / name)) != digest:
            raise ValueError(f"Changed saved bank evidence: {name}")
    for name, digest in read_json(V6 / "evaluation.json")["outputs_sha256"].items():
        if sha256_file(track(V6 / name)) != digest:
            raise ValueError(f"Changed saved v6 evidence: {name}")
    track(ROOT / "scripts/evaluate_gates.py")
    track(ROOT / "docs/03_Evaluation/GATES_CURRENT.md")
    official = read_csv(ROOT / "outputs/implementation/gates.csv").set_index("gate")

    # The product ECE uses equal-width bins. v6's report uses quantile bins;
    # recompute from individual predictions instead of reusing that column.
    ece_rows = []
    for path in sorted((V6 / "evaluation_predictions").glob("*.parquet")):
        frame = pd.read_parquet(track(path))
        if frame.duplicated(["world", "invoice_id"]).any():
            raise ValueError("Duplicate first eligible invoice anchors")
        p = frame[[f"p_paid_{d}d" for d in (28, 91, 365)]].to_numpy()
        w = frame[[f"p_writeoff_{d}d" for d in (28, 91, 365)]].to_numpy()
        if (not np.isfinite(p).all() or not np.isfinite(w).all()
                or (p < 0).any() or (w < 0).any() or (p + w > 1 + 3e-6).any()
                or (np.diff(p, axis=1) < -3e-6).any() or (np.diff(w, axis=1) < -3e-6).any()):
            raise ValueError("Invalid competing-risk probabilities")
        actual = frame.cause.eq(1) & frame.time_days.le(28)
        value = ece(actual, frame.p_paid_28d, bins=10)
        ece_rows.append({"world": path.stem, "anchors": len(frame),
                         "ece_4w_equal_width_10": value, "threshold": .05,
                         "passes_numeric_threshold": value <= .05,
                         "scope": "mapped G4 diagnostic; first eligible anchors, not original source rolling protocol"})
    ece_frame = pd.DataFrame(ece_rows)
    if len(ece_frame) != 6 or ece_frame.anchors.sum() != 65221:
        raise ValueError("Incomplete v6 diagnostic cohort")

    directory = V2 / "fresh_test"
    weekly = read_csv(directory / "weekly_predictions.csv")
    company = read_csv(directory / "company_scores.csv")
    keys = ["world", "firm_id", "cutoff", "model"]
    if (len(company) != 128 or len(weekly) != 1664 or company.duplicated(keys).any()
            or weekly.duplicated(keys + ["week"]).any()
            or not weekly.groupby(keys).week.agg(set).map(lambda v: v == set(range(1, 14))).all()):
        raise ValueError("Incomplete paired bank evidence")
    if (set(weekly.world) != {entry["name"] for entry in protocol["fresh_holdouts"]}
            or set(weekly.cutoff) != set(protocol["evaluation_cutoffs"])
            or set(weekly.model) != {"v6", "unified"}):
        raise ValueError("Bank evidence differs from the locked cohort")
    weekly["covered"] = weekly.balance_true.between(weekly.p10, weekly.p90)
    saved = weekly.groupby(keys).covered.mean().reset_index().merge(company, on=keys, validate="one_to_one")
    if not np.allclose(saved.covered, saved.coverage_80):
        raise ValueError("Recomputed coverage differs from saved company scores")
    weekly["horizon"] = np.where(weekly.week <= 4, "w1-4", "w5-13")
    coverage = weekly.groupby(["model", "world", "horizon"], as_index=False).agg(
        company_weeks=("week", "size"), coverage_80=("covered", "mean"))
    pooled = weekly.groupby(["model", "horizon"], as_index=False).agg(
        company_weeks=("week", "size"), coverage_80=("covered", "mean"))
    pooled["world"] = "ALL_FOUR_WORLDS"
    coverage = pd.concat([coverage, pooled], ignore_index=True)
    coverage["passes_75_85_percent"] = coverage.coverage_80.between(.75, .85)
    coverage["scope"] = "mapped G12 coverage diagnostic; raw bank bands, no ACI, observed synthetic receipt labels"
    firm_coverage = weekly.groupby(["model", "world", "firm_id", "horizon"], as_index=False).agg(
        company_weeks=("week", "size"), coverage_80=("covered", "mean"))

    # Recheck the official blockers against their own CSVs. They are not
    # measurements of the proposed v6 composition.
    alerts = read_csv(ROOT / "outputs/e2e/protocol/alert_policy_v2.csv")
    alert = alerts[alerts.model.eq("MC-copula-t (T1+T4+T5)") & alerts.calibration.eq("isotonic") & alerts.horizon.eq(13)]
    if len(alert) != 1:
        raise ValueError("Ambiguous official G13 row")
    alert = alert.iloc[0]
    alert_pass = bool(alert.n_events > 0 and alert.detected_at_least_4w >= .7
                      and alert.median_lead_weeks >= 4 and alert.false_alarms_per_firm_year <= 1)
    t9 = read_csv(ROOT / "outputs/t9/sprint3/target_metrics.csv")
    part = t9[t9.world.eq("tgt")]
    deployed = part[part.method.eq("Deployment source-selected")]
    if len(deployed) != 1:
        raise ValueError("Ambiguous official G15 row")
    deployed = deployed.iloc[0]
    t9_pass = bool(deployed.link_f1 >= .8 and deployed.link_f1 > part[part.method.isin(["R1", "R2"])].link_f1.max()
                   and deployed.link_precision >= .95 and deployed.auto_txn_coverage >= .6
                   and deployed.pay_date_MAE_est_days <= 3)
    if (alert_pass != (official.loc["G13", "status"] == "passed")
            or t9_pass != (official.loc["G15", "status"] == "passed")):
        raise ValueError("Official blocker CSVs and gate table disagree")

    mapping = {
        "G1": "Need matched B1 and candidate cash WAPE on the same two source origins; CRPS vs v6 is a different test.",
        "G2": "Need weekly paid IBS vs B1 on the same risk set; four-state Brier at 91 days is not IBS.",
        "G3": "Need source-fitted Mondrian CQR vs global CQR; finite-horizon competing-risk quantiles need an explicit tail policy.",
        "G4": "Equal-width ECE recomputed here; one old test World exceeds .05. Original two-source-origin protocol still missing.",
        "G5": "Real-domain BLEND results do not validate v6; AR real-data evaluation required.",
        "G6": "Real-domain BLEND results do not validate v6; matched real baselines required.",
        "G7": "v6 source-to-target adaptation has not been measured.",
        "G8": "SBA loan default and invoice finite-horizon write-off are different targets; no transfer of G8 evidence.",
        "G9": "T4 family is reused but these refitted weights need G9 baseline comparisons.",
        "G10": "These T4 weights have no matched real retail-domain gate evidence.",
        "G11": "Expert rule verification remains required for real pilot; out of scope for synthetic stage only.",
        "G12": "Raw bank coverage misses .75-.85; ACI, four baselines and estimated T9 labels are missing from this composition.",
        "G13": "Candidate has only two origins, no alert-episode backtest; legacy G13 also fails false-alarm budget.",
        "G14": "No candidate T7 integration/backtest; unchanged legacy result is failed.",
        "G15": "Unchanged required T9 component fails F1/precision; v6 cannot fix reconciliation coverage by itself.",
        "G16": "Existing T0 component evidence remains passed; verify its boundary again with the new input contract.",
        "G17": "No v6 promise ablation under the registered protocol.",
        "G18": "No matched v6 estimated-T9 versus ledger/oracle ablation.",
    }
    gate_rows = []
    for gate, reason in mapping.items():
        status = "not_measured_for_candidate"
        if gate in {"G4", "G12"}:
            status = "fails_mapped_diagnostic"
        elif gate == "G15":
            status = "failed_unchanged_component"
        elif gate == "G16":
            status = "existing_component_pass_only"
        elif gate == "G11":
            status = "out_of_scope_synthetic_only"
        gate_rows.append({"gate": gate, "required_for_real_pilot": gate in OFFICIAL_REQUIRED,
                          "required_for_synthetic_stage": gate in OFFICIAL_REQUIRED - {"G11"},
                          "official_existing_pipeline_status": official.loc[gate, "status"],
                          "candidate_status": status, "reason": reason,
                          "official_evidence": official.loc[gate, "evidence"]})

    candidate = {
        "candidate": "v6_competing_shared_contract_20261104",
        "status": "recommended_integration_candidate_not_released",
        "scope": "retrospective architecture decision after inspected results; no new holdout claim",
        "collection_model": str((V6 / "model.txt").relative_to(ROOT).as_posix()),
        "collection_model_sha256": metadata["model_sha256"],
        "calibration": calibration["selected"],
        "T1_T2": "one competing-risk classifier; paid and write-off CIF from the same hazards",
        "T2_semantics": "finite-horizon synthetic write-off, not never-pay or SBA default",
        "T6_collection_pmf": "F_paid(7*k)-F_paid(7*(k-1)); do not renormalize its horizon mass",
        "T6_collection_amount": "initial open amount once at sampled settlement week (approximation)",
        "separate_T2_draw": False, "cash_head_in_sampling": False,
        "T4_T5_bank": "frozen v2/r3 T4 weights and daily bank context/fee/draw adapter",
        "T4_weights_sha256": t4_metadata["hashes"],
        "bank_artifact_directory": V2.relative_to(ROOT).as_posix(),
        "bank_adapter_source": "experiments/unified_collection_v2/cash.py",
        "measured_bank_ACI": False,
        "paths_per_replicate": protocol["simulation"]["paths"],
        "MC_replicates": len(protocol["simulation"]["mc_seeds"]),
        "copula": {"nu": 4, "rho_firm": .15, "rho_customer": .15},
        "product_gate_pass_demonstrated": False, "service_activated": False,
        "new_weekly_partial_collection_model": False,
    }
    result = {
        "candidate": candidate["candidate"], "decision": "NO_GO_for_product_gate_promotion",
        "recommendation": "use v6 as integration candidate; retain frozen v2 weekly model as research artifact",
        "G4_equal_width_failed_worlds": ece_frame.loc[~ece_frame.passes_numeric_threshold, "world"].tolist(),
        "G12_raw_pooled_coverage": {r.horizon: r.coverage_80 for r in pooled[pooled.model.eq("v6")].itertuples()},
        "G12_full_protocol_completed": False, "G13_candidate_measured": False,
        "official_G13": {"passed": alert_pass, "detected_at_least_4w": float(alert.detected_at_least_4w),
                         "median_lead_weeks": float(alert.median_lead_weeks),
                         "false_alarms_per_firm_year": float(alert.false_alarms_per_firm_year)},
        "official_G15": {"passed": t9_pass, "f1": float(deployed.link_f1),
                         "precision": float(deployed.link_precision), "auto_coverage": float(deployed.auto_txn_coverage),
                         "pay_date_mae_days": float(deployed.pay_date_MAE_est_days)},
        "official_synthetic_missing": [g for g in official.index if g in OFFICIAL_REQUIRED - {"G11"} and official.loc[g, "status"] != "passed"],
        "input_files_unchanged": True, "audit_source_sha256": sha256_file(Path(__file__)),
        "bank_experiment_source": source_integrity,
        "input_sha256": inputs,
    }
    # Every original input is checked before writing isolated audit outputs.
    for name, digest in inputs.items():
        if sha256_file(ROOT / name) != digest:
            raise ValueError(f"Input changed during audit: {name}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, frame in (("g4_equal_width_diagnostic.csv", ece_frame), ("g12_coverage_diagnostic.csv", coverage),
                        ("g12_firm_coverage_diagnostic.csv", firm_coverage), ("gate_mapping.csv", pd.DataFrame(gate_rows))):
        frame.to_csv(OUTPUT / name, index=False)
    for name, data in (("candidate.json", candidate), ("verification.json", result)):
        (OUTPUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(ece_frame[["world", "ece_4w_equal_width_10", "passes_numeric_threshold"]].to_string(index=False))
    print(pooled.to_string(index=False))
    print(f"{result['decision']}; legacy blockers: {result['official_synthetic_missing']}; checked {len(inputs)} inputs")


if __name__ == "__main__":
    main()
