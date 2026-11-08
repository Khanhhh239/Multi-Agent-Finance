"""T0 must admit the same invoice facts from JSON/XML/ERP and keep one debt."""
from io import BytesIO
import hashlib
import json
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from agent1.synth.einvoice import invoice_to_xml
from agent1.synth.names import make_mst
from agent1_service.api import create_app
from agent1_service.ingest.invoices import effective_invoices


def invoice(number='1', *, invoice_id='i1', gross=1100, issue='2024-01-01'):
    rng = np.random.default_rng(9)
    net = round(gross / 1.1)
    return dict(invoice_id=invoice_id, customer_id='buyer-1', seller_mst=make_mst(rng),
                buyer_mst=make_mst(rng), symbol='1C24TAA', invoice_no=number,
                issue_date=issue, due_date='2024-02-01', amount_net=net,
                vat=gross - net, amount_gross=gross, currency='VND')


def xml(row, *, nature=None, original=None):
    inv = pd.Series({**row, 'term_days': 30, 'vat_rate': .1})
    seller = pd.Series(dict(name='Seller', mst=row['seller_mst']))
    buyer = pd.Series(dict(name='Buyer', mst=row['buyer_mst']))
    root = ET.fromstring(invoice_to_xml(inv, seller, buyer))
    if nature:
        related = ET.SubElement(root.find('DLHDon/TTChung'), 'TTHDLQuan')
        for tag, value in [('TCHDon', nature), ('KHHDCLQuan', original['symbol']),
                           ('SHDCLQuan', original['invoice_no']), ('NLHDCLQuan', original['issue_date'])]:
            ET.SubElement(related, tag).text = value
    return ET.tostring(root, encoding='utf-8')


def post(client, table, records):
    if table == 'invoices':
        records = [dict(row, available_on=row.get('available_on', row['issue_date'])) for row in records]
    elif table == 'invoice_events':
        records = [dict(row, available_on=row.get('available_on', row['event_date'])) for row in records]
    return client.post('/ingest', headers={'Authorization': 'Bearer secret'},
                       json={'table': table, 'records': records})


def upload(client, kind, content, available_on=None):
    return client.post('/ingest/file', headers={'Authorization': 'Bearer secret'},
                       data={'kind': kind, **({'available_on': available_on} if available_on else {})},
                       files={'file': ('invoice.xml' if kind == 'xml' else 'ledger.xlsx', content)})


def test_json_and_erp_both_use_full_invoice_gate(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENT1_PSEUDONYMIZE', '0')
    app = create_app(tmp_path, token='secret')
    base = invoice()
    with TestClient(app) as client:
        for change in ({'buyer_mst': '123'}, {'vat': 200}, {'amount_gross': 3000}):
            response = post(client, 'invoices', [{**base, **change}])
            assert response.status_code == 422, response.text
        assert post(client, 'invoices', [base]).status_code == 200
        incomplete = pd.DataFrame([{k: base[k] for k in ('invoice_id', 'customer_id', 'issue_date', 'due_date', 'amount_gross')}])
        data = BytesIO()
        incomplete.to_excel(data, index=False)
        assert upload(client, 'ledger_excel', data.getvalue()).status_code == 422
        assert len(app.state.store.get('F000', 'invoices')) == 1


def test_cross_source_reconciliation_and_duplicate_rejection(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENT1_PSEUDONYMIZE', '0')
    app = create_app(tmp_path, token='secret')
    base = invoice()
    with TestClient(app) as client:
        assert upload(client, 'xml', xml(base)).status_code == 200
        ledger = {**base, 'invoice_id': 'erp-99', 'customer_id': 'erp-customer'}
        data = BytesIO()
        pd.DataFrame([ledger]).to_excel(data, index=False)
        result = upload(client, 'ledger_excel', data.getvalue())
        assert result.status_code == 200, result.text
        rows = app.state.store.get('F000', 'invoices')
        assert len(rows) == 1 and rows[0]['invoice_id'] == 'i1'
        assert rows[0]['customer_id'] == 'erp-customer'
        assert rows[0]['sources'] == ['erp', 'xml']
        assert rows[0]['source_ids'] == {'xml': 'i1', 'erp': 'erp-99'}
        assert rows[0]['source_file'] == 'invoice.xml'
        assert rows[0]['source_row'] == 1
        assert rows[0]['source_sha256'] == hashlib.sha256(xml(base)).hexdigest()
        assert set(rows[0]['source_lineage']) == {'xml', 'erp'}
        conflict = {**ledger, 'amount_gross': 2000}
        data = BytesIO()
        pd.DataFrame([conflict]).to_excel(data, index=False)
        assert upload(client, 'ledger_excel', data.getvalue()).status_code == 422
        assert post(client, 'invoices', [{**base, 'invoice_id': 'other'}]).status_code == 422
        assert len(app.state.store.get('F000', 'invoices')) == 1
        event = dict(event_id='cancel-erp', invoice_id='erp-99', event_type='cancel', event_date='2024-01-02')
        assert post(client, 'invoice_events', [event]).status_code == 200
        assert app.state.store.get('F000', 'invoice_events')[0]['invoice_id'] == 'i1'


def test_replacement_adjustment_and_cancellation_are_as_of(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENT1_PSEUDONYMIZE', '0')
    app = create_app(tmp_path, token='secret')
    first = invoice()
    replacement = invoice('2', invoice_id='i2', gross=2200, issue='2024-01-10')
    delta = invoice('3', invoice_id='i3', gross=-550, issue='2024-01-20')
    delta['due_date'] = '2024-02-01'
    with TestClient(app) as client:
        assert upload(client, 'xml', xml(first), '2024-01-01').status_code == 200
        assert upload(client, 'xml', xml(replacement, nature='1', original=first), '2024-01-10').status_code == 200
        assert upload(client, 'xml', xml(delta, nature='2', original=replacement), '2024-01-20').status_code == 200
        stored = app.state.store.get('F000', 'invoices')
        assert len(stored) == 3
        before = effective_invoices(stored, cutoff='2024-01-05')
        assert before.invoice_id.tolist() == ['i1'] and before.amount_gross.iloc[0] == 1100
        after = effective_invoices(stored, cutoff='2024-01-21')
        assert after.invoice_id.tolist() == ['i2'] and after.amount_gross.iloc[0] == 1650
        event = dict(event_id='cancel-i2', invoice_id='i2', event_type='cancel', event_date='2024-01-25')
        assert post(client, 'invoice_events', [event]).status_code == 200
        assert effective_invoices(stored, app.state.store.get('F000', 'invoice_events'), '2024-01-26').empty
        assert post(client, 'invoice_events', [dict(event, event_id='again')]).status_code == 422


def test_unresolved_or_unsupported_xml_relation_is_rejected_atomically(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENT1_PSEUDONYMIZE', '0')
    app = create_app(tmp_path, token='secret')
    original = invoice()
    new = invoice('2', invoice_id='i2', issue='2024-01-10')
    with TestClient(app) as client:
        assert upload(client, 'xml', xml(new, nature='1', original=original)).status_code == 422
        assert upload(client, 'xml', xml(new, nature='3', original=original)).status_code == 422
        assert app.state.store.get('F000', 'invoices') == []


def test_forecast_receives_only_effective_debt_and_rejects_fully_cancelled(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENT1_RESEARCH_MODE', '1')
    observed = []

    def engine(invoices, *_args):
        observed.append(invoices[['invoice_id', 'amount_gross']].to_dict('records'))
        return dict(cutoff='2024-02-01', shortfall_4w=0., shortfall_13w=0.,
                    band=[], collections=[], review_count=0, seconds=0.), {}

    app = create_app(tmp_path, token='secret', engine=engine)
    base = invoice()
    delta = invoice('2', invoice_id='i2', gross=-220, issue='2024-01-10')
    delta.update(adjustment_type='adjustment', adjusts_invoice_id='i1')
    with TestClient(app) as client:
        assert post(client, 'invoices', [base, delta]).status_code == 200
        assert post(client, 'bank_txns', [dict(txn_id='t', value_date='2024-01-03', amount=100, memo='x')]).status_code == 200
        assert post(client, 'customers', [dict(customer_id='buyer-1', short='Buyer')]).status_code == 200
        assert post(client, 'outflows', [dict(date='2024-02-01', amount=10, category='rent')]).status_code == 200
        headers = {'Authorization': 'Bearer secret'}
        response = client.post('/forecast', headers=headers, json={'cutoff': '2024-02-01', 'balance': 100})
        assert response.status_code == 200, response.text
        assert len(observed[-1]) == 1 and observed[-1][0]['invoice_id'] == 'i1'
        assert observed[-1][0]['amount_gross'] == 880
        event = dict(event_id='cancel', invoice_id='i1', event_type='cancel', event_date='2024-02-02')
        assert post(client, 'invoice_events', [event]).status_code == 200
        response = client.post('/forecast', headers=headers, json={'cutoff': '2024-02-03', 'balance': 100})
        assert response.status_code == 422


def test_late_revision_is_not_visible_in_past_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENT1_PSEUDONYMIZE', '0')
    monkeypatch.setenv('AGENT1_RESEARCH_MODE', '1')
    observed = []

    def engine(invoices, *_args):
        observed.append(invoices.amount_gross.tolist())
        return dict(cutoff='2024-02-01', shortfall_4w=0., shortfall_13w=0.,
                    band=[], collections=[], review_count=0, seconds=0.), {}

    app = create_app(tmp_path, token='secret', engine=engine)
    original = invoice()
    original['available_on'] = '2024-01-02'
    revised = dict(original, amount_gross=2200, amount_net=2000, vat=200,
                   record_version=2, available_on='2024-03-01')
    with TestClient(app) as client:
        assert post(client, 'invoices', [original]).status_code == 200
        assert post(client, 'invoices', [revised]).status_code == 200
        versions = app.state.store.get('F000', 'invoice_versions')
        assert len(versions) == 2
        assert effective_invoices(versions, cutoff='2024-02-01').amount_gross.tolist() == [1100]
        assert effective_invoices(versions, cutoff='2024-03-02').amount_gross.tolist() == [2200]
        assert post(client, 'bank_txns', [dict(txn_id='t', value_date='2024-01-03', amount=100, memo='x')]).status_code == 200
        assert post(client, 'customers', [dict(customer_id='buyer-1', short='Buyer')]).status_code == 200
        assert post(client, 'outflows', [dict(date='2024-02-01', amount=10, category='rent')]).status_code == 200
        headers = {'Authorization': 'Bearer secret'}
        for cutoff, expected in (('2024-02-01', 1100), ('2024-03-02', 2200)):
            response = client.post('/forecast', headers=headers, json={'cutoff': cutoff, 'balance': 100})
            assert response.status_code == 200, response.text
            assert observed[-1] == [expected]
        conflict = dict(revised, amount_gross=3300, amount_net=3000, vat=300)
        assert post(client, 'invoices', [conflict]).status_code == 422
        assert len(app.state.store.get('F000', 'invoice_versions')) == 2


def test_strict_json_and_csv_report_source_line(tmp_path, bank_registry):
    app = create_app(tmp_path, token='secret', bank_accounts_file=bank_registry())
    headers = {'Authorization': 'Bearer secret'}
    with TestClient(app) as client:
        for payload in (b'{"table":"invoices","table":"bank_txns","records":[]}',
                        b'{"table":"bank_txns","records":[{"x":{"a":1,"a":2}}]}',
                        b'{"table":"bank_txns","records":[{"amount":NaN}]}',
                        b'{"table":"bank_txns","records":[{"amount":1e999}]}'):
            assert client.post('/ingest', headers=headers, content=payload).status_code == 422
        for raw, marker in ((b'a,a\n1,2\n', 'dòng 1'),
                            (b'a,b\n1\n', 'dòng 2'),
                            (b'a,b\n1,2,3\n', 'dòng 2'),
                            (b'a,b\na,b\n', 'dòng 2')):
            response = client.post('/ingest/file', headers=headers, data={'kind': 'bank_csv'},
                                   files={'file': ('bad.csv', raw, 'text/csv')})
            assert response.status_code == 422
            detail = response.json()['detail']
            assert marker in detail['reason']
            assert detail['sha256'] == hashlib.sha256(raw).hexdigest()
            assert detail['file'] == 'bad.csv'
        bad_value = 'Ngày giao dịch,Số tiền ghi có,Số tiền ghi nợ,Nội dung\n2024-01-01,không rõ,0,thu tiền\n'.encode()
        scope = dict(account_id='A',currency='VND',period_start='2024-01-01',period_end='2024-01-31',
                     opening_balance='0',closing_balance='100',total_credits='100',
                     total_debits='0',expected_accounts=['A'])
        response = client.post('/ingest/file', headers=headers,
                               data={'kind': 'bank_csv', 'statement': json.dumps(scope)},
                               files={'file': ('bank.csv', bad_value, 'text/csv')})
        assert response.status_code == 422
        assert response.json()['detail']['row'] == 2
        quarantine = app.state.store.get('F000', 'ingest_quarantine')
        assert len(quarantine) == 5
        assert next(row for row in quarantine if row['file'] == 'bank.csv')['raw']['Số tiền ghi có'] == 'không rõ'
        assert app.state.store.get('F000', 'bank_txns') == []


def test_late_cancel_event_does_not_change_past(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENT1_PSEUDONYMIZE', '0')
    app = create_app(tmp_path, token='secret')
    base = dict(invoice(), available_on='2024-01-01')
    event = dict(event_id='cancel-late', invoice_id='i1', event_type='cancel',
                 event_date='2024-01-10', available_on='2024-03-01')
    with TestClient(app) as client:
        assert post(client, 'invoices', [base]).status_code == 200
        assert post(client, 'invoice_events', [event]).status_code == 200
        versions = app.state.store.get('F000', 'invoice_versions')
        events = app.state.store.get('F000', 'invoice_events')
        assert effective_invoices(versions, events, '2024-02-01').invoice_id.tolist() == ['i1']
        assert effective_invoices(versions, events, '2024-03-02').empty
