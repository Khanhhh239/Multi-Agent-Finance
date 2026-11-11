"""Budgeted triage metrics, not causal collections uplift."""

import numpy as np


def budget_metrics(scores, unresolved_amount, budget):
    scores = np.asarray(scores, float)
    target = np.asarray(unresolved_amount, float)
    k = min(int(budget), len(target))
    if k <= 0 or np.any(target < 0) or not np.isfinite(target).all():
        raise ValueError("Invalid budget or outcome")
    chosen = np.argsort(-scores, kind="stable")[:k]
    ideal = np.sort(target)[::-1][:k].sum()
    return dict(
        budget=k,
        amount_capture=float(target[chosen].sum() / target.sum())
        if target.sum()
        else 0.0,
        normalized_value=float(target[chosen].sum() / ideal) if ideal else 0.0,
        precision=float(np.mean(target[chosen] > 0)),
    )


def train_policy(data, asof):
    import pandas as pd
    from .data import observed
    from .methods import Method

    rows = []
    for days in (84, 56, 28):
        origin = pd.Timestamp(asof) - pd.Timedelta(days=days)
        past = observed(data, origin)
        opened = past[
            (past.remaining_amount > 0.01) & past.written_off_at.isna()
        ].copy()
        if len(opened) < 20:
            return dict(policy="amount", status="insufficient_history")
        future = observed(data, origin + pd.Timedelta(days=28)).set_index("invoice_id")
        target = future.loc[opened.invoice_id, "remaining_amount"].to_numpy()
        p = (
            Method("customer")
            .fit(past, origin)
            .distribution(opened, (origin - opened.issue_date).dt.days.to_numpy())[
                :, :4
            ]
            .sum(1)
        )
        rows.append((opened.remaining_amount.to_numpy(), p, target))
    policies = ("amount", "risk", "amount_at_risk")

    def evaluate(row, policy):
        amount, p, target = row
        scores = (
            amount
            if policy == "amount"
            else 1 - p
            if policy == "risk"
            else amount * (1 - p)
        )
        return budget_metrics(scores, target, 10)

    validation = {
        n: float(np.mean([evaluate(row, n)["normalized_value"] for row in rows[:2]]))
        for n in policies
    }
    selected = max(validation, key=validation.get)
    audit = evaluate(rows[2], selected)
    baseline = evaluate(rows[2], "amount")
    accepted = audit["normalized_value"] >= baseline["normalized_value"]
    return dict(
        policy=selected if accepted else "amount",
        status="evaluated",
        validation=validation,
        audit=audit,
        baseline=baseline,
        accepted=accepted,
        metric="normalized_unresolved_value_at_10_after_28d",
        limitation="Triage coverage, not incremental cash caused by contacting a customer",
    )
