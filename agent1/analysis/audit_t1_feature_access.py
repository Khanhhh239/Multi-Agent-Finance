"""Inventory feature accessibility from one seller's B2B data, without fitting.

Policies describe required real sources, not proof those sources are connected.
The historical v6 model and synthetic measurement experiment stay unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from agent1.paths import ROOT
from agent1.models.t1 import WEEK_FEATS
from experiments.t1_competing_v6.features import V6_FEATURES
from experiments.t1_credit_context.features import CREDIT_FEATURES, INDUSTRY_FEATURES
from experiments.t1_credit_context.practical import PRACTICAL_CONTEXT_FEATURES


GROUPS = [
    ("invoice_contract", "internal", "Seller invoice and agreed contract terms", "Retain from dated own records; do not invent missing due dates", [
        "log_amount_rel", "term_days", "age_days", "days_to_due", "days_past_due", "is_overdue", "issue_month", "due_dom", "due_dow", "has_due"]),
    ("allocated_receipts", "conditional_internal", "Seller receipts allocated to own invoices, with reconciliation knowledge time", "Require observed allocations; true synthetic links are not an available source", [
        "paid_frac_so_far", "i_payment_count_asof", "i_days_since_receipt", "i_receipt_frac_28d", "i_receipt_frac_90d", "i_remaining_frac", "i_has_receipt"]),
    ("credit_note", "conditional_internal", "Seller dated invoice adjustments / credit notes with knowledge time", "Require adjustment lifecycle; absence of imported data is not confirmed zero", ["i_credit_frac_known"]),
    ("open_receivables", "conditional_internal", "Seller open AR, known receipts, known closures and adjustments", "Use only receivables owed to this seller, never customer's entire balance sheet", [
        "c_open_n", "c_open_share", "c_open_overdue_n", "c_max_dpd", "f_open_n", "c_overdue30_amount_share", "c_overdue60_amount_share", "c_overdue90_amount_share", "f_overdue90_amount_share", "c_open_amount_rel_v6"]),
    ("settled_history", "conditional_internal", "Seller own observed settlement history and imported history coverage", "Use bank/reconciled facts known at cutoff; tenure is observed relationship history, not company age", [
        "c_n_hist", "c_delay_mean", "c_delay_med", "c_delay_std", "c_delay_eb", "c_delay_ewm", "c_late_share", "c_late30_share", "c_last_delay", "c_trend", "c_days_since_last_pay", "c_tenure_days", "c_life_med", "c_payrun_strength", "c_days_due_to_payrun", "c_dow_strength", "c_amount_rel_med", "c_pay_30d", "f_n_hist", "f_delay_mean", "f_resid_28d", "f_resid_trend", "payrun_in_k"]),
    ("promise", "conditional_internal", "Seller timestamped collection CRM plus observed promise outcome", "Promises are optional; kept must be derived from observed receipts, not synthetic outcome", [
        "has_promise", "days_to_promised", "promise_overdue", "c_promise_rel", "c_promise_n", "promised_in_k"]),
    ("writeoff_history", "conditional_not_ingested", "Seller own dated write-off decisions and settled invoices, with complete import coverage", "Not global customer defaults; current observed training path has no writeoff ingestion", [
        "c_closed_n_asof", "c_writeoff_n_asof", "c_writeoff_rate_eb_v6", "c_writeoff_180d_n", "f_writeoff_rate_asof", "f_writeoff_180d_rate"]),
    ("calendar", "known_calendar", "Forecast index, agreed due date and calendar version available at cutoff", "Use known calendar or explicit assumptions; future official holiday decisions are not already published", [
        "days_to_tet", "cut_month", "due_near_tet", "k", "dtd_k", "due_in_k", "bd_in_k", "tet_in_k"]),
]


def inventory():
    policies = {}
    for group, access, source, decision, names in GROUPS:
        for name in names:
            if name in policies:
                raise ValueError(f"Duplicate policy: {name}")
            policies[name] = dict(group=group, access=access, required_source=source, decision=decision)
    if set(policies) != set(V6_FEATURES + WEEK_FEATS):
        raise ValueError("Access policy does not cover exact v6 feature set")
    rows = [dict(feature=name, feature_set="v6_snapshot" if name in V6_FEATURES else "v6_week",
                 tenant_scope="own_seller_only", **policies[name]) for name in V6_FEATURES + WEEK_FEATS]
    for name in CREDIT_FEATURES:
        rows.append(dict(feature=name, feature_set="research_context", tenant_scope="external_series",
                         group="simulated_credit_survey", access="hypothetical_unavailable",
                         required_source="No actual supplier or historical releases connected",
                         decision="Exclude from practical input; simulation only"))
    for name in INDUSTRY_FEATURES:
        rows.append(dict(feature=name, feature_set="research_context", tenant_scope="own_seller_only",
                         group="dated_industry", access="conditional_dated_source",
                         required_source="Own profile / customer master / supplied or verified extract with actual known_at",
                         decision="Use practical adapter; absent or unmapped record becomes unknown; no first-invoice backdating"))
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/analysis/t1_feature_access_20261105")
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to((ROOT / "outputs/analysis").resolve()):
        raise ValueError("Output must remain in outputs/analysis")
    out.mkdir(parents=True, exist_ok=False)
    table = inventory()
    table.to_csv(out / "feature_access.csv", index=False)
    protected = json.loads((ROOT / "outputs/analysis/t1_credit_context_20261105/verification.json").read_text(encoding="utf-8"))["prerequisites_sha256"]
    changed = []
    for relative, expected in protected.items():
        with (ROOT / relative).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                changed.append(relative)
    if changed:
        raise ValueError(f"Historical files changed: {changed}")
    summary = dict(scope="source accessibility audit; no prediction-quality claim", n_v6_snapshot=len(V6_FEATURES),
                   n_v6_week=len(WEEK_FEATS), n_research_context=len(CREDIT_FEATURES + INDUSTRY_FEATURES),
                   access_counts=dict(Counter(table.access)), practical_context_features=PRACTICAL_CONTEXT_FEATURES,
                   excluded_hypothetical_macro_features=CREDIT_FEATURES, protected_files_checked=len(protected),
                   changed_protected_files=changed, fit_or_calibration_performed=False,
                   limitation="Source requirements are audited; actual ERP/CRM sources have not been connected")
    with (out / "summary.json").open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
