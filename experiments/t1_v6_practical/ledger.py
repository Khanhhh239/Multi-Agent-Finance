"""Recent behavior from append-only, tenant-scoped ledger observations.

Effective date alone never confers visibility. A late allocation or reversal
affects features only from known_at. No oracle outcome columns are accepted.
Coverage exports distinguish an observed zero from a missing ledger.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from experiments.t1_credit_context.practical import _dates, practical_context_features


BEHAVIOR_FEATURES = [
    "b_c_delay_mean_28d", "b_c_delay_delta_28d", "b_c_settled_n_28d",
    "b_c_collection_ratio_28d", "b_c_collection_ratio_delta_28d",
    "b_c_overdue_share", "b_c_overdue_share_delta_28d",
    "b_c_partial_share", "b_c_partial_share_delta_28d",
    "b_i_receipt_frac_28d", "b_c_days_since_receipt", "b_c_open_balance_change_28d",
    "b_ledger_history_days", "b_ledger_report_age_days", "b_ledger_missing",
]
INVOICE_COLUMNS = {"firm_id", "customer_id", "invoice_id", "issue_date", "due_date", "amount_gross", "known_at"}
ENTRY_COLUMNS = {"firm_id", "invoice_id", "entry_id", "event_date", "known_at", "entry_type", "amount"}
COVERAGE_COLUMNS = {"firm_id", "history_start", "through_date", "known_at"}


def _validate(frame, columns, authorized, date_columns):
    if set(frame) != columns:
        raise ValueError("Only registered observed ledger columns are accepted")
    frame = frame.copy()
    if not set(frame.firm_id).issubset(authorized):
        raise ValueError("Ledger records outside authorized tenants")
    for name in date_columns:
        if name == "due_date":
            frame[name] = pd.to_datetime(frame[name], errors="raise", format="mixed")
        else:
            frame[name] = _dates(frame[name])
    return frame


class PracticalFeatureBuilder:
    def __init__(self, invoices, entries, coverage, *, authorized_firms,
                 buyer_observations=None, seller_observations=None, max_report_age_days=7):
        self.authorized = frozenset(authorized_firms)
        if not self.authorized or max_report_age_days < 0:
            raise ValueError("Explicit tenant authorization and report-age policy required")
        self.inv = _validate(invoices, INVOICE_COLUMNS, self.authorized, ["issue_date", "due_date", "known_at"])
        self.ent = _validate(entries, ENTRY_COLUMNS, self.authorized, ["event_date", "known_at"])
        self.cov = _validate(coverage, COVERAGE_COLUMNS, self.authorized, ["history_start", "through_date", "known_at"])
        for frame, key in ((self.inv, ["firm_id", "invoice_id"]), (self.ent, ["firm_id", "entry_id"])):
            if frame[key].isna().any().any() or frame.duplicated(key).any():
                raise ValueError("Missing or duplicate ledger identity")
        if ((self.inv.known_at < self.inv.issue_date).any()
                or (self.ent.known_at < self.ent.event_date).any()
                or (self.cov.known_at < self.cov.through_date).any()
                or (self.cov.history_start > self.cov.through_date).any()):
            raise ValueError("Invalid observation chronology")
        if not self.ent.entry_type.isin(["receipt", "credit", "writeoff"]).all():
            raise ValueError("Unsupported ledger entry type")
        if (not np.isfinite(self.inv.amount_gross).all() or not self.inv.amount_gross.gt(0).all()
                or not np.isfinite(self.ent.amount).all()
                or self.ent.loc[self.ent.entry_type.eq("writeoff"), "amount"].lt(0).any()):
            raise ValueError("Invalid ledger amount")
        for obs in (buyer_observations, seller_observations):
            if obs is not None and not set(obs.firm_id).issubset(self.authorized):
                raise ValueError("Industry records outside authorized tenants")
        self.buyer, self.seller = buyer_observations, seller_observations
        self.max_age = max_report_age_days
        self.cache = {}
        self.inv_by_firm = dict(tuple(self.inv.groupby("firm_id", sort=False)))
        self.ent_by_firm = dict(tuple(self.ent.groupby("firm_id", sort=False)))
        self.cov_by_firm = dict(tuple(self.cov.groupby("firm_id", sort=False)))

    def _state(self, firm, cutoff):
        key = (firm, pd.Timestamp(cutoff))
        if key in self.cache:
            return self.cache[key]
        cutoff = key[1]
        cov = self.cov_by_firm.get(firm, self.cov.iloc[:0])
        cov = cov[cov.known_at.le(cutoff)].sort_values(["through_date", "known_at"])
        if cov.empty or (cutoff - cov.through_date.iloc[-1]).days > self.max_age:
            self.cache[key] = None
            return None
        report = cov.iloc[-1]
        end = report.through_date
        source = self.inv_by_firm.get(firm, self.inv.iloc[:0])
        uncovered = set(source.loc[source.known_at.le(cutoff) & source.issue_date.le(end)
                                   & source.issue_date.lt(report.history_start), "customer_id"])
        inv = source[source.known_at.le(cutoff) & source.issue_date.le(end) & source.issue_date.ge(report.history_start)].copy()
        inv = inv.set_index("invoice_id")
        source_entries = self.ent_by_firm.get(firm, self.ent.iloc[:0])
        entries = source_entries[source_entries.known_at.le(cutoff)
                                & source_entries.event_date.le(end) & source_entries.invoice_id.isin(inv.index)].copy()
        # Signed receipts/credit entries allow append-only accounting reversals.
        for kind, column in (("receipt", "cash"), ("credit", "credit"), ("writeoff", "written")):
            inv[column] = entries.loc[entries.entry_type.eq(kind)].groupby("invoice_id").amount.sum().reindex(inv.index, fill_value=0.)
        inv["open_balance"] = (inv.amount_gross - inv.cash - inv.credit - inv.written).clip(lower=0)
        inv["partial_balance"] = inv.open_balance.where(inv.cash.gt(0) & inv.open_balance.gt(1), 0.)
        inv["overdue_balance"] = inv.open_balance.where(inv.due_date.lt(end), 0.)
        grouped = inv.groupby("customer_id")[["open_balance", "partial_balance", "overdue_balance"]].sum()
        # Aggregate same-time entries before detecting a settlement. Later
        # reversals cannot retroactively change an earlier snapshot.
        movement = entries.groupby(["invoice_id", "known_at", "entry_type"]).amount.sum().unstack("entry_type", fill_value=0.).reset_index()
        for col in ("receipt", "credit", "writeoff"):
            if col not in movement:
                movement[col] = 0.
        movement = movement.sort_values(["invoice_id", "known_at"])
        if len(movement):
            cumulative = movement.groupby("invoice_id")[["receipt", "credit", "writeoff"]].cumsum()
            paid = cumulative.receipt.gt(1) & cumulative.writeoff.eq(0) & cumulative.sum(axis=1).ge(movement.invoice_id.map(inv.amount_gross) - 1)
            crossing = paid & ~paid.groupby(movement.invoice_id).shift(fill_value=False)
            settled = movement[crossing].groupby("invoice_id").known_at.max()
            inv["settled_at"] = inv.index.map(settled)
        else:
            inv["settled_at"] = pd.NaT
        inv.loc[inv.open_balance.gt(1) | inv.written.gt(0), "settled_at"] = pd.NaT
        inv["delay"] = (inv.settled_at - inv.due_date).dt.total_seconds().div(86400).clip(0, 240)
        receipts = entries[entries.entry_type.eq("receipt")].copy()
        receipts["customer_id"] = receipts.invoice_id.map(inv.customer_id)
        state = {"inv": inv, "customers": grouped, "receipts": receipts, "start": report.history_start,
                 "end": end, "cutoff": cutoff, "uncovered_customers": uncovered,
                 "unknown_due_customers": set(inv.loc[inv.open_balance.gt(1) & inv.due_date.isna(), "customer_id"])}
        self.cache[key] = state
        return state

    @staticmethod
    def _window(state, previous):
        inv, rec = state["inv"], state["receipts"]
        left = state["cutoff"] - pd.Timedelta(days=28)
        recent = inv[inv.settled_at.gt(left) & inv.settled_at.le(state["cutoff"])]
        delay = recent.groupby("customer_id").delay.mean()
        count = recent.groupby("customer_id").size()
        received = rec[rec.known_at.gt(left)].groupby("customer_id").amount.sum()
        frac = rec[rec.known_at.gt(left)].groupby("invoice_id").amount.sum().div(inv.amount_gross)
        collection = pd.Series(dtype=float)
        if previous is not None:
            issued = inv[inv.known_at.gt(left)].groupby("customer_id").amount_gross.sum()
            pool = previous["customers"].open_balance.add(issued, fill_value=0.)
            collection = received.reindex(pool.index, fill_value=0.).div(pool.where(pool.gt(0)))
        return delay, count, received, frac, collection

    def transform(self, keys):
        if set(keys) != {"firm_id", "customer_id", "invoice_id", "cutoff"}:
            raise ValueError("Only invoice forecast keys may enter behavior builder")
        keys = keys.reset_index(drop=True).copy()
        if not set(keys.firm_id).issubset(self.authorized):
            raise ValueError("Forecast outside authorized tenants")
        if keys[["firm_id", "customer_id", "invoice_id"]].isna().any().any():
            raise ValueError("Missing forecast identity")
        keys["cutoff"] = _dates(keys.cutoff)
        output = pd.DataFrame(np.nan, index=keys.index, columns=BEHAVIOR_FEATURES)
        output["b_ledger_missing"] = 1.
        industry = practical_context_features(keys[["firm_id", "customer_id", "cutoff"]],
                    buyer_observations=self.buyer, seller_observations=self.seller)
        for (firm, cutoff), idx in keys.groupby(["firm_id", "cutoff"]).groups.items():
            self.cache = {k: v for k, v in self.cache.items() if k[0] == firm and k[1] >= cutoff - pd.Timedelta(days=56)}
            state = self._state(firm, cutoff)
            if state is None:
                continue
            inv, current = state["inv"], state["customers"]
            part = keys.loc[idx]
            # An invoice with the same ID at a different tenant/customer cannot
            # receive a customer's features through an accidental join.
            valid = part.invoice_id.map(inv.customer_id).eq(part.customer_id) & ~part.customer_id.isin(state["uncovered_customers"])
            ix = part.index[valid]
            if not len(ix):
                continue
            part = keys.loc[ix]
            prev = self._state(firm, cutoff - pd.Timedelta(days=28))
            older = self._state(firm, cutoff - pd.Timedelta(days=56))
            delay, count, received, frac, collection = self._window(state, prev)
            history = max(0, (cutoff - state["start"]).days)
            def put(name, values):
                output.loc[ix, name] = part.customer_id.map(values).to_numpy()
            put("b_c_delay_mean_28d", delay)
            put("b_c_settled_n_28d", count.reindex(current.index, fill_value=0))
            put("b_c_collection_ratio_28d", collection)
            overdue = current.overdue_balance.div(current.open_balance.where(current.open_balance.gt(0)))
            overdue = overdue.mask(overdue.index.isin(state["unknown_due_customers"]))
            partial = current.partial_balance.div(current.open_balance.where(current.open_balance.gt(0)))
            put("b_c_overdue_share", overdue)
            put("b_c_partial_share", partial)
            output.loc[ix, "b_i_receipt_frac_28d"] = part.invoice_id.map(frac).fillna(0).to_numpy()
            positive = state["receipts"][state["receipts"].amount.gt(0)].groupby("customer_id").known_at.max()
            output.loc[ix, "b_c_days_since_receipt"] = (cutoff - part.customer_id.map(positive)).dt.total_seconds().div(86400).to_numpy()
            output.loc[ix, "b_ledger_history_days"] = history
            output.loc[ix, "b_ledger_report_age_days"] = (cutoff - state["end"]).days
            output.loc[ix, "b_ledger_missing"] = 0.
            if prev is not None and history >= 28:
                prior = prev["customers"]
                prev_overdue = prior.overdue_balance.div(prior.open_balance.where(prior.open_balance.gt(0)))
                prev_overdue = prev_overdue.mask(prev_overdue.index.isin(prev["unknown_due_customers"]))
                prev_partial = prior.partial_balance.div(prior.open_balance.where(prior.open_balance.gt(0)))
                put("b_c_overdue_share_delta_28d", overdue.subtract(prev_overdue))
                put("b_c_partial_share_delta_28d", partial.subtract(prev_partial))
                put("b_c_open_balance_change_28d", current.open_balance.subtract(prior.open_balance).div(prior.open_balance.where(prior.open_balance.gt(0))))
                prior_delay, _, _, _, prior_collection = self._window(prev, older)
                if history >= 56:
                    put("b_c_delay_delta_28d", delay.subtract(prior_delay))
                    put("b_c_collection_ratio_delta_28d", collection.subtract(prior_collection))
            if history < 28:
                output.loc[ix, ["b_c_delay_mean_28d", "b_c_settled_n_28d", "b_i_receipt_frac_28d", "b_c_collection_ratio_28d"]] = np.nan
        if np.isinf(output.to_numpy()).any():
            raise ValueError("Behavior feature division produced infinity")
        # Cache is local to one transform to avoid retaining a World per cutoff.
        self.cache.clear()
        return pd.concat([industry, output], axis=1)
