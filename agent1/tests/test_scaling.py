import numpy as np
import pandas as pd
import pytest
from agent1.data.scaling import NestedRowWriter,MemmapSequence
from agent1.models.features import SnapshotBuilder,add_labels
from agent1.models import t1
from scripts.run_scaling import expanded_count


def test_population_count_excludes_event_in_administratively_truncated_week(monkeypatch):
    monkeypatch.setattr(t1,'FULL_WEEK_ONLY',True)
    inv=pd.DataFrame(dict(issue_date=pd.to_datetime(['2024-01-01']),paid_date_true=pd.to_datetime(['2024-01-10']),
        writeoff_date=pd.to_datetime([None])))
    assert expanded_count(inv,pd.to_datetime(['2024-01-08']),pd.Timestamp('2024-01-11'))==0


def test_nested_sampler_is_exact_unique_and_batch_readable(tmp_path):
    X=np.arange(200,dtype='float32').reshape(100,2);y=(X[:,0]%3==0).astype(float)
    writer=NestedRowWriter(tmp_path,[20,50,80],100,2)
    for a,b in [(0,17),(17,61),(61,100)]:writer.append(X[a:b],y[a:b])
    writer.finish()
    selected=[]
    for n in [20,50,80]:
        seq=MemmapSequence(tmp_path/f'X_{n}.dat',n,2)
        assert len(seq)==n
        rows=seq[:n];assert len(np.unique(rows[:,0]))==n
        labels=np.memmap(tmp_path/f'y_{n}.dat',dtype='float32',mode='r',shape=(n,))
        np.testing.assert_array_equal(labels,(rows[:,0]%3==0))
        selected.append(set(rows[:,0]))
    assert selected[0]<selected[1]<selected[2]
    with pytest.raises(ValueError):NestedRowWriter(tmp_path/'bad',[101],100,2)


def test_count_pass_matches_actual_censored_week_expansion():
    inv=pd.DataFrame(dict(invoice_id=['a','b','c'],firm_id=['f']*3,customer_id=['c']*3,
        issue_date=pd.to_datetime(['2023-01-01']*3),due_date=pd.to_datetime(['2023-01-31']*3),
        paid_date_true=pd.to_datetime(['2023-02-14','2023-05-01',None]),
        writeoff_date=pd.to_datetime([None,None,'2023-03-01']),amount_gross=[100.,200.,300.],term_days=[30]*3))
    cuts=pd.to_datetime(['2023-01-10','2023-02-01','2023-03-10']);origin=pd.Timestamp('2023-03-20')
    builder=SnapshotBuilder(inv);actual=0
    for t in cuts:
        frame=builder.snapshot(t)
        if len(frame):actual+=len(t1.expand(add_labels(frame,origin),True)[1])
    assert actual==expanded_count(inv,cuts,origin)


def test_sequence_training_matches_in_memory_histograms(tmp_path):
    import lightgbm as lgb
    rng=np.random.default_rng(11);X=rng.normal(size=(500,4)).astype('float32');y=(X[:,0]+X[:,1]>0).astype(int)
    path=tmp_path/'matrix.dat';matrix=np.memmap(path,dtype='float32',mode='w+',shape=X.shape);matrix[:]=X;matrix.flush()
    parameters=dict(objective='binary',num_leaves=7,min_data_in_leaf=10,verbosity=-1,num_threads=1,seed=7)
    direct=lgb.train(parameters,lgb.Dataset(X,label=y),num_boost_round=20)
    streamed=lgb.train(parameters,lgb.Dataset(MemmapSequence(path,len(X),4),label=y),num_boost_round=20)
    np.testing.assert_allclose(direct.predict(X),streamed.predict(X),atol=1e-10)
