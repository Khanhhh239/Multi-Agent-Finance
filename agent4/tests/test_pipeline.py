import json
import pytest
from agent4.engine.metrics import REGISTRY
from agent4.agent.pipeline import PipelineAgent,PipelineConfig,native_tools
from agent4.agent.llm import ScriptedClient,LLMResponse
from agent4.agent.state import ConversationState


def cfg(**kwargs):return PipelineConfig(hints=True,output_mode='schema',verifier=True,**kwargs)


def test_b0_exposes_66_real_native_functions_without_hints(engine):
    response=LLMResponse(tool_calls=[{'function':{'name':'net_revenue','arguments':{'period':'2026-Q3'}}}])
    llm=ScriptedClient([response]);reply=PipelineAgent(engine,llm,PipelineConfig()).ask('Tra doanh thu thuần quý 3/2026')
    assert reply.behavior=='answer'
    assert len(llm.requests[0]['tools'])==66
    assert {t['function']['name'] for t in llm.requests[0]['tools']}==set(REGISTRY)
    assert 'HINTS' not in llm.requests[0]['messages'][-1]['content']


@pytest.mark.parametrize('metrics',[['net_revenue','cogs'],['net_revenue','cogs','gross_profit']])
def test_two_three_metric_answers_use_only_engine_values(engine,metrics):
    llm=ScriptedClient([{'calls':[{'action':'query_metric','metric':m,'period':'2026-Q3'} for m in metrics]}])
    reply=PipelineAgent(engine,llm,cfg()).ask('Doanh thu thuần, giá vốn hàng bán và lợi nhuận gộp quý 3/2026?')
    assert reply.behavior=='answer' and len(reply.blocks['results'])==len(metrics)
    assert len(reply.blocks['lineage_ids'])==len(metrics)
    for row in reply.blocks['results']:assert row['value']==engine.query(row['metric_id'],'2026-Q3')['value']
    assert any(s.stage=='verifier_final' and s.data['ok'] for s in reply.trace)


@pytest.mark.parametrize('calls',[
    [{'action':'query_metric','metric':m} for m in ['net_revenue','cogs','gross_profit','net_profit']],
    [{'action':'query_metric','metric':'net_revenue'},{'action':'query_metric','metric':'cogs','scope':{}}],
])
def test_entire_batch_validated_before_any_execution(engine,calls):
    reply=PipelineAgent(engine,ScriptedClient([{'calls':calls}]*3),cfg()).ask('Tra doanh thu thuần và giá vốn')
    assert reply.behavior!='answer' and not any(s.stage=='engine' for s in reply.trace)


def test_group_followup_carries_metric_and_period(engine):
    state=ConversationState();llm=ScriptedClient([{'action':'query_metric','metric':'net_revenue','period':'2026-Q3'},
                                                {'action':'query_metric','metric':'net_revenue'}])
    agent=PipelineAgent(engine,llm,cfg());agent.ask('Doanh thu thuần quý 3/2026?',state=state)
    reply=agent.ask('Trong kỳ đó, phân theo chi nhánh.',state=state)
    assert reply.behavior=='answer'
    assert reply.blocks['calls'][0]['period']=='2026-Q3' and reply.blocks['calls'][0]['group_by']=='branch'


def test_why_question_uses_comparison_and_no_invented_cause(engine):
    llm=ScriptedClient([{'action':'query_metric','metric':'net_profit'}])
    reply=PipelineAgent(engine,llm,cfg()).ask('Vì sao lợi nhuận sau thuế tháng này giảm?')
    assert reply.behavior=='answer' and reply.blocks['calls'][0]['compare_to']=='previous_period'
    assert 'Chưa đủ bằng chứng' in reply.text or 'không xác nhận giả định giảm' in reply.text
    assert not any(s.stage=='verifier_final' and not s.data['ok'] for s in reply.trace)


def test_tax_only_metric_is_not_unconditionally_changed_to_management_in_b0(engine):
    reply=PipelineAgent(engine,ScriptedClient([LLMResponse(tool_calls=[{'function':{'name':'taxable_income','arguments':{'period':'this_month'}}}])]),PipelineConfig()).ask('Thu nhập chịu thuế tháng này?')
    assert reply.behavior=='answer' and reply.blocks['results'][0]['view']=='tax'


def test_model_selected_slots_still_cannot_emit_financial_text(engine):
    llm=ScriptedClient([{'action':'query_metric','metric':'net_revenue'},{'slots':['100 tỷ đồng']}])
    reply=PipelineAgent(engine,llm,cfg(answer_mode='hybrid')).ask('Doanh thu thuần tháng này?')
    assert reply.behavior=='answer' and '100 tỷ' not in reply.text
    assert any(s.stage=='insight_fallback' for s in reply.trace)

def test_history_keeps_partner_codes_instead_of_unwrapped_names(engine):
    code,partner=next((c,p) for c,p in engine.partners.items() if p['type']=='CUSTOMER')
    state=ConversationState()
    llm=ScriptedClient([{'action':'query_metric','metric':'ar_balance','filters':{'customer':partner['name']}}])
    reply=PipelineAgent(engine,llm,cfg()).ask('Tra phải thu của khách hàng '+code,state=state)
    assert reply.behavior=='answer'
    filters=state.history[-1]['calls'][0]['filters']
    assert filters['customer']==[code] and partner['name'] not in json.dumps(filters,ensure_ascii=False)
