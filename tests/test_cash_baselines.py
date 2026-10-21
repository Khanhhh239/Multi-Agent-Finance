import numpy as np
import pandas as pd
import pytest
from agent1.models.cash_baselines import due_spreadsheet,time_series_paths


def test_due_spreadsheet_uses_overdue_first_week_and_keeps_late_amount_outside_horizon():
    frame=pd.DataFrame(dict(days_to_due=[-3.,8.,100.],amount_open=[10.,20.,1000.]))
    balances=due_spreadsheet(frame,np.ones(13),[0.,1.],5.,100.)
    np.testing.assert_allclose(balances[:3],[109.,133.,137.])
    assert balances[-1]==100+30+12*5-13


@pytest.mark.parametrize('model',['ETS','ARIMA'])
def test_time_series_paths_repeat_exactly_and_do_not_mutate_history(model):
    history=np.sin(np.arange(52)/3)+np.arange(52)*.02
    before=history.copy()
    first,info=time_series_paths(history,model,n=16,seed=123)
    second,_=time_series_paths(history,model,n=16,seed=123)
    assert first.shape==(16,13) and np.isfinite(first).all()
    assert info['n_history']==52
    np.testing.assert_allclose(first,second)
    np.testing.assert_array_equal(history,before)
