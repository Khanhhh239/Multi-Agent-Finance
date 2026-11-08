"""Ngày nghiệp vụ Việt Nam: đầu ra timezone-naive, kể cả khi nguồn có offset."""
import pandas as pd
import re


DATE_FIELDS = frozenset({
    'date', 'issue_date', 'due_date', 'value_date', 'event_date',
    'made_date', 'promised_date', 'credit_note_date', 'ledger_clear_date',
    'adjusts_issue_date', 'available_on', 'known_at', 'ingested_on',
})


def local_dates(values,dayfirst=True):
    def convert(value):
        # ISO dates in an ERP export are year-first even when other rows use
        # the Vietnamese day/month/year convention.
        iso=isinstance(value,str) and re.match(r'^\d{4}-\d{2}-\d{2}(?:\D|$)',value)
        stamp=pd.to_datetime(value,dayfirst=False if iso else dayfirst,errors='coerce')
        if pd.isna(stamp):return pd.NaT
        if stamp.tzinfo is not None:stamp=stamp.tz_convert('Asia/Ho_Chi_Minh').tz_localize(None)
        return stamp.normalize()
    return pd.to_datetime(values.map(convert))


def normalize_date_fields(row, *, required=()):
    """Return canonical Vietnam calendar dates without mutating source records."""
    result = dict(row)
    for column in DATE_FIELDS.intersection(row) | set(required):
        value = row.get(column)
        missing = value is None or isinstance(value, str) and not value.strip()
        if not missing and not isinstance(value, (str, bool, int, float)):
            missing = bool(pd.isna(value))
        if missing and column not in required:
            result[column] = None
            continue
        if missing or isinstance(value, (bool, int, float)):
            raise ValueError(f'{column}: ngày không hợp lệ')
        parsed = local_dates(pd.Series([value]), dayfirst=False).iloc[0]
        if pd.isna(parsed):
            raise ValueError(f'{column}: ngày không hợp lệ')
        result[column] = parsed.date().isoformat()
    return result
