import subprocess

import numpy as np
import pandas as pd
import pytest

from analysis.benchmark_t1_khanh_vs_v6 import (
    COMMIT, LEGACY_FILES, ROOT, bootstrap_difference, legacy_labels, old_module, paid_cdf,
    probability_score, restricted_score,
)
from experiments.t1_competing_v6.features import V6_FEATURES


@pytest.fixture(scope="module")
def archived(tmp_path_factory):
    output = tmp_path_factory.mktemp("khanh_benchmark")
    for name in LEGACY_FILES:
        path = output / "legacy/agent1" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(subprocess.check_output(["git", "show", f"{COMMIT}:agent1/{name}"], cwd=ROOT))
    return old_module(output)


def test_archived_native_configuration_and_common_features(archived):
    model = archived.HazardGBM(params={"num_threads": 4})
    assert model.rounds == 600
    assert model.p["num_leaves"] == 63
    assert model.p["seed"] == 7
    assert archived.K == 13
    assert archived.FEATURES == V6_FEATURES[:46]
    assert archived.FULL_WEEK_ONLY


def test_archived_paid_labels_keep_writeoff_as_nonpaid_and_stop_at_paid(archived):
    frame = pd.DataFrame(0., index=range(4), columns=archived.FEATURES)
    frame["cutoff"] = pd.to_datetime(["2024-01-01"] * 3 + ["2024-04-23"])
    frame["label_date"] = pd.to_datetime(["2024-01-08", "2024-01-16", None, None])
    frame["writeoff_date"] = pd.to_datetime([None, None, "2024-01-15", None])
    labeled = legacy_labels(archived, frame, "2024-05-01")
    assert labeled.event.tolist() == [1, 1, 0, 0]
    assert np.isinf(labeled.remaining.iloc[2])
    assert labeled.time_obs.iloc[2] == 121
    _, y, ix = archived.expand(labeled)
    assert np.bincount(ix).tolist() == [1, 3, 13, 1]
    assert y[ix == 0].tolist() == [1]
    assert y[ix == 1].tolist() == [0, 0, 1]
    assert not y[ix == 2].any()


@pytest.mark.parametrize("day", [28, 91, 120, 180, 270, 365])
def test_native_paid_cdf_constant_hazard(day):
    h = np.full((2, 13), .1)
    np.testing.assert_allclose(paid_cdf(h, day), 1 - .9 ** (day / 7))


def test_native_tail_uses_published_clipping():
    np.testing.assert_allclose(paid_cdf(np.zeros((1, 13)), 120), 1 - .98 ** (29 / 7))
    with pytest.raises(ValueError):
        paid_cdf(np.ones((1, 13)), 91)


def test_proper_paid_score_does_not_pad_legacy_writeoff_probability():
    result = probability_score([1, 0], [.8, .1])
    assert result["paid_brier"] == pytest.approx(.025)
    assert result["paid_gap"] == pytest.approx(-.05)
    with pytest.raises(ValueError):
        probability_score([1, 0], [.8, np.nan])


def test_restricted_score_includes_unpaid_without_inventing_payment():
    frame = pd.DataFrame({"cutoff": pd.to_datetime(["2024-01-01"] * 2),
                          "label_date": pd.to_datetime(["2024-01-06", None])})
    result = restricted_score(frame, np.array([[5, 5, 5], [np.nan, np.nan, np.nan]]))
    assert result["restricted_pinball120"] == 0
    assert result["restricted_median_mae120"] == 0


def test_clustered_difference_is_paired_and_reproducible():
    frame = pd.DataFrame({"firm_id": ["A", "A", "B"]})
    result, draws = bootstrap_difference(frame, np.zeros(3), 17)
    assert result["firms"] == 2
    assert result["delta_v6_minus_khanh"] == result["ci_low"] == result["ci_high"] == 0
    np.testing.assert_array_equal(draws, np.zeros(1000))
