"""Minimal Ollama chat client with explicit context size and a truncation guard."""
import json
import time
import urllib.error
import urllib.request

CHARS_PER_TOKEN = 3.2     # measured on Vietnamese legal text with qwen3:8b (3.2 to 3.4) on 05/11/2026


class LLMUnavailable(RuntimeError):
    pass


class ContextOverflow(RuntimeError):
    pass


class Ollama:
    def __init__(self, model='qwen3:8b', url='http://127.0.0.1:11434', num_ctx=12288, timeout=600, think=False):
        self.model, self.url, self.num_ctx, self.timeout, self.think = model, url.rstrip('/'), num_ctx, timeout, think

    def chat(self, system: str, user: str, schema: dict | None = None, num_predict: int = 900) -> tuple[str, dict]:
        expected = (len(system) + len(user)) / CHARS_PER_TOKEN
        if expected + num_predict > self.num_ctx - 128:
            raise ContextOverflow(f'prompt about {expected:.0f} tokens plus {num_predict} output exceeds num_ctx {self.num_ctx}')
        body = dict(model=self.model, stream=False, think=self.think,
                    options=dict(num_ctx=self.num_ctx, temperature=0, seed=0, num_predict=num_predict),
                    messages=[dict(role='system', content=system), dict(role='user', content=user)])
        if schema:
            body['format'] = schema
        req = urllib.request.Request(f'{self.url}/api/chat', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        t = time.time()
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=self.timeout).read())
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            raise LLMUnavailable(f'Ollama không phản hồi tại {self.url}: {e}')
        pe = r.get('prompt_eval_count') or 0
        stats = dict(model=self.model, num_ctx=self.num_ctx, prompt_tokens=pe, expected_prompt_tokens=round(expected),
                     output_tokens=r.get('eval_count'), seconds=round(time.time() - t, 1))
        if pe >= self.num_ctx - 8 or (pe and pe < 0.6 * expected):
            raise ContextOverflow(f'model read {pe} prompt tokens, expected about {expected:.0f}: context was cut')
        return r['message']['content'], stats
