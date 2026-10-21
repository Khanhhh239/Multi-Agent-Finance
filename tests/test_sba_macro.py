import pandas as pd
import pytest
from agent1.data.sba_macro import prior_cohort_features


def test_lag_window_and_self_exclusion():
    history=pd.DataFrame({'ApprovalDate':['2019-01-01','2019-03-01','2020-04-01','2021-01-01'],
        'ChargeOffDate':['2020-11-01','2020-01-01','2020-05-01','2021-01-01']})
    row=prior_cohort_features(history,pd.Series(['2021-01-01'])).iloc[0]
    assert row.prior_cohort_n==2
    assert row.prior_cohort_chgoff_rate==.5


def test_future_status_and_chargeoff_cannot_change_past_features():
    history=pd.DataFrame({'ApprovalDate':['2019-01-01','2019-03-01'],
        'ChargeOffDate':['2022-01-01',None],'LoanStatus':['EXEMPT','CHGOFF']})
    queries=pd.Series(['2021-01-01','2020-01-01'])
    first=prior_cohort_features(history,queries)
    changed=history.assign(ChargeOffDate=['2025-01-01','2024-01-01'],LoanStatus='PIF')
    pd.testing.assert_frame_equal(first,prior_cohort_features(changed,queries))


def test_calendar_year_boundary_and_duplicate_approval_dates():
    history=pd.DataFrame({'ApprovalDate':['2018-02-28','2018-02-28','2019-02-28'],
        'ChargeOffDate':['2018-05-01','2018-06-01','2019-03-01']})
    row=prior_cohort_features(history,pd.Series(['2020-02-29'])).iloc[0]
    assert row.prior_cohort_n==2 and row.prior_cohort_chgoff_rate==1


def test_invalid_queries_or_negative_lag_rejected():
    history=pd.DataFrame({'ApprovalDate':['2019-01-01'],'ChargeOffDate':[None]})
    with pytest.raises(ValueError):prior_cohort_features(history,pd.Series(['bad']))
    with pytest.raises(ValueError):prior_cohort_features(history,pd.Series(['2020-01-01']),-1)
