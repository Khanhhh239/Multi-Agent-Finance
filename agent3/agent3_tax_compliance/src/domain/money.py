"""Exact decimal boundary: no binary floats, exponents or implicit rounding."""
import re
from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer, WithJsonSchema

DECIMAL_PATTERN = r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$'


def parse_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError('finite decimal required')
        return value
    if not isinstance(value, str) or not re.fullmatch(DECIMAL_PATTERN, value):
        raise ValueError('money/quantity/rate requires Decimal or a plain decimal string')
    return Decimal(value)


def decimal_string(value: Decimal) -> str:
    result = format(value, 'f')
    if '.' in result:
        result = result.rstrip('0').rstrip('.')
    return '0' if Decimal(result) == 0 else result


ExactDecimal = Annotated[
    Decimal, BeforeValidator(parse_decimal),
    PlainSerializer(decimal_string, return_type=str),
    WithJsonSchema({'type': 'string', 'pattern': DECIMAL_PATTERN}),
]
