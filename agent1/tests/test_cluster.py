import numpy as np
import pytest
from agent1.eval.cluster import mean_ci, ratio_ci


def test_paired_cluster_bootstrap_keeps_identical_relative_gain():
    # Công ty có quy mô và số hàng khác nhau; tỷ lệ cải thiện vẫn cố định.
    x = np.array([1., 2., 2., 2., 8., 8.])
    ci = mean_ci(x, ['a', 'b', 'b', 'b', 'c', 'c'], baseline=x * 2, n=300)
    assert ci['n_firms'] == 3
    assert ci['bootstrap_n'] >= 200
    np.testing.assert_allclose([ci['improvement_pct'], ci['improvement_ci_low'], ci['improvement_ci_high']], 50.)


def test_cluster_ratio_resamples_whole_companies_with_row_weights():
    one=ratio_ci([1.,9.],[2.,18.])
    assert one['ci_low']==one['ci_high']==.5
    assert one['bootstrap_n']==300 and one['n_firms']==2


def test_cluster_ratio_omits_undefined_resamples():
    result=ratio_ci([0.,1.],[0.,2.])
    assert 0 < result['bootstrap_valid'] < 300
    assert result['ci_low']==result['ci_high']==.5
    assert np.isnan(ratio_ci([0.],[0.])['ci_low'])
    with pytest.raises(ValueError):ratio_ci([1.],[-1.])
