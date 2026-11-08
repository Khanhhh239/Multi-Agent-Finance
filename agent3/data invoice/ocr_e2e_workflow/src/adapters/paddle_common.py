from __future__ import annotations

from typing import Any, Iterable


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    for attribute in ("json", "to_dict", "dict"):
        candidate = getattr(value, attribute, None)
        if callable(candidate):
            candidate = candidate()
        if isinstance(candidate, dict):
            return candidate
    return {}


def _first_present(payload: dict[str, Any], *names: str) -> Any:
    """Select a Paddle result field without truth-testing NumPy arrays."""
    for name in names:
        value = payload.get(name)
        if value is not None:
            return value
    return []


def paddle_result_orientation(results: Iterable[Any]) -> int:
    for result in results:
        value = _as_dict(result)
        payload = value.get("res", value)
        preprocessor = payload.get("doc_preprocessor_res") or {}
        if "angle" in preprocessor:
            return int(preprocessor["angle"]) % 360
    return 0


def paddle_classification_label(results: Iterable[Any]) -> tuple[str | None, float | None]:
    """Return the top Paddle image-classification label and score."""
    for result in results:
        value = _as_dict(result)
        payload = value.get("res", value)
        labels = _first_present(payload, "label_names", "class_ids")
        scores = _first_present(payload, "scores")
        if len(labels):
            score = float(scores[0]) if len(scores) else None
            return str(labels[0]), score
    return None, None


def polygon_to_original(
    polygon: list[list[float]], source_size: tuple[int, int], paddle_angle: int
) -> list[list[float]]:
    width, height = source_size
    clockwise_rotation = (-paddle_angle) % 360
    if clockwise_rotation == 90:
        return [[y, height - x] for x, y in polygon]
    if clockwise_rotation == 180:
        return [[width - x, height - y] for x, y in polygon]
    if clockwise_rotation == 270:
        return [[width - y, x] for x, y in polygon]
    return polygon


def paddle_result_to_detections(
    results: Iterable[Any], source_size: tuple[int, int] | None = None
) -> list[dict[str, Any]]:
    detections: list[dict[str, Any]] = []
    for result in results:
        value = _as_dict(result)
        payload = value.get("res", value)
        preprocessor = payload.get("doc_preprocessor_res") or {}
        angle = int(preprocessor.get("angle", 0)) % 360
        polygons = _first_present(payload, "rec_polys", "dt_polys", "polys")
        texts = _first_present(payload, "rec_texts", "texts")
        scores = _first_present(payload, "rec_scores", "dt_scores", "scores")
        for index, polygon in enumerate(polygons):
            normalized_polygon = [[float(point[0]), float(point[1])] for point in polygon]
            if source_size is not None:
                normalized_polygon = polygon_to_original(
                    normalized_polygon, source_size, angle
                )
            text = str(texts[index]) if index < len(texts) else ""
            score = float(scores[index]) if index < len(scores) else None
            detections.append(
                {
                    "polygon": normalized_polygon,
                    "text_raw": text,
                    "confidence": score,
                    "source_id": str(len(detections)),
                }
            )
    return detections
