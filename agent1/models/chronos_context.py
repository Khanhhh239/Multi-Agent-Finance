"""Ngữ cảnh số dư tuần chỉ tới cutoff; không nhập Torch vào dịch vụ mặc định."""
import numpy as np
import pandas as pd


def balance_context(series,cutoff,weeks=52):
    cutoff=pd.Timestamp(cutoff)
    observed=series[series.index<=cutoff]
    dates=pd.date_range(end=cutoff,periods=weeks,freq='7D')
    result=observed.reindex(dates).to_numpy(float)
    if not np.isfinite(result).all():raise ValueError('Thiếu số dư quan sát ở ngữ cảnh tuần')
    return result
