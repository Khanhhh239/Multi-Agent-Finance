"""Chọn ngưỡng từ cửa sổ nguồn và chấm cảnh báo theo sự kiện, không đếm lặp mỗi tuần."""
import numpy as np
import pandas as pd


def choose_threshold(y, p, cost_ratio=5):
    y, p = np.asarray(y, bool), np.asarray(p, float)
    thresholds = np.linspace(0, 1, 101)
    costs = [cost_ratio * np.mean(y & (p < tau)) + np.mean(~y & (p >= tau)) for tau in thresholds]
    ix = int(np.argmin(costs))
    return float(thresholds[ix]), float(costs[ix])


def event_metrics(predictions, daily_cash, *, threshold, probability='p13', horizon_days=91):
    detected, leads, false_alarms, exposure, n_events = [], [], 0, 0., 0
    for fid, pred in predictions.groupby('firm_id'):
        pred = pred.sort_values('cutoff')
        cash = daily_cash[daily_cash.firm_id == fid].sort_values('date')
        negative = cash.balance < 0
        starts = cash.loc[negative & ~negative.shift(fill_value=False), 'date']
        start, end = pred.cutoff.min(), pred.cutoff.max() + pd.Timedelta(days=7)
        events = starts[(starts > start) & (starts <= end)]
        alarms = pred.loc[pred[probability] >= threshold, 'cutoff']
        # Gộp các tuần cảnh báo liên tục thành một đợt cảnh báo.
        episodes = alarms[(alarms.diff().dt.days > 7) | alarms.diff().isna()]
        for event in events:
            prior = alarms[(alarms < event) & (alarms >= event - pd.Timedelta(days=horizon_days))]
            lead = (event - prior.min()).days / 7 if len(prior) else 0.
            leads.append(lead); detected.append(lead >= 4); n_events += 1
        for warning in episodes:
            future = cash[(cash.date > warning) & (cash.date <= warning + pd.Timedelta(days=horizon_days))]
            if len(future) and (future.balance >= 0).all():
                false_alarms += 1
        exposure += max((end - start).days / 365.25, 1e-9)
    return dict(n_events=n_events, detected_at_least_4w=float(np.mean(detected)) if detected else np.nan,
                median_lead_weeks=float(np.median(leads)) if leads else np.nan,
                false_alarms_per_firm_year=false_alarms / max(exposure, 1e-9))
