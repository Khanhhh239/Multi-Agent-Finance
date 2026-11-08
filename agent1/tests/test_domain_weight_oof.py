import numpy as np
import pandas as pd
import pytest
from agent1.models.domain_weight_oof import company_folds,oof_domain_weights


def data():
    return pd.DataFrame({'firm_id':np.repeat(['a','b','c','d'],3),'cutoff':pd.Timestamp('2023-01-01')})


def test_domain_folds_hold_out_entire_companies_and_cover_every_row_once():
    source=data();target=data();groups=np.r_['src/'+source.firm_id.to_numpy(),'tgt/'+target.firm_id.to_numpy()]
    counts=np.zeros(len(groups))
    for train,test in company_folds(source,target):
        assert not set(groups[train])&set(groups[test])
        assert {key.split('/')[0] for key in groups[test]}=={'src','tgt'}
        counts[test]+=1
    np.testing.assert_array_equal(counts,np.ones(len(groups)))


def test_too_few_companies_or_future_target_cannot_estimate_weights():
    with pytest.raises(ValueError):company_folds(data(),data().iloc[:3])
    with pytest.raises(ValueError,match='trước'):
        oof_domain_weights(data(),data().assign(cutoff='2024-07-01'),origin='2024-07-01')
