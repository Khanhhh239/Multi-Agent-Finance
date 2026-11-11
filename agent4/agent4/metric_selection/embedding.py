"""Versioned embeddings and business-only documents for offline indexing."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from uuid import uuid4

import httpx
import numpy as np

from agent4.core.cache import LRUTTLCache, build_scoped_cache_key
from agent4.core.catalog import MetricCatalog
from agent4.core.context import SUPPORTED_LOCALES
from agent4.core.errors import ContractError, enforce_exact_keys
from agent4.engine.metrics import GROUP_LABELS

from .config import EmbeddingConfig, backend_cache_identity, openai_endpoint

DOCUMENT_VERSION = "metric-doc-v2"
_EMBEDDING_STAGE = "embedding_provider"
_REQUEST_KEYS = {"texts", "model_id", "model_version", "normalize"}
_QUERY_CACHE = LRUTTLCache(
    max_entries=1024, ttl_seconds=3600, max_bytes_budget=32 * 1024**2, max_rows_per_entry=1
)
_DIMENSION_NAMES = {
    "branch_code": "branch",
    "department_code": "department",
    "partner_code": "partner",
}
_UNSAFE_DOCUMENT = re.compile(
    r"\b(?:select|from|insert|update|delete|drop|with|alter|create|attach|truncate|pragma)\s+"
    r"|\bcase\s+when\b"
    r"|\b(?:sum|avg|count|min|max|coalesce|round)\s*\("
    r"|\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b",
    re.IGNORECASE,
)


class EmbeddingProvider:
    """Embed bounded batches using a fixed model identity and normalization mode."""

    def __init__(
        self,
        config: EmbeddingConfig | None = None,
        *,
        available: bool = True,
        max_batch_size: int = 32,
        max_text_length: int = 1000,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if max_batch_size < 1 or max_text_length < 1:
            raise ValueError("Embedding batch and text limits must be positive.")
        self.config = config or EmbeddingConfig()
        self.available = available
        self.max_batch_size = max_batch_size
        self.max_text_length = max_text_length
        self._transport = transport
        self._transport_partition = uuid4().hex if transport is not None else None

    @property
    def model_id(self) -> str:
        return self.config.model

    @property
    def model_version(self) -> str:
        return self.config.model_version

    @property
    def dimension(self) -> int:
        return self.config.dimensions

    @property
    def normalize(self) -> bool:
        return self.config.normalize

    def cache_identity(self) -> dict[str, Any]:
        return {
            "config": backend_cache_identity(self.config),
            "transport_partition": self._transport_partition,
            "max_text_length": self.max_text_length,
        }

    def embed(
        self, request: dict[str, Any], *, cache_scope: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        enforce_exact_keys(request, required_keys=_REQUEST_KEYS, stage=_EMBEDDING_STAGE)
        if request["model_id"] != self.model_id or request["model_version"] != self.model_version:
            raise ContractError("invalid_request", _EMBEDDING_STAGE, "Embedding model mismatch.")
        if request["normalize"] is not self.normalize:
            raise ContractError(
                "invalid_request", _EMBEDDING_STAGE, "Embedding normalization mismatch."
            )

        texts = request["texts"]
        if not isinstance(texts, list) or not 1 <= len(texts) <= self.max_batch_size:
            raise ContractError(
                "invalid_request", _EMBEDDING_STAGE, "Invalid embedding batch size."
            )
        if any(not isinstance(text, str) or len(text) > self.max_text_length for text in texts):
            raise ContractError("invalid_request", _EMBEDDING_STAGE, "Invalid embedding text.")
        if not self.available:
            raise _embedding_unavailable()

        key = None
        if cache_scope is not None and len(texts) == 1:
            key = build_scoped_cache_key(
                "query-embedding",
                **cache_scope,
                normalized_question=texts[0],
                backend=self.cache_identity(),
            )
            if (cached := _QUERY_CACHE.get(key)) is not None:
                return cached

        if self.config.provider in ("ollama", "openai"):
            vectors = self._embed_remote(texts)
        else:
            # SHAKE supplies a deterministic byte for every requested dimension.
            digests = [
                hashlib.shake_256(text.lower().encode()).digest(self.dimension) for text in texts
            ]
            vectors = np.array([np.frombuffer(digest, dtype=np.uint8) for digest in digests])
            vectors = vectors / 127.5 - 1.0

        if self.normalize:
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            if np.any(norms == 0):
                raise _embedding_unavailable()
            vectors = vectors / norms

        result = {
            "vectors": [
                {"values": values, "dimension": self.dimension, "normalized": self.normalize}
                for values in vectors.tolist()
            ],
            "model_id": self.model_id,
            "model_version": self.model_version,
            "dimension": self.dimension,
        }
        if key is not None:
            _QUERY_CACHE.set(key, result, row_count=1)
        return result

    def _embed_remote(self, texts: list[str]) -> np.ndarray:
        payload = {"model": self.model_id, "input": texts, "dimensions": self.dimension}
        openai = self.config.provider == "openai"
        if openai:
            url = openai_endpoint(self.config.base_url, "embeddings")
        else:
            url = f"{self.config.base_url.rstrip('/')}/api/embed"
            payload["truncate"] = False
        headers = (
            {"Authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else None
        )
        try:
            with httpx.Client(
                timeout=self.config.timeout_s,
                trust_env=False,
                transport=self._transport,
                headers=headers,
            ) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
            body = response.json()
            rows = (
                _openai_embedding_rows(body["data"], len(texts)) if openai else body["embeddings"]
            )
            if (
                not isinstance(rows, list)
                or len(rows) != len(texts)
                or any(
                    not isinstance(row, list)
                    or len(row) != self.dimension
                    or any(type(value) not in (int, float) for value in row)
                    for row in rows
                )
            ):
                raise ValueError("Invalid embedding shape or values")
            # Convert to the index's storage precision before checking for overflow.
            with np.errstate(over="ignore"):
                vectors = np.asarray(rows, dtype=np.float32).astype(np.float64)
            if not np.isfinite(vectors).all():
                raise ValueError("Non-finite embeddings")
        except (
            httpx.HTTPError,
            httpx.InvalidURL,
            KeyError,
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise _embedding_unavailable() from exc
        return vectors


def _openai_embedding_rows(data: Any, count: int) -> list:
    if not isinstance(data, list) or len(data) != count:
        raise ValueError("Invalid embedding response length")
    if any(not isinstance(item, dict) or type(item.get("index")) is not int for item in data):
        raise ValueError("Invalid embedding response index")
    ordered = sorted(data, key=lambda item: item["index"])
    if [item["index"] for item in ordered] != list(range(count)):
        raise ValueError("Missing or duplicate embedding response index")
    return [item["embedding"] for item in ordered]


def _embedding_unavailable() -> ContractError:
    return ContractError(
        "retrieval_unavailable",
        _EMBEDDING_STAGE,
        "Embedding provider is temporarily unavailable.",
        retryable=True,
        final_status="temporarily_unavailable",
    )


def build_metric_documents(catalog: MetricCatalog, locale: str = "vi-VN") -> list[dict[str, Any]]:
    """Build deterministic documents from governed catalog metadata."""
    stage = "document_builder"
    if not isinstance(locale, str) or locale not in SUPPORTED_LOCALES:
        raise ContractError(
            "unsupported_locale",
            stage,
            "Requested locale is not supported.",
            final_status="unsupported",
        )
    catalog_hash = catalog.get_catalog_hash()
    vietnamese = locale == "vi-VN"
    documents = []
    for metric in catalog.list_approved_metrics():
        label = metric["label"]
        label_en = metric.get("label_en") or label
        labels = dict.fromkeys((label, label_en) if vietnamese else (label_en, label))
        description = re.sub(
            r"\bas_of\b", "chốt sổ" if vietnamese else "as of", metric["description"]
        )
        aliases = ", ".join(metric.get("aliases", [])[:8])
        dimensions = []
        for key in metric["supported_dimensions"]:
            name = _DIMENSION_NAMES.get(key, key)
            if name not in GROUP_LABELS and _UNSAFE_DOCUMENT.search(name):
                raise ContractError(
                    "invalid_request", stage, "Metric document contains a prohibited dimension."
                )
            display_name = name.replace("_", " ")
            dimensions.append(GROUP_LABELS.get(name, display_name) if vietnamese else display_name)
        parts = [*labels, description, ("Đơn vị " if vietnamese else "Unit ") + metric["unit"]]
        if category := metric.get("category"):
            parts.append(("Nhóm " if vietnamese else "Category ") + category)
        if aliases:
            parts.append(("Còn gọi là " if vietnamese else "Aliases ") + aliases)
        if dimensions:
            parts.append(("Hỗ trợ theo " if vietnamese else "Supports ") + ", ".join(dimensions))
        document_text = ". ".join(part.strip().rstrip(".") for part in parts) + "."
        if _UNSAFE_DOCUMENT.search(document_text):
            raise ContractError(
                "invalid_request", stage, "Metric document contains prohibited content."
            )
        documents.append(
            {
                "metric_id": metric["metric_id"],
                "document_text": document_text,
                "locale": locale,
                "catalog_hash": catalog_hash,
                "document_version": DOCUMENT_VERSION,
            }
        )
    return documents
