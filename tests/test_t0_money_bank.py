"""Exact source money and complete bank-statement admission."""
import json
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from agent1.synth.names import make_mst
from agent1_service.api import create_app
from agent1_service.ingest.money import minor
from agent1_service.ingest.invoices import effective_invoices
import numpy as np
import pandas as pd


def test_minor_units_reject_float_nonfinite_and_excess_precision():
    assert minor('12.34','USD') == 1234
    assert minor('12.340','USD') == 1234
    assert minor('-12.34','USD') == -1234
    assert minor('12','VND') == 12
    for value,currency in ((12.34,'USD'),('12.341','USD'),('1.1','VND'),
                           ('NaN','USD'),('Infinity','USD'),(True,'VND')):
        with pytest.raises(ValueError):minor(value,currency)


def _invoice():
    rng=np.random.default_rng(9)
    return dict(invoice_id='usd-1',customer_id='buyer',seller_mst=make_mst(rng),
                buyer_mst=make_mst(rng),symbol='1C24TAA',invoice_no='88',
                issue_date='2024-01-01',due_date='2024-02-01',
                amount_net='100.00',vat='10.00',amount_gross='110.00',
                currency='USD',available_on='2024-01-01')


def test_invoice_money_is_exact_in_store_and_json_float_is_rejected(tmp_path,monkeypatch):
    monkeypatch.setenv('AGENT1_PSEUDONYMIZE','0')
    monkeypatch.setenv('AGENT1_RESEARCH_MODE','1')
    app=create_app(tmp_path,token='secret')
    headers={'Authorization':'Bearer secret'}
    row=_invoice()
    with TestClient(app) as client:
        bad=dict(row,amount_net=100.0)
        assert client.post('/ingest',headers=headers,json={'table':'invoices','records':[bad]}).status_code==422
        assert client.post('/ingest',headers=headers,json={'table':'invoices','records':[row]}).status_code==200
        saved=app.state.store.get('F000','invoices')[0]
        assert saved['amount_net']=='100.00'
        assert saved['vat_minor']==1000 and saved['amount_gross_minor']==11000
        bad=dict(row,invoice_id='usd-2',invoice_no='89',amount_gross='110.001')
        assert client.post('/ingest',headers=headers,json={'table':'invoices','records':[bad]}).status_code==422
        workbook=BytesIO()
        pd.DataFrame([dict(row,invoice_id='erp-float',amount_net=100.01)]).to_excel(workbook,index=False)
        response=client.post('/ingest/file',headers=headers,data={'kind':'ledger_excel'},
                             files={'file':('ledger.xlsx',workbook.getvalue())})
        assert response.status_code==422 and 'float' in response.text
        for table,records in (('bank_txns',[dict(txn_id='t',value_date='2024-01-02',amount=1,memo='x')]),
                              ('customers',[dict(customer_id='buyer',short='Buyer')]),
                              ('outflows',[dict(date='2024-02-01',amount=1,category='rent')])):
            assert client.post('/ingest',headers=headers,json={'table':table,'records':records}).status_code==200
        response=client.post('/forecast',headers=headers,json={'cutoff':'2024-02-01','balance':100})
        assert response.status_code==422 and 'tỷ giá' in response.text


def test_xml_and_erp_compare_usd_cents_exactly(tmp_path,monkeypatch):
    monkeypatch.setenv('AGENT1_PSEUDONYMIZE','0')
    app=create_app(tmp_path,token='secret')
    row=_invoice()
    row.update(invoice_id='xml-usd',amount_net='100.01',vat='10.00',amount_gross='110.01')
    xml=(f'<HDon><DLHDon Id="xml-usd"><TTChung><PBan>2.0.0</PBan>'
         f'<KHHDon>{row["symbol"]}</KHHDon><SHDon>{row["invoice_no"]}</SHDon>'
         f'<NLap>{row["issue_date"]}</NLap><DVTTe>USD</DVTTe></TTChung>'
         f'<NDHDon><NBan><MST>{row["seller_mst"]}</MST></NBan>'
         f'<NMua><MST>{row["buyer_mst"]}</MST></NMua><TToan>'
         f'<TgTCThue>100.01</TgTCThue><TgTThue>10.00</TgTThue>'
         f'<TgTTTBSo>110.01</TgTTTBSo></TToan></NDHDon></DLHDon></HDon>').encode()
    headers={'Authorization':'Bearer secret'}
    def ledger(value):
        data=BytesIO()
        fields={k:v for k,v in row.items() if k!='available_on'}
        pd.DataFrame([dict(fields,invoice_id='erp-usd',amount_net=value,
                           amount_gross='110.02' if value=='100.02' else '110.01')]).to_excel(data,index=False)
        return data.getvalue()
    with TestClient(app) as client:
        result=client.post('/ingest/file',headers=headers,data={'kind':'xml'},
                           files={'file':('usd.xml',xml,'application/xml')})
        assert result.status_code==200,result.text
        bad=client.post('/ingest/file',headers=headers,data={'kind':'ledger_excel'},
                        files={'file':('ledger.xlsx',ledger('100.02'))})
        assert bad.status_code==422
        good=client.post('/ingest/file',headers=headers,data={'kind':'ledger_excel'},
                         files={'file':('ledger.xlsx',ledger('100.01'))})
        assert good.status_code==200,good.text
        saved=app.state.store.get('F000','invoices')
        assert len(saved)==1 and saved[0]['amount_net_minor']==10001


def test_signed_usd_adjustment_uses_minor_units(tmp_path,monkeypatch):
    monkeypatch.setenv('AGENT1_PSEUDONYMIZE','0')
    app=create_app(tmp_path,token='secret')
    original=_invoice()
    adjustment=dict(original,invoice_id='usd-2',invoice_no='89',issue_date='2024-01-10',
                    available_on='2024-01-10',amount_net='-0.01',vat='0.00',
                    amount_gross='-0.01',adjustment_type='adjustment',adjusts_invoice_id='usd-1')
    headers={'Authorization':'Bearer secret'}
    with TestClient(app) as client:
        result=client.post('/ingest',headers=headers,json={'table':'invoices','records':[original,adjustment]})
        assert result.status_code==200,result.text
        frame=effective_invoices(app.state.store.get('F000','invoices'),cutoff='2024-01-11')
        assert frame.amount_gross_minor.tolist()==[10999]
        assert frame.amount_gross.tolist()==[109.99]


def _statement(account='A',start='2024-03-01',end='2024-03-31',opening='1000',
               credits='100',debits='20',expected=None):
    return dict(account_id=account,currency='VND',period_start=start,period_end=end,
                opening_balance=opening,closing_balance=str(int(opening)+int(credits)-int(debits)),
                total_credits=credits,total_debits=debits,expected_accounts=expected or ['A'])


def _upload(client,raw,statement,available_on=None):
    return client.post('/ingest/file',headers={'Authorization':'Bearer secret'},
                       data={'kind':'bank_csv','bank':'vcb','statement':json.dumps(statement),
                             'available_on':available_on or statement['period_end']},
                       files={'file':('bank.csv',raw.encode('utf-8'),'text/csv')})


def test_uploaded_account_list_cannot_hide_approved_account(tmp_path,bank_registry):
    registry_file=bank_registry(('A','B'))
    app=create_app(tmp_path,token='secret',bank_accounts_file=registry_file)
    raw='Ngày giao dịch,Số tiền ghi có,Số tiền ghi nợ,Nội dung\n15/03/2024,100,0,thu\n'
    with TestClient(app) as client:
        hidden=_upload(client,raw,_statement(debits='0',expected=['A']))
        assert hidden.status_code==422
        assert 'danh mục tài khoản đã duyệt' in hidden.text
        assert app.state.store.get('F000','bank_statements')==[]
        statement=_statement(debits='0')
        statement.pop('expected_accounts')
        accepted=_upload(client,raw,statement)
        assert accepted.status_code==200,accepted.text
        assert accepted.json()['coverage']['expected_accounts']==['A','B']
        assert accepted.json()['coverage']['missing_from']=={'B':'2024-03-01'}
        assert client.get('/bank/coverage',headers={'Authorization':'Bearer secret'}).json()['verified'] is False


def test_bank_upload_fails_without_reviewed_registry_or_matching_evidence(tmp_path,bank_registry):
    app=create_app(tmp_path,token='secret')
    raw='Ngày giao dịch,Số tiền ghi có,Số tiền ghi nợ,Nội dung\n15/03/2024,100,0,thu\n'
    with TestClient(app) as client:
        assert _upload(client,raw,_statement(debits='0')).status_code==422
        coverage=client.get('/bank/coverage',headers={'Authorization':'Bearer secret'}).json()
        assert coverage['verified'] is False
    registry_file=bank_registry()
    app=create_app(tmp_path / 'other',token='secret',bank_accounts_file=registry_file)
    registry_file.with_name('confirmation.txt').write_bytes(b'changed')
    with TestClient(app) as client:
        assert _upload(client,raw,_statement(debits='0')).status_code==422
        assert app.state.store.get('F000','bank_statements')==[]


def test_registry_expansion_exposes_missing_account_in_existing_period(tmp_path,bank_registry):
    registry_file=bank_registry(('A',))
    app=create_app(tmp_path,token='secret',bank_accounts_file=registry_file)
    raw='Ngày giao dịch,Số tiền ghi có,Số tiền ghi nợ,Nội dung\n15/03/2024,100,0,thu\n'
    headers={'Authorization':'Bearer secret'}
    with TestClient(app) as client:
        assert _upload(client,raw,_statement(debits='0')).status_code==200
        assert client.get('/bank/coverage',headers=headers).json()['verified'] is True
        bank_registry(('A','B'))
        coverage=client.get('/bank/coverage',headers=headers).json()
        assert coverage['verified'] is False
        assert coverage['missing_from']=={'B':'2024-03-01'}


def test_statement_checks_both_sides_and_account_coverage(tmp_path,monkeypatch,bank_registry):
    monkeypatch.setenv('AGENT1_RESEARCH_MODE','1')
    def engine(*_args):
        return dict(cutoff='2024-03-31',shortfall_4w=0.,shortfall_13w=0.,
                    band=[],collections=[],review_count=0,seconds=0.),{}
    app=create_app(tmp_path,token='secret',engine=engine,
                   bank_accounts_file=bank_registry(('A','B')))
    raw=('Ngày giao dịch,Số tiền ghi có,Số tiền ghi nợ,Nội dung\n'
         '15/03/2024,100,0,thu HD88\n20/03/2024,0,20,phi\n')
    with TestClient(app) as client:
        credit_only='Ngày giao dịch,Số tiền ghi có,Nội dung\n15/03/2024,100,thu\n'
        assert _upload(client,credit_only,_statement(debits='0')).status_code==422
        out_of_period=('Ngày giao dịch,Số tiền ghi có,Số tiền ghi nợ,Nội dung\n'
                       '01/04/2024,100,0,thu\n')
        assert _upload(client,out_of_period,_statement(debits='0')).status_code==422
        bad=_statement();bad['closing_balance']='999'
        assert _upload(client,raw,bad).status_code==422
        bad=_statement(credits='101')
        assert _upload(client,raw,bad).status_code==422
        assert app.state.store.get('F000','bank_txns')==[]
        response=_upload(client,raw,_statement(expected=['A','B']))
        assert response.status_code==200,response.text
        assert response.json()['accepted']==1
        assert response.json()['coverage']['missing_from']=={'B':'2024-03-01'}
        assert len(app.state.store.get('F000','bank_entries'))==2
        assert len(app.state.store.get('F000','bank_txns'))==1
        assert client.get('/bank/coverage',headers={'Authorization':'Bearer secret'}).json()['verified'] is False
        invoice=dict(_invoice(),currency='VND',amount_net=100,vat=10,amount_gross=110,
                     issue_date='2024-03-01',due_date='2024-04-01',available_on='2024-03-01')
        headers={'Authorization':'Bearer secret'}
        for table,records in (('invoices',[invoice]),('customers',[dict(customer_id='buyer',short='Buyer')]),
                              ('outflows',[dict(date='2024-03-31',amount=1,category='rent')])):
            assert client.post('/ingest',headers=headers,json={'table':table,'records':records}).status_code==200
        forecast=lambda:client.post('/forecast',headers=headers,json={'cutoff':'2024-03-31','balance':100})
        assert forecast().status_code==422
        second=_statement(account='B',expected=['A','B'])
        assert _upload(client,raw,second).status_code==200
        assert client.get('/bank/coverage',headers={'Authorization':'Bearer secret'}).json()['verified'] is True
        assert forecast().status_code==200


def test_statement_gap_and_opening_discontinuity_are_rejected(tmp_path,bank_registry):
    app=create_app(tmp_path,token='secret',bank_accounts_file=bank_registry())
    header='Ngày giao dịch,Số tiền ghi có,Số tiền ghi nợ,Nội dung\n'
    with TestClient(app) as client:
        first=header+'15/03/2024,100,0,thu\n'
        assert _upload(client,first,_statement(debits='0')).status_code==200
        april=header+'15/04/2024,100,0,thu\n'
        gap=_statement(start='2024-04-02',end='2024-04-30',opening='1100',debits='0')
        assert _upload(client,april,gap).status_code==422
        discontinuous=_statement(start='2024-04-01',end='2024-04-30',opening='999',debits='0')
        assert _upload(client,april,discontinuous).status_code==422
        assert len(app.state.store.get('F000','bank_statements'))==1


def test_late_statement_cannot_enter_earlier_forecast(tmp_path,monkeypatch,bank_registry):
    monkeypatch.setenv('AGENT1_RESEARCH_MODE','1')
    app=create_app(tmp_path,token='secret',engine=lambda *_: ({},{}),
                   bank_accounts_file=bank_registry())
    raw='Ngày giao dịch,Số tiền ghi có,Số tiền ghi nợ,Nội dung\n15/03/2024,100,0,thu\n'
    headers={'Authorization':'Bearer secret'}
    with TestClient(app) as client:
        assert _upload(client,raw,_statement(debits='0'),available_on='2024-04-01').status_code==200
        invoice=dict(_invoice(),currency='VND',amount_net=100,vat=10,amount_gross=110,
                     issue_date='2024-03-01',due_date='2024-04-01',available_on='2024-03-01')
        for table,records in (('invoices',[invoice]),('customers',[dict(customer_id='buyer',short='Buyer')]),
                              ('outflows',[dict(date='2024-03-31',amount=1,category='rent')])):
            assert client.post('/ingest',headers=headers,json={'table':table,'records':records}).status_code==200
        response=client.post('/forecast',headers=headers,json={'cutoff':'2024-03-31','balance':100})
        assert response.status_code==422 and 'Phạm vi sao kê' in response.text
