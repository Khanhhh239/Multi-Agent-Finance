"""Offline lifecycle for the persisted metric vector index."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from zipfile import BadZipFile

import numpy as np

from agent4.core.catalog import MetricCatalog
from agent4.core.errors import ContractError

from .embedding import DOCUMENT_VERSION, EmbeddingProvider, build_metric_documents

INDEX_VERSION = "metric-dense-index-v3"
_ARCHIVE_FIELDS = {"vectors", "metric_ids", "document_texts", "metadata"}
_METADATA_TYPES = {
    "catalog_hash": str,
    "model_id": str,
    "model_version": str,
    "dimension": int,
    "normalized": bool,
    "document_version": str,
    "index_version": str,
}


@dataclass(frozen=True)
class MetricVectorIndex:
    """Aligned vectors, metric IDs, texts, and their build metadata."""

    vectors: np.ndarray
    metric_ids: tuple[str, ...]
    document_texts: tuple[str, ...]
    metadata: dict[str, Any]

    def is_stale(self, catalog_hash: str, embedding_provider: EmbeddingProvider) -> bool:
        return is_index_stale(self.metadata, catalog_hash, embedding_provider)


def _index_metadata(catalog_hash: str, provider: EmbeddingProvider) -> dict[str, Any]:
    return {
        "catalog_hash": catalog_hash,
        "model_id": provider.model_id,
        "model_version": provider.model_version,
        "dimension": provider.dimension,
        "normalized": provider.normalize,
        "document_version": DOCUMENT_VERSION,
        "index_version": INDEX_VERSION,
    }


def is_index_stale(
    index_meta: Mapping[str, Any], catalog_hash: str, embedding_provider: EmbeddingProvider
) -> bool:
    """Compare the stored build metadata with the active catalog and provider."""
    expected = _index_metadata(catalog_hash, embedding_provider)
    return any(
        type(index_meta.get(key)) is not type(value) or index_meta[key] != value
        for key, value in expected.items()
    )


def build_index(
    catalog: MetricCatalog,
    embedding_provider: EmbeddingProvider,
    path: str | Path | None = None,
    *,
    locale: str = "vi-VN",
) -> MetricVectorIndex:
    """Embed approved documents in batches and write the index when caching is enabled."""
    docs = build_metric_documents(catalog, locale=locale)
    texts = tuple(doc["document_text"] for doc in docs)
    metadata = _index_metadata(catalog.get_catalog_hash(), embedding_provider)
    vectors = np.empty((len(docs), metadata["dimension"]), dtype=np.float32)
    batch_size = embedding_provider.max_batch_size
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = embedding_provider.embed(
            {
                "texts": list(batch),
                "model_id": metadata["model_id"],
                "model_version": metadata["model_version"],
                "normalize": metadata["normalized"],
            }
        )
        vectors[start : start + len(batch)] = [vector["values"] for vector in response["vectors"]]

    index = MetricVectorIndex(vectors, tuple(doc["metric_id"] for doc in docs), texts, metadata)
    if path is not None or embedding_provider.config.cache_enabled:
        _save_index(Path(path) if path is not None else embedding_provider.config.cache_path, index)
    return index


def _save_index(path: Path, index: MetricVectorIndex) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with NamedTemporaryFile(dir=path.parent, suffix=".npz", delete=False) as file:
            temporary_path = Path(file.name)
            np.savez_compressed(
                file,
                vectors=index.vectors,
                metric_ids=np.asarray(index.metric_ids, dtype=str),
                document_texts=np.asarray(index.document_texts, dtype=str),
                metadata=json.dumps(index.metadata, sort_keys=True),
            )
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def rebuild_index(
    catalog: MetricCatalog,
    embedding_provider: EmbeddingProvider,
    path: str | Path | None = None,
    *,
    locale: str = "vi-VN",
) -> MetricVectorIndex:
    """Replace the previous index only after a successful build."""
    return build_index(catalog, embedding_provider, path, locale=locale)


def load_index(
    path: str | Path,
    *,
    catalog_hash: str | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> MetricVectorIndex:
    """Load a validated archive and optionally reject stale metadata."""
    if (catalog_hash is None) != (embedding_provider is None):
        raise ValueError("Freshness checks require both the catalog hash and embedding provider.")
    try:
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != _ARCHIVE_FIELDS:
                raise ValueError("Invalid index archive fields")
            metadata = json.loads(archive["metadata"].item())
            vectors, metric_ids, texts = (
                archive["vectors"],
                archive["metric_ids"],
                archive["document_texts"],
            )
        _validate_index(metadata, vectors, metric_ids, texts)
    except (AttributeError, BadZipFile, EOFError, OSError, TypeError, ValueError) as exc:
        raise _index_unavailable("Metric vector index is missing or invalid.") from exc
    if (
        catalog_hash is not None
        and embedding_provider is not None
        and is_index_stale(metadata, catalog_hash, embedding_provider)
    ):
        raise _index_unavailable("Metric vector index is stale.")
    return MetricVectorIndex(vectors, tuple(metric_ids.tolist()), tuple(texts.tolist()), metadata)


def _validate_index(
    metadata: Any, vectors: np.ndarray, metric_ids: np.ndarray, texts: np.ndarray
) -> None:
    if (
        not isinstance(metadata, dict)
        or metadata.keys() != _METADATA_TYPES.keys()
        or any(type(metadata[key]) is not kind for key, kind in _METADATA_TYPES.items())
        or metadata["dimension"] < 1
    ):
        raise ValueError("Invalid index metadata")
    if (
        metric_ids.ndim != 1
        or texts.shape != metric_ids.shape
        or metric_ids.dtype.kind != "U"
        or texts.dtype.kind != "U"
        or np.any(metric_ids[1:] <= metric_ids[:-1])
        or vectors.shape != (len(metric_ids), metadata["dimension"])
        or vectors.dtype != np.float32
        or not np.isfinite(vectors).all()
    ):
        raise ValueError("Invalid index arrays")
    if metadata["normalized"] and not np.allclose(
        np.linalg.norm(vectors.astype(np.float64), axis=1), 1.0, atol=1e-6
    ):
        raise ValueError("Invalid normalized index vectors")


def _index_unavailable(message: str) -> ContractError:
    return ContractError(
        "retrieval_unavailable",
        "vector_index",
        message,
        retryable=True,
        final_status="temporarily_unavailable",
    )
