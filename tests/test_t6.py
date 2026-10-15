import numpy as np
import pandas as pd
import pytest
from agent1.models.t6_cash import simulate, collection_kernel, ACI


def test_simulation_conserves_money_and_is_reproducible():
    inv = pd.DataFrame({'amount_open': [100., 200.]})
    p = np.zeros((2, 13)); p[:, 0] = 1
    args = (inv, p, 50., np.full(13, 10.), None, np.zeros(17), 0., [])
    bal, net = simulate(*args, n=100, seed=9)
    np.testing.assert_allclose(bal[0], 350 - 10 * np.arange(1, 14))
    np.testing.assert_array_equal(bal, simulate(*args, n=100, seed=9)[0])
    np.testing.assert_allclose(bal, 50 + np.cumsum(net, axis=1))


def test_t_copula_preserves_payment_probability_marginals():
    inv = pd.DataFrame({'amount_open': [1.]})
    p = np.zeros((1, 13)); p[0, :2] = [.2, .3]
    for rho in [0., .3, .8]:
        _, net = simulate(inv, p, 0., np.zeros(13), None, np.zeros(17), 0., [], n=50000, rho=rho, seed=3)
        np.testing.assert_allclose(net.mean(0)[:2], [.2, .3], atol=.008)


def test_bad_debt_has_correct_horizon_loss():
    inv = pd.DataFrame({'amount_open': [100.]})
    p = np.zeros((1, 13)); p[0, 0] = 1
    _, net = simulate(inv, p, 0., np.zeros(13), None, np.zeros(17), 0., [], n=50000,
                      p_bad=np.array([.3]), seed=15)
    assert abs(net.sum(1).mean() - 70.) < 1.


def test_crn_identical_scenario_and_forced_collection():
    inv = pd.DataFrame({'amount_open': [100.]})
    p = np.full((1, 13), .04)
    args = (inv, p, 0., np.ones(13), None, np.zeros(17), 0., [])
    bal, _ = simulate(*args, n=100, seed=5)
    same, _ = simulate(*args, n=100, seed=5, payment_shift=[0])
    np.testing.assert_array_equal(bal, same)
    early, _ = simulate(*args, n=100, seed=5, force_week=[0])
    assert (early >= bal).all()


def test_kernel_ignores_future_payments():
    inv = pd.DataFrame({'issue_date': pd.to_datetime(['2023-01-01'] * 30),
                        'paid_date_true': pd.to_datetime(['2024-01-01'] * 30), 'amount_gross': [1.] * 30})
    assert collection_kernel(inv, '2023-12-01').sum() == 0


def test_aci_direction_and_bounds():
    aci = ACI()
    aci.update(0, True)
    assert aci.a[0] < .2
    for _ in range(1000):
        aci.update(0, True)
    assert aci.a[0] == .005
    lo, hi = aci.interval(np.arange(100), 0)
    assert lo < hi
