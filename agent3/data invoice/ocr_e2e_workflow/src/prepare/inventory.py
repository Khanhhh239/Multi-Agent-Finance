from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.prepare.common import output_path, source_path
from src.utils import sha256_file, write_json


SOURCE_KEYS = (
    "recognition_images",
    "recognition_train_labels",
    "recognition_test_labels",
    "full_images",
    "field_csv",
    "detection_labels",
    "detection_images",
    "detection_visualization_labels",
    "kie_transcripts",
)


def inventory_path(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    if path.is_file():
        return {
            "path": str(path),
            "exists": True,
            "type": "file",
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    extensions = Counter(item.suffix.lower() for item in path.iterdir() if item.is_file())
    files = [item for item in path.iterdir() if item.is_file()]
    return {
        "path": str(path),
        "exists": True,
        "type": "directory",
        "file_count": len(files),
        "size_bytes": sum(item.stat().st_size for item in files),
        "extensions": dict(sorted(extensions.items())),
    }


def build_inventory(config: dict[str, Any]) -> dict[str, Any]:
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": {key: inventory_path(source_path(config, key)) for key in SOURCE_KEYS},
    }
    manifest_dir = output_path(config, "manifests")
    manifest_dir.mkdir(parents=True, exist_ok=True)
    write_json(manifest_dir / "source_inventory.json", report)
    return report
