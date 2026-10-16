import json,time
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from agent4.agent.state import ConversationState,update
from agent4.agent.fewshot import FewShotBank
from agent4.agent.prompts import build_messages,SYSTEM
from agent4.agent.preprocess import Hints,analyze
from agent4.agent.tools import build_union_schema
from agent4.engine.metrics import REGISTRY

def test_bank_has_60_development_examples_and_valid_calls():
    bank=FewShotBank()
    assert len(bank.examples)==60
    validator=Draft202012Validator(build_union_schema(list(REGISTRY)))
    for example in bank.examples:
        assert example['split']=='dev'
        assert validator.is_valid(example['answer']),example
    assert len({e['answer']['action'] for e in bank.examples})>=4

def test_knn_excludes_exact_question():
    bank=FewShotBank()
    q=bank.examples[0]['question']
    chosen=bank.select_examples(q,3)
    assert len(chosen)==3 and all(e['question']!=q for e in chosen)

def test_bank_rejects_non_dev(tmp_path):
    p=tmp_path/'bad.jsonl'
    p.write_text(json.dumps({'split':'test','question':'q','answer':{}}),encoding='utf-8')
    with pytest.raises(ValueError): FewShotBank(p)

def test_prompt_snapshot_and_fixed_prefix():
    messages=build_messages('Tra doanh thu tháng trước',Hints(),['net_revenue','cogs'])
    expected=json.loads(Path('tests/data/prompt_golden.json').read_text(encoding='utf-8'))
    assert messages==expected
    assert messages[0]['content']==build_messages('Câu khác',Hints(),['net_profit'])[0]['content']==SYSTEM

def test_state_is_bounded_expires_and_does_not_cross_users():
    state=ConversationState(last_metric='net_revenue',last_period='this_month',last_view='mgmt',
                            last_filters={'customer':['KH0001']*100},updated_at=100,user_id='a')
    assert len(state.summary().encode())<=80
    assert state.active('a',now=1000) and not state.active('a',now=1001)
    assert not state.active('b',now=200)

def test_state_update_preserves_codes_only_and_three_turns(engine):
    state=ConversationState()
    call={'action':'query_metric','metric':'net_revenue','period':'2026-Q3','filters':{'branch':'Hồ Chí Minh'},'view':'mgmt'}
    result=engine.query('net_revenue','2026-Q3',filters={'branch':'HCM'})
    for i in range(5): state=update(state,call,result,question=str(i),user_id='a')
    assert len(state.history)==3 and state.last_filters=={'branch':['HCM']}
    assert state.last_result.get('display') and '_sql' not in state.last_result

def test_untrusted_names_in_question_and_state_are_wrapped():
    state=ConversationState(last_filters={'customer':'Hoàng Long'})
    text=json.dumps(build_messages('Hoàng Long nợ bao nhiêu',Hints(),['ar_balance'],state),ensure_ascii=False)
    assert '<du_lieu_khong_tin_cay' in text
    assert 'user.question' in text and 'state' in text

def test_followup_inherits_and_explicit_period_overrides(engine):
    state=ConversationState(last_metric='net_revenue',last_period='2026-Q3',last_filters={'branch':['HCM']})
    hints=analyze('Còn quý trước?',engine,state)
    assert hints.inherited.get('metric')=='net_revenue'
    assert not hints.inherited.get('period')
    assert hints.periods[0].period.token=='last_quarter'
