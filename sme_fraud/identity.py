"""Shared identity keys for rules and features; missing contacts never match."""
from functools import lru_cache
import re
import unicodedata


MISSING_CONTACTS = frozenset({'NA', 'NAN', 'NONE', 'NULL', 'UNKNOWN', 'NOTAVAILABLE', 'KHONGCO', 'CHUACO'})
CONTACT_KINDS = frozenset({'phone', 'address'})


def normalize(value, kind='text'):
    # Contacts are identifiers, not numbers or serialized Python objects.
    if kind in CONTACT_KINDS and not isinstance(value, str):
        return ''
    return _normalized(value, kind)


@lru_cache(maxsize=100000)
def _normalized(value, kind):
    value = str(value or '').strip().upper().replace('Đ', 'D')
    value = ''.join(c for c in unicodedata.normalize('NFD', value)
                    if unicodedata.category(c) != 'Mn')
    value = re.sub(r'[^A-Z0-9]', '', value)
    if kind in CONTACT_KINDS and value in MISSING_CONTACTS:
        return ''
    if kind == 'phone' and value.isdigit():
        if not value.strip('0'):
            return ''
        if value.startswith('0084') and len(value) == 13:
            value = '0' + value[4:]
        elif value.startswith('84') and len(value) == 11:
            value = '0' + value[2:]
    return value
