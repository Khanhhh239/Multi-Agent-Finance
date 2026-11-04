"""Structured LLM provider boundary and an Ollama implementation."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Protocol, TypeVar, runtime_checkable

import httpx
from pydantic import BaseModel

from ..errors import LLMProviderError, LLMTimeoutError
from .parser import parse_structured_output

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@runtime_checkable
class LLMProvider(Protocol):
    @property
    def model_id(self) -> str: ...

    @property
    def last_usage(self) -> TokenUsage: ...

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[ModelT],
    ) -> ModelT: ...


class OllamaLLMProvider:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        temperature: float = 0.0,
        timeout_s: float = 180.0,
        max_retries: int = 1,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.transport = transport
        self._last_usage = TokenUsage()

    @property
    def model_id(self) -> str:
        return f"ollama:{self.model}"

    @property
    def last_usage(self) -> TokenUsage:
        return self._last_usage

    async def _request(
        self,
        messages: list[dict[str, str]],
        response_model: type[ModelT],
    ) -> ModelT:
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": response_model.model_json_schema(),
            "options": {"temperature": self.temperature},
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_s,
                transport=self.transport,
            ) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=body)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"LLM request timed out after {self.timeout_s}s") from exc
        except (httpx.HTTPError, OSError, json.JSONDecodeError) as exc:
            raise LLMProviderError(f"Ollama request failed: {exc}") from exc
        try:
            content = payload["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMProviderError("Ollama response is missing message.content") from exc
        self._last_usage = TokenUsage(
            prompt_tokens=int(payload.get("prompt_eval_count", 0)),
            completion_tokens=int(payload.get("eval_count", 0)),
        )
        return parse_structured_output(content, response_model)

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[ModelT],
    ) -> ModelT:
        error: LLMProviderError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await self._request(messages, response_model)
            except LLMProviderError as exc:
                error = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(min(0.25 * (2**attempt), 1.0))
        assert error is not None
        raise error


class MockLLMProvider:
    def __init__(self, responses: BaseModel | dict | list[BaseModel | dict]) -> None:
        self.responses = responses if isinstance(responses, list) else [responses]
        self.calls = 0
        self.messages: list[list[dict[str, str]]] = []
        self._last_usage = TokenUsage()

    @property
    def model_id(self) -> str:
        return "mock:v1"

    @property
    def last_usage(self) -> TokenUsage:
        return self._last_usage

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[ModelT],
    ) -> ModelT:
        self.messages.append(messages)
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        response = self.responses[index]
        if isinstance(response, BaseModel):
            return response_model.model_validate(response.model_dump())
        return response_model.model_validate(response)
