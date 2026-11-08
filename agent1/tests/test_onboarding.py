import json
import pytest
from agent1.models.onboarding import choose_strategy


def test_onboarding_requires_source_evidence_and_available_history(tmp_path):
    path=tmp_path/'policy.json'
    assert choose_strategy(12,1000,.8,path)=='zero-shot'
    policy=dict(target_used=False,selection_domain='src_company_holdout',training_firms=['a'],validation_firms=['b'],
        max_validated_domain_auc=.9,rules=[dict(months_history=3,min_rows=500,strategy='fine-tune')])
    path.write_text(json.dumps(policy))
    assert choose_strategy(3,500,.8,path)=='fine-tune'
    assert choose_strategy(2,500,.8,path)=='zero-shot'
    assert choose_strategy(3,499,.8,path)=='zero-shot'
    assert choose_strategy(12,1000,.95,path)=='zero-shot'
    policy['target_used']=True;path.write_text(json.dumps(policy))
    with pytest.raises(ValueError):choose_strategy(12,1000,.8,path)


@pytest.mark.parametrize('values',[(-1,0,.8),(0,-1,.8),(3,50,.3),(3,50,float('nan'))])
def test_onboarding_rejects_invalid_inputs(values):
    with pytest.raises(ValueError):choose_strategy(*values)
