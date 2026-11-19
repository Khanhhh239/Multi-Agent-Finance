"""As-of inputs and daily operating-bank accounting, with explicit fee bridge.

All future timestamps used by forecast code are generated from the calendar or
dated known_at records. Truth is a separate function and never enters context.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.special import ndtr

from agent1 import calendar_vn as calendar
from agent1.models import t4_revenue as T4
from .randomness import generator

OTHER = ["inflow_financing", "inflow_internal", "inflow_cash_deposit",
         "inflow_other_external", "inflow_unclassified"]


def v6_receipts(frame, paid_pmf, paths, seed, rho_firm, rho_customer):
    """Fixed settlement comparator, without a second T2 draw or cash head."""
    from agent1.models.t6_cash import simulate
    _, cash = simulate(frame, paid_pmf, 0., np.zeros(13), None, np.zeros(17), 0., [],
                       n=paths, rho=rho_firm, rho_customer=rho_customer, seed=seed)
    return cash


def future_dates(cutoff):
    return pd.date_range(pd.Timestamp(cutoff)+pd.Timedelta(days=1), periods=91, freq="D")


def daily_values(frame, date_col, amount_col, dates):
    if frame.empty:
        return np.zeros(len(dates))
    return frame.groupby(date_col)[amount_col].sum().reindex(dates, fill_value=0).to_numpy(float)


def weekly_sum(daily):
    values = np.asarray(daily, float)
    if values.shape[-1] != 91:
        raise ValueError("Daily horizon must contain exactly 91 days")
    return values.reshape(*values.shape[:-1], 13, 7).sum(axis=-1)


def revenue_history(invoices, cutoff):
    cutoff = pd.Timestamp(cutoff)
    if cutoff.dayofweek != 0:
        raise ValueError("v2 protocol uses Monday origins and Tuesday–Monday weeks")
    known = invoices[invoices.issue_date.le(cutoff)].copy()
    if known.empty:
        return pd.Series(dtype=float)
    known["week"] = known.issue_date.dt.to_period("W-MON").dt.start_time
    series = known.groupby("week").amount_gross.sum()
    last = cutoff-pd.Timedelta(days=6)
    return series.reindex(pd.date_range(series.index.min(), last, freq="7D"), fill_value=0.)


def revenue_quantiles(models, invoices, cutoff):
    s = revenue_history(invoices, cutoff)
    if len(s) < 30:
        return None
    weeks = pd.date_range(s.index[0], periods=len(s)+13, freq="7D")
    x, _, meta = T4.make_rows(s.to_numpy(), weeks, True, [len(s)-1], with_target=False)
    return np.sort(np.column_stack([models[q].predict(x, num_threads=4) for q in T4.QS]), axis=1).clip(0)*meta[:,2:3]


def cash_kernel(invoices, payments, cutoff):
    """Actual partial receipts from fully observed historical issuance cohorts."""
    cutoff = pd.Timestamp(cutoff)
    cohort = invoices[invoices.issue_date.between(cutoff-pd.Timedelta(days=730), cutoff-pd.Timedelta(days=120))]
    if cohort.empty or cohort.amount_gross.sum() <= 0:
        kernel = np.zeros(91)
        kernel[42] = 1.
        return kernel
    p = payments[payments.pay_date_true.le(cutoff)][["invoice_id", "pay_date_true", "amount"]].merge(
        cohort[["invoice_id", "issue_date"]], on="invoice_id", validate="many_to_one")
    lag = (p.pay_date_true-p.issue_date).dt.days.to_numpy()
    keep = (lag >= 0) & (lag < 91)
    kernel = np.bincount(lag[keep], weights=p.amount.to_numpy()[keep], minlength=91)/cohort.amount_gross.sum()
    if kernel.sum() > 1+1e-6:
        raise ValueError("Historical cash kernel exceeds issued receivables")
    return kernel


def profiles(dates, values, cutoff):
    """Observed daily proportions, aligned to target origin's seven-day weeks."""
    cutoff = pd.Timestamp(cutoff)
    start = cutoff-pd.Timedelta(days=7*104-1)
    history_dates = pd.date_range(start, cutoff)
    s = pd.Series(np.asarray(values, float), index=pd.DatetimeIndex(dates)).groupby(level=0).sum()
    x = s.reindex(history_dates, fill_value=0).to_numpy().reshape(-1,7)
    total = x.sum(1)
    x = x[total > 0]/total[total > 0,None]
    if not len(x):
        target = future_dates(cutoff)[:7]
        weights = np.array([calendar.is_business_day(d) for d in target], float)
        if not weights.sum():
            weights[:] = 1
        x = (weights/weights.sum())[None,:]
    return x


def draw_profiles(pool, n, rng):
    return pool[rng.integers(0,len(pool),size=(n,13))]


def allocate_weekly(amount, daily_profiles):
    a, profiles_array = np.asarray(amount, float), np.asarray(daily_profiles, float)
    if a.ndim != 2 or a.shape[1] != 13 or profiles_array.shape != (*a.shape,7):
        raise ValueError("Cash/profile dimensions do not match")
    if (a < 0).any() or (profiles_array < 0).any() or not np.allclose(profiles_array.sum(2),1):
        raise ValueError("Invalid nonnegative cash allocation")
    return (a[:,:,None]*profiles_array).reshape(len(a),91)


def fee_rate(bank, cutoff):
    known = bank[bank.value_date.le(pd.Timestamp(cutoff)) & bank.cash_flow_class.eq("ar")]
    fee = known.fee_deducted.fillna(0).sum()
    gross = known.balance_effect.sum()+fee
    return float(np.clip(fee/max(gross,1),0,1))


def net_bank_cash(applied, rate):
    if not 0 <= rate <= 1 or (np.asarray(applied)<0).any():
        raise ValueError("Invalid AR/fee bridge")
    fees = np.asarray(applied)*rate
    return np.asarray(applied)-fees, fees


def seasonal_schedule(outflows, cutoff):
    """Historical recurring cash obligations; no undated future actuals."""
    cutoff = pd.Timestamp(cutoff)
    dates = future_dates(cutoff)
    known = outflows[outflows.date.le(cutoff)].copy()
    recurrent = known[~known.category.isin(["supplier","capex"])]
    previous = recurrent[recurrent.date.gt(cutoff-pd.DateOffset(years=1))].copy()
    previous["forecast_date"] = previous.date.map(lambda d: calendar.next_business_day(d+pd.DateOffset(years=1)))
    previous = previous[previous.forecast_date.isin(dates)].copy()
    for category, index in previous.groupby("category").groups.items():
        history = recurrent[recurrent.category.eq(category)].sort_values("date")
        recent = history[history.date.gt(cutoff-pd.Timedelta(days=120))].amount
        past = history[history.date.between(cutoff-pd.Timedelta(days=485),cutoff-pd.Timedelta(days=365))].amount
        ratio = np.clip(recent.median()/past.median(),.5,2.) if len(recent) and len(past) and past.median()>0 else 1.
        previous.loc[index,"amount"] *= ratio
    expected = daily_values(previous,"forecast_date","amount",dates)
    # Explicitly recorded obligations override historical recurrence per category.
    if "known_at" in outflows:
        announced = outflows[outflows.known_at.le(cutoff) & outflows.date.isin(dates) & ~outflows.category.isin(["supplier","capex"])]
        categories = announced.category.unique()
        if len(categories):
            expected -= daily_values(previous[previous.category.isin(categories)],"forecast_date","amount",dates)
            expected += daily_values(announced,"date","amount",dates)
    return expected


def history_blocks(daily, outflows, cutoff, n, rng):
    """Joint 13-week historical blocks for all non-AR classes, supplier and capex."""
    cutoff = pd.Timestamp(cutoff)
    known = daily[daily.date.le(cutoff)].set_index("date")
    dates = pd.date_range(max(known.index.min(),cutoff-pd.Timedelta(days=729)),cutoff)
    arrays = [known.reindex(dates)[c].fillna(0).to_numpy(float) if c in known else np.zeros(len(dates)) for c in OTHER]
    out = outflows[outflows.date.le(cutoff)]
    for category in ("supplier","capex"):
        arrays.append(daily_values(out[out.category.eq(category)],"date","amount",dates))
    matrix = np.column_stack(arrays)
    possible = np.arange(max(0,len(dates)-90))
    possible = possible[dates[possible].dayofweek == future_dates(cutoff)[0].dayofweek]
    if not len(possible):
        return np.zeros((n,91,len(arrays)))
    starts = rng.choice(possible,n)
    return matrix[starts[:,None]+np.arange(91)[None,:]]


def draw_policy(daily, cutoff, n, rng):
    history = daily[daily.date.le(pd.Timestamp(cutoff)) & daily.date.gt(pd.Timestamp(cutoff)-pd.Timedelta(days=730))]
    ends = history[history.date.dt.is_quarter_end]
    positive = ends.owner_draw.gt(0)
    if not positive.any():
        return None, {"identified":False,"reason":"no past draw; no future draw inferred"}
    target = float(ends.loc[positive,"balance"].median())
    pre = ends.balance+ends.owner_draw
    upper = float(pre[positive].min())
    lower = max(target,float(pre[~positive].max())) if (~positive).any() else target
    consistent = lower <= upper
    cap = rng.uniform(lower,upper,n) if consistent and upper>lower else np.full(n,max(target,upper))
    return {"cap":cap,"target":np.full(n,target)}, {"identified":True,"consistent_bounds":consistent,
        "cap_lower":lower,"cap_upper":upper,"target":target}


def build_context(invoices, payments, bank, outflows, daily, cutoff, t4, *, n, seed, case):
    cutoff = pd.Timestamp(cutoff)
    observed = daily[daily.date.le(cutoff)]
    if observed.empty:
        raise ValueError("Opening bank balance is unavailable")
    dates = future_dates(cutoff)
    past_bank = bank[bank.value_date.le(cutoff) & bank.cash_flow_class.eq("ar")]
    ar_gross = past_bank.balance_effect+past_bank.fee_deducted.fillna(0)
    open_pool = profiles(past_bank.value_date,ar_gross,cutoff)
    origin_inv = invoices[invoices.issue_date.le(cutoff)]
    issue_pool = profiles(origin_inv.issue_date,origin_inv.amount_gross,cutoff)
    open_profile = draw_profiles(open_pool,n,generator(seed,case,"open_cash_timing"))
    rq = revenue_quantiles(t4,invoices,cutoff)
    issued = np.zeros((n,13))
    if rq is not None:
        u = ndtr(generator(seed,case,"new_revenue").standard_normal((n,13)))
        q10,q50,q90 = rq.T
        issued = np.maximum(0,np.where(u<.5,q10+(q50-q10)*(u-.1)/.4,q50+(q90-q50)*(u-.5)/.4))
    issued_daily = allocate_weekly(issued,draw_profiles(issue_pool,n,generator(seed,case,"new_issue_timing")))
    kernel = cash_kernel(invoices,payments,cutoff)
    gross_new = np.zeros((n,91))
    for delay in np.flatnonzero(kernel):
        gross_new[:,delay:] += issued_daily[:,:91-delay]*kernel[delay]
    rate = fee_rate(bank,cutoff)
    new_bank,new_fees = net_bank_cash(gross_new,rate)
    blocks = history_blocks(daily,outflows,cutoff,n,generator(seed,case,"non_ar_and_variable_outflows"))
    other_by_class = blocks[:,:,:len(OTHER)]
    variable = blocks[:,:,len(OTHER):].copy()
    if "known_at" in outflows:
        for column,category in enumerate(("supplier","capex")):
            announced = outflows[outflows.known_at.le(cutoff)&outflows.date.isin(dates)&outflows.category.eq(category)]
            if len(announced):
                known_days = dates.isin(announced.date)
                # Known category/day totals replace that sampled category/day,
                # rather than adding a second payment on top of historical cash.
                variable[:,known_days,column] = daily_values(announced,"date","amount",dates)[known_days]
    outflow = variable.sum(2)+seasonal_schedule(outflows,cutoff)[None,:]
    policy,policy_audit = draw_policy(daily,cutoff,n,generator(seed,case,"draw_policy"))
    return {"b0":float(observed.sort_values("date").balance.iloc[-1]),"dates":dates,
            "open_profiles":open_profile,"fee_rate":rate,"new_bank_daily":new_bank,"new_fee_daily":new_fees,
            "other_daily":other_by_class.sum(2),"other_by_class_daily":other_by_class,
            "outflow_daily":outflow,"draw":policy,"draw_audit":policy_audit,
            "scale":max(float(outflow.mean()*7),1.),"scope":"operating_bank_account"}


def bank_paths_from_daily(b0, inflow_daily, outflow_daily, dates, draw=None):
    inflow,outflow = np.asarray(inflow_daily,float),np.asarray(outflow_daily,float)
    if inflow.shape != outflow.shape or inflow.ndim!=2 or inflow.shape[1]!=91 or not np.isfinite(inflow).all() or not np.isfinite(outflow).all():
        raise ValueError("Bank ledger requires finite aligned daily cashflows")
    balance = np.empty_like(inflow)
    withdrawal = np.zeros_like(inflow)
    running = np.full(len(inflow),float(b0))
    max_error = 0.
    for day,date in enumerate(dates):
        before = running.copy()
        running += inflow[:,day]-outflow[:,day]
        if draw is not None and date.is_quarter_end:
            withdrawal[:,day] = np.where(running>draw["cap"],np.maximum(running-draw["target"],0),0)
            running -= withdrawal[:,day]
        balance[:,day] = running
        max_error = max(max_error,float(np.abs(before+inflow[:,day]-outflow[:,day]-withdrawal[:,day]-running).max(initial=0)))
    return {"balance":balance[:,6::7],"daily_balance":balance,"owner_draw":withdrawal,"max_ledger_error_vnd":max_error}


def simulate_bank(open_applied_weekly,context):
    applied = allocate_weekly(open_applied_weekly,context["open_profiles"])
    open_bank,fee = net_bank_cash(applied,context["fee_rate"])
    inflow = open_bank+context["new_bank_daily"]+context["other_daily"]
    result = bank_paths_from_daily(context["b0"],inflow,context["outflow_daily"],context["dates"],context["draw"])
    result.update(open_applied_daily=applied,open_bank_daily=open_bank,open_fee_daily=fee)
    return result


def truth_from_daily(daily,cutoff):
    cutoff = pd.Timestamp(cutoff)
    history = daily[daily.date.le(cutoff)].sort_values("date")
    dates = future_dates(cutoff)
    actual = daily.set_index("date").reindex(dates)
    if actual.balance.isna().any():
        raise ValueError("Truth lacks complete follow-up")
    return float(history.balance.iloc[-1]),actual.balance.to_numpy()[6::7]
