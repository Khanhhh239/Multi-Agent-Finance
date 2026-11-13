"""Observed cash and out-of-sample forecast errors, restricted to reconciled account periods."""

from datetime import date, timedelta
import numpy as np
import pandas as pd
from .data import as_of


def weekly_cash(data, start, weeks, asof, accounts):
    """One common scope for all weeks. Uncovered dates are missing rather than zero."""
    data = as_of(data, asof)
    periods = [r for r in data.get("statements", []) if r["known_at"] <= asof]
    dates = pd.date_range(start, periods=7 * weeks)
    covered = np.full(len(dates), bool(accounts))
    for account in accounts:
        mask = np.zeros(len(dates), bool)
        for r in periods:
            if r["account"] == account:
                mask |= (dates >= r["start_date"]) & (dates <= r["end_date"])
        covered &= mask
    flows = np.zeros((weeks, 4))
    for r in data.get("bank", []):
        if r["account"] not in accounts or r["known_at"] > asof:
            continue
        day = (date.fromisoformat(r["date"]) - dates[0].date()).days
        if not 0 <= day < 7 * weeks:
            continue
        i = day // 7
        flows[i, 0 if r["direction"] == "in" else 1] += r["amount"]
        if r.get("component") == "cash_sale":
            flows[i, 2] += r["amount"]
        if r.get("component") == "variable_cost":
            flows[i, 3] += r["amount"]
    flows[~covered.reshape(weeks, 7).all(1)] = np.nan
    return flows


def evaluate_plan(data, plan, asof, accounts):
    data = as_of(data, asof)
    flows = weekly_cash(
        data,
        str(date.fromisoformat(plan["cutoff"]) + timedelta(days=1)),
        len(plan["weeks"]),
        asof,
        accounts,
    )
    balance = plan["opening_balance"]
    rows = []
    for week, (cin, cout, *_) in zip(plan["weeks"], flows):
        balance += cin - cout
        # The actual balance comes from reconciled bank balances even if the
        # opening amount entered by the planner was incorrect.
        if np.isfinite(cin):
            end = week["date"]
            balance = 0.0
            for account in accounts:
                s = next(
                    r
                    for r in data["statements"]
                    if r["account"] == account
                    and r["start_date"] <= end <= r["end_date"]
                    and r["known_at"] <= asof
                )
                balance += s["opening_balance"] + sum(
                    (1 if r["direction"] == "in" else -1) * r["amount"]
                    for r in data.get("bank", [])
                    if r["account"] == account
                    and s["start_date"] <= r["date"] <= end
                    and r["known_at"] <= asof
                )
        ready = np.isfinite(balance)
        row = dict(
            week=week["week"],
            date=week["date"],
            covered=bool(np.isfinite(cin)),
            balance_available=bool(ready),
        )
        if row["covered"]:
            row.update(
                actual_in=cin,
                actual_out=cout,
                in_error=week["cash_in"] - cin,
                out_error=week["cash_out"] - cout,
            )
        if ready:
            err = balance - week["balance"]
            row.update(
                actual_balance=balance,
                balance_error=-err,
                abs_error=abs(err),
                interval_hit=bool(week["low"] <= balance <= week["high"]),
                interval_width=week["high"] - week["low"],
                shortfall=bool(balance < plan.get("cash_floor", 0)),
                alert=any(a["week"] == week["week"] for a in plan["alerts"]),
            )
            for q, field in ((0.1, "low"), (0.9, "high")):
                residual = balance - week[field]
                row[f"pinball_{field}"] = max(q * residual, (q - 1) * residual)
        rows.append(row)
    return rows


def calibrate_bands(plan, previous, data):
    """Past prospective base plans only; one non-overlapping origin per forecast horizon."""
    scores = []
    last = None
    for old in sorted(
        (p for p in previous if p), key=lambda p: p["cutoff"], reverse=True
    ):
        if len(old["weeks"]) != len(plan["weeks"]):
            continue
        end = date.fromisoformat(old["cutoff"]) + timedelta(weeks=len(old["weeks"]))
        if str(end) > plan["cutoff"] or (last and end > last):
            continue
        if (
            old["created_at"][:10] > old["cutoff"]
            or old.get("accounts") != plan["accounts"]
        ):
            continue
        if any(
            old.get(k) != plan.get(k)
            for k in (
                "model_version",
                "mode",
                "scenario",
                "operating_included",
                "new_credit_included",
                "confirmed_weeks",
                "band_protocol",
                "adapter_version",
                "partial_version",
                "t6_version",
            )
        ):
            continue
        rows = evaluate_plan(data, old, plan["cutoff"], plan["accounts"])
        if not all(r["balance_available"] for r in rows):
            continue
        scores.append(
            [
                max(
                    w.get("raw_low", w["low"]) - r["actual_balance"],
                    r["actual_balance"] - w.get("raw_high", w["high"]),
                    0.0,
                )
                for w, r in zip(old["weeks"], rows)
            ]
        )
        last = date.fromisoformat(old["cutoff"])
    n = len(scores)
    plan["calibration_origins"] = n
    plan["band_status"] = "insufficient_out_of_sample_errors"
    if n < 12:
        return
    delta = np.sort(scores, axis=0)[int(np.ceil((n + 1) * 0.8)) - 1]
    for w, extra in zip(plan["weeks"], delta):
        w.update(raw_low=w["low"], raw_high=w["high"])
        w["low"] -= float(extra)
        w["high"] += float(extra)
    plan["band_status"] = "calibrated_out_of_sample"
    plan["assumptions"].append(
        f"Dải số dư điều chỉnh bằng sai số tại {n} gốc lịch sử không chồng lấn; xác suất cảnh báo vẫn là mô phỏng."
    )
