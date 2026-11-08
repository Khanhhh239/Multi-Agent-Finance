import pandas as pd
import pytest
from agent1.data.real_loaders import label_sba


def sba_rows():
    return pd.DataFrame({'LoanStatus': ['EXEMPT', 'EXEMPT', 'PIF', 'CHGOFF', 'COMMIT'],
                         'ApprovalDate': ['2018-01-01'] * 5,
                         'PaidInFullDate': [None, None, '2019-01-01', None, None],
                         'ChargeOffDate': [None, '2019-01-01', None, '2023-01-01', None]})


def test_exempt_policies_preserve_unknown_outcomes():
    raw = sba_rows()
    drop = label_sba(raw)
    assert len(drop) == 2
    keep = label_sba(raw, exempt='keep')
    assert keep.y.tolist() == [0, 1, 0, 0]
    cens = label_sba(raw, exempt='censor')
    assert pd.isna(cens.y.iloc[0])
    assert not cens.label_observed.iloc[0]
    assert cens.y.iloc[1] == 1  # Có chứng cứ xoá nợ trong kỳ thì nhãn dương vẫn biết.
    assert cens.label_observed.iloc[1]
    with pytest.raises(ValueError):
        label_sba(raw, exempt='invent')


def test_sba_rejects_cohort_without_full_horizon():
    df = sba_rows().assign(ApprovalDate='2025-01-01')
    assert label_sba(df, asof='2026-06-30').empty
