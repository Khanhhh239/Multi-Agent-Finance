from __future__ import annotations

from typing import Any

from ..catalog.adapter import MetricCatalogAdapter
from ..errors import OutputValidationError
from ..schemas import MetricCandidate, MetricSelectionResult


class SelectionValidator:
    def __init__(self, catalog: MetricCatalogAdapter) -> None:
        self.catalog = catalog

    def validate(
        self,
        result: MetricSelectionResult,
        candidates: list[MetricCandidate],
        context: dict[str, Any] | None = None,
    ) -> MetricSelectionResult:
        candidate_ids = [candidate.metric_id for candidate in candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise OutputValidationError("Candidate set contains duplicate metric IDs")
        unknown = [metric_id for metric_id in result.metric_ids if not self.catalog.contains(metric_id)]
        if unknown:
            raise OutputValidationError(f"Unknown selected metric IDs: {unknown}")
        outside = [metric_id for metric_id in result.metric_ids if metric_id not in candidate_ids]
        if outside:
            raise OutputValidationError(f"Selected IDs are outside the candidate set: {outside}")
        requested_view = (context or {}).get("view")
        if requested_view in {"mgmt", "tax"}:
            invalid_view = [
                metric_id
                for metric_id in result.metric_ids
                if requested_view not in self.catalog.get(metric_id).views
            ]
            if invalid_view:
                raise OutputValidationError(
                    f"Selected metrics do not support explicit {requested_view!r} view: {invalid_view}"
                )
        return result
