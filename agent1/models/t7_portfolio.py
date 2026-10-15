"""Bằng chứng chung của nhiều bộ phát hiện và danh mục; không dùng cảnh báo tương lai."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .t7_changepoint import cusum, page_hinkley, bocpd


def consensus_alarms(dates, z, raw=None, *, window_days=30, cooldown_days=30):
    dates = pd.DatetimeIndex(dates)
    if not dates.is_monotonic_increasing:
        raise ValueError('Chuỗi phải sắp theo thời gian')
    raw_alarms = {'CUSUM': cusum(z), 'PH': page_hinkley(z), 'BOCPD': bocpd(z)}
    events = sorted((dates[i], name) for name, indices in raw_alarms.items() for i in indices)
    history, confirmed = {}, []
    last = pd.Timestamp.min
    for when, detector in events:
        history[detector] = when
        support = sum(when - d <= pd.Timedelta(days=window_days) for d in history.values())
        if support >= 2 and (not confirmed or when - last >= pd.Timedelta(days=cooldown_days)):
            confirmed.append(when); last = when
    return pd.DatetimeIndex(confirmed)


def portfolio_stream(residuals):
    """Đầu vào (firm_id, customer_id, date, z) đã tính PIT as-of; mỗi khách một phiếu/tuần."""
    data = residuals.copy()
    data['week'] = data['date'].dt.to_period('W-SUN').dt.start_time
    per_customer = data.groupby(['firm_id', 'week', 'customer_id']).z.mean()
    return per_customer.groupby(['firm_id', 'week']).agg(z='mean', n='size').reset_index()


class RegimeController:
    def __init__(self, gamma=.01, quiet_days=84):
        self.base_gamma, self.quiet_days = gamma, quiet_days
        self.state, self.last_alarm, self.last_update = 'normal', None, None

    def update(self, T, *, portfolio_alarm=False, confirmed_customers=0):
        T = pd.Timestamp(T)
        if self.last_update is not None and T < self.last_update:
            raise ValueError('Không được cập nhật ngược thời gian')
        self.last_update = T
        if portfolio_alarm or confirmed_customers >= 2:
            self.state, self.last_alarm = 'crisis', T
        elif confirmed_customers:
            self.state, self.last_alarm = 'alert', T
        elif self.last_alarm is not None and (T - self.last_alarm).days >= self.quiet_days:
            self.state = 'normal'
        return dict(state=self.state, ewm_halflife=30 if self.state == 'crisis' else 90,
                    aci_gamma=self.base_gamma * (3 if self.state == 'crisis' else 1),
                    retrain_window_weeks=12 if self.state == 'crisis' else None)
