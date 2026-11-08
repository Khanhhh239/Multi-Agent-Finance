"""Independent cash, knowledge-time and service regression checks for the T9 port."""
from pathlib import Path
import hashlib
import json

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import pandas as pd
import pytest

from agent1.reconciliation import operations
from agent1.reconciliation.pipeline import ObservedSource, ObservedSnapshotBuilder
from agent1_service.api import create_app
from agent1_service.store import Store


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setattr(operations, 'today', lambda: '2024-03-01')
    store = Store(tmp_path/'state'/'agent1.db', Fernet.generate_key())
    store.put('F', 'invoices', [dict(id='I1', invoice_id='I1', firm_id='F', customer_id='C',
        invoice_no='INV-001', issue_date='2024-01-01', due_date='2024-02-01',
        amount_gross=100000, amount_gross_minor=100000, available_on='2024-01-01', currency='VND')])
    store.put('F', 'customers', [dict(id='C', customer_id='C', short='Buyer', available_on='2024-01-01')])
    store.put('F', 'bank_txns', [dict(id='B1', txn_id='B1', firm_id='F', value_date='2024-02-01',
        amount=100000, amount_minor=100000, available_on='2024-02-02', currency='VND',
        memo='TT INV-001', counterparty='Buyer', direction='in')])
    yield ObservedSource(store, 'F')
    store.connection.close()


def test_proposal_does_not_create_cash_labels_and_port_preserves_money(source):
    proposal = operations.propose(source, '2024-03-01')
    assert proposal['method'] == 'constrained_flow'
    assert proposal['allocations'][0]['amount_minor'] == 100000
    assert source.view('2024-03-01')['links'].empty
    assert source.view('2024-03-01')['invoices'].iloc[0].amount_open_minor == 100000
    assert source.ledger.events() == []


def test_acceptance_is_idempotent_encrypted_and_not_visible_in_the_past(source):
    proposal = operations.propose(source, '2024-03-01')
    first = operations.accept(source, 'accept-1', 'Reviewer', proposal_id=proposal['id'])
    again = operations.accept(source, 'accept-1', 'Reviewer', proposal_id=proposal['id'])
    assert again['replayed'] and again['decision_id'] == first['decision_id']
    before, after = source.view('2024-02-29'), source.view('2024-03-01')
    assert before['links'].empty and before['invoices'].paid_date_est.isna().all()
    assert after['links'].amount_minor.sum() == 100000
    assert after['links'].known_at.iloc[0] == pd.Timestamp('2024-03-01')
    assert after['invoices'].paid_date_est.iloc[0] == pd.Timestamp('2024-02-01')
    payload = source.store.connection.execute("SELECT payload FROM records WHERE kind='t9_events'").fetchone()[0]
    assert b'Reviewer' not in payload
    with pytest.raises(ValueError, match='Idempotency'):
        operations.accept(source, 'accept-1', 'Different reviewer', proposal_id=proposal['id'])


def test_reversal_keeps_cash_and_old_snapshot_but_reopens_invoice(source, monkeypatch):
    proposal = operations.propose(source, '2024-03-01')
    result = operations.accept(source, 'a', 'Reviewer', proposal_id=proposal['id'])
    old = source.view('2024-03-01')['snapshot_hash']
    monkeypatch.setattr(operations, 'today', lambda: '2024-03-02')
    operations.reverse(source, 'r', result['decision_id'], 'Reviewer', 'Incorrect remittance')
    assert source.view('2024-03-01')['snapshot_hash'] == old
    assert source.view('2024-03-02')['invoices'].iloc[0].amount_open_minor == 100000
    assert source.view('2024-03-02')['gold']['bank_movements'][0]['net_minor'] == 100000
    assert operations.reverse(source, 'r', result['decision_id'], 'Reviewer', 'Incorrect remittance')['replayed']


def test_ambiguous_reference_requires_review_and_manual_evidence(source):
    invoice = source.store.get('F', 'invoices')[0]
    source.store.put('F', 'invoices', [dict(invoice, id='I2', invoice_id='I2', invoice_no='INV-002')])
    proposal = operations.propose(source, '2024-03-01')
    assert not proposal['allocations']
    with pytest.raises(ValueError, match='ghi chú'):
        operations.accept(source, 'm', 'Reviewer', allocations=[dict(txn_id='B1', invoice_id='I1', amount_minor=100000)])
    operations.accept(source, 'm', 'Reviewer', allocations=[dict(txn_id='B1', invoice_id='I1', amount_minor=100000)],
                      note='Remittance advice document 123')
    assert source.view('2024-03-01')['invoices'].set_index('invoice_id').loc['I2','amount_open_minor'] == 100000


def test_overallocation_and_stale_proposal_do_not_write_any_events(source):
    proposal = operations.propose(source, '2024-03-01')
    with pytest.raises(ValueError, match='vượt'):
        operations.accept(source, 'bad', 'Reviewer', allocations=[dict(txn_id='B1', invoice_id='I1', amount_minor=100001)], note='Evidence')
    assert not source.ledger.events()
    bank = source.store.get('F','bank_txns')[0]
    source.store.put('F','bank_txns',[dict(bank,memo='changed')])
    with pytest.raises(ValueError, match='đã cũ'):
        operations.accept(source, 'old', 'Reviewer', proposal_id=proposal['id'])
    assert not source.ledger.events()


def test_partial_cash_and_writeoff_remain_different_outcomes(source, monkeypatch):
    operations.accept(source, 'partial', 'Reviewer', allocations=[dict(txn_id='B1', invoice_id='I1', amount_minor=40000)], note='Partial payment confirmation')
    view = source.view('2024-03-01')
    assert view['invoices'].paid_date_est.isna().all()
    assert view['invoices'].iloc[0].amount_open_minor == 60000
    monkeypatch.setattr(operations, 'today', lambda: '2024-03-03')
    operations.writeoff(source, 'w', 'I1', '2024-03-02', 'Reviewer', 'Decision WO-1')
    assert source.view('2024-03-02')['invoices'].writeoff_date.isna().all()
    after = source.view('2024-03-03')
    assert after['invoices'].iloc[0].closure_type == 'writeoff'
    assert after['invoices'].paid_date_est.isna().all()
    assert after['links'].amount_minor.sum() == 40000
    assert after['gold']['bank_movements'][0]['net_minor'] == 100000


def test_builder_never_uses_late_known_allocations_as_past_features(source):
    operations.accept(source, 'partial', 'Reviewer', allocations=[dict(txn_id='B1', invoice_id='I1', amount_minor=40000)], note='Receipt advice')
    builder = ObservedSnapshotBuilder(source)
    old = builder.snapshot('2024-02-15').iloc[0]
    new = builder.snapshot('2024-03-01').iloc[0]
    assert pd.isna(old.paid_frac_so_far) and old.amount_open == 100000
    assert new.paid_frac_so_far == .4 and new.amount_open == 60000


@pytest.mark.parametrize('kind', ['invoices', 'bank_txns'])
def test_source_waits_for_both_availability_and_knowledge_date(source, kind):
    row = source.store.get('F', kind)[0]
    source.store.put('F', kind, [dict(row, known_at='2024-03-02')])
    view = source.view('2024-03-01')
    if kind == 'invoices':
        assert view['invoices'].empty
    else:
        assert not view['bank']
    assert source.propose('2024-03-01')['allocations'] == []
    later = source.view('2024-03-02')
    assert len(later['invoices']) == len(later['bank']) == 1


def test_noncash_closed_invoice_does_not_inflate_open_portfolio_features(source):
    operations.accept(source, 'partial', 'Reviewer',
        allocations=[dict(txn_id='B1', invoice_id='I1', amount_minor=40000)], note='Receipt advice')
    invoice = source.store.get('F', 'invoices')[0]
    source.store.put('F', 'invoices', [
        dict(invoice, credit_note=60000, credit_note_date='2024-03-02'),
        dict(invoice, id='I2', invoice_id='I2', invoice_no='INV-002'),
    ])
    row = ObservedSnapshotBuilder(source).snapshot('2024-03-02').iloc[0]
    assert row.invoice_id == 'I2' and row.amount_open == 100000
    assert row.c_open_n == row.f_open_n == 1


def test_observed_vnd_snapshot_keeps_exact_one_dong_residual(source):
    invoice = source.store.get('F', 'invoices')[0]
    source.store.put('F', 'invoices', [dict(invoice, credit_note=99999, credit_note_date='2024-03-01')])
    view = source.view('2024-03-01')
    assert view['invoices'].iloc[0].amount_open_minor == 1
    rows = ObservedSnapshotBuilder(source).snapshot('2024-03-01')
    assert rows.invoice_id.tolist() == ['I1'] and rows.amount_open.tolist() == [1]


def test_later_knowledge_date_controls_credit_labels_and_outcome_provenance(source):
    operations.accept(source, 'partial', 'Reviewer',
        allocations=[dict(txn_id='B1', invoice_id='I1', amount_minor=40000)], note='Receipt advice')
    invoice = source.store.get('F', 'invoices')[0]
    source.store.put('F', 'invoice_versions', [
        dict(invoice, id='I1:1', revision=1),
        dict(invoice, id='I1:2', revision=2, credit_note=60000, credit_note_date='2024-01-20',
             available_on='2024-01-20', known_at='2024-03-03'),
    ])
    assert source.view('2024-03-02')['invoices'].iloc[0].amount_open_minor == 60000
    view = source.view('2024-03-03')
    assert view['invoices'].iloc[0].outcome_known_at == '2024-03-03'
    assert view['noncash_changes']['I1'][0]['available_on'] == '2024-03-03'
    assert ObservedSnapshotBuilder(source).build(['2024-01-25'], label_end='2024-03-03').empty


def test_late_known_past_settlement_is_not_a_future_payment_training_label(source):
    proposal = operations.propose(source, '2024-03-01')
    operations.accept(source, 'a', 'Reviewer', proposal_id=proposal['id'])
    builder = ObservedSnapshotBuilder(source)
    assert not builder.snapshot('2024-02-15').empty
    assert builder.build(['2024-02-15'], label_end='2024-03-01').empty
    trained = builder.build(['2024-01-15'], label_end='2024-03-01')
    assert trained.event.tolist() == [1]
    assert trained.remaining.tolist() == [17.0]


def test_non_ar_and_cross_tenant_observations_are_not_silently_matched(source):
    bank = source.store.get('F','bank_txns')[0]
    source.store.put('F','bank_txns',[dict(bank,cash_flow_class='financing')])
    assert not source.propose('2024-03-01')['allocations']
    with pytest.raises(ValueError, match='không phải'):
        operations.accept(source, 'a', 'Reviewer', allocations=[dict(txn_id='B1',invoice_id='I1',amount_minor=1)], note='Evidence')
    source.store.put('F','bank_txns',[dict(bank,firm_id='OTHER')])
    with pytest.raises(ValueError, match='doanh nghiệp khác'):
        source.view('2024-03-01')


def test_upstream_source_files_keep_their_recorded_hashes():
    root = Path(__file__).resolve().parents[1]/'agent1/reconciliation/_thang'
    provenance = json.loads((root/'provenance.json').read_text(encoding='utf-8'))
    assert provenance['commit'] == '89c144ba3b3d2e7d79d8cb70dc7baf99dc319268'
    for path, digest in provenance['source_sha256'].items():
        assert hashlib.sha256((root/Path(path).name).read_bytes()).hexdigest() == digest


def test_nightly_uses_the_same_credit_adjusted_debt_and_never_calls_legacy_t9(source, monkeypatch):
    from agent1_service.jobs.nightly import run
    from agent1 import api_surface
    invoice=source.store.get('F','invoices')[0]
    source.store.put('F','invoices',[dict(invoice,credit_note=20000,credit_note_date='2024-02-01')])
    operations.accept(source,'partial','Reviewer',allocations=[dict(txn_id='B1',invoice_id='I1',amount_minor=40000)],note='Advice')
    def forbidden(*args,**kwargs):
        raise AssertionError('Live pipeline must not call legacy T9')
    monkeypatch.setattr(api_surface,'Reconciler',forbidden)
    view=source.view('2024-03-01')
    bank=pd.DataFrame(view['bank']);bank['value_date']=pd.to_datetime(bank.value_date)
    result,args=run(view['invoices'],bank,pd.DataFrame(),None,pd.DataFrame(),'2024-03-01',500000,
                    observed_source=source)
    assert args['open_df'].amount_open.tolist()==[40000]
    assert result['data_snapshot']==view['snapshot_hash']
    assert result['reconciliation']=='accepted_ledger'


def test_no_open_invoices_still_forecasts_remaining_cash_without_recounting_receipts(source):
    from agent1_service.jobs.nightly import run
    proposal=operations.propose(source,'2024-03-01')
    operations.accept(source,'a','Reviewer',proposal_id=proposal['id'])
    view=source.view('2024-03-01')
    bank=pd.DataFrame(view['bank']);bank['value_date']=pd.to_datetime(bank.value_date)
    result,args=run(view['invoices'],bank,pd.DataFrame(),None,pd.DataFrame(),'2024-03-01',100000,
                    observed_source=source)
    assert args['open_df'].empty
    assert all(r['P50']==100000 for r in result['band'])


def test_writeoff_can_be_reversed_without_rewriting_old_snapshot(source,monkeypatch):
    operations.writeoff(source,'w','I1','2024-02-20','Reviewer','WO-1')
    event=source.view('2024-03-01')['gold']['writeoffs'][0]
    monkeypatch.setattr(operations,'today',lambda:'2024-03-02')
    operations.reverse(source,'rw',event['decision_id'],'Reviewer','Incorrect decision')
    assert source.view('2024-03-01')['invoices'].closure_type.tolist()==['writeoff']
    assert source.view('2024-03-02')['invoices'].closure_type.tolist()==['open']


def test_service_review_snapshot_strict_money_and_authentication(tmp_path, monkeypatch):
    monkeypatch.setattr(operations, 'today', lambda: '2024-03-01')
    monkeypatch.setenv('AGENT1_PSEUDONYMIZE','0')
    app = create_app(tmp_path/'api', token='secret', firm_id='F')
    store = app.state.store
    store.put('F','invoices',[dict(id='I1',invoice_id='I1',firm_id='F',customer_id='C',invoice_no='INV-1',
        issue_date='2024-01-01',due_date='2024-02-01',amount_gross=100000,currency='VND',available_on='2024-01-01')])
    store.put('F','bank_txns',[dict(id='B1',txn_id='B1',firm_id='F',value_date='2024-02-01',amount=100000,
        available_on='2024-02-02',memo='INV-1',counterparty='',currency='VND')])
    headers={'Authorization':'Bearer secret'}
    with TestClient(app) as client:
        assert client.get('/snapshot?cutoff=2024-03-01').status_code == 401
        proposal = client.post('/reconciliation/run',headers=headers,json={'cutoff':'2024-03-01'})
        assert proposal.status_code == 200, proposal.text
        body=dict(idempotency_key='a',reviewed_by='Reviewer',proposal_id=proposal.json()['id'])
        accepted=client.post('/reconciliation/accept',headers=headers,json=body)
        assert accepted.status_code == 200, accepted.text
        assert client.post('/reconciliation/accept',headers=headers,json=body).json()['replayed']
        view=client.get('/snapshot?cutoff=2024-03-01',headers=headers).json()
        assert view['invoices'][0]['closure_type'] == 'paid'
        assert view['cash_allocations'][0]['amount_minor'] == 100000
        assert client.get('/snapshot?cutoff=2024-02-15',headers=headers).json()['cash_allocations'] == []
        bad=dict(idempotency_key='bad',reviewed_by='Reviewer',allocations=[dict(txn_id='B1',invoice_id='I1',amount_minor=True)],note='Evidence')
        assert client.post('/reconciliation/accept',headers=headers,json=bad).status_code == 422
        assert client.post('/reconciliation/accept',headers=headers,json=dict(body,available_on='2020-01-01')).status_code == 422


def test_bank_observation_retry_is_idempotent_and_cannot_rewrite_past(tmp_path,monkeypatch):
    monkeypatch.setenv('AGENT1_PSEUDONYMIZE','0')
    app=create_app(tmp_path/'api',token='secret')
    headers={'Authorization':'Bearer secret'}
    row=dict(txn_id='B1',value_date='2024-02-01',available_on='2024-02-02',amount=100000,memo='INV-1')
    with TestClient(app) as client:
        body=dict(table='bank_txns',records=[row])
        assert client.post('/ingest',headers=headers,json=body).status_code==200
        assert client.post('/ingest',headers=headers,json=body).status_code==200
        assert len(app.state.store.get('F000','bank_txns'))==1
        changed=dict(table='bank_txns',records=[dict(row,amount=90000)])
        assert client.post('/ingest',headers=headers,json=changed).status_code==422
        assert app.state.store.get('F000','bank_txns')[0]['amount_minor']==100000
        mismatch=dict(table='bank_txns',records=[dict(row,txn_id='B2',amount_minor=200000)])
        assert client.post('/ingest',headers=headers,json=mismatch).status_code==422
        assert len(app.state.store.get('F000','bank_txns'))==1


def test_credit_only_closure_censors_cash_training_and_never_creates_a_receipt(source):
    invoice=source.store.get('F','invoices')[0]
    source.store.put('F','invoice_versions',[
        dict(invoice,id='I1:1',revision=1),
        dict(invoice,id='I1:2',revision=2,credit_note=100000,credit_note_date='2024-02-20',available_on='2024-02-20'),
    ])
    view=source.view('2024-03-01')
    assert view['links'].empty
    assert view['invoices'].paid_date_est.isna().all()
    assert view['invoices'].closure_type.tolist()==['credit_note']
    training=ObservedSnapshotBuilder(source).build(['2024-01-15'],label_end='2024-03-01')
    assert training.event.tolist()==[0]
    assert training.obs_window.tolist()==[36.0]


def test_changed_t0_document_cannot_apply_an_old_proposal(source):
    proposal=operations.propose(source,'2024-03-01')
    invoice=source.store.get('F','invoices')[0]
    source.store.put('F','invoices',[dict(invoice,amount_gross=200000,amount_gross_minor=200000)])
    with pytest.raises(ValueError,match='đã cũ'):
        operations.accept(source,'a','Reviewer',proposal_id=proposal['id'])
    assert not source.ledger.events()


def test_task_views_share_cutoff_and_do_not_treat_a_claimed_promise_as_verified(source):
    source.store.put('F','outflows',[
        dict(id='rent',firm_id='F',date='2024-03-15',amount=1000,category='rent',available_on='2024-02-01'),
        dict(id='late',firm_id='F',date='2024-03-16',amount=999999,category='rent',available_on='2024-04-01'),
    ])
    source.store.put('F','promises',[dict(id='ptp',invoice_id='I1',customer_id='C',made_date='2024-02-01',
        promised_date='2024-02-15',available_on='2024-02-01',kept=True)])
    bundle=source.task_tables('2024-03-01')
    assert bundle['outflows'].amount.tolist()==[1000]
    assert bundle['outflows'].known_at.tolist()==[pd.Timestamp('2024-02-01')]
    assert bundle['promises'].kept.isna().all()


def test_latent_synthetic_outcomes_cannot_become_operational_cash_labels(source):
    invoice=source.store.get('F','invoices')[0]
    source.store.put('F','invoices',[dict(invoice,paid_date_true='2024-01-02',writeoff_date='2024-01-03',
                                         cash_received_amount=100000,remaining_amount=0)])
    view=source.view('2024-03-01')
    assert view['invoices'].paid_date_est.isna().all() and view['invoices'].writeoff_date.isna().all()
    assert view['invoices'].amount_open_minor.tolist()==[100000]
    assert 'paid_date_true' not in view['invoices']


def test_missing_past_statement_coverage_is_not_invented_as_training_history(source,monkeypatch):
    from agent1.reconciliation.pipeline import ObservationGap
    original=source.view
    def gap(cutoff):
        if str(cutoff)[:10]=='2024-02-15':raise ObservationGap('Missing statement')
        return original(cutoff)
    monkeypatch.setattr(source,'view',gap)
    builder=ObservedSnapshotBuilder(source)
    assert builder.build(['2024-01-15'],label_end='2024-02-15').empty
    assert builder.missing_windows==['2024-02-15']


def test_real_forecast_endpoint_shares_the_reviewed_debt_and_snapshot(tmp_path,monkeypatch):
    import numpy as np
    from agent1.synth.names import make_mst
    monkeypatch.setattr(operations,'today',lambda:'2024-03-01')
    monkeypatch.setenv('AGENT1_PSEUDONYMIZE','0')
    monkeypatch.setenv('AGENT1_RESEARCH_MODE','1')
    app=create_app(tmp_path/'api',token='secret',firm_id='F')
    rng=np.random.default_rng(32)
    tables={
        'invoices':[dict(invoice_id='I1',customer_id='C',seller_mst=make_mst(rng),buyer_mst=make_mst(rng),
            symbol='1C24TAA',invoice_no='1',issue_date='2024-01-01',due_date='2024-02-01',
            amount_net=200000,vat=20000,amount_gross=220000,currency='VND',available_on='2024-01-01')],
        'bank_txns':[dict(txn_id='B1',value_date='2024-02-01',available_on='2024-02-02',amount=110000,memo='HD 1')],
        'customers':[dict(customer_id='C',short='Buyer',available_on='2024-01-01')],
        'outflows':[dict(id='rent',date='2024-03-08',amount=10000,category='rent',available_on='2024-02-01')],
    }
    headers={'Authorization':'Bearer secret'}
    with TestClient(app) as client:
        for table,records in tables.items():
            response=client.post('/ingest',headers=headers,json=dict(table=table,records=records))
            assert response.status_code==200,response.text
        response=client.post('/reconciliation/accept',headers=headers,json=dict(idempotency_key='partial',
            reviewed_by='Reviewer',allocations=[dict(txn_id='B1',invoice_id='I1',amount_minor=110000)],note='Bank advice'))
        assert response.status_code==200,response.text
        response=client.post('/forecast',headers=headers,json=dict(cutoff='2024-03-01',balance=110000))
        assert response.status_code==200,response.text
        result=response.json()
        snapshot=client.get('/snapshot?cutoff=2024-03-01',headers=headers).json()
        assert result['data_snapshot']==snapshot['snapshot_hash']
        assert result['data_contract']==snapshot['contract_version']
        assert result['collections'][0]['amount_open']==110000
        assert len(result['band'])==13
        assert snapshot['obligations'][0]['amount']==10000
        assert client.get('/health').json()['pilot_ready'] is False


def test_deactivating_old_model_selection_keeps_the_artifact(tmp_path):
    app=create_app(tmp_path/'api',token='secret')
    app.state.store.put('F000','model_active',[dict(id='active',version='old')])
    app.state.store.put('F000','model_registry',[dict(id='old',model_text='retained for audit')])
    with TestClient(app) as client:
        assert client.post('/models/deactivate').status_code==401
        assert client.post('/models/deactivate',headers={'Authorization':'Bearer secret'}).status_code==200
        assert not app.state.store.get('F000','model_active')
        assert app.state.store.get('F000','model_registry')[0]['id']=='old'


@pytest.mark.parametrize('kind,initial,change', [
    ('customers', dict(id='extra',customer_id='extra',short='Old buyer'), dict(short='New buyer')),
    ('promises', dict(id='P',invoice_id='I1',customer_id='C',made_date='2024-01-10',promised_date='2024-02-10'),
     dict(promised_date='2024-04-01')),
    ('outflows', dict(id='O',date='2024-04-01',amount=1000,category='rent'), dict(amount=2000)),
])
def test_auxiliary_revisions_preserve_past_snapshot_and_hash(source,kind,initial,change):
    old=dict(initial,available_on='2024-01-10')
    source.store.put('F',kind,[old])
    before=source.view('2024-02-01')['snapshot_hash']
    source.store.put('F',kind,[dict(old,**change,available_on='2024-03-01')])
    assert source.view('2024-02-01')['snapshot_hash']==before
    assert old in source.store.as_of('F',kind,'2024-02-01')
    assert dict(old,**change,available_on='2024-03-01') in source.store.as_of('F',kind,'2024-03-01')
    assert len(source.store.get('F',kind+'_versions'))>=2


def test_legacy_observation_is_preserved_on_first_revision(source):
    old=dict(id='legacy',customer_id='legacy',short='Old',available_on='2024-01-01')
    payload=source.store.cipher.encrypt(json.dumps(old).encode())
    with source.store.connection:
        source.store.connection.execute('INSERT INTO records VALUES (?,?,?,?)',('F','customers','legacy',payload))
    source.store.put('F','customers',[dict(old,short='New',available_on='2024-03-01')])
    assert old in source.store.as_of('F','customers','2024-02-01')
    assert len([r for r in source.store.get('F','customers_versions') if r['record_id']=='legacy'])==2


def test_customer_api_updates_are_versioned_and_same_day_conflicts_are_atomic(tmp_path,monkeypatch):
    monkeypatch.setenv('AGENT1_PSEUDONYMIZE','0')
    app=create_app(tmp_path/'api',token='secret')
    headers={'Authorization':'Bearer secret'}
    old=dict(customer_id='C',short='Old',available_on='2024-01-01')
    with TestClient(app) as client:
        def ingest(rows):
            return client.post('/ingest',headers=headers,json=dict(table='customers',records=rows))
        assert ingest([old]).status_code==200
        snapshot=client.get('/snapshot?cutoff=2024-02-01',headers=headers).json()
        assert ingest([dict(old,short='New',available_on='2024-03-01')]).status_code==200
        assert client.get('/snapshot?cutoff=2024-02-01',headers=headers).json()==snapshot
        assert ingest([dict(old,short='New',available_on='2024-03-01')]).status_code==200
        assert ingest([dict(customer_id='X',short='X',available_on='2024-03-01'),
                       dict(old,short='Conflict',available_on='2024-03-01')]).status_code==422
        assert not any(r['customer_id']=='X' for r in app.state.store.get('F000','customers'))
        assert len(app.state.store.get('F000','customers_versions'))==2


def test_promise_endpoint_cannot_create_retroactive_observation(tmp_path,monkeypatch):
    from agent1.reconciliation import pipeline
    monkeypatch.setattr(pipeline,'today',lambda:'2024-03-01')
    app=create_app(tmp_path/'api',token='secret')
    with TestClient(app) as client:
        response=client.post('/promises',headers={'Authorization':'Bearer secret'},json=dict(
            invoice_id='I1',customer_id='C',made_date='2024-01-01',promised_date='2024-04-01',amount=1000))
        assert response.status_code==200,response.text
        assert not app.state.store.as_of('F000','promises','2024-02-01')
        assert len(app.state.store.as_of('F000','promises','2024-03-01'))==1


def test_accepted_cash_cannot_follow_invoice_revision_to_another_customer(source,monkeypatch):
    result=operations.accept(source,'a','Reviewer',allocations=[dict(txn_id='B1',invoice_id='I1',amount_minor=40000)],note='Evidence')
    original=source.store.get('F','invoices')[0]
    source.store.put('F','invoice_versions',[
        dict(original,id='I1:1',revision=1),
        dict(original,id='I1:2',revision=2,customer_id='OTHER',available_on='2024-03-02'),
    ])
    assert source.view('2024-03-01')['invoices'].iloc[0].customer_id=='C'
    with pytest.raises(ValueError,match='Khách hàng.*đã đổi'):
        source.view('2024-03-02')
    monkeypatch.setattr(operations,'today',lambda:'2024-03-02')
    operations.reverse(source,'reverse',result['decision_id'],'Reviewer','Check corrected buyer')
    assert source.view('2024-03-02')['links'].empty
    assert source.view('2024-03-02')['invoices'].iloc[0].amount_open_minor==100000


@pytest.mark.parametrize('credit_date', ['2024-02-01','2024-03-03'])
def test_credit_at_or_after_last_receipt_closes_debt_without_a_paid_label(source,credit_date):
    operations.accept(source,'a','Reviewer',allocations=[dict(txn_id='B1',invoice_id='I1',amount_minor=40000)],note='Evidence')
    original=source.store.get('F','invoices')[0]
    source.store.put('F','invoice_versions',[
        dict(original,id='I1:1',revision=1),
        dict(original,id='I1:2',revision=2,credit_note=60000,credit_note_date=credit_date,available_on='2024-03-03'),
    ])
    row=source.view('2024-03-03')['invoices'].iloc[0]
    assert row.closure_type=='credit_note' and row.amount_open_minor==0
    assert pd.isna(row.paid_date_est)
    assert row.last_cash_date==pd.Timestamp('2024-02-01')
    assert row.closed_date==pd.Timestamp(credit_date)
    assert row.outcome_known_at=='2024-03-03'
    builder=ObservedSnapshotBuilder(source)
    assert builder.snapshot('2024-03-03').empty
    training=builder.build(['2024-01-15'],label_end='2024-03-03')
    assert training.event.tolist()==[0]
    assert training.obs_window.tolist()==[(pd.Timestamp(credit_date)-pd.Timestamp('2024-01-15')).days]
    assert source.view('2024-03-02')['invoices'].iloc[0].amount_open_minor==60000


def test_credit_before_final_cash_censors_old_face_value_but_allows_later_cash_target(source):
    operations.accept(source,'a','Reviewer',allocations=[dict(txn_id='B1',invoice_id='I1',amount_minor=40000)],note='Evidence')
    original=source.store.get('F','invoices')[0]
    source.store.put('F','invoice_versions',[
        dict(original,id='I1:1',revision=1),
        dict(original,id='I1:2',revision=2,credit_note=60000,credit_note_date='2024-01-20',available_on='2024-01-20'),
    ])
    row=source.view('2024-03-01')['invoices'].iloc[0]
    assert row.closure_type=='paid' and row.paid_date_est==pd.Timestamp('2024-02-01')
    builder=ObservedSnapshotBuilder(source)
    before=builder.build(['2024-01-15'],label_end='2024-03-01')
    assert before.event.tolist()==[0] and before.obs_window.tolist()==[5.]
    after=builder.build(['2024-01-25'],label_end='2024-03-01')
    assert after.event.tolist()==[1] and after.amount_open.tolist()==[40000]


def test_late_known_past_credit_is_not_a_future_payment_of_original_face_value(source):
    operations.accept(source,'a','Reviewer',allocations=[dict(txn_id='B1',invoice_id='I1',amount_minor=40000)],note='Evidence')
    original=source.store.get('F','invoices')[0]
    source.store.put('F','invoice_versions',[
        dict(original,id='I1:1',revision=1),
        dict(original,id='I1:2',revision=2,credit_note=60000,credit_note_date='2024-01-20',available_on='2024-03-03'),
    ])
    builder=ObservedSnapshotBuilder(source)
    assert builder.build(['2024-01-25'],label_end='2024-03-03').empty
    row=builder.build(['2024-01-15'],label_end='2024-03-03').iloc[0]
    assert row.event==0 and row.obs_window==5


def test_amount_revision_after_partial_receipt_cannot_backdate_cash_settlement(source):
    operations.accept(source,'a','Reviewer',allocations=[dict(txn_id='B1',invoice_id='I1',amount_minor=40000)],note='Evidence')
    original=source.store.get('F','invoices')[0]
    source.store.put('F','invoice_versions',[
        dict(original,id='I1:1',revision=1),
        dict(original,id='I1:2',revision=2,amount_gross=40000,amount_gross_minor=40000,available_on='2024-03-03'),
    ])
    row=source.view('2024-03-03')['invoices'].iloc[0]
    assert row.closure_type=='adjustment' and pd.isna(row.paid_date_est)
    assert row.closed_date==pd.Timestamp('2024-03-03')
    training=ObservedSnapshotBuilder(source).build(['2024-01-15'],label_end='2024-03-03')
    assert training.empty


def test_face_increase_after_settlement_does_not_turn_a_paid_origin_into_an_unpaid_label(source):
    operations.accept(source,'a','Reviewer',proposal_id=operations.propose(source,'2024-03-01')['id'])
    original=source.store.get('F','invoices')[0]
    source.store.put('F','invoice_versions',[
        dict(original,id='I1:1',revision=1),
        dict(original,id='I1:2',revision=2,amount_gross=200000,amount_gross_minor=200000,available_on='2024-03-03'),
    ])
    assert ObservedSnapshotBuilder(source).build(['2024-01-15'],label_end='2024-03-03').empty


def test_bank_customer_conflict_is_rejected_before_committing_a_decision(source):
    bank=source.store.get('F','bank_txns')[0]
    source.store.put('F','bank_txns',[dict(bank,customer_id='OTHER')])
    with pytest.raises(ValueError,match='Khách hàng.*không khớp'):
        operations.accept(source,'a','Reviewer',allocations=[dict(txn_id='B1',invoice_id='I1',amount_minor=40000)],note='Evidence')
    assert source.ledger.events()==[]


def test_live_forecast_never_builds_training_labels_or_fits_t1_or_t4(source,monkeypatch):
    from agent1 import api_surface
    from agent1_service.jobs import nightly
    import numpy as np
    def forbidden(*args,**kwargs):
        raise AssertionError('Live inference must not train')
    monkeypatch.setattr(api_surface.HazardGBM,'fit',forbidden)
    monkeypatch.setattr(nightly.GlobalQuantileLGBM,'fit',forbidden)
    monkeypatch.setattr(ObservedSnapshotBuilder,'build',forbidden)
    original=source.store.get('F','invoices')[0]
    source.store.put('F','invoices',[dict(original,id=f'old{i}',invoice_id=f'old{i}',
        issue_date=str(d.date()),due_date=str((d+pd.Timedelta(days=30)).date()),available_on=str(d.date()))
        for i,d in enumerate(pd.date_range('2022-01-01',periods=60,freq='7D'))])
    view=source.view('2024-03-01')
    inputs=(view['invoices'],pd.DataFrame(view['bank']),pd.DataFrame(),None,pd.DataFrame(),'2024-03-01',100000)
    result,_=nightly.run(*inputs,observed_source=source)
    assert result['model']=='B1d-fallback'
    assert result['new_revenue_included'] is False
    class SelectedModel:
        def hazards(self,frame):
            return np.full((len(frame),13),.03)
    result,_=nightly.run(*inputs,observed_source=source,model_cache={'t1':SelectedModel()})
    assert result['model']=='tenant-HazardGBM'
