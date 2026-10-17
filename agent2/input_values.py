"""Canonical tokens at the ingestion boundary, before temporal comparisons."""
from decimal import Decimal, InvalidOperation

import pandas as pd


def timestamp(value, timezone='Asia/Ho_Chi_Minh'):
    if value is None or pd.isna(value) or value == '':
        return ''
    when = pd.Timestamp(value)
    if pd.isna(when):
        raise ValueError('invalid datetime token')
    if when.tzinfo is None:
        when = when.tz_localize(timezone, ambiguous='raise', nonexistent='raise')
    return when.tz_convert('Asia/Ho_Chi_Minh').isoformat()


def integer_token(value):
    if value is None or pd.isna(value) or value == '':
        return ''
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return value
    if number.is_finite() and number == number.to_integral_value():
        return str(int(number))
    return value


def normalize(frame, timezone='Asia/Ho_Chi_Minh', integer_strings=True):
    frame = frame.copy()
    for column in frame:
        if column.endswith('_at'):
            frame[column] = frame[column].map(lambda value: timestamp(value, timezone))
        elif integer_strings and (column.endswith('_vnd') or column in {'support_doc_count', 'goods_receipt_verified', 'is_financial_entry',
                                                                       'evidence_on_file', 'saturday_operations'}):
            frame[column] = frame[column].map(integer_token)
    return frame
