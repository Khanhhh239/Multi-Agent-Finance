"""Authenticated OpenAI-compatible chat client with context-size guards."""

import json
import time
import urllib.error
import urllib.request

from ..runtime_config import env

CHARS_PER_TOKEN = 3.2


class LLMUnavailable(RuntimeError):
    pass


class ContextOverflow(RuntimeError):
    pass


class OpenAICompatible:
    """Minimal JSON client for OpenAI-compatible chat-completions endpoints."""

    def __init__(self, model, base_url, api_key, num_ctx=32768, timeout=180, think=False):
        self.model = model
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key or ''
        self.num_ctx = int(num_ctx)
        self.timeout = timeout
        self.think = think

    def _endpoint(self):
        return self.base_url if self.base_url.endswith('/chat/completions') else f'{self.base_url}/chat/completions'

    def chat(self, system: str, user: str, schema: dict | None = None, num_predict: int = 900) -> tuple[str, dict]:
        expected = (len(system) + len(user)) / CHARS_PER_TOKEN
        if expected + num_predict > self.num_ctx - 128:
            raise ContextOverflow(f'prompt about {expected:.0f} tokens plus {num_predict} output exceeds num_ctx {self.num_ctx}')
        if not self.api_key:
            raise LLMUnavailable('Chưa cấu hình AGENT3_LLM_API_KEY cho nhà cung cấp API.')
        body = dict(
            model=self.model,
            stream=False,
            temperature=0,
            max_tokens=num_predict,
            messages=[dict(role='system', content=system), dict(role='user', content=user)],
        )
        if schema:
            body['response_format'] = {'type': 'json_object'}
        req = urllib.request.Request(
            self._endpoint(),
            data=json.dumps(body).encode(),
            headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {self.api_key}'},
        )
        started = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read(512).decode('utf-8', 'replace')
            raise LLMUnavailable(f'Nhà cung cấp LLM trả HTTP {exc.code}: {detail[:240]}') from exc
        except (urllib.error.URLError, ConnectionError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMUnavailable(f'Không gọi được nhà cung cấp LLM tại {self.base_url}: {exc}') from exc
        try:
            message = payload['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMUnavailable('Phản hồi LLM không có choices[0].message.content hợp lệ.') from exc
        if isinstance(message, list):
            message = ''.join(str(part.get('text', '')) if isinstance(part, dict) else str(part) for part in message)
        stats = dict(
            model=self.model,
            num_ctx=self.num_ctx,
            prompt_tokens=(payload.get('usage') or {}).get('prompt_tokens'),
            output_tokens=(payload.get('usage') or {}).get('completion_tokens'),
            seconds=round(time.time() - started, 1),
            provider=self.base_url,
        )
        return str(message), stats


def configured_llm(model: str | None = None, *, num_ctx: int | None = None, timeout: int | None = None):
    """Build Agent 3's authenticated OpenAI-compatible chat client."""
    provider = (env('AGENT3_LLM_PROVIDER', 'openai') or 'openai').lower()
    if provider not in ('openai', 'openai-compatible', 'groq', 'openrouter'):
        raise LLMUnavailable(f'Nhà cung cấp LLM không được hỗ trợ: {provider}')
    resolved_model = model or env('AGENT3_LLM_MODEL', 'qwen/qwen3.8-27b')
    resolved_ctx = num_ctx or int(env('AGENT3_LLM_NUM_CTX', '32768'))
    resolved_timeout = timeout or int(env('AGENT3_LLM_TIMEOUT', '180'))
    key = env('AGENT3_LLM_API_KEY') or env('AGENT3_API_KEY') or env('OPENAI_API_KEY') or env('GROQ_API_KEY')
    base_url = env('AGENT3_LLM_BASE_URL', 'https://api.groq.com/openai/v1')
    return OpenAICompatible(resolved_model, base_url, key, resolved_ctx, resolved_timeout)
