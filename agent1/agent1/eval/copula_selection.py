"""Khoá chọn copula bằng điểm nguồn, không cho trộn kết quả miền đích."""
import pandas as pd
import numpy as np


def select_copulas(scores,*,test_origin):
    required={'world','outcome_end','rho','rho_customer','IS80'}
    if not required<=set(scores) or scores.empty:raise ValueError('Thiếu điểm hiệu chỉnh nguồn')
    if set(scores.world)!={'src'}:raise ValueError('Chỉ chọn copula trên nguồn')
    end=pd.to_datetime(scores.outcome_end)
    if end.isna().any() or (end>pd.Timestamp(test_origin)-pd.Timedelta(days=120)).any():
        raise ValueError('Hiệu chỉnh phải tách test ít nhất 120 ngày')
    if not np.isfinite(scores[['rho','rho_customer','IS80']].to_numpy()).all():raise ValueError('Điểm không hữu hạn')
    if ((scores.rho<0)|(scores.rho_customer<0)|(scores.rho+scores.rho_customer>1)).any():raise ValueError('Phương sai copula không hợp lệ')
    mean=scores.groupby(['rho','rho_customer'],as_index=False).IS80.mean().sort_values(['IS80','rho_customer','rho'])
    one=mean[mean.rho_customer==0]
    if one.empty:raise ValueError('Thiếu mốc một nhân tố')
    best_one=one.iloc[0];best_joint=mean.iloc[0]
    return {'source_selected_one_factor':(float(best_one.rho),0.),
        'source_selected_hierarchical':(float(best_joint.rho),float(best_joint.rho_customer))}
