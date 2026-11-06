"""Paired T1/baseline scores on observed, complete horizon follow-up.

No short-follow-up event is preferentially included. Noncash-censored rows
contribute only before censoring. These conditional scores do not estimate
outcomes after an informative noncash change and are not pilot acceptance.
"""
import numpy as np


def horizon_metrics(frame, cdf, baseline_cdf, horizons=(7, 28, 56, 91)):
    cdf, baseline_cdf = np.asarray(cdf, float), np.asarray(baseline_cdf, float)
    if cdf.shape != (len(frame), 13) or baseline_cdf.shape != cdf.shape:
        raise ValueError('T1 evaluation requires 13 weekly cumulative probabilities per row')
    for values in (cdf, baseline_cdf):
        if not np.isfinite(values).all() or (values < 0).any() or (values > 1).any() or (np.diff(values, axis=1) < -1e-12).any():
            raise ValueError('Invalid cumulative probabilities')
    if not len(frame):
        remaining, event, observation, amounts = (np.array([]) for _ in range(4))
    else:
        remaining = frame.remaining.to_numpy(float)
        event = frame.event.to_numpy(int)
        observation = frame.obs_window.to_numpy(float)
        amounts = frame.amount_open.to_numpy(float)
        if (not np.isfinite(observation).all() or (observation < 0).any()
                or not np.isfinite(amounts).all() or (amounts < 0).any()):
            raise ValueError('Invalid observation window or amount at risk')
    scores = {}
    for horizon in horizons:
        if horizon % 7 or not 7 <= horizon <= 91:
            raise ValueError('Evaluation horizon must be a weekly boundary within 91 days')
        complete = observation >= horizon
        target = ((event == 1) & (remaining <= horizon))[complete].astype(float)
        weights = amounts[complete]
        result = dict(n=int(complete.sum()), paid=int(target.sum()),
                      not_paid=int(len(target)-target.sum()),
                      excluded_short_followup=int((~complete).sum()))
        for name, values in (('model', cdf), ('baseline', baseline_cdf)):
            p = values[complete, horizon//7-1]
            result[name] = dict(
                brier=float(np.mean((p-target)**2)) if len(p) else None,
                amount_weighted_brier=float(np.average((p-target)**2, weights=weights)) if weights.sum() > 0 else None,
                mean_probability=float(p.mean()) if len(p) else None,
                observed_rate=float(target.mean()) if len(p) else None,
            )
        scores[str(horizon)] = result
    return dict(validation_rows=len(frame), resolved_only=False,
                evaluation='complete_followup_by_horizon_v1', horizons=scores)
