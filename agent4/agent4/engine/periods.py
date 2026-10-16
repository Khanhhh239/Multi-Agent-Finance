"""Deterministic resolution of time expressions (Vietnamese + canonical tokens).

Small LLMs are unreliable at calendar arithmetic ("quý trước" in October →
Q3, "cùng kỳ năm trước", "6 tháng gần nhất"...).  The agent therefore never
asks the model to compute dates: the model passes either a canonical token
(``this_month``, ``2026-Q2`` …) or the user's own words, and this module turns
it into an exact [start, end] range relative to the data cut-off date.
"""
from __future__ import annotations

import calendar
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta


class PeriodError(ValueError):
    pass


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    label: str
    grain: str  # day | week | month | quarter | half | year | custom
    token: str

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def as_dict(self) -> dict:
        return {"start_date": self.start.isoformat(), "end_date": self.end.isoformat(), "label": self.label, "token": self.token}


def _month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def _add_months(y: int, m: int, n: int) -> tuple[int, int]:
    k = y * 12 + (m - 1) + n
    return k // 12, k % 12 + 1


def strip_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", strip_accents(text.lower())).strip()


def month_period(y: int, m: int) -> Period:
    return Period(date(y, m, 1), _month_end(y, m), f"tháng {m:02d}/{y}", "month", f"{y}-{m:02d}")


def quarter_period(y: int, q: int) -> Period:
    if not 1 <= q <= 4:
        raise PeriodError(f"quý không hợp lệ: {q}")
    m0 = 3 * (q - 1) + 1
    return Period(date(y, m0, 1), _month_end(y, m0 + 2), f"quý {q}/{y}", "quarter", f"{y}-Q{q}")


def half_period(y: int, h: int) -> Period:
    return Period(date(y, 1 if h == 1 else 7, 1), _month_end(y, 6 if h == 1 else 12),
                  f"{'6 tháng đầu' if h == 1 else '6 tháng cuối'} năm {y}", "half", f"{y}-H{h}")


def year_period(y: int) -> Period:
    return Period(date(y, 1, 1), date(y, 12, 31), f"năm {y}", "year", str(y))


def _vn_date(d: date) -> str:
    return f"{d:%d/%m/%Y}"


def resolve_period(expr: str | dict | None, as_of: date, default: str = "this_month") -> Period:
    """Resolve a canonical token, an ISO range or a Vietnamese phrase."""
    try:
        return _resolve_period(expr, as_of, default)
    except PeriodError:
        raise
    except (ValueError, OverflowError) as exc:
        raise PeriodError(f"Mốc thời gian không hợp lệ: {expr!r}") from exc


def _resolve_period(expr: str | dict | None, as_of: date, default: str = "this_month") -> Period:
    if expr is None or (isinstance(expr, str) and not expr.strip()):
        expr = default
    if isinstance(expr, dict):
        s, e = expr.get("start_date") or expr.get("start"), expr.get("end_date") or expr.get("end")
        if s and e:
            return _custom(date.fromisoformat(str(s)), date.fromisoformat(str(e)))
        expr = expr.get("token") or expr.get("label") or default
    raw = str(expr).strip()
    t = _norm(raw)
    t = t.replace("_", " ") if re.fullmatch(r"[a-z_0-9]+", t) else t
    y, m = as_of.year, as_of.month
    q = (m - 1) // 3 + 1

    # ---- explicit ranges / ISO forms
    mm = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\s*(?:\.\.|to|den|->|–|-)\s*(\d{4}-\d{2}-\d{2})", t)
    if mm:
        return _custom(date.fromisoformat(mm.group(1)), date.fromisoformat(mm.group(2)))
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
        d = date.fromisoformat(t)
        return Period(d, d, f"ngày {_vn_date(d)}", "day", t)
    if mm := re.fullmatch(r"(\d{4})-(\d{1,2})", t):
        return month_period(int(mm.group(1)), int(mm.group(2)))
    if mm := re.fullmatch(r"(\d{4})\s*-?\s*q([1-4])", t):
        return quarter_period(int(mm.group(1)), int(mm.group(2)))
    if mm := re.fullmatch(r"q([1-4])\s*[/ -]?\s*(\d{4})", t):
        return quarter_period(int(mm.group(2)), int(mm.group(1)))
    if mm := re.fullmatch(r"(\d{4})\s*-?\s*h([12])", t):
        return half_period(int(mm.group(1)), int(mm.group(2)))
    if re.fullmatch(r"\d{4}", t):
        return year_period(int(t))

    # ---- canonical tokens (English) and Vietnamese phrases
    if t in ("today", "hom nay", "as of", "as_of", "hien tai", "bay gio", "now", "cuoi ky", "hien nay", "luc nay"):
        return Period(as_of, as_of, f"ngày {_vn_date(as_of)}", "day", "today")
    if t in ("this month", "mtd", "thang nay", "thang hien tai", "trong thang", "thang nay den nay"):
        p = month_period(y, m)
        return Period(p.start, p.end, f"tháng {m:02d}/{y}", "month", "this_month")
    if t in ("last month", "previous month", "thang truoc", "thang vua roi", "thang roi", "thang vua qua"):
        yy, mo = _add_months(y, m, -1)
        p = month_period(yy, mo)
        return Period(p.start, p.end, p.label, "month", "last_month")
    if t in ("next month", "thang toi", "thang sau", "thang ke tiep"):
        yy, mo = _add_months(y, m, 1)
        p = month_period(yy, mo)
        return Period(p.start, p.end, p.label, "month", "next_month")
    if t in ("this quarter", "qtd", "quy nay", "quy hien tai"):
        p = quarter_period(y, q)
        return Period(p.start, p.end, p.label, "quarter", "this_quarter")
    if t in ("last quarter", "previous quarter", "quy truoc", "quy vua roi", "quy vua qua"):
        yy, qq = (y, q - 1) if q > 1 else (y - 1, 4)
        p = quarter_period(yy, qq)
        return Period(p.start, p.end, p.label, "quarter", "last_quarter")
    if t in ("this year", "nam nay", "nam hien tai"):
        p = year_period(y)
        return Period(p.start, p.end, p.label, "year", "this_year")
    if t in ("ytd", "year to date", "tu dau nam", "luy ke tu dau nam", "luy ke nam", "tu dau nam den nay", "luy ke"):
        return Period(date(y, 1, 1), as_of, f"lũy kế từ 01/01/{y} đến {_vn_date(as_of)}", "custom", "ytd")
    if t in ("last year", "previous year", "nam ngoai", "nam truoc", "nam roi", "nam vua qua"):
        p = year_period(y - 1)
        return Period(p.start, p.end, p.label, "year", "last_year")
    if t in ("this week", "tuan nay"):
        s = as_of - timedelta(days=as_of.weekday())
        return Period(s, s + timedelta(days=6), f"tuần {_vn_date(s)}–{_vn_date(s + timedelta(days=6))}", "week", "this_week")
    if t in ("last week", "tuan truoc", "tuan roi"):
        s = as_of - timedelta(days=as_of.weekday() + 7)
        return Period(s, s + timedelta(days=6), f"tuần {_vn_date(s)}–{_vn_date(s + timedelta(days=6))}", "week", "last_week")
    if mm := re.fullmatch(r"(?:last|past)\s*(\d+)\s*months?|(\d+)\s*thang\s*(?:gan nhat|gan day|qua|vua qua|truoc|vua roi)", t):
        n = int(mm.group(1) or mm.group(2))
        if n < 1:
            raise PeriodError("Số tháng phải lớn hơn 0.")
        # N most recent *complete* months (the current month is still open)
        ey, em = _add_months(y, m, -1)
        sy, sm = _add_months(ey, em, -(n - 1))
        return Period(date(sy, sm, 1), _month_end(ey, em), f"{n} tháng gần nhất ({sm:02d}/{sy}–{em:02d}/{ey})", "custom", f"last_{n}_months")
    if mm := re.fullmatch(r"(?:last|past)\s*(\d+)\s*days?|(\d+)\s*ngay\s*(?:gan nhat|qua|vua qua)", t):
        n = int(mm.group(1) or mm.group(2))
        if n < 1:
            raise PeriodError("Số ngày phải lớn hơn 0.")
        return Period(as_of - timedelta(days=n - 1), as_of, f"{n} ngày gần nhất", "custom", f"last_{n}_days")
    if mm := re.fullmatch(r"(?:next)\s*(\d+)\s*days?|(\d+)\s*ngay\s*(?:toi|sap toi|ke tiep|tiep theo)", t):
        n = int(mm.group(1) or mm.group(2))
        if n < 1:
            raise PeriodError("Số ngày phải lớn hơn 0.")
        s = as_of + timedelta(days=1)
        return Period(s, as_of + timedelta(days=n), f"{n} ngày tới ({_vn_date(s)}–{_vn_date(as_of + timedelta(days=n))})", "custom", f"next_{n}_days")
    if mm := re.fullmatch(r"(?:thang|t)\s*(\d{1,2})(?:\s*(?:/|-|nam)\s*(\d{4}))?", t):
        mo = int(mm.group(1))
        yy = int(mm.group(2)) if mm.group(2) else (y if mo <= m else y - 1)
        return month_period(yy, mo)
    if mm := re.fullmatch(r"(?:quy|q)\s*([1-4]|i{1,3}|iv)(?:\s*(?:/|-|nam)\s*(\d{4}))?", t):
        qq = {"i": 1, "ii": 2, "iii": 3, "iv": 4}.get(mm.group(1), None) or int(mm.group(1))
        yy = int(mm.group(2)) if mm.group(2) else (y if qq <= q else y - 1)
        return quarter_period(yy, qq)
    if mm := re.fullmatch(r"nam\s*(\d{4})", t):
        return year_period(int(mm.group(1)))
    if t in ("6 thang dau nam", "nua dau nam", "h1"):
        return half_period(y, 1)
    if t in ("6 thang cuoi nam", "nua cuoi nam", "h2"):
        return half_period(y, 2)
    raise PeriodError(f"không hiểu mốc thời gian '{raw}'")


def _custom(s: date, e: date) -> Period:
    if s > e:
        raise PeriodError(f"ngày bắt đầu {s} sau ngày kết thúc {e}")
    if s.day == 1 and e == _month_end(e.year, e.month):
        if (s.year, s.month) == (e.year, e.month):
            return month_period(s.year, s.month)
        if s.month in (1, 4, 7, 10) and _add_months(s.year, s.month, 2) == (e.year, e.month):
            return quarter_period(s.year, (s.month - 1) // 3 + 1)
        if s.month == 1 and e.month == 12 and s.year == e.year:
            return year_period(s.year)
    return Period(s, e, f"{_vn_date(s)}–{_vn_date(e)}", "custom", f"{s.isoformat()}..{e.isoformat()}")


def previous_period(p: Period) -> Period:
    if p.grain == "month":
        yy, mo = _add_months(p.start.year, p.start.month, -1)
        return month_period(yy, mo)
    if p.grain == "quarter":
        qq = (p.start.month - 1) // 3 + 1
        return quarter_period(p.start.year, qq - 1) if qq > 1 else quarter_period(p.start.year - 1, 4)
    if p.grain == "half":
        return half_period(p.start.year, 1) if p.start.month == 7 else half_period(p.start.year - 1, 2)
    if p.grain == "year":
        return year_period(p.start.year - 1)
    length = p.days
    e = p.start - timedelta(days=1)
    return _custom(e - timedelta(days=length - 1), e)


def same_period_last_year(p: Period) -> Period:
    def shift(d: date) -> date:
        try:
            return d.replace(year=d.year - 1)
        except ValueError:
            return d.replace(year=d.year - 1, day=28)
    s, e = shift(p.start), shift(p.end)
    if p.grain == "month":
        return month_period(s.year, s.month)
    if p.grain == "quarter":
        return quarter_period(s.year, (s.month - 1) // 3 + 1)
    if p.grain == "year":
        return year_period(s.year)
    return _custom(s, e)


def clamp_to_as_of(p: Period, as_of: date) -> Period:
    """Same period, restricted to the data cut-off (for MTD/QTD/YTD)."""
    if p.end <= as_of:
        return p
    end = max(as_of, p.start - timedelta(days=1)) if p.start > as_of else as_of
    return Period(p.start, end, p.label, p.grain, p.token)


def comparable_partial(p: Period, cmp: Period, as_of: date) -> Period:
    """Like-for-like comparison: if p is an open period cut at as_of (e.g. MTD 1–14/10),
    cut the comparison period at the same day offset (1–14/9)."""
    if p.end <= as_of or p.start > as_of:
        return cmp
    offset = (as_of - p.start).days
    end = min(cmp.end, cmp.start + timedelta(days=offset))
    return Period(cmp.start, end, f"{cmp.label} (cùng số ngày: {_vn_date(cmp.start)}–{_vn_date(end)})", cmp.grain, cmp.token)


_PHRASES = [
    r"\d+\s*thang\s*(?:gan nhat|gan day|qua|vua qua|truoc|vua roi)", r"\d+\s*ngay\s*(?:toi|sap toi|ke tiep|tiep theo|gan nhat|qua|vua qua)",
    r"thang\s*\d{1,2}\s*(?:/|-|nam)\s*\d{4}", r"quy\s*(?:[1-4]|iv|i{1,3})\s*(?:/|-|nam)\s*\d{4}", r"q[1-4]\s*[/ -]?\s*\d{4}",
    r"(?<![a-z])thang\s*\d{1,2}(?!\d)", r"(?<![a-z])quy\s*(?:[1-4]|iv|i{1,3})(?![a-z0-9])", r"nam\s*\d{4}",
    r"6 thang dau nam", r"6 thang cuoi nam", r"nua dau nam", r"nua cuoi nam",
    r"luy ke tu dau nam", r"tu dau nam(?: den nay)?", r"luy ke nam",
    r"thang nay", r"thang truoc", r"thang vua roi", r"thang vua qua", r"thang toi", r"thang sau", r"thang hien tai",
    r"quy nay", r"quy truoc", r"quy vua roi", r"quy vua qua", r"quy hien tai",
    r"nam nay", r"nam ngoai", r"nam truoc", r"nam vua qua",
    r"tuan nay", r"tuan truoc", r"hom nay", r"hien tai", r"hien nay", r"cuoi ky",
]
_PHRASE_RE = re.compile("|".join(f"(?:{p})" for p in _PHRASES))


def extract_periods(question: str, as_of: date) -> list[tuple[str, Period]]:
    """Find every time expression in a free-text question (left to right)."""
    t = _norm(question)
    out: list[tuple[str, Period]] = []
    token_pattern = r"(?<!\w)\d{4}-(?:q[1-4]|h[12]|\d{2}(?:-\d{2})?)(?!\w)"
    combined = re.compile(token_pattern + "|" + _PHRASE_RE.pattern)
    for mm in combined.finditer(t):
        phrase = mm.group(0)
        if phrase in ("nam truoc",) and "cung ky" in t[max(0, mm.start() - 12):mm.start()]:
            continue  # "cùng kỳ năm trước" is a comparison, not a period
        try:
            out.append((phrase, resolve_period(phrase, as_of)))
        except PeriodError:
            continue
    return out


def detect_comparison(question: str) -> str | None:
    t = _norm(question)
    if re.search(r"cung ky|so voi nam truoc|so voi nam ngoai|yoy|year over year", t):
        return "same_period_last_year"
    if re.search(r"so voi (?:thang|quy|ky|tuan) truoc|so voi (?:thang|quy) vua|tang hay giam|tang giam|bien dong|thay doi so voi|mom|qoq", t):
        return "previous_period"
    return None
