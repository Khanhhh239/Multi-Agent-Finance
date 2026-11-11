"""Exact interventional Shapley attribution of the served four-week probability.

Enumerate all 64 coalitions of the six prepared T1 inputs. This explains the
whole conditional distribution, including probability pooling and scenario
shifts, rather than summing attributions of individual weekly log-odds.
Exactness concerns this finite reference sample, not a population or causality.
"""

import hashlib
import json
from math import comb

import numpy as np
from threadpoolctl import threadpool_limits

from .business_explanations import HistoryEvidence, review_factors
from .explanation_reference import HybridSupport, reference_plan, stability_report

INPUTS = (
    ("amount", "Giá trị hóa đơn", "VND"),
    ("term_days", "Kỳ hạn thanh toán", "ngày"),
    (
        "customer_delay_days",
        "Trễ lịch sử khách trước ngày lập (đã co về doanh nghiệp)",
        "ngày",
    ),
    ("company_delay_days", "Trễ trung vị doanh nghiệp trước ngày lập", "ngày"),
    (
        "customer_history_count",
        "Số hóa đơn khách đã tất toán trước ngày lập",
        "hóa đơn",
    ),
    ("age_days", "Tuổi hóa đơn tại ngày dự báo", "ngày"),
)
PROTOCOL = "t1-4w-exact-interventional-v2"


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


def _leaves(components):
    from .methods import DistributionEnsemble, Method

    result = []
    for weight, model in components:
        if weight == 0:
            continue
        if not np.isfinite(weight) or weight < 0:
            raise ValueError("Trọng số mô hình giải thích không hợp lệ")
        if isinstance(model, DistributionEnsemble):
            if not model.members:
                raise ValueError("Tổ hợp mô hình rỗng")
            result.extend(
                _leaves([(weight / len(model.members), m) for m in model.members])
            )
        elif isinstance(model, Method):
            result.append((float(weight), model))
        else:
            raise TypeError("Mô hình chưa hỗ trợ giao diện giải thích T1")
    return result


def _natural_value(column, value):
    if column in (0, 4):
        return round(float(np.expm1(value)))
    return float(value)


def _hybrid_probabilities(model, hybrids, weeks, cache):
    """Reuse identical prepared inputs across coalitions and displayed invoices.

    Keep four cumulative probabilities so customer-specific scenario horizons
    can share evaluations. The cache is per model/per request and bounded.
    """
    if weeks == 0:
        return np.zeros(len(hybrids))
    unique, inverse = np.unique(hybrids, axis=0, return_inverse=True)
    cumulative = np.empty((len(unique), 4))
    keys = [row.tobytes() for row in unique]
    missing = []
    for i, key in enumerate(keys):
        known = cache.get(key)
        if known is None:
            missing.append(i)
        else:
            cumulative[i] = known
    for start in range(0, len(missing), 16384):
        positions = missing[start : start + 16384]
        batch = unique[positions]
        predictions = model.distribution_from_features(
            batch[:, :5], batch[:, 5], horizon=4
        )
        values = predictions[:, :4].cumsum(1)
        cumulative[positions] = values
        for position, value in zip(positions, values):
            if len(cache) >= 100000:
                break
            cache[keys[position]] = value.copy()
    return cumulative[inverse, weeks - 1]


def explain_collections(
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
    """Attach immutable explanations only to invoices in the displayed queue.

    Background: census or weighted strata from the open cohort at the same
    cutoff, shared across displayed invoices. All feature histories remain fixed. Six
    prepared feature groups are replaced jointly across ensemble members; age
    determines the conditional weekly risk set and is recomputed for each mask.

    Return the reproducible background snapshot once for storage at plan level.
    """
    from .methods import CATALOG, features

    common = {
        "protocol": PROTOCOL,
        "target": probability_field,
        "horizon_weeks": 4,
        "cutoff": str(cutoff.date()),
        "model_asof": model_asof,
        "model_version": None,
        "units": "probability",
        "contribution_units": "percentage_points",
    }
    try:
        leaves = _leaves(components)
    except TypeError:
        for row in rows:
            row[output_field] = dict(
                common,
                status="unavailable",
                message="Phiên bản này chưa hỗ trợ giải thích xác suất tất toán.",
            )
        return
    if not leaves or not np.isclose(sum(w for w, _ in leaves), 1):
        raise ValueError("Tổng trọng số mô hình giải thích phải bằng một")

    if not rows:
        return None
    positions = {str(iid): i for i, iid in enumerate(opened.invoice_id)}
    selected = np.asarray([positions[r["invoice_id"]] for r in rows])
    ages = (cutoff - opened.issue_date).dt.days.to_numpy()
    shift = int(np.ceil(delay_days / 7)) if delay_days else 0
    shifts = np.asarray(
        [
            shift if not delay_customer or r["customer_id"] == delay_customer else 0
            for r in rows
        ]
    )
    effective_weeks = np.maximum(0, 4 - shifts)
    dimensions = len(INPUTS)
    masks = (np.arange(2**dimensions)[:, None] & (1 << np.arange(dimensions))) != 0
    encoded_members = [
        np.column_stack((features(opened, model.history), ages)) for _, model in leaves
    ]
    if not all(np.isfinite(encoded).all() for encoded in encoded_members):
        raise ValueError("Đặc trưng giải thích phải hữu hạn")
    # Strata use only the serving model's prepared inputs, not labels/outcomes.
    sampling_inputs = sum(
        weight * encoded for (weight, _), encoded in zip(leaves, encoded_members)
    )
    reference_indices, reference_weights, reference_info = reference_plan(
        opened.invoice_id.tolist(), sampling_inputs
    )
    n_reference = len(reference_indices)
    games = np.zeros((reference_weights.shape[1], len(rows), len(masks)))
    unsupported_fraction = np.zeros(len(rows))
    member_values = []
    evidence_sources = [HistoryEvidence(model.history) for _, model in leaves]
    reference_payload = []
    members = []
    with threadpool_limits(limits=1, user_api="blas"):
        for (weight, model), encoded in zip(leaves, encoded_members):
            targets, background = encoded[selected], encoded[reference_indices]
            name = model.variant
            label = next((r[2] for r in CATALOG if r[0] == name), name)
            members.append({"method": name, "label": label, "weight": weight})
            member_values.append(targets)
            reference_payload.append(
                {"method": name, "weight": weight, "values": background.tolist()}
            )
            support = HybridSupport(encoded)
            prediction_cache = {}
            for i, target in enumerate(targets):
                # Bound memory independently of the displayed queue length.
                hybrids = np.where(
                    masks[:, None, :], target, background[None, :, :]
                ).reshape(-1, dimensions)
                scores = _hybrid_probabilities(
                    model, hybrids, effective_weeks[i], prediction_cache
                )
                masked_predictions = scores.reshape(len(masks), n_reference)
                games[:, i] += weight * (masked_predictions @ reference_weights).T
                unsupported = support.unsupported(hybrids).reshape(
                    len(masks), n_reference
                )
                # Exclude the unmodified target/background coalitions.
                unsupported_fraction[i] += weight * float(
                    (unsupported[1:-1] @ reference_weights[:, 0]).mean()
                )

    game = games[0]
    contributions = shapley_values(game, dimensions)
    audit_contributions = np.asarray([shapley_values(g, dimensions) for g in games[1:]])
    if len(games) == 1:
        audit_contributions = np.empty((0, len(rows), dimensions))
    snapshot = dict(
        protocol=PROTOCOL,
        cutoff=str(cutoff.date()),
        model_asof=model_asof,
        **reference_info,
        prepared_inputs=reference_payload,
    )
    reference_hash = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    snapshot["hash"] = reference_hash
    for i, row in enumerate(rows):
        probability = float(row[probability_field])
        if not np.isclose(game[i, -1], probability, atol=1e-10, rtol=0):
            raise ValueError("Giải thích không khớp xác suất mô hình đang phục vụ")
        if not np.allclose(games[:, i, -1], probability, atol=1e-10, rtol=0):
            raise ValueError("Mẫu kiểm tra giải thích không khớp xác suất đang phục vụ")
        stability, diagnostics = stability_report(
            contributions[i], audit_contributions[:, i], len(opened)
        )
        plausibility = {
            "status": "caution" if unsupported_fraction[i] > 0.1 else "no_warning",
            "unsupported_fraction": float(unsupported_fraction[i]),
            "threshold": 0.1,
            "method": "history_constraint_and_correlated_pair_support_v1",
            "scope": "diagnostic_not_proof_of_validity",
        }
        factors = []
        for j, (key, label, unit) in enumerate(INPUTS):
            values = [_natural_value(j, x[i, j]) for x in member_values]
            # Preserve the invoice's original VND value rather than inverting a log.
            if j == 0:
                values = [int(opened.iloc[selected[i]].amount)] * len(values)
            same = all(np.isclose(v, values[0], atol=1e-8, rtol=0) for v in values)
            effect = float(contributions[i, j])
            displayed_value = values[0] if same else None
            if j == 0 and same and abs(displayed_value) > 2**53 - 1:
                displayed_value = str(displayed_value)
            factors.append(
                {
                    "feature": key,
                    "label": label,
                    "value": displayed_value,
                    "value_unit": unit,
                    "values_by_model": [
                        {"method": m["method"], "value": v}
                        for m, v in zip(members, values)
                    ]
                    if not same
                    else [],
                    "contribution": effect,
                    "contribution_pp": 100 * effect,
                    "stability": stability[j],
                    "direction": "increase"
                    if effect > 1e-12
                    else "decrease"
                    if effect < -1e-12
                    else "neutral",
                }
            )
        invoice = opened.iloc[selected[i]]
        review_factors(
            factors,
            invoice,
            cutoff,
            [
                source.for_invoice(invoice, target[i])
                for source, target in zip(evidence_sources, member_values)
            ],
            checked=(
                diagnostics["checked"]
                and diagnostics["sample_count"] >= 3
                and plausibility["status"] == "no_warning"
                and reference_info["max_weighted_cdf_distance"] <= 0.1
            ),
        )
        baseline = float(game[i, 0])
        reconstructed = baseline + float(contributions[i].sum())
        if not np.isclose(reconstructed, probability, atol=1e-10, rtol=0):
            raise ValueError("Tổng đóng góp SHAP không khớp dự báo")
        row[output_field] = dict(
            common,
            status="available",
            probability=probability,
            method="exact_interventional_shapley",
            baseline_probability=baseline,
            reconstructed_probability=reconstructed,
            additivity_error=abs(reconstructed - probability),
            members=members,
            stability=diagnostics,
            plausibility=plausibility,
            scenario_shift_weeks=int(shifts[i]),
            reference={
                "kind": "open_invoices_at_cutoff",
                "count": reference_info["count"],
                "population": len(opened),
                "cutoff": str(cutoff.date()),
                "hash": reference_hash,
                "selection": reference_info["selection"],
                "policy": reference_info["policy"],
                "weighting": reference_info["weighting"],
                "max_weighted_cdf_distance": reference_info[
                    "max_weighted_cdf_distance"
                ],
            },
            factors=sorted(factors, key=lambda f: -abs(f["contribution"])),
            limitations=[
                "Đóng góp giải thích dự báo, không chứng minh nguyên nhân hoặc hiệu quả liên hệ thu nợ.",
                "Độ ổn định chỉ đo độ nhạy với mẫu nền, không phải độ tin cậy của xác suất dự báo.",
                "Kiểm tra tổ hợp đầu vào là chẩn đoán hỗ trợ dữ liệu, không bảo đảm mọi tổ hợp đều thực tế.",
            ]
            + (
                ["Chỉ có một hóa đơn tham chiếu nên chưa có khác biệt để phân rã."]
                if len(opened) == 1
                else []
            ),
        )
    return snapshot
