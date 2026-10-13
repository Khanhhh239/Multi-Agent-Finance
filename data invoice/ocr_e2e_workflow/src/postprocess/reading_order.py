from __future__ import annotations

from typing import Any


def polygon_bounds(polygon: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def sort_detections(detections: list[dict[str, Any]], line_tolerance: float = 0.6) -> list[dict[str, Any]]:
    enriched: list[tuple[dict[str, Any], float, float, float]] = []
    for detection in detections:
        polygon = detection.get("polygon") or []
        if not polygon:
            enriched.append((detection, float("inf"), float("inf"), 1.0))
            continue
        x1, y1, _, y2 = polygon_bounds(polygon)
        enriched.append((detection, y1, x1, max(1.0, y2 - y1)))
    enriched.sort(key=lambda item: (item[1], item[2]))
    rows: list[list[tuple[dict[str, Any], float, float, float]]] = []
    for item in enriched:
        if not rows:
            rows.append([item])
            continue
        row_y = sum(member[1] for member in rows[-1]) / len(rows[-1])
        row_height = sum(member[3] for member in rows[-1]) / len(rows[-1])
        if abs(item[1] - row_y) <= line_tolerance * max(item[3], row_height):
            rows[-1].append(item)
        else:
            rows.append([item])
    result: list[dict[str, Any]] = []
    for row in rows:
        row.sort(key=lambda item: item[2])
        result.extend(item[0] for item in row)
    return result

