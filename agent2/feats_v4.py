"""Past-only red-flag features for the records added in world v4 (receivables, payroll calendar, payees, write-offs).

Each feature is a documented audit red flag, defined on what an accountant could know at posting time:
  receipt_payer_mismatch      bank statement payer differs from the customer the receipt is applied to (lapping)
  receipt_days_late           days after the invoice due date at which the receipt is posted
  collector_late_trend_90d    mean lateness of receipts handled by the same collector in the last 90 days
  payee_not_on_master         vendor payment to an account not on the vendor master nor any observed bank change
  payroll_after_leave         payroll posted after the employee's recorded termination
  payroll_off_calendar        payroll posted outside the company's published pay days (+-3 days)
  payroll_rows_same_month     earlier payroll rows for the same employee in the same month
  writeoff_overdue_days       for bad-debt write-offs: age past due of the customer's oldest open invoice (0 = nothing overdue)
  refund_to_foreign_account   refund paid to an account that is not the customer's
  return_vs_recent_sales      return amount / customer's invoices in the last 60 days
  writeoff_vs_cogs_90d        inventory write-off / company cost of goods sold in the last 90 days
  creator_writeoffs_90d       inventory write-offs by the same creator in the last 90 days
  offquarter_writeoff         inventory write-off not on a quarter-end count date
  customer_amount_logz        sales invoice size vs the customer's own history
  self_approved_advance_ratio advance self-approved by its own recipient, amount / approval limit
"""
from __future__ import annotations

import math
from collections import defaultdict, deque
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

V4_FEATURES = ["receipt_payer_mismatch", "receipt_days_late", "collector_late_trend_90d", "payee_not_on_master", "payroll_after_leave",
               "payroll_off_calendar", "payroll_rows_same_month", "writeoff_overdue_days", "refund_to_foreign_account",
               "return_vs_recent_sales", "writeoff_vs_cogs_90d", "creator_writeoffs_90d", "offquarter_writeoff",
               "customer_amount_logz", "self_approved_advance_ratio"]
DAY = 86400.0


def is_v4(dataset: Path) -> bool:
    return (Path(dataset) / "truth_cases.csv").exists()


def v4_features(dataset: Path) -> pd.DataFrame:
    dataset = Path(dataset)
    tx = pd.read_csv(dataset / "transactions.csv", dtype=str, keep_default_na=False)
    emp = pd.read_csv(dataset / "employees.csv", dtype=str, keep_default_na=False).set_index("employee_id")
    ven = pd.read_csv(dataset / "vendors.csv", dtype=str, keep_default_na=False).set_index("vendor_id")
    cus = pd.read_csv(dataset / "customers.csv", dtype=str, keep_default_na=False).set_index("customer_id")
    comp = pd.read_csv(dataset / "companies.csv", dtype=str, keep_default_na=False).set_index("company_id")
    bank = pd.read_csv(dataset / "bank_account_changes.csv", dtype=str, keep_default_na=False)
    tx["t"] = pd.to_datetime(tx["posted_at"], utc=True).dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None)
    tx = tx.sort_values(["t", "transaction_id"], kind="stable").reset_index(drop=True)
    bank["t"] = pd.to_datetime(bank["observed_at"], utc=True).dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None)
    changes = defaultdict(list)
    for r in bank.itertuples(index=False):
        changes[r.vendor_id].append((r.t, r.new_account))
    pay_days = {c: [x for x in str(v).split("|") if x] for c, v in comp["pay_days"].items()}
    terms = comp["customer_terms_days"].astype(int).to_dict()
    term_rec = {e: pd.Timestamp(v[:19]) for e, v in emp["termination_recorded_at"].items() if v}

    out = {k: np.zeros(len(tx)) for k in V4_FEATURES}
    inv_info = {}                                       # invoice -> (customer, issued time, gross)
    open_inv = defaultdict(dict)                        # customer -> {invoice: issued time} (unpaid as known)
    collector_late = defaultdict(deque)
    cust_sales = defaultdict(deque)                     # customer -> (t, gross)
    cust_hist = defaultdict(lambda: [0, 0.0, 0.0])
    cogs = defaultdict(deque)
    creator_wo = defaultdict(deque)
    payroll_month = defaultdict(int)

    for i, r in enumerate(tx.itertuples(index=False)):
        t, kind, cid = r.t, r.txn_type, r.company_id
        amount = float(r.amount_vnd)
        if kind == "customer_receipt":
            known = cus.at[r.customer_id, "bank_account"] if r.customer_id in cus.index else ""
            out["receipt_payer_mismatch"][i] = float(bool(r.payer_account) and r.payer_account != known)
            if r.applied_invoice_id in inv_info:
                _, issued, _ = inv_info[r.applied_invoice_id]
                late = (t - issued).days - terms.get(cid, 30)
                out["receipt_days_late"][i] = late
                dq = collector_late[r.collector_id]
                while dq and (t - dq[0][0]).days > 90:
                    dq.popleft()
                out["collector_late_trend_90d"][i] = np.mean([x for _, x in dq]) if dq else 0.0
        elif kind == "vendor_payment" and r.vendor_id:
            known = {ven.at[r.vendor_id, "bank_account"]} if r.vendor_id in ven.index else set()
            known |= {acct for ct, acct in changes.get(r.vendor_id, []) if ct <= t}
            out["payee_not_on_master"][i] = float(bool(r.recipient_account) and r.recipient_account not in known)
        elif kind == "payroll" and r.employee_id:
            rec = term_rec.get(r.employee_id)
            out["payroll_after_leave"][i] = float(rec is not None and rec <= t)
            days = []
            for d in pay_days.get(cid, []):
                days.append(pd.Timestamp(t.year, t.month, 1).days_in_month if d == "last" else int(d))
            out["payroll_off_calendar"][i] = float(bool(days) and min(abs(t.day - d) for d in days) > 3)
            out["payroll_rows_same_month"][i] = payroll_month[(r.employee_id, t.year, t.month)]
        elif kind == "bad_debt_writeoff":
            opens = open_inv.get(r.customer_id, {})
            ages = [(t - issued).days - terms.get(cid, 30) for issued in opens.values()]
            out["writeoff_overdue_days"][i] = max(ages) if ages else 0.0
        elif kind == "customer_refund":
            known = cus.at[r.customer_id, "bank_account"] if r.customer_id in cus.index else ""
            out["refund_to_foreign_account"][i] = float(bool(r.recipient_account) and r.recipient_account != known)
        elif kind == "sales_return":
            dq = cust_sales[r.customer_id]
            recent = sum(g for st, g in dq if (t - st).days <= 60)
            out["return_vs_recent_sales"][i] = amount / recent if recent else 10.0
        elif kind == "inventory_writeoff":
            dq = cogs[cid]
            while dq and (t - dq[0][0]).days > 90:
                dq.popleft()
            total = sum(x for _, x in dq)
            out["writeoff_vs_cogs_90d"][i] = amount / total if total else 1.0
            cw = creator_wo[(cid, r.creator_id)]
            while cw and (t - cw[0]).days > 90:
                cw.popleft()
            out["creator_writeoffs_90d"][i] = len(cw)
            out["offquarter_writeoff"][i] = float(not (t.month in (3, 6, 9, 12) and t.day >= 25))
        elif kind == "sales_invoice" and r.customer_id:
            h = cust_hist[r.customer_id]
            lx = math.log1p(amount)
            if h[0] >= 3:
                sd = math.sqrt(h[2] / (h[0] - 1)) if h[0] > 1 else .5
                out["customer_amount_logz"][i] = (lx - h[1]) / max(.2, sd)
        elif kind == "advance_issue" and r.creator_id == r.approver_id == r.employee_id and r.employee_id in emp.index:
            out["self_approved_advance_ratio"][i] = amount / max(1.0, float(emp.at[r.employee_id, "approval_limit_vnd"] or 1))

        # ---- update state after scoring
        if kind == "sales_invoice" and r.invoice_id:
            inv_info[r.invoice_id] = (r.customer_id, t, amount)
            open_inv[r.customer_id][r.invoice_id] = t
            cust_sales[r.customer_id].append((t, amount))
            h = cust_hist[r.customer_id]
            lx = math.log1p(amount)
            h[0] += 1
            d = lx - h[1]
            h[1] += d / h[0]
            h[2] += d * (lx - h[1])
        if kind == "customer_receipt" and r.applied_invoice_id in inv_info:
            owner = inv_info[r.applied_invoice_id][0]
            open_inv[owner].pop(r.applied_invoice_id, None)
            if r.collector_id:
                collector_late[r.collector_id].append((t, out["receipt_days_late"][i]))
        if kind in ("bad_debt_writeoff", "sales_return") and r.applied_invoice_id:
            open_inv[r.customer_id].pop(r.applied_invoice_id, None)
        if kind == "cogs":
            cogs[cid].append((t, amount))
        if kind == "inventory_writeoff":
            creator_wo[(cid, r.creator_id)].append(t)
        if kind == "payroll" and r.employee_id:
            payroll_month[(r.employee_id, t.year, t.month)] += 1
    frame = pd.DataFrame(out)
    frame.insert(0, "transaction_id", tx["transaction_id"].values)
    return frame
