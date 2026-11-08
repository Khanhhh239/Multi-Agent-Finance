from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from src.prepare.common import output_path
from src.utils import read_jsonl, write_json


def duplicate_values(records: list[dict[str, Any]], key: str) -> list[str]:
    values = [str(record[key]) for record in records]
    return sorted(value for value, count in Counter(values).items() if count > 1)


def validate_prepared_data(config: dict[str, Any]) -> dict[str, Any]:
    manifest_dir = output_path(config, "manifests")
    ground_truth_dir = output_path(config, "ground_truth")
    train_rec = list(read_jsonl(manifest_dir / "recognition_train.jsonl"))
    test_rec = list(read_jsonl(manifest_dir / "recognition_test.jsonl"))
    dev = list(read_jsonl(manifest_dir / "full_image_dev.jsonl"))
    test = list(read_jsonl(manifest_dir / "full_image_test.jsonl"))
    detection = list(read_jsonl(ground_truth_dir / "detection" / "all.jsonl"))
    fields = list(read_jsonl(ground_truth_dir / "fields" / "all.jsonl"))

    train_ids = {row["source_image_id"] for row in train_rec}
    test_ids = {row["source_image_id"] for row in test_rec}
    dev_ids = {row["image_id"] for row in dev}
    full_test_ids = {row["image_id"] for row in test}
    detection_ids = {row["image_id"] for row in detection}
    field_ids = {row["image_id"] for row in fields}

    errors: list[str] = []
    if train_ids & test_ids:
        errors.append(f"recognition source leakage: {len(train_ids & test_ids)}")
    if dev_ids & full_test_ids:
        errors.append(f"full-image leakage: {len(dev_ids & full_test_ids)}")
    missing_crops = [row["crop_id"] for row in train_rec + test_rec if not row["exists"]]
    missing_full = [row["image_id"] for row in dev + test if not row["exists"]]
    if missing_crops:
        errors.append(f"missing crop images: {len(missing_crops)}")
    if missing_full:
        errors.append(f"missing full images: {len(missing_full)}")
    expected_ids = dev_ids | full_test_ids
    if detection_ids != expected_ids:
        errors.append("detection ground-truth image IDs do not match manifests")
    if not full_test_ids <= field_ids:
        errors.append(f"test images missing field GT: {len(full_test_ids - field_ids)}")

    warnings: list[str] = []
    invalid_detection = sum(len(row.get("errors", [])) for row in detection)
    if invalid_detection:
        warnings.append(f"detection label warnings: {invalid_detection}")
    field_errors = sum(len(row.get("errors", [])) for row in fields)
    if field_errors:
        warnings.append(f"field label warnings: {field_errors}")

    report = {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "recognition_train": len(train_rec),
            "recognition_test": len(test_rec),
            "dev_images": len(dev),
            "test_images": len(test),
            "detection_images": len(detection),
            "field_images": len(fields),
            "detection_boxes": sum(len(row["boxes"]) for row in detection),
            "fields": sum(len(row["fields"]) for row in fields),
        },
        "missing_crops": missing_crops,
        "missing_full_images": missing_full,
        "duplicate_train_crops": duplicate_values(train_rec, "crop_id"),
        "duplicate_test_crops": duplicate_values(test_rec, "crop_id"),
    }
    write_json(ground_truth_dir / "validation_report.json", report)
    return report

