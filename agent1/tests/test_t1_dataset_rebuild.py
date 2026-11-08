"""Rebuilding samples preserves evidence dates, encryption and separate training."""
import hashlib
import io
import json
import sys

from cryptography.fernet import Fernet
import pandas as pd
import pytest

from agent1.jobs import retrain
from agent1.reconciliation import operations
from agent1.reconciliation.pipeline import ObservedSource
from agent1_service.store import Store


@pytest.fixture
def history(tmp_path, monkeypatch):
    store=Store(tmp_path/'source'/'agent1.db',Fernet.generate_key())
    store.put('F','invoices',[dict(id=i,invoice_id=i,firm_id='F',customer_id='C',invoice_no=i,
        issue_date='2022-01-01',due_date='2022-02-01',available_on='2022-01-01',amount_gross=100000,currency='VND')
        for i in ('paid','unpaid')])
    store.put('F','customers',[dict(id='C',customer_id='C',short='Buyer',available_on='2022-01-01')])
    store.put('F','bank_txns',[
        dict(id='first',txn_id='first',firm_id='F',value_date='2022-01-10',available_on='2022-01-11',amount=40000,memo='paid'),
        dict(id='final',txn_id='final',firm_id='F',value_date='2023-02-01',available_on='2023-02-02',amount=60000,memo='paid'),
    ])
    source=ObservedSource(store,'F')
    for tid,date,amount in [('first','2023-01-01',40000),('final','2023-03-01',60000)]:
        monkeypatch.setattr(operations,'today',lambda value=date:value)
        operations.accept(source,tid,'Reviewer',allocations=[dict(txn_id=tid,invoice_id='paid',amount_minor=amount)],note='Fixture evidence')
    yield store,source
    store.connection.close()


def test_rebuild_exports_only_encrypted_samples_with_correct_historical_cash(history,tmp_path,monkeypatch):
    store,source=history
    before=store.connection.execute('SELECT kind,id,payload FROM records ORDER BY kind,id').fetchall()
    def forbidden(*args,**kwargs):raise AssertionError('Preparing data must not fit a model')
    monkeypatch.setattr(retrain.HazardGBM,'fit',forbidden)
    output=tmp_path/'rebuilt'
    result=retrain.export_training_data(store,'F','2024-01-01',output)
    assert result['label_mode']=='accepted_ledger'
    assert result['data_snapshot']==source.view('2024-01-01')['snapshot_hash']
    assert result['trained'] is result['activated'] is False
    assert {p.name for p in output.iterdir()}=={'dataset.json','train.parquet.enc','validation.parquet.enc'}
    frames={}
    for role,record in result['files'].items():
        encrypted=(output/record['file']).read_bytes()
        assert not encrypted.startswith(b'PAR1')
        assert hashlib.sha256(encrypted).hexdigest()==record['encrypted_sha256']
        content=store.cipher.decrypt(encrypted)
        assert hashlib.sha256(content).hexdigest()==record['plaintext_sha256']
        frames[role]=pd.read_parquet(io.BytesIO(content))
        assert len(frames[role])==record['rows']
        assert not {'paid_date_true','source_payloads','source_lineage','remaining_amount'}&set(frames[role])
    paid=frames['train'][frames['train'].invoice_id.eq('paid')]
    assert len(paid)>0
    assert paid.cutoff.ge('2023-01-01').all() and paid.cutoff.lt('2023-02-01').all()
    assert paid.amount_open.eq(60000).all() and paid.event.eq(1).all()
    assert frames['validation'].invoice_id.tolist()==['unpaid']
    assert frames['validation'].event.tolist()==[0]
    assert not store.get('F','model_registry') and not store.get('F','model_active')
    assert before==store.connection.execute('SELECT kind,id,payload FROM records ORDER BY kind,id').fetchall()
    assert json.loads((output/'dataset.json').read_text(encoding='utf-8'))==result


def test_rebuild_refuses_to_overwrite_existing_dataset(history,tmp_path):
    store,_=history
    output=tmp_path/'existing';output.mkdir()
    marker=output/'dataset.json';marker.write_text('keep',encoding='utf-8')
    with pytest.raises(ValueError,match='đã tồn tại'):
        retrain.export_training_data(store,'F','2024-01-01',output)
    assert marker.read_text(encoding='utf-8')=='keep'


def test_rebuild_missing_history_leaves_no_partial_dataset(tmp_path):
    store=Store(tmp_path/'empty.db',Fernet.generate_key())
    try:
        output=tmp_path/'rebuilt'
        with pytest.raises(ValueError,match='Cần hoá đơn'):
            retrain.export_training_data(store,'F','2024-01-01',output)
        assert not output.exists()
    finally:store.connection.close()


def test_cli_missing_source_does_not_create_a_database(tmp_path,monkeypatch):
    state=tmp_path/'missing'
    monkeypatch.setattr(sys,'argv',['retrain','--firm','F','--reason','manual','--cutoff','2024-01-01',
        '--state',str(state),'--prepare-only','--dataset-output',str(tmp_path/'dataset')])
    with pytest.raises(ValueError,match='Chưa có agent1.db'):
        retrain.main()
    assert not state.exists() and not (tmp_path/'dataset').exists()


def test_cli_cannot_activate_during_dataset_preparation(tmp_path,monkeypatch):
    monkeypatch.setattr(sys,'argv',['retrain','--firm','F','--reason','manual','--cutoff','2024-01-01',
        '--prepare-only','--activate','--dataset-output',str(tmp_path/'dataset')])
    with pytest.raises(SystemExit) as error:retrain.main()
    assert error.value.code==2 and not (tmp_path/'dataset').exists()
