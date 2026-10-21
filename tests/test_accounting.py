import pytest
from agent1.eval.accounting import accounting_days


def test_accounting_days_uses_average_balance_and_unit_invariance():
    assert accounting_days(100,300,2000)==36.5
    assert accounting_days(100e6,300e6,2000e6)==36.5


@pytest.mark.parametrize('values',[(1,2,0),(1,-2,3),(float('nan'),2,3),(1,2,float('inf'))])
def test_invalid_accounting_denominators_rejected(values):
    with pytest.raises(ValueError):accounting_days(*values)
