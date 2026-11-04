from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ..catalog.adapter import MetricCatalogAdapter
from ..errors import ConfigurationError
from ..schemas import MetricSelectionResult


class FewshotExample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    question: str
    answer: MetricSelectionResult
    decision_tags: list[str] = Field(default_factory=list)
    confusable_metrics: list[str] = Field(default_factory=list)


class ExampleBank:
    def __init__(self, examples: list[FewshotExample], catalog: MetricCatalogAdapter) -> None:
        self.examples = examples
        self.catalog = catalog
        self._validate()

    @classmethod
    def from_jsonl(cls, path: str | Path, catalog: MetricCatalogAdapter) -> ExampleBank:
        source = Path(path)
        try:
            examples = [
                FewshotExample.model_validate_json(line)
                for line in source.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, ValueError) as exc:
            raise ConfigurationError(f"Invalid example bank {source}: {exc}") from exc
        return cls(examples, catalog)

    def _validate(self) -> None:
        ids = [example.id for example in self.examples]
        if len(ids) != len(set(ids)):
            raise ConfigurationError("Example bank contains duplicate IDs")
        for example in self.examples:
            referenced = [*example.answer.metric_ids, *example.confusable_metrics]
            unknown = [metric_id for metric_id in referenced if not self.catalog.contains(metric_id)]
            if unknown:
                raise ConfigurationError(
                    f"Example {example.id} references unknown metrics: {unknown}"
                )

    def __len__(self) -> int:
        return len(self.examples)

    @property
    def version(self) -> str:
        payload = json.dumps(
            [example.model_dump(mode="json") for example in self.examples],
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
