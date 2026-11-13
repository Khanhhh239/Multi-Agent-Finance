"""Explicit payment completeness attestations; missing scope is censored."""

import pandas as pd


def attest(data, cutoff, known_at):
    starts = [r["issue_date"] for r in data.get("invoices", []) if r["known_at"] <= str(cutoff)[:10]]
    return dict(start_date=min(starts, default=str(cutoff)[:10]), end_date=str(cutoff)[:10],
                known_at=str(known_at)[:10], complete=True, source="payments_complete_confirmation")


def followup_days(data, origin, label_end, invoice_id, customer_id):
    days = min(91, (label_end - origin).days)
    covered = [False] * days
    for r in data.get("payment_coverage", []):
        if (r.get("complete") is not True or pd.Timestamp(r["known_at"]) > label_end
                or r.get("invoice_ids") is not None and invoice_id not in r["invoice_ids"]
                or r.get("customer_ids") is not None and customer_id not in r["customer_ids"]):
            continue
        first = max(1, (pd.Timestamp(r["start_date"]) - origin).days)
        last = min(days, (pd.Timestamp(r["end_date"]) - origin).days)
        for day in range(first, last + 1):
            covered[day - 1] = True
    return next((i for i, known in enumerate(covered) if not known), days)
