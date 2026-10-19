"""Accounting templates for the transaction kinds added in world v4 (friend's module left untouched on disk).

New kinds (simplified TT133/TT200 postings, scenario templates only, not tax advice):
  sales_return        Nợ 511 / Có 131   giảm trừ doanh thu cho hàng bán bị trả lại, giảm giá (ghi giảm trực tiếp)
  customer_refund     Nợ 131 / Có 112   hoàn tiền cho khách
  bad_debt_writeoff   Nợ 642 (hoặc 2293) / Có 131   xóa nợ phải thu không thu hồi được
  inventory_writeoff  Nợ 632 / Có 156 (155, 152)  xuất hủy, hao hụt hàng tồn kho
  cash_withdrawal     Nợ 111 / Có 112   rút tiền gửi ngân hàng về quỹ tiền mặt
"""
from __future__ import annotations

import sme_fraud.accounting as acc

NEW_KINDS = {"sales_return": ("511", "131"), "customer_refund": ("131", "112"), "bad_debt_writeoff": ("642", "131"),
             "inventory_writeoff": ("632", "156"), "cash_withdrawal": ("111", "112")}
MONEY_KINDS = {"customer_refund", "cash_withdrawal"}
_original = acc.pair_supported


def pair_supported_v4(debit, credit, purpose, framework):
    if purpose in NEW_KINDS:
        admin = acc.expense_account(framework)
        rules = {"sales_return": {("511", "131")}, "customer_refund": {("131", "112")},
                 "bad_debt_writeoff": {(admin, "131"), ("2293", "131")},
                 "inventory_writeoff": {("632", "156"), ("632", "155"), ("632", "152"), (admin, "156")},
                 "cash_withdrawal": {("111", "112")}}[purpose]
        return acc.account_supported(debit, framework) and acc.account_supported(credit, framework) and (debit, credit) in rules
    return _original(debit, credit, purpose, framework)


def install():
    acc.pair_supported = pair_supported_v4
    import sme_fraud.audit_accounting as audit
    audit.pair_supported = pair_supported_v4
    # Register the same five explicit kinds with scalar validation without
    # changing generate.PAIRS or the feature-column contract shared by v2/v3.
    import sme_fraud.exception_validation as validation
    validation.PAIRS = {**validation.PAIRS, **NEW_KINDS}


def check_accounting_v4(tables):
    """Run the friend's accounting audit; money kinds are presented as cash movements to its type-specific checks."""
    install()
    from sme_fraud.audit_accounting import check_accounting
    shadow = dict(tables)
    shadow["transactions"] = [dict(r, txn_type="cash_expense") if r["txn_type"] in MONEY_KINDS else r for r in tables["transactions"]]
    return check_accounting(shadow)


install()
