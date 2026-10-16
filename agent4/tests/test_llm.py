import os,json
import httpx
import pytest
from agent4.agent.llm import OllamaClient,ScriptedClient,LLMUnavailable,LLMResponse
from agent4.config import LLMConfig

def test_ollama_payload_schema_and_usage():
    seen = []
    def respond(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200,json={'message':{'content':'{"ok":true}'},'prompt_eval_count':12,'eval_count':6})
    with OllamaClient(transport=httpx.MockTransport(respond)) as llm:
        result=llm.chat([{'role':'user','content':'test'}],schema={'type':'object'},options={'num_ctx':4096},think=False)
    assert result.usage=={'prompt_tokens':12,'eval_tokens':6}
    assert result.latency_ms>0
    assert seen[0]['stream'] is False and seen[0]['think'] is False
    assert seen[0]['format']=={'type':'object'}
    assert seen[0]['options']['num_ctx']==4096 and seen[0]['options']['temperature']==0

@pytest.mark.parametrize('mode',['timeout','server','malformed'])
def test_one_retry_then_failure(mode):
    attempts=[]
    def respond(request):
        attempts.append(request)
        if mode=='timeout':
            raise httpx.ReadTimeout('test',request=request)
        return httpx.Response(503,json={}) if mode=='server' else httpx.Response(200,json={})
    with OllamaClient(transport=httpx.MockTransport(respond),retry_delay=0) as llm:
        with pytest.raises(LLMUnavailable):
            llm.chat([])
    assert len(attempts)==2

def test_permanent_model_failure_not_retried():
    attempts=[]
    def respond(request):
        attempts.append(request)
        return httpx.Response(404,json={'error':'no model'})
    with OllamaClient(transport=httpx.MockTransport(respond)) as llm:
        with pytest.raises(LLMUnavailable): llm.chat([])
    assert len(attempts)==1

def test_scripted_client():
    llm=ScriptedClient([{'action':'refuse'},LLMResponse(text='hello'),LLMUnavailable('offline')])
    assert json.loads(llm.chat([]).text)['action']=='refuse'
    assert llm.chat([]).text=='hello'
    with pytest.raises(LLMUnavailable): llm.chat([])
    with pytest.raises(LLMUnavailable): llm.chat([])
    assert len(llm.requests)==4

@pytest.mark.llm
@pytest.mark.skipif(os.getenv('AGENT4_RUN_LLM')!='1',reason='set AGENT4_RUN_LLM=1 for local model integration')
@pytest.mark.parametrize('model',['qwen3:4b-instruct-2507-q4_K_M','qwen3:8b'])
def test_local_models(model):
    with OllamaClient(LLMConfig(model=model,num_ctx=4096)) as llm:
        response=llm.chat([{'role':'user','content':'Trả JSON {"ok": true}.'}],schema={'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok']},think=False)
    assert json.loads(response.text)['ok'] is True
    assert response.usage['eval_tokens']>0
