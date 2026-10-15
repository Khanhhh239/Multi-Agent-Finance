import numpy as np
from agent1.models.t1 import pmf_from_hazard, quantiles_from_hazard, expected_days_from_hazard, cqr_fit, cqr_apply
from agent1.models.t1 import cdf_from_quantiles, cqr_fit_asym, cqr_apply_asym


def test_hazard_mass_and_quantiles():
    H = np.random.default_rng(3).uniform(0, 1, (100, 13))
    P, S = pmf_from_hazard(H)
    np.testing.assert_allclose(P.sum(1) + S[:, -1], 1)
    Q = quantiles_from_hazard(H)
    assert (np.diff(Q, axis=1) >= 0).all()
    assert ((Q >= .5) & (Q <= 120)).all()
    means = expected_days_from_hazard(H)
    assert ((means >= 0) & (means <= 120)).all()


def test_cqr_on_exchangeable_data():
    r = np.random.default_rng(7)
    ycal, ytest = r.normal(50, 10, (2, 5000))
    Q = np.tile([45., 50., 55.], (5000, 1))
    out = cqr_apply(Q, cqr_fit(ycal, Q))
    cov = ((ytest >= out[:, 0]) & (ytest <= out[:, -1])).mean()
    assert cov >= .78


def test_asymmetric_cqr_shrinks_and_preserves_order():
    r = np.random.default_rng(9)
    ycal, yt = r.normal(50, 5, (2, 5000))
    Q = np.tile([10., 50., 100.], (5000, 1))
    shift = cqr_fit_asym(ycal, Q)
    assert max(shift) < 0
    pred = cqr_apply_asym(Q, shift)
    assert (np.diff(pred, axis=1) >= 0).all()
    cov = ((yt >= pred[:, 0]) & (yt <= pred[:, -1])).mean()
    assert .78 <= cov <= .82


def test_pchip_with_crossing_and_repeated_quantiles():
    q = np.array([[20., 30., 50.], [7., 7., 7.], [50., 20., 10.]])
    f = cdf_from_quantiles(q)
    assert np.isfinite(f).all()
    assert ((f >= 0) & (f <= 1)).all()
    assert (np.diff(f, axis=1) >= 0).all()
    assert f[1, 0] >= .9
    np.testing.assert_allclose(cdf_from_quantiles([[10., 20., 50.]], grid=[10., 20., 50.]), [[.1, .5, .9]])
