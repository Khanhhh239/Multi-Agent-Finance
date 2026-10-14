"""Decimal-only adapter predicates. No money is transported to ZEN."""
from decimal import Decimal, localcontext, ROUND_HALF_UP, ROUND_HALF_EVEN
from ..domain.money import parse_decimal, decimal_string
from ..canonicalization.normalize import exact_sum, exact_product

POLICY = 'decimal-facts-v1'
MAX_DIGITS = 60
MAX_SCALE = 12


def checked(value):
    number = parse_decimal(value)
    sign, digits, exponent = number.as_tuple()
    if len(digits) + max(exponent, 0) > MAX_DIGITS or max(-exponent, 0) > MAX_SCALE:
        raise ValueError('Decimal outside supported 60-digit/12-scale domain')
    return number


def equal(left, right):
    return checked(left) == checked(right)


def add(values):
    return checked(exact_sum(checked(v) for v in values))


def product(left, right):
    return checked(exact_product(checked(left), checked(right)))


def rounded(value, scale, mode):
    if type(scale) is not int or not 0 <= scale <= MAX_SCALE or mode not in ('HALF_UP', 'HALF_EVEN'):
        raise ValueError('Explicit supported rounding policy required')
    with localcontext() as context:
        context.prec = MAX_DIGITS + MAX_SCALE + 4
        result = checked(value).quantize(Decimal(1).scaleb(-scale), rounding={'HALF_UP': ROUND_HALF_UP, 'HALF_EVEN': ROUND_HALF_EVEN}[mode])
    return checked(result)


def text(value):
    return decimal_string(checked(value))
