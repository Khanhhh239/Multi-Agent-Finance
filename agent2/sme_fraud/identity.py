"""Shared identity keys for rules and features; missing contacts never match."""
from functools import lru_cache
import re
import unicodedata


MISSING_CONTACTS = frozenset({
    'NA', 'NAN', 'NONE', 'NULL', 'UNKNOWN', 'NOTAVAILABLE',
    'KHONGCO', 'CHUACO', 'CHUACAPNHAT', 'KHONGXACDINH', 'TRONG', 'UNSPECIFIED',
})
CONTACT_KINDS = frozenset({'phone', 'address'})
FILTERED_KINDS = frozenset({'phone', 'address', 'tax_code', 'tax_id', 'bank_account'})
_NON_ALNUM_RE = re.compile(r'[^A-Z0-9]')
_MST_RE = re.compile(r'(?:[0-9]{10}|[0-9]{12}|[0-9]{13})\Z')


def normalize_vn_phone_digits(digits):
    """Normalize 10-digit VN mobile and 11-digit VN landline numbers (+84 / 0084)."""
    if not digits or not digits.isdigit() or not digits.strip('0'):
        return ''
    if digits.startswith('00840') and len(digits) in (14, 15) and digits[5] in '235789':
        return '0' + digits[5:]
    if digits.startswith('0084'):
        if len(digits) == 13 or (len(digits) == 14 and digits[4] == '2'):
            return '0' + digits[4:]
    if digits.startswith('840') and len(digits) in (12, 13) and digits[3] in '235789':
        return '0' + digits[3:]
    if digits.startswith('84'):
        if len(digits) == 11 or (len(digits) == 12 and digits[2] == '2'):
            return '0' + digits[2:]
    return digits


def normalize_mst(token):
    """Normalize 10-digit corporate, 12-digit CCCD (TT 86/2024), or 13-digit branch MST."""
    if not token or token in MISSING_CONTACTS:
        return ''
    if token.startswith('MSTSYN') or _MST_RE.fullmatch(token):
        return token
    return ''


def normalize(value, kind='text'):
    # Contacts are identifiers, not numbers or serialized Python objects.
    if kind in CONTACT_KINDS and not isinstance(value, str):
        return ''
    if kind in ('tax_code', 'tax_id', 'bank_account') and value is not None and not isinstance(value, str):
        return ''
    return _normalized(value, kind)


@lru_cache(maxsize=100000)
def _normalized(value, kind):
    value = str(value or '').strip().upper().replace('Đ', 'D')
    value = ''.join(c for c in unicodedata.normalize('NFD', value)
                    if unicodedata.category(c) != 'Mn')
    value = _NON_ALNUM_RE.sub('', value)
    if kind in FILTERED_KINDS and value in MISSING_CONTACTS:
        return ''
    if kind == 'phone' and value.isdigit():
        return normalize_vn_phone_digits(value)
    if kind in ('tax_code', 'tax_id'):
        return normalize_mst(value)
    return value
