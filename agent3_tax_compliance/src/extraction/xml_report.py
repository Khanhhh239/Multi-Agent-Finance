"""Reviewer-facing summary of XML invoice checks, grouped in plain Vietnamese.

Group statuses: OK (every check ran and passed), REVIEW (a deviation a human must look at), FAIL (a check failed),
UNAVAILABLE (no legitimate data channel or not enough history; never reported as OK). FAIL outranks REVIEW outranks UNAVAILABLE.
"""
from .xml_context import STORED_PREFIXES
from .xml_invoice import extract

GROUPS = (
    ('amounts', 'Số tiền', ('XML_CHECK_ARITH_', 'XML_CHECK_WORDS', 'XML_CHECK_TOTALS_PRESENT', 'XML_CHECK_VAT_RATE')),
    ('invoice', 'Thông tin hóa đơn', ('XML_CHECK_SYMBOL', 'XML_CHECK_DATE', 'XML_CHECK_NUMBER', 'XML_CHECK_AUTHORITY_CODE', 'XML_CHECK_DUPLICATE')),
    ('related', 'Hóa đơn thay thế hoặc điều chỉnh', ('XML_CHECK_RELATED_', 'XML_REVIEW_RELATED_')),
    ('tax_ids', 'Mã số thuế', ('XML_CHECK_TAX_ID_CHECKSUM',)),
    ('buyer', 'Người mua so với hồ sơ doanh nghiệp', ('XML_REVIEW_BUYER_', 'XML_CONTEXT_BUYER_')),
    ('vendor', 'Người bán so với lịch sử mua hàng', ('XML_REVIEW_VENDOR_', 'XML_CONTEXT_VENDOR_', 'XML_CONTEXT_AMOUNT_')),
    ('signature', 'Chữ ký điện tử', ('XML_CHECK_SIGNATURE_',)),
    ('qr', 'Mã QR trên hóa đơn', ('XML_CHECK_QR_',)),
    ('authority', 'Đối chiếu với cơ quan thuế', ('XML_CHECK_CERT_CHAIN', 'XML_CHECK_SELLER_STATUS')),
)
# Context records: what could not be judged (UNCHECKED) versus what was judged and passed (PASS).
PASSED_CONTEXT = ('XML_CONTEXT_BUYER_CHECKED', 'XML_CONTEXT_AMOUNT_HISTORY_SUFFICIENT')
NOT_APPLICABLE_CONTEXT = ('XML_CONTEXT_BUYER_NOT_TAXPAYER',)


def _issue_status(code):
    if code.startswith('XML_CHECK_'):
        return 'ERROR'
    if code.startswith('XML_REVIEW_'):
        return 'WARN'
    if code in PASSED_CONTEXT:
        return 'PASS'
    if code in NOT_APPLICABLE_CONTEXT:
        return 'NA'
    return 'UNCHECKED'


def check_groups(raw: bytes, created_at, issues=()):
    """Recompute the guards deterministically from the source bytes; add observations stored on the artifact."""
    checks = [(c.code, c.status, c.note) for c in extract(raw, today=created_at.date()).checks]
    observed = [i for i in issues if i.code.startswith(STORED_PREFIXES + ('XML_REVIEW_BUYER_', 'XML_CONTEXT_BUYER_'))]
    checks += [(i.code, _issue_status(i.code), i.message) for i in observed]
    if not any(code == 'XML_CHECK_DUPLICATE' for code, _, _ in checks):
        checks.append(('XML_CHECK_DUPLICATE', 'PASS', ''))
    out = []
    for key, label, prefixes in GROUPS:
        items = [dict(code=c, status=s, note=n) for c, s, n in checks if c.startswith(prefixes)]
        if not items or all(i['status'] == 'NA' for i in items):
            continue
        if any(i['status'] == 'ERROR' for i in items):
            status = 'FAIL'
        elif any(i['status'] == 'WARN' for i in items):
            status = 'REVIEW'
        elif any(i['status'] == 'UNCHECKED' for i in items):
            status = 'UNAVAILABLE'
        else:
            status = 'OK'
        out.append(dict(group=key, label=label, status=status, items=items))
    return out
