"""Không bỏ tuần hết AR: vẫn có số dư đầu kỳ, doanh thu mới và lịch chi."""
import numpy as np
from agent1.models.t1 import pmf_from_hazard
from agent1.models.t6_cash import K


def forecast_pmf(model,snapshot):
    return np.empty((0,K)) if snapshot.empty else pmf_from_hazard(model.hazards(snapshot))[0]


def validate_cash_cohort(frame,n_firms,n_origins,n_models):
    keys=['firm_id','cutoff','model','k']
    expected=n_firms*n_origins*n_models*K
    if len(frame)!=expected or frame.duplicated(keys).any():raise ValueError('Thiếu/trùng tuần dự báo, kể cả tuần hết AR')
    if frame.firm_id.nunique()!=n_firms or frame.model.nunique()!=n_models:raise ValueError('Sai số DN/mô hình')
    if not frame.groupby(['firm_id','model']).size().eq(n_origins*K).all():raise ValueError('Cohort DN thiếu tuần')
