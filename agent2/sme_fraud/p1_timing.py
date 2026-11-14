"""Explicit invoice header clocks for the retained native P1 profile.

Undated legacy headers retain their old input contract; this does not certify
their availability. Canonical snapshot inputs require explicit source clocks.
"""
from datetime import datetime
from functools import lru_cache


@lru_cache(maxsize=150000)
def _instant(value):
    at=datetime.fromisoformat(value)
    if at.utcoffset() is None:raise ValueError('Invoice timestamp needs timezone')
    return at


def unavailable_fields(row,now):
    cutoff=_instant(now);missing=[]
    for field in ('invoice_issued_at','invoice_observed_at'):
        value=row.get(field)
        if not value:continue  # Compatibility only, never an invented timestamp.
        try:known=_instant(value)<=cutoff
        except (TypeError,ValueError):known=False
        if not known:missing.append(field)
    return missing
