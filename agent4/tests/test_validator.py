from types import SimpleNamespace
import pytest
from agent4.engine.metrics import REGISTRY
from agent4.agent.preprocess import Hints,PeriodHit,EntityHit,analyze
from agent4.agent.tools import Principal
from agent4.agent.validator import validate,repair_prompt
from agent4.engine.periods import resolve_period

def check(engine,call,hints=None,principal=None,candidates=None):
    return validate(call,hints=hints or Hints(),candidates=candidates or list(REGISTRY),principal=principal or Principal(),engine=engine)

@pytest.mark.parametrize('metric',REGISTRY)
def test_valid_metric_and_defaults(engine,metric):
    h=Hints(view_hint='tax' if REGISTRY[metric].default_view=='tax' else None)
    result=check(engine,{'action':'query_metric','metric':metric},h)
    assert result.ok,result.errors
    assert result.fixed_call['view']==REGISTRY[metric].default_view

@pytest.mark.parametrize('bad',[
    {},[],None,{'action':'delete'}, {'action':'query_metric','metric':'fake'},
    {'action':'query_metric','metric':'net_profit','scope':{}},
    {'action':'query_metric','metric':'net_profit','top_k':0},
    {'action':'query_metric','metric':'net_profit','top_k':51},
    {'action':'query_metric','metric':'net_profit','params':{'sql':'SELECT 1'}},
    {'action':'query_metric','metric':'net_profit','filters':{'unknown':'secret'}},
    {'action':'query_metric','metric':{'x':1}},
])
def test_bad_schema_never_executes(engine,bad):
    assert not check(engine,bad).ok

@pytest.mark.parametrize('metric',['net_revenue','net_profit','cogs','gross_profit','operating_expenses'])
def test_tax_view_never_passes_for_operational_question(engine,metric):
    result=check(engine,{'action':'query_metric','metric':metric,'view':'tax'})
    if result.ok: assert result.fixed_call['view']=='mgmt'
    else: assert result.action in ('repair','clarify')

def test_hints_correct_period_comparison_and_group(engine):
    h=analyze('Giá vốn hàng bán theo từng tháng trong 6 tháng gần nhất?',engine)
    result=check(engine,{'action':'query_metric','metric':'cogs','period':'this_year'},h)
    assert result.ok and result.fixed_call['period']=='last_6_months' and result.fixed_call['group_by']=='month'
    h=analyze('Doanh thu quý này so với quý trước?',engine)
    result=check(engine,{'action':'query_metric','metric':'net_revenue'},h)
    assert result.ok and result.fixed_call['period']=='this_quarter'
    assert result.fixed_call['compare_to']=='previous_period'

def test_explicit_unknown_period_repair(engine):
    assert check(engine,{'action':'query_metric','metric':'net_profit','period':'some day'}).action=='repair'

def test_future_flow_refused(engine):
    assert check(engine,{'action':'query_metric','metric':'net_revenue','period':'2030'}).action=='refuse'

@pytest.mark.parametrize('cue',['jailbreak','unsafe_action','out_of_scope'])
def test_pre_filter_cues_enforced(engine,cue):
    assert check(engine,{'action':'query_metric','metric':'net_revenue'},Hints(cues={cue})).action=='refuse'

def test_semantic_ambiguity_asks(engine):
    h=analyze('Lợi nhuận tháng này?',engine)
    assert check(engine,{'action':'query_metric','metric':'gross_profit'},h).action=='clarify'

def test_ambiguous_entity_asks(engine):
    h=Hints(entities=[EntityHit('customer','khách Hoàng',['a','b'])])
    assert check(engine,{'action':'query_metric','metric':'ar_balance'},h).action=='clarify'

def test_candidate_boundary(engine):
    assert not check(engine,{'action':'query_metric','metric':'net_profit'},candidates=['net_revenue']).ok

@pytest.mark.parametrize('principal',[Principal(role='auditor'),Principal(role='sales'),Principal(role='unknown')])
def test_permissions_block_before_engine(engine,principal):
    result=check(engine,{'action':'query_metric','metric':'cash_and_equivalents'},principal=principal)
    assert not result.ok and result.action=='refuse'

def test_unimplemented_subledger_filter_does_not_silently_disappear(engine):
    r=check(engine,{'action':'query_metric','metric':'payroll_summary','filters':{'branch':'HCM'}})
    assert not r.ok and r.errors[0].code=='FILTER_UNSUPPORTED'

def test_safe_proposal_is_only_structured_draft(engine):
    assert check(engine,{'action':'propose_action','action_type':'flag_for_review','rationale':'kiểm tra'}).ok

def test_repair_diagnostic_is_short(engine):
    result=check(engine,{'action':'delete'})
    prompt=repair_prompt(result.errors)
    assert len(prompt.split())<=25 and 'SCHEMA' in prompt
