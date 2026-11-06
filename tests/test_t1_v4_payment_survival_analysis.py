"""Check full-payment timing and T1 geometric tail calculations."""

import numpy as np
import pytest

from analysis.analyze_t1_v4_payment_survival import (
    predicted_cdf, summarize_timing, week_hazards,
)


def test_tail_curve_starts_at_week_13_and_uses_four_week_mean():
    hazards = np.full((2, 13), .1)
    hazards[1, -4:] = .04
    at_91 = predicted_cdf(hazards, 91)
    at_120 = predicted_cdf(hazards, 120)
    assert at_91[0] == pytest.approx(1 - .9**13)
    assert at_120[0] == pytest.approx(1 - .9**13 * .9 ** (29 / 7))
    assert at_120[1] == pytest.approx(1 - (1 - at_91[1]) * .96 ** (29 / 7))


def test_timing_keeps_unpaid_and_writeoff_out_of_paid_buckets():
    timing = summarize_timing(np.array([10., 150., np.inf, 400.]),
                              np.array([np.inf, np.inf, 200., np.inf]))
    assert timing["paid_by_120"] == 1
    assert timing["paid_day_121_to_365"] == 1
    assert timing["not_paid_by_365"] == 2
    assert timing["written_off_by_365"] == 1
    assert timing["observed_q50_all_if_by_365"] == 150
    assert timing["observed_q90_all_if_by_365"] is None


def test_week_hazard_uses_actual_survivors_and_exposes_writeoff_mass():
    hazards = np.full((3, 13), .2)
    rows = week_hazards(hazards, np.array([5., 12., np.inf]),
                        np.array([np.inf, np.inf, 10.]), max_week=3)
    assert rows[0]["at_risk"] == 3 and rows[0]["paid_in_week"] == 1
    assert rows[1]["at_risk"] == 2 and rows[1]["paid_in_week"] == 1
    assert rows[2]["at_risk"] == 1 and rows[2]["paid_in_week"] == 0
    assert rows[2]["already_written_off_at_week_start"] == 1
    assert rows[2]["active_at_risk_excluding_writeoff"] == 0
