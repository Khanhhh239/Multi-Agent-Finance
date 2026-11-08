import pandas as pd
import numpy as np
from agent1.models.no_due_features import NoDueSnapshotBuilder


def test_virtual_due_remains_marked_unknown_and_does_not_mutate_input():
    inv=pd.DataFrame(dict(invoice_id=['i'],firm_id=['f'],customer_id=['c'],issue_date=pd.to_datetime(['2024-01-01']),
        due_date=pd.to_datetime([None]),paid_date_true=pd.to_datetime([None]),amount_gross=[100.]))
    result=NoDueSnapshotBuilder(inv).snapshot('2024-01-10')
    assert result.no_due.iloc[0]==1 and result.has_due.iloc[0]==0
    assert result.days_to_due.iloc[0]==result.age_days.iloc[0]==9
    assert inv.due_date.isna().all()


def test_bounded_training_keeps_same_fixed_budget_for_feature_ablation():
    from scripts.run_nodue_bpi import bounded_training
    from agent1.models.features import SnapshotBuilder
    inv=pd.DataFrame(dict(invoice_id=list('abcde'),firm_id=['f']*5,customer_id=['c']*5,
        issue_date=pd.to_datetime(['2024-01-01']*5),due_date=pd.to_datetime([None]*5),
        paid_date_true=pd.to_datetime(['2024-02-01']*5),amount_gross=[100.]*5))
    cuts=pd.date_range('2024-01-10',periods=3)
    original=bounded_training(SnapshotBuilder(inv),cuts,'2024-02-01',budget=7)
    proxy=bounded_training(NoDueSnapshotBuilder(inv),cuts,'2024-02-01',budget=7)
    assert len(original)==7
    pd.testing.assert_frame_equal(original[['invoice_id','cutoff']],proxy[['invoice_id','cutoff']])


def test_streamed_metrics_equal_in_memory_definitions():
    from scripts.run_nodue_bpi import aggregate
    from agent1.models.t1 import evaluate_quantiles,cdf_from_quantiles
    from agent1.eval.metrics import ibs_weekly
    frame=pd.DataFrame(dict(remaining=[4.,10.,np.inf,100.],firm_id=['a','a','b','b']))
    Q=np.array([[1.,5.,10.],[2.,9.,20.],[60.,90.,120.],[20.,80.,120.]])
    cdf=cdf_from_quantiles(Q);grouped=aggregate(frame,Q,cdf,'test')
    expected=evaluate_quantiles(frame.remaining,Q);count=grouped.n.sum()
    assert abs(grouped.pinball.sum()/count-expected['pinball_avg'])<1e-12
    assert abs(grouped.interval.sum()/count-expected['IS80'])<1e-12
    assert abs(grouped.IBS.sum()/count-ibs_weekly(frame.remaining,cdf)[0])<1e-12
