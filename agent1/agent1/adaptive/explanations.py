"""Exact interventional Shapley attribution of the served four-week probability.

Shared Shapley arithmetic and delegation to the active landmark's groups.
This explains the whole conditional distribution, including probability pooling
and scenario shifts, rather than summing individual weekly log-odds.
Exactness concerns this finite reference sample, not a population or causality.
"""

from math import comb

import numpy as np


def shapley_values(coalition_values, dimensions):
    """Shapley formula; columns are bit masks 0 .. 2**dimensions - 1."""
    values = np.asarray(coalition_values, float)
    if (
        values.ndim != 2
        or values.shape[1] != 2**dimensions
        or not np.isfinite(values).all()
    ):
        raise ValueError("Giá trị liên minh SHAP không hợp lệ")
    result = np.zeros((len(values), dimensions))
    for feature in range(dimensions):
        for mask in range(2**dimensions):
            if not mask & (1 << feature):
                weight = 1 / (dimensions * comb(dimensions - 1, mask.bit_count()))
                result[:, feature] += weight * (
                    values[:, mask | (1 << feature)] - values[:, mask]
                )
    return result


def explain_collections(
    rows, opened, components, cutoff, *, delay_days=0, delay_customer=None,
    model_asof=None, probability_field="payment_probability_4w",
    output_field="payment_explanation",
):
    """Explain only the active global/continued landmark T1 interface."""
    from .compact_t1 import CompactT1, explain_compact

    if all(isinstance(model, CompactT1) for weight, model in components if weight):
        return explain_compact(
            rows, opened, components, cutoff, delay_days=delay_days,
            delay_customer=delay_customer, model_asof=model_asof,
            probability_field=probability_field, output_field=output_field,
        )
    for row in rows:
        row[output_field] = {
            "status": "unavailable", "target": probability_field,
            "cutoff": str(cutoff.date()),
            "message": "Phiên bản T1 không hỗ trợ giao diện landmark hiện tại.",
        }
    return None
