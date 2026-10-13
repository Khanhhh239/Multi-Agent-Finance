from __future__ import annotations

from pathlib import Path
from typing import Any

from src.metrics.confidence_interval import bootstrap_mean_ci
from src.metrics.detection import evaluate_detection
from src.metrics.fields import evaluate_fields
from src.metrics.hallucination import evaluate_hallucination_diagnostics
from src.metrics.performance import evaluate_performance
from src.metrics.recognition import evaluate_pairs
from src.metrics.text_spotting import evaluate_key_field_spotting
from src.postprocess.field_extractor import extract_fields
from src.prepare.common import output_path
from src.utils import read_json, read_jsonl, write_json, write_jsonl


def _recognized_text(result: dict[str, Any]) -> str:
    if result.get("document_text_raw"):
        return str(result["document_text_raw"])
    detections = result.get("detections", [])
    return " ".join(item.get("text_raw", "") for item in detections).strip()


def filter_ground_truth(
    rows: list[dict[str, Any]], split: str, evaluated_image_ids: set[str]
) -> list[dict[str, Any]]:
    """Keep ground truth for exactly the images captured in this run."""
    return [
        row
        for row in rows
        if row.get("split") == split and row.get("image_id") in evaluated_image_ids
    ]


def evaluate_run(config: dict[str, Any], run_id: str) -> Path:
    run_dir = output_path(config, "runs") / run_id
    snapshot = read_json(run_dir / "config.snapshot.json")
    split = snapshot["split"]
    predictions = list(read_jsonl(run_dir / "predictions" / "raw.jsonl"))
    full_manifest = list(read_jsonl(run_dir / "inputs" / "full_images.jsonl"))
    evaluated_image_ids = {row["image_id"] for row in full_manifest}
    recognition_predictions = list(read_jsonl(run_dir / "predictions" / "recognition_raw.jsonl"))
    recognition_manifest = list(read_jsonl(run_dir / "inputs" / "recognition_crops.jsonl"))
    pred_by_crop = {row["image_id"]: row for row in recognition_predictions}
    pairs = [
        (row["text_raw"], _recognized_text(pred_by_crop.get(row["crop_id"], {})))
        for row in recognition_manifest
    ]
    recognition_strict = evaluate_pairs(pairs, normalized=False)
    recognition_normalized = evaluate_pairs(pairs, normalized=True)

    field_predictions = [extract_fields(row) for row in predictions]
    write_jsonl(run_dir / "predictions" / "fields.jsonl", field_predictions)
    detection_gt = list(read_jsonl(output_path(config, "ground_truth") / "detection" / "all.jsonl"))
    field_gt = list(read_jsonl(output_path(config, "ground_truth") / "fields" / "all.jsonl"))
    detection_gt = filter_ground_truth(detection_gt, split, evaluated_image_ids)
    field_gt = filter_ground_truth(field_gt, split, evaluated_image_ids)
    location_support = any(
        bool(row.get("metadata", {}).get("location_support")) for row in predictions if not row.get("error")
    )

    detection = evaluate_detection(
        predictions,
        detection_gt,
        [float(value) for value in config["evaluation"]["detection_iou_thresholds"]],
        location_support,
    )
    spotting = evaluate_key_field_spotting(
        predictions,
        field_gt,
        split,
        float(config["evaluation"]["primary_iou_threshold"]),
        float(config["evaluation"]["soft_text_similarity"]),
        location_support,
    )
    fields = evaluate_fields(field_predictions, field_gt, split)
    performance = evaluate_performance(predictions)
    hallucination = evaluate_hallucination_diagnostics(
        recognition_normalized, None, field_predictions, predictions
    )
    ci = bootstrap_mean_ci(
        [float(row["all_four_correct"]) for row in fields["per_image"]],
        int(config["evaluation"].get("bootstrap_samples", 1000)),
        seed=int(config.get("seed", 20260922)),
    )
    metrics = {
        "run_id": run_id,
        "model_id": snapshot["model_id"],
        "model_revision": snapshot.get("revision") or snapshot.get("model_name") or snapshot.get("ocr_version"),
        "split": split,
        "output_mode": snapshot.get("output_mode"),
        "sample_counts": {
            "full_images": len(full_manifest),
            "recognition_crops": len(recognition_manifest),
        },
        "location_support": location_support,
        "recognition_strict": recognition_strict,
        "recognition_normalized": recognition_normalized,
        "detection": detection,
        "text_spotting": spotting,
        "fields": fields,
        "performance": performance,
        "hallucination_diagnostics": hallucination,
        "all_four_fields_ci95": ci,
    }
    for name, value in metrics.items():
        if isinstance(value, dict):
            write_json(run_dir / "metrics" / f"{name}.json", value)
    write_json(run_dir / "metrics" / "summary.json", metrics)
    return run_dir / "metrics" / "summary.json"
