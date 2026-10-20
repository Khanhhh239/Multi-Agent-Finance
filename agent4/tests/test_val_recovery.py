import pytest
from scripts.recover_p2_val import require_recoverable


def test_recovery_requires_original_routing_and_frozen_val_data():
    meta={'split':'val','config':{'verifier':False,'answer_mode':'template'},'routing_hash':'original','data_hashes':{'e1':'frozen'}}
    require_recoverable(meta,'original',{'e1':'frozen'})
    with pytest.raises(ValueError,match='source'):require_recoverable(meta,'changed',{'e1':'frozen'})
    with pytest.raises(ValueError,match='data'):require_recoverable(meta,'original',{'e1':'changed'})
    with pytest.raises(ValueError,match='VAL only'):require_recoverable({**meta,'split':'test'},'original',{'e1':'frozen'})
    with pytest.raises(ValueError,match='diagnostic'):require_recoverable({**meta,'config':{'verifier':True,'answer_mode':'template'}},'original',{'e1':'frozen'})
