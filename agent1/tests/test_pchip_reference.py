import numpy as np
from scipy.interpolate import PchipInterpolator
from agent1.models.t1 import cdf_from_quantiles


def test_vectorized_pchip_agrees_with_scipy_for_distinct_quantiles():
    rng=np.random.default_rng(7)
    Q=np.sort(rng.uniform(1,119,(100,9)),axis=1)
    alphas=np.array([.05,.1,.2,.3,.5,.7,.8,.9,.95]);grid=7*np.arange(1,14)
    actual=cdf_from_quantiles(Q,alphas)
    expected=np.array([PchipInterpolator(np.r_[0,row,180],np.r_[0,alphas,.999])(grid) for row in Q])
    np.testing.assert_allclose(actual,expected,atol=1e-12)
