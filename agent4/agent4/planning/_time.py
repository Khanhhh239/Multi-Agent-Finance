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
_MONTH_COUNTS = {
    name: number
    for number, name in enumerate(
        (
            "một",
            "hai",
            "ba",
            "bốn",
            "năm",
            "sáu",
            "bảy",
            "tám",
            "chín",
            "mười",
            "mười một",
            "mười hai",
        ),
        1,
    )
}
_COUNT = r"\d{1,2}|" + "|".join(sorted(_MONTH_COUNTS, key=len, reverse=True))
_FISCAL = r"(?:fy|fiscal(?: year)?|tài khóa|năm tài chính)"
_PERIOD = re.compile(
    rf"(?<![\w/.-])(?:"
    rf"(?P<date>{_DATE})"
    rf"|(?P<first_months>(?:(?:{_COUNT}) tháng đầu năm|first \d{{1,2}} months of)\s+{_YEAR})"
    rf"|(?P<half>(?:[hH][12]|(?:first|second) half(?: of)?|(?:6|sáu) tháng (?:đầu|cuối)(?: năm)?)\s+{_YEAR})"
    rf"|(?P<quarter>(?:(?:quý|quarter|q)\s*\d{{1,2}}|[1-4](?:st|nd|rd|th) quarter)(?:\s*[/,-]\s*|\s+(?:of |năm )?){_YEAR})"
    rf"|(?P<month>(?:tháng|month)\s*\d{{1,2}}(?:\s*[/,-]\s*|\s+(?:năm |of )?){_YEAR}|t\d{{1,2}}/{_YEAR}|(?:{_MONTH_NAMES})\.?\s+{_YEAR}|{_YEAR}-\d{{1,2}}|\d{{1,2}}/{_YEAR})"
    rf"|(?P<year>(?:(?:{_FISCAL}|năm|year)\s+)?{_YEAR}))"
    r"(?![\w/-]|\.\d)"
)
_AS_OF = re.compile(r"\b(?:as of|as at|tính đến|đến ngày)\s*$")
_PERIOD_END = re.compile(r"\b(?:cuối|end of)(?: the)?\s*$")
_YEAR_START = re.compile(r"\b(?:đầu|beginning of)\s*$")
_INCOMPLETE_PERIOD = re.compile(
    r"\b(?:(?:q|h)\s*[1-4]|(?:quý|quarter|tháng|month)\s*\d{1,2}"
    rf"|(?:{'|'.join(month for month in _MONTH_NUMBERS if month != 'may')})"
    r"|may(?=\s+(?:and|or|to))|(?:first|second) half|(?:6|sáu) tháng (?:đầu|cuối))\b"
)
# A lone year can be a code or a number.
_YEAR_CUE = re.compile(
    r"\b(?:năm|in|for|during|of|trong|kỳ|year|from|between|từ|giữa|to|through|đến)\s+$"
    r"|\d{4}\s+(?:and|or|và|hay|hoặc|vs\.?|versus)\s+$"
)
_NON_CALENDAR_YEAR = re.compile(r"\b(?:non[- ]calendar|lệch năm dương lịch)\b")
_FISCAL_START = re.compile(
    rf"\b(?:bắt đầu(?: từ| vào)?|start(?:s|ing)?(?: in)?|begin(?:s|ning)?(?: in)?) "
    rf"(?:tháng )?(?P<month>{_MONTH_NAMES}|\d{{1,2}})\b"
)
_CAP = re.compile(r"\s*(?:\(?\s*(?:up to|through the end of)|\(\s*đến hết)\s+")
_RANGE_END = re.compile(r"\s+(?:to|through|đến(?: hết)?|tới(?: hết)?)\s+")
_BETWEEN = re.compile(r"\b(?:between|giữa|so sánh|compare)\b")
_RANGE_PAIR = re.compile(r"\s+(?:and|và|with|với|vs\.?|versus)\s+")
_SHARED_YEAR_START = re.compile(rf"\bfrom (?P<month>{_MONTH_NAMES})\.? (?:to|through)\s+$")
_MONTH_LIST = re.compile(r"\s*\(tháng (\d{1,2}(?:,\s*\d{1,2})+)\)")
_GRAIN_ORDER = ("day", "month", "quarter", "year")


def _calendar_year_question(question: str) -> str:
    if _NON_CALENDAR_YEAR.search(question):
        raise ValueError("Non-calendar years require a configured fiscal calendar")
    if re.search(rf"\b{_FISCAL}\b", question) and (match := _FISCAL_START.search(question)):
        month = match["month"]
        if (int(month) if month.isdigit() else _MONTH_NUMBERS[month]) != 1:
            raise ValueError("Non-calendar years require a configured fiscal calendar")
        return question[: match.start()] + question[match.end() :]
    return question


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
    if kind == "first_months":
        count = text.split(" tháng", 1)[0]
        end_month = _MONTH_COUNTS[count] if count in _MONTH_COUNTS else int(numbers[0])
        start_month, grain = 1, "month"
    elif kind == "half":
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


def _flow_range(question: str, periods: list[TimeDraft], spans: list[tuple[int, int]]) -> TimeDraft:
    first = periods[0]
    if all(period == first for period in periods):
        return first
    if len(periods) != 2:
        return TimeDraft.none()

    last = periods[1]
    prefix = question[: spans[0][0]]
    connector = question[spans[0][1] : spans[1][0]]
    grain = min((first.grain, last.grain), key=_GRAIN_ORDER.index)
    if _CAP.fullmatch(connector):
        # A cap narrows the parent period, including when it appears in parentheses.
        end = min(first.end, last.end)
        if end < first.start or last.start > first.end:
            return TimeDraft.none()
        return TimeDraft.range(first.start, end, grain)
    if _RANGE_END.fullmatch(connector):
        if first.start > last.start:
            return TimeDraft.none()
        return TimeDraft.range(first.start, last.end, grain)
    if _RANGE_PAIR.fullmatch(connector) and (
        _BETWEEN.search(prefix)
        or (first.end.year < last.start.year and re.search(r"\bcả\s*$", prefix))
    ):
        return TimeDraft.range(min(first.start, last.start), max(first.end, last.end), grain)
    return TimeDraft.none()


def _snapshot(question: str, periods: list[TimeDraft], spans: list[tuple[int, int]]) -> TimeDraft:
    dates = {item.end for item in periods if item.grain == "day"}
    if len(dates) == 1:
        day = next(iter(dates))
        for item, (start, _) in zip(periods, spans, strict=True):
            if not item.start <= day <= item.end:
                return TimeDraft.none()
            if _PERIOD_END.search(question[:start]) and day != item.end:
                return TimeDraft.none()
        return TimeDraft.as_of_date(day)
    if len(periods) == 1:
        prefix = question[: spans[0][0]]
        if _PERIOD_END.search(prefix) or _AS_OF.search(prefix):
            return TimeDraft.as_of_date(periods[0].end)
        if _YEAR_START.search(prefix) and periods[0].grain == "year":
            return TimeDraft.as_of_date(periods[0].start)
    return TimeDraft.none()


def _month_list(parent: TimeDraft, text: str) -> TimeDraft:
    months = [int(value) for value in re.findall(r"\d+", text)]
    if months != list(range(months[0], months[-1] + 1)):
        return TimeDraft.none()
    year = parent.start.year
    first = date(year, months[0], 1)
    last = date(year, months[-1], monthrange(year, months[-1])[1])
    if not parent.start <= first <= last <= parent.end:
        return TimeDraft.none()
    return TimeDraft.range(first, last, "month")


def _parse_time(question: str, locale: str, period_type: str | None) -> TimeDraft:
    question = _calendar_year_question(question)
    periods = []
    spans = []
    snapshot_cue = False
    for match in _PERIOD.finditer(question):
        kind, value = match.lastgroup, match[0]
        before = question[: match.start()]
        as_of = bool(_AS_OF.search(before))
        if (
            kind == "year"
            and value.isdigit()
            and before
            and not (_YEAR_CUE.search(before) or as_of)
        ):
            continue
        snapshot_cue |= as_of
        if kind == "date":
            day = _date_value(value, locale)
            parsed = TimeDraft.range(day, day, "day")
        else:
            parsed = _calendar_period(kind, value)
        start, end = match.span()
        if kind == "month" and (shared := _SHARED_YEAR_START.search(before)):
            first = date(parsed.start.year, _MONTH_NUMBERS[shared["month"]], 1)
            if first > parsed.start:
                return TimeDraft.none()
            parsed = TimeDraft.range(first, parsed.end, "month")
            start = shared.start()
        if kind in {"year", "quarter"} and (months := _MONTH_LIST.match(question, end)):
            parsed = _month_list(parsed, months[1])
            if parsed.mode == "none":
                return parsed
            end = months.end()
        periods.append(parsed)
        spans.append((start, end))

    remainder = question
    for start, end in reversed(spans):
        remainder = remainder[:start] + " " * (end - start) + remainder[end:]
    if not periods or _INCOMPLETE_PERIOD.search(remainder):
        return TimeDraft.none()
    if period_type == "snapshot" or (
        period_type is None and (snapshot_cue or any(item.grain == "day" for item in periods))
    ):
        return _snapshot(question, periods, spans)
    if snapshot_cue or (len(periods) == 1 and _YEAR_START.search(question[: spans[0][0]])):
        return TimeDraft.none()
    return _flow_range(question, periods, spans)


def parse_time_slot(
    question: str, *, locale: str = "vi-VN", period_type: str | None = None
) -> dict[str, Any]:
    """Return a canonical time object or mode 'none' for unresolved time."""
    question = " ".join(question.casefold().split())
    try:
        parsed = _parse_time(question, locale, period_type)
    except ValueError:
        parsed = TimeDraft.none()
    return parsed.model_dump(mode="json")
