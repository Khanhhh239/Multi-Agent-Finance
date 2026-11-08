"""Regressions for the five observed T0/T9/T1 audit findings of 2026-11-06."""
from io import BytesIO

from fastapi.testclient import TestClient
import pandas as pd
import pytest

from agent1.reconciliation import operations, pipeline
from agent1.reconciliation.pipeline import ObservedSource, ObservedSnapshotBuilder
from agent1_service.api import create_app
from test_t0_ingest_pipeline import invoice, xml


HEADERS = {'Authorization': 'Bearer secret'}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENT1_PSEUDONYMIZE', '0')
    monkeypatch.setattr(operations, 'today', lambda: '2024-03-01')
    monkeypatch.setattr(pipeline, 'today', lambda: '2024-03-01')
    app = create_app(tmp_path/'api', token='secret', firm_id='F')
    with TestClient(app) as client:
        yield client, app.state.store, ObservedSource(app.state.store, 'F')


def ingest(client, table, records):
    return client.post('/ingest', headers=HEADERS, json=dict(table=table, records=records))


def base_invoice(**changes):
    return dict(invoice(gross=110000), available_on='2024-01-01', record_version=1, **changes)


def test_create_promise_preserves_shared_snapshot_and_real_forecast(api, monkeypatch):
    client, store, _ = api
    monkeypatch.setenv('AGENT1_RESEARCH_MODE', '1')
    tables = dict(
        invoices=[base_invoice()],
        bank_txns=[dict(txn_id='B', value_date='2024-02-01', available_on='2024-02-02', amount=1000, memo='1')],
        customers=[dict(customer_id='buyer-1', short='Buyer', available_on='2024-01-01')],
        outflows=[dict(id='O', date='2024-04-01', amount=1000, category='rent', available_on='2024-02-01')],
    )
    for table, rows in tables.items():
        response = ingest(client, table, rows)
        assert response.status_code == 200, response.text
    store.put('F', 'promises', [dict(id='old', invoice_id='i1', customer_id='buyer-1', amount=110000,
        made_date='2024-01-15T00:00:00', promised_date='2024-03-15T00:00:00', available_on='2024-01-15')])
    response = client.post('/promises', headers=HEADERS, json=dict(
        invoice_id='i1', customer_id='buyer-1', amount=110000,
        made_date='2024-02-01T20:00:00Z', promised_date='2024-04-01T00:00:00+07:00'))
    assert response.status_code == 200, response.text
    saved = next(r for r in store.get('F', 'promises') if r['id'] == response.json()['id'])
    assert saved['made_date'] == '2024-02-02' and saved['promised_date'] == '2024-04-01'
    snapshot = client.get('/snapshot?cutoff=2024-03-01', headers=HEADERS)
    assert snapshot.status_code == 200, snapshot.text
    assert len(snapshot.json()['promises']) == 2
    forecast = client.post('/forecast', headers=HEADERS, json=dict(cutoff='2024-03-01', balance=100000))
    assert forecast.status_code == 200, forecast.text
    assert forecast.json()['data_snapshot'] == snapshot.json()['snapshot_hash']
    assert forecast.json()['model'] == 'B1d-fallback'


@pytest.mark.parametrize('table,row,fields', [
    ('bank_txns', dict(txn_id='B', value_date='2024-02-01T20:00:00Z', amount=100, memo='1'), ('value_date',)),
    ('customers', dict(customer_id='C', short='Buyer'), ()),
    ('promises', dict(id='P', invoice_id='i1', customer_id='C', made_date='2024-02-01T20:00:00Z',
                      promised_date='2024-04-01T00:00:00'), ('made_date', 'promised_date')),
    ('outflows', dict(id='O', date='2024-04-01T00:00:00', amount=10, category='rent'), ('date',)),
    ('cash_balances', dict(date='2024-02-01T20:00:00Z', balance=100), ('date',)),
])
def test_json_admission_normalizes_all_shared_date_fields(api, table, row, fields):
    client, store, _ = api
    response = ingest(client, table, [dict(row, available_on='2024-02-02T00:00:00+07:00',
                                          known_at='2024-02-01T20:00:00Z')])
    assert response.status_code == 200, response.text
    saved = store.get('F', table)[0]
    for field in (*fields, 'available_on', 'known_at'):
        assert len(saved[field]) == 10
    assert saved['available_on'] == saved['known_at'] == '2024-02-02'
    response = client.get('/snapshot?cutoff=2024-03-01', headers=HEADERS)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize('value', [None, '', 'invalid', 123, True])
def test_invalid_required_date_is_rejected_before_storage(api, value):
    client, store, _ = api
    response = ingest(client, 'promises', [dict(id='P', invoice_id='i1', customer_id='C',
        made_date=value, promised_date='2024-04-01')])
    assert response.status_code == 422
    assert not store.get('F', 'promises')


def test_invoice_dates_are_canonical_and_changed_optional_date_is_not_discarded(api):
    client, store, _ = api
    row = base_invoice()
    row.update(issue_date='2024-01-01T00:00:00', due_date='2024-02-01T00:00:00',
               credit_note_date='2024-01-15T20:00:00Z', credit_note=1000,
               ledger_clear_date='2024-02-01T00:00:00', available_on='2024-02-02T00:00:00')
    assert ingest(client, 'invoices', [row]).status_code == 200
    saved = store.get('F', 'invoices')[0]
    assert saved['credit_note_date'] == '2024-01-16'
    for field in ('issue_date', 'due_date', 'ledger_clear_date', 'available_on'):
        assert len(saved[field]) == 10
    assert ingest(client, 'invoices', [dict(row, credit_note_date='2024-01-17')]).status_code == 422


def test_legacy_timestamp_promise_is_read_without_rewriting_history(api):
    client, store, source = api
    old = dict(id='P', invoice_id='i1', customer_id='C', made_date='2024-02-01T00:00:00',
               promised_date='2024-04-01T00:00:00', available_on='2024-02-01')
    store.put('F', 'promises', [old])
    before = store.connection.execute('SELECT kind,id,payload FROM records ORDER BY kind,id').fetchall()
    response = client.get('/snapshot?cutoff=2024-03-01', headers=HEADERS)
    assert response.status_code == 200, response.text
    assert source.task_records('2024-03-01')['promises'][0]['made_date'] == '2024-02-01'
    assert store.get('F', 'promises') == [old]
    assert before == store.connection.execute('SELECT kind,id,payload FROM records ORDER BY kind,id').fetchall()


@pytest.mark.parametrize('change', [
    dict(due_date='2024-04-01'), dict(customer_id='another-buyer'),
    dict(credit_note=1000), dict(credit_note_date='2024-01-20'),
    dict(ledger_clear_date='2024-01-20'), dict(adjusts_invoice_id='other'), dict(buyer_name='Changed'),
])
def test_same_version_changed_business_payload_is_rejected_atomically(api, change):
    client, store, _ = api
    original = base_invoice()
    assert ingest(client, 'invoices', [original]).status_code == 200
    before = store.get('F', 'invoices')
    changed = dict(original, **change, available_on='2024-03-01')
    response = ingest(client, 'invoices', [base_invoice(invoice_no='2', invoice_id='i2'), changed])
    assert response.status_code == 422, response.text
    assert 'record_version' in response.json()['detail']
    assert store.get('F', 'invoices') == before
    assert len(store.get('F', 'invoice_versions')) == 1


def test_exact_retry_preserves_original_history_but_higher_version_applies_change(api):
    client, store, source = api
    original = base_invoice()
    assert ingest(client, 'invoices', [original]).status_code == 200
    before = source.view('2024-02-01')['snapshot_hash']
    retry = dict(original, source_file='another-export.json', source_row=99, source_sha256='new-file-hash',
                 available_on='2024-02-15')
    assert ingest(client, 'invoices', [retry]).status_code == 200
    assert len(store.get('F', 'invoice_versions')) == 1
    revision = dict(original, record_version=2, available_on='2024-03-01', due_date='2024-04-01')
    assert ingest(client, 'invoices', [revision]).status_code == 200
    assert store.get('F', 'invoices')[0]['due_date'] == '2024-04-01'
    assert source.view('2024-02-01')['snapshot_hash'] == before


def test_legacy_single_source_retry_checks_every_business_field(api):
    client, store, _ = api
    original = base_invoice()
    assert ingest(client, 'invoices', [original]).status_code == 200
    saved = store.get('F', 'invoices')[0]
    saved.pop('source_payloads')
    saved.pop('term_days')  # Older admission derived this only after a merge.
    store.put('F', 'invoices', [saved])
    assert ingest(client, 'invoices', [original]).status_code == 200
    assert ingest(client, 'invoices', [dict(original, due_date='2024-04-01')]).status_code == 422


def test_xml_and_erp_retries_compare_their_own_facts_after_merge(api):
    client, store, _ = api
    original = base_invoice()
    data = BytesIO()
    pd.DataFrame([dict(original, invoice_id='ERP', customer_id='erp-buyer')]).to_excel(data, index=False)
    def upload(kind, name, content):
        return client.post('/ingest/file', headers=HEADERS,
            data=dict(kind=kind, available_on='2024-01-01'), files={'file': (name, content)})
    for kind, name, content in [('xml', 'invoice.xml', xml(original)), ('ledger_excel', 'erp.xlsx', data.getvalue())]*2:
        response = upload(kind, name, content)
        assert response.status_code == 200, response.text
    assert len(store.get('F', 'invoices')) == 1
    assert len(store.get('F', 'invoice_versions')) == 2
    assert store.get('F', 'invoices')[0]['customer_id'] == 'erp-buyer'
    changed = BytesIO()
    pd.DataFrame([dict(original, invoice_id='ERP', customer_id='different-buyer')]).to_excel(changed, index=False)
    assert upload('ledger_excel', 'erp.xlsx', changed.getvalue()).status_code == 422


def approve_cash(client, amount=110000, key='cash'):
    return client.post('/reconciliation/accept', headers=HEADERS, json=dict(
        idempotency_key=key, reviewed_by='Reviewer', note='Bank advice',
        allocations=[dict(txn_id='B', invoice_id='i1', amount_minor=amount)]))


@pytest.mark.parametrize('change', [dict(issue_date='2024-02-15', due_date='2024-03-15'),
                                   dict(customer_id='another-buyer')])
def test_source_revision_conflict_blocks_snapshot_but_can_be_reversed(api, monkeypatch, change):
    client, store, source = api
    original = base_invoice()
    assert ingest(client, 'invoices', [original]).status_code == 200
    assert ingest(client, 'bank_txns', [dict(txn_id='B', value_date='2024-02-01',
        available_on='2024-02-02', amount=110000, memo='1')]).status_code == 200
    accepted = approve_cash(client)
    assert accepted.status_code == 200, accepted.text
    before = source.view('2024-03-01')['snapshot_hash']
    revision = dict(original, **change, record_version=2, available_on='2024-03-02')
    assert ingest(client, 'invoices', [revision]).status_code == 200
    response = client.get('/snapshot?cutoff=2024-03-02', headers=HEADERS)
    assert response.status_code == 422
    assert 'đảo phân bổ' in response.json()['detail']
    assert source.view('2024-03-01')['snapshot_hash'] == before
    assert client.get('/reconciliation/history?cutoff=2024-03-02', headers=HEADERS).status_code == 200
    monkeypatch.setattr(operations, 'today', lambda: '2024-03-02')
    response = client.post('/reconciliation/reverse', headers=HEADERS, json=dict(
        idempotency_key='undo', decision_id=accepted.json()['decision_id'], reviewed_by='Reviewer', note='Source correction'))
    assert response.status_code == 200, response.text
    assert source.view('2024-03-02')['links'].empty
    assert source.view('2024-03-02')['invoices'].amount_open_minor.tolist() == [110000]


@pytest.mark.parametrize('change,conflict', [
    (dict(customer_id='another-buyer'), True), (dict(buyer_mst='0100109106'), True),
    (dict(issue_date='2024-01-02'), True), (dict(due_date='2024-04-01'), False),
])
def test_writeoff_stays_bound_to_its_reviewed_customer_and_document(api, monkeypatch, change, conflict):
    client, store, source = api
    original = base_invoice()
    assert ingest(client, 'invoices', [original]).status_code == 200
    accepted = client.post('/reconciliation/writeoffs', headers=HEADERS, json=dict(
        idempotency_key='w', invoice_id='i1', effective_on='2024-02-20', reviewed_by='Reviewer', source_ref='WO-1'))
    assert accepted.status_code == 200, accepted.text
    event = source.ledger.events()[-1]
    assert event['invoice_context']['customer_id'] == 'buyer-1'
    before = source.view('2024-03-01')['snapshot_hash']
    revision = dict(original, **change, record_version=2, available_on='2024-03-02')
    assert ingest(client, 'invoices', [revision]).status_code == 200
    snapshot = client.get('/snapshot?cutoff=2024-03-02', headers=HEADERS)
    assert snapshot.status_code == (422 if conflict else 200), snapshot.text
    assert source.view('2024-03-01')['snapshot_hash'] == before
    if conflict:
        assert 'đảo write-off' in snapshot.json()['detail']
        monkeypatch.setattr(operations, 'today', lambda: '2024-03-02')
        response = client.post('/reconciliation/reverse', headers=HEADERS, json=dict(
            idempotency_key='undo', decision_id=accepted.json()['decision_id'], reviewed_by='Reviewer', note='Source correction'))
        assert response.status_code == 200, response.text
        assert source.view('2024-03-02')['invoices'].closure_type.tolist() == ['open']


@pytest.mark.parametrize('historical_source', [True, False])
def test_legacy_writeoff_uses_retained_history_or_requires_review(api, historical_source):
    client, store, source = api
    original = base_invoice()
    assert ingest(client, 'invoices', [original]).status_code == 200
    # Represents an immutable event written by the older adapter, without scope.
    old = dict(tenant_id='F', action='writeoff', decision_id='W-legacy', invoice_id='i1', amount_minor=110000,
               effective_on='2024-02-20', available_on='2024-03-01', reviewed_by='Reviewer', source_ref='WO-old')
    store.put('F', 't9_events', [dict(id='00000000000000000001', command=old)])
    if historical_source:
        assert source.view('2024-03-01')['invoices'].closure_type.tolist() == ['writeoff']
        revision = dict(original, customer_id='new-buyer', record_version=2, available_on='2024-03-02')
        assert ingest(client, 'invoices', [revision]).status_code == 200
        with pytest.raises(ValueError, match='đảo write-off'):
            source.view('2024-03-02')
    else:
        with store.connection:
            store.connection.execute("DELETE FROM records WHERE kind='invoice_versions'")
        with pytest.raises(ValueError, match='thiếu lịch sử'):
            source.view('2024-03-01')
    assert source.ledger.events() == [old]


def test_late_review_of_past_partial_receipt_excludes_only_affected_origins(api):
    client, store, source = api
    assert ingest(client, 'invoices', [base_invoice()]).status_code == 200
    rows = [dict(txn_id='B', value_date='2024-01-10', available_on='2024-01-11', amount=44000, memo='1'),
            dict(txn_id='future', value_date='2024-02-01', available_on='2024-02-02', amount=66000, memo='1')]
    assert ingest(client, 'bank_txns', rows).status_code == 200
    assert approve_cash(client, amount=44000).status_code == 200
    response = client.post('/reconciliation/accept', headers=HEADERS, json=dict(
        idempotency_key='final', reviewed_by='Reviewer', note='Bank advice',
        allocations=[dict(txn_id='future', invoice_id='i1', amount_minor=66000)]))
    assert response.status_code == 200, response.text
    builder = ObservedSnapshotBuilder(source)
    past = builder.snapshot('2024-01-15')
    assert past.amount_open.tolist() == [110000]  # What was known then stays unchanged.
    rows = builder.build(['2024-01-05', '2024-01-10', '2024-01-15'], label_end='2024-03-01')
    assert rows.cutoff.tolist() == [pd.Timestamp('2024-01-05')]
    assert rows.amount_open.tolist() == [110000]
    assert rows.event.tolist() == [1]


def test_legacy_writeoff_cannot_infer_scope_across_same_day_customer_change(api, monkeypatch):
    client, store, source = api
    original = base_invoice()
    assert ingest(client, 'invoices', [original]).status_code == 200
    event = dict(tenant_id='F', action='writeoff', decision_id='W-legacy', invoice_id='i1', amount_minor=110000,
                 effective_on='2024-02-20', available_on='2024-03-01', reviewed_by='Reviewer', source_ref='WO-old')
    store.put('F', 't9_events', [dict(id='00000000000000000001', command=event)])
    revision = dict(original, customer_id='new-buyer', record_version=2, available_on='2024-03-01')
    assert ingest(client, 'invoices', [revision]).status_code == 200
    with pytest.raises(ValueError, match='cùng ngày'):
        source.view('2024-03-01')
    monkeypatch.setattr(operations, 'today', lambda: '2024-03-02')
    operations.reverse(source, 'undo', 'W-legacy', 'Reviewer', 'Uncertain historic scope')
    assert source.ledger.events()[0] == event
    assert source.view('2024-03-02')['invoices'].closure_type.tolist() == ['open']


def test_known_partial_receipt_uses_remaining_balance_in_training(api, monkeypatch):
    client, store, source = api
    assert ingest(client, 'invoices', [base_invoice()]).status_code == 200
    assert ingest(client, 'bank_txns', [dict(txn_id='B', value_date='2024-01-10',
        available_on='2024-01-11', amount=44000, memo='1')]).status_code == 200
    monkeypatch.setattr(operations, 'today', lambda: '2024-01-12')
    assert approve_cash(client, amount=44000).status_code == 200
    assert ingest(client, 'bank_txns', [dict(txn_id='future', value_date='2024-02-01',
        available_on='2024-02-02', amount=66000, memo='1')]).status_code == 200
    monkeypatch.setattr(operations, 'today', lambda: '2024-03-01')
    response = client.post('/reconciliation/accept', headers=HEADERS, json=dict(
        idempotency_key='final', reviewed_by='Reviewer', note='Bank advice',
        allocations=[dict(txn_id='future', invoice_id='i1', amount_minor=66000)]))
    assert response.status_code == 200, response.text
    rows = ObservedSnapshotBuilder(source).build(['2024-01-15'], label_end='2024-03-01')
    assert rows.amount_open.tolist() == [66000]
    assert rows.event.tolist() == [1] and rows.remaining.tolist() == [17.0]


@pytest.mark.parametrize('change', [dict(known_at='2024-02-03'), dict(remittance=[dict(invoice_id='i1', amount_minor=1000)]),
                                   dict(account_id='other-account'), dict(statement_id='other-statement')])
def test_bank_retry_cannot_silently_discard_changed_matching_or_knowledge_facts(api, change):
    client, store, _ = api
    original = dict(txn_id='B', value_date='2024-02-01', available_on='2024-02-02', amount=1000, memo='1')
    assert ingest(client, 'bank_txns', [original]).status_code == 200
    before = store.get('F', 'bank_txns')
    assert ingest(client, 'bank_txns', [dict(original, **change)]).status_code == 422
    assert store.get('F', 'bank_txns') == before


@pytest.mark.parametrize('kind', ['invoice_revision', 'cancellation'])
def test_invoice_lifecycle_waits_for_later_knowledge_date_in_every_view(api, kind):
    from agent1_service.ingest.invoices import effective_invoices

    client, store, source = api
    original = base_invoice()
    assert ingest(client, 'invoices', [original]).status_code == 200
    if kind == 'invoice_revision':
        row = dict(original, customer_id='buyer-2', record_version=2,
                   available_on='2024-02-10', known_at='2024-03-02')
        assert ingest(client, 'invoices', [row]).status_code == 200
    else:
        row = dict(event_id='cancel', invoice_id='i1', event_type='cancel',
                   event_date='2024-02-01', available_on='2024-02-10', known_at='2024-03-02')
        assert ingest(client, 'invoice_events', [row]).status_code == 200

    versions = store.get('F', 'invoice_versions')
    events = store.get('F', 'invoice_events')
    for cutoff in ('2024-02-29', '2024-03-02'):
        effective = effective_invoices(versions, events, cutoff)
        observed = source.view(cutoff)['invoices']
        response = client.get('/snapshot', headers=HEADERS, params=dict(cutoff=cutoff))
        assert response.status_code == 200, response.text
        if cutoff == '2024-03-02' and kind == 'cancellation':
            assert effective.empty and observed.empty and response.json()['invoices'] == []
        else:
            expected = 'buyer-2' if cutoff == '2024-03-02' else 'buyer-1'
            assert effective.customer_id.tolist() == observed.customer_id.tolist() == [expected]
            assert response.json()['invoices'][0]['customer_id'] == expected


@pytest.mark.parametrize('changed', [False, True])
def test_cancellation_retry_is_idempotent_but_rejects_changed_business_facts(api, changed):
    client, store, _ = api
    assert ingest(client, 'invoices', [base_invoice()]).status_code == 200
    row = dict(event_id='cancel', invoice_id='i1', event_type='cancel',
               event_date='2024-02-01', available_on='2024-02-10')
    assert ingest(client, 'invoice_events', [row]).status_code == 200
    before = store.get('F', 'invoice_events')
    retry = dict(row, event_date='2024-02-02') if changed else dict(row)
    response = ingest(client, 'invoice_events', [retry])
    assert response.status_code == (422 if changed else 200), response.text
    assert store.get('F', 'invoice_events') == before
