"""Local-only Ollama transport and a deterministic test double.

Experimental: công thức chưa được kế toán duyệt (G0.7 mở).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, Any
from time import perf_counter, sleep
import copy
import httpx
from agent4.config import LLMConfig

class LLMUnavailable(RuntimeError):
    code = 'LLM_UNAVAILABLE'

@dataclass
class LLMResponse:
    text: str = ''
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    latency_ms: float = 0.0
    raw: dict = field(default_factory=dict)

class LLMClient(Protocol):
    def chat(self,messages: list[dict],*,schema: dict|None=None,tools: list[dict]|None=None,
             options: dict|None=None,think: bool|None=None) -> LLMResponse: ...

class OllamaClient:
    def __init__(self,cfg: LLMConfig|None=None,*,transport=None,keep_alive='5m',retry_delay=.25):
        self.cfg = cfg or LLMConfig()
        self.keep_alive, self.retry_delay = keep_alive,retry_delay
        self.http = httpx.Client(base_url=self.cfg.base_url,timeout=self.cfg.timeout_s,transport=transport)

    def chat(self,messages,*,schema=None,tools=None,options=None,think=None):
        opts = {'temperature':self.cfg.temperature,'top_k':20,'top_p':.8,
                'num_ctx':self.cfg.num_ctx,'num_predict':512,**(options or {})}
        timeout_s=float(opts.pop('_timeout_s',self.cfg.timeout_s))
        payload = {'model':self.cfg.model,'messages':messages,'stream':False,'keep_alive':self.keep_alive,
                   'options':opts,'think':self.cfg.think if think is None else think}
        if schema is not None:
            payload['format'] = schema
        if tools is not None:
            payload['tools'] = tools
        start = perf_counter()
        for attempt in range(2):
            try:
                remaining=timeout_s-(perf_counter()-start)
                if remaining<=0: raise LLMUnavailable('Đã hết thời gian chờ model cục bộ.')
                response = self.http.post('/api/chat',json=payload,timeout=min(self.cfg.timeout_s,remaining))
                response.raise_for_status()
                raw = response.json()
                msg = raw['message']
                if not isinstance(msg,dict) or not isinstance(msg.get('content',''),str):
                    raise ValueError('invalid message')
                calls = msg.get('tool_calls') or []
                if not isinstance(calls,list):
                    raise ValueError('invalid tool calls')
                return LLMResponse(msg.get('content',''),calls,
                    {'prompt_tokens':int(raw.get('prompt_eval_count') or 0),'eval_tokens':int(raw.get('eval_count') or 0)},
                    (perf_counter()-start)*1000,raw)
            except (httpx.HTTPError,ValueError,KeyError,TypeError) as exc:
                # Permanent request/model failures should not be retried.
                permanent = isinstance(exc,httpx.HTTPStatusError) and exc.response.status_code<500 and exc.response.status_code!=429
                if attempt or permanent:
                    raise LLMUnavailable('Không kết nối được model cục bộ hoặc phản hồi không hợp lệ.') from exc
                sleep(self.retry_delay)
        raise LLMUnavailable('Model cục bộ chưa sẵn sàng.')

    def close(self):
        self.http.close()

    def __enter__(self):
        return self

    def __exit__(self,*exc):
        self.close()

class ScriptedClient:
    """Consume responses, JSON objects, strings, exceptions, or request callbacks."""
    def __init__(self,responses):
        self.responses = iter(responses)
        self.requests = []

    def chat(self,messages,*,schema=None,tools=None,options=None,think=None):
        import json
        request = copy.deepcopy(dict(messages=messages,schema=schema,tools=tools,options=options,think=think))
        self.requests.append(request)
        try:
            response = next(self.responses)
        except StopIteration as exc:
            raise LLMUnavailable('Kịch bản model giả đã hết phản hồi.') from exc
        if callable(response):
            response = response(request)
        if isinstance(response,Exception):
            raise response
        if isinstance(response,LLMResponse):
            return response
        text = response if isinstance(response,str) else json.dumps(response,ensure_ascii=False)
        return LLMResponse(text=text,usage={'prompt_tokens':0,'eval_tokens':0},raw={'scripted':True})
