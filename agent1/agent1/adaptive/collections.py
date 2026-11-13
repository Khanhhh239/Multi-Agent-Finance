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
    """Default amount policy; the removed customer T1 is never trained here."""
    return {
        "policy": "amount",
        "status": "fixed_amount_policy",
        "limitation": "Probability policies require a separate causal audit using the active T1.",
    }
