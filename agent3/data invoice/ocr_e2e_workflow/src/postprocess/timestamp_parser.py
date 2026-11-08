from __future__ import annotations

import re
from datetime import datetime


_PATTERNS = (
    re.compile(r"(?P<day>\d{1,2})[/-](?P<month>\d{1,2})[/-](?P<year>\d{2,4})(?:\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?)?"),
    re.compile(r"(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?\s*[- ]\s*(?P<day>\d{1,2})[/-](?P<month>\d{1,2})[/-](?P<year>\d{2,4})"),
)


def parse_timestamp(value: str) -> str | None:
    for pattern in _PATTERNS:
        match = pattern.search(value or "")
        if not match:
            continue
        parts = match.groupdict(default="0")
        year = int(parts["year"])
        if year < 100:
            year += 2000
        try:
            parsed = datetime(
                year,
                int(parts["month"]),
                int(parts["day"]),
                int(parts["hour"]),
                int(parts["minute"]),
                int(parts["second"]),
            )
        except ValueError:
            continue
        return parsed.isoformat(timespec="seconds")
    return None

