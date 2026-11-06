"""T1 validation must expose unpaid invoices and actual follow-up support."""
import numpy as np
import pandas as pd
import pytest

from agent1.eval.observed_t1 import horizon_metrics


def test_horizon_scores_include_unpaid_on_identical_model_baseline_support():
    frame=pd.DataFrame(dict(remaining=[10.,50.,np.inf,np.inf],event=[1,1,0,0],
                            obs_window=[120.,120.,120.,120.],amount_open=[100.,100.,300.,500.]))
    predicted=np.full((4,13),.9)
    baseline=np.full((4,13),.3)
    metrics=horizon_metrics(frame,predicted,baseline)
    early=metrics['horizons']['28'];late=metrics['horizons']['91']
    assert not metrics['resolved_only']
    assert (early['n'],early['paid'],early['not_paid'])==(4,1,3)
    assert (late['n'],late['paid'],late['not_paid'])==(4,2,2)
    assert early['model']['brier']==pytest.approx(np.mean((.9-np.array([1,0,0,0]))**2))
    assert early['model']['amount_weighted_brier']==pytest.approx((.01*100+.81*900)/1000)
    assert early['baseline']['brier']<early['model']['brier']


def test_short_followup_does_not_select_only_early_paid_cases():
    frame=pd.DataFrame(dict(remaining=[5.,np.inf,np.inf],event=[1,0,0],
                            obs_window=[10.,10.,120.],amount_open=[1.,1.,1.]))
    result=horizon_metrics(frame,np.full((3,13),.9),np.full((3,13),.2))
    assert result['horizons']['7']['n']==3
    late=result['horizons']['28']
    assert late['n']==1 and late['excluded_short_followup']==2
    assert late['paid']==0 and late['not_paid']==1
    assert late['model']['brier']==pytest.approx(.81)


def test_no_complete_followup_reports_missing_score_instead_of_success():
    frame=pd.DataFrame(dict(remaining=[np.inf],event=[0],obs_window=[2.],amount_open=[100.]))
    score=horizon_metrics(frame,np.full((1,13),.1),np.full((1,13),.2))['horizons']['91']
    assert score['n']==0 and score['model']['brier'] is None


def test_empty_validation_can_be_serialized_without_nan():
    import json
    result=horizon_metrics(pd.DataFrame(),np.empty((0,13)),np.empty((0,13)))
    json.dumps(result,allow_nan=False)
    assert result['validation_rows']==0


def test_retrain_registers_unpaid_validation_metrics(tmp_path,monkeypatch):
    from cryptography.fernet import Fernet
    from agent1.jobs import retrain
    from agent1.models.features import FEATURES,BASELINE_QUANTILES
    from agent1_service.store import Store
    rng=np.random.default_rng(40)
    train=pd.DataFrame(rng.normal(size=(120,len(FEATURES))),columns=FEATURES)
    train['cutoff']=pd.Timestamp('2023-01-01')
    train['remaining']=np.r_[np.full(30,20.),np.full(90,np.inf)]
    train['event']=np.r_[np.ones(30,dtype=int),np.zeros(90,dtype=int)]
    train['obs_window']=120.
    train['time_obs']=np.minimum(train.remaining,120.)
    train['amount_open']=100000.
    for column,value in zip(BASELINE_QUANTILES,(5.,20.,60.)):
        train[column]=value
    class Builder:
        def __init__(self,source):pass
        def build(self,cutoffs,label_end):return train.copy()
    monkeypatch.setattr(retrain,'ObservedSnapshotBuilder',Builder)
    monkeypatch.setattr(retrain,'observed_tables',lambda *args:dict(invoices=pd.DataFrame({'id':['I']})))
    monkeypatch.setattr(retrain.ObservedSource,'view',lambda *args:dict(
        invoices=pd.DataFrame({'issue_date':[pd.Timestamp('2022-01-01')]}),
        contract_version='fixture',snapshot_hash='fixture'))
    store=Store(tmp_path/'state.db',Fernet.generate_key())
    try:
        candidate=retrain.train_candidate(store,'F','2024-03-01','manual',rounds=3)
        assert candidate['metrics']['resolved_rows']==30
        assert candidate['metrics']['horizons']['91']['n']==120
        assert candidate['metrics']['horizons']['91']['not_paid']==90
        assert not candidate['metrics']['resolved_only']
        assert store.get('F','model_active')==[]
    finally:
        store.connection.close()
