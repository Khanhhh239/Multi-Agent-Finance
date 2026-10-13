from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


_MONEY_CANDIDATE = re.compile(r"(?<!\d)(\d{1,3}(?:[. ,]\d{3})+|\d{4,})(?:\s*(?:đ|vnd|vnđ))?", re.I)


def parse_money(value: str) -> int | None:
    if not value:
        return None
    candidates = _MONEY_CANDIDATE.findall(value)
    if not candidates:
        digits = re.sub(r"\D", "", value)
        return int(digits) if digits else None
    raw = candidates[-1]
    normalized = re.sub(r"[. ,]", "", raw)
    try:
        amount = Decimal(normalized)
    except InvalidOperation:
        return None
    return int(amount)


def money_candidates(value: str) -> list[int]:
    amounts: list[int] = []
    for match in _MONEY_CANDIDATE.finditer(value or ""):
        parsed = parse_money(match.group(0))
        if parsed is not None:
            amounts.append(parsed)
    return amounts

