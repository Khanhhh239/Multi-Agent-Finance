"""Controlled Vietnamese observations for the fifteen existing v4 features.

Does not introduce a detector, change scores, or attribute causality to a model.
Evidence describes an observation requiring human review, never a person.
"""
from __future__ import annotations

import math
import json

from .explain_check import check

V4_REASONS = {
    "receipt_payer_mismatch": "Tài khoản trả tiền khác tài khoản đã đăng ký của khách trên phiếu thu.",
    "receipt_days_late": "Khoản thu được ghi nhận trễ {value:.0f} ngày so với hạn thanh toán tham chiếu.",
    "collector_late_trend_90d": "Các khoản thu trước của người thu tiền có độ trễ trung bình {value:.1f} ngày trong {window:.0f} ngày.",
    "payee_not_on_master": "Tài khoản nhận tiền không có trong danh mục nhà cung cấp hoặc các thay đổi tài khoản đã được ghi nhận.",
    "payroll_after_leave": "Lương được đăng khi hồ sơ đã ghi nhận việc nghỉ của nhân viên; cần đối chiếu quyết toán hợp lệ.",
    "payroll_off_calendar": "Ngày đăng lương nằm ngoài khoảng ngày trả lương tham chiếu của công ty.",
    "payroll_rows_same_month": "Nhân viên đã có {value:.0f} dòng lương trước đó trong cùng tháng.",
    "writeoff_overdue_days": "Khi xóa nợ, hóa đơn đang mở lâu nhất của khách đã quá hạn {value:.0f} ngày.",
    "refund_to_foreign_account": "Tài khoản nhận hoàn tiền khác tài khoản đã đăng ký của khách.",
    # The feature code uses fallback ratios when the denominator is absent.
    # Do not present these fallbacks as measured percentages.
    "return_vs_recent_sales": "Khoản hoàn hàng cần được đối chiếu với hóa đơn bán và doanh số hai tháng trước của khách.",
    "writeoff_vs_cogs_90d": "Khoản hủy hàng cần được đối chiếu với giá vốn ba tháng trước và biên bản kiểm kê.",
    "creator_writeoffs_90d": "Người lập đã ghi {value:.0f} khoản hủy hàng trong {window:.0f} ngày trước.",
    "offquarter_writeoff": "Khoản hủy hàng được đăng ngoài cửa sổ cuối quý của phép kiểm tra; cần xác minh lịch kiểm kê thực tế.",
    "customer_amount_logz": "Số tiền hóa đơn bán cao so với lịch sử hóa đơn của chính khách này.",
    "self_approved_advance_ratio": "Người nhận tự lập và tự duyệt tạm ứng; số tiền bằng {value:.0%} hạn mức duyệt tham chiếu.",
}


def observations(row, features=None):
    """Render supported positive observations, optionally restricted by signal names.

    The caller selects signals to explain. A positive observation alone is not an
    alert threshold and does not claim that a learned model relied on the field.
    """
    out = []
    for name in features if features is not None else V4_REASONS:
        if name == "writeoff_recency":
            name = "writeoff_overdue_days"
        if name not in V4_REASONS:
            continue
        try:
            value = float(row.get(name, 0))
        except (ValueError, TypeError):
            continue
        if not math.isfinite(value) or value == 0:
            continue
        evidence = {name: value}
        template = V4_REASONS[name]
        if name == "writeoff_overdue_days" and value < 0:
            template = "Khi xóa nợ, hóa đơn đang mở lâu nhất còn {value:.0f} ngày mới đến hạn tham chiếu."
            value = -value
            evidence = {"days_until_due": value}
        elif value < 0:
            continue
        if name in ("collector_late_trend_90d", "creator_writeoffs_90d"):
            evidence["history_window_days"] = 90
        text = template.format(value=value, window=90)
        result = check(text, evidence)
        if not result["ok"]:
            raise ValueError(f"template evidence mismatch: {name}: {result}")
        out.append({"feature": name, "text": text, "evidence": evidence})
    return out


def rule_observations(row):
    from sme_fraud.rules import RULE_NAMES
    raw = row.get("rule_evidence_json", "{}")
    evidence_by_rule = json.loads(raw) if isinstance(raw, str) else raw
    out = []
    for name in str(row.get("rule_ids", "")).split("|"):
        if name not in RULE_NAMES or name not in evidence_by_rule:
            continue
        evidence = evidence_by_rule[name]
        if name in ("A1", "A2"):
            required = ("count", "window_days", "total_vnd", "approval_limit_vnd")
            if not all(k in evidence for k in required):
                continue
            scope = "cùng người nhận" if name == "A1" else "cùng người lập và người nhận"
            text = (f"Có {evidence['count']:.0f} khoản {scope} trong {evidence['window_days']:.0f} ngày; "
                    f"tổng {evidence['total_vnd']:.0f} đồng so với hạn mức {evidence['approval_limit_vnd']:.0f} đồng.")
        elif name == "C3":
            if "approval_seconds" not in evidence:
                continue
            text = f"Giao dịch có mức thẩm quyền cao được duyệt trong {evidence['approval_seconds']:.1f} giây."
        else:
            text = RULE_NAMES[name] + "; cần đối chiếu bằng chứng gốc."
        if check(text, evidence)["ok"]:
            out.append({"feature": f"rule:{name}", "text": text, "evidence": evidence})
    return out


def entity_observations(row, parts):
    """Existing baseline signals, using measured row values rather than tail ranks."""
    out = []
    for name, tail in sorted(parts.items(), key=lambda pair: -pair[1]):
        if tail < 4 or name in V4_REASONS or name == "writeoff_recency":
            continue
        if name in ("price_logratio", "price_shift3", "p_logratio", "p_logratio_bonus", "cu_logratio"):
            source = "p_logratio" if name == "p_logratio_bonus" else name
            value = float(row.get(source, 0))
            if value <= 0 or not math.isfinite(value) or value > 20:
                continue
            ratio = math.expm1(value)
            lead = {"price_logratio": "Đơn giá cao hơn", "price_shift3": "Đơn giá ba lần mua trước cao hơn",
                    "p_logratio": "Khoản lương ngoài tháng thưởng cao hơn", "p_logratio_bonus": "Khoản lương trong tháng thưởng cao hơn",
                    "cu_logratio": "Số tiền nghiệp vụ của người lập cao hơn"}[name]
            text = f"{lead} {ratio:.0%} so với mức tham chiếu lịch sử tương ứng."
            evidence = {"relative_increase": ratio}
        elif name in ("near_dup_30d", "near_dup_other_invoice_30d", "creator_cash_near_selflimit_30d", "creator_unsupported_selfcash_30d"):
            count = float(row.get(name, 0))
            if count <= 0:
                continue
            lead = {"near_dup_30d": "khoản gần trùng số tiền của cùng nhà cung cấp",
                    "near_dup_other_invoice_30d": "khoản gần trùng số tiền nhưng khác hóa đơn của cùng nhà cung cấp",
                    "creator_cash_near_selflimit_30d": "khoản chi tiền mặt sát hạn mức của người lập",
                    "creator_unsupported_selfcash_30d": "khoản chi tiền mặt tự duyệt thiếu chứng từ của người lập"}[name]
            text = f"Lịch sử có {count:.0f} {lead} trong 30 ngày trước."
            evidence = {name: count, "history_window_days": 30}
        else:
            lead = {"price_logz": "Đơn giá lệch rõ so với biến động lịch sử của nhà cung cấp.",
                    "amount_selflimit_ratio": "Khoản chi tiền mặt tự duyệt cần được đối chiếu với hạn mức tham chiếu.",
                    "v_days_dormant_amount": "Khoản thanh toán cho nhà cung cấp cần đối chiếu với khoảng gián đoạn giao dịch trước đó."}
            if name not in lead:
                continue
            text, evidence = lead[name], {"tail_score": float(tail)}
        if check(text, evidence)["ok"]:
            out.append({"feature": name, "text": text, "evidence": evidence})
    return out
