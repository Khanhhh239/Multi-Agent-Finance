from __future__ import annotations

import hashlib
import json
import os
import platform
import random
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

import yaml


WORKFLOW_ROOT = Path(__file__).resolve().parents[1]


def resolve_path(value: str | Path, base: Path = WORKFLOW_ROOT) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def environment_dir_from_python(value: str | Path) -> Path:
    configured = resolve_path(value)
    if configured.parent.name.lower() in {"scripts", "bin"}:
        return configured.parent.parent
    return configured.parent


def resolve_python_executable(value: str | Path) -> Path:
    configured = resolve_path(value)
    if configured.is_file():
        return configured
    environment_dir = environment_dir_from_python(value)
    candidates = (
        [environment_dir / "Scripts" / "python.exe", environment_dir / "bin" / "python"]
        if os.name == "nt"
        else [environment_dir / "bin" / "python", environment_dir / "Scripts" / "python.exe"]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def assert_within_workflow(path: Path) -> None:
    target = path.resolve()
    try:
        target.relative_to(WORKFLOW_ROOT)
    except ValueError as exc:
        raise ValueError(f"Refusing to write outside workflow: {target}") from exc


def ensure_output_dir(path: str | Path) -> Path:
    target = resolve_path(path)
    assert_within_workflow(target)
    target.mkdir(parents=True, exist_ok=True)
    return target


def load_yaml(path: str | Path) -> dict[str, Any]:
    with resolve_path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def dump_yaml(path: str | Path, data: dict[str, Any]) -> None:
    target = resolve_path(path)
    assert_within_workflow(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    with resolve_path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"JSONL record must be object: {path}:{line_number}")
            yield value


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> None:
    target = resolve_path(path)
    assert_within_workflow(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n")


def write_json(path: str | Path, data: Any) -> None:
    target = resolve_path(path)
    assert_within_workflow(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")


def read_json(path: str | Path) -> Any:
    with resolve_path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with resolve_path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


_CROP_SUFFIX = re.compile(r"^(?P<stem>.+)_([0-9]+)(?P<suffix>\.[^.]+)$")


def crop_to_source_name(filename: str) -> str:
    match = _CROP_SUFFIX.match(Path(filename).name)
    if not match:
        raise ValueError(f"Crop filename has no numeric suffix: {filename}")
    return f"{match.group('stem')}{match.group('suffix')}"


def utc_run_id(model_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", model_id)
    return f"{stamp}_{safe}"


def environment_metadata() -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cwd": os.getcwd(),
    }
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        metadata["gpu"] = result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        metadata["gpu"] = None
    return metadata


def seed_everything(seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass
