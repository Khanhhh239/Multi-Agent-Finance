"""Vietnamese number formatting and parsing.

The same rules are used to (1) render tool results the LLM must copy and (2)
parse numbers back out of the LLM's answer for the citation verifier, so a
number formatted here always verifies.
"""
from __future__ import annotations

import math
import re
from decimal import Decimal


def _group(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _dec(x: float, digits: int) -> str:
    s = f"{x:.{digits}f}"
    if digits:
        s = s.rstrip("0").rstrip(".")
    return s.replace(".", ",")


def fmt_vnd(v: float | Decimal | None, exact: bool = False) -> str:
    """12345678900 → '12,35 tỷ đồng'; exact=True → '12.345.678.900 đ'."""
    if v is None:
        return "không có dữ liệu"
    v = float(v)
    if exact:
        return f"{'-' if v < 0 else ''}{_group(int(round(abs(v))))} đ"
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1e9:
        return f"{sign}{_dec(a / 1e9, 2)} tỷ đồng"
    if a >= 1e6:
        return f"{sign}{_dec(a / 1e6, 2 if a < 1e7 else 1 if a < 1e8 else 0)} triệu đồng"
    if a >= 1e3:
        return f"{sign}{_group(int(round(a)))} đồng"
    return f"{sign}{int(round(a))} đồng"


def fmt_pct(v: float | None, digits: int = 1) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "không xác định"
    return f"{_dec(float(v), digits)}%"


def fmt_days(v: float | None) -> str:
    if v is None:
        return "không xác định"
    return f"{_dec(float(v), 0 if abs(v) >= 10 else 1)} ngày"


def fmt_ratio(v: float | None) -> str:
    if v is None:
        return "không xác định"
    return f"{_dec(float(v), 2)} lần"


def fmt_count(v: float | None) -> str:
    return "0" if v is None else _group(int(round(float(v))))


def fmt_value(v, unit: str) -> str:
    if unit == "VND":
        return fmt_vnd(v)
    if unit == "%":
        return fmt_pct(v)
    if unit == "days":
        return fmt_days(v)
    if unit == "ratio":
        return fmt_ratio(v)
    if unit == "count":
        return fmt_count(v)
    return str(v)


def fmt_delta(delta: float | None, unit: str) -> str:
    if delta is None:
        return "không xác định"
    if unit == "%":
        return f"{'+' if delta >= 0 else ''}{_dec(delta, 1)} điểm %"
    body = fmt_value(abs(delta), unit)
    return f"{'+' if delta >= 0 else '-'}{body}"


# ------------------------------------------------------------------ parsing
_SCALE = {"ty": 1e9, "tỷ": 1e9, "tỉ": 1e9, "ti": 1e9, "trieu": 1e6, "triệu": 1e6, "tr": 1e6, "nghin": 1e3, "nghìn": 1e3, "ngan": 1e3,
          "ngàn": 1e3, "k": 1e3, "billion": 1e9, "million": 1e6, "bn": 1e9, "m": 1e6}
_NUM_RE = re.compile(
    r"(?<![\w.,])([-+−]?\d{1,3}(?:\.\d{3})+(?:,\d+)?|[-+−]?\d+(?:,\d+)?|[-+−]?\d+(?:\.\d+)?)"
    r"\s*(tỷ|tỉ|ty|ti|triệu|trieu|tr|nghìn|nghin|ngàn|ngan|billion|million|bn|%)?(?![\w])",
    re.IGNORECASE,
)


def parse_vn_number(token: str) -> float:
    token = token.replace("−", "-").replace("+", "")
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+(?:,\d+)?", token):
        return float(token.replace(".", "").replace(",", "."))
    if "," in token:
        return float(token.replace(",", "."))
    return float(token)


def extract_numbers(text: str) -> list[dict]:
    """Return every number in a Vietnamese answer with its scale.

    '12,35 tỷ' → 12.35e9, '345 triệu' → 345e6, '19,1%' → 19.1 (unit %),
    '1.234.567 đ' → 1234567.  Dates (14/10/2026) and codes (KH0012) are skipped.
    """
    cleaned = re.sub(r"\b\d{1,2}/\d{1,2}/\d{4}\b|\b\d{1,2}/\d{4}\b|\b\d{4}-\d{2}(?:-\d{2})?\b", " ", text)
    cleaned = re.sub(r"\b[A-Za-z]+[-_]?\d[\w\-/]*\b", " ", cleaned)  # codes like KH0012, Q3, 1C26TMP-00001
    out = []
    for mm in _NUM_RE.finditer(cleaned):
        tok, unit = mm.group(1), (mm.group(2) or "").lower()
        try:
            val = parse_vn_number(tok)
        except ValueError:
            continue
        if unit == "%":
            out.append({"value": val, "unit": "%", "raw": mm.group(0)})
        else:
            out.append({"value": val * _SCALE.get(unit, 1.0), "unit": "abs" if unit else "plain", "raw": mm.group(0)})
    return out
