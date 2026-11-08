"""Audit ONE proposed feature family, without fitting or changing v6.

Run with -B; output must be new. Existing diagnostic anchors are reused exactly.
The hypothetical observation producer sees scenarios; the consumer receives
released measurements and dated registry columns only. Oracles go to audit CSVs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from agent1.paths import ROOT, SYNTH
from agent1.synth.shocks import ShockEpisode
from experiments.t1_credit_context.features import CONTEXT_FEATURES, context_features
from experiments.t1_credit_context.observations import SurveyDesign, design_dict, national_credit_pressure, simulate_releases


ARTIFACT = ROOT / "outputs/data/t1_competing_v6_20261101"
DIAGNOSIS = ROOT / "outputs/analysis/t1_v6_diagnosis_20261105_r2"
TEST = "v4_shortpay_4shock_20261028_test_000"


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def dated_registry(world):
    """HYPOTHESIS: KYC industry recorded on first observed invoice.

    World files have no industry publication date. This assumption is explicit;
    these are not verified historical KYC records or an actual public source.
    """
    directory = SYNTH / world
    invoices = pd.read_parquet(directory / "invoices.parquet", columns=["customer_id", "firm_id", "issue_date"])
    registries = []
    for key, filename in (("customer_id", "customers.parquet"), ("firm_id", "firms.parquet")):
        registry = pd.read_parquet(directory / filename, columns=[key, "industry"])
        registry["known_at"] = registry[key].map(invoices.groupby(key).issue_date.min())
        registries.append(registry.dropna(subset=["known_at"]))
    return registries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/analysis/t1_credit_context_20261105")
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to((ROOT / "outputs/analysis").resolve()):
        raise ValueError("Research output must remain in outputs/analysis")
    metadata = json.loads((ARTIFACT / "train.json").read_text(encoding="utf-8"))
    old_verification = json.loads((DIAGNOSIS / "verification.json").read_text(encoding="utf-8"))
    if sha256(ARTIFACT / "model.txt") != metadata["model_sha256"] or old_verification["model_sha256"] != metadata["model_sha256"]:
        raise ValueError("v6/diagnosis model mismatch")
    worlds = [row["world"] for row in metadata["world_audit"]] + [TEST]
    protected_dirs = [ARTIFACT, ROOT / "experiments/t1_competing_v6", ROOT / "experiments/t1_competing_v5"]
    protected_dirs += [SYNTH / world for world in worlds]
    protected = {p: sha256(p) for directory in protected_dirs for p in directory.rglob("*")
                 if p.is_file() and "__pycache__" not in p.parts}
    anchors_path = DIAGNOSIS / "diagnostic_anchor_context.parquet"
    protected[anchors_path] = sha256(anchors_path)
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "measurement_design.json", {
        "status": "hypothetical measurement feasibility; NOT a preregistered model result",
        "base_design": design_dict(SurveyDesign()),
        "world_seed_rule": "base survey seed + world seed; separate from World RNG",
        "industry_knowledge_assumption": "fixed KYC classification known from first observed invoice",
        "max_reference_age_days": 62, "min_respondents": 30,
        "estimator_features": CONTEXT_FEATURES,
        "source_code_sha256": {p.relative_to(ROOT).as_posix(): sha256(p) for p in
                               [Path(__file__), *sorted((ROOT / "experiments/t1_credit_context").glob("*.py"))]},
    })
    cutoffs, feature_parts, release_audits, coupling = [], [], [], []
    for ordinal, world in enumerate(worlds):
        print(f"Audit credit observations: {world}", flush=True)
        cfg = json.loads((SYNTH / world / "config.json").read_text(encoding="utf-8"))
        episodes = [ShockEpisode(**spec) for spec in cfg["shock_schedule"]]
        survey = SurveyDesign(seed=SurveyDesign().seed + cfg["seed"])
        releases = simulate_releases(episodes, cfg["start"], cfg["end"], survey)
        releases.to_csv(out / f"releases_{world}.csv", index=False)
        if ordinal < len(worlds) - 1:
            detail = metadata["world_audit"][ordinal]
            cache = ARTIFACT / "cache" / f"train_{world}.parquet"
            if sha256(cache) != detail["cache_sha256"]:
                raise ValueError("Source snapshot cache changed")
            cached = pd.read_parquet(cache, columns=["partition", "invoice_id", "firm_id", "customer_id", "cutoff"])
            frame = cached[cached.partition.eq("fit")].drop(columns="partition").reset_index(drop=True)
            scope = "train_fit"
        else:
            frame = pd.read_parquet(anchors_path, columns=["world", "invoice_id", "firm_id", "customer_id", "cutoff"])
            if not frame.world.eq(TEST).all() or len(frame) != 5772 or frame.invoice_id.duplicated().any():
                raise ValueError("Unexpected diagnostic anchor population")
            frame = frame.drop(columns="world").reset_index(drop=True)
            scope = "test_000_diagnostic"
        buyer, seller = dated_registry(world)
        features = context_features(frame[["firm_id", "customer_id", "cutoff"]], releases, buyer, seller)
        candidate = pd.concat([frame, features], axis=1).assign(world=world, scope=scope)
        feature_parts.append(candidate)
        period_pressures = []
        for release in releases.itertuples(index=False):
            pressure = float(national_credit_pressure(episodes, pd.date_range(release.period_start, release.period_end)).mean())
            period_pressures.append(pressure)
            release_audits.append({"world": world, "period_end": release.period_end,
                                   "credit_reference_oracle": pressure, "measured_share": release.restricted_share,
                                   "respondents": release.respondents})
        oracle_by_reference = dict(zip(releases.period_end, period_pressures))
        for cutoff, part in candidate.groupby("cutoff"):
            visible = releases[releases.ingested_at.le(cutoff)]
            latest = visible.iloc[-1] if len(visible) else None
            reference = latest.period_end if latest is not None else None
            true_current = float(national_credit_pressure(episodes, [cutoff])[0])
            true_reference = oracle_by_reference.get(reference)
            cutoffs.append({
                "world": world, "scope": scope, "cutoff": cutoff, "n": len(part),
                "latest_reference": reference, "latest_ingested_at": latest.ingested_at if latest is not None else None,
                "known_restricted_share": part.macro_credit_restricted_share.iloc[0],
                "reference_age_days": part.macro_credit_age_days.iloc[0],
                "credit_current_oracle": true_current, "credit_reference_oracle": true_reference,
                "current_credit_not_in_reference": true_current > 0 and true_reference == 0,
                "buyer_unknown_n": int(part.buyer_industry_unknown.sum()),
                "seller_unknown_n": int(part.seller_industry_unknown.sum()),
            })
        audit = pd.DataFrame(release_audits).query("world == @world")
        active = audit.credit_reference_oracle.gt(0)
        coupling.append({"world": world, "n_months": len(audit), "n_credit_active_months": int(active.sum()),
                         "mean_measured_active": float(audit.loc[active, "measured_share"].mean()),
                         "mean_measured_calm": float(audit.loc[~active, "measured_share"].mean()),
                         "pearson_with_reference_oracle": float(audit.measured_share.corr(audit.credit_reference_oracle))})
    features = pd.concat(feature_parts, ignore_index=True)
    features.to_parquet(out / "candidate_context.parquet", index=False)
    cutoff_table = pd.DataFrame(cutoffs)
    cutoff_table.to_csv(out / "cutoff_observability_audit.csv", index=False)
    pd.DataFrame(release_audits).to_csv(out / "measurement_oracle_audit.csv", index=False)
    pd.DataFrame(coupling).to_csv(out / "measurement_coupling.csv", index=False)
    stats = []
    for scope, group in features.groupby("scope"):
        matching = cutoff_table[cutoff_table.scope.eq(scope)]
        stats.append({"scope": scope, "n": len(group),
                      "known_share_min": float(group.macro_credit_restricted_share.min()),
                      "known_share_max": float(group.macro_credit_restricted_share.max()),
                      "missing_n": int(group.macro_credit_missing.sum()),
                      "credit_active_at_cutoff_n": int(matching.loc[matching.credit_current_oracle.gt(0), "n"].sum()),
                      "credit_active_in_reference_n": int(matching.loc[matching.credit_reference_oracle.gt(0), "n"].sum()),
                      "current_credit_not_in_reference_n": int(matching.loc[matching.current_credit_not_in_reference, "n"].sum())})
    train = features[features.scope.eq("train_fit")]
    test = features[features.scope.eq("test_000_diagnostic")]
    a, b = train.macro_credit_restricted_share, test.macro_credit_restricted_share
    changed = [str(p.relative_to(ROOT)) for p, value in protected.items() if sha256(p) != value]
    verification = {"fit_or_calibration_performed": False, "v6_model_sha256": metadata["model_sha256"],
                    "protected_file_count": len(protected), "changed_protected_files": changed,
                    "candidate_feature_count": len(CONTEXT_FEATURES),
                    "oracle_columns_in_candidate": [name for name in features if "oracle" in name or "shock" in name],
                    "prerequisites_sha256": {str(p.relative_to(ROOT)): value for p, value in protected.items()}}
    write_json(out / "verification.json", verification)
    if changed or verification["oracle_columns_in_candidate"]:
        raise ValueError("Preservation or feature isolation check failed")
    summary = {"scope": "synthetic measurement feasibility, not evidence of forecast improvement",
               "population_stats": stats,
               "test_share_outside_train_measurement_range": float(((b < a.min()) | (b > a.max())).mean()),
               "test_july_anchors": int(test.cutoff.dt.month.eq(7).sum()),
               "measurement_coupling": coupling,
               "verification": {k: v for k, v in verification.items() if k != "prerequisites_sha256"}}
    write_json(out / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
