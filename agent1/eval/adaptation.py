"""Thống kê cặp DA từ tổng theo công ty; cùng cohort và mẫu số tiền thật."""
import numpy as np
import pandas as pd
from agent1.eval.cluster import ratio_ci


def paired_improvement(company, model, baseline, metric='pinball_sum'):
    left = company[company.model == model].set_index('firm_id')
    right = company[company.model == baseline].set_index('firm_id')
    if set(left.index) != set(right.index) or not len(left):
        raise ValueError('Hai mô hình phải có cùng tập công ty không rỗng')
    left = left.reindex(right.index)
    if not np.array_equal(left.n.to_numpy(), right.n.to_numpy()):
        raise ValueError('Số hàng hai cohort không khớp')
    numerator = right[metric].to_numpy() - left[metric].to_numpy()
    denominator = right[metric].to_numpy()
    if denominator.sum() <= 0:
        raise ValueError('Tổn thất mốc phải dương')
    ci = ratio_ci(numerator, denominator)
    return dict(improvement_pct=100*numerator.sum()/denominator.sum(),
                improvement_ci_low=100*ci['ci_low'], improvement_ci_high=100*ci['ci_high'],
                n_firms=ci['n_firms'], bootstrap_n=ci['bootstrap_n'])


def company_statistics(frame, quantiles, pmf):
    from agent1.models.t1 import CAP, QS, collections_by_week
    error = np.minimum(frame.remaining.to_numpy(), CAP)[:, None] - quantiles
    loss = np.maximum(np.asarray(QS)*error, (np.asarray(QS)-1)*error).mean(1)
    result = pd.DataFrame(dict(firm_id=frame.firm_id.to_numpy(), loss=loss)).groupby('firm_id').agg(
        pinball_sum=('loss','sum'), n=('loss','size'))
    cash = collections_by_week(frame, pmf)
    cash['firm_id'] = cash.index.astype(str).str.split('|', n=1).str[0]
    cash['abs_error'] = np.abs(cash.pred - cash.act)
    for suffix, mask in [('w1_4',cash.k<=4), ('w5_13',cash.k>4)]:
        sums = cash.loc[mask].groupby('firm_id')[['abs_error','act']].sum()
        result[f'cash_error_{suffix}'] = sums.abs_error
        result[f'cash_actual_{suffix}'] = sums.act
    return result.reset_index()
