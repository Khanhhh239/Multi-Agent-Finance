import pytest

from agent2.monitoring import population_stability


def test_psi_identical_data_is_zero_and_shift_is_positive():
    assert population_stability(range(100), range(100)) == 0
    assert population_stability(range(100), range(100, 200)) > 0


def test_constant_baseline_can_detect_departure_and_missing_stays_missing():
    assert population_stability([0] * 10, [0] * 10) == 0
    assert population_stability([0] * 10, [1] * 10) > 0
    assert population_stability([], [1]) is None
    with pytest.raises(ValueError):
        population_stability([0], [1], smoothing=0)
