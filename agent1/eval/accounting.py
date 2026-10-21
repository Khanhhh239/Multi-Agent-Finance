"""Tỷ số kế toán mô tả, không phải kỳ thu tiền ước lượng từ một hoá đơn."""
import numpy as np


def accounting_days(opening,closing,annual_flow,days_basis=365.):
    values=np.asarray([opening,closing,annual_flow,days_basis],float)
    if not np.isfinite(values).all() or (values<0).any() or annual_flow<=0 or days_basis<=0:
        raise ValueError('Số dư phải không âm, doanh số và số ngày phải dương hữu hạn')
    return float((opening+closing)/2/annual_flow*days_basis)
