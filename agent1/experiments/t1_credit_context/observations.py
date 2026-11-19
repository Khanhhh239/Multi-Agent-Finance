"""Hypothetical survey producer. Only this simulation layer sees shock scenarios.

This creates NEW observations under an explicit measurement assumption, not
historical public data. It does not read shock_truth, defaults, private buyer
exposures, outcomes, or estimator inputs. Existing World generation is untouched.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from agent1.synth.shocks import episode_path


SERIES = "synthetic_credit_restriction_survey_v1"
RELEASE_COLUMNS = [
    "series_id", "period_start", "period_end", "published_at", "ingested_at",
    "restricted_share", "respondents",
]


@dataclass(frozen=True)
class SurveyDesign:
    panel_size: int = 128
    response_probability: float = 0.8
    baseline_logit: float = -2.0
    pressure_loading: float = 1.2
    respondent_sd: float = 0.4
    release_error_sd: float = 0.25
    publication_lag_days: int = 15
    ingestion_lag_days: int = 1
    seed: int = 20261105

    def __post_init__(self):
        if self.panel_size < 30 or not 0 < self.response_probability <= 1:
            raise ValueError("Invalid survey panel")
        numeric = (self.baseline_logit, self.pressure_loading, self.respondent_sd, self.release_error_sd)
        if not np.isfinite(numeric).all() or self.pressure_loading <= 0 or min(numeric[2:]) <= 0:
            raise ValueError("A noisy, finite measurement model is required")
        if self.publication_lag_days < 1 or self.ingestion_lag_days < 0 or self.seed < 0:
            raise ValueError("Invalid release timing or seed")


def national_credit_pressure(episodes, dates):
    """Generator/audit only: credit pressure for calendar dates, before exposure.

    Current v4 credit episodes are nationwide. Refuse to silently interpret a
    future targeted episode as a national/sector indicator.
    """
    dates = pd.DatetimeIndex(dates)
    if dates.empty:
        return np.array([], dtype=float)
    mondays = dates - pd.to_timedelta(dates.weekday, unit="D")
    values = np.zeros(len(dates))
    for episode in episodes:
        if episode.family == "credit":
            if episode.industries or episode.regions:
                raise ValueError("Targeted credit needs an explicit survey sampling design")
            values += episode_path(episode, mondays)
    return values


def simulate_releases(episodes, start, end, design=SurveyDesign()):
    """One report per completed calendar month, with stable per-period RNG.

    Extending the horizon or adding future episodes cannot change past reports.
    A fixed independent panel has respondent heterogeneity, nonresponse,
    release-level measurement error, and Bernoulli response noise.
    """
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if pd.isna(start) or pd.isna(end) or end < start:
        raise ValueError("Invalid survey observation interval")
    episodes = tuple(episodes)
    panel_rng = np.random.default_rng(np.random.SeedSequence([design.seed, 101]))
    respondent_effect = panel_rng.normal(0, design.respondent_sd, design.panel_size)
    rows = []
    for period in pd.period_range(start, end, freq="M"):
        first, last = period.start_time.normalize(), period.end_time.normalize()
        if first < start or last > end:
            continue
        pressure = national_credit_pressure(episodes, pd.date_range(first, last)).mean()
        rng = np.random.default_rng(np.random.SeedSequence([design.seed, period.year, period.month, 102]))
        error = rng.normal(0, design.release_error_sd)
        logits = design.baseline_logit + respondent_effect + design.pressure_loading * pressure + error
        probability = 1 / (1 + np.exp(-np.clip(logits, -50, 50)))
        responding = rng.random(design.panel_size) < design.response_probability
        reports = rng.random(design.panel_size) < probability
        n = int(responding.sum())
        published = last + pd.Timedelta(days=design.publication_lag_days)
        rows.append([SERIES, first, last, published,
                     published + pd.Timedelta(days=design.ingestion_lag_days),
                     float(reports[responding].mean()) if n else np.nan, n])
    return pd.DataFrame(rows, columns=RELEASE_COLUMNS)


def design_dict(design):
    return {"series_id": SERIES, **asdict(design)}
