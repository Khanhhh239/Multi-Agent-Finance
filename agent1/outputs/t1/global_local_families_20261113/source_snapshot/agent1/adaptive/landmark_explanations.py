"""Whole-ensemble grouped SHAP with census/stratified references and sensitivity."""

import hashlib
import json
import time

import numpy as np
import pandas as pd

from .compact_t1 import CompactT1
from .explanation_reference import reference_plan, stability_report
from .explanations import shapley_values

PROTOCOL = "landmark-grouped-exact-reference-v2"


def explain_landmark(
    rows,
    opened,
    components,
    cutoff,
    *,
    delay_days=0,
    delay_customer=None,
    model_asof=None,
    probability_field="payment_probability_4w",
    output_field="payment_explanation",
):
    if not rows:
        return None
    started = time.perf_counter()
    leaves = [(float(weight), model) for weight, model in components if weight]
    if not leaves or any(
        not isinstance(model, CompactT1) or not np.isfinite(weight) or weight < 0
        for weight, model in leaves
    ):
        raise ValueError("Invalid landmark explanation components")
    if not np.isclose(sum(weight for weight, _ in leaves), 1.0, atol=1e-12, rtol=0):
        raise ValueError("Invalid landmark explanation weights")
    schema = leaves[0][1].feature_schema
    names = leaves[0][1].feature_names
    if any(
        model.feature_schema != schema or model.feature_names != names
        for _, model in leaves
    ):
        raise ValueError("Incompatible landmark explanation schemas")
    values = [model.prepare(opened) for _, model in leaves]
    active = {column for _, model in leaves for column in model.active}
    groups = [
        (key, label, columns)
        for key, label, columns in leaves[0][1].shap_groups
        if active.intersection(columns)
    ]
    dimensions = len(groups)
    masks = (np.arange(2**dimensions)[:, None] & (1 << np.arange(dimensions))) != 0
    column_masks = np.zeros((len(masks), len(names)), bool)
    for index, (_, _, columns) in enumerate(groups):
        column_masks[:, columns] = masks[:, index, None]
    # The existing reference planner stratifies age, terms, relative amount,
    # customer history count and delay. Its six-column input order is explicit.
    order = [
        names.index(name)
        for name in (
            "relative_amount",
            "term_days",
            "customer_delay_180d",
            "company_delay_180d",
            "customer_settlements_180d",
            "age_days",
        )
    ]
    references, weights, info = reference_plan(
        opened.invoice_id.tolist(), values[0][:, order]
    )
    snapshot = dict(
        protocol=PROTOCOL,
        cutoff=str(pd.Timestamp(cutoff).date()),
        schema=schema,
        **info,
        union_count=len(references),
        prepared_inputs=[
            {
                "method": model.variant,
                "weight": weight,
                "values": value[references].tolist(),
            }
            for (weight, model), value in zip(leaves, values)
        ],
        groups=[
            {
                "key": key,
                "columns": [names[column] for column in columns if column in active],
            }
            for key, _, columns in groups
        ],
    )
    reference_hash = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    snapshot["hash"] = reference_hash
    positions = {str(iid): position for position, iid in enumerate(opened.invoice_id)}
    for row in rows:
        position = positions[str(row["invoice_id"])]
        shift = (
            int(np.ceil(delay_days / 7))
            if delay_days
            and (not delay_customer or row["customer_id"] == delay_customer)
            else 0
        )
        effective_weeks = max(0, 4 - shift)
        games = np.zeros((weights.shape[1], len(masks)))
        for (weight, model), value in zip(leaves, values):
            hybrids = np.where(
                column_masks[:, None, :], value[position], value[references][None, :, :]
            ).reshape(-1, len(names))
            unique, inverse = np.unique(hybrids, axis=0, return_inverse=True)
            probabilities = (
                model.distribution_from_features(unique, horizon=4)[
                    :, :effective_weeks
                ].sum(1)
                if effective_weeks
                else np.zeros(len(unique))
            )
            masked = probabilities[inverse].reshape(len(masks), len(references))
            games += weight * (masked @ weights).T
        contributions = shapley_values(games, dimensions)
        primary = contributions[0]
        stability, diagnostics = stability_report(
            primary, contributions[1:], len(opened)
        )
        probability = float(row[probability_field])
        reconstructed = float(games[0, 0] + primary.sum())
        if not np.allclose(
            games[:, -1], probability, atol=1e-10, rtol=0
        ) or not np.isclose(reconstructed, probability, atol=1e-10, rtol=0):
            raise ValueError(
                "Landmark SHAP does not reconstruct the served probability"
            )
        factors = []
        for index, (key, label, columns) in enumerate(groups):
            raw = {
                names[column]: float(values[0][position, column])
                for column in columns
                if column in active
            }
            effect = float(primary[index])
            factors.append(
                {
                    "feature": key,
                    "label": label,
                    "value": raw,
                    "value_unit": "prepared_group",
                    "contribution": effect,
                    "contribution_pp": 100 * effect,
                    "direction": "increase"
                    if effect > 1e-12
                    else "decrease"
                    if effect < -1e-12
                    else "neutral",
                    "stability": stability[index],
                    "business_review": {
                        "status": "context_only",
                        "feature": key,
                        "value": raw,
                        "reason": "Grouped predictive attribution requires separate business evidence.",
                    },
                }
            )
        row[output_field] = {
            "protocol": PROTOCOL,
            "status": "available",
            "method": "exact_grouped_interventional_shapley",
            "target": probability_field,
            "horizon_weeks": 4,
            "cutoff": snapshot["cutoff"],
            "model_asof": model_asof,
            "model_version": schema,
            "feature_schema": schema,
            "units": "probability",
            "contribution_units": "percentage_points",
            "probability": probability,
            "baseline_probability": float(games[0, 0]),
            "reconstructed_probability": reconstructed,
            "additivity_error": abs(reconstructed - probability),
            "factors": sorted(factors, key=lambda item: -abs(item["contribution"])),
            "scenario_shift_weeks": shift,
            "stability": diagnostics,
            "reference": dict(
                kind="open_invoices_at_cutoff",
                **{
                    key: snapshot[key]
                    for key in (
                        "count",
                        "population",
                        "selection",
                        "weighting",
                        "hash",
                        "cutoff",
                        "max_weighted_cdf_distance",
                        "audit_sample_count",
                    )
                },
            ),
            "group_count": dimensions,
            "coalition_count": len(masks),
            "background_count": info["count"],
            "background_union_count": len(references),
            "limitations": [
                "Exact for the declared groups and finite reference distribution. Within-group feature effects are combined.",
                "Sensitivity concerns background sampling. It does not measure uncertainty in the prediction or support of every hybrid input.",
                "Attributions describe predictive associations. Causal or collection-effect conclusions require separate evidence.",
            ],
        }
    snapshot["elapsed_seconds"] = time.perf_counter() - started
    return snapshot
