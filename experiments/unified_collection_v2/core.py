"""One accounting transition shared by observed training and generated rollouts.

Only the label builder receives future transactions. The estimator sees origin
features, known calendar and state produced by preceding weekly transitions.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from agent1.models import t1
from experiments.t1_competing_v6.features import ReceiptIndex, V6_FEATURES

OPEN, PAID, WRITEOFF, CREDIT = range(4)
STATE_NAMES = ("open", "paid", "writeoff", "credit_note")
PATH_FEATURES = ["remaining_origin_ratio", "cash_origin_ratio", "credit_origin_ratio",
                 "receipt_weeks", "weeks_since_receipt", "last_cash_origin_ratio"]
FEATURES = [f"origin_{c}" for c in V6_FEATURES] + [f"week_{c}" for c in t1.WEEK_FEATS] + PATH_FEATURES


def origin_view(frame):
    """Whitelist boundary: no future labels or transactions survive this view."""
    context = ["invoice_id", "firm_id", "customer_id", "cutoff", "amount_open", "top1", "top2"]
    columns = list(dict.fromkeys(context + V6_FEATURES))
    if frame.empty:
        return frame.reindex(columns=columns).copy()
    frame = frame.copy()
    for name in ("top1", "top2"):
        if name not in frame:
            frame[name] = np.nan
    if set(columns) - set(frame):
        raise ValueError(f"Missing origin fields: {sorted(set(columns)-set(frame))}")
    out = frame[columns].reset_index(drop=True).copy()
    if len(out) and (not np.isfinite(out.amount_open).all() or out.amount_open.le(0).any()):
        raise ValueError("Origin requires positive finite collectible balances")
    return out


@dataclass
class PathState:
    remaining: np.ndarray
    cash: np.ndarray
    credit: np.ndarray
    receipt_weeks: np.ndarray
    since_receipt: np.ndarray
    last_cash: np.ndarray
    status: np.ndarray

    @classmethod
    def start(cls, n):
        return cls(np.ones(n), np.zeros(n), np.zeros(n), np.zeros(n),
                   np.full(n, np.nan), np.zeros(n), np.zeros(n, dtype=np.int8))

    def take(self, indices):
        return PathState(*(getattr(self, name)[indices] for name in self.__dataclass_fields__))

    def matrix(self):
        return np.column_stack((self.remaining, self.cash, self.credit,
                                self.receipt_weeks, self.since_receipt, self.last_cash))


def advance(state, indices, cash_fraction, credit_fraction, terminal):
    """Fractions are of opening balance. Return cash, credit and writeoff ratios.

    Exact full-payment outcomes are absorbing. A writeoff extinguishes only the
    residual after cash/credit, and never contributes to cash.
    """
    indices = np.asarray(indices, dtype=int)
    cash, credit, status = np.broadcast_arrays(np.asarray(cash_fraction, float),
                                              np.asarray(credit_fraction, float),
                                              np.asarray(terminal, int))
    if cash.shape != indices.shape or (state.status[indices] != OPEN).any():
        raise ValueError("Transition requires matching open rows")
    if (not np.isfinite(cash).all() or not np.isfinite(credit).all() or
            (cash < 0).any() or (credit < 0).any() or (cash+credit > 1+1e-8).any() or
            not np.isin(status, range(4)).all()):
        raise ValueError("Invalid cash/noncash transition")
    residual = np.maximum(0., 1-cash-credit)
    if ((status == PAID) | (status == CREDIT))[residual > 1e-8].any():
        raise ValueError("Paid/credit closure must extinguish the balance")
    if ((status == OPEN) & (residual <= 1e-12)).any():
        raise ValueError("Zero balance cannot remain open")
    before = state.remaining[indices].copy()
    received, credited = before*cash, before*credit
    written = np.where(status == WRITEOFF, before*residual, 0.)
    state.remaining[indices] = np.where(status == OPEN, before*residual, 0.)
    state.cash[indices] += received
    state.credit[indices] += credited
    positive = cash > 0
    state.receipt_weeks[indices] += positive
    state.since_receipt[indices] = np.where(positive, 0., state.since_receipt[indices]+1)
    state.last_cash[indices] = received
    state.status[indices] = status
    error = before - received - credited - written - state.remaining[indices]
    if np.max(np.abs(error), initial=0) > 1e-8:
        raise ValueError("Accounting identity failed")
    return received, credited, written


def feature_matrix(origin, week, state, invoice_indices=None):
    if not 1 <= week <= 13:
        raise ValueError("Week outside 13-step contract")
    index = np.arange(len(origin)) if invoice_indices is None else np.asarray(invoice_indices, int)
    if len(index) != len(state.remaining):
        raise ValueError("Feature/state alignment mismatch")
    calendar = t1._week_feats(origin, week)
    base = origin[V6_FEATURES].to_numpy(np.float32)[index]
    weekly = np.column_stack([calendar[c][index] for c in t1.WEEK_FEATS])
    return np.column_stack((base, weekly, state.matrix())).astype(np.float32)


class LabelIndex:
    def __init__(self, invoices, payments):
        if not invoices.invoice_id.is_unique:
            raise ValueError("Duplicate invoice labels")
        if "currency" in invoices and not invoices.currency.eq("VND").all():
            raise ValueError("Prototype supports VND only")
        if "fx_adjustment" in payments and payments.fx_adjustment.fillna(0).ne(0).any():
            raise ValueError("FX accounting is outside this prototype contract")
        self.invoices = invoices.set_index("invoice_id")
        wo = payments.invoice_id.map(self.invoices.writeoff_date)
        if (pd.to_datetime(payments.pay_date_true) > pd.to_datetime(wo)).any():
            raise ValueError("Post-writeoff recoveries are unsupported")
        self.receipts = ReceiptIndex(payments)

    def weekly(self, frame, label_end):
        origin = origin_view(frame)
        if (pd.to_datetime(origin.cutoff)+pd.Timedelta(days=91)).gt(pd.Timestamp(label_end)).any():
            raise ValueError("Weekly labels require full 13-week follow-up")
        inv = self.invoices.reindex(origin.invoice_id)
        if inv.index.hasnans or inv.amount_gross.isna().any():
            raise ValueError("Missing invoice labels")
        at = pd.to_datetime(origin.cutoff).reset_index(drop=True)
        ids = origin.invoice_id
        cumulative = np.column_stack([self.receipts.total_at(ids, at+pd.Timedelta(days=7*k))
                                      for k in range(14)])
        cash = np.diff(cumulative, axis=1)
        credit_at = pd.to_datetime(inv.credit_note_date).to_numpy()
        credit_value = inv.credit_note.fillna(0).to_numpy(float)
        paid_at = pd.to_datetime(inv.paid_date_true).to_numpy()
        wo_at = pd.to_datetime(inv.writeoff_date).to_numpy()
        pure_credit = inv.closure_type.eq("credit_note").to_numpy()
        if (pd.notna(paid_at) & pd.notna(wo_at)).any():
            raise ValueError("Post-writeoff recoveries/conflicting closures are unsupported")
        credit = np.zeros_like(cash)
        status = np.zeros(cash.shape, dtype=np.int8)
        for k in range(13):
            left = (at+pd.Timedelta(days=7*k)).to_numpy()
            right = (at+pd.Timedelta(days=7*(k+1))).to_numpy()
            credit[:, k] = np.where((credit_at > left) & (credit_at <= right), credit_value, 0)
            status[:, k] = np.where((wo_at > left) & (wo_at <= right), WRITEOFF,
                             np.where((paid_at > left) & (paid_at <= right), PAID,
                             np.where(pure_credit & (credit_at > left) & (credit_at <= right), CREDIT, OPEN)))
        # Check origin accounting, not just future targets.
        known_credit = np.where(credit_at <= at.to_numpy(), credit_value, 0)
        actual_open = inv.amount_gross.to_numpy(float)-cumulative[:, 0]-known_credit
        if np.max(np.abs(actual_open-origin.amount_open.to_numpy(float)), initial=0) > 1:
            raise ValueError("Origin balance does not reconcile with dated transactions")
        return origin, cash, credit, status


def cash_band(fraction, edges):
    f = np.asarray(fraction)
    # Codes: 0=exact zero; 1..4=partial; 5=exact full.
    partial = np.searchsorted(np.asarray(edges)[1:-1], f, side="right")+1
    return np.where(f <= 0, 0, np.where(f >= 1, len(edges), partial)).astype(int)


def outcome_keys(cash, credit, status, edges):
    return np.column_stack((cash_band(cash, edges), cash_band(credit, edges), status)).astype(int)


def observed_rows(frame, labels, label_end, edges):
    origin, cash, credit, status = labels.weekly(frame, label_end)
    state = PathState.start(len(origin))
    xs, keys, pairs, info = [], [], [], []
    for week in range(1, 14):
        active = np.flatnonzero(state.status == OPEN)
        if not len(active):
            break
        opening = state.remaining[active]*origin.amount_open.to_numpy()[active]
        c, r = cash[active, week-1].copy(), credit[active, week-1].copy()
        if (c < -1e-6).any() or (r < 0).any() or (c+r > opening+1).any():
            raise ValueError("Observed cash/credit exceeds opening balance")
        cf, rf = np.maximum(c, 0)/opening, r/opening
        st = status[active, week-1]
        # Reconcile sub-VND rounding only; larger closure discrepancies fail.
        closed = np.isin(st, [PAID, CREDIT])
        if (np.abs(opening-c-r)[closed] > 1).any():
            raise ValueError("Terminal labels fail cash/noncash reconciliation")
        rf = np.where(closed & (rf > 0), 1-cf, rf)
        cf = np.where(closed & (rf == 0), 1., cf)
        total = cf+rf
        rf = np.where(total > 1, np.maximum(0, 1-cf), rf)
        cf = np.minimum(cf, 1)
        xs.append(feature_matrix(origin, week, state.take(active), active))
        keys.append(outcome_keys(cf, rf, st, edges))
        pairs.append(np.column_stack((cf, rf)))
        detail = frame.iloc[active][[c for c in ("world", "partition", "firm_id", "customer_id", "invoice_id", "cutoff") if c in frame]].copy()
        detail["week"] = week
        detail["opening"] = opening
        detail["cash_actual"] = c
        info.append(detail)
        advance(state, active, cf, rf, st)
    return np.vstack(xs), np.vstack(keys), np.vstack(pairs), pd.concat(info, ignore_index=True)


def fit_vocabulary(keys, pairs):
    """Joint outcome representatives are feasible observed pairs, never centroids."""
    result = []
    for key in np.unique(keys, axis=0):
        take = np.all(keys == key, axis=1)
        values = pairs[take]
        target = np.median(values, axis=0)
        pair = values[np.argmin(np.sum((values-target)**2, axis=1))]
        result.append({"key": key.tolist(), "cash_fraction": float(pair[0]),
                       "credit_fraction": float(pair[1]), "status": int(key[2]), "train_rows": int(take.sum())})
    return sorted(result, key=lambda c: (c["cash_fraction"], c["credit_fraction"], c["status"]))


def encode(keys, vocabulary, allow_unknown=False):
    lookup = {tuple(c["key"]): i for i, c in enumerate(vocabulary)}
    y = np.array([lookup.get(tuple(k), -1) for k in keys], dtype=int)
    if (y < 0).any() and not allow_unknown:
        raise ValueError("Outcome absent from train vocabulary")
    return y
