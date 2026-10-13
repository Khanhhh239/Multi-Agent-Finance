from __future__ import annotations

import ast
import csv
from pathlib import Path
from typing import Any

from src.prepare.common import output_path, source_path
from src.utils import read_jsonl, write_jsonl


LABEL_MAP = {"TOTAL_TOTAL_COST": "TOTAL_COST"}
VALID_LABELS = {"SELLER", "ADDRESS", "TIMESTAMP", "TOTAL_COST"}


def segmentation_to_polygon(
    annotation: dict[str, Any], target_width: int, target_height: int
) -> list[list[float]]:
    segmentation = annotation.get("segmentation") or []
    if segmentation and isinstance(segmentation[0], list):
        values = max(segmentation, key=len)
    else:
        values = segmentation
    source_width = float(annotation.get("width") or target_width)
    source_height = float(annotation.get("height") or target_height)
    scale_x = target_width / source_width
    scale_y = target_height / source_height
    return [
        [float(values[i]) * scale_x, float(values[i + 1]) * scale_y]
        for i in range(0, len(values) - 1, 2)
    ]


def parse_field_row(
    row: dict[str, str], line_number: int, target_width: int, target_height: int
) -> dict[str, Any]:
    annotations = ast.literal_eval(row["anno_polygons"])
    texts = row["anno_texts"].split("|||") if row["anno_texts"] else []
    labels = row["anno_labels"].split("|||") if row["anno_labels"] else []
    labels = [LABEL_MAP.get(label, label) for label in labels]
    errors: list[str] = []
    if not (len(annotations) == len(texts) == len(labels)):
        errors.append(
            f"count mismatch polygons={len(annotations)} texts={len(texts)} labels={len(labels)}"
        )
    fields: list[dict[str, Any]] = []
    for index, (annotation, text, label) in enumerate(zip(annotations, texts, labels)):
        if label not in VALID_LABELS:
            errors.append(f"unknown label at {index}: {label}")
        fields.append(
            {
                "field_id": f"{row['img_id']}:{index}",
                "label": label,
                "text_raw": text,
                "polygon": segmentation_to_polygon(annotation, target_width, target_height),
                "bbox": annotation.get("bbox"),
                "source_category_id": annotation.get("category_id"),
            }
        )
    return {
        "image_id": row["img_id"],
        "source_line": line_number,
        "image_quality": float(row["anno_image_quality"]) if row.get("anno_image_quality") else None,
        "fields": fields,
        "errors": errors,
    }


def build_field_ground_truth(config: dict[str, Any]) -> dict[str, Any]:
    manifest_dir = output_path(config, "manifests")
    allowed: dict[str, dict[str, Any]] = {}
    for split in ("dev", "test"):
        for record in read_jsonl(manifest_dir / f"full_image_{split}.jsonl"):
            allowed[record["image_id"]] = {**record, "split": split}
    records: list[dict[str, Any]] = []
    with source_path(config, "field_csv").open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for line_number, row in enumerate(reader, 2):
            image_id = row["img_id"]
            if image_id not in allowed:
                continue
            target = allowed[image_id]
            record = parse_field_row(row, line_number, int(target["width"]), int(target["height"]))
            record["split"] = target["split"]
            records.append(record)
    ground_truth_dir = output_path(config, "ground_truth")
    write_jsonl(ground_truth_dir / "fields" / "all.jsonl", records)
    label_counts: dict[str, int] = {}
    for record in records:
        for field in record["fields"]:
            label_counts[field["label"]] = label_counts.get(field["label"], 0) + 1
    return {
        "images": len(records),
        "fields": sum(len(row["fields"]) for row in records),
        "label_counts": label_counts,
        "errors": [
            {"image_id": row["image_id"], "errors": row["errors"]}
            for row in records
            if row["errors"]
        ],
    }
