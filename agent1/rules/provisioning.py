"""Gợi ý sàn tuổi nợ theo lịch sử TT48; chưa phải bút toán tự động."""
import numpy as np
import pandas as pd
from . import load_rules


def suggest_provision(invoices, T, *, p_bad=None):
    T = pd.Timestamp(T)
    out = invoices[invoices.issue_date <= T].copy()
    due = pd.to_datetime(out.due_date)
    thresholds = load_rules(T)['provisioning_months']
    rates = np.zeros(len(out))
    for months, rate in thresholds:
        rates = np.where(due + pd.DateOffset(months=months) <= T, rate, rates)
    if 'paid_date_est' in out:
        settled = out.paid_date_est.notna() & (out.paid_date_est <= T)
        rates[settled] = 0.
    amount = out.amount_open if 'amount_open' in out else out.amount_gross
    out['provision_floor_rate'] = rates
    out['provision_floor_amount'] = amount * rates
    out['requires_accountant_review'] = True
    if p_bad is not None:
        prob = np.asarray(p_bad, float)
        if len(prob) != len(out):
            raise ValueError('p_bad phải khớp hoá đơn as-of')
        out['early_model_warning'] = prob > rates
    return out
