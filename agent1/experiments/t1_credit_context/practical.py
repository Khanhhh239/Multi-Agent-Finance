"""B2B context from tenant-owned, dated records; no simulated macro input.

This is an input adapter, not a trained model or a production integration.
Missing records become unknown. No first-invoice-date inference, World lookup,
cross-tenant customer history, or automatic access to a public registry.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .features import INDUSTRIES, INDUSTRY_FEATURES


PRACTICAL_CONTEXT_FEATURES = list(INDUSTRY_FEATURES)
SOURCE_KINDS = {
    "buyer": {"customer_master", "customer_supplied", "verified_registry_extract"},
    "seller": {"own_company_profile", "verified_registry_extract"},
}


def _dates(values):
    dates = pd.to_datetime(values, errors="raise", format="mixed")
    if dates.isna().any():
        raise ValueError("An actual knowledge timestamp is required")
    # Internally use Vietnam local wall time, including for aware source stamps.
    if dates.dt.tz is not None:
        dates = dates.dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None)
    return dates


def _industry_as_of(keys, observations, side):
    entity = ["firm_id", "customer_id"] if side == "buyer" else ["firm_id"]
    if observations is None:
        return pd.Series("unknown", index=keys.index)
    expected = {*entity, "industry", "known_at", "source_kind", "source_ref"}
    if set(observations) != expected:
        raise ValueError("Industry observations require tenant keys, actual known_at and source provenance only")
    if observations.empty:
        return pd.Series("unknown", index=keys.index)
    observations = observations.copy()
    for name in (*entity, "source_kind", "source_ref"):
        if observations[name].isna().any() or observations[name].astype(str).str.strip().eq("").any():
            raise ValueError("Missing industry key or provenance")
    if not observations.source_kind.isin(SOURCE_KINDS[side]).all():
        raise ValueError("Synthetic or unsupported industry source")
    observations["known_at"] = _dates(observations.known_at)
    if observations.duplicated([*entity, "known_at"]).any():
        raise ValueError("Conflicting industry observations at the same knowledge time")
    # A revision learned later must not replace an earlier classification in
    # historical snapshots. An explicit unknown revision also replaces old data.
    left = keys[[*entity, "cutoff"]].assign(_row=np.arange(len(keys)))
    matched = pd.merge_asof(
        left.sort_values("cutoff"), observations.sort_values("known_at"),
        left_on="cutoff", right_on="known_at", by=entity, direction="backward",
    ).sort_values("_row")
    return matched.industry.where(matched.industry.isin(INDUSTRIES), "unknown").reset_index(drop=True)


def practical_context_features(keys, *, buyer_observations=None, seller_observations=None):
    """Return 14 industry indicators in input row order, using actual records.

    known_at is when this tenant first had this version of the classification,
    not incorporation date, invoice date, or a backdated business effective date.
    source_ref identifies a supplied record/extract; it is not fetched here.
    The caller supplies an already verified mapping to the six-category taxonomy.
    Unmapped activities and absent records remain unknown.
    """
    if set(keys) != {"firm_id", "customer_id", "cutoff"}:
        raise ValueError("Only tenant/customer keys and forecast cutoff are accepted")
    data = keys.reset_index(drop=True).copy()
    if data[["firm_id", "customer_id"]].isna().any().any():
        raise ValueError("Missing tenant/customer key")
    for name in ("firm_id", "customer_id"):
        if data[name].astype(str).str.strip().eq("").any():
            raise ValueError("Empty tenant/customer key")
    data["cutoff"] = _dates(data.cutoff)
    result = pd.DataFrame(index=data.index)
    for side, observations in (("buyer", buyer_observations), ("seller", seller_observations)):
        industry = _industry_as_of(data, observations, side)
        for name in (*INDUSTRIES, "unknown"):
            result[f"{side}_industry_{name}"] = industry.eq(name).astype(float)
    result.index = keys.index
    return result[PRACTICAL_CONTEXT_FEATURES]
