import pandas as pd
import pytest
from agent1 import calendar_vn as cal
from agent1.rules import load_rules
from agent1.rules.provisioning import suggest_provision


@pytest.mark.parametrize('date,expected', [('2019-12-31',4180000),('2020-01-01',4420000),
    ('2022-06-30',4420000),('2022-07-01',4680000),('2024-06-30',4680000),('2024-07-01',4960000),
    ('2025-12-31',4960000),('2026-01-01',5310000)])
def test_wage_before_after_effective_date(date, expected):
    assert cal.min_wage(date, 1) == expected


@pytest.mark.parametrize('date,expected', [('2022-01-31',.1),('2022-02-01',.08),('2022-12-31',.08),
    ('2023-01-01',.1),('2023-06-30',.1),('2023-07-01',.08),('2024-01-01',.08),('2026-12-31',.08),('2027-01-01',.1)])
def test_vat_effective_boundaries(date, expected):
    assert cal.vat_rate(date, 'textile_clothing') == expected


@pytest.mark.parametrize('region',[0,5,-1])
def test_invalid_wage_region_rejected(region):
    with pytest.raises(ValueError):
        cal.min_wage('2025-01-01',region)


@pytest.mark.parametrize('months,rate',[(5,0),(6,.3),(11,.3),(12,.5),(23,.5),(24,.7),(35,.7),(36,1.)])
def test_provision_uses_calendar_months(months, rate):
    due=pd.Timestamp('2020-02-29')
    inv=pd.DataFrame({'issue_date':[due],'due_date':[due],'amount_gross':[100.]})
    result=suggest_provision(inv,due+pd.DateOffset(months=months))
    assert result.provision_floor_rate.iloc[0] == rate


def test_unverified_rules_are_not_silently_approved():
    with pytest.raises(ValueError,match='xác minh'):
        load_rules('2026-10-16',strict=True)
