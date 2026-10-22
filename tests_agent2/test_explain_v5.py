"""Fidelity of v5 change-feature sentences (dữ liệu tổng hợp)."""
import math

import pytest

from agent2.change_detect import ED2_SPECS
from agent2.explain_check import check
from agent2.explain_v5 import _sentence, change_observations

SAMPLE = {"pay_lr": math.log(1.18), "pay_cusum_up": .4, "pay_shift": math.log(1.12), "grp_pay_up_n": 4,
          "price_lr2": math.log(1.3), "price_cusum_up": .2, "price_slope6": .03, "cust_z": -4.2, "cust_cusum_dn": 3.1,
          "ar_cust_overdue_n": 3, "ar_mgr_overdue_share": .6, "ar_creator_reversal_share": .25, "ar_reversal_unpaid": 1,
          "ar_reversal_age_days": 12, "rec_excess": 2.5, "rec_amount_lr": math.log(2), "rec_new_counterparty": 1,
          "adv_open_n": 2, "adv_growth": math.log(1.25)}


@pytest.mark.parametrize("feat,side", [(f, "+" if s > 0 else "-") for f, s, _ in ED2_SPECS])
def test_every_registered_detector_has_a_faithful_sentence_or_none(feat, side):
    made = _sentence(feat + side, SAMPLE)
    if made is None:
        return
    text, evidence = made
    assert check(text, evidence)["ok"], text


def test_sentences_carry_measured_numbers():
    text, _ = _sentence("pay_lr+", SAMPLE)
    assert "18%" in text
    text, _ = _sentence("price_lr2+", SAMPLE)
    assert "30%" in text and "sáu" in text
    text, _ = _sentence("grp_pay_up_n+", SAMPLE)
    assert text.startswith("Trong 35 ngày trước, 4 người")


def test_left_tail_customer_discount_and_wrong_side_is_silent():
    assert "thấp bất thường" in _sentence("cust_z-", SAMPLE)[0]
    assert _sentence("cust_z+", SAMPLE) is None             # measured value is negative: no "high" sentence
    assert _sentence("pay_lr+", {"pay_lr": 0}) is None


def test_observations_respect_tail_threshold_and_top():
    parts = {"pay_lr+": 9.0, "price_lr2+": 6.0, "adv_growth+": 5.0, "cust_z-": 3.0}
    out = change_observations(SAMPLE, parts)
    assert [o["feature"] for o in out] == ["pay_lr+", "price_lr2+"]
    assert all(o["tail"] >= 4 for o in out)


def test_tampered_number_fails_fidelity():
    text, evidence = _sentence("adv_growth+", SAMPLE)
    assert not check(text.replace("25%", "35%"), evidence)["ok"]
