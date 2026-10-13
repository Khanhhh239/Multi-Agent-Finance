from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from PIL import Image
from tqdm.auto import tqdm

from src.adapters import create_adapter
from src.contracts import OCRResult
from src.utils import read_jsonl


def failed_result(config: dict, run_id: str, image_path: Path, error: str) -> dict:
    with Image.open(image_path) as image:
        width, height = image.size
    return OCRResult(
        schema_version="1.1",
        run_id=run_id,
        model_id=config["model_id"],
        output_mode=config.get("output_mode", "full_page_text"),
        image_id=image_path.name,
        image_width=width,
        image_height=height,
        load_time_ms=0.0,
        inference_time_ms=0.0,
        error=error,
        metadata={"traceback": traceback.format_exc(limit=8)},
    ).to_dict()


def prepare_resume(
    output_path: Path, all_records: list[dict], resume: bool
) -> tuple[list[dict], int]:
    if not resume or not output_path.is_file():
        return all_records, 0
    completed_ids: set[str] = set()
    valid_existing: list[dict] = []
    with output_path.open("r", encoding="utf-8") as existing:
        for line in existing:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and item.get("image_id"):
                valid_existing.append(item)
                completed_ids.add(str(item["image_id"]))
    # Remove a possible truncated final line left by a native process crash.
    with output_path.open("w", encoding="utf-8", newline="\n") as repaired:
        for item in valid_existing:
            repaired.write(json.dumps(item, ensure_ascii=False) + "\n")
    remaining = [
        row
        for row in all_records
        if str(row.get("image_id") or row.get("crop_id")) not in completed_ids
    ]
    return remaining, len(completed_ids)


def discard_recovered_native_failures(output_path: Path) -> int:
    """Let a later run retry samples marked failed after a native worker crash."""
    if not output_path.is_file():
        return 0
    retained = []
    removed = 0
    with output_path.open("r", encoding="utf-8") as existing:
        for line in existing:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                retained.append(line)
                continue
            if (
                isinstance(item, dict)
                and item.get("metadata", {}).get("recovery_action")
                == "sample_marked_failed"
            ):
                removed += 1
            else:
                retained.append(line)
    if removed:
        replacement = output_path.with_name(output_path.name + ".retry.tmp")
        with replacement.open("w", encoding="utf-8", newline="\n") as target:
            target.writelines(retained)
        replacement.replace(output_path)
    return removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-json", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--description", default="OCR")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-samples-per-worker", type=int)
    args = parser.parse_args()
    config = json.loads(Path(args.config_json).read_text(encoding="utf-8"))
    all_records = list(read_jsonl(args.manifest))
    if (
        config.get("adapter") == "ppocrv6_vietocr"
        and all_records
        and all("crop_path" in row and "image_path" not in row for row in all_records)
    ):
        config["recognition_only"] = True
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records, completed_count = prepare_resume(output_path, all_records, args.resume)
    if not records:
        tqdm.write(
            f"[{args.description}] Already complete ({completed_count}/{len(all_records)}).",
            file=sys.stderr,
        )
        return 0
    try:
        tqdm.write(
            f"[{args.description}] Loading {config['model_id']}...",
            file=sys.stderr,
        )
        adapter = create_adapter(config, args.run_id)
        initialization_error = None
    except Exception as exc:
        adapter = None
        initialization_error = f"adapter initialization failed: {type(exc).__name__}: {exc}"

    mode = "a" if args.resume else "w"
    processed = 0
    with output_path.open(mode, encoding="utf-8", newline="\n") as handle:
        for row in tqdm(
            records,
            desc=args.description,
            unit="image",
            dynamic_ncols=True,
            total=len(all_records),
            initial=completed_count,
        ):
            image_path = Path(row.get("image_path") or row.get("crop_path"))
            if initialization_error:
                prediction = failed_result(config, args.run_id, image_path, initialization_error)
            else:
                prediction = adapter.predict(image_path).to_dict()
            handle.write(json.dumps(prediction, ensure_ascii=False) + "\n")
            handle.flush()
            processed += 1
            if (
                args.max_samples_per_worker is not None
                and processed >= args.max_samples_per_worker
            ):
                break
    if processed < len(records):
        tqdm.write(
            f"[{args.description}] Planned worker recycle after {processed} samples.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
