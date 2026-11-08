import numpy as np
import pandas as pd
import pytest
from agent1.models.chronos_context import balance_context


def test_future_balance_cannot_change_chronos_context():
    series=pd.Series(np.arange(500,dtype=float),index=pd.date_range('2023-01-01',periods=500))
    before=balance_context(series,'2024-01-01')
    changed=series.copy();changed[changed.index>'2024-01-01']=-1e20
    np.testing.assert_array_equal(before,balance_context(changed,'2024-01-01'))
    assert len(before)==52 and before[-1]==365
    with pytest.raises(ValueError,match='Thiếu'):balance_context(series.iloc[300:],'2024-01-01')
