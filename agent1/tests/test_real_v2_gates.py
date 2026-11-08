import pandas as pd
import pytest
from agent1.eval.real_v2_gates import real_v2_decisions


def frames():
    return pd.DataFrame([dict(setting=setting,model='BLEND(DH-GBM,B1d) w=.5',n=100,
        measurement_version='C-real-fullweek-refit-blend-v2',expand_full_week_only=True,
        pinball_avg=9.,improvement_vs_B1d_pct=2.,improvement_ci_low=.1,improvement_ci_high=3.) for setting in ['ci','bpi']]),\
        pd.DataFrame([dict(setting='ci',model='B1-cust-median',n=100,pinball_avg=10.)])


@pytest.mark.parametrize('low,passed',[(0,False),(.001,True)])
def test_g5_requires_strictly_positive_ci_and_ten_percent_vs_b1(low,passed):
    frame,reference=frames();frame.loc[frame.setting=='ci','improvement_ci_low']=low
    assert real_v2_decisions(frame,reference)['G5']==passed
    frame.loc[frame.setting=='ci','pinball_avg']=9.01
    assert real_v2_decisions(frame,reference)['G5'] is False


@pytest.mark.parametrize('point,high,passed',[(-2,0,True),(-2.001,1,False),(0,-.001,False)])
def test_g6_preregistered_noninferiority_boundaries(point,high,passed):
    frame,reference=frames();frame.loc[frame.setting=='bpi',['improvement_vs_B1d_pct','improvement_ci_high']]=[point,high]
    assert real_v2_decisions(frame,reference)['G6']==passed


def test_cqr_or_legacy_or_missing_domain_cannot_replace_deployed_blend():
    frame,reference=frames()
    frame.loc[0,'model']='BLEND(DH-GBM,B1d)+CQR'
    assert not real_v2_decisions(frame,reference)['G6']
    frame,reference=frames();frame['expand_full_week_only']=False
    assert not real_v2_decisions(frame,reference)['G5']
