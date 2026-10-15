"""Extra past-only features: per-entity baselines, approver concentration, near-duplicates.

The friend's 190 features only keep company-level history per transaction type. Fraud that hides inside
one vendor's, one employee's or one creator-approver pair's own behaviour (overpricing, padded payroll,
collusion) is invisible to company-level statistics. Everything here is computed in one chronological
pass and each row only sees rows posted strictly earlier (ties are updated after the batch).
"""
from __future__ import annotations

import math
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

VENDOR_KINDS = {"vendor_payment", "stock_purchase", "material_purchase", "rent", "equipment_purchase", "selling_expense"}
TET = [datetime(2024, 2, 10), datetime(2025, 1, 29)]
DAY = 86400.0

ENGINEERED = [
    "creator_unsupported_selfcash_30d",
    "price_n", "price_logratio", "price_logz", "price_shift3", "is_bonus_season",
    "v_n", "v_logz", "v_logratio", "v_days_since_last", "v_nearest_amount_gap",
    "p_n", "p_logratio", "cu_n", "cu_logratio",
    "near_dup_30d", "near_dup_other_invoice_30d",
    "pair_count_90d", "pair_share_90d", "creator_n_90d", "creator_distinct_approvers_90d", "pair_exclusive",
    "creator_self_rate_90d", "amount_selflimit_ratio", "creator_cash_30d", "creator_cash_near_selflimit_30d",
    "dom", "is_month_end", "is_pre_tet", "vendor_share_90d",
]


class Welford:
    __slots__ = ("n", "mean", "m2")

    def __init__(self):
        self.n, self.mean, self.m2 = 0, 0.0, 0.0

    def add(self, x):
        self.n += 1
        d = x - self.mean
        self.mean += d / self.n
        self.m2 += d * (x - self.mean)

    def std(self):
        return math.sqrt(self.m2 / (self.n - 1)) if self.n > 1 else 0.0


def _ts(series):
    return pd.to_datetime(series, utc=True).dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None)


def engineered_features(dataset: Path) -> pd.DataFrame:
    dataset = Path(dataset)
    tx = pd.read_csv(dataset / "transactions.csv", dtype=str, keep_default_na=False,
                     usecols=["transaction_id", "company_id", "posted_at", "txn_type", "vendor_id", "employee_id",
                              "creator_id", "approver_id", "amount_vnd", "invoice_number", "unit_price_vnd", "support_doc_count"])
    emp = pd.read_csv(dataset / "employees.csv", dtype=str, keep_default_na=False,
                      usecols=["employee_id", "self_approval_limit_vnd"]).set_index("employee_id")["self_approval_limit_vnd"].astype(float)
    tx["t"] = _ts(tx["posted_at"])
    tx["amount"] = tx["amount_vnd"].astype(float)
    tx = tx.sort_values(["t", "transaction_id"], kind="stable").reset_index(drop=True)

    vendor_hist, payroll_hist, cu_hist = defaultdict(Welford), defaultdict(Welford), defaultdict(Welford)
    price_hist = defaultdict(list)       # (c,v) -> log unit prices
    payroll_recent = defaultdict(lambda: deque(maxlen=12))
    vendor_last, vendor_amounts = {}, defaultdict(list)
    near_dup = defaultdict(deque)
    creator_events = defaultdict(deque)      # (c,u) -> (t, approver, self_flag)
    cash_events = defaultdict(deque)         # (c,u) -> (t, ratio)
    unsupported = defaultdict(deque)         # (c,u) -> t of self-approved cash expenses with <=1 supporting document
    company_vendor_events = defaultdict(deque)  # c -> (t, vendor)
    vendor_count_90 = defaultdict(lambda: defaultdict(int))
    out = {name: np.zeros(len(tx)) for name in ENGINEERED}

    for i, r in enumerate(tx.itertuples(index=False)):
        c, v, e, u, a, kind = r.company_id, r.vendor_id, r.employee_id, r.creator_id, r.approver_id, r.txn_type
        t, x = r.t, r.amount
        ts = t.timestamp()
        lx = math.log1p(x)
        if kind in VENDOR_KINDS and v:
            h = vendor_hist[(c, v)]
            out["v_n"][i] = h.n
            if h.n >= 3:
                out["v_logz"][i] = (lx - h.mean) / max(.12, h.std())
            if h.n >= 2:
                out["v_logratio"][i] = lx - h.mean
            last = vendor_last.get((c, v))
            out["v_days_since_last"][i] = min(730.0, (ts - last) / DAY) if last else 730.0
            amts = vendor_amounts[(c, v)]
            if amts:
                out["v_nearest_amount_gap"][i] = min(abs(x - y) / max(x, 1.0) for y in amts[-30:])
            dq = near_dup[(c, v)]
            while dq and ts - dq[0][0] > 30 * DAY:
                dq.popleft()
            out["near_dup_30d"][i] = sum(abs(x - y) / x <= .03 for _, y, _ in dq)
            out["near_dup_other_invoice_30d"][i] = sum(abs(x - y) / x <= .03 and inv != r.invoice_number for _, y, inv in dq)
            cv = company_vendor_events[c]
            while cv and ts - cv[0][0] > 90 * DAY:
                _, old = cv.popleft()
                vendor_count_90[c][old] -= 1
            total = len(cv)
            out["vendor_share_90d"][i] = vendor_count_90[c][v] / total if total else 0.0
        out["is_bonus_season"][i] = float(t.month in (12, 1))
        if kind == "payroll" and e:
            recent = payroll_recent[(c, e)]
            out["p_n"][i] = len(recent)
            if len(recent) >= 2:
                out["p_logratio"][i] = lx - float(np.median(recent))
        if kind in VENDOR_KINDS and v and r.unit_price_vnd:
            lp = math.log(float(r.unit_price_vnd))
            hist = price_hist[(c, v)]
            out["price_n"][i] = len(hist)
            if len(hist) >= 3:
                med = float(np.median(hist[-20:]))
                out["price_logratio"][i] = lp - med
                sd = float(np.std(hist[-20:])) if len(hist) > 3 else .05
                out["price_logz"][i] = (lp - med) / max(.02, sd)
            if len(hist) >= 6:
                older = float(np.median(hist[-20:-2]))
                out["price_shift3"][i] = (lp + hist[-1] + hist[-2]) / 3 - older
        cu = cu_hist[(c, u, kind)]
        out["cu_n"][i] = cu.n
        if cu.n >= 5:
            out["cu_logratio"][i] = lx - cu.mean
        ev = creator_events[(c, u)]
        while ev and ts - ev[0][0] > 90 * DAY:
            ev.popleft()
        n_ev = len(ev)
        pair = sum(1 for _, ap, _ in ev if ap == a)
        out["creator_n_90d"][i] = n_ev
        out["pair_count_90d"][i] = pair
        out["pair_share_90d"][i] = pair / n_ev if n_ev else 0.0
        out["creator_distinct_approvers_90d"][i] = len({ap for _, ap, _ in ev})
        out["pair_exclusive"][i] = float(n_ev >= 5 and pair == n_ev)
        out["creator_self_rate_90d"][i] = sum(s for _, _, s in ev) / n_ev if n_ev else 0.0
        limit = emp.get(u, 2_000_000.0) or 2_000_000.0
        ratio = x / limit
        out["amount_selflimit_ratio"][i] = ratio
        ce = cash_events[(c, u)]
        while ce and ts - ce[0][0] > 30 * DAY:
            ce.popleft()
        out["creator_cash_30d"][i] = len(ce)
        out["creator_cash_near_selflimit_30d"][i] = sum(1 for _, q in ce if .6 <= q < 1.0)
        uq = unsupported[(c, u)]
        while uq and ts - uq[0] > 30 * DAY:
            uq.popleft()
        out["creator_unsupported_selfcash_30d"][i] = len(uq)
        out["dom"][i] = t.day
        out["is_month_end"][i] = float(t.day >= 26)
        out["is_pre_tet"][i] = float(any(0 < (tt - t.to_pydatetime()).days <= 21 for tt in TET))

        # ---- update after scoring this row
        if kind in VENDOR_KINDS and v:
            vendor_hist[(c, v)].add(lx)
            vendor_last[(c, v)] = ts
            vendor_amounts[(c, v)].append(x)
            near_dup[(c, v)].append((ts, x, r.invoice_number))
            company_vendor_events[c].append((ts, v))
            vendor_count_90[c][v] += 1
        if kind in VENDOR_KINDS and v and r.unit_price_vnd:
            price_hist[(c, v)].append(math.log(float(r.unit_price_vnd)))
        if kind == "payroll" and e:
            payroll_hist[(c, e)].add(lx)
            if t.month not in (12, 1):
                payroll_recent[(c, e)].append(lx)
        cu.add(lx)
        creator_events[(c, u)].append((ts, a, int(u == a)))
        if kind == "cash_expense":
            cash_events[(c, u)].append((ts, ratio))
            if u == a and int(r.support_doc_count) <= 1:
                unsupported[(c, u)].append(ts)
    frame = pd.DataFrame(out)
    frame.insert(0, "transaction_id", tx["transaction_id"].values)
    return frame
