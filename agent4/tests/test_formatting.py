import math
import pytest
from hypothesis import given,strategies as st
from agent4.engine.formatting import fmt_vnd,fmt_days,fmt_ratio,fmt_pct,fmt_delta,extract_numbers,parse_vn_number

@pytest.mark.parametrize('value',[0,1,-1,999,1000,1234567,-123456789,999999999,1000000000,12345678901])
def test_vnd_roundtrip(value):
    actual = extract_numbers(fmt_vnd(value))
    a = abs(value)
    tolerance = 5e6 if a>=1e9 else 5e5 if a>=1e8 else 5e4 if a>=1e7 else 5e3 if a>=1e6 else .5
    assert len(actual)==1
    assert actual[0]['value']==pytest.approx(value,abs=tolerance,rel=0)

@given(st.integers(min_value=-10**14,max_value=10**14))
def test_exact_money_roundtrip(value):
    assert extract_numbers(fmt_vnd(value,exact=True))[0]['value']==value

@given(st.floats(min_value=-1e5,max_value=1e5,allow_nan=False,allow_infinity=False))
def test_ratio_and_percent_roundtrip(value):
    assert extract_numbers(fmt_ratio(value))[0]['value']==pytest.approx(value,abs=.00500001,rel=0)
    assert extract_numbers(fmt_pct(value))[0]['value']==pytest.approx(value,abs=.05000001,rel=0)
    assert extract_numbers(fmt_days(value))[0]['value']==pytest.approx(value,abs=.50000001 if abs(value)>=10 else .05000001,rel=0)

@pytest.mark.parametrize('text',['KH0012','Q3','1C26TMP-00001','2026-Q3','14/10/2026','10/2026','2026-10-14','NV0012'])
def test_metadata_is_not_a_financial_number(text):
    assert extract_numbers(text)==[]

@pytest.mark.parametrize('text,value',[('1.25',1.25),('-1.25',-1.25),('1.234,56',1234.56),('−12,5',-12.5),('1.234.567 đ',1234567)])
def test_decimal_parsing(text,value):
    assert extract_numbers(text)[0]['value']==value

def test_delta_units_and_missing():
    assert fmt_delta(1.2,'%')=='+1,2 điểm %'
    assert fmt_delta(-1200000,'VND')=='-1,2 triệu đồng'
    assert extract_numbers(fmt_vnd(None))==[]
    assert extract_numbers(fmt_pct(math.nan))==[]
