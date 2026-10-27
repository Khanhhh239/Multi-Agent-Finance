"""Exogenous weekly episodes and private buyer/seller exposure.

The coefficients below are synthetic scenario assumptions, not estimates of
Vietnamese firms' response to historical events.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


FAMILIES = ('demand', 'supply', 'price', 'credit')


@dataclass(frozen=True)
class ShockEpisode:
    family: str
    start: str
    rise_weeks: int = 2
    peak_weeks: int = 4
    recovery_weeks: int = 8
    severity: float = 1.0
    industries: tuple[str, ...] = ()
    regions: tuple[int, ...] = ()
    reference_event: str = 'synthetic_assumption'

    def __post_init__(self):
        if self.family not in FAMILIES:
            raise ValueError(f'Unknown shock family: {self.family}')
        if self.rise_weeks < 1 or self.peak_weeks < 1 or self.recovery_weeks < 2:
            raise ValueError('Shock needs rise, peak and observable recovery weeks')
        if not np.isfinite(self.severity) or self.severity < 0 or self.severity > 3:
            raise ValueError('Shock severity must be finite and in [0, 3]')
        pd.Timestamp(self.start)


def episode_path(episode: ShockEpisode, weeks: pd.DatetimeIndex) -> np.ndarray:
    """A causal, finite rise / peak / recovery path, zero outside its episode."""
    first = pd.Timestamp(episode.start)
    if first.weekday():
        raise ValueError('Shock episode must start on a Monday')
    age = ((weeks - first).days // 7).to_numpy()
    rise, peak, recovery = episode.rise_weeks, episode.peak_weeks, episode.recovery_weeks
    shape = np.zeros(len(weeks), dtype=float)
    climbing = (age >= 0) & (age < rise)
    shape[climbing] = (age[climbing] + 1) / rise
    shape[(age >= rise) & (age < rise + peak)] = 1.
    falling = (age >= rise + peak) & (age < rise + peak + recovery)
    shape[falling] = 1. - (age[falling] - rise - peak + 1) / recovery
    return episode.severity * np.maximum(shape, 0.)


def exposed(episode: ShockEpisode, entity: dict) -> bool:
    return ((not episode.industries or entity['industry'] in episode.industries) and
            (not episode.regions or entity['region'] in episode.regions))


def exposure_vectors(episodes, paths, entity, weeks):
    """Private channel pressure for one buyer or seller over the common weeks."""
    result = {family: np.zeros(weeks, dtype=float) for family in FAMILIES}
    for episode, path in zip(episodes, paths):
        if exposed(episode, entity):
            result[episode.family] += path * entity[f'{episode.family}_exposure']
    return result
