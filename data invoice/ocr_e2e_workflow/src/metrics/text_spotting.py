from __future__ import annotations

from typing import Any, Callable

from src.metrics.geometry import maximum_bipartite_matches, polygon_iou
from src.metrics.recognition import text_similarity
from src.postprocess.text_normalizer import normalize_text


def _score(
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    predicate: Callable[[str, str], bool],
    iou_threshold: float,
) -> dict[str, float]:
    edges: list[list[int]] = []
    for prediction in predictions:
        candidates: list[tuple[int, float]] = []
        for index, truth in enumerate(ground_truth):
            iou = polygon_iou(prediction["polygon"], truth["polygon"])
            if iou >= iou_threshold and predicate(truth["text_raw"], prediction.get("text_raw", "")):
                candidates.append((index, iou))
        candidates.sort(key=lambda item: item[1], reverse=True)
        edges.append([index for index, _ in candidates])
    matched = len(maximum_bipartite_matches(edges, len(ground_truth)))
    precision = matched / len(predictions) if predictions else 0.0
    recall = matched / len(ground_truth) if ground_truth else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "matched": matched}


def evaluate_key_field_spotting(
    predictions: list[dict[str, Any]],
    field_ground_truth: list[dict[str, Any]],
    split: str,
    iou_threshold: float = 0.5,
    soft_similarity: float = 0.8,
    location_support: bool = True,
) -> dict[str, Any]:
    if not location_support:
        return {"applicable": False, "reason": "model does not return real coordinates"}
    prediction_map = {row["image_id"]: row for row in predictions}
    exact_totals = {"pred": 0, "gt": 0, "matched": 0}
    soft_totals = {"pred": 0, "gt": 0, "matched": 0}
    for truth in field_ground_truth:
        if truth.get("split") != split:
            continue
        pred = prediction_map.get(truth["image_id"], {"detections": []}).get("detections", [])
        gt = truth.get("fields", [])
        exact = _score(
            pred,
            gt,
            lambda reference, hypothesis: normalize_text(reference) == normalize_text(hypothesis),
            iou_threshold,
        )
        soft = _score(
            pred,
            gt,
            lambda reference, hypothesis: text_similarity(normalize_text(reference), normalize_text(hypothesis)) >= soft_similarity,
            iou_threshold,
        )
        for totals, score in ((exact_totals, exact), (soft_totals, soft)):
            totals["pred"] += len(pred)
            totals["gt"] += len(gt)
            totals["matched"] += int(score["matched"])

    def finish(totals: dict[str, int]) -> dict[str, float]:
        precision = totals["matched"] / max(1, totals["pred"])
        recall = totals["matched"] / max(1, totals["gt"])
        return {
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        }

    return {"applicable": True, "exact": finish(exact_totals), "soft": finish(soft_totals)}

