"""Convert a dated research ledger into the same accounting view as Workspace.

Noncash credits are claim versions, not receipts. All downstream landmark
features, partial-cash profiles and SHAP use workspace_context on this view.
"""
import pandas as pd
import numpy as np


CONTRACT = "workspace-accounting-landmark18-v1"


def ledger_context(ledger, cutoff):
    """Vectorized adapter for this bounded ledger format, with Workspace semantics.

    General Workspace data (replacements, cancellations, aliases) continues to
    use workspace_context. This adapter handles original claims and dated
    credit versions only; parity is verified against that canonical path.
    """
    clock = pd.Timestamp(cutoff)
    frame = ledger.invoices[(ledger.invoices.issue_date <= clock) & (ledger.invoices.known_at <= clock)].copy()
    def date_values(values):
        return pd.Series(values.reindex(frame.invoice_id).array, index=frame.index)
    credit = ledger.credits[ledger.credits.available <= clock]
    frame["amount"] = np.rint(frame.amount).astype(np.int64)
    credit_sum = frame.invoice_id.map(credit.groupby("invoice_id").amount.sum()).fillna(0)
    frame["credit_amount"] = credit_sum
    frame["amount"] = np.rint((frame.amount-credit_sum).clip(lower=0)).astype(np.int64)
    credit_known = date_values(credit.groupby("invoice_id").available.max())
    frame["known_at"] = pd.concat([frame.known_at, credit_known], axis=1).max(axis=1)
    pay = ledger.payments[(ledger.payments.available <= clock) & ledger.payments.invoice_id.isin(frame.invoice_id)].copy()
    positions = pd.Series(np.arange(len(ledger.payments)), index=ledger.payments.index)
    pay["payment_id"] = [f"receipt_{i}" for i in positions.loc[pay.index]]
    pay = pay.sort_values(["date", "payment_id"], kind="stable")
    pay["amount"] = np.rint(pay.amount).astype(np.int64)
    pay["total"] = pay.groupby("invoice_id").amount.cumsum()
    pay["known_ns"] = pay.known_at.astype("datetime64[ns]").astype("int64")
    pay["known_max"] = pd.to_datetime(pay.groupby("invoice_id").known_ns.cummax())
    claim = frame.set_index("invoice_id").amount
    full = pay[pay.total >= pay.invoice_id.map(claim)].drop_duplicates("invoice_id")
    frame["settled"] = date_values(full.set_index("invoice_id").date)
    settled_known = date_values(full.set_index("invoice_id").known_max)
    frame["settled_known_at"] = pd.concat([settled_known, frame.known_at.where(frame.settled.notna())], axis=1).max(axis=1)
    frame["received"] = frame.invoice_id.map(pay.groupby("invoice_id").amount.sum()).fillna(0)
    frame["remaining_amount"] = (frame.amount-frame.received).clip(lower=0)
    frame["last_receipt"] = date_values(pay.groupby("invoice_id").date.max())
    frame["receipt_count"] = frame.invoice_id.map(pay.groupby("invoice_id").size()).fillna(0)
    recent = pay[pay.date > clock-pd.Timedelta(days=28)]
    frame["received_28d"] = frame.invoice_id.map(recent.groupby("invoice_id").amount.sum()).fillna(0)
    frame["written_off_at"] = frame.written_off_at.where(frame.written_off_at <= clock)
    frame.attrs["cutoff"] = str(clock.date())
    return frame


def workspace_data(ledger):
    invoices = [dict(invoice_id=str(r.invoice_id), customer_id=str(r.customer_id),
                     issue_date=str(r.issue_date.date()), due_date=str(r.due_date.date()),
                     known_at=str(r.known_at.date()), amount=int(round(r.amount)), currency="VND")
                for r in ledger.invoices.itertuples()]
    versions = [dict(r) for r in invoices]
    by_id = {r["invoice_id"]: r for r in invoices}
    totals = {}
    for r in ledger.credits.sort_values("available").itertuples():
        totals[r.invoice_id] = totals.get(r.invoice_id, 0) + r.amount
        original = by_id[r.invoice_id]
        versions.append(dict(original, amount=max(0, int(round(original["amount"] - totals[r.invoice_id]))),
                             known_at=str(r.available.date())))
    payments = [dict(payment_id=f"receipt_{i}", invoice_id=str(r.invoice_id),
                     payment_date=str(r.date.date()), known_at=str(r.known_at.date()),
                     amount=int(round(r.amount))) for i, r in enumerate(ledger.payments.itertuples())]
    actions = [dict(event_id=f"writeoff_{r.invoice_id}", invoice_id=str(r.invoice_id), kind="write_off",
                    date=str(r.written_off_at.date()), known_at=str(r.written_off_at.date()))
               for r in ledger.invoices.itertuples() if pd.notna(r.written_off_at)]
    return dict(invoices=invoices, payments=payments, actions=actions, outflows=[],
                record_history={"invoices": versions})
