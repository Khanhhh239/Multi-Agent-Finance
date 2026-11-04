from __future__ import annotations

import csv
from pathlib import Path

from agent4.text2sql.catalog import CatalogSnapshot


def main() -> None:
    catalog = CatalogSnapshot()
    destinations = [
        Path("integration/CAPABILITY_MATRIX.csv"),
        Path("release/CAPABILITY_MATRIX.csv"),
    ]
    fields = [
        "metric_id", "label", "kind", "category", "unit", "source_status",
        "synthetic_status", "real_data_status", "group_bys", "verified_group_bys",
        "views", "handler",
        "blocker_reason",
    ]
    rows = []
    for item in catalog.public_metrics():
        metric = catalog.get(item["id"])
        capability = catalog.capability(metric.id)
        rows.append({
            "metric_id": metric.id,
            "label": metric.label,
            "kind": metric.kind,
            "category": metric.category,
            "unit": metric.unit,
            "source_status": capability.source_status,
            "synthetic_status": capability.synthetic_status,
            "real_data_status": capability.real_data_status,
            "group_bys": "|".join(metric.group_bys),
            "verified_group_bys": "|".join(capability.verified_group_bys),
            "views": "|".join(metric.views),
            "handler": capability.handler,
            "blocker_reason": capability.reason or "",
        })
    for destination in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    main()
