import numpy as np
import pandas as pd
import pytest

from experiments.t1_competing_v5.core import (
    PAID, WRITEOFF, aalen_johansen, cumulative_incidence,
    expand_weekly, label_first_event, observed_state,
)
from agent1.models.features import FEATURES
from experiments.t1_competing_v5.run import v5_state_at_day


def test_first_event_and_admin_censor_are_distinct():
    frame = pd.DataFrame({
        "cutoff": pd.to_datetime(["2025-01-01"] * 3),
        "label_date": pd.to_datetime(["2025-01-20", None, "2025-06-01"]),
        "writeoff_date": pd.to_datetime([None, "2025-02-10", None]),
        "closure_type": ["paid", "writeoff", "paid"],
    })
    labeled = label_first_event(frame, "2025-04-30")
    assert labeled.cause.tolist() == [PAID, WRITEOFF, 0]
    assert labeled.time_days.tolist() == [19, 40, 119]
    assert observed_state(labeled, 28).tolist() == [PAID, 0, 0]


def test_credit_only_is_never_hidden_as_censoring():
    frame = pd.DataFrame({
        "cutoff": pd.to_datetime(["2025-01-01"]),
        "label_date": pd.to_datetime([None]),
        "writeoff_date": pd.to_datetime([None]),
        "closure_type": ["credit_note"],
    })
    with pytest.raises(ValueError, match="fourth terminal cause"):
        label_first_event(frame, "2025-12-31")


def test_credit_adjusted_payment_and_conflicting_terminal_dates():
    frame = pd.DataFrame({
        "cutoff": pd.to_datetime(["2025-01-01"]),
        "label_date": pd.to_datetime(["2025-01-20"]),
        "writeoff_date": pd.to_datetime([None]),
        "closure_type": ["paid_after_credit_note"],
    })
    assert label_first_event(frame, "2025-12-31").cause.tolist() == [PAID]
    frame["writeoff_date"] = pd.Timestamp("2025-01-21")
    with pytest.raises(ValueError, match="coexist"):
        label_first_event(frame, "2025-12-31")


def test_three_states_conserve_probability():
    hazards = np.array([[[.7, .2, .1], [.5, .3, .2]]])
    fp, fw, so = cumulative_incidence(hazards)
    assert fp[0].tolist() == pytest.approx([.2, .41])
    assert fw[0].tolist() == pytest.approx([.1, .24])
    assert so[0].tolist() == pytest.approx([.7, .35])
    assert np.allclose(fp + fw + so, 1)


def test_aj_counts_writeoff_as_competing_event_not_paid():
    frame = pd.DataFrame({"time_days": [7, 14, 21, 30],
                          "cause": [PAID, WRITEOFF, 0, PAID],
                          "obs_days": [40, 40, 21, 40]})
    result = aalen_johansen(frame, [7, 14, 30])
    assert result[0]["aj_paid"] == pytest.approx(.25)
    assert result[1]["aj_writeoff"] == pytest.approx(.25)
    # One invoice is censored on day 21, leaving one at risk on day 30.
    assert result[2]["aj_paid"] == pytest.approx(.75)
    assert result[2]["aj_open"] == pytest.approx(0)


def test_weekly_risk_set_stops_after_first_event_and_drops_partial_week():
    frame = pd.DataFrame({name: [0.0, 0.0, 0.0] for name in FEATURES})
    frame["cutoff"] = pd.Timestamp("2025-01-01")
    frame["top1"] = np.nan
    frame["top2"] = np.nan
    frame["time_days"] = [8, 14, 10]
    frame["obs_days"] = [30, 30, 10]
    frame["cause"] = [PAID, WRITEOFF, 0]
    x, y, counts = expand_weekly(frame, FEATURES)
    assert len(x) == 5  # 3 rows in week 1; 2 terminal events in week 2.
    assert y.tolist() == [0, 0, 0, PAID, WRITEOFF]
    assert counts == {"open": 3, "paid": 1, "writeoff": 1}


def test_day_365_partial_week_keeps_three_state_identity():
    hazards = np.tile(np.array([.7, .2, .1]), (2, 53, 1))
    fp, fw, so = cumulative_incidence(hazards)
    p, w, o = v5_state_at_day(fp, fw, so, hazards, 365)
    assert np.allclose(p + w + o, 1)
    assert np.all(p > fp[:, 51])
    assert np.all(p < fp[:, 52])
