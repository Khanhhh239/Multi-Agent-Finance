"""Đo T8 theo tuần: chỉ các lời hứa đã xác minh tại cutoff được làm lịch sử."""
import numpy as np
import pandas as pd

from agent1.models.t8_promise import PromiseReliability


def resolved_history(promises, cutoff):
    cutoff = pd.Timestamp(cutoff)
    mask = (promises.made_date <= cutoff) & (promises.promised_date + pd.Timedelta(days=3) <= cutoff)
    if 'resolved_date' in promises:
        mask &= promises.resolved_date.notna() & (promises.resolved_date <= cutoff)
    return promises.loc[mask & promises.kept.notna()].copy()


def predict_week(promises, query, cutoff):
    """Query chỉ cung cấp định danh; không đọc kết quả, ngày hứa hoặc số tiền tương lai."""
    history = resolved_history(promises, cutoff)
    customers = query[['customer_id', 'firm_id']].reset_index(drop=True)
    model = PromiseReliability().fit(promises, cutoff)
    learned = model.predict(customers).reliability.to_numpy()
    rates = history.groupby('customer_id').kept.mean()
    firms = history.groupby('firm_id').kept.agg(['sum', 'count'])
    prior = (firms['sum'] + 4) / (firms['count'] + 6)
    fallback = customers.firm_id.map(prior).fillna(4 / 6)
    customer_rate = customers.customer_id.map(rates).fillna(fallback).to_numpy(float)
    return {'Customer historical rate': customer_rate,
            'Firm Beta prior': fallback.to_numpy(float),
            'T8 hierarchical recency EB': np.asarray(learned, float)}
