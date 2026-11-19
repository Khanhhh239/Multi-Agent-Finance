"""Fetch and verify one immutable warehouse artifact from a presigned URL."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import httpx

_DEFAULT_MAX_BYTES = 64 * 1024 * 1024


def _expected_sha256() -> str | None:
    value = os.getenv("AGENT4_WAREHOUSE_SHA256", "").strip().lower()
    if not value:
        return None
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise RuntimeError("AGENT4_WAREHOUSE_SHA256 must be a 64-character hexadecimal digest")
    return value


def _max_bytes() -> int:
    value = int(os.getenv("AGENT4_WAREHOUSE_MAX_BYTES", str(_DEFAULT_MAX_BYTES)))
    if value <= 0:
        raise RuntimeError("AGENT4_WAREHOUSE_MAX_BYTES must be positive")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify(path: Path, expected: str | None, max_bytes: int) -> None:
    size = path.stat().st_size
    if size <= 0 or size > max_bytes:
        raise RuntimeError("warehouse artifact size is outside the configured limit")
    if expected and _sha256(path) != expected:
        raise RuntimeError("warehouse artifact checksum mismatch")


def prepare() -> None:
    raw_path = os.getenv("AGENT4_WAREHOUSE_PATH", "").strip()
    if not raw_path:
        raise RuntimeError("AGENT4_WAREHOUSE_PATH is required in cloud mode")
    path = Path(raw_path)
    expected = _expected_sha256()
    max_bytes = _max_bytes()
    if path.is_file():
        _verify(path, expected, max_bytes)
        return

    url = os.getenv("AGENT4_WAREHOUSE_URL", "").strip()
    if not url:
        raise RuntimeError("warehouse artifact is missing and AGENT4_WAREHOUSE_URL is not set")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.download")
    digest = hashlib.sha256()
    size = 0
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True, trust_env=False) as client, client.stream(
            "GET", url
        ) as response:
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > max_bytes:
                raise RuntimeError("warehouse artifact exceeds configured size limit")
            with temporary.open("wb") as output:
                for chunk in response.iter_bytes(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise RuntimeError("warehouse artifact exceeds configured size limit")
                    digest.update(chunk)
                    output.write(chunk)
        if size == 0 or (expected and digest.hexdigest() != expected):
            raise RuntimeError("warehouse artifact checksum or size verification failed")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    _verify(path, expected, max_bytes)


if __name__ == "__main__":
    prepare()
