import json
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import numpy as np
import pytest
from agent1_service.api import create_app
from agent1_service.store import Store
from agent1_service.monitoring import psi,retrain_required


@pytest.fixture
def client(tmp_path):
    app=create_app(tmp_path,token='test-secret',firm_id='F000')
    with TestClient(app) as client:yield client


@pytest.mark.parametrize('path',['/alerts','/data'])
@pytest.mark.parametrize('token',[None,'Bearer wrong','Basic test-secret','Bearer test-secret-extra'])
def test_access_requires_exact_bearer(client,path,token):
    headers={} if token is None else {'Authorization':token}
    assert client.get(path,headers=headers).status_code==401


def test_cross_firm_ingest_is_rejected(client):
    r=client.post('/ingest',headers={'Authorization':'Bearer test-secret'},json={'table':'customers','records':[
        dict(customer_id='c',short='A',firm_id='OTHER')]})
    assert r.status_code==403


def test_no_go_forecast_is_not_exposed_by_default(client,monkeypatch):
    monkeypatch.delenv('AGENT1_RESEARCH_MODE',raising=False)
    r=client.post('/forecast',headers={'Authorization':'Bearer test-secret'},json={'cutoff':'2024-07-01','balance':100})
    assert r.status_code==409


def test_ingest_and_delete_are_idempotent(client):
    headers={'Authorization':'Bearer test-secret'}
    payload={'table':'customers','records':[dict(customer_id='c',short='Buyer')]}
    assert client.post('/ingest',headers=headers,json=payload).status_code==200
    assert client.post('/ingest',headers=headers,json=payload).status_code==200
    assert client.get('/data',headers=headers).json()['customers']==1
    assert client.delete('/data',headers=headers).status_code==200
    assert client.get('/data',headers=headers).json()['customers']==0


def test_database_payload_is_encrypted_and_tenant_scoped(tmp_path):
    path=tmp_path/'s.db';store=Store(path,Fernet.generate_key())
    store.put('a','customer',[dict(id='c',name='Private Customer Name')])
    assert store.get('b','customer')==[]
    assert store.get('a','customer')[0]['name']=='Private Customer Name'
    assert b'Private Customer Name' not in path.read_bytes()
    store.connection.close()


def test_monitoring_detects_distribution_shift_and_four_bad_windows():
    x=np.random.default_rng(7).normal(size=10000)
    assert psi(x,x)<1e-9
    assert psi(x,x+2)>.1
    assert retrain_required(0,[.6,.6,.6,.6])
    assert not retrain_required(0,[.8,.8,.8,.8])


@pytest.mark.parametrize('encoding',['utf-8','utf-16','utf-16-be'])
def test_xml_dtd_and_entities_rejected_in_all_encodings(encoding):
    from agent1_service.ingest.einvoice_xml import read_invoice_xml
    xml = '<?xml version="1.0"?><!DOCTYPE HDon [<!ENTITY x "unsafe">]><HDon>&x;</HDon>'
    with pytest.raises(ValueError):
        read_invoice_xml(xml.encode(encoding),'F000',validate=False)


def test_non_ascii_bearer_is_unauthorized_instead_of_server_error(client):
    assert client.get('/data',headers={b'Authorization':b'Bearer caf\xe9'}).status_code==401


def test_boolean_amount_is_not_treated_as_money(client):
    payload={'table':'bank_txns','records':[dict(txn_id='t',value_date='2024-01-01',amount=True,memo='')]}
    assert client.post('/ingest',headers={'Authorization':'Bearer test-secret'},json=payload).status_code==422


@pytest.mark.parametrize('date',['','NaT','invalid-date'])
def test_promise_missing_date_is_rejected(client,date):
    payload=dict(invoice_id='i',customer_id='c',amount=1,made_date=date,promised_date='2024-02-01')
    assert client.post('/promises',headers={'Authorization':'Bearer test-secret'},json=payload).status_code==422


def test_promise_mixed_offsets_normalizes_to_vietnam_date(client):
    payload=dict(invoice_id='i',customer_id='c',amount=1,made_date='2024-01-01T18:00:00Z',promised_date='2024-01-02')
    assert client.post('/promises',headers={'Authorization':'Bearer test-secret'},json=payload).status_code==200
