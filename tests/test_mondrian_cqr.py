import numpy as np
import pytest
from agent1.models.mondrian_cqr import MondrianCQR,maturity_groups


def test_maturity_bins_include_exact_boundaries():
    assert maturity_groups([-1,0,1,14,15,42,43,np.nan]).tolist()==[
        'overdue','weeks_1_2','weeks_1_2','weeks_1_2','weeks_3_6','weeks_3_6','after_week_6','unknown']


def test_different_group_bias_and_shrinking_are_fitted_only_on_calibration():
    y=np.r_[np.full(200,50.),np.full(200,90.)]
    quantiles=np.tile([10.,50.,110.],(400,1));due=np.r_[np.full(200,7.),np.full(200,70.)]
    model=MondrianCQR().fit(y,quantiles,due)
    result=model.apply(quantiles,due)
    assert model.offsets['weeks_1_2'][0]<0 and model.offsets['weeks_1_2'][1]<0
    assert result[0,2]<result[-1,2] and result[0,0]>quantiles[0,0]
    saved=dict(model.offsets)
    model.apply(np.tile([1.,20.,100.],(2,1)),[-1,10])
    assert model.offsets==saved


def test_sparse_unseen_group_uses_source_fallback_and_order_is_preserved():
    model=MondrianCQR(min_group=100).fit(np.arange(30.),np.tile([0.,15.,40.],(30,1)),np.ones(30))
    result=model.apply(np.tile([0.,15.,40.],(3,1)),[-1,30,99])
    assert np.all(np.diff(result,axis=1)>=0)
    assert model.offsets['weeks_1_2']==model.fallback
    with pytest.raises(ValueError):MondrianCQR().apply(result,[1,2,3])
