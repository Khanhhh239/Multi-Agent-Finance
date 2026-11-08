import pandas as pd
import pytest
from agent1.rules.obligations import extended_schedule,rent_events,loan_events,weekly_extended_cash


def event(**changes):
    return dict(dict(obligation_id='PIT-2025-01',category='pit_withholding',amount=100.,
        due_date='2025-02-20',known_at='2025-02-01',source='Hồ sơ thử đã duyệt',verified=False),**changes)


@pytest.mark.parametrize('category',['pit_withholding','foreign_contractor_tax','salary_bonus','rent_contract','loan_interest','loan_principal'])
def test_declared_amount_not_recalculated_from_statutory_rate(category):
    result=extended_schedule([event(category=category)],asof='2025-02-02',start='2025-02-01',end='2025-02-28')
    assert len(result)==1 and result.amount.sum()==100 and result.direction.iloc[0]=='outflow'


@pytest.mark.parametrize('approval,expected',[(None,0),('2025-02-10',0),('2025-02-01',1)])
def test_refund_is_not_cash_before_known_decision(approval,expected):
    result=extended_schedule([event(category='vat_refund',refund_approved_at=approval)],
        asof='2025-02-02',start='2025-02-01',end='2025-02-28')
    assert len(result)==expected
    if expected:assert result.direction.iloc[0]=='inflow'


def test_future_amendment_cannot_affect_forecast():
    future=event(obligation_id='future',known_at='2025-03-01',amount=999)
    kwargs=dict(asof='2025-02-02',start='2025-02-01',end='2025-02-28')
    pd.testing.assert_frame_equal(extended_schedule([event()],**kwargs),extended_schedule([event(),future],**kwargs))


@pytest.mark.parametrize('change',[{'amount':-1},{'amount':float('nan')},{'amount':float('inf')},
    {'known_at':None},{'due_date':None},{'source':''},{'verified':'false'},{'category':'made_up'}])
def test_invalid_financial_record_rejected(change):
    with pytest.raises(ValueError):extended_schedule([event(**change)],asof='2025-02-02',start='2025-02-01',end='2025-02-28')


def test_duplicates_and_unverified_strict_rejected():
    kwargs=dict(asof='2025-02-02',start='2025-02-01',end='2025-02-28')
    with pytest.raises(ValueError):extended_schedule([event(),event()],**kwargs)
    with pytest.raises(ValueError):extended_schedule([event()],strict=True,**kwargs)


def test_rent_price_step_and_short_month():
    steps=[dict(effective_from='2025-01-01',effective_to='2025-02-28',amount=100),
        dict(effective_from='2025-03-01',amount=150)]
    events=rent_events('rent',steps,months=['2025-02','2025-03'],due_day=31,known_at='2025-01-01',source='HĐ',business_day='none')
    assert [row['amount'] for row in events]==[100,150]
    assert [row['due_date'] for row in events]==[pd.Timestamp('2025-02-28'),pd.Timestamp('2025-03-31')]


def test_loan_principal_and_interest_not_counted_as_combined_service():
    events=loan_events('loan',[dict(date='2025-02-08',principal=1000,interest=70)],known_at='2025-01-01',source='Tín dụng')
    schedule=extended_schedule(events,asof='2025-02-01',start='2025-02-01',end='2025-03-01')
    assert set(schedule.category)=={'loan_interest','loan_principal'}
    inflows,outflows=weekly_extended_cash(schedule,'2025-02-01')
    assert inflows.sum()==0 and outflows[0]==1070 and outflows.sum()==1070


def test_refund_and_bonus_separate_cash_directions_and_cutoff():
    schedule=extended_schedule([event(obligation_id='r',category='vat_refund',refund_approved_at='2025-02-01',due_date='2025-02-08',amount=300),
        event(obligation_id='b',category='salary_bonus',due_date='2025-02-09',amount=125.5)],
        asof='2025-02-01',start='2025-02-01',end='2025-03-01')
    inflows,outflows=weekly_extended_cash(schedule,'2025-02-01')
    assert inflows[0]==300 and outflows[0]==0 and outflows[1]==126
