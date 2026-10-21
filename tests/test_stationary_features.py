import numpy as np
import pandas as pd
import pytest
from agent1.models.features import StationaryFeatures


def sample():
    return pd.DataFrame(dict(f_n_hist=[0.,100.,200.],c_tenure_days=[0.,30.,730.],
        cutoff=pd.to_datetime(['2024-03-01']*3),firm_history_days=[200,731,900],
        issue_month=[1,2,3],cut_month=[3,3,3],remaining=[1,2,3]))


def test_training_cap_is_frozen_and_test_extremes_do_not_reestimate_it():
    train=sample();state=StationaryFeatures().fit(train)
    test=train.copy();test.loc[2,'f_n_hist']=1e12
    result=state.transform(test)
    assert state.count_cap==pytest.approx(198)
    assert result.f_n_hist.iloc[2]==pytest.approx(np.log1p(198))
    assert result.c_tenure_days.iloc[1]==pytest.approx(np.log1p(30))
    pd.testing.assert_frame_equal(train,sample())


def test_calendar_months_hidden_only_before_twenty_four_calendar_months():
    frame=sample();result=StationaryFeatures().fit(frame).transform(frame)
    assert result.loc[0,['issue_month','cut_month']].isna().all()
    assert result.issue_month.iloc[1]==2  # 01/03/2022 -> 01/03/2024 có 731 ngày.
    pd.testing.assert_series_equal(result.remaining,frame.remaining)


def test_transform_requires_train_fit_and_observed_company_history():
    with pytest.raises(ValueError,match='fit'):StationaryFeatures().transform(sample())
    state=StationaryFeatures().fit(sample())
    with pytest.raises(ValueError,match='lịch sử'):state.transform(sample().drop(columns='firm_history_days'))
