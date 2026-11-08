"""Kiểm thử T5 (lịch nghĩa vụ theo ví dụ trong văn bản) và T0 (XML hoá đơn điện tử + cổng chất lượng).

Chạy: .venv/Scripts/python.exe -m pytest -q tests
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1 import calendar_vn as cal  # noqa: E402
from agent1.synth.names import valid_mst, make_mst  # noqa: E402
from agent1.data.schema import quality_gate, inject_errors  # noqa: E402
from agent1.synth.einvoice import parse_xml  # noqa: E402
from agent1.paths import SYNTH  # noqa: E402

TS = pd.Timestamp


# ----------------------------------------------------------------------------- T5
@pytest.mark.parametrize("period_end,monthly,expected", [
    ("2025-01-31", True, "2025-02-20"),   # ngày 20 tháng sau, thứ Năm
    ("2024-09-30", True, "2024-10-21"),   # 20/10/2024 là Chủ nhật -> thứ Hai 21/10
    ("2024-06-30", False, "2024-07-31"),  # quý: ngày cuối tháng đầu quý sau
    ("2023-12-31", False, "2024-01-31"),
])
def test_vat_deadline(period_end, monthly, expected):
    assert cal.vat_deadline(TS(period_end), monthly) == TS(expected)


def test_vat_deadline_holiday_shift_q1():
    # Q1: hạn 30/4 trùng nghỉ lễ 30/4–1/5 -> ngày làm việc kế tiếp (không phải 30/4 hay 1/5)
    d = cal.vat_deadline(TS("2025-03-31"), monthly=False)
    assert d > TS("2025-05-01") and cal.is_business_day(d)


def test_cit_provisional():
    assert cal.cit_provisional_deadline(TS("2024-06-30")) == TS("2024-07-30")
    # 30/01/2025 rơi vào kỳ nghỉ Tết Ất Tỵ (25/01–02/02) -> ngày làm việc kế tiếp 03/02/2025
    assert cal.cit_provisional_deadline(TS("2024-12-31")) == TS("2025-02-03")
    assert cal.cit_provisional_deadline(TS("2023-12-31")) == TS("2024-01-30")


def test_cit_final():
    assert cal.cit_final_deadline(2024) == TS("2025-03-31")


def test_license_fee_abolished_2026():
    assert cal.license_fee_deadline(2024) == TS("2024-01-30")
    assert cal.license_fee_deadline(2025) == TS("2025-02-03")  # 30/01/2025 trong kỳ nghỉ Tết
    assert cal.license_fee_deadline(2026) is None


def test_min_wage_effective_dates():
    assert cal.min_wage("2026-01-15", 1) == 5_310_000
    assert cal.min_wage("2024-08-01", 1) == 4_960_000
    assert cal.min_wage("2024-06-30", 4) == 3_250_000


def test_vat_rate_reduction_and_metal_exclusion():
    assert cal.vat_rate("2025-03-01", "textile_clothing") == 0.08
    assert cal.vat_rate("2025-03-01", "steel_metals") == 0.10
    assert cal.vat_rate("2023-03-01", "plastic_rubber") == 0.10


def test_tet_is_not_business_day():
    for d in ("2026-02-16", "2026-02-17", "2025-01-29", "2024-02-12"):
        assert not cal.is_business_day(d)


def test_obligation_schedule_contains_core_items():
    firm = dict(revenue_prev_year=80e9, payday=10, payroll_lag_month=1, rent=50e6, rent_day=5,
                loan_payment=10e6, loan_day=25, charter_capital=5e9, payroll_gross=300e6)
    s = cal.obligation_schedule(firm, "2025-01-01", "2025-06-30", vat_by_period={TS("2025-01-31"): 1e8})
    cats = set(s["category"])
    assert {"payroll_net", "social_insurance", "rent", "loan_service", "vat"} <= cats
    assert (s["date"].map(cal.is_business_day)).all()
    assert TS("2025-02-20") in set(s.loc[s["category"] == "vat", "date"])


# ----------------------------------------------------------------------------- T0
def test_mst_checksum():
    assert valid_mst("0100109106")
    assert not valid_mst("0100109107")
    import numpy as np
    r = np.random.default_rng(0)
    assert all(valid_mst(make_mst(r)) for _ in range(200))


@pytest.mark.skipif(not (SYNTH / "tgt" / "einvoice_xml").exists(), reason="chưa sinh thế giới tgt")
def test_xml_roundtrip_matches_table():
    inv = pd.read_parquet(SYNTH / "tgt" / "invoices.parquet").set_index("invoice_id")
    files = sorted((SYNTH / "tgt" / "einvoice_xml").glob("*.xml"))[:50]
    assert files
    for f in files:
        x = parse_xml(f)
        r = inv.loc[x["invoice_key"]]
        assert x["invoice_no"] == r["invoice_no"]
        assert abs(x["amount_gross"] - r["amount_gross"]) < 1
        assert abs(x["amount_net"] + x["vat"] - x["amount_gross"]) <= 1000


@pytest.mark.skipif(not (SYNTH / "tgt" / "einvoice_xml").exists(), reason="chưa sinh thế giới tgt")
def test_quality_gate_detects_injected_errors():
    rows = [parse_xml(f) for f in sorted((SYNTH / "tgt" / "einvoice_xml").glob("*.xml"))]
    df = pd.DataFrame(rows)
    clean = quality_gate(df, today="2026-10-01")
    assert clean["any_error"].mean() == 0, clean.sum()[clean.sum() > 0]
    dirty, truth = inject_errors(df, rate=0.3, seed=1)
    e = quality_gate(dirty, today="2026-10-01")["any_error"]
    recall = (e & truth).sum() / truth.sum()
    precision = (e & truth).sum() / max(e.sum(), 1)
    assert recall >= 0.95 and precision >= 0.95
