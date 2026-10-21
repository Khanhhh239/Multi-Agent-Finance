import pandas as pd
import pytest
from agent1.eval.copula_selection import select_copulas


def scores():
    return pd.DataFrame(dict(world=['src']*3,outcome_end=['2023-06-26']*3,rho=[0.,.15,.15],rho_customer=[0.,0.,.2],IS80=[9.,7.,6.]))


def test_joint_and_one_factor_selected_on_same_source_score():
    result=select_copulas(scores(),test_origin='2024-07-01')
    assert result['source_selected_one_factor']==(.15,0.)
    assert result['source_selected_hierarchical']==(.15,.2)


@pytest.mark.parametrize('changes',[dict(world='tgt'),dict(outcome_end='2024-06-01'),dict(rho_customer=.9)])
def test_target_future_or_invalid_variance_cannot_select(changes):
    with pytest.raises(ValueError):select_copulas(scores().assign(**changes),test_origin='2024-07-01')
