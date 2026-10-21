import numpy as np
import pandas as pd
import pytest
from agent1.eval.adaptation import paired_improvement, company_statistics


def test_paired_cluster_improvement_uses_matching_firms_not_row_order():
    data=pd.DataFrame(dict(firm_id=['f2','f1','f1','f2'],model=['new','new','base','base'],
        pinball_sum=[8.,4.,5.,10.],n=[2,1,1,2]))
    result=paired_improvement(data,'new','base')
    assert result['improvement_pct']==20
    np.testing.assert_allclose([result['improvement_ci_low'],result['improvement_ci_high']],[20,20])
    data.loc[0,'n']=3
    with pytest.raises(ValueError,match='cohort'):paired_improvement(data,'new','base')


def test_cash_statistics_group_forecast_errors_before_company_bootstrap():
    frame=pd.DataFrame(dict(firm_id=['f','f'],cutoff=pd.to_datetime(['2024-01-01']*2),
        remaining=[7.,14.],amount_open=[10.,20.]))
    Q=np.column_stack([[7.,14.]]*3);P=np.zeros((2,13));P[:,0]=1
    result=company_statistics(frame,Q,P).iloc[0]
    assert result.pinball_sum==0 and result.n==2
    assert result.cash_actual_w1_4==30
    assert result.cash_error_w1_4==40


def test_equal_losses_do_not_support_strict_iw_improvement():
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
    from run_da_paired import hypothesis_status
    effect=dict(improvement_ci_low=0.,improvement_ci_high=0.)
    assert hypothesis_status(effect,strict=True)=='rejected'
    assert hypothesis_status(effect,strict=False)=='supported'
