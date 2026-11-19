"""Offline contracts for the additive Neon migration and lazy adapter."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from agent4.persistence.neon import NeonAuditStore, NeonConfig
from scripts.migrate_neon import migration_plan


class _Connection:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return self

    def fetchone(self):
        return (1,)


class _Pool:
    def __init__(self):
        self.connection_obj = _Connection()

    def connection(self):
        return self.connection_obj


def test_migration_plan_is_present_additive_and_secret_free():
    plan = migration_plan()
    assert [item["version"] for item in plan] == ["001"]
    sql = (
        Path(__file__).resolve().parents[3]
        / "database/migrations/001_agent4_cloud_control_plane.sql"
    ).read_text(encoding="utf-8")
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "vector(4096)" in sql
    assert "DROP " not in sql.upper()
    assert "TRUNCATE " not in sql.upper()
    assert "DELETE " not in sql.upper()


def test_neon_config_hides_url_and_reads_optional_environment(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("NEON_DATABASE_URL", raising=False)
    assert NeonConfig.from_env() is None
    config = NeonConfig("postgresql://user:secret@example.test/db")
    assert "secret" not in repr(config)
    assert "[REDACTED]" in repr(config)


def test_neon_audit_adapter_writes_bounded_metadata_only():
    pool = _Pool()
    store = NeonAuditStore(NeonConfig("postgresql://user:secret@example.test/db"), pool=pool)
    store.record_query_audit(
        audit_id=uuid4(),
        request_id="request-1",
        trace_id="trace-1",
        tenant_id="tenant-a",
        user_id="user-a",
        policy_hash="policy-a",
        status="ready",
        metric_ids=["net_revenue"],
        latency_ms=12.5,
        error_code=None,
        data_watermark="2026-08-31",
    )
    query, params = pool.connection_obj.calls[0]
    assert "query_audits" in query
    assert json.loads(params[7]) == ["net_revenue"]
    assert all("secret" not in str(item) for item in params)
    assert "SELECT" not in query.upper()


def test_neon_warehouse_manifest_is_parameterized():
    pool = _Pool()
    store = NeonAuditStore(NeonConfig("postgresql://user:secret@example.test/db"), pool=pool)
    store.register_warehouse_artifact(
        artifact_id=uuid4(),
        tenant_id="tenant-a",
        object_key="tenants/tenant-a/warehouses/artifact-1/warehouse.duckdb",
        sha256="a" * 64,
        size_bytes=1024,
        schema_version="agent4-smoke-v1",
        source_revision="test",
        generated_at=datetime.now(UTC),
    )
    query, params = pool.connection_obj.calls[0]
    assert "warehouse_artifacts" in query
    assert params[3] == "a" * 64
