from __future__ import annotations

from typing import Any


def worst_field_cases(summary: dict[str, Any], limit: int = 20) -> list[dict[str, Any]]:
    rows = summary.get("fields", {}).get("per_image", [])
    return sorted(
        rows,
        key=lambda row: (
            row.get("total_cost_correct", False),
            row.get("timestamp_correct", False),
            row.get("seller_similarity", 0.0),
            row.get("address_similarity", 0.0),
        ),
    )[:limit]

