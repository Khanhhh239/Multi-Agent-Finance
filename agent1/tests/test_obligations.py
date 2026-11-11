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


@pytest.mark.parametrize('value',['false','true',0,1,None])
@pytest.mark.parametrize('kind',['rent','loan'])
def test_contract_builders_reject_non_boolean_verification(kind,value):
    with pytest.raises(ValueError,match='verified phải là bool'):
        if kind=='rent':
            rent_events('rent',[dict(effective_from='2025-01-01',amount=100,verified=value)],
                months=['2025-02'],due_day=20,known_at='2025-01-01',source='HĐ')
        else:
            loan_events('loan',[dict(date='2025-02-20',principal=1000,interest=70,verified=value)],
                known_at='2025-01-01',source='Tín dụng')


@pytest.mark.parametrize('verified',[False,True])
@pytest.mark.parametrize('kind',['rent','loan'])
def test_contract_verification_is_preserved_in_strict_schedule(kind,verified):
    if kind=='rent':
        events=rent_events('rent',[dict(effective_from='2025-01-01',amount=100,verified=verified)],
            months=['2025-02'],due_day=20,known_at='2025-01-01',source='HĐ')
    else:
        events=loan_events('loan',[dict(date='2025-02-20',principal=1000,interest=70,verified=verified)],
            known_at='2025-01-01',source='Tín dụng')
    kwargs=dict(asof='2025-02-01',start='2025-02-01',end='2025-02-28',strict=True)
    if verified:
        schedule=extended_schedule(events,**kwargs)
        assert len(schedule)==(1 if kind=='rent' else 2)
        assert schedule.verified.all()
    else:
        with pytest.raises(ValueError,match='chưa xác minh'):
            extended_schedule(events,**kwargs)


def test_refund_schedule_retains_approval_knowledge_when_reused_at_earlier_cutoff():
    schedule=extended_schedule([event(category='vat_refund',refund_approved_at='2025-02-10')],
        asof='2025-02-12',start='2025-02-01',end='2025-02-28')
    assert schedule.known_at.iloc[0]==pd.Timestamp('2025-02-10')
    assert weekly_extended_cash(schedule,'2025-02-02')[0].sum()==0
    assert weekly_extended_cash(schedule,'2025-02-12')[0].sum()==100


def test_versions_select_latest_known_and_ignore_future_same_id():
    versions=[event(),event(amount=150,known_at='2025-02-10'),event(amount=999,known_at='2025-03-01')]
    kwargs=dict(start='2025-02-01',end='2025-02-28')
    assert extended_schedule(versions,asof='2025-02-02',**kwargs).amount.sum()==100
    assert extended_schedule(list(reversed(versions)),asof='2025-02-12',**kwargs).amount.sum()==150
    assert extended_schedule([*versions,event(known_at='2025-02-15',status='cancelled')],
        asof='2025-02-16',**kwargs).empty


def test_rent_amendment_keeps_previous_price_before_knowledge_date():
    steps=[dict(effective_from='2025-01-01',effective_to='2025-12-31',amount=100,known_at='2025-01-01'),
        dict(effective_from='2025-03-01',amount=150,known_at='2025-02-15')]
    kwargs=dict(months=['2025-03'],due_day=5,known_at='2025-01-01',source='HĐ')
    events=rent_events('R',steps,**kwargs)
    assert len(events)==2 and len({r['obligation_id'] for r in events})==1
    for cutoff,expected in [('2025-02-01',100),('2025-02-16',150)]:
        result=extended_schedule(events,asof=cutoff,start='2025-03-01',end='2025-03-31')
        assert result.amount.sum()==expected
    earlier=rent_events('R',steps,asof='2025-02-01',**kwargs)
    assert len(earlier)==1 and earlier[0]['amount']==100


def test_rent_same_knowledge_date_cannot_choose_between_overlapping_prices():
    with pytest.raises(ValueError,match='chồng lấn'):
        rent_events('R',[dict(effective_from='2025-01-01',amount=100),
            dict(effective_from='2025-02-01',amount=150)],months=['2025-03'],due_day=5,
            known_at='2025-01-01',source='HĐ')


def test_loan_installment_ids_do_not_shift_when_future_installments_are_inserted():
    original=[dict(date='2025-02-20',principal=100,interest=10)]
    kwargs=dict(known_at='2025-01-01',source='HĐ')
    first=loan_events('L',original,**kwargs)
    amended=loan_events('L',[dict(date='2025-01-20',principal=50,interest=5,known_at='2025-03-01'),*original],**kwargs)
    assert first==amended[2:]


def test_rescheduled_loan_keeps_original_installment_identity_until_amendment_known():
    rows=loan_events('L',[
        dict(installment_id='P1',date='2025-02-20',principal=100,interest=10,known_at='2025-01-01'),
        dict(installment_id='P1',date='2025-02-25',principal=100,interest=12,known_at='2025-02-15'),
    ],known_at='2025-01-01',source='Loan contract')
    kwargs=dict(start='2025-02-01',end='2025-02-28')
    before=extended_schedule(rows,asof='2025-02-02',**kwargs)
    after=extended_schedule(rows,asof='2025-02-16',**kwargs)
    assert set(before.obligation_id)==set(after.obligation_id)
    assert set(before.date)=={pd.Timestamp('2025-02-20')} and before.amount.sum()==110
    assert set(after.date)=={pd.Timestamp('2025-02-25')} and after.amount.sum()==112
