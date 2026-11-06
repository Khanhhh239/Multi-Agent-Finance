"""Four-state event labels, coherent hazards and finite-horizon quantiles."""
from __future__ import annotations

import numpy as np
import pandas as pd

from agent1.models import t1
from .features import validate_features

OPEN, PAID, WRITEOFF, CREDIT = range(4)
STATE_NAMES = ("open", "paid", "writeoff", "credit_note")
WEEKS = 53


def label_events(frame, label_end):
    result = frame.copy()
    cutoff = pd.to_datetime(frame.cutoff)
    end = pd.Timestamp(label_end)
    paid = pd.to_datetime(frame.label_date)
    written = pd.to_datetime(frame.writeoff_date)
    credit = pd.to_datetime(frame.credit_note_date).where(frame.closure_type.eq("credit_note"))
    dates = pd.concat([paid, written, credit], axis=1)
    if dates.notna().sum(axis=1).gt(1).any():
        raise ValueError("Conflicting terminal dates; post-writeoff recoveries are unsupported")
    if (frame.closure_type.eq("credit_note") & credit.isna()).any():
        raise ValueError("Credit-only closure lacks a dated credit note")
    if cutoff.gt(end).any() or dates.le(cutoff, axis=0).any(axis=None):
        raise ValueError("Closed invoice or invalid cutoff in risk set")
    event_date = dates.min(axis=1)
    days = (event_date - cutoff).dt.days.to_numpy(float)
    days = np.where(np.isfinite(days), days, np.inf)
    cause = np.where(paid.notna(), PAID, np.where(written.notna(), WRITEOFF, np.where(credit.notna(), CREDIT, OPEN)))
    obs = (end - cutoff).dt.days.to_numpy(int)
    result["obs_days"] = obs
    result["time_days"] = np.minimum(days, obs).astype(np.int32)
    result["cause"] = np.where(days <= obs, cause, OPEN).astype(np.int8)
    return result


def week_matrix(frame, week, features):
    validate_features(features)
    if not 1 <= week <= WEEKS:
        raise ValueError("Week outside v6 risk horizon")
    weekly = t1._week_feats(frame, week)
    return np.hstack((frame[features].to_numpy(np.float32), np.column_stack([weekly[n] for n in t1.WEEK_FEATS]).astype(np.float32)))


def expand_weekly(frame, features):
    matrices, labels = [], []
    times, obs, causes = (frame[n].to_numpy(int) for n in ("time_days", "obs_days", "cause"))
    for week in range(1, WEEKS + 1):
        left, right = 7 * (week - 1), 7 * week
        keep = (times > left) & (obs >= right)
        if not keep.any():
            continue
        matrices.append(week_matrix(frame.loc[keep], week, features))
        labels.append(np.where(times[keep] <= right, causes[keep], OPEN).astype(np.int8))
    if not matrices:
        raise ValueError("No fully observed weekly risk rows")
    return np.vstack(matrices), np.concatenate(labels)


def validate_hazards(hazards):
    h = np.asarray(hazards, dtype=float)
    if h.ndim != 3 or h.shape[2] != 4 or not np.isfinite(h).all() or (h < 0).any() or not np.allclose(h.sum(axis=2), 1, atol=2e-6):
        raise ValueError("Invalid four-state hazards")
    return h


def predict_hazards(booster, frame, features, active_causes):
    result = np.zeros((len(frame), WEEKS, 4), dtype=np.float32)
    for week in range(1, WEEKS + 1):
        probability = booster.predict(week_matrix(frame, week, features), num_threads=4)
        for column, cause in enumerate(active_causes):
            result[:, week - 1, cause] = probability[:, column]
    validate_hazards(result)
    return result


def cumulative_states(hazards):
    h = validate_hazards(hazards)
    survival = np.cumprod(h[:, :, OPEN], axis=1)
    previous = np.column_stack((np.ones(len(h)), survival[:, :-1]))
    result = np.zeros_like(h)
    result[:, :, OPEN] = survival
    result[:, :, 1:] = np.cumsum(previous[:, :, None] * h[:, :, 1:], axis=1)
    if not np.allclose(result.sum(axis=2), 1, atol=3e-6):
        raise ValueError("Cumulative probabilities do not sum to one")
    return result


def state_at_day(hazards, day):
    h = validate_hazards(hazards)
    if not 0 <= day <= h.shape[1] * 7:
        raise ValueError("Day outside fitted horizon")
    full, partial = divmod(int(day), 7)
    states = cumulative_states(h)
    previous = np.zeros((len(h), 4))
    previous[:, OPEN] = 1
    if full:
        previous = states[:, full - 1, :].copy()
    if not partial:
        return previous
    current = h[:, full, :]
    fraction = 1 - np.power(current[:, OPEN], partial / 7)
    total = current[:, 1:].sum(axis=1)
    proportions = np.divide(current[:, 1:], total[:, None], out=np.zeros_like(current[:, 1:]), where=total[:, None] > 0)
    remaining = previous[:, OPEN].copy()
    previous[:, 1:] += remaining[:, None] * fraction[:, None] * proportions
    previous[:, OPEN] = remaining * (1 - fraction)
    return previous


def observed_state(frame, day):
    if frame.obs_days.lt(day).any():
        raise ValueError("Outcome is not fully observed at this horizon")
    return np.where(frame.time_days.to_numpy() <= day, frame.cause.to_numpy(), OPEN).astype(int)


def paid_quantiles(hazards, quantiles=(0.1, 0.5, 0.9), max_day=365):
    h = validate_hazards(hazards)
    if not 0 < max_day <= 7 * h.shape[1]:
        raise ValueError("Invalid quantile horizon")
    cumulative = cumulative_states(h)
    at_end = state_at_day(h, max_day)[:, PAID]
    output = {}
    for q in quantiles:
        if not 0 < q < 1:
            raise ValueError("Invalid quantile probability")
        result = np.full(len(h), np.nan)
        reached = at_end >= q
        for index in np.flatnonzero(reached):
            week = int(np.argmax(cumulative[index, :, PAID] >= q))
            before = 0.0 if week == 0 else cumulative[index, week - 1, PAID]
            opened = 1.0 if week == 0 else cumulative[index, week - 1, OPEN]
            paid_share = h[index, week, PAID] / max(1e-15, 1 - h[index, week, OPEN])
            proportion = np.clip((q - before) / max(1e-15, opened * paid_share), 0, 1)
            stay = h[index, week, OPEN]
            days = 0.0 if stay == 0 else 7 * np.log1p(-min(proportion, 1 - 1e-15)) / np.log(stay)
            result[index] = min(max_day, 7 * week + days)
        output[f"q{round(q * 100)}_days"] = result
        output[f"q{round(q * 100)}_status"] = np.where(reached, "reached", f"not_reached_by_{max_day}")
    return output


def cash_matrix(frame, features, day):
    validate_features(features)
    return np.column_stack((frame[features].to_numpy(np.float32), np.full(len(frame), day, np.float32)))


def predict_cash_fraction(booster, frame, features, horizons):
    values = np.column_stack([booster.predict(cash_matrix(frame, features, day), num_threads=4) for day in horizons])
    return np.maximum.accumulate(np.clip(values, 0, 1), axis=1)
