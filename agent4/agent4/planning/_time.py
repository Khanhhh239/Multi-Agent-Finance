"""Resolve explicit calendar periods without using the wall clock."""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import date
from typing import Any

from agent4.text2sql.models import TimeDraft

_MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_MONTH_NUMBERS = {
    name: number for number, month in enumerate(_MONTHS, 1) for name in (month, month[:3])
}
_MONTH_NAMES = "|".join(sorted(_MONTH_NUMBERS, key=len, reverse=True))
_DATE = rf"\d{{4}}-\d{{1,2}}-\d{{1,2}}|\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{4}}|(?:{_MONTH_NAMES})\.? \d{{1,2}},? \d{{4}}|\d{{1,2}} (?:{_MONTH_NAMES})\.? \d{{4}}"
_YEAR = r"\d{4}"
_PERIOD = re.compile(
    rf"(?<![\w/.-])(?:"
    rf"(?P<date>{_DATE})"
    rf"|(?P<half>(?:[hH][12]|(?:first|second) half(?: of)?|(?:6|sáu) tháng (?:đầu|cuối)(?: năm)?)\s+{_YEAR})"
    rf"|(?P<quarter>(?:(?:quý|quarter|q)\s*\d{{1,2}}|[1-4](?:st|nd|rd|th) quarter)(?:\s*[/,-]\s*|\s+(?:of )?){_YEAR})"
    rf"|(?P<month>(?:tháng|month)\s*\d{{1,2}}(?:\s*[/,-]\s*|\s+(?:năm |of )?){_YEAR}|(?:{_MONTH_NAMES})\.?\s+{_YEAR}|{_YEAR}-\d{{1,2}}|\d{{1,2}}/{_YEAR})"
    rf"|(?P<year>(?:(?:năm|year)\s+)?{_YEAR}))"
    r"(?![\w/-]|\.\d)"
)
_AS_OF = re.compile(r"\b(?:as of|as at|on|tính đến|tại ngày|đến ngày|ngày)\s*$")
_INCOMPLETE_PERIOD = re.compile(
    r"\b(?:(?:q|h)\s*[1-4]|(?:quý|quarter|tháng|month)\s*\d{1,2}"
    rf"|(?:{'|'.join(month for month in _MONTH_NUMBERS if month != 'may')})"
    r"|may(?=\s+(?:and|or|to))|(?:first|second) half|(?:6|sáu) tháng (?:đầu|cuối))\b"
)
# A lone year can be a code or a number. Require a temporal cue or a bare-year question.
_YEAR_CUE = re.compile(
    r"\b(?:năm|in|for|during|of|trong|kỳ|year)\s+$"
    r"|\d{4}\s+(?:and|or|to|và|hay|hoặc|đến|vs\.?|versus)\s+$"
)
_NON_CALENDAR_YEAR = re.compile(r"\b(?:fy|fiscal(?: year)?|tài khóa|năm tài chính)\s*$")


def _date_value(text: str, locale: str) -> date:
    if re.match(r"\d{4}-", text):
        return date(*map(int, text.split("-")))
    if re.fullmatch(r"[\d/-]+", text):
        first, second, year = map(int, re.split(r"[/-]", text))
        month, day = (first, second) if locale == "en-US" else (second, first)
        return date(year, month, day)

    first, second, year = text.replace(".", "").replace(",", "").split()
    if first.isdigit():
        return date(int(year), _MONTH_NUMBERS[second], int(first))
    return date(int(year), _MONTH_NUMBERS[first], int(second))


def _calendar_period(kind: str, text: str) -> TimeDraft:
    numbers = re.findall(r"\d+", text)
    year = int(numbers[-1])
    if kind == "year":
        return TimeDraft.range(date(year, 1, 1), date(year, 12, 31), "year")
    if kind == "half":
        second = text.startswith(("h2", "second")) or "cuối" in text
        start_month, end_month, grain = (7, 12, "month") if second else (1, 6, "month")
    elif kind == "quarter":
        quarter = int(numbers[0])
        start_month, end_month, grain = 3 * quarter - 2, 3 * quarter, "quarter"
    else:
        if re.fullmatch(r"\d{4}-\d{1,2}", text):
            year, month = map(int, numbers)
        else:
            name = re.match(r"[a-z]+", text)
            month = (
                _MONTH_NUMBERS[name[0]] if name and name[0] in _MONTH_NUMBERS else int(numbers[0])
            )
        start_month, end_month, grain = month, month, "month"
    start = date(year, start_month, 1)
    end = date(year, end_month, monthrange(year, end_month)[1])
    return TimeDraft.range(start, end, grain)


def parse_time_slot(
    question: str, *, locale: str = "vi-VN", period_type: str | None = None
) -> dict[str, Any]:
    """Return a canonical time object or mode 'none' for unresolved time."""
    question = " ".join(question.casefold().split())
    none = TimeDraft.none()
    times = []
    spans = []
    for match in _PERIOD.finditer(question):
        kind, value = match.lastgroup, match[0]
        before = question[: match.start()]
        if (
            kind == "year"
            and value.isdigit()
            and not (
                _YEAR_CUE.search(before) or not before.strip() or question.rstrip("?.!") == value
            )
        ):
            continue
        if _NON_CALENDAR_YEAR.search(before):
            return none.model_dump(mode="json")
        try:
            as_of = _AS_OF.search(before)
            if kind == "date":
                if period_type == "flow":
                    return none.model_dump(mode="json")
                parsed = TimeDraft.as_of_date(_date_value(value, locale))
            elif as_of or period_type == "snapshot":
                return none.model_dump(mode="json")
            else:
                parsed = _calendar_period(kind, value)
        except ValueError:
            return none.model_dump(mode="json")
        if parsed not in times:
            times.append(parsed)
        spans.append(match.span())

    for start, end in reversed(spans):
        question = question[:start] + " " * (end - start) + question[end:]
    if len(times) != 1 or _INCOMPLETE_PERIOD.search(question):
        return none.model_dump(mode="json")
    return times[0].model_dump(mode="json")
