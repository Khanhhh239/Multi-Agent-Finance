"""Receipts from credit invoices not yet issued; keep them separate from opening AR and cash sales."""

from datetime import date, timedelta
import numpy as np
from .cash_history import weekly_cash
from .data import effective_data


def build(data, clock, accounts):
    data = effective_data(data, clock)
    data["invoices"] = [dict(r, issue_date=r.get("origin_issue_date", r["issue_date"])) for r in data["invoices"]]
    end = date.fromisoformat(clock)
    # Cash labels must be traceable to the same verified bank scope.
    bank = {
        r["bank_id"]: r
        for r in data.get("bank", [])
        if r["account"] in accounts and r["known_at"] <= clock
    }
    inv = {
        r["invoice_id"]: r
        for r in data["invoices"]
        if r["known_at"] <= clock and r["issue_date"] <= clock
    }
    hist = weekly_cash(
        data, str(end - timedelta(weeks=52) + timedelta(days=1)), 52, clock, accounts
    )
    if not np.isfinite(hist).all():
        return None
    eligible = {
        k: r
        for k, r in inv.items()
        if 91 <= (end - date.fromisoformat(r["issue_date"])).days < 364
        and r["known_at"] == r["issue_date"]
    }
    if len(eligible) < 50:
        return None
    total = sum(r["amount"] for r in eligible.values())
    kernel = np.zeros(13)
    linked = 0
    for p in data.get("payments", []):
        if p["invoice_id"] not in eligible or p["known_at"] > clock:
            continue
        if p.get("bank_id") not in bank:
            return None
        age = (
            date.fromisoformat(p["payment_date"])
            - date.fromisoformat(eligible[p["invoice_id"]]["issue_date"])
        ).days
        if 0 <= age < 91:
            kernel[age // 7] += p["amount"] / total
            linked += 1
    if linked < 20:
        return None
    issuance = np.zeros(52)
    for r in inv.values():
        days = (end - date.fromisoformat(r["issue_date"])).days
        if 0 <= days < 364:
            issuance[51 - days // 7] += r["amount"]
    return dict(kernel=kernel, issuance=issuance)


def point(model, kind):
    sales = (
        model["issuance"][:13]
        if kind == "seasonal"
        else np.full(13, model["issuance"][-8:].mean())
    )
    return np.convolve(sales, model["kernel"])[:13]


def receipts(data, origin, end, accounts):
    data = effective_data(data, end)
    # Excludes all opening invoices even if settled after origin.
    start = date.fromisoformat(origin) + timedelta(days=1)
    if not np.isfinite(weekly_cash(data, str(start), 13, end, accounts)).all():
        return None
    inv = {
        r["invoice_id"]
        for r in data["invoices"]
        if r.get("origin_issue_date", r["issue_date"]) > origin and r["known_at"] <= end
    }
    bank = {
        r["bank_id"]
        for r in data.get("bank", [])
        if r["account"] in accounts and r["known_at"] <= end
    }
    y = np.zeros(13)
    for p in data.get("payments", []):
        if p["invoice_id"] not in inv or p["known_at"] > end:
            continue
        day = (date.fromisoformat(p["payment_date"]) - start).days
        if 0 <= day < 91:
            if p.get("bank_id") not in bank:
                return None
            y[day // 7] += p["amount"]
    return y


def select_credit(data, asof, accounts):
    final = build(data, asof, accounts)
    if final is None:
        return None
    end = date.fromisoformat(asof)
    audit = str(end - timedelta(weeks=13))
    errors = {k: [] for k in ("seasonal", "recent")}
    for delta in (52, 39, 26, 13):
        origin = str(end - timedelta(weeks=delta))
        model = build(data, origin, accounts)
        y = receipts(data, origin, asof if delta == 13 else audit, accounts)
        if model is None or y is None:
            return None
        if delta != 13:
            for k in errors:
                errors[k].append(y - point(model, k))
        else:
            k = min(errors, key=lambda n: np.abs(errors[n]).mean())
            err = float(np.abs(y - point(model, k)).mean())
            zero = float(np.abs(y).mean())
            if err >= zero:
                return None
            return dict(
                kind=k,
                validation_mae=float(np.abs(errors[k]).mean()),
                audit_mae=err,
                zero_mae=zero,
                residuals=np.array(errors[k]),
            )
