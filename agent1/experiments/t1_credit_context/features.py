"""Point-in-time consumer of released observations and dated industry records.

No import of the producer, generator, shock scenarios or oracle annotations.
Returned columns alone are candidate estimator inputs; identifiers and release
metadata remain outside this view. This module is not wired into v6.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


INDUSTRIES = ("steel_metals", "textile_clothing", "plastic_rubber", "wholesale", "food_processing", "services")
CREDIT_FEATURES = ["macro_credit_restricted_share", "macro_credit_delta", "macro_credit_age_days",
                   "macro_credit_missing", "macro_credit_delta_missing"]
INDUSTRY_FEATURES = [f"{side}_industry_{name}" for side in ("buyer", "seller") for name in (*INDUSTRIES, "unknown")]
CONTEXT_FEATURES = CREDIT_FEATURES + INDUSTRY_FEATURES
REQUIRED_RELEASES = {"series_id", "period_start", "period_end", "published_at", "ingested_at", "restricted_share", "respondents"}


def validated_releases(releases):
    if set(releases) != REQUIRED_RELEASES:
        raise ValueError("Release schema must contain only registered observation columns")
    data = releases.copy()
    for name in ("period_start", "period_end", "published_at", "ingested_at"):
        data[name] = pd.to_datetime(data[name], errors="raise")
        if data[name].isna().any():
            raise ValueError("Missing release date")
    if (not data.series_id.eq("synthetic_credit_restriction_survey_v1").all()
            or data.period_end.duplicated().any()
            or (data.period_start > data.period_end).any()
            or (data.published_at <= data.period_end).any()
            or (data.ingested_at < data.published_at).any()):
        raise ValueError("Invalid release sequence or chronology")
    shares = pd.to_numeric(data.restricted_share, errors="raise")
    counts = pd.to_numeric(data.respondents, errors="raise")
    if (not counts.ge(0).all() or not np.isfinite(counts).all() or counts.mod(1).ne(0).any()
            or (shares.notna() & ~shares.between(0, 1)).any()):
        raise ValueError("Invalid survey measurement")
    data["restricted_share"], data["respondents"] = shares, counts
    return data.sort_values("period_end")


def credit_as_of(releases, cutoff, *, max_age_days=62, min_respondents=30):
    data = validated_releases(releases)
    cutoff = pd.Timestamp(cutoff)
    if pd.isna(cutoff) or max_age_days < 1 or min_respondents < 1:
        raise ValueError("Invalid as-of policy")
    visible = data[(data.ingested_at <= cutoff) & (data.period_end <= cutoff)]
    result = dict(zip(CREDIT_FEATURES, [np.nan, np.nan, np.nan, 1., 1.]))
    if visible.empty:
        return result
    latest = visible.iloc[-1]
    age = (cutoff - latest.period_end).days
    if age > max_age_days or latest.respondents < min_respondents or pd.isna(latest.restricted_share):
        return result
    result.update(macro_credit_restricted_share=float(latest.restricted_share),
                  macro_credit_age_days=float(age), macro_credit_missing=0.)
    if len(visible) >= 2:
        previous = visible.iloc[-2]
        # Delta means adjacent months, never an arbitrary gap between reports.
        adjacent = latest.period_end.to_period("M") - 1 == previous.period_end.to_period("M")
        if adjacent and previous.respondents >= min_respondents and pd.notna(previous.restricted_share):
            result.update(macro_credit_delta=float(latest.restricted_share - previous.restricted_share),
                          macro_credit_delta_missing=0.)
    return result


def context_features(keys, releases, buyer_registry, seller_registry):
    """keys: firm_id/customer_id/cutoff; registries: id/industry/known_at.

    Static classification is usable only from its explicitly recorded knowledge
    date. Unknown/unavailable categories get their own indicator. Reclassification
    and revised releases require a separately versioned observation contract.
    """
    if set(keys) != {"firm_id", "customer_id", "cutoff"}:
        raise ValueError("Pass keys only, never labels or latent snapshot columns")
    data = keys.reset_index(drop=True).copy()
    data["cutoff"] = pd.to_datetime(data.cutoff, errors="raise")
    if data.isna().any().any():
        raise ValueError("Missing context key")
    result = pd.DataFrame(index=data.index, columns=CONTEXT_FEATURES, dtype=float)
    for cutoff, idx in data.groupby("cutoff").groups.items():
        result.loc[idx, CREDIT_FEATURES] = list(credit_as_of(releases, cutoff).values())
    for side, key, registry in (("buyer", "customer_id", buyer_registry), ("seller", "firm_id", seller_registry)):
        if set(registry) != {key, "industry", "known_at"} or registry[key].isna().any() or registry[key].duplicated().any():
            raise ValueError("Industry registry needs unique keys and dated observations only")
        registry = registry.copy()
        registry["known_at"] = pd.to_datetime(registry.known_at, errors="raise")
        if registry.known_at.isna().any():
            raise ValueError("Missing industry knowledge date")
        registry = registry.set_index(key)
        industry = data[key].map(registry.industry)
        known = data[key].map(registry.known_at)
        industry = industry.where(known.le(data.cutoff) & industry.isin(INDUSTRIES), "unknown")
        for name in (*INDUSTRIES, "unknown"):
            result[f"{side}_industry_{name}"] = industry.eq(name).astype(float)
    return result[CONTEXT_FEATURES]
