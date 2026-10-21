import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from agent1.models.features import FEATURES
from agent1.models.t1 import HazardGBM,WEEK_FEATS
from agent1_service.api import create_app
from agent1_service.model_registry import register,activate,load,summaries
from agent1_service.monitoring import realized_coverage,weekly_report
from agent1_service.store import Store
from agent1.jobs.retrain import observed_tables


@pytest.fixture
def registered(tmp_path):
    store=Store(tmp_path/'s.db',Fernet.generate_key())
    rng=np.random.default_rng(8);x=rng.normal(size=(200,len(FEATURES)+len(WEEK_FEATS)))
    model=HazardGBM(dict(min_data_in_leaf=5),rounds=5)
    model.booster=lgb.train(model.p,lgb.Dataset(x,(x[:,0]>0).astype(int),feature_name=FEATURES+WEEK_FEATS),num_boost_round=5)
    summary=register(store,'f',model,dict(available_at='2024-07-01',training_label_end='2024-03-03'),pd.DataFrame(x[:,:len(FEATURES)],columns=FEATURES))
    yield store,model,summary,x
    store.connection.close()


def test_encrypted_registry_roundtrip_and_firm_boundary(registered,tmp_path):
    store,model,summary,x=registered
    assert load(store,'f','2024-08-01')==(None,None)
    activate(store,'f',summary['id'])
    loaded,record=load(store,'f','2024-07-01')
    np.testing.assert_allclose(loaded.booster.predict(x),model.booster.predict(x))
    assert load(store,'other','2024-07-01')==(None,None)
    assert b'tree\nversion=' not in (tmp_path/'s.db').read_bytes()
    assert not {'model_text','reference'}&summaries(store,'f')[0].keys()
    assert record['research_only']


def test_registry_rejects_future_version_corruption_and_code_change(registered):
    store,_,summary,_=registered;activate(store,'f',summary['id'])
    with pytest.raises(ValueError,match='chưa tồn tại'):load(store,'f','2024-06-30')
    row=store.get('f','model_registry')[0];row['model_text']+='invalid'
    store.put('f','model_registry',[row])
    with pytest.raises(ValueError,match='Hash'):load(store,'f','2024-07-01')
    row['code_signature']='old';store.put('f','model_registry',[row])
    with pytest.raises(ValueError,match='thay đổi'):load(store,'f','2024-07-01')


def test_monitoring_waits_for_actual_end_of_week_and_no_future():
    forecasts=[dict(cutoff='2024-07-01',band=[dict(week=1,P10=0,P90=10),dict(week=2,P10=0,P90=10)])]
    balances=[dict(date='2024-07-07',balance=999),dict(date='2024-07-08',balance=5),dict(date='2024-07-15',balance=-10)]
    assert realized_coverage(forecasts,balances,'2024-07-07')==[]
    assert realized_coverage(forecasts,balances,'2024-07-08')[0]['cov80']==1
    assert realized_coverage(forecasts,balances,'2024-07-15')[0]['cov80']==.5
    offset_balances=[dict(date='2024-07-07T18:00:00Z',balance=5)]
    assert realized_coverage(forecasts,offset_balances,'2024-07-08')[0]['cov80']==1


def test_weekly_report_marks_missing_evidence_and_persists_drift(registered):
    store,_,_,_=registered
    empty=weekly_report(store,'f','2024-07-01')
    assert not empty['retrain_required'] and len(empty['missing_inputs'])==2
    report=weekly_report(store,'f','2024-07-08',pd.DataFrame({'x':np.arange(100)+200}),{'x':list(range(100))})
    assert report['retrain_required'] and not report['pilot_ready']
    assert len(store.get('f','monitoring'))==2


def test_registry_and_monitoring_endpoints_require_auth_and_cash_can_be_negative(tmp_path):
    app=create_app(tmp_path,token='secret');headers={'Authorization':'Bearer secret'}
    with TestClient(app) as client:
        for path in ['/models','/monitoring']:
            assert client.get(path).status_code==401
            assert client.get(path,headers=headers).status_code==200
        body=dict(table='cash_balances',records=[dict(date='2024-07-01',balance=-50)])
        assert client.post('/ingest',headers=headers,json=body).status_code==200
        assert client.get('/data',headers=headers).json()['cash_balances']==1


def test_training_inputs_exclude_future_transactions_invoices_and_customers(tmp_path):
    store=Store(tmp_path/'s.db',Fernet.generate_key())
    for kind,rows in {
        'invoices':[dict(id='a',invoice_id='a',customer_id='a',issue_date='2024-01-01'),dict(id='b',invoice_id='b',customer_id='b',issue_date='2025-01-01')],
        'bank_txns':[dict(id='a',value_date='2024-01-01'),dict(id='b',value_date='2025-01-01')],
        'customers':[dict(id='a',customer_id='a'),dict(id='b',customer_id='b')],
    }.items():store.put('f',kind,rows)
    tables=observed_tables(store,'f','2024-07-01')
    assert all(len(tables[k])==1 for k in ['invoices','bank_txns','customers'])
    store.connection.close()
