"""Exact source money, represented as integer currency minor units."""
from decimal import Decimal, InvalidOperation


SCALES = {'VND': 0, 'JPY': 0, 'USD': 2, 'EUR': 2, 'CNY': 2}


def minor(value, currency):
    if currency not in SCALES:
        raise ValueError(f'Tiền tệ không hỗ trợ: {currency}')
    if isinstance(value, (float, bool)) or not isinstance(value, (str, int, Decimal)):
        raise ValueError('Tiền nguồn phải là chuỗi thập phân hoặc số nguyên, không nhận float')
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('Số tiền không hợp lệ') from exc
    if not number.is_finite():
        raise ValueError('Số tiền không hữu hạn')
    sign, digits, exponent = number.as_tuple()
    shift = exponent + SCALES[currency]
    if abs(exponent) > 100 or len(digits) + max(shift, 0) > 18:
        raise ValueError('Số tiền vượt giới hạn 18 chữ số đơn vị nhỏ nhất')
    coefficient = int(''.join(map(str, digits)))
    if shift >= 0:
        coefficient *= 10 ** shift
    else:
        coefficient, remainder = divmod(coefficient, 10 ** -shift)
        if remainder:
            raise ValueError(f'Số tiền vượt quá {SCALES[currency]} chữ số thập phân của {currency}')
    return -coefficient if sign else coefficient


def major(value, currency):
    """Stable canonical decimal text for persisted invoice money."""
    scale = SCALES[currency]
    sign = '-' if value < 0 else ''
    digits = str(abs(value))
    if not scale:
        return sign + digits
    digits = digits.zfill(scale + 1)
    return sign + digits[:-scale] + '.' + digits[-scale:]
