"""Predeclared bank scenarios for a closed receivables book at each origin.

These are counterfactual synthetic stress fixtures, not additional independent
companies. Historical inputs are untouched; no future invoice is issued. Future
receipts on the opening book come from the existing demo's recorded outcomes.
Expense budgets use past cash only, never a forecast or future receipts.
"""
from copy import deepcopy
from datetime import date, timedelta
import hashlib

import numpy as np

from agent1.adaptive.data import as_of, validate_dataset
from scripts.business.backtest_t6_baseline import opening_balance
from .evaluation import knowledge_snapshot

PROFILES = {
    "buffered": dict(fixed_fraction=.12, bullet_weeks=0., variable_shock=1., missing_schedule=False),
    "payment_pressure": dict(fixed_fraction=.40, bullet_weeks=3., variable_shock=1., missing_schedule=False),
    "cost_shock": dict(fixed_fraction=.12, bullet_weeks=0., variable_shock=3., missing_schedule=False),
    "schedule_gap": dict(fixed_fraction=.40, bullet_weeks=3., variable_shock=1., missing_schedule=True),
}
SEED = 261113601


def make_stress(original, cutoff, profile, accounts):
    spec = PROFILES[profile]
    start = date.fromisoformat(cutoff)
    end = start+timedelta(weeks=13)
    data = deepcopy(knowledge_snapshot(original, cutoff))
    # Flat demo tables: no record-history mutation or inferred missing documents.
    if data.get("record_history") or len(accounts) != 1:
        raise ValueError("Stress fixture requires the flat, single-account demo")
    account = accounts[0]
    history = [r for r in data["bank"] if r["account"] == account and
               str(start-timedelta(weeks=13)) < r["date"] <= cutoff]
    ar_scale = max(1., sum(r["amount"] for r in history if r["direction"] == "in" and r.get("component") != "cash_sale")/13)
    sale_scale = max(1., sum(r["amount"] for r in history if r.get("component") == "cash_sale")/13)
    cost_scale = max(1., sum(r["amount"] for r in history if r.get("component") == "variable_cost")/13)
    # The RNG is fixed by origin, shared across stress profiles for matched noise.
    seed = SEED+int(hashlib.sha256(cutoff.encode()).hexdigest()[:6], 16)
    rng = np.random.default_rng(seed)
    ids = {r["invoice_id"] for r in data["invoices"]}
    future = [dict(r) for r in original["payments"] if r["invoice_id"] in ids and cutoff < r["payment_date"] <= str(end)]
    bank = {r["bank_id"]: r for r in original["bank"]}
    for r in future:
        data["payments"].append(r)
        data["bank"].append(dict(bank[r["bank_id"]]))
    data["actions"].extend(dict(r) for r in original["actions"]
                           if r["invoice_id"] in ids and cutoff < r["known_at"] <= str(end))
    data["expense_payments"] = []
    balance = opening_balance(data, cutoff, accounts)
    for week in range(1, 14):
        day = str(start+timedelta(weeks=week))
        sale = max(1, round(sale_scale*rng.lognormal(-.5*.10**2, .10)))
        cost = max(1, round(cost_scale*rng.lognormal(-.5*.12**2, .12)*
                            (spec["variable_shock"] if 5 <= week <= 9 else 1)))
        fixed = max(1, round(ar_scale*(spec["fixed_fraction"]+(spec["bullet_weeks"] if week == 4 else 0))))
        expense_id = f"ST-{profile}-{cutoff}-{week}"
        known = day if spec["missing_schedule"] and week % 2 == 0 else cutoff
        data["outflows"].append(dict(expense_id=expense_id, date=day, known_at=known,
                                     amount=fixed, category="supplier_contract"))
        for label, amount, direction, component in (("SALE", sale, "in", "cash_sale"),
                                                   ("VAR", cost, "out", "variable_cost"),
                                                   ("FIX", fixed, "out", "other")):
            bid = f"ST-{profile}-{cutoff}-{week}-{label}"
            data["bank"].append(dict(bank_id=bid, account=account, date=day, known_at=day,
                                     amount=amount, direction=direction, component=component))
            if label == "FIX":
                data["expense_payments"].append(dict(settlement_id="PAY-"+bid, expense_id=expense_id,
                    bank_id=bid, payment_date=day, known_at=day, amount=amount))
        lo = str(start+timedelta(weeks=week-1, days=1))
        movement = sum(r["amount"]*(1 if r["direction"] == "in" else -1) for r in data["bank"]
                       if r["account"] == account and lo <= r["date"] <= day)
        data["statements"].append(dict(statement_id=f"ST-{profile}-{cutoff}-{week}", account=account,
            start_date=lo, end_date=day, known_at=day, opening_balance=balance, closing_balance=balance+movement))
        balance += movement
    validate_dataset(data)
    return data, dict(synthetic=True, counterfactual=True, closed_book=True, profile=profile, seed=seed,
        past_weekly_ar_vnd=ar_scale, past_weekly_sale_vnd=sale_scale, past_weekly_variable_vnd=cost_scale,
        opening_balance=opening_balance(data, cutoff, accounts),
        confirmed_weeks=[] if spec["missing_schedule"] else list(range(1, 14)),
        design=spec, raw_bank_truth_modified=False,
        scope="Separate generated fixture; original demo is preserved; no future invoices issued.")
