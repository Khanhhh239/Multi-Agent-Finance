"""Causal operating decisions made from information available in the current week."""
from __future__ import annotations

import numpy as np
import pandas as pd


def plan_inventory_purchases(booked_orders, cogs_ratio, opening_inventory,
                             *, sale_price_index=None, input_cost_index=None):
    """Replenish against current bookings and stock, never a later week's demand.

    Values are net of VAT and in VND. Bookings are observed at the start of each
    week. Purchases arrive in that week; fulfillment then consumes their cost.
    """
    orders = np.asarray(booked_orders, dtype=float)
    sale_price = np.ones(len(orders)) if sale_price_index is None else np.asarray(sale_price_index, dtype=float)
    input_cost = np.ones(len(orders)) if input_cost_index is None else np.asarray(input_cost_index, dtype=float)
    if (sale_price.shape != orders.shape or input_cost.shape != orders.shape or
            not np.isfinite(sale_price).all() or not np.isfinite(input_cost).all() or
            (sale_price <= 0).any() or (input_cost <= 0).any()):
        raise ValueError('Invalid weekly sale price or input cost index')
    if not np.isfinite(orders).all() or (orders < 0).any() or not 0 <= cogs_ratio <= 1:
        raise ValueError('Invalid booked orders or cost ratio')
    stock = float(opening_inventory)
    if not np.isfinite(stock) or stock < 0:
        raise ValueError('Invalid opening inventory')
    expected = float(orders[0] / sale_price[0]) if len(orders) else 0.
    rows = []
    for order, price, cost in zip(orders, sale_price, input_cost):
        units_at_base_price = order / price
        expected = .7 * expected + .3 * units_at_base_price
        fulfillment = units_at_base_price * cogs_ratio * cost
        target = 1.5 * expected * cogs_ratio * cost
        purchase = max(0., fulfillment + target - stock)
        close = stock + purchase - fulfillment
        rows.append((order, stock, purchase, fulfillment, close, target))
        stock = close
    return pd.DataFrame(rows, columns=['booked_orders', 'opening_inventory', 'purchase_net',
                                       'fulfilled_order_cost', 'closing_inventory', 'target_inventory'])


def observed_credit_holds(liquidity, rng, *, default_week=None, default_events=None, seller_credit_stress=None,
                          hold_threshold=-1.4, release_threshold=-.6,
                          default_cooldown_weeks=26):
    """Seller sees a noisy current credit signal and may hold later sales.

    A hold begins after two weak weekly signals. It ends after two recovery
    signals. Neither the realized default week nor a later signal is consulted.
    """
    liquidity = np.asarray(liquidity, dtype=float)
    if liquidity.ndim != 2:
        raise ValueError('Expected customers by weeks')
    n, weeks = liquidity.shape
    seller_stress = (np.zeros(weeks) if seller_credit_stress is None else
                     np.asarray(seller_credit_stress, dtype=float))
    if seller_stress.shape != (weeks,) or not np.isfinite(seller_stress).all():
        raise ValueError('Expected one finite seller credit stress value per week')
    defaults = np.full(n, -1, dtype=int) if default_week is None else np.asarray(default_week, dtype=int)
    if len(defaults) != n:
        raise ValueError('One observed default week per customer is required')
    if default_events is None:
        default_events = np.zeros((n, weeks), dtype=bool)
        valid = (defaults >= 0) & (defaults < weeks)
        default_events[np.flatnonzero(valid), defaults[valid]] = True
    else:
        default_events = np.asarray(default_events, dtype=bool)
        if default_events.shape != (n, weeks):
            raise ValueError('Expected customer by week default events')
    default_block = np.zeros((n, weeks), dtype=bool)
    for event_week in range(weeks):
        affected = default_events[:, event_week]
        if affected.any():
            default_block[affected, event_week + 1:min(weeks, event_week + default_cooldown_weeks + 1)] = True
    signal = liquidity + rng.normal(0, .45, (n, weeks))
    held = np.zeros((n, weeks), dtype=bool)
    transitions = []
    for customer in range(n):
        weak = recovered = 0
        signal_active = False
        default_active = False
        for week in range(weeks):
            score = float(signal[customer, week])
            # Orders are booked on Monday; the default event is recorded on
            # Thursday of its week, so it can only block next week's orders.
            default_now = bool(default_block[customer, week])
            if default_now and not default_active:
                transitions.append((customer, week, 'seller_default_hold', score,
                                    float(signal[customer, week - 1]) if week else np.nan))
            elif default_active and not default_now:
                transitions.append((customer, week, 'seller_default_release', score,
                                    float(signal[customer, week - 1]) if week else np.nan))
            default_active = default_now
            weak = weak + 1 if score < hold_threshold + .40 * seller_stress[week] else 0
            recovered = recovered + 1 if score > release_threshold + .25 * seller_stress[week] else 0
            if not signal_active and weak >= 2:
                signal_active = True
                transitions.append((customer, week, 'seller_credit_hold', score,
                                    float(signal[customer, week - 1])))
            elif signal_active and recovered >= 2:
                signal_active = False
                transitions.append((customer, week, 'seller_credit_release', score,
                                    float(signal[customer, week - 1])))
            held[customer, week] = signal_active or default_active
    return held, transitions


def customer_activity(liquidity, initial_active, rng, *, growth=0., demand_stress=None,
                      protected=None):
    """Draw entry, temporary exit and return using only the current week's state.

    Customers are a prospect pool, so an inactive prospect can become a new
    buyer and a former buyer can return. The fixed pool is an explicit finite
    horizon approximation; no final-period sales are used to set transitions.
    """
    liquidity = np.asarray(liquidity, dtype=float)
    n, weeks = liquidity.shape
    initial_active = np.asarray(initial_active, dtype=bool)
    if initial_active.shape != (n,):
        raise ValueError('Expected one initial activity state per customer')
    stress = np.zeros(weeks) if demand_stress is None else np.asarray(demand_stress, dtype=float)
    protected = np.zeros(n, dtype=bool) if protected is None else np.asarray(protected, dtype=bool)
    if stress.shape != (weeks,) or protected.shape != (n,):
        raise ValueError('Invalid customer activity inputs')
    active = initial_active.copy()
    seen = initial_active.copy()
    path = np.zeros((n, weeks), dtype=bool)
    changes = []
    for week in range(weeks):
        if week:
            # 12% annual base attrition, offset by prospect entry and return.
            # These are synthetic sensitivity parameters, not VN estimates.
            weak = np.clip(-liquidity[:, week], 0, 3)
            good = np.clip(liquidity[:, week], -3, 3)
            churn_p = np.clip(.0025 * np.exp(.35 * weak + .30 * stress[week] - .25 * growth), 0, .04)
            entry_p = np.clip(.008 * np.exp(.20 * good - .35 * stress[week] + .30 * growth), .001, .04)
            exit_now = active & ~protected & (rng.random(n) < churn_p)
            enter_now = ~active & (rng.random(n) < entry_p)
            for i in np.flatnonzero(exit_now):
                changes.append((int(i), week, 'customer_churned'))
            for i in np.flatnonzero(enter_now):
                changes.append((int(i), week, 'customer_returned' if seen[i] else 'customer_acquired'))
            active[exit_now] = False
            active[enter_now] = True
            seen |= enter_now
        path[:, week] = active
    return path, changes


def next_default_after_issue(issue_day, customer_index, default_events, week0_i):
    """Find the next observed default for each invoice, excluding past episodes."""
    issue_day = np.asarray(issue_day, dtype=np.int64)
    customer_index = np.asarray(customer_index, dtype=int)
    events = np.asarray(default_events, dtype=bool)
    if events.ndim != 2 or issue_day.shape != customer_index.shape:
        raise ValueError('Invalid invoice or customer default event shape')
    result = np.full(len(issue_day), 10 ** 9, dtype=np.int64)
    for customer in np.unique(customer_index):
        weeks = np.flatnonzero(events[customer])
        if not len(weeks):
            continue
        dates = int(week0_i) + weeks * 7 + 3
        rows = np.flatnonzero(customer_index == customer)
        following = np.searchsorted(dates, issue_day[rows], side='left')
        valid = following < len(dates)
        result[rows[valid]] = dates[following[valid]]
    return result


def weekly_payment_dates(cal, week0_i, customer_i, start_i, liquidity, stress,
                         median_days, payrun, stop_i, observation_end_i, rng, ultra=None):
    """Draw payment execution each week while an invoice remains outstanding.

    ``stop_i`` is the date an observed customer default prevents further
    payment. A return value of -1 means administratively censored or stopped;
    it does not mean bad debt. Only current-week liquidity enters the hazard.
    """
    customer_i = np.asarray(customer_i, dtype=int)
    start_i = np.asarray(start_i, dtype=int)
    stop_i = np.asarray(stop_i, dtype=int)
    median_days = np.asarray(median_days, dtype=float)
    payrun = np.asarray(payrun)
    n, weeks = len(start_i), liquidity.shape[1]
    result = np.full(n, -1, dtype=int)
    if n == 0:
        return result
    start_week = np.clip((start_i - week0_i) // 7, 0, weeks - 1)
    order = np.argsort(start_week, kind='stable')
    sorted_weeks = start_week[order]
    cursor = 0
    active = np.empty(0, dtype=int)
    for week in range(weeks):
        next_cursor = int(np.searchsorted(sorted_weeks, week, side='right'))
        if next_cursor > cursor:
            active = np.concatenate((active, order[cursor:next_cursor]))
            cursor = next_cursor
        if not len(active):
            continue
        week_start = week0_i + 7 * week
        active = active[(week_start < stop_i[active]) & (start_i[active] <= observation_end_i)]
        if not len(active):
            continue
        earliest = np.maximum(start_i[active], week_start)
        candidate = np.empty(len(active), dtype=int)
        for pattern in np.unique(payrun[active]):
            mask = payrun[active] == pattern
            schedule = cal.next_ptn[str(pattern)]
            normal = cal.snap_bd(schedule[cal.clip(earliest[mask])])
            # A nominal weekend/holiday run may have rolled into this week.
            prior = cal.snap_bd(schedule[cal.clip(earliest[mask] - 6)])
            candidate[mask] = np.where(prior >= earliest[mask], prior, normal)
        available = ((candidate <= week_start + 6) & (candidate <= observation_end_i) &
                     (candidate < stop_i[active]))
        scale = np.exp(.7 * liquidity[customer_i[active], week] - .25 * stress[week])
        if ultra is not None:
            scale *= np.where(np.asarray(ultra)[active], .18, 1.)
        hazard = 1 - np.exp(-7. * scale / np.maximum(median_days[active], 3.))
        paid = available & (rng.random(len(active)) < np.clip(hazard, 0, .95))
        result[active[paid]] = candidate[paid]
        active = active[~paid]
    return result
