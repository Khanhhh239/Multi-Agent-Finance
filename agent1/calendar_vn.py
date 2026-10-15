"""Lịch Việt Nam + bộ máy quy tắc nghĩa vụ tất định (T5).

Mọi quy tắc có ngày hiệu lực (effective-dated) để chạy được lịch sử 2019–2026.
Nguồn (thứ cấp, cần đối chiếu văn bản gốc trước khi dùng thật — xem docs/DATA_CARD.md):
  - Luật Quản lý thuế 38/2019/QH14 Điều 44: tờ khai tháng ngày 20 tháng sau; quý: ngày cuối tháng đầu quý sau;
    hạn nộp tiền = hạn nộp tờ khai (Điều 55); trùng ngày nghỉ -> ngày làm việc kế tiếp (Điều 86 TT80/2021,
    Bộ luật Dân sự Điều 148).
  - Nghị định 126/2020 Điều 8, 55: thuế TNDN tạm nộp quý, chậm nhất ngày 30 tháng đầu quý sau;
    quyết toán năm: ngày cuối tháng thứ 3 sau năm tài chính.
  - Ngưỡng khai thuế GTGT theo tháng: doanh thu năm trước > 50 tỷ (NĐ 126/2020 Điều 9).
  - BHXH/BHYT/BHTN: đóng hằng tháng, chậm nhất ngày cuối tháng (QĐ 595/QĐ-BHXH); tỷ lệ 32% (DN 21,5%, NLĐ 10,5%).
  - Lương tối thiểu vùng: NĐ 90/2019, NĐ 38/2022, NĐ 74/2024, NĐ 293/2025.
  - Lệ phí môn bài: hạn 30/01; bãi bỏ từ 01/01/2026 (NQ 198/2025/QH15).
  - Giảm thuế GTGT 2% (10% -> 8%): NQ 43/2022, 101/2023, 110/2023, 142/2024, 174/2024, 204/2025 (tới 31/12/2026);
    không áp dụng cho kim loại & sản phẩm kim loại (giả định đơn giản hoá theo phụ lục loại trừ).
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd

try:
    import holidays as _hol
except ImportError:  # pragma: no cover
    _hol = None

# Mùng 1 Tết âm lịch
LUNAR_NEW_YEAR = {
    2018: "2018-02-16", 2019: "2019-02-05", 2020: "2020-01-25", 2021: "2021-02-12", 2022: "2022-02-01",
    2023: "2023-01-22", 2024: "2024-02-10", 2025: "2025-01-29", 2026: "2026-02-17", 2027: "2027-02-06",
}
# Kỳ nghỉ Tết chính thức theo thông báo Chính phủ (gồm nghỉ bù/hoán đổi)
TET_BREAK = {
    2018: ("2018-02-14", "2018-02-20"), 2019: ("2019-02-02", "2019-02-10"), 2020: ("2020-01-23", "2020-01-29"),
    2021: ("2021-02-10", "2021-02-16"), 2022: ("2022-01-29", "2022-02-06"), 2023: ("2023-01-20", "2023-01-26"),
    2024: ("2024-02-08", "2024-02-14"), 2025: ("2025-01-25", "2025-02-02"), 2026: ("2026-02-14", "2026-02-22"),
    2027: ("2027-02-04", "2027-02-10"),
}

MIN_WAGE = [  # (hiệu lực từ, vùng I..IV) VND/tháng
    ("2019-01-01", (4180000, 3710000, 3250000, 2920000)),
    ("2020-01-01", (4420000, 3920000, 3430000, 3070000)),
    ("2022-07-01", (4680000, 4160000, 3640000, 3250000)),
    ("2024-07-01", (4960000, 4410000, 3860000, 3450000)),
    ("2026-01-01", (5310000, 4730000, 4140000, 3700000)),
]
VAT_REDUCTION = [("2022-02-01", "2022-12-31"), ("2023-07-01", "2023-12-31"), ("2024-01-01", "2024-06-30"),
                 ("2024-07-01", "2024-12-31"), ("2025-01-01", "2025-06-30"), ("2025-07-01", "2026-12-31")]
SI_RATE_EMPLOYER = 0.215
SI_RATE_EMPLOYEE = 0.105
MONTHLY_VAT_THRESHOLD = 50e9
LICENSE_FEE_ABOLISHED = date(2026, 1, 1)


@lru_cache(maxsize=None)
def holiday_set(y0: int = 2017, y1: int = 2028) -> frozenset:
    """Ngày nghỉ lễ: thư viện python-holidays (VN) + kỳ nghỉ Tết chính thức (có nghỉ bù)."""
    s = set()
    if _hol is not None:
        s |= set(_hol.country_holidays("VN", years=range(y0, y1 + 1)).keys())
    else:
        for y in range(y0, y1 + 1):
            for m, d in ((1, 1), (4, 30), (5, 1), (9, 2)):
                s.add(date(y, m, d))
    for a, b in TET_BREAK.values():
        for d in pd.date_range(a, b):
            s.add(d.date())
    return frozenset(s)


def is_business_day(d) -> bool:
    d = pd.Timestamp(d).date()
    return d.weekday() < 5 and d not in holiday_set()


def next_business_day(d, include_self=True):
    d = pd.Timestamp(d).date()
    if not include_self:
        d += timedelta(days=1)
    while not is_business_day(d):
        d += timedelta(days=1)
    return pd.Timestamp(d)


def prev_business_day(d, include_self=True):
    d = pd.Timestamp(d).date()
    if not include_self:
        d -= timedelta(days=1)
    while not is_business_day(d):
        d -= timedelta(days=1)
    return pd.Timestamp(d)


@lru_cache(maxsize=None)
def business_day_index(start="2017-01-01", end="2028-12-31") -> pd.DatetimeIndex:
    days = pd.date_range(start, end)
    hs = holiday_set()
    return pd.DatetimeIndex([d for d in days if d.weekday() < 5 and d.date() not in hs])


def roll_forward_np(dates: np.ndarray) -> np.ndarray:
    """Vector hoá: đẩy mỗi ngày (datetime64[D]) tới ngày làm việc gần nhất >= nó."""
    bd = business_day_index().values.astype("datetime64[D]")
    idx = np.searchsorted(bd, dates.astype("datetime64[D]"), side="left")
    idx = np.clip(idx, 0, len(bd) - 1)
    return bd[idx]


def days_to_tet(d) -> int:
    """Số ngày tới mùng 1 Tết gần nhất (âm = đã qua Tết của năm đó, trong vòng 60 ngày)."""
    d = pd.Timestamp(d)
    best = None
    for y in (d.year - 1, d.year, d.year + 1):
        if y in LUNAR_NEW_YEAR:
            k = (pd.Timestamp(LUNAR_NEW_YEAR[y]) - d).days
            if best is None or (k >= -60 and (best < -60 or abs(k) < abs(best))):
                best = k
    return int(best)


def days_to_tet_np(dates: np.ndarray) -> np.ndarray:
    t = np.array(sorted(pd.Timestamp(v).value for v in LUNAR_NEW_YEAR.values()), dtype="datetime64[ns]")
    t = t.astype("datetime64[D]")
    d = dates.astype("datetime64[D]")
    i = np.searchsorted(t, d, side="left")
    nxt = t[np.clip(i, 0, len(t) - 1)]
    prv = t[np.clip(i - 1, 0, len(t) - 1)]
    dn = (nxt - d).astype(int)
    dp = (prv - d).astype(int)  # <= 0
    return np.where(dp >= -45, dp, dn)


def in_tet_break(d) -> bool:
    d = pd.Timestamp(d)
    a, b = TET_BREAK.get(d.year, (None, None))
    return a is not None and pd.Timestamp(a) <= d <= pd.Timestamp(b)


def min_wage(d, region: int) -> int:
    d = pd.Timestamp(d)
    val = MIN_WAGE[0][1]
    for eff, v in MIN_WAGE:
        if d >= pd.Timestamp(eff):
            val = v
    return val[region - 1]


def vat_rate(d, industry: str) -> float:
    d = pd.Timestamp(d)
    if industry == "steel_metals":
        return 0.10
    for a, b in VAT_REDUCTION:
        if pd.Timestamp(a) <= d <= pd.Timestamp(b):
            return 0.08
    return 0.10


def month_end(y, m) -> pd.Timestamp:
    return pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)


# --------------------------------------------------------------------- T5: lịch nghĩa vụ

def vat_deadline(period_end: pd.Timestamp, monthly: bool) -> pd.Timestamp:
    """Hạn nộp tờ khai + tiền thuế GTGT cho kỳ kết thúc tại period_end."""
    period_end = pd.Timestamp(period_end)
    nxt = period_end + pd.offsets.MonthBegin(1)
    raw = pd.Timestamp(nxt.year, nxt.month, 20) if monthly else month_end(nxt.year, nxt.month)
    return next_business_day(raw)


def cit_provisional_deadline(quarter_end: pd.Timestamp) -> pd.Timestamp:
    q = pd.Timestamp(quarter_end) + pd.offsets.MonthBegin(1)
    return next_business_day(pd.Timestamp(q.year, q.month, 30) if q.month != 2 else month_end(q.year, 2))


def cit_final_deadline(fiscal_year: int) -> pd.Timestamp:
    return next_business_day(month_end(fiscal_year + 1, 3))


def si_deadline(y: int, m: int) -> pd.Timestamp:
    """BHXH tháng m: chậm nhất ngày cuối tháng; nếu là ngày nghỉ, ngân hàng xử lý ngày làm việc trước đó
    (đóng sớm để kịp hạch toán) — giả định thận trọng: lùi về ngày làm việc trước."""
    return prev_business_day(month_end(y, m))


def license_fee_deadline(y: int):
    if date(y, 1, 1) >= LICENSE_FEE_ABOLISHED:
        return None
    return next_business_day(pd.Timestamp(y, 1, 30))


def obligation_schedule(firm: dict, start, end, payroll_by_month: dict | None = None,
                        vat_by_period: dict | None = None, cit_by_quarter: dict | None = None) -> pd.DataFrame:
    """Sinh lịch chi tất định của một doanh nghiệp (ngày, loại, số tiền).

    firm: {revenue_prev_year, payday (int 1..31 hoặc 'eom'), payroll_lag_month (0/1), rent, rent_day,
           loan_payment, loan_day, charter_capital, license_fee}
    payroll_by_month: {(y,m): tổng lương gross}; vat_by_period: {period_end: số thuế};
    cit_by_quarter: {quarter_end: số tạm nộp}.
    """
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    rows = []
    monthly_vat = firm.get("revenue_prev_year", 0) > MONTHLY_VAT_THRESHOLD
    for p in pd.period_range(start - pd.offsets.MonthBegin(2), end, freq="M"):
        y, m = p.year, p.month
        gross = (payroll_by_month or {}).get((y, m), firm.get("payroll_gross", 0.0))
        # lương: payday của tháng (lag 0) hoặc tháng sau (lag 1)
        py, pm = (y, m) if firm.get("payroll_lag_month", 1) == 0 else ((p + 1).year, (p + 1).month)
        pd_ = firm.get("payday", 10)
        pd_ = "eom" if str(pd_) == "eom" else int(pd_)
        raw = month_end(py, pm) if pd_ == "eom" else pd.Timestamp(py, pm, min(int(pd_), month_end(py, pm).day))
        rows.append((prev_business_day(raw), "payroll_net", gross * (1 - SI_RATE_EMPLOYEE), (y, m)))
        rows.append((si_deadline(y, m), "social_insurance", gross * (SI_RATE_EMPLOYER + SI_RATE_EMPLOYEE), (y, m)))
        if firm.get("rent"):
            rows.append((next_business_day(pd.Timestamp(y, m, firm.get("rent_day", 5))), "rent", firm["rent"], (y, m)))
        if firm.get("loan_payment"):
            rows.append((next_business_day(pd.Timestamp(y, m, firm.get("loan_day", 25))), "loan_service",
                         firm["loan_payment"], (y, m)))
        pe = month_end(y, m)
        if monthly_vat or m in (3, 6, 9, 12):
            amt = (vat_by_period or {}).get(pe, np.nan)
            rows.append((vat_deadline(pe, monthly_vat), "vat", amt, (y, m)))
        if m in (3, 6, 9, 12):
            rows.append((cit_provisional_deadline(pe), "cit_provisional", (cit_by_quarter or {}).get(pe, np.nan), (y, m)))
        if m == 1:
            dl = license_fee_deadline(y)
            if dl is not None:
                fee = 3_000_000 if firm.get("charter_capital", 0) > 10e9 else 2_000_000
                rows.append((dl, "license_fee", fee, (y, m)))
    df = pd.DataFrame(rows, columns=["date", "category", "amount", "period"])
    return df[(df["date"] >= start) & (df["date"] <= end)].sort_values("date").reset_index(drop=True)
