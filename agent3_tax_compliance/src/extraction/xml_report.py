"""Reviewer-facing summary of XML invoice checks, grouped in plain Vietnamese.

Statuses: OK (every check in the group ran and passed), FAIL (at least one failed),
UNAVAILABLE (no legitimate data channel yet; never reported as OK).
"""
from .xml_invoice import extract

GROUPS = (
    ('amounts', 'Số tiền', ('XML_CHECK_ARITH_', 'XML_CHECK_WORDS', 'XML_CHECK_TOTALS_PRESENT', 'XML_CHECK_VAT_RATE')),
    ('invoice', 'Thông tin hóa đơn', ('XML_CHECK_SYMBOL', 'XML_CHECK_DATE', 'XML_CHECK_NUMBER', 'XML_CHECK_AUTHORITY_CODE', 'XML_CHECK_DUPLICATE')),
    ('tax_ids', 'Mã số thuế', ('XML_CHECK_TAX_ID_CHECKSUM',)),
    ('signature', 'Chữ ký điện tử', ('XML_CHECK_SIGNATURE_',)),
    ('qr', 'Mã QR trên hóa đơn', ('XML_CHECK_QR_',)),
    ('authority', 'Đối chiếu với cơ quan thuế', ('XML_CHECK_CERT_CHAIN', 'XML_CHECK_SELLER_STATUS')),
)


def check_groups(raw: bytes, created_at, issues=()):
    """Recompute the guards deterministically from the source bytes; add observations stored on the artifact."""
    checks = [(c.code, c.status, c.note) for c in extract(raw, today=created_at.date()).checks]
    checks += [(i.code, 'ERROR', i.message) for i in issues if i.code == 'XML_CHECK_DUPLICATE']
    if not any(code == 'XML_CHECK_DUPLICATE' for code, _, _ in checks):
        checks.append(('XML_CHECK_DUPLICATE', 'PASS', ''))
    out = []
    for key, label, prefixes in GROUPS:
        items = [dict(code=c, status=s, note=n) for c, s, n in checks if c.startswith(prefixes)]
        if not items:
            continue
        if any(i['status'] in ('ERROR', 'WARN') for i in items):
            status = 'FAIL'
        elif any(i['status'] == 'UNCHECKED' for i in items):
            status = 'UNAVAILABLE'
        else:
            status = 'OK'
        out.append(dict(group=key, label=label, status=status, items=items))
    return out
