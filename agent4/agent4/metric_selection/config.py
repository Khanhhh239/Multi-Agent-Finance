"""Versioned configuration loading for the metric-selection pipeline."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import ConfigurationError

PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_DIR / "config" / "selection.yaml"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class EmbeddingConfig(StrictModel):
    provider: Literal["hashing", "ollama", "openai", "mock"] = "hashing"
    model: str = Field(default="hashing-v1", min_length=1)
    model_version: str = Field(default="1", min_length=1)
    dimensions: int = Field(default=768, ge=64)
    base_url: str = Field(default="http://localhost:11434", min_length=1)
    api_key: str | None = Field(default=None, exclude=True, repr=False)
    normalize: bool = True
    timeout_s: float = Field(default=30.0, gt=0, allow_inf_nan=False)
    cache_enabled: bool = True
    cache_path: Path = PROJECT_DIR / ".cache" / "metric_selection_index.npz"

    @model_validator(mode="before")
    @classmethod
    def set_default_model(cls, data: object) -> object:
        if isinstance(data, dict) and data.get("provider") == "ollama" and "model" not in data:
            return {**data, "model": "qwen3-embedding:0.6b"}
        return data


class RetrievalConfig(StrictModel):
    mode: Literal["full_catalog", "dense_only", "hybrid", "lexical_only"] = "full_catalog"
    dense_enabled: bool = True
    lexical_enabled: bool = True
    fusion_method: Literal["rrf"] = "rrf"
    dense_top_k: int = Field(default=15, ge=1)
    lexical_top_k: int = Field(default=15, ge=1)
    fusion_top_k: int = Field(default=20, ge=1)
    rrf_k: int = Field(default=60, ge=1)
    mention_retrieval_enabled: bool = False

    @model_validator(mode="after")
    def at_least_one_retriever(self) -> RetrievalConfig:
        if self.mode != "full_catalog" and not self.dense_enabled and not self.lexical_enabled:
            raise ValueError("at least one retrieval method must be enabled")
        return self


class ExpansionConfig(StrictModel):
    enabled: bool = True
    max_hops: int = Field(default=1, ge=0, le=1)
    max_candidates: int = Field(default=30, ge=1)
    relationship_path: Path = PROJECT_DIR / "config" / "metric_relationships.yaml"


class RerankingConfig(StrictModel):
    metadata_enabled: bool = True
    cross_encoder_enabled: bool = False
    final_top_k: int = Field(default=12, ge=1)
    metadata_weight: float = Field(default=1.0, ge=0)
    cross_encoder_weight: float = Field(default=0.4, ge=0)


class FewshotConfig(StrictModel):
    enabled: bool = False
    strategy: Literal["zero", "static", "similarity", "coverage", "hybrid"] = "zero"
    min_examples: int = Field(default=0, ge=0)
    max_examples: int = Field(default=4, ge=0)
    token_budget: int = Field(default=2500, ge=0)
    initial_pool_size: int = Field(default=15, ge=1)
    example_bank_path: Path = PROJECT_DIR / "data" / "example_bank.jsonl"
    alpha: float = Field(default=1.0, ge=0, allow_inf_nan=False)
    beta: float = Field(default=0.5, ge=0, allow_inf_nan=False)
    gamma: float = Field(default=0.5, ge=0, allow_inf_nan=False)
    delta: float = Field(default=0.25, ge=0, allow_inf_nan=False)

    @field_validator("strategy", mode="before")
    @classmethod
    def normalize_legacy_strategy(cls, value: object) -> object:
        return "hybrid" if value == "adaptive" else value

    @model_validator(mode="after")
    def validate_range(self) -> FewshotConfig:
        if self.min_examples > self.max_examples:
            raise ValueError("min_examples must be <= max_examples")
        return self


class LLMSelectionConfig(StrictModel):
    provider: Literal["ollama", "openai", "mock"] = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = "qwen3:4b"
    api_key: str | None = Field(default=None, exclude=True, repr=False)
    max_tokens: int = Field(default=1024, ge=64)
    temperature: float = Field(default=0.0, ge=0)
    timeout_s: float = Field(default=360.0, gt=0)
    max_retries: int = Field(default=0, ge=0, le=1)
    context_window: int = Field(default=8192, ge=1)
    structured_output: bool = False


class EvaluationConfig(StrictModel):
    save_traces: bool = True
    report_per_category: bool = True
    random_seed: int = 20261101


class RecoveryConfig(StrictModel):
    enable_empty_candidate_fallback: bool = False
    degraded_lexical_fallback: bool = False
    enable_candidate_expansion: bool = False


class MetricSelectionConfig(StrictModel):
    version: str = "1"
    prompt_version: str = "metric-selection-v1"
    cache_enabled: bool = True
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    expansion: ExpansionConfig = Field(default_factory=ExpansionConfig)
    reranking: RerankingConfig = Field(default_factory=RerankingConfig)
    fewshot: FewshotConfig = Field(default_factory=FewshotConfig)
    llm: LLMSelectionConfig = Field(default_factory=LLMSelectionConfig)
    recovery: RecoveryConfig = Field(default_factory=RecoveryConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)


_ENV_OVERRIDES = {
    "llm": {
        "provider": "AGENT4_LLM_PROVIDER",
        "base_url": "AGENT4_LLM_BASE_URL",
        "model": "AGENT4_LLM_MODEL",
        "api_key": "AGENT4_LLM_API_KEY",
    },
    "embedding": {
        "provider": "AGENT4_EMBED_PROVIDER",
        "base_url": "AGENT4_EMBED_BASE_URL",
        "model": "AGENT4_EMBED_MODEL",
        "dimensions": "AGENT4_EMBED_DIMENSIONS",
        "api_key": "AGENT4_EMBED_API_KEY",
    },
    "retrieval": {"mode": "AGENT4_RETRIEVAL_MODE"},
}


def load_config(path: str | Path | None = None) -> MetricSelectionConfig:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if isinstance(raw, dict):
            for section, fields in _ENV_OVERRIDES.items():
                overrides = {
                    field: os.environ[key] for field, key in fields.items() if key in os.environ
                }
                current = raw.get(section, {})
                if overrides and isinstance(current, dict):
                    raw[section] = {**current, **overrides}
        config = MetricSelectionConfig.model_validate(raw)
        embedding = config.embedding.model_copy(
            update={
                "cache_path": _absolute_project_path(config.embedding.cache_path),
            }
        )
        expansion = config.expansion.model_copy(
            update={
                "relationship_path": _absolute_project_path(config.expansion.relationship_path),
            }
        )
        fewshot = config.fewshot.model_copy(
            update={
                "example_bank_path": _absolute_project_path(config.fewshot.example_bank_path),
            }
        )
        return config.model_copy(
            update={"embedding": embedding, "expansion": expansion, "fewshot": fewshot}
        )
    except yaml.YAMLError:
        raise ConfigurationError(f"Invalid metric-selection YAML in {config_path}") from None
    except (OSError, ValueError) as exc:
        raise ConfigurationError(
            f"Cannot load metric-selection config {config_path}: {exc}"
        ) from exc


def _absolute_project_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_DIR / path


def config_fingerprint(config: MetricSelectionConfig) -> str:
    payload = json.dumps(config.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def openai_endpoint(base_url: str, resource: str) -> str:
    """Accept the server root or its OpenAI-compatible /v1 prefix."""
    base_url = base_url.rstrip("/")
    prefix = base_url if base_url.endswith("/v1") else f"{base_url}/v1"
    return f"{prefix}/{resource}"


def backend_cache_identity(config: EmbeddingConfig | LLMSelectionConfig) -> dict:
    identity = config.model_dump(mode="json")
    if config.api_key:
        identity["credential_digest"] = hashlib.sha256(config.api_key.encode()).hexdigest()
    return identity
