"""Measure forecast cash against reconciled bank truth without silently changing scope."""
from datetime import date, timedelta

import numpy as np

from agent1.adaptive.cash_history import evaluate_plan
from agent1.adaptive.data import as_of

HORIZON = 13


def knowledge_snapshot(data, cutoff):
    """Resolve versions and physically remove future flat rows for the leak check."""
    selected = as_of(data, cutoff)
    result = {}
    for key, value in selected.items():
        if isinstance(value, list):
            result[key] = [r for r in value if r.get("known_at", "0001-01-01") <= cutoff]
        elif key == "record_history":
            result[key] = {kind: [r for r in history if r["known_at"] <= cutoff]
                           for kind, history in value.items()}
        else:
            result[key] = value
    return result


def measure(data, plan, truth_asof, accounts):
    outcomes = evaluate_plan(data, plan, truth_asof, accounts)
    if len(outcomes) != HORIZON or not all(r["covered"] and r["balance_available"] for r in outcomes):
        raise ValueError("Need reconciled coverage for all thirteen outcome weeks")
    if plan.get("new_credit_included") or any(w.get("new_credit_in", 0) for w in plan["weeks"]):
        raise ValueError("New-invoice forecasting is excluded from this study")
    cutoff = plan["cutoff"]
    start = date.fromisoformat(cutoff)
    opened = {r["invoice_id"] for r in plan["cash_decomposition"]["invoices"]}
    invoices = {r["invoice_id"]: r for r in data["invoices"]}
    bank = {r["bank_id"]: r for r in data["bank"]
            if r["account"] in accounts and r["known_at"] <= truth_asof}
    amounts = {k: np.zeros(HORIZON) for k in (
        "opening_ar", "new_invoice", "cash_sale", "variable", "scheduled", "other_in", "other_out")}

    def index(day):
        n = (date.fromisoformat(day) - start).days
        return (n - 1) // 7 if 1 <= n <= HORIZON * 7 else None

    allocated = {}
    for r in data.get("payments", []):
        txn = bank.get(r.get("bank_id"))
        if r["known_at"] > truth_asof or txn is None or index(txn["date"]) is None:
            continue
        if txn["direction"] != "in" or r["payment_date"] != txn["date"]:
            raise ValueError("Invalid receipt/bank allocation")
        kind = ("opening_ar" if r["invoice_id"] in opened else
                "new_invoice" if invoices[r["invoice_id"]]["issue_date"] > cutoff else "other_in")
        amounts[kind][index(txn["date"])] += r["amount"]
        allocated[txn["bank_id"]] = allocated.get(txn["bank_id"], 0) + r["amount"]
    expenses = {r["expense_id"]: r for r in data.get("outflows", [])}
    for r in data.get("expense_payments", []):
        txn = bank.get(r.get("bank_id"))
        if r["known_at"] > truth_asof or txn is None or index(txn["date"]) is None:
            continue
        if txn["direction"] != "out" or r["payment_date"] != txn["date"]:
            raise ValueError("Invalid expense/bank allocation")
        kind = "variable" if expenses[r["expense_id"]]["category"] == "variable_cost" else "scheduled"
        amounts[kind][index(txn["date"])] += r["amount"]
        allocated[txn["bank_id"]] = allocated.get(txn["bank_id"], 0) + r["amount"]
    for txn in bank.values():
        i = index(txn["date"])
        if i is None:
            continue
        remaining = txn["amount"] - allocated.get(txn["bank_id"], 0)
        if remaining < 0:
            raise ValueError("Allocations exceed bank cash")
        kind = ("cash_sale" if txn.get("component") == "cash_sale" else
                "variable" if txn.get("component") == "variable_cost" else
                "other_in" if txn["direction"] == "in" else "other_out")
        amounts[kind][i] += remaining
    known_variable = np.zeros(HORIZON)
    for r in plan["cash_decomposition"]["outflows"]:
        if r["category"] == "variable_cost":
            known_variable[r["week"] - 1] += r["amount"]
    rows = []
    cumulative = dict(ar=0., sale=0., variable=0., scheduled=0., scope=0., obligation=0.)
    for i, (w, actual, parts) in enumerate(zip(plan["weeks"], outcomes, plan["cash_decomposition"]["weeks"])):
        ain = sum(amounts[k][i] for k in ("opening_ar", "new_invoice", "cash_sale", "other_in"))
        aout = sum(amounts[k][i] for k in ("variable", "scheduled", "other_out"))
        if not np.allclose([ain, aout], [actual["actual_in"], actual["actual_out"]], rtol=0, atol=.01):
            raise ValueError("Bank components do not sum to observed cash")
        pvar = parts["variable_cost_topup"] + known_variable[i]
        pscheduled = parts["scheduled_out"] - known_variable[i]
        errors = dict(ar=parts["ar_in"] - amounts["opening_ar"][i],
                      sale=parts["cash_sale_in"] - amounts["cash_sale"][i],
                      variable=amounts["variable"][i] - pvar,
                      scheduled=amounts["scheduled"][i] - pscheduled,
                      scope=amounts["other_out"][i] - amounts["new_invoice"][i] - amounts["other_in"][i],
                      obligation=parts["obligation_in"])
        for k, v in errors.items():
            cumulative[k] += v
        error = w["balance"] - actual["actual_balance"]
        if not np.isclose(error, sum(cumulative.values()), rtol=0, atol=.01):
            raise ValueError("Balance error bridge does not reconcile")
        row = dict(cutoff=cutoff, week=i+1, date=w["date"], opening_balance=plan["opening_balance"],
                   predicted_balance=w["balance"], actual_balance=actual["actual_balance"],
                   p10=w["low"], p90=w["high"], cash_floor=plan["cash_floor"],
                   below_floor_probability=w["below_floor_probability"],
                   alert=actual["alert"], shortfall=actual["shortfall"],
                   predicted_in=w["cash_in"], actual_in=ain, predicted_out=w["cash_out"], actual_out=aout,
                   predicted_ar_in=parts["ar_in"], actual_ar_in=float(amounts["opening_ar"][i]),
                   actual_cumulative_ar_in=float(amounts["opening_ar"][:i+1].sum()),
                   predicted_cash_sale_in=parts["cash_sale_in"], actual_cash_sale_in=float(amounts["cash_sale"][i]),
                   predicted_variable_out=pvar, actual_variable_out=float(amounts["variable"][i]),
                   predicted_scheduled_out=pscheduled, actual_scheduled_out=float(amounts["scheduled"][i]),
                   actual_excluded_new_invoice_in=float(amounts["new_invoice"][i]),
                   actual_other_in=float(amounts["other_in"][i]), actual_other_out=float(amounts["other_out"][i]),
                   cumulative_ar_error=cumulative["ar"], balance_error=error,
                   cumulative_scope_effect=cumulative["scope"],
                   error_bridge_residual=error-sum(cumulative.values()), outflow_status=w["outflow_status"])
        row.update({"cumulative_"+k+"_effect": v for k, v in cumulative.items() if k not in ("ar", "scope")})
        rows.append(row)
    return rows


def score(rows):
    if not rows:
        raise ValueError("No measured weeks")
    y, p, lo, hi, prob = (np.asarray([r[k] for r in rows], float) for k in
                          ("actual_balance", "predicted_balance", "p10", "p90", "below_floor_probability"))
    if not np.isfinite(np.r_[y, p, lo, hi, prob]).all() or np.any(lo > hi) or np.any((prob < 0) | (prob > 1)):
        raise ValueError("Invalid forecast interval or probability")
    actual = np.asarray([r["shortfall"] for r in rows], bool)
    alert = np.asarray([r["alert"] for r in rows], bool)
    hits = int((actual & alert).sum())
    return dict(weeks=len(rows), mae_balance_vnd=float(abs(p-y).mean()), bias_balance_vnd=float((p-y).mean()),
                coverage80=float(((lo <= y) & (y <= hi)).mean()), mean_width80_vnd=float((hi-lo).mean()),
                interval_score80_vnd=float((hi-lo+10*np.maximum(lo-y, 0)+10*np.maximum(y-hi, 0)).mean()),
                brier_weekly_shortfall=float(((prob-actual)**2).mean()),
                actual_shortfall_weeks=int(actual.sum()), alert_weeks=int(alert.sum()), true_alert_weeks=hits,
                false_alert_weeks=int((alert & ~actual).sum()), missed_shortfall_weeks=int((~alert & actual).sum()),
                recall_weekly=hits/int(actual.sum()) if actual.any() else None,
                precision_weekly=hits/int(alert.sum()) if alert.any() else None,
                mae_weekly_in_vnd=float(np.mean([abs(r["predicted_in"]-r["actual_in"]) for r in rows])),
                mae_weekly_out_vnd=float(np.mean([abs(r["predicted_out"]-r["actual_out"]) for r in rows])),
                mae_weekly_ar_vnd=float(np.mean([abs(r["predicted_ar_in"]-r["actual_ar_in"]) for r in rows])),
                mae_cumulative_ar_vnd=float(np.mean([abs(r["cumulative_ar_error"]) for r in rows])))


def ar_score(rows):
    """AR-only plans have no other movements; their bands measure cumulative receipts."""
    measured = []
    for r in rows:
        item = dict(r, actual_balance=r["actual_cumulative_ar_in"], predicted_balance=r["predicted_balance"]-r["opening_balance"],
                    p10=r["p10"]-r["opening_balance"], p90=r["p90"]-r["opening_balance"], shortfall=False, alert=False)
        measured.append(item)
    result = score(measured)
    return {k: v for k, v in result.items() if k not in (
        "actual_shortfall_weeks", "alert_weeks", "true_alert_weeks", "false_alert_weeks", "missed_shortfall_weeks",
        "recall_weekly", "precision_weekly", "brier_weekly_shortfall", "mae_weekly_in_vnd", "mae_weekly_out_vnd")}


def event_score(rows):
    """Horizon-level alert decisions, without inventing a joint probability from marginals."""
    grouped = {}
    for r in rows:
        grouped.setdefault((r["dataset"], r["profile"], r["cutoff"]), []).append(r)
    truth = [any(r["shortfall"] for r in group) for group in grouped.values()]
    alerts = [any(r["alert"] for r in group) for group in grouped.values()]
    hits = sum(a and b for a, b in zip(truth, alerts))
    return dict(contexts=len(grouped), actual_shortfall_contexts=sum(truth), alert_contexts=sum(alerts),
                false_alert_contexts=sum(b and not a for a, b in zip(truth, alerts)),
                missed_shortfall_contexts=sum(a and not b for a, b in zip(truth, alerts)),
                recall_context=hits/sum(truth) if any(truth) else None,
                precision_context=hits/sum(alerts) if any(alerts) else None)
