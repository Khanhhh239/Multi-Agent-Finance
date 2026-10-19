import json
from agent4.agent.cli import main
from agent4.agent.llm import ScriptedClient


def test_configured_cli_supports_multiple_metrics(monkeypatch,tmp_path,warehouse,capsys):
    class Fake(ScriptedClient):
        def __init__(self,*a,**k):super().__init__([{'calls':[{'action':'query_metric','metric':'net_revenue'}, {'action':'query_metric','metric':'cogs'}]}])
        def __enter__(self):return self
        def __exit__(self,*a):pass
    monkeypatch.setattr('agent4.agent.cli.OllamaClient',Fake)
    config=tmp_path/'pipeline.yaml';config.write_text(json.dumps({'hints':True,'output_mode':'schema','verifier':True}),encoding='utf8')
    assert main(['--db',str(warehouse),'--config',str(config),'--question','Doanh thu thuần và giá vốn tháng này?',
                 '--json','--trace',str(tmp_path/'trace.jsonl')])==0
    result=json.loads(capsys.readouterr().out)
    assert result['behavior']=='answer' and len(result['blocks']['results'])==2
    assert result['blocks']['report_notice']=='formulas not accountant-approved'
