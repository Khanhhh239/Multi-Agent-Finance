"""Synthetic ERP observation process, explicitly separate from real adapters.

This is not real customer KYC. A quarterly batch learns mapped industry for a
fixed 75% sample, 14 days after quarter-end. No backdating to first invoice.
Ledger features receive ledger allocations/posting dates, not true cash links.
All simulation assumptions must be locked before model training.
"""
from __future__ import annotations

import hashlib

import pandas as pd

from .ledger import PracticalFeatureBuilder


OBSERVATION_DESIGN = {
    "evidence": "synthetic ERP observation simulation; not verified SME records",
    "invoice_ingestion_lag_days": 1,
    "ledger_ingestion_lag_days": 1,
    "credit_ingestion_lag_days": 1,
    "writeoff_ingestion_lag_days": 7,
    "industry_batch_frequency": "calendar quarter",
    "industry_publication_lag_days": 14,
    "buyer_industry_coverage": 0.75,
    "industry_sample_seed": 202611051,
    "industry_time_policy": "first completed quarterly customer-master export after buyer is observed",
    "coverage": "daily complete ledger posting exports with one-day ingestion lag",
    "not_model_inputs": ["true cash invoice links", "private exposures", "shock schedules", "default dates"],
}


def _sample(world, customer):
    value = hashlib.sha256(f"202611051/{world}/{customer}".encode()).digest()
    return int.from_bytes(value[:8], "big") / 2**64 < OBSERVATION_DESIGN["buyer_industry_coverage"]


def observed_tables(directory):
    directory = directory.resolve()
    raw = pd.read_parquet(directory / "invoices.parquet")
    pay = pd.read_parquet(directory / "payments.parquet",
                          columns=["payment_id", "firm_id", "ledger_invoice_id", "ledger_post_date", "amount"])
    invoices = raw[["firm_id", "customer_id", "invoice_id", "issue_date", "due_date", "amount_gross"]].copy()
    invoices["known_at"] = invoices.issue_date + pd.Timedelta(days=1)
    receipts = pay.rename(columns={"payment_id": "entry_id", "ledger_invoice_id": "invoice_id", "ledger_post_date": "event_date"})
    receipts["entry_id"] = "receipt/" + receipts.entry_id.astype(str)
    receipts["entry_type"] = "receipt"
    receipts["known_at"] = receipts.event_date + pd.Timedelta(days=1)
    extras = []
    for kind, date_col, amount_col, lag in (("credit", "credit_note_date", "credit_note", 1),
                                           ("writeoff", "writeoff_date", "writeoff_amount", 7)):
        event = raw.loc[raw[date_col].notna() & raw[amount_col].gt(0), ["firm_id", "invoice_id", date_col, amount_col]].rename(
            columns={date_col: "event_date", amount_col: "amount"})
        event["entry_id"] = kind + "/" + event.invoice_id
        event["entry_type"] = kind
        event["known_at"] = event.event_date + pd.Timedelta(days=lag)
        extras.append(event)
    entries = pd.concat([receipts, *extras], ignore_index=True)[
        ["firm_id", "invoice_id", "entry_id", "event_date", "known_at", "entry_type", "amount"]]
    first, last = raw.issue_date.min(), raw.observation_end.max()
    reports = []
    for firm in raw.firm_id.unique():
        report = pd.DataFrame({"through_date": pd.date_range(first, last)})
        report["firm_id"], report["history_start"] = firm, first
        report["known_at"] = report.through_date + pd.Timedelta(days=1)
        reports.append(report)
    coverage = pd.concat(reports, ignore_index=True)[["firm_id", "history_start", "through_date", "known_at"]]
    # Classification is learned at a new synthetic batch observation, not
    # asserted to have been known on the invoice date in the original World.
    customers = pd.read_parquet(directory / "customers.parquet", columns=["firm_id", "customer_id", "industry"])
    first_seen = invoices.groupby(["firm_id", "customer_id"]).known_at.min()
    customers["seen"] = pd.MultiIndex.from_frame(customers[["firm_id", "customer_id"]]).map(first_seen)
    customers = customers[customers.seen.notna() & customers.customer_id.map(lambda c: _sample(directory.name, c))].copy()
    customers["known_at"] = customers.seen.dt.to_period("Q").dt.end_time.dt.normalize() + pd.Timedelta(days=14)
    customers["source_kind"] = "customer_master"
    customers["source_ref"] = directory.name + "/simulated-quarterly-master/" + customers.customer_id
    buyer = customers[["firm_id", "customer_id", "industry", "known_at", "source_kind", "source_ref"]]
    firms = pd.read_parquet(directory / "firms.parquet", columns=["firm_id", "industry"])
    firms["known_at"] = first.to_period("Q").end_time.normalize() + pd.Timedelta(days=14)
    firms["source_kind"] = "own_company_profile"
    firms["source_ref"] = directory.name + "/simulated-onboarding-profile/" + firms.firm_id
    return invoices, entries, coverage, buyer, firms


def build_features(directory, frame, output_directory=None):
    inv, entries, coverage, buyer, seller = observed_tables(directory)
    if output_directory is not None:
        output_directory.mkdir(parents=True, exist_ok=False)
        for name, table in (("invoices", inv), ("ledger_entries", entries), ("coverage", coverage),
                            ("buyer_industry", buyer), ("seller_industry", seller)):
            table.to_parquet(output_directory / f"{name}.parquet", index=False)
    builder = PracticalFeatureBuilder(inv, entries, coverage, authorized_firms=set(inv.firm_id),
                                     buyer_observations=buyer, seller_observations=seller)
    return builder.transform(frame[["firm_id", "customer_id", "invoice_id", "cutoff"]])
