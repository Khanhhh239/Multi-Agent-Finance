"""Event policy, weekly risk sets and coherent competing-risk probabilities."""
from __future__ import annotations

import numpy as np
import pandas as pd

from agent1.models import t1

OPEN, PAID, WRITEOFF = 0, 1, 2
WEEKS = 53


def label_first_event(frame: pd.DataFrame, label_end) -> pd.DataFrame:
    """Attach first-event time/cause; no terminal credit cancellation is hidden."""
    end = pd.Timestamp(label_end)
    cutoff = pd.to_datetime(frame["cutoff"])
    paid = pd.to_datetime(frame["label_date"])
    written = pd.to_datetime(frame["writeoff_date"])
    if "closure_type" in frame and frame["closure_type"].eq("credit_note").any():
        raise ValueError("credit_note-only closure needs a fourth terminal cause")
    if (paid.notna() & written.notna()).any():
        raise ValueError("Paid and write-off dates coexist for one invoice")
    if ((paid.notna() & (paid <= cutoff)) | (written.notna() & (written <= cutoff))).any():
        raise ValueError("Closed invoice appeared in an open snapshot")
    if (cutoff > end).any():
        raise ValueError("Snapshot after administrative label end")
    obs = (end - cutoff).dt.days.to_numpy(dtype=np.int32)
    paid_days = (paid - cutoff).dt.days.to_numpy(dtype=float)
    writeoff_days = (written - cutoff).dt.days.to_numpy(dtype=float)
    event_days = np.where(np.isfinite(paid_days), paid_days, writeoff_days)
    event_days = np.where(np.isfinite(event_days), event_days, np.inf)
    event_type = np.where(np.isfinite(paid_days), PAID,
                          np.where(np.isfinite(writeoff_days), WRITEOFF, OPEN)).astype(np.int8)
    within = event_days <= obs
    result = frame.copy()
    result["obs_days"] = obs
    result["time_days"] = np.minimum(event_days, obs).astype(np.int32)
    result["cause"] = np.where(within, event_type, OPEN).astype(np.int8)
    if (result.time_days < 0).any():
        raise ValueError("Negative time to event")
    return result


def week_matrix(frame: pd.DataFrame, week: int, feats: list[str]) -> np.ndarray:
    if week < 1 or week > WEEKS:
        raise ValueError("Week outside v5 horizon")
    x = frame[feats].to_numpy(dtype=np.float32)
    week_values = t1._week_feats(frame, week)
    if "days_to_promised" not in feats:
        week_values["promised_in_k"] = np.full(len(frame), np.nan)
    w = np.column_stack([week_values[name] for name in t1.WEEK_FEATS]).astype(np.float32)
    return np.hstack((x, w))


def expand_weekly(frame: pd.DataFrame, feats: list[str]) -> tuple[np.ndarray, np.ndarray, dict]:
    """Keep only fully observed weeks while open at the week's start."""
    t1.validate_feature_columns(feats)
    parts, labels = [], []
    counts = {"open": 0, "paid": 0, "writeoff": 0}
    time = frame.time_days.to_numpy(dtype=np.int32)
    obs = frame.obs_days.to_numpy(dtype=np.int32)
    cause = frame.cause.to_numpy(dtype=np.int8)
    for week in range(1, WEEKS + 1):
        left, right = 7 * (week - 1), 7 * week
        selected = (time > left) & (obs >= right)
        if not selected.any():
            continue
        x = week_matrix(frame.loc[selected], week, feats)
        y = np.where((time[selected] <= right) & (cause[selected] == PAID), PAID,
                     np.where((time[selected] <= right) & (cause[selected] == WRITEOFF),
                              WRITEOFF, OPEN)).astype(np.int8)
        parts.append(x)
        labels.append(y)
        counts["open"] += int((y == OPEN).sum())
        counts["paid"] += int((y == PAID).sum())
        counts["writeoff"] += int((y == WRITEOFF).sum())
    if not parts:
        raise ValueError("No complete weekly risk sets")
    return np.vstack(parts), np.concatenate(labels), counts


def predict_hazards(booster, frame: pd.DataFrame, feats: list[str]) -> np.ndarray:
    hazards = np.empty((len(frame), WEEKS, 3), dtype=np.float32)
    for week in range(1, WEEKS + 1):
        hazards[:, week - 1, :] = booster.predict(week_matrix(frame, week, feats))
    if not np.isfinite(hazards).all() or (hazards < 0).any() or \
            not np.allclose(hazards.sum(axis=2), 1, atol=2e-6):
        raise ValueError("Invalid weekly class probabilities")
    return hazards


def cumulative_incidence(hazards: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return paid CIF, write-off CIF and still-open probability at each week."""
    h = np.asarray(hazards, dtype=float)
    if h.ndim != 3 or h.shape[2] != 3 or not np.isfinite(h).all() or \
            (h < 0).any() or not np.allclose(h.sum(axis=2), 1, atol=2e-6):
        raise ValueError("Hazards must be n × weeks × [open, paid, writeoff]")
    open_probability = np.ones(len(h), dtype=float)
    fp = np.empty((len(h), h.shape[1]), dtype=float)
    fw = np.empty_like(fp)
    so = np.empty_like(fp)
    paid = np.zeros(len(h), dtype=float)
    written = np.zeros(len(h), dtype=float)
    for week in range(h.shape[1]):
        paid += open_probability * h[:, week, PAID]
        written += open_probability * h[:, week, WRITEOFF]
        open_probability *= h[:, week, OPEN]
        fp[:, week], fw[:, week], so[:, week] = paid, written, open_probability
    if not np.allclose(fp + fw + so, 1, atol=3e-6):
        raise ValueError("Cumulative incidences do not conserve probability")
    return fp, fw, so


def observed_state(frame: pd.DataFrame, day: int) -> np.ndarray:
    if (frame.obs_days < day).any():
        raise ValueError("Outcome horizon extends beyond administrative observation")
    occurred = frame.time_days.to_numpy() <= day
    return np.where(occurred, frame.cause.to_numpy(), OPEN).astype(np.int8)


def aalen_johansen(frame: pd.DataFrame, horizons: list[int]) -> list[dict]:
    """Nonparametric first-event CIF with right censoring at obs_days."""
    if not horizons or min(horizons) < 0:
        raise ValueError("Invalid AJ horizons")
    time = frame.time_days.to_numpy(dtype=int)
    cause = frame.cause.to_numpy(dtype=int)
    dates = np.unique(time[cause != OPEN])
    n = len(frame)
    fp = fw = 0.0
    so = 1.0
    step = []
    for day in dates:
        risk = int((time >= day).sum())
        d_paid = int(((time == day) & (cause == PAID)).sum())
        d_written = int(((time == day) & (cause == WRITEOFF)).sum())
        if risk < d_paid + d_written:
            raise ValueError("Event count exceeds risk set")
        old_so = so
        fp += old_so * d_paid / risk
        fw += old_so * d_written / risk
        so *= 1 - (d_paid + d_written) / risk
        step.append((day, risk, d_paid, d_written, fp, fw, so))
    output = []
    for horizon in horizons:
        earlier = [row for row in step if row[0] <= horizon]
        if earlier:
            _, _, _, _, paid, written, opened = earlier[-1]
        else:
            paid, written, opened = 0.0, 0.0, 1.0
        output.append({"day": int(horizon), "aj_paid": float(paid),
                       "aj_writeoff": float(written), "aj_open": float(opened),
                       "n_at_risk_at_day": int((time >= horizon).sum())})
    return output
