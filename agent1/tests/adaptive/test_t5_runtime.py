"""T5 cash conservation, observation clocks and connected import/forecast flow."""

from io import BytesIO

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from agent1.adaptive.data import merge_import, parse_rows, suggested_mapping, validate_dataset
from agent1.adaptive.methods import forecast
from agent1.adaptive.obligations import cash_schedule
from agent1_service.api import create_app
from agent1_service.workspace.forecast_export import workbook_bytes

CUTOFF='2026-02-10'


def expense(identifier='E',**changes):
    return dict(dict(expense_id=identifier,date='2026-02-12',amount=100,
        known_at='2026-02-01',category='rent'),**changes)


def bank(identifier='B',**changes):
    return dict(dict(bank_id=identifier,account='A',date='2026-02-09',direction='out',amount=40,
        known_at='2026-02-09'),**changes)


def payment(identifier='S',**changes):
    return dict(dict(settlement_id=identifier,expense_id='E',bank_id='B',payment_date='2026-02-09',
        amount=40,known_at='2026-02-09'),**changes)


def book():
    return dict(invoices=[dict(invoice_id='I',customer_id='C',amount=100,issue_date='2026-01-01',
        due_date='2026-01-10',known_at='2026-01-01')],
        payments=[dict(payment_id='P',invoice_id='I',payment_date='2026-01-10',known_at='2026-01-10',amount=100)],
        outflows=[],bank=[])


def test_early_partial_payment_reduces_future_cash_without_redebiting_opening_balance():
    data=dict(book(),outflows=[expense()],bank=[bank()],expense_payments=[payment()])
    validate_dataset(data)
    plan=forecast(data,CUTOFF,960,horizon_weeks=2)
    assert plan['weeks'][0]['cash_out']==60 and plan['weeks'][0]['balance']==900
    row=plan['t5']['obligations'][0]
    assert (row['status'],row['settled_amount'],row['remaining_amount'])==('partial',40,60)
    assert plan['cash_decomposition']['outflows'][0]['original_amount']==60
    data['bank'].append(bank('B2',amount=60))
    data['expense_payments'].append(payment('S2',bank_id='B2',amount=60))
    validate_dataset(data)
    assert forecast(data,CUTOFF,900,horizon_weeks=1)['weeks'][0]['cash_out']==0


def test_future_or_late_known_settlement_does_not_change_earlier_forecast():
    data=dict(book(),outflows=[expense()],bank=[bank(known_at='2026-02-11')],
              expense_payments=[payment(known_at='2026-02-11')])
    validate_dataset(data)
    assert cash_schedule(data,CUTOFF)['outflows'][0]['amount']==100
    assert cash_schedule(data,'2026-02-11')['outflows'][0]['amount']==60


def test_overdue_outgoing_is_carried_and_cancelled_remainder_is_not_projected():
    data=dict(book(),outflows=[expense(date='2026-02-09')])
    result=cash_schedule(data,CUTOFF)
    assert result['outflows'][0]['date']=='2026-02-11'
    assert result['obligations'][0]['status']=='overdue'
    assert forecast(data,CUTOFF,1000,horizon_weeks=1)['weeks'][0]['balance']==900
    data=merge_import(data,'outflows',[expense(date='2026-02-09',known_at='2026-02-11',status='cancelled')])
    assert cash_schedule(data,CUTOFF)['outflows'][0]['amount']==100
    assert not cash_schedule(data,'2026-02-11')['outflows']


@pytest.mark.parametrize('change',[
    {'amount':101},{'bank_id':'missing'},{'payment_date':'2026-02-08'},
    {'known_at':'2026-01-31'},{'expense_id':'missing'},
])
def test_invalid_settlement_rejected(change):
    data=dict(book(),outflows=[expense()],bank=[bank(amount=100)],expense_payments=[payment(**change)])
    with pytest.raises(ValueError):validate_dataset(data)


def test_multiple_allocations_cannot_overuse_one_bank_line():
    data=dict(book(),outflows=[expense(),expense('E2')],bank=[bank(amount=50)],
        expense_payments=[payment(),payment('S2',expense_id='E2',amount=20)])
    with pytest.raises(ValueError,match='vượt số tiền'):validate_dataset(data)


def test_actual_payment_cannot_use_wrong_direction_or_modelled_variable_cost():
    for change in ({'direction':'in'},{'component':'variable_cost'}):
        data=dict(book(),outflows=[expense()],bank=[bank(**change)],expense_payments=[payment()])
        with pytest.raises(ValueError):validate_dataset(data)


def test_later_bank_and_obligation_corrections_cannot_fund_earlier_allocations():
    data=dict(book(),outflows=[expense(amount=200,known_at='2026-02-15')],
        bank=[bank(amount=200,known_at='2026-02-15')],expense_payments=[payment(amount=150)])
    data['record_history']=dict(outflows=[expense(),data['outflows'][0]],bank=[bank(),data['bank'][0]])
    with pytest.raises(ValueError,match='được biết'):validate_dataset(data)


def test_settlement_reversal_preserves_previous_forecast_snapshot():
    data=dict(book(),outflows=[expense()],bank=[bank()],expense_payments=[payment()])
    data['record_history']=dict(expense_payments=[payment(),dict(settlement_id='S',known_at='2026-02-11',_deleted=True)])
    data['expense_payments']=[]
    assert cash_schedule(data,CUTOFF)['outflows'][0]['amount']==60
    assert cash_schedule(data,'2026-02-11')['outflows'][0]['amount']==100


def refund(**changes):
    return expense('REFUND',category='vat_refund',source='Approved refund decision',verified=True,
        refund_approved_at='2026-02-10',**changes)


def test_refund_has_own_cash_direction_and_approval_clock_and_is_not_cost_scaled():
    data=dict(book(),outflows=[refund()])
    validate_dataset(data)
    before=forecast(data,'2026-02-09',1000,horizon_weeks=2)
    assert before['weeks'][0]['cash_in']==0
    plan=forecast(data,CUTOFF,1000,horizon_weeks=2,expense_multiplier=3)
    assert plan['weeks'][0]['cash_in']==100 and plan['weeks'][0]['cash_out']==0
    assert plan['weeks'][0]['balance']==1100
    assert plan['cash_decomposition']['totals']['obligation_in']==100
    assert plan['t5']['inflows'][0]['known_at']=='2026-02-10'
    for scenario in plan['cash_decomposition']['timing_comparison']['scenarios']:
        assert scenario['weeks'][0]['cash_in']==100


def test_overdue_refund_requires_new_expected_date_and_receipt_is_subtracted():
    data=dict(book(),outflows=[refund(date='2026-02-10')])
    pending=cash_schedule(data,CUTOFF)
    assert not pending['inflows'] and pending['obligations'][0]['status']=='awaiting_refund_date'
    data['outflows'][0]['forecast_date']='2026-02-13'
    data['bank']=[bank(direction='in',date='2026-02-10',known_at=CUTOFF,cash_flow_class='non_ar')]
    data['expense_payments']=[payment(expense_id='REFUND',payment_date=CUTOFF,known_at=CUTOFF)]
    validate_dataset(data)
    assert cash_schedule(data,CUTOFF)['inflows'][0]['amount']==60
    data['bank'][0]['cash_flow_class']='ar'
    with pytest.raises(ValueError,match='phi công nợ'):validate_dataset(data)


def test_partial_schedule_does_not_claim_full_week_coverage():
    data=dict(book(),outflows=[expense()])
    plan=forecast(data,CUTOFF,1000,horizon_weeks=2)
    assert plan['unknown_outflow_weeks']==[1,2]
    assert plan['weeks'][0]['outflow_status']=='scheduled_unconfirmed'
    confirmed=forecast(data,CUTOFF,1000,horizon_weeks=2,confirmed_weeks=[1,2])
    assert confirmed['unknown_outflow_weeks']==[]
    assert [w['outflow_status'] for w in confirmed['weeks']]==['scheduled','confirmed_zero']


def test_split_contract_replaces_legacy_combined_service_once_and_preserves_earlier_snapshot():
    data=dict(book(),outflows=[expense('COMBINED',category='loan_service',amount=110,source='Loan contract')])
    for identifier,category,amount in [('PRINCIPAL','loan_principal',100),('INTEREST','loan_interest',10)]:
        data=merge_import(data,'outflows',[expense(identifier,category=category,amount=amount,
            known_at=CUTOFF,source='Loan contract',verified=True,replaces_expense_id='COMBINED')])
    assert sum(r['amount'] for r in cash_schedule(data,CUTOFF)['outflows'])==110
    assert cash_schedule(data,CUTOFF)['obligations'][0]['status']=='replaced'
    assert [r['expense_id'] for r in cash_schedule(data,'2026-02-09')['outflows']]==['COMBINED']


def test_csv_maps_extended_schedule_and_parses_false_without_truthiness():
    frame=pd.DataFrame([dict(obligation_id='R',due_date='2026-02-20',known_at='2026-02-01',
        amount=100,category='vat_refund',source='Decision',verified='false',refund_approved_at='2026-02-10')])
    rows,errors,_=parse_rows(frame,'outflows',suggested_mapping(frame.columns,'outflows'),'%Y-%m-%d','plain')
    assert not errors and rows[0]['verified'] is False and rows[0]['refund_approved_at']==CUTOFF
    with pytest.raises(ValueError,match='verified'):validate_dataset(dict(book(),outflows=rows))


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(state_dir=tmp_path/'data',key_dir=tmp_path/'keys',token='test-t5',firm_id='SME')) as client:
        client.headers['Authorization']='Bearer test-t5'
        yield client


def upload(client,kind,rows):
    result=client.post('/v1/imports/preview',files={'file':('t5.csv',pd.DataFrame(rows).to_csv(index=False).encode())},
        data={'kind':kind,'date_format':'%Y-%m-%d','number_format':'plain'})
    assert result.status_code==200,result.text
    preview=result.json()
    assert preview['can_commit'],preview
    result=client.post('/v1/imports/'+preview['id']+'/commit')
    assert result.status_code==200,result.text


def test_api_import_settlement_forecast_records_and_export_are_connected(client):
    data=dict(book(),outflows=[expense(),refund()],bank=[bank()],expense_payments=[payment()])
    for kind,rows in data.items():upload(client,kind,rows)
    template=client.get('/v1/templates/expense_payments')
    assert template.status_code==200 and b'settlement_id' in template.content
    records=client.get('/v1/records',params={'kind':'outflows'}).json()
    row=next(r for r in records['rows'] if r['identifier']=='E')
    assert row['remaining_amount']==60 and row['allocated_amount']==40
    detail=client.get('/v1/records/outflows/E').json()
    assert {(r['kind'],r['identifier']) for r in detail['related']}=={('expense_payments','S'),('bank','B')}
    result=client.post('/v1/predict',json=dict(cutoff=CUTOFF,opening_balance=960,payments_complete=True,horizon_weeks=2))
    assert result.status_code==200,result.text
    plan=result.json()
    assert plan['weeks'][0]['balance']==1000
    assert plan['band_protocol']=='cash-v3-t5-ledger'
    export=load_workbook(BytesIO(workbook_bytes(plan,'SME')))
    assert export['Nghĩa vụ T5'].max_row==3 and export['Thanh toán T5'].max_row==2
    assert export['Hoàn thuế theo lịch'].max_row==2
    assert client.delete('/v1/records/outflows/E').status_code==409
    assert client.delete('/v1/records/bank/B').status_code==409
