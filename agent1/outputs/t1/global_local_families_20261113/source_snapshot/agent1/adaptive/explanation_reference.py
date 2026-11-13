"""Reproducible, invoice-weighted backgrounds and sampling diagnostics for T1.

All choices use inputs available at cutoff, never settlement outcomes. Sampling
weights preserve each stratum's share of the open invoice population. Diagnostic
thresholds are engineering tolerances, not statistical confidence guarantees.
"""

import hashlib

import numpy as np

FULL_COHORT_LIMIT = 512
SAMPLE_SIZE = 128
AUDIT_SEEDS = (101, 211, 307)
MIN_AUDIT_POPULATION = 16
STRATIFY_COLUMNS = (5, 1, 0, 4, 2)  # age, term, log amount, history count/delay
POLICY = "open-invoices-stratified-v2"


def _strata(values):
    """Partition the joint feature space; do not form sparse Cartesian bins."""
    scale = np.std(values, axis=0)
    scaled = (values - np.mean(values, axis=0)) / np.where(scale > 0, scale, 1)
    groups = [np.arange(len(values))]
    if len(values) > FULL_COHORT_LIMIT:
        # Reserve strata for extreme amounts and cold-start customers. Pure
        # median splits can miss small, financially meaningful tail segments.
        remaining = groups.pop()
        low, high = np.quantile(values[:, 2], [0.01, 0.99])
        for condition in (values[:, 2] <= low, values[:, 2] >= high, values[:, 3] == 0):
            take = condition[remaining]
            if take.any() and not take.all():
                groups.append(remaining[take])
                remaining = remaining[~take]
        groups.append(remaining)
    limit = min(16, max(1, len(values) // 16))
    while len(groups) < limit:
        candidates = []
        for position, group in enumerate(groups):
            for column in range(values.shape[1]):
                unique, counts = np.unique(values[group, column], return_counts=True)
                if len(unique) < 2:
                    continue
                boundary = np.argmin(abs(counts.cumsum()[:-1] - len(group) / 2))
                left = values[group, column] <= unique[boundary]
                gain = len(group) * np.var(scaled[group, column])
                candidates.append((gain, position, column, left))
        if not candidates:
            break
        _, position, _, left = max(candidates, key=lambda item: item[:3])
        group = groups.pop(position)
        groups.extend((group[left], group[~left]))
    return groups


def _sample(groups, size, seed):
    counts = np.array([len(group) for group in groups])
    allocation = np.ones(len(groups), dtype=int)
    # Proportional allocation after one slot per stratum; cap at its population.
    while allocation.sum() < size:
        ideal = size * counts / counts.sum()
        eligible = allocation < counts
        priority = np.where(eligible, ideal - allocation, -np.inf)
        allocation[np.argmax(priority)] += 1
    rng = np.random.default_rng(seed)
    indices, weights = [], []
    for group, take in zip(groups, allocation):
        chosen = np.sort(rng.choice(group, int(take), replace=False))
        indices.extend(chosen.tolist())
        weights.extend([len(group) / counts.sum() / take] * int(take))
    return np.asarray(indices), np.asarray(weights)


def reference_plan(invoice_ids, encoded):
    """Return a union of reference rows and weights for primary + audit games.

    Sort by a fixed hash only to remove dependence on input order. Strata and
    weighted random samples, rather than invoice ID spacing, determine selection.
    Small cohorts use a census; subset audits measure sensitivity to its makeup.
    """
    n = len(invoice_ids)
    if not n:
        raise ValueError("Không có hóa đơn để chọn nền giải thích")
    order = np.array(
        sorted(
            range(n),
            key=lambda i: (
                hashlib.sha256(str(invoice_ids[i]).encode()).hexdigest(),
                str(invoice_ids[i]),
            ),
        )
    )
    values = np.asarray(encoded)[order][:, STRATIFY_COLUMNS]
    groups = _strata(values)
    census = n <= FULL_COHORT_LIMIT
    primary = (
        (np.arange(n), np.full(n, 1 / n))
        if census
        else _sample(groups, SAMPLE_SIZE, 17)
    )
    samples = [primary]
    seeds = [None if census else 17]
    if n >= MIN_AUDIT_POPULATION:
        size = min(SAMPLE_SIZE, int(np.ceil(n * 0.8)))
        for seed in AUDIT_SEEDS:
            samples.append(_sample(groups, size, seed))
            seeds.append(seed)
    union = np.unique(np.concatenate([indices for indices, _ in samples]))
    weights = np.zeros((len(union), len(samples)))
    definitions = []
    for column, ((indices, mass), seed) in enumerate(zip(samples, seeds)):
        positions = np.searchsorted(union, indices)
        weights[positions, column] = mass
        definitions.append(
            {
                "role": "primary" if column == 0 else "sensitivity",
                "seed": seed,
                "positions": positions.tolist(),
                "weights": mass.tolist(),
            }
        )
    distances = []
    for column in range(values.shape[1]):
        grid = np.unique(values[:, column])
        pop = np.searchsorted(np.sort(values[:, column]), grid, side="right") / n
        indices, mass = primary
        sequence = np.argsort(values[indices, column], kind="stable")
        locations = np.searchsorted(
            values[indices[sequence], column], grid, side="right"
        )
        sample = np.r_[0, mass[sequence].cumsum()][locations]
        distances.append(float(np.max(abs(pop - sample))))
    info = {
        "policy": POLICY,
        "selection": "census" if census else "weighted_stratified_sample",
        "population": n,
        "count": len(primary[0]),
        "weighting": "equal_per_open_invoice",
        "strata_population": [len(group) for group in groups],
        "stratify_features": [
            "age_days",
            "term_days",
            "amount",
            "customer_history_count",
            "customer_delay_days",
        ],
        "max_weighted_cdf_distance": max(distances),
        "cdf_distances": dict(
            zip(
                [
                    "age_days",
                    "term_days",
                    "amount",
                    "customer_history_count",
                    "customer_delay_days",
                ],
                distances,
            )
        ),
        "audit_sample_count": len(samples) - 1,
        "audit_kind": "stratified_subset_sensitivity"
        if census
        else "repeated_stratified_sampling",
        "sample_sets": definitions,
        "invoice_ids": [str(invoice_ids[order[i]]) for i in union],
    }
    return order[union], weights, info


class HybridSupport:
    """Flag broken history constraints and unseen bins of correlated pairs.

    This is a conservative support diagnostic, not a learned conditional masker
    and not proof that a hybrid input is realistic or causal.
    """

    def __init__(self, population):
        self.pairs = []
        spread = np.std(population, axis=0)
        varying = np.flatnonzero(spread > 1e-10)
        if len(population) < MIN_AUDIT_POPULATION or len(varying) < 2:
            return
        correlation = np.corrcoef(population[:, varying], rowvar=False)
        for a, left in enumerate(varying):
            for b in range(a + 1, len(varying)):
                right = varying[b]
                if abs(correlation[a, b]) < 0.8:
                    continue
                cuts = [
                    np.unique(np.quantile(population[:, j], [0.25, 0.5, 0.75]))
                    for j in (left, right)
                ]
                bins = [
                    np.searchsorted(cut, population[:, j], side="right")
                    for j, cut in zip((left, right), cuts)
                ]
                supported = np.zeros((len(cuts[0]) + 1, len(cuts[1]) + 1), bool)
                supported[bins[0], bins[1]] = True
                self.pairs.append((left, right, cuts, supported))

    def unsupported(self, hybrids):
        missing_history = np.isclose(hybrids[:, 4], 0, atol=1e-10)
        invalid = missing_history & ~np.isclose(
            hybrids[:, 2], hybrids[:, 3], atol=1e-8, rtol=0
        )
        for left, right, cuts, supported in self.pairs:
            a = np.searchsorted(cuts[0], hybrids[:, left], side="right")
            b = np.searchsorted(cuts[1], hybrids[:, right], side="right")
            invalid |= ~supported[a, b]
        return invalid


def stability_report(primary, audits, population):
    """Per-feature sensitivity; ranges are not prediction confidence intervals."""
    values = np.concatenate([primary[None], audits], axis=0) * 100
    lo, hi = values.min(0), values.max(0)
    delta = np.max(abs(values - values[0]), axis=0)
    meaningful = np.max(abs(values), axis=0) >= 0.1
    sign_flip = (lo < -1e-8) & (hi > 1e-8) & (hi - lo >= 0.1)
    magnitude = delta > np.maximum(0.5, 0.25 * abs(values[0]))
    strongest = int(np.argmax(abs(primary)))
    top_agreement = [
        abs(value[strongest]) >= np.max(abs(value)) - 0.1 for value in values[1:]
    ]
    checked = len(audits) >= 3 and population >= MIN_AUDIT_POPULATION
    result = []
    for column in range(len(primary)):
        reasons = []
        if sign_flip[column]:
            reasons.append("direction_changed")
        if magnitude[column]:
            reasons.append("magnitude_changed")
        if column == strongest and meaningful[column] and not all(top_agreement):
            reasons.append("top_feature_changed")
        status = "insufficient" if not checked else "unstable" if reasons else "stable"
        result.append(
            {
                "status": status,
                "reasons": reasons,
                "min_contribution_pp": float(lo[column]),
                "max_contribution_pp": float(hi[column]),
                "max_change_pp": float(delta[column]),
                "meaningful": bool(meaningful[column]),
            }
        )
    return result, {
        "checked": checked,
        "sample_count": len(audits),
        "top_feature_agreement": float(np.mean(top_agreement))
        if top_agreement
        else None,
        "sign_change_tolerance_pp": 0.1,
        "absolute_change_tolerance_pp": 0.5,
        "relative_change_tolerance": 0.25,
        "scope": "background_sampling_sensitivity_only",
    }
