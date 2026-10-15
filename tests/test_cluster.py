import numpy as np
from agent1.eval.cluster import mean_ci


def test_paired_cluster_bootstrap_keeps_identical_relative_gain():
    # Công ty có quy mô và số hàng khác nhau; tỷ lệ cải thiện vẫn cố định.
    x = np.array([1., 2., 2., 2., 8., 8.])
    ci = mean_ci(x, ['a', 'b', 'b', 'b', 'c', 'c'], baseline=x * 2, n=300)
    assert ci['n_firms'] == 3
    assert ci['bootstrap_n'] >= 200
    np.testing.assert_allclose([ci['improvement_pct'], ci['improvement_ci_low'], ci['improvement_ci_high']], 50.)
