from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from src.utils import WORKFLOW_ROOT, load_yaml, resolve_path


def benchmark_config(path: str | Path = "configs/benchmark.yaml") -> dict[str, Any]:
    config = load_yaml(path)
    config["_config_path"] = str(resolve_path(path))
    return config


def source_path(config: dict[str, Any], key: str) -> Path:
    value = config.get("paths", {}).get(key)
    if not value:
        raise KeyError(f"Missing paths.{key} in benchmark config")
    return resolve_path(value, WORKFLOW_ROOT)


def output_path(config: dict[str, Any], key: str) -> Path:
    value = config.get("output", {}).get(key)
    if not value:
        raise KeyError(f"Missing output.{key} in benchmark config")
    return resolve_path(value, WORKFLOW_ROOT)


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size

