"""Change detection per entity, two-sided deviations, group shifts and receivable state (v5 R2).

Every feature is computed in ONE chronological pass over a world's transactions. A row only sees rows
posted strictly earlier; rows sharing a timestamp are scored first and absorbed afterwards (same rule as
`feats.py`). Nothing reads labels, scheme names or splits. All values are dữ liệu tổng hợp when run on
the synthetic worlds.

Mechanisms (generic audit red flags, not tied to any scenario):
  payroll      level change of one employee's pay vs that employee's own recent pay (robust median),
               two-sided CUSUM, short-vs-long level shift; group shift = how many people paid by the
               same preparer recently moved up at once
  vendor price unit price vs the vendor's own recent prices, two-sided CUSUM, trend slope of the last six
  customer     invoice amount vs that customer's own history in robust z units, two-sided CUSUM (a large
               discount is as suspicious as an inflated invoice)
  receivables  overdue open invoices of the customer and of the same salesperson; share of a creator's
               recent invoices later reversed; age and payment state of the invoice a reversal closes
  recurring    payments of a recurring kind (cash withdrawal, tax, rent) more frequent than the company's
               own monthly rhythm, amount vs the kind's median, new counterparty for a recurring kind
  advances     advances issued to an employee while earlier ones are still open, growth vs the last one

`EntityDeviation2` turns these into label-free tail scores (left, right or both sides, reference = the
world's training period) and the maximum over detectors.
"""
from __future__ import annotations

import math
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd

CD_FEATURES = [
    "pay_lr", "pay_cusum_up", "pay_cusum_dn", "pay_shift", "grp_pay_up_share", "grp_pay_up_n",
    "price_lr2", "price_cusum_up", "price_cusum_dn", "price_slope6",
    "cust_z", "cust_cusum_up", "cust_cusum_dn",
    "ar_cust_overdue_n", "ar_mgr_overdue_share", "ar_creator_reversal_share", "ar_reversal_age_days",
    "ar_reversal_unpaid",
    "rec_excess", "rec_amount_lr", "rec_new_counterparty",
    "adv_open_n", "adv_growth",
]
PAY_K, PRICE_K, CUST_K = .03, .02, .5          # CUSUM allowances: log units, log units, robust z units
HIST = 6                                       # own-history window (rows) for the robust reference
RECURRING = ("cash_withdrawal", "tax_payment", "rent")
REVERSALS = ("sales_return", "bad_debt_writeoff")
DAY = 86400.0


def _median(values):
    return float(np.median(values)) if values else math.nan


def _mad(values, med):
    return float(np.median(np.abs(np.asarray(values) - med))) * 1.4826 if len(values) >= 3 else math.nan


def _slope(values):
    if len(values) < 3:
        return 0.0
    x = np.arange(len(values), dtype=float)
    x -= x.mean()
    return float((x * (np.asarray(values) - np.mean(values))).sum() / (x * x).sum())


class _Cusum:
    __slots__ = ("up", "dn")

    def __init__(self):
        self.up = self.dn = 0.0

    def step(self, d, k):
        self.up = max(0.0, self.up + d - k)
        self.dn = max(0.0, self.dn - d - k)


def change_features(dataset: Path | str) -> pd.DataFrame:
    """One causal pass; returns `transaction_id` plus CD_FEATURES (float32)."""
    dataset = Path(dataset)
    cols = ["transaction_id", "company_id", "posted_at", "txn_type", "amount_vnd", "unit_price_vnd", "vendor_id",
            "customer_id", "employee_id", "creator_id", "invoice_id", "applied_invoice_id", "collector_id",
            "advance_id"]
    tx = pd.read_csv(dataset / "transactions.csv", dtype=str, keep_default_na=False, usecols=cols)
    terms = pd.read_csv(dataset / "companies.csv", dtype=str, keep_default_na=False).set_index("company_id")[
        "customer_terms_days"].astype(float).to_dict()
    # Seconds since epoch, independent of the datetime storage unit (pandas 3 parses to ms, not ns).
    t = ((pd.to_datetime(tx["posted_at"], utc=True) - pd.Timestamp("1970-01-01", tz="UTC"))
         / pd.Timedelta(seconds=1)).to_numpy(dtype=float)
    order = np.lexsort((tx["transaction_id"].to_numpy(), t))
    n = len(tx)
    out = {k: np.zeros(n, dtype=np.float64) for k in CD_FEATURES}

    # state
    pay_hist, pay_cusum, pay_recent = defaultdict(lambda: deque(maxlen=12)), defaultdict(_Cusum), defaultdict(deque)
    pay_month = defaultdict(int)                    # (company, employee, YYYY-MM) -> payroll rows already posted
    price_hist, price_cusum = defaultdict(lambda: deque(maxlen=HIST)), defaultdict(_Cusum)
    cust_hist, cust_cusum = defaultdict(lambda: deque(maxlen=24)), defaultdict(_Cusum)
    invoices = {}                                   # invoice -> [company, customer, creator, issued, gross, paid]
    open_by_customer = defaultdict(set)
    open_by_creator = defaultdict(set)
    creator_invoices = defaultdict(deque)           # (company, creator) -> deque[(t, invoice)]
    reversed_invoices = set()
    rec_times, rec_amounts, rec_parties, rec_first = defaultdict(deque), defaultdict(lambda: deque(maxlen=12)), defaultdict(set), {}
    adv_open, adv_last = defaultdict(dict), {}

    cols_np = {c: tx[c].to_numpy() for c in cols}
    amount = pd.to_numeric(tx["amount_vnd"], errors="coerce").fillna(0).to_numpy()
    price = pd.to_numeric(tx["unit_price_vnd"], errors="coerce").to_numpy()
    pending = []                                    # updates applied when the timestamp changes

    def flush():
        for fn in pending:
            fn()
        pending.clear()

    last_t = None
    for i in order:
        ti = t[i]
        if last_t is not None and ti != last_t:
            flush()
        last_t = ti
        cid, kind = cols_np["company_id"][i], cols_np["txn_type"][i]
        a = amount[i]

        # ---------------- payroll level and CUSUM, group shift
        emp = cols_np["employee_id"][i]
        month = (cid, emp, cols_np["posted_at"][i][:7])
        first_of_month = kind == "payroll" and emp and pay_month[month] == 0
        if kind == "payroll" and emp:
            pending.append(lambda month=month: pay_month.__setitem__(month, pay_month[month] + 1))
        if first_of_month and a > 0:
            # Only the first pay row of an employee's month is compared with earlier first rows; bonuses and
            # extra runs are later rows of the month, so they neither score here nor pollute the reference.
            key = (cid, emp)
            hist = pay_hist[key]
            x = math.log(a)
            had = len(hist) >= 3
            if had:
                ref = _median(list(hist)[-HIST:])
                lr = x - ref
                out["pay_lr"][i] = lr
                c = pay_cusum[key]
                out["pay_cusum_up"][i] = max(0.0, c.up + lr - PAY_K)
                out["pay_cusum_dn"][i] = max(0.0, c.dn - lr - PAY_K)
                if len(hist) >= 6:
                    h = list(hist)
                    out["pay_shift"][i] = _median(h[-3:] + [x]) - _median(h[:-3])
            else:
                lr = 0.0
            creator = cols_np["creator_id"][i]
            grp = pay_recent[(cid, creator)]
            while grp and ti - grp[0][0] > 35 * DAY:
                grp.popleft()
            movers = {e for (_, e, up) in grp if up}
            out["grp_pay_up_n"][i] = len(movers)
            people = {e for (_, e, _) in grp}
            out["grp_pay_up_share"][i] = len(movers) / len(people) if people else 0.0

            def upd(key=key, x=x, lr=lr, hist=hist, creator=creator, emp=emp, ti=ti, cid=cid, had=had):
                if had:
                    pay_cusum[key].step(lr, PAY_K)
                hist.append(x)
                pay_recent[(cid, creator)].append((ti, emp, lr > .05))
            pending.append(upd)

        # ---------------- vendor unit price
        ven = cols_np["vendor_id"][i]
        p = price[i]
        if ven and p == p and p > 0:
            key = (cid, ven)
            hist = price_hist[key]
            x = math.log(p)
            had = len(hist) >= 3
            if had:
                lr = x - _median(list(hist))
                out["price_lr2"][i] = lr
                c = price_cusum[key]
                out["price_cusum_up"][i] = max(0.0, c.up + lr - PRICE_K)
                out["price_cusum_dn"][i] = max(0.0, c.dn - lr - PRICE_K)
                out["price_slope6"][i] = _slope(list(hist) + [x])
            else:
                lr = 0.0

            def upd(key=key, x=x, lr=lr, hist=hist, had=had):
                if had:
                    price_cusum[key].step(lr, PRICE_K)
                hist.append(x)
            pending.append(upd)

        # ---------------- customer invoices: robust z, CUSUM, receivable state at issue time
        cus = cols_np["customer_id"][i]
        if kind == "sales_invoice" and cus and a > 0:
            key = (cid, cus)
            hist = cust_hist[key]
            x = math.log(a)
            z = 0.0
            had = len(hist) >= 5
            if had:
                h = list(hist)
                med = _median(h)
                mad = _mad(h, med)
                z = (x - med) / max(mad, .1)
                out["cust_z"][i] = z
                c = cust_cusum[key]
                out["cust_cusum_up"][i] = max(0.0, c.up + z - CUST_K)
                out["cust_cusum_dn"][i] = max(0.0, c.dn - z - CUST_K)
            due = terms.get(cid, 30.0) * DAY
            out["ar_cust_overdue_n"][i] = sum(1 for inv in open_by_customer[key] if ti - invoices[inv][3] > due)
            creator = cols_np["creator_id"][i]
            mine = open_by_creator[(cid, creator)]
            out["ar_mgr_overdue_share"][i] = (sum(1 for inv in mine if ti - invoices[inv][3] > due) / len(mine)) if mine else 0.0
            recent = creator_invoices[(cid, creator)]
            while recent and ti - recent[0][0] > 180 * DAY:
                recent.popleft()
            out["ar_creator_reversal_share"][i] = (sum(1 for _, inv in recent if inv in reversed_invoices) / len(recent)) if recent else 0.0
            inv_id = cols_np["invoice_id"][i]

            def upd(key=key, x=x, z=z, hist=hist, inv_id=inv_id, cid=cid, cus=cus, creator=creator, ti=ti, a=a, had=had):
                if had:
                    cust_cusum[key].step(z, CUST_K)
                hist.append(x)
                if inv_id:
                    invoices[inv_id] = [cid, cus, creator, ti, a, False]
                    open_by_customer[(cid, cus)].add(inv_id)
                    open_by_creator[(cid, creator)].add(inv_id)
                    creator_invoices[(cid, creator)].append((ti, inv_id))
            pending.append(upd)

        applied = cols_np["applied_invoice_id"][i]
        if applied and applied in invoices:
            rec = invoices[applied]
            if kind in REVERSALS:
                out["ar_reversal_age_days"][i] = (ti - rec[3]) / DAY
                out["ar_reversal_unpaid"][i] = float(not rec[5])

            def upd(applied=applied, kind=kind):
                rec = invoices[applied]
                if kind == "customer_receipt":
                    rec[5] = True
                if kind in REVERSALS:
                    reversed_invoices.add(applied)
                open_by_customer[(rec[0], rec[1])].discard(applied)
                open_by_creator[(rec[0], rec[2])].discard(applied)
            pending.append(upd)

        # ---------------- recurring kinds
        if kind in RECURRING and a > 0:
            key = (cid, kind)
            times = rec_times[key]
            first = rec_first.get(key)
            if first is not None and ti - first > 120 * DAY:
                months = (ti - first) / (30.4 * DAY)
                past = [s for s in times if ti - s <= 180 * DAY]
                monthly = len(past) / min(6.0, months)
                last35 = sum(1 for s in times if ti - s <= 35 * DAY)
                out["rec_excess"][i] = last35 - monthly
            amts = rec_amounts[key]
            if len(amts) >= 3:
                out["rec_amount_lr"][i] = math.log(a) - _median(list(amts))
            party = cols_np["vendor_id"][i] or cols_np["employee_id"][i]
            out["rec_new_counterparty"][i] = float(bool(party) and len(rec_parties[key]) > 0 and party not in rec_parties[key])

            def upd(key=key, ti=ti, a=a, party=party):
                rec_first.setdefault(key, ti)
                rec_times[key].append(ti)
                while rec_times[key] and ti - rec_times[key][0] > 200 * DAY:
                    rec_times[key].popleft()
                rec_amounts[key].append(math.log(a))
                if party:
                    rec_parties[key].add(party)
            pending.append(upd)

        # ---------------- advances
        adv = cols_np["advance_id"][i]
        if kind == "advance_issue" and emp and a > 0:
            key = (cid, emp)
            out["adv_open_n"][i] = len(adv_open[key])
            prev = adv_last.get(key)
            out["adv_growth"][i] = math.log(a / prev) if prev else 0.0

            def upd(key=key, adv=adv, a=a):
                if adv:
                    adv_open[key][adv] = a
                adv_last[key] = a
            pending.append(upd)
        elif kind in ("advance_settlement", "advance_writeoff") and emp and adv:
            def upd(key=(cid, emp), adv=adv):
                adv_open[key].pop(adv, None)
            pending.append(upd)
    flush()
    frame = pd.DataFrame({k: v.astype(np.float32) for k, v in out.items()})
    frame.insert(0, "transaction_id", tx["transaction_id"].to_numpy())
    return frame


# ------------------------------------------------------------------------------------------------ label-free scores
# (feature, side, activity mask on the feature frame + txn_type). side: +1 right tail, -1 left tail.
ED2_SPECS = [
    ("pay_lr", +1, "payroll"), ("pay_lr", -1, "payroll"), ("pay_cusum_up", +1, "payroll"),
    ("pay_shift", +1, "payroll"), ("grp_pay_up_n", +1, "payroll"),
    ("price_lr2", +1, None), ("price_cusum_up", +1, None), ("price_slope6", +1, None),
    ("cust_z", +1, "sales_invoice"), ("cust_z", -1, "sales_invoice"), ("cust_cusum_dn", +1, "sales_invoice"),
    ("ar_cust_overdue_n", +1, "sales_invoice"), ("ar_mgr_overdue_share", +1, "sales_invoice"),
    ("ar_creator_reversal_share", +1, "sales_invoice"), ("ar_reversal_unpaid", +1, "reversal"),
    ("ar_reversal_age_days", -1, "reversal"),
    ("rec_excess", +1, "recurring"), ("rec_amount_lr", +1, "recurring"), ("rec_new_counterparty", +1, "recurring"),
    ("adv_open_n", +1, "advance_issue"), ("adv_growth", +1, "advance_issue"),
]
MIN_REFERENCE = 20


def _active(kind_values, spec_kind, feature_values):
    if spec_kind is None:
        return feature_values != 0
    if spec_kind == "reversal":
        return np.isin(kind_values, REVERSALS)
    if spec_kind == "recurring":
        return np.isin(kind_values, RECURRING)
    return kind_values == spec_kind


class EntityDeviation2:
    """Label-free, two-sided tails of the change features; reference = training period of the same world."""

    def fit(self, frame: pd.DataFrame, kinds: np.ndarray):
        self.ref = {}
        for feat, side, kind in ED2_SPECS:
            v = frame[feat].to_numpy(dtype=float)
            mask = _active(kinds, kind, v)
            r = np.sort(side * v[mask])
            if len(r) >= MIN_REFERENCE:
                self.ref[(feat, side)] = r
        return self

    def parts(self, frame: pd.DataFrame, kinds: np.ndarray) -> dict:
        out = {}
        for feat, side, kind in ED2_SPECS:
            ref = self.ref.get((feat, side))
            if ref is None:
                continue
            v = frame[feat].to_numpy(dtype=float)
            mask = _active(kinds, kind, v)
            x = side * v
            tail = (len(ref) - np.searchsorted(ref, x, side="left") + 1) / (len(ref) + 1)
            out[f"{feat}{'+' if side > 0 else '-'}"] = np.where(mask, -np.log(tail), 0.0)
        return out

    def score(self, frame: pd.DataFrame, kinds: np.ndarray) -> np.ndarray:
        p = self.parts(frame, kinds)
        return np.max(np.vstack(list(p.values())), axis=0) if p else np.zeros(len(frame))
