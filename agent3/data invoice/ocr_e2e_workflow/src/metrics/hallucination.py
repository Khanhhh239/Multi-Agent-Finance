from __future__ import annotations

from typing import Any

from src.postprocess.text_normalizer import normalize_text


def evaluate_hallucination_diagnostics(
    recognition_metrics: dict[str, Any],
    blank_predictions: list[dict[str, Any]] | None,
    field_predictions: list[dict[str, Any]],
    raw_predictions: list[dict[str, Any]],
) -> dict[str, Any]:
    blank_predictions = blank_predictions or []
    blank_with_text = 0
    for prediction in blank_predictions:
        text = prediction.get("document_text_raw", "") + " ".join(
            item.get("text_raw", "") for item in prediction.get("detections", [])
        )
        blank_with_text += bool(normalize_text(text))
    raw_map = {row["image_id"]: row for row in raw_predictions}
    unsupported = total_values = 0
    for field_record in field_predictions:
        raw = raw_map.get(field_record["image_id"], {})
        evidence_text = normalize_text(
            (raw.get("document_text_raw") or "")
            + " "
            + " ".join(item.get("text_raw", "") for item in raw.get("detections", []))
        ).casefold()
        for key in ("seller", "address", "timestamp", "total_cost"):
            field = field_record.get(key, {})
            raw_value = normalize_text(str(field.get("raw") or field.get("value") or "")).casefold()
            if raw_value:
                total_values += 1
                unsupported += raw_value not in evidence_text
    return {
        "recognition_insertion_rate": recognition_metrics.get("insertion_rate"),
        "blank_image_samples": len(blank_predictions),
        "blank_image_text_rate": blank_with_text / max(1, len(blank_predictions)) if blank_predictions else None,
        "unsupported_field_rate": unsupported / max(1, total_values),
        "unsupported_field_count": unsupported,
        "field_value_count": total_values,
        "scope_note": "Diagnostics only; full-page hallucination rate is unavailable without complete transcripts.",
    }

