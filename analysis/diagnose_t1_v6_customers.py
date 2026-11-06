"""Explain leading customer errors using dated history, with oracle fields flagged.

This is an explanatory companion to diagnose_t1_v6, not a model experiment.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from agent1.paths import ROOT, SYNTH
from experiments.t1_competing_v6.features import V6_FEATURES
from experiments.t1_competing_v6.run import build_frame, load_world
from analysis.diagnose_t1_v6 import ARTIFACT, TEST, digest, dump


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=str, default="outputs/analysis/t1_v6_diagnosis_20261105_r2")
    args = parser.parse_args()
    out = ROOT/args.directory
    bias = pd.read_csv(out/"subgroup_bias.csv", keep_default_na=False)
    customers = bias[(bias.dimension == "customer_id") & (bias.day == 365) & (bias.cause == "writeoff")]
    selected = customers.sort_values("expected_minus_actual_events").head(20)
    raw_c = pd.read_parquet(SYNTH/TEST/"customers.parquet").set_index("customer_id")
    inv = pd.read_parquet(SYNTH/TEST/"invoices.parquet")
    builder, _ = load_world(TEST)
    protocol = json.loads((ARTIFACT/"protocol.lock.json").read_text(encoding="utf-8"))
    cutoffs = pd.date_range(protocol["eval_first_cutoff"], protocol["eval_last_cutoff"], freq=f"{protocol['eval_stride_days']}D")
    frames = build_frame(builder, TEST, cutoffs, protocol["eval_label_end"])
    frames = frames.sort_values(["cutoff", "invoice_id"]).drop_duplicates("invoice_id").reset_index(drop=True)
    rows = []
    for row in selected.itertuples():
        customer = row.group
        f = frames[frames.customer_id.eq(customer)]
        first = f.cutoff.min()
        prior = inv[inv.customer_id.eq(customer) & inv.issue_date.le(first)]
        written = prior.writeoff_date.notna() & prior.writeoff_date.le(first)
        closed = prior.paid_date_true.notna() & prior.paid_date_true.le(first)
        default = raw_c.loc[customer, "default_date"]
        first_wo = inv.loc[inv.customer_id.eq(customer), "writeoff_date"].min()
        rows.append({"customer_id": customer, "n_anchors": row.n,
                     "actual_writeoff_365": row.actual, "predicted_writeoff_365": row.predicted,
                     "writeoff_gap": row.gap, "missing_expected_events": -row.expected_minus_actual_events,
                     "first_cutoff": first, "paid_invoices_known_first_cutoff": int(closed.sum()),
                     "writeoffs_known_first_cutoff": int(written.sum()),
                     "median_dpd_at_anchor": float(f.days_past_due.median()),
                     "median_customer_max_dpd": float(f.c_max_dpd.median()),
                     "median_customer_overdue30_amount_share": float(f.c_overdue30_amount_share.median()),
                     "median_days_since_last_pay": float(f.c_days_since_last_pay.median()),
                     "median_recent_payments_count": float(f.c_pay_30d.median()),
                     "median_prior_writeoff_n": float(f.c_writeoff_n_asof.median()),
                     "oracle_FIRST_default_date_NOT_FEATURE": default,
                     "oracle_first_writeoff_date": first_wo,
                     "oracle_FIRST_default_to_first_wo_days": int((first_wo-default).days) if pd.notna(default) and pd.notna(first_wo) else None,
                     "oracle_FIRST_default_after_first_cutoff": bool(default > first) if pd.notna(default) else None})
    profiles = pd.DataFrame(rows)
    profiles.to_csv(out/"leading_customer_profiles.csv", index=False)
    total_missing = -float(bias[(bias.dimension == "all") & (bias.day == 365) & (bias.cause == "writeoff") & (bias.scope == "test_000")].expected_minus_actual_events.iloc[0])
    summary = {"scope": "Explanatory retrospective profiles; no oracle fields passed to any estimator",
               "top_1_share_of_net_missing_writeoff_events": float(profiles.missing_expected_events.head(1).sum()/total_missing),
               "top_5_share_of_net_missing_writeoff_events": float(profiles.missing_expected_events.head(5).sum()/total_missing),
               "top_20_share_of_net_missing_writeoff_events": float(profiles.missing_expected_events.sum()/total_missing),
               "source_sha256": digest(__file__)}
    dump(out/"customer_profile_summary.json", summary)
    weekly = pd.read_csv(out/"weekly_hazards.csv")
    weekly["band"] = pd.cut(weekly.week, [0, 4, 13, 26, 39, 53], labels=["01_04", "05_13", "14_26", "27_39", "40_53"])
    bands = []
    for (scope, band, cause), group in weekly.groupby(["scope", "band", "cause"], observed=True):
        bands.append({"scope": scope, "week_band": band, "cause": cause,
                      "risk_rows": int(group.risk_n.sum()), "events": int(group.events.sum()),
                      "observed_hazard": float(group.events.sum()/group.risk_n.sum()),
                      "predicted_hazard_observed_risk": float(group.expected_events_on_observed_risk.sum()/group.risk_n.sum()),
                      "observed_unconditional_mass": float(group.observed_unconditional_event_mass.sum()),
                      "predicted_unconditional_mass": float(group.predicted_unconditional_event_mass.sum())})
    pd.DataFrame(bands).to_csv(out/"weekly_hazard_bands.csv", index=False)
    # Hold calendar origin and overdue age fixed when describing shock association.
    context_path = out/"diagnostic_anchor_context.parquet"
    if context_path.exists():
        context = pd.read_parquet(context_path)
        predictions = pd.read_parquet(ARTIFACT/"evaluation_predictions"/f"{TEST}.parquet")
        context = context.merge(predictions[["invoice_id", "p_writeoff_365d"]], on="invoice_id", validate="one_to_one")
        context["cutoff_month"] = context.cutoff.dt.strftime("%Y-%m")
        context["overdue_band"] = pd.cut(context.days_past_due, [-np.inf, 0, 30, 90, np.inf], labels=["not_overdue", "01_30", "31_90", "91_plus"])
        context["shock_band_oracle"] = pd.cut(context.shock_origin_oracle, [-np.inf, 1e-12, 1, 2, np.inf], labels=["none", "0_1", "1_2", "2_plus"])
        context["actual_writeoff_365"] = ((context.cause == 2) & (context.time_days <= 365)).astype(float)
        slices = context.groupby(["cutoff_month", "overdue_band", "shock_band_oracle"], observed=True).agg(
            n=("invoice_id", "size"), actual=("actual_writeoff_365", "mean"), predicted=("p_writeoff_365d", "mean")).reset_index()
        slices["gap"] = slices.predicted-slices.actual
        slices.to_csv(out/"shock_age_calendar_slices.csv", index=False)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
