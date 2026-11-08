"""Sprint 4: realism v2 chỉ đổi khi bật cờ; v1 giữ nguyên kết quả."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.synth import world as W  # noqa: E402


def _mini(realism, seed=5, customer=False):
    cfg = W.WorldConfig(name="t", seed=seed, n_firms=2, realism=realism, customer_realism=customer, write_xml=0,
                        start="2022-01-01", end="2022-12-31", n_cust_median=12)
    w = W.World(cfg)
    w.macro()
    firm = w.make_firm(0)
    cust = w.make_customers(firm)
    return w.make_invoices(firm, cust), w


def test_defaults_are_v1():
    c = W.WorldConfig()
    assert c.realism == "v1" and c.customer_realism is False


def test_v2_has_more_weekend_invoices_than_v1():
    v1, w1 = _mini("v1")
    v2, w2 = _mini("v2")
    wk = lambda inv, w: float((w.cal.wd[inv["issue_i"].values] >= 5).mean())  # noqa: E731
    assert wk(v1, w1) < 0.08
    assert wk(v2, w2) > 0.10


def test_v2_amount_dispersion_is_wider():
    v1, _ = _mini("v1")
    v2, _ = _mini("v2")
    assert np.log(v2["net"]).std() > np.log(v1["net"]).std()


def test_v1_is_deterministic_same_seed():
    a, _ = _mini("v1", seed=9)
    b, _ = _mini("v1", seed=9)
    pd.testing.assert_frame_equal(a, b)
