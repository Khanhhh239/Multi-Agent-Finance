"""Controlled Vietnamese observations for the v5 change features and EntityDeviation2 detectors.

Same contract as explain_v4: every number in a sentence comes from the row's measured value (checked by
`explain_check.check`); a sentence describes an observation to verify, never a person or a conclusion.
Detectors are named as in `change_detect.ED2_SPECS` with a side suffix ('+' right tail, '-' left tail).
"""
from __future__ import annotations

import math

from .explain_check import check

MIN_TAIL = 4.0          # same reporting threshold as the v4 entity reasons (tail probability about 1.8 percent)


def _ratio(log_value):
    return math.expm1(log_value)


def _sentence(detector, row):
    """Return (text, evidence) for one detector, or None when the measured value does not support it."""
    feat, side = detector[:-1], detector[-1]
    value = float(row.get(feat, 0) or 0)
    if not math.isfinite(value) or value == 0:
        return None
    if feat == "pay_lr":
        r = _ratio(value)
        word = "cao hơn" if value > 0 else "thấp hơn"
        return (f"Lương kỳ đầu tháng {word} {abs(r):.0%} so với trung vị các kỳ trước của chính nhân viên.",
                {"relative_change": abs(r)})
    if feat == "pay_cusum_up":
        return ("Lương của nhân viên cao hơn mức tham chiếu của chính họ ở nhiều kỳ liên tiếp; cần đối chiếu quyết định "
                "điều chỉnh lương.", {})
    if feat == "pay_shift" and value > 0:
        return (f"Mức lương ba kỳ gần nhất cao hơn {_ratio(value):.0%} so với các kỳ trước đó của nhân viên.",
                {"relative_increase": _ratio(value)})
    if feat == "grp_pay_up_n" and value > 0:
        return (f"Trong 35 ngày trước, {value:.0f} người do cùng người lập bảng lương đã được tăng lương trên 5%; "
                "cần đối chiếu quyết định tăng lương chung.",
                {"employees": value, "window_days": 35, "threshold": .05})
    if feat == "price_lr2" and value > 0:
        return (f"Đơn giá cao hơn {_ratio(value):.0%} so với trung vị sáu lần mua gần nhất của nhà cung cấp.",
                {"relative_increase": _ratio(value), "history_purchases": 6})
    if feat == "price_cusum_up":
        return ("Đơn giá của nhà cung cấp cao hơn mức tham chiếu ở nhiều lần mua liên tiếp; cần đối chiếu báo giá "
                "và hợp đồng.", {})
    if feat == "price_slope6" and value > 0:
        return ("Đơn giá của nhà cung cấp có xu hướng tăng đều qua các lần mua gần nhất.", {})
    if feat == "cust_z":
        if side == "-" and value < 0:
            return ("Số tiền hóa đơn bán thấp bất thường so với lịch sử hóa đơn của chính khách này; cần đối chiếu "
                    "chính sách chiết khấu và hợp đồng.", {})
        if side == "+" and value > 0:
            return ("Số tiền hóa đơn bán cao bất thường so với lịch sử hóa đơn của chính khách này.", {})
        return None
    if feat == "cust_cusum_dn":
        return ("Các hóa đơn gần đây cho cùng khách liên tục thấp hơn mức thường lệ của khách.", {})
    if feat == "ar_cust_overdue_n" and value > 0:
        return (f"Khi lập hóa đơn mới, khách đang có {value:.0f} hóa đơn quá hạn chưa thu.", {"overdue_invoices": value})
    if feat == "ar_mgr_overdue_share" and value > 0:
        return (f"{value:.0%} số hóa đơn đang mở do cùng người lập phụ trách đã quá hạn thanh toán.", {"share": value})
    if feat == "ar_creator_reversal_share" and value > 0:
        return (f"{value:.0%} số hóa đơn người lập phát hành trong 180 ngày trước đã bị trả hàng hoặc xóa nợ.",
                {"share": value, "window_days": 180})
    if feat == "ar_reversal_unpaid" and value > 0:
        return ("Hóa đơn bị trả hàng hoặc xóa nợ chưa từng được thu tiền; cần đối chiếu việc giao hàng thực tế.", {})
    if feat == "ar_reversal_age_days" and value > 0:
        return (f"Hóa đơn được trả hàng hoặc xóa nợ sau {value:.0f} ngày kể từ khi lập.", {"days": value})
    if feat == "rec_excess" and value > 0:
        return (f"Số khoản cùng loại trong 35 ngày qua nhiều hơn nhịp hằng tháng thường lệ của công ty {value:.1f} khoản.",
                {"excess": value, "window_days": 35})
    if feat == "rec_amount_lr" and value > 0:
        return (f"Số tiền cao hơn {_ratio(value):.0%} so với trung vị các khoản cùng loại trước đó của công ty.",
                {"relative_increase": _ratio(value)})
    if feat == "rec_new_counterparty" and value > 0:
        return ("Khoản chi định kỳ được trả cho đối tượng chưa từng nhận khoản cùng loại trước đây.", {})
    if feat == "adv_open_n" and value > 0:
        return (f"Nhân viên đang có {value:.0f} khoản tạm ứng chưa quyết toán khi nhận tạm ứng mới.",
                {"open_advances": value})
    if feat == "adv_growth" and value > 0:
        return (f"Tạm ứng mới cao hơn {_ratio(value):.0%} so với lần tạm ứng trước của cùng nhân viên.",
                {"relative_increase": _ratio(value)})
    return None


def change_observations(row, parts, min_tail=MIN_TAIL, top=2):
    """Strongest EntityDeviation2 detectors first; only sentences whose numbers pass the fidelity check."""
    out = []
    for detector, tail in sorted(parts.items(), key=lambda kv: -kv[1]):
        if tail < min_tail or len(out) >= top:
            continue
        made = _sentence(detector, row)
        if made is None:
            continue
        text, evidence = made
        result = check(text, evidence)
        if not result["ok"]:
            raise ValueError(f"template evidence mismatch: {detector}: {result}")
        out.append({"feature": detector, "text": text, "evidence": evidence, "tail": float(tail)})
    return out
