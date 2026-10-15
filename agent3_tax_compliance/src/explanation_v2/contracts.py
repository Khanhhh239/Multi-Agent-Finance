from datetime import date
from typing import Literal
from pydantic import Field, model_validator
from ..domain.base import Contract, Identifier, Stamped
from ..domain.envelope import Sha256


class Policy(Contract):
    version: Identifier = 'explanation-v2-1'
    enabled: bool = False
    provider: Literal['ollama'] = 'ollama'
    endpoint: str = 'http://127.0.0.1:11434/api/chat'
    model: str = 'qwen3:8b'
    model_revision: str = 'UNVERIFIED'
    timeout_seconds: float = Field(default=20, gt=0, le=60)
    max_output_tokens: int = Field(default=1536, ge=128, le=4096)
    max_context_bytes: int = Field(default=48000, ge=1024, le=128000)
    max_response_bytes: int = Field(default=64000, ge=1024, le=256000)
    top_k: int = Field(default=3, ge=1, le=5)
    max_facts: int = Field(default=30, ge=5, le=100)


class Chunk(Contract):
    chunk_id: Identifier
    document_id: Identifier
    locator: str = Field(min_length=1, max_length=500)
    document_sha256: Sha256
    text_sha256: Sha256
    text: str = Field(min_length=1, max_length=12000)
    effective_from: date
    effective_to: date | None = None
    reviewed: Literal[True]

    @model_validator(mode='after')
    def valid(self):
        import hashlib
        if hashlib.sha256(self.text.encode('utf-8')).hexdigest() != self.text_sha256:
            raise ValueError('Chunk text hash mismatch')
        if self.effective_to and self.effective_to <= self.effective_from:
            raise ValueError('Invalid chunk interval')
        return self


class Corpus(Contract):
    version: Identifier
    registry_version: Identifier
    chunks: tuple[Chunk, ...] = ()

    @model_validator(mode='after')
    def unique(self):
        if len({c.chunk_id for c in self.chunks}) != len(self.chunks):
            raise ValueError('Duplicate chunk IDs')
        return self


class Fact(Contract):
    fact_id: Identifier
    variants: tuple[str, ...] = Field(min_length=1)
    refs: tuple[str, ...]


class Context(Contract):
    evaluation_id: Identifier
    record_revision: int = Field(ge=1)
    record_sha256: Sha256
    facts: tuple[Fact, ...]
    excerpts: tuple[Chunk, ...]


class Claim(Contract):
    fact_id: Identifier
    text: str = Field(min_length=1, max_length=16000)
    refs: tuple[str, ...]


class LLMOutput(Contract):
    claims: tuple[Claim, ...] = Field(min_length=1, max_length=100)


class ExplanationArtifact(Stamped):
    explanation_id: Identifier
    tenant_id: Identifier
    taxpayer_id: Identifier
    evaluation_id: Identifier
    record_revision: int = Field(ge=1)
    evaluation_sha256: Sha256
    context_sha256: Sha256
    config_sha256: Sha256
    corpus_sha256: Sha256
    implementation_sha256: Sha256
    prompt_version: Identifier
    provider: str
    model: str
    model_revision: str
    mode: Literal['TEMPLATE', 'LLM_VALIDATED']
    fallback_reason: str | None
    claims: tuple[Claim, ...]
    excerpts: tuple[Chunk, ...]
    elapsed_seconds: float = Field(ge=0)
    technical_only: Literal[True] = True

    @model_validator(mode='after')
    def consistent(self):
        import math
        if (self.mode == 'TEMPLATE') != bool(self.fallback_reason):
            raise ValueError('Fallback reason and mode disagree')
        if not self.claims or len({c.fact_id for c in self.claims}) != len(self.claims):
            raise ValueError('Missing or duplicate claims')
        if not math.isfinite(self.elapsed_seconds):
            raise ValueError('Invalid elapsed time')
        return self
