"""Stable semantic documents generated from REGISTRY metadata."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .adapter import MetricCatalogAdapter


class MetricDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MetricDocumentBuilder:
    def __init__(self, catalog: MetricCatalogAdapter) -> None:
        self.catalog = catalog

    def build(self, metric_id: str) -> MetricDocument:
        metric = self.catalog.get(metric_id)
        synonyms = "; ".join(metric.synonyms)
        text = (
            f"Metric Name:\n{metric.label}\n\n"
            f"Description:\n{metric.description}\n\n"
            f"Synonyms:\n{synonyms}\n\n"
            f"Category:\n{metric.category}"
        )
        metadata = {
            "kind": metric.kind,
            "unit": metric.unit,
            "category": metric.category,
            "group_bys": list(metric.group_bys),
            "views": list(metric.views),
            "default_view": metric.default_view,
            "params": metric.params,
            "period_type": metric.period_type,
        }
        return MetricDocument(metric_id=metric.id, text=text, metadata=metadata)

    def build_all(self) -> list[MetricDocument]:
        return [self.build(metric.id) for metric in self.catalog]

    @property
    def version(self) -> str:
        payload = json.dumps(
            [doc.model_dump() for doc in self.build_all()],
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
