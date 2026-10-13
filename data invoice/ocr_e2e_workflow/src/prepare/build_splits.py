from __future__ import annotations

from pathlib import Path
from typing import Any

from src.prepare.common import image_size, output_path, source_path
from src.utils import crop_to_source_name, sha256_file, write_jsonl


def parse_recognition_labels(label_path: Path, image_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with label_path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            line = raw_line.rstrip("\r\n")
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) != 2:
                raise ValueError(f"Expected tab in {label_path}:{line_number}")
            filename, text = parts
            image_path = (image_dir / filename).resolve()
            source_name = crop_to_source_name(filename)
            records.append(
                {
                    "crop_id": filename,
                    "crop_path": str(image_path),
                    "source_image_id": source_name,
                    "text_raw": text,
                    "line_number": line_number,
                    "exists": image_path.is_file(),
                }
            )
    return records


def build_splits(config: dict[str, Any]) -> dict[str, Any]:
    recognition_dir = source_path(config, "recognition_images")
    train_records = parse_recognition_labels(
        source_path(config, "recognition_train_labels"), recognition_dir
    )
    test_records = parse_recognition_labels(
        source_path(config, "recognition_test_labels"), recognition_dir
    )
    manifest_dir = output_path(config, "manifests")
    manifest_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(manifest_dir / "recognition_train.jsonl", train_records)
    write_jsonl(manifest_dir / "recognition_test.jsonl", test_records)

    test_ids = {item["source_image_id"] for item in test_records}
    train_ids = {item["source_image_id"] for item in train_records}
    overlap = sorted(test_ids & train_ids)
    full_image_dir = source_path(config, "full_images")

    def full_record(image_id: str, split: str) -> dict[str, Any]:
        path = (full_image_dir / image_id).resolve()
        record: dict[str, Any] = {
            "image_id": image_id,
            "image_path": str(path),
            "split": split,
            "exists": path.is_file(),
        }
        if path.is_file():
            width, height = image_size(path)
            record.update(
                {
                    "width": width,
                    "height": height,
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
        return record

    dev_ids = sorted(train_ids - test_ids)
    full_dev = [full_record(image_id, "dev") for image_id in dev_ids]
    full_test = [full_record(image_id, "test") for image_id in sorted(test_ids)]
    write_jsonl(manifest_dir / "full_image_dev.jsonl", full_dev)
    write_jsonl(manifest_dir / "full_image_test.jsonl", full_test)
    return {
        "recognition_train_count": len(train_records),
        "recognition_test_count": len(test_records),
        "dev_source_count": len(full_dev),
        "test_source_count": len(full_test),
        "source_overlap": overlap,
        "missing_recognition_images": sum(not row["exists"] for row in train_records + test_records),
        "missing_full_images": sum(not row["exists"] for row in full_dev + full_test),
    }

