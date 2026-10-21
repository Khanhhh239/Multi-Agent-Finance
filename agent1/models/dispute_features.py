"""Lịch sử tranh chấp đóng băng tại ngày lập HĐ, không cập nhật bằng kết quả chính HĐ."""
from agent1.models.t3_features import issue_features


def at_issue_dispute_rates(invoices):
    return issue_features(invoices).set_index('invoice_id')['c_disp_eb']


def add_dispute_rates(frame, rates):
    result = frame.copy()
    result['c_disp_eb'] = result.invoice_id.map(rates)
    if result.c_disp_eb.isna().any():
        raise ValueError('Thiếu lịch sử tranh chấp tại ngày lập của hoá đơn')
    return result
