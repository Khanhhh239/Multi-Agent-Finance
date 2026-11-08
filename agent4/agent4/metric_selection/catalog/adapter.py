"""Read-only adapter around the financial metric source of truth."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import asdict

from agent4.engine.metrics import REGISTRY, M, MetricDef

from ..errors import CatalogError


class MetricCatalogAdapter:
    def __init__(
        self,
        registry: Mapping[str, MetricDef] | None = None,
        definitions: list[MetricDef] | None = None,
    ) -> None:
        self._registry = dict(registry or REGISTRY)
        self._definitions = list(definitions or M)
        self._validate()

    def _validate(self) -> None:
        ids = [metric.id for metric in self._definitions]
        if len(ids) != len(set(ids)):
            duplicates = sorted({item for item in ids if ids.count(item) > 1})
            raise CatalogError(f"Duplicate metric IDs: {duplicates}")
        if set(ids) != set(self._registry):
            raise CatalogError("Metric definitions and REGISTRY contain different IDs")
        for metric in self._definitions:
            if not metric.id or not metric.label or not metric.description:
                raise CatalogError(f"Metric {metric.id!r} has incomplete retrieval metadata")
            if metric.default_view not in metric.views:
                raise CatalogError(f"Metric {metric.id} has invalid default_view")
            if metric.kind not in {"flow", "snapshot", "ratio", "custom"}:
                raise CatalogError(f"Metric {metric.id} has unsupported kind {metric.kind}")

    def __len__(self) -> int:
        return len(self._registry)

    def __iter__(self) -> Iterator[MetricDef]:
        for metric_id in sorted(self._registry):
            yield self._registry[metric_id]

    def get(self, metric_id: str) -> MetricDef:
        try:
            return self._registry[metric_id]
        except KeyError as exc:
            raise CatalogError(f"Unknown metric ID: {metric_id}") from exc

    def contains(self, metric_id: str) -> bool:
        return metric_id in self._registry

    @property
    def metric_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._registry))

    @property
    def version(self) -> str:
        records = [asdict(metric) for metric in self]
        payload = json.dumps(records, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
