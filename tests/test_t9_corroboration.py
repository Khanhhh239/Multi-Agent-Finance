import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.models.t9_fast import corroborated, reconcile_arrays  # noqa: E402


def test_memo_number_corroborates():
    assert corroborated(pd.Series({'name_score': 10}), {1234}, [1234, 99])


def test_name_corroborates():
    assert corroborated(pd.Series({'name_score': 95}), set(), [7])


def test_neither_does_not_corroborate():
    assert not corroborated(pd.Series({'name_score': 60}), {5}, [7])
    assert not corroborated(pd.Series({}), set(), [7])


def test_guard_threshold_must_be_at_least_tau():
    try:
        reconcile_arrays(None, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), tau_auto=.8, corroborate_below=.5)
    except ValueError:
        return
    raise AssertionError('expected ValueError')
