from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageOps, ImageStat

from src.prepare.common import image_size, output_path, source_path
from src.utils import read_jsonl, write_jsonl


def polygon_area(points: list[list[float]]) -> float:
    return abs(
        sum(
            points[index][0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * points[index][1]
            for index in range(len(points))
        )
    ) / 2


def detect_rotation_to_target(source_path: Path, target_path: Path) -> tuple[int, dict[str, float]]:
    """Find the clockwise rotation that aligns the label image with the benchmark image."""
    with Image.open(source_path) as source_raw, Image.open(target_path) as target_raw:
        source = source_raw.convert("L")
        target = ImageOps.autocontrast(target_raw.convert("L").resize((96, 96)))
        transposes = {
            0: None,
            90: Image.Transpose.ROTATE_270,
            180: Image.Transpose.ROTATE_180,
            270: Image.Transpose.ROTATE_90,
        }
        scores: dict[str, float] = {}
        for rotation, transpose in transposes.items():
            candidate = source if transpose is None else source.transpose(transpose)
            candidate = ImageOps.autocontrast(candidate.resize((96, 96)))
            difference = ImageChops.difference(candidate, target)
            scores[str(rotation)] = ImageStat.Stat(difference).mean[0] / 255.0
    best_rotation = min((int(value) for value in scores), key=lambda value: scores[str(value)])
    return best_rotation, scores


def transform_point(
    x: float,
    y: float,
    source_width: int,
    source_height: int,
    target_width: int,
    target_height: int,
    rotation: int,
) -> list[float]:
    rotation %= 360
    if rotation == 90:
        rotated_x, rotated_y = source_height - y, x
        rotated_width, rotated_height = source_height, source_width
    elif rotation == 180:
        rotated_x, rotated_y = source_width - x, source_height - y
        rotated_width, rotated_height = source_width, source_height
    elif rotation == 270:
        rotated_x, rotated_y = y, source_width - x
        rotated_width, rotated_height = source_height, source_width
    else:
        rotated_x, rotated_y = x, y
        rotated_width, rotated_height = source_width, source_height
    return [
        rotated_x * target_width / rotated_width,
        rotated_y * target_height / rotated_height,
    ]


def parse_detection_file(
    path: Path,
    source_width: int,
    source_height: int,
    target_width: int,
    target_height: int,
    rotation: int = 0,
) -> tuple[list[dict[str, Any]], list[str]]:
    boxes: list[dict[str, Any]] = []
    errors: list[str] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            tokens = [token.strip() for token in raw_line.rstrip("\r\n").split(",")]
            if len(tokens) < 10:
                errors.append(f"{path.name}:{line_number}: invalid TSV column count {len(tokens)}")
                continue
            try:
                values = [float(token) for token in tokens[1:9]]
            except ValueError:
                errors.append(f"{path.name}:{line_number}: non-numeric coordinate")
                continue
            polygon = [
                transform_point(
                    values[i],
                    values[i + 1],
                    source_width,
                    source_height,
                    target_width,
                    target_height,
                    rotation,
                )
                for i in range(0, 8, 2)
            ]
            area = polygon_area(polygon)
            in_bounds = all(0 <= x <= target_width and 0 <= y <= target_height for x, y in polygon)
            if area <= 0:
                errors.append(f"{path.name}:{line_number}: zero-area polygon")
            boxes.append(
                {
                    "polygon": polygon,
                    "area": area,
                    "in_bounds": in_bounds,
                    "line_number": line_number,
                    "transcript": ",".join(tokens[9:-1]) if len(tokens) > 10 else tokens[9],
                    "label": tokens[-1] if len(tokens) > 10 else None,
                }
            )
    return boxes, errors


def build_detection_ground_truth(config: dict[str, Any]) -> dict[str, Any]:
    manifest_dir = output_path(config, "manifests")
    detection_dir = source_path(config, "detection_labels")
    detection_image_dir = source_path(config, "detection_images")
    ground_truth_dir = output_path(config, "ground_truth")
    records: list[dict[str, Any]] = []
    all_errors: list[str] = []
    for split in ("dev", "test"):
        for image in read_jsonl(manifest_dir / f"full_image_{split}.jsonl"):
            label_path = detection_dir / f"{Path(image['image_id']).stem}.tsv"
            detection_image_path = detection_image_dir / image["image_id"]
            boxes: list[dict[str, Any]] = []
            errors: list[str] = []
            alignment: dict[str, Any] | None = None
            if label_path.is_file() and detection_image_path.is_file() and image.get("exists"):
                source_width, source_height = image_size(detection_image_path)
                rotation, scores = detect_rotation_to_target(
                    detection_image_path, Path(image["image_path"])
                )
                sorted_scores = sorted(scores.values())
                alignment = {
                    "clockwise_rotation": rotation,
                    "scores": scores,
                    "best_score": sorted_scores[0],
                    "margin": sorted_scores[1] - sorted_scores[0],
                }
                boxes, errors = parse_detection_file(
                    label_path,
                    source_width,
                    source_height,
                    image["width"],
                    image["height"],
                    rotation,
                )
            elif not label_path.is_file():
                errors.append(f"missing detection label: {label_path.name}")
            elif not detection_image_path.is_file():
                errors.append(f"missing detection source image: {detection_image_path.name}")
            all_errors.extend(errors)
            records.append(
                {
                    "image_id": image["image_id"],
                    "split": split,
                    "label_path": str(label_path.resolve()),
                    "coordinate_source_image": str(detection_image_path.resolve()),
                    "alignment": alignment,
                    "boxes": boxes,
                    "errors": errors,
                }
            )
    write_jsonl(ground_truth_dir / "detection" / "all.jsonl", records)
    return {
        "images": len(records),
        "boxes": sum(len(row["boxes"]) for row in records),
        "errors": all_errors,
    }
