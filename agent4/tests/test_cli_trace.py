import copy,json,subprocess,sys
import pytest
from pathlib import Path
from agent4.agent.cli import main
from agent4.agent.llm import ScriptedClient
from agent4.agent.trace import TraceWriter,public_data
from agent4.agent.orchestrator import AgentReply,Step
from agent4.agent.constants import NOTICE

def test_form_cli_does_not_need_llm(tmp_path,warehouse,capsys):
    trace=tmp_path/'form.jsonl'
    assert main(['--db',str(warehouse),'--query','net_revenue','--period','2026-Q3','--json','--trace',str(trace)])==0
    result=json.loads(capsys.readouterr().out)
    assert result['behavior']=='answer' and result['blocks']['G0_7']=='CHƯA ĐẠT'
    assert NOTICE in result['text']
    assert '_sql' not in json.dumps(result)
    assert json.loads(trace.read_text(encoding='utf-8'))['steps'][0]['stage']=='form_query'

def test_chat_cli_exercises_full_path_with_scripted_transport(monkeypatch,tmp_path,warehouse,capsys):
    class FakeClient(ScriptedClient):
        def __init__(self,*a,**k): super().__init__([{'action':'query_metric','metric':'net_revenue'},{'commentary':'Có thể xem chi tiết nguồn.'}])
        def __enter__(self): return self
        def __exit__(self,*a): pass
    monkeypatch.setattr('agent4.agent.cli.OllamaClient',FakeClient)
    assert main(['--db',str(warehouse),'--question','Doanh thu thuần tháng này là bao nhiêu?','--json','--trace',str(tmp_path/'chat.jsonl')])==0
    result=json.loads(capsys.readouterr().out)
    assert result['behavior']=='answer'
    assert {'hints','retriever','validator','engine','render','verifier_facts'}<={s['stage'] for s in result['trace']}

def test_trace_appends_utf8_readable_records_without_sql(tmp_path):
    p=tmp_path/'trace.jsonl'
    reply=AgentReply(NOTICE,{'lineage_ids':['L-x'],'calls':[{'action':'query_metric','metric':'net_revenue'}]},'answer',
                     [Step('engine',1,{'_sql':'SELECT SECRET','lineage_id':'L-x'})],{'prompt_tokens':8,'eval_tokens':2},10)
    writer=TraceWriter(p)
    first=writer.append('Doanh thu?',reply)
    second=writer.append('Còn kỳ trước?',reply)
    rows=[json.loads(line) for line in p.read_text(encoding='utf-8').splitlines()]
    assert first!=second and len(rows)==2
    assert 'SECRET' not in p.read_text(encoding='utf-8')
    assert all(r['G0_7']=='CHƯA ĐẠT' and r['experimental_notice']==NOTICE for r in rows)

def test_cli_help_documents_experimental_status():
    p=subprocess.run([sys.executable,'-X','utf8','-m','agent4.agent.cli','--help'],capture_output=True,text=True,encoding='utf-8')
    assert p.returncode==0 and 'G0.7' in p.stdout and '--model' in p.stdout

def test_bad_form_metric_returns_safe_json(tmp_path,warehouse,capsys):
    assert main(['--db',str(warehouse),'--query','not_real','--json','--trace',str(tmp_path/'bad.jsonl')])==0
    result=json.loads(capsys.readouterr().out)
    assert result['behavior']=='refuse' and NOTICE in result['text']
@pytest.mark.parametrize('metric,period,start,end,group',[
    ('cogs','last_6_months','2026-04-01','2026-09-30','month'),
    ('gross_profit','this_month','2026-10-01','2026-10-31','product_line'),
    ('expense_by_category','this_month','2026-10-01','2026-10-31','cost_category'),
])
def test_m1_scorer_rejects_missing_duplicate_and_wrong_group_values(engine,metric,period,start,end,group):
    from eval.smoke_m1 import check_groups
    result=engine.query(metric,period,group_by=group)
    assert not check_groups(engine.con,result,metric,start,end,group)
    missing=copy.deepcopy(result);missing['rows'].pop()
    assert 'group_coverage' in check_groups(engine.con,missing,metric,start,end,group)
    duplicate=copy.deepcopy(result);duplicate['rows'].append(duplicate['rows'][0])
    assert 'group_coverage' in check_groups(engine.con,duplicate,metric,start,end,group)
    wrong=copy.deepcopy(result);wrong['rows'][0]['value']+=1000
    assert any(e.startswith('group_value:') for e in check_groups(engine.con,wrong,metric,start,end,group))
