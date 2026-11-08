"""Build and cache the small in-memory dense metric index."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..errors import EmbeddingProviderError
from ..retrieval.embedding import EmbeddingProvider
from .document_builder import MetricDocumentBuilder


@dataclass(frozen=True)
class DenseIndex:
    metric_ids: tuple[str, ...]
    matrix: np.ndarray
    catalog_version: str
    document_version: str
    embedding_model: str


class MetricIndexBuilder:
    def __init__(
        self,
        documents: MetricDocumentBuilder,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.documents = documents
        self.embedding_provider = embedding_provider

    def build(self) -> DenseIndex:
        docs = self.documents.build_all()
        try:
            matrix = np.asarray(
                self.embedding_provider.embed_documents([doc.text for doc in docs]),
                dtype=np.float64,
            )
        except Exception as exc:
            raise EmbeddingProviderError(f"Document embedding failed: {exc}") from exc
        if matrix.ndim != 2 or matrix.shape[0] != len(docs):
            raise EmbeddingProviderError("Embedding provider returned an invalid matrix")
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = np.divide(matrix, norms, out=np.zeros_like(matrix), where=norms != 0)
        return DenseIndex(
            metric_ids=tuple(doc.metric_id for doc in docs),
            matrix=matrix,
            catalog_version=self.documents.catalog.version,
            document_version=self.documents.version,
            embedding_model=self.embedding_provider.model_id,
        )

    def save(self, index: DenseIndex, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        metadata = json.dumps(
            {
                "metric_ids": index.metric_ids,
                "catalog_version": index.catalog_version,
                "document_version": index.document_version,
                "embedding_model": index.embedding_model,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        np.savez_compressed(target, matrix=index.matrix, metadata=np.asarray(metadata))

    def load(self, path: str | Path) -> DenseIndex | None:
        source = Path(path)
        if not source.exists():
            return None
        try:
            with np.load(source, allow_pickle=False) as payload:
                metadata = json.loads(str(payload["metadata"]))
                index = DenseIndex(
                    metric_ids=tuple(metadata["metric_ids"]),
                    matrix=np.asarray(payload["matrix"], dtype=np.float64),
                    catalog_version=metadata["catalog_version"],
                    document_version=metadata["document_version"],
                    embedding_model=metadata["embedding_model"],
                )
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return None
        if (
            index.catalog_version != self.documents.catalog.version
            or index.document_version != self.documents.version
            or index.embedding_model != self.embedding_provider.model_id
            or index.matrix.shape[0] != len(index.metric_ids)
        ):
            return None
        return index

    def load_or_build(self, path: str | Path | None = None) -> DenseIndex:
        if path:
            cached = self.load(path)
            if cached is not None:
                return cached
        index = self.build()
        if path:
            self.save(index, path)
        return index
