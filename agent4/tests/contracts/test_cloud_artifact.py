"""Offline verification contracts for the immutable cloud warehouse artifact."""

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from cloud.prepare_artifact import prepare


def test_existing_artifact_requires_checksum_and_size_budget(monkeypatch, tmp_path):
    path = tmp_path / "warehouse.duckdb"
    path.write_bytes(b"immutable smoke artifact")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setenv("AGENT4_WAREHOUSE_PATH", str(path))
    monkeypatch.setenv("AGENT4_WAREHOUSE_SHA256", digest)
    monkeypatch.setenv("AGENT4_WAREHOUSE_MAX_BYTES", "1024")
    monkeypatch.delenv("AGENT4_WAREHOUSE_URL", raising=False)
    prepare()


def test_checksum_mismatch_fails_before_runtime(monkeypatch, tmp_path):
    path = tmp_path / "warehouse.duckdb"
    path.write_bytes(b"not-the-published-artifact")
    monkeypatch.setenv("AGENT4_WAREHOUSE_PATH", str(path))
    monkeypatch.setenv("AGENT4_WAREHOUSE_SHA256", "0" * 64)
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        prepare()


def test_missing_artifact_requires_presigned_url(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT4_WAREHOUSE_PATH", str(tmp_path / "missing.duckdb"))
    monkeypatch.delenv("AGENT4_WAREHOUSE_URL", raising=False)
    with pytest.raises(RuntimeError, match="URL is not set"):
        prepare()
