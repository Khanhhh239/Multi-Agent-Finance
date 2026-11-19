"""Private v6 feature policy: only facts available at the forecast cutoff.

The shared v4/v5 whitelist and SnapshotBuilder are deliberately not edited.
End-of-world balances, payment counts, risk flags and latent variables are
never used. Payments and write-offs are filtered by their dated availability.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from agent1.models.features import FEATURES, MODEL_VISIBLE_COLUMNS, SnapshotBuilder


EXTRA_FEATURES = [
    "c_closed_n_asof", "c_writeoff_n_asof", "c_writeoff_rate_eb_v6",
    "c_writeoff_180d_n", "f_writeoff_rate_asof", "f_writeoff_180d_rate",
    "c_overdue30_amount_share", "c_overdue60_amount_share",
    "c_overdue90_amount_share", "f_overdue90_amount_share",
    "c_open_amount_rel_v6", "i_payment_count_asof", "i_days_since_receipt",
    "i_receipt_frac_28d", "i_receipt_frac_90d", "i_credit_frac_known",
    "i_remaining_frac", "i_has_receipt",
]
V6_FEATURES = list(FEATURES) + EXTRA_FEATURES


def validate_features(features):
    if len(features) != len(set(features)) or set(features) - set(V6_FEATURES):
        raise ValueError("Unregistered or duplicate v6 feature")


class V6SnapshotBuilder(SnapshotBuilder):
    def snapshot(self, T, visible_from=None, firms=None):
        result = super().snapshot(T, visible_from=visible_from, firms=firms)
        if result.empty:
            return result
        T = pd.Timestamp(T)
        visible = self.inv[self.inv.issue_date.le(T)].copy()
        if firms is not None:
            visible = visible[visible.firm_id.isin(firms)]
        if visible_from is not None:
            visible = visible[visible.issue_date.ge(pd.Timestamp(visible_from))]
        settled = visible.label_date.notna() & visible.label_date.le(T)
        written = visible.writeoff_date.notna() & visible.writeoff_date.le(T)
        closed = visible[settled | written]
        c_closed = closed.groupby("customer_id").size()
        c_written = visible[written].groupby("customer_id").size()
        f_closed = closed.groupby("firm_id").size()
        f_written = visible[written].groupby("firm_id").size()
        firm_rate = (f_written.reindex(f_closed.index, fill_value=0) + 1) / (f_closed + 20)
        prior = result.firm_id.map(firm_rate).fillna(0.05)
        result["c_closed_n_asof"] = result.customer_id.map(c_closed).fillna(0)
        result["c_writeoff_n_asof"] = result.customer_id.map(c_written).fillna(0)
        result["c_writeoff_rate_eb_v6"] = (
            result.c_writeoff_n_asof + 8 * prior
        ) / (result.c_closed_n_asof + 8)
        result["f_writeoff_rate_asof"] = prior
        recent_written = written & visible.writeoff_date.gt(T - pd.Timedelta(days=180))
        recent_closed = (settled & visible.label_date.gt(T - pd.Timedelta(days=180))) | recent_written
        recent_w = visible[recent_written].groupby("firm_id").size()
        recent_c = visible[recent_closed].groupby("firm_id").size()
        recent_rate = (recent_w.reindex(recent_c.index, fill_value=0) + 1) / (recent_c + 20)
        result["f_writeoff_180d_rate"] = result.firm_id.map(recent_rate).fillna(prior)
        result["c_writeoff_180d_n"] = result.customer_id.map(
            visible[recent_written].groupby("customer_id").size()
        ).fillna(0)

        # Base amount_open already subtracts only dated payments/credit known at T.
        total_c = result.groupby("customer_id").amount_open.sum()
        total_f = result.groupby("firm_id").amount_open.sum()
        for days in (30, 60, 90):
            overdue = result[result.days_past_due.ge(days)]
            share = overdue.groupby("customer_id").amount_open.sum().div(total_c.clip(lower=1))
            result[f"c_overdue{days}_amount_share"] = result.customer_id.map(share).fillna(0)
        share_f = result[result.days_past_due.ge(90)].groupby("firm_id").amount_open.sum().div(total_f.clip(lower=1))
        result["f_overdue90_amount_share"] = result.firm_id.map(share_f).fillna(0)
        med = visible.groupby("firm_id").amount_gross.median().clip(lower=1)
        result["c_open_amount_rel_v6"] = result.customer_id.map(total_c) / result.firm_id.map(med)

        for name in ("i_payment_count_asof", "i_receipt_frac_28d", "i_receipt_frac_90d", "i_has_receipt"):
            result[name] = 0.0
        result["i_days_since_receipt"] = np.nan
        if self.pay is not None:
            known = self.pay[self.pay.pdate.le(T) & self.pay.invoice_id.isin(result.invoice_id)]
            result["i_payment_count_asof"] = result.invoice_id.map(known.groupby("invoice_id").size()).fillna(0)
            last = result.invoice_id.map(known.groupby("invoice_id").pdate.max())
            result["i_days_since_receipt"] = (T - last).dt.days
            result["i_has_receipt"] = result.i_payment_count_asof.gt(0).astype(float)
            for days in (28, 90):
                recent = known[known.pdate.gt(T - pd.Timedelta(days=days))]
                received = result.invoice_id.map(recent.groupby("invoice_id").face_amount.sum()).fillna(0)
                result[f"i_receipt_frac_{days}d"] = (received / result.amount_gross).clip(0, 1)
        indexed = visible.set_index("invoice_id")
        credit = indexed.credit_note.where(indexed.credit_note_date.le(T), 0).fillna(0)
        result["i_credit_frac_known"] = (result.invoice_id.map(credit) / result.amount_gross).clip(0, 1)
        result["i_remaining_frac"] = (result.amount_open / result.amount_gross).clip(0, 1)
        return result


def model_view(snapshot, cutoff):
    if snapshot.empty:
        return snapshot.copy()
    validate_features(V6_FEATURES)
    if not pd.to_datetime(snapshot.cutoff).eq(pd.Timestamp(cutoff)).all():
        raise ValueError("Mixed cutoffs in v6 forecast view")
    missing = set(V6_FEATURES) - set(snapshot)
    if missing:
        raise ValueError(f"Missing v6 features: {sorted(missing)}")
    columns = list(dict.fromkeys((*MODEL_VISIBLE_COLUMNS, *EXTRA_FEATURES)))
    return snapshot[[c for c in columns if c in snapshot]].copy()


class ReceiptIndex:
    """Dated cash lookup used for labels, never passed to an estimator."""
    def __init__(self, payments):
        p = payments[["invoice_id", "pay_date_true", "amount"]].copy()
        p["pay_date_true"] = pd.to_datetime(p.pay_date_true).astype("datetime64[ns]")
        p["invoice_id"] = p.invoice_id.astype(str)
        if p.amount.lt(0).any() or p.pay_date_true.isna().any():
            raise ValueError("Invalid cash receipt labels")
        p = p.groupby(["invoice_id", "pay_date_true"], as_index=False).amount.sum()
        p = p.sort_values(["invoice_id", "pay_date_true"])
        p["cumulative_cash"] = p.groupby("invoice_id").amount.cumsum()
        self.pay = p.sort_values("pay_date_true")[["invoice_id", "pay_date_true", "cumulative_cash"]]

    def total_at(self, invoice_ids, dates):
        if self.pay.empty:
            return np.zeros(len(invoice_ids))
        query = pd.DataFrame({"invoice_id": np.asarray(invoice_ids).astype(str), "at": pd.to_datetime(np.asarray(dates)).astype("datetime64[ns]"), "row": np.arange(len(invoice_ids))})
        joined = pd.merge_asof(query.sort_values("at"), self.pay, left_on="at", right_on="pay_date_true", by="invoice_id", direction="backward")
        return joined.sort_values("row").cumulative_cash.fillna(0).to_numpy(float)

    def targets(self, frame, horizons, label_end):
        base = self.total_at(frame.invoice_id, frame.cutoff)
        values = []
        for day in horizons:
            end = frame.cutoff + pd.Timedelta(days=day)
            if end.gt(pd.Timestamp(label_end)).any():
                raise ValueError("Cash target lacks complete follow-up")
            cash = np.maximum(0, self.total_at(frame.invoice_id, end) - base)
            values.append(cash)
        return np.column_stack(values)
