"""Temporal and information-boundary tests for the isolated context prototype."""
import numpy as np
import pandas as pd
import pytest

from agent1.synth.shocks import ShockEpisode
from experiments.t1_credit_context.features import CONTEXT_FEATURES, context_features, credit_as_of
from experiments.t1_credit_context.observations import SurveyDesign, simulate_releases


def reports(episodes=(), end="2024-10-31"):
    return simulate_releases(episodes, "2024-01-01", end)


def test_future_episode_and_horizon_cannot_change_past_measurements():
    base = reports(end="2024-06-30")
    future = ShockEpisode(family="credit", start="2024-07-01", severity=1.1)
    extended = reports([future])
    pd.testing.assert_frame_equal(base, extended.iloc[:len(base)].reset_index(drop=True))


def test_release_and_ingestion_both_precede_feature_availability():
    data = reports()
    # Jan report: published Feb 15, ingested Feb 16.
    assert credit_as_of(data, "2024-02-15")["macro_credit_missing"] == 1
    assert credit_as_of(data, "2024-02-16")["macro_credit_missing"] == 0
    assert credit_as_of(data, "2024-02-16")["macro_credit_age_days"] == 16


def test_july_shock_cannot_reach_either_july_anchor():
    episode = ShockEpisode(family="credit", start="2024-07-01", severity=1.1)
    calm, shocked = reports(), reports([episode])
    for day in ("2024-07-01", "2024-07-29"):
        assert credit_as_of(calm, day) == credit_as_of(shocked, day)
    assert credit_as_of(calm, "2024-08-26")["macro_credit_restricted_share"] != credit_as_of(shocked, "2024-08-26")["macro_credit_restricted_share"]


def test_future_measurement_mutation_does_not_change_past_feature():
    data = reports()
    altered = data.copy()
    altered.loc[altered.ingested_at.gt("2024-06-01"), "restricted_share"] = 1.
    assert credit_as_of(data, "2024-06-01") == credit_as_of(altered, "2024-06-01")


def test_stale_and_small_sample_reports_are_missing_not_calm():
    data = reports(end="2024-01-31")
    assert credit_as_of(data, "2024-05-01")["macro_credit_missing"] == 1
    data["respondents"] = 2
    result = credit_as_of(data, "2024-02-16")
    assert result["macro_credit_missing"] == 1
    assert np.isnan(result["macro_credit_restricted_share"])


def test_delta_requires_adjacent_released_months():
    data = reports()
    first = credit_as_of(data, "2024-02-16")
    assert first["macro_credit_delta_missing"] == 1
    later = credit_as_of(data, "2024-03-16")
    assert later["macro_credit_delta_missing"] == 0
    gapped = data[data.period_end.ne(pd.Timestamp("2024-02-29"))]
    assert credit_as_of(gapped, "2024-04-16")["macro_credit_delta_missing"] == 1


@pytest.mark.parametrize("mutation", ["latent", "early", "duplicate", "bad_share"])
def test_consumer_rejects_invalid_or_latent_release_data(mutation):
    data = reports()
    if mutation == "latent":
        data["shock_truth"] = 1
    elif mutation == "early":
        data.loc[0, "published_at"] = data.loc[0, "period_start"]
    elif mutation == "duplicate":
        data = pd.concat([data, data.iloc[:1]], ignore_index=True)
    else:
        data.loc[0, "restricted_share"] = 1.5
    with pytest.raises(ValueError):
        credit_as_of(data, "2024-04-01")


def test_industry_requires_knowledge_date_and_never_has_numeric_order():
    keys = pd.DataFrame({"firm_id": ["f", "f"], "customer_id": ["c", "c"],
                         "cutoff": pd.to_datetime(["2024-04-01", "2024-05-01"])})
    buyer = pd.DataFrame({"customer_id": ["c"], "industry": ["services"], "known_at": ["2024-04-15"]})
    seller = pd.DataFrame({"firm_id": ["f"], "industry": ["steel_metals"], "known_at": ["2024-01-01"]})
    result = context_features(keys, reports(), buyer, seller)
    assert list(result) == CONTEXT_FEATURES
    assert result.buyer_industry_unknown.tolist() == [1, 0]
    assert result.buyer_industry_services.tolist() == [0, 1]
    assert result.filter(like="buyer_industry_").sum(axis=1).eq(1).all()
    assert result.filter(like="seller_industry_").sum(axis=1).eq(1).all()
    with pytest.raises(ValueError):
        context_features(keys.assign(default_date="2025-01-01"), reports(), buyer, seller)
    with pytest.raises(ValueError):
        context_features(keys, reports(), buyer.assign(credit_exposure=2), seller)


def test_survey_has_measurement_error_and_never_invents_sector_resolution():
    data = reports()
    assert data.restricted_share.nunique() > 1  # noise even under constant calm state
    assert data.respondents.between(30, 127).all()
    targeted = ShockEpisode(family="credit", start="2024-07-01", industries=("services",))
    with pytest.raises(ValueError, match="sampling design"):
        reports([targeted])
    with pytest.raises(ValueError):
        SurveyDesign(release_error_sd=0)
