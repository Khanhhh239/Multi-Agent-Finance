"""Lazy, parameterized Neon adapters for small Agent 4 control-plane records.

The cloud query slice remains usable without a database driver: importing this module
does not open a connection or require ``psycopg``. Raw questions, SQL, rows and provider
credentials are deliberately not accepted by the audit adapter.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True, repr=False)
class NeonConfig:
    """Connection settings read from environment without exposing the URL in repr/logs."""

    database_url: str = field(repr=False)
    min_size: int = 1
    max_size: int = 2
    connect_timeout_s: float = 5.0

    def __post_init__(self) -> None:
        if not self.database_url.strip():
            raise ValueError("database_url must not be empty")
        if self.min_size < 1 or self.max_size < self.min_size:
            raise ValueError("invalid Neon pool size")
        if self.connect_timeout_s <= 0:
            raise ValueError("connect_timeout_s must be positive")

    def __repr__(self) -> str:
        return (
            "NeonConfig(database_url='[REDACTED]', "
            f"min_size={self.min_size}, max_size={self.max_size}, "
            f"connect_timeout_s={self.connect_timeout_s!r})"
        )

    @classmethod
    def from_env(cls) -> NeonConfig | None:
        url = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
        if not url:
            return None
        return cls(
            database_url=url,
            min_size=int(os.getenv("NEON_POOL_MIN_SIZE", "1")),
            max_size=int(os.getenv("NEON_POOL_MAX_SIZE", "2")),
            connect_timeout_s=float(os.getenv("NEON_CONNECT_TIMEOUT_S", "5")),
        )


class NeonAuditStore:
    """Small query-audit and warehouse-manifest adapter using a bounded lazy pool."""

    def __init__(self, config: NeonConfig, *, pool=None) -> None:
        self.config = config
        self._pool = pool

    def _get_pool(self):
        if self._pool is None:
            try:
                from psycopg_pool import ConnectionPool
            except ImportError as exc:  # pragma: no cover - exercised in deploy image
                raise RuntimeError(
                    "Neon persistence requires the optional psycopg[binary,pool] dependency"
                ) from exc
            self._pool = ConnectionPool(
                conninfo=self.config.database_url,
                min_size=self.config.min_size,
                max_size=self.config.max_size,
                timeout=self.config.connect_timeout_s,
                open=False,
            )
        return self._pool

    def open(self) -> None:
        pool = self._get_pool()
        if hasattr(pool, "open"):
            pool.open(wait=True)

    def close(self) -> None:
        if self._pool is not None and hasattr(self._pool, "close"):
            self._pool.close()

    def ping(self) -> None:
        with self._get_pool().connection() as connection:
            connection.execute("SELECT 1").fetchone()

    def record_query_audit(
        self,
        *,
        audit_id: UUID,
        request_id: str,
        trace_id: str,
        tenant_id: str,
        user_id: str,
        policy_hash: str,
        status: str,
        metric_ids: list[str],
        latency_ms: float | None,
        error_code: str | None,
        data_watermark: str | None,
    ) -> None:
        """Write only bounded metadata; never accept prompt, SQL, rows or credentials."""
        with self._get_pool().connection() as connection:
            connection.execute(
                """
                INSERT INTO cloud.query_audits (
                    audit_id, request_id, trace_id, tenant_id, user_id, policy_hash,
                    status, metric_ids, latency_ms, error_code, data_watermark
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                ON CONFLICT (request_id) DO UPDATE SET
                    trace_id = EXCLUDED.trace_id,
                    status = EXCLUDED.status,
                    metric_ids = EXCLUDED.metric_ids,
                    latency_ms = EXCLUDED.latency_ms,
                    error_code = EXCLUDED.error_code,
                    data_watermark = EXCLUDED.data_watermark
                """,
                (
                    audit_id,
                    request_id,
                    trace_id,
                    tenant_id,
                    user_id,
                    policy_hash,
                    status,
                    json.dumps(metric_ids, ensure_ascii=True, separators=(",", ":")),
                    latency_ms,
                    error_code,
                    data_watermark,
                ),
            )

    def register_warehouse_artifact(
        self,
        *,
        artifact_id: UUID,
        tenant_id: str,
        object_key: str,
        sha256: str,
        size_bytes: int,
        schema_version: str,
        source_revision: str,
        generated_at,
        provider_version: str | None = None,
    ) -> None:
        """Register an immutable object reference; bytes stay in object storage."""
        with self._get_pool().connection() as connection:
            connection.execute(
                """
                INSERT INTO cloud.warehouse_artifacts (
                    artifact_id, tenant_id, object_key, sha256, size_bytes, schema_version,
                    source_revision, generated_at, provider_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, sha256) DO NOTHING
                """,
                (
                    artifact_id,
                    tenant_id,
                    object_key,
                    sha256,
                    size_bytes,
                    schema_version,
                    source_revision,
                    generated_at,
                    provider_version,
                ),
            )
