import pytest
from eval.prepare_warehouses import reconciliation,GAPS


def test_only_zero_gaps_allowed():
    assert reconciliation(dict.fromkeys(GAPS,0))==dict.fromkeys(GAPS,0)
    for key in GAPS:
        stats=dict.fromkeys(GAPS,0);stats[key]=.01
        with pytest.raises(ValueError):reconciliation(stats)
