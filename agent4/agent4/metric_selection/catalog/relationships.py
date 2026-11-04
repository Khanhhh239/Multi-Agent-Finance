"""Curated, auditable relationships between registered metrics."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from ..errors import ConfigurationError
from .adapter import MetricCatalogAdapter

RelationshipType = Literal[
    "specialization", "related_concept", "alternative_definition", "confusable_with"
]


class MetricRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    target: str
    type: RelationshipType
    metadata: dict[str, Any] = Field(default_factory=dict)


class RelationshipRegistry:
    def __init__(
        self,
        relationships: list[MetricRelationship],
        catalog: MetricCatalogAdapter,
    ) -> None:
        self.relationships = relationships
        self.catalog = catalog
        self._validate()
        self._adjacency: dict[str, list[MetricRelationship]] = {}
        for relationship in relationships:
            self._adjacency.setdefault(relationship.source, []).append(relationship)
            reverse = MetricRelationship(
                source=relationship.target,
                target=relationship.source,
                type=relationship.type,
                metadata={**relationship.metadata, "reverse": True},
            )
            self._adjacency.setdefault(reverse.source, []).append(reverse)
        for edges in self._adjacency.values():
            edges.sort(key=lambda edge: (edge.type, edge.target))

    @classmethod
    def from_yaml(
        cls,
        path: str | Path,
        catalog: MetricCatalogAdapter,
    ) -> RelationshipRegistry:
        source = Path(path)
        try:
            raw = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
            relationships = [
                MetricRelationship.model_validate(item)
                for item in raw.get("relationships", [])
            ]
        except (OSError, yaml.YAMLError, ValueError) as exc:
            raise ConfigurationError(f"Invalid relationship config {source}: {exc}") from exc
        return cls(relationships, catalog)

    def _validate(self) -> None:
        seen: set[tuple[str, str, str]] = set()
        for relationship in self.relationships:
            if relationship.source == relationship.target:
                raise ConfigurationError("A metric relationship cannot reference itself")
            for metric_id in (relationship.source, relationship.target):
                if not self.catalog.contains(metric_id):
                    raise ConfigurationError(
                        f"Relationship references unknown metric ID: {metric_id}"
                    )
            key = (relationship.source, relationship.target, relationship.type)
            reverse = (relationship.target, relationship.source, relationship.type)
            if key in seen or reverse in seen:
                raise ConfigurationError(f"Duplicate relationship: {key}")
            seen.add(key)

    def related(self, metric_id: str) -> list[MetricRelationship]:
        return list(self._adjacency.get(metric_id, []))

    def relationship_types(self, metric_ids: set[str]) -> set[str]:
        return {
            edge.type
            for source in metric_ids
            for edge in self.related(source)
            if edge.target in metric_ids
        }

    @property
    def version(self) -> str:
        payload = json.dumps(
            [relationship.model_dump(mode="json") for relationship in self.relationships],
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
