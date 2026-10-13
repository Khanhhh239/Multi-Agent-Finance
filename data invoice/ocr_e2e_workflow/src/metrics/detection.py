from __future__ import annotations

from typing import Any

from src.metrics.geometry import match_polygons


def _safe_prf(true_positive: int, predicted: int, actual: int) -> dict[str, float]:
    precision = true_positive / predicted if predicted else (1.0 if actual == 0 else 0.0)
    recall = true_positive / actual if actual else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def evaluate_detection(
    predictions: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    thresholds: list[float],
    location_support: bool,
) -> dict[str, Any]:
    if not location_support:
        return {"applicable": False, "reason": "model does not return real coordinates"}
    prediction_map = {row["image_id"]: row for row in predictions}
    output: dict[str, Any] = {"applicable": True, "thresholds": {}, "per_image": []}
    for threshold in thresholds:
        total_predicted = total_actual = total_matched = 0
        macro: list[dict[str, float]] = []
        for truth in ground_truth:
            prediction = prediction_map.get(truth["image_id"], {"detections": []})
            pred_polygons = [item["polygon"] for item in prediction.get("detections", []) if item.get("polygon")]
            gt_polygons = [item["polygon"] for item in truth.get("boxes", [])]
            matches = match_polygons(pred_polygons, gt_polygons, threshold)
            total_predicted += len(pred_polygons)
            total_actual += len(gt_polygons)
            total_matched += len(matches)
            score = _safe_prf(len(matches), len(pred_polygons), len(gt_polygons))
            macro.append(score)
            if threshold == 0.5:
                output["per_image"].append({"image_id": truth["image_id"], **score})
        micro = _safe_prf(total_matched, total_predicted, total_actual)
        output["thresholds"][str(threshold)] = {
            "micro": micro,
            "macro": {
                key: sum(item[key] for item in macro) / max(1, len(macro))
                for key in ("precision", "recall", "f1")
            },
            "true_positive": total_matched,
            "false_positive": total_predicted - total_matched,
            "false_negative": total_actual - total_matched,
        }
    return output

