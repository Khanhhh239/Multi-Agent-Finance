"""Run safety-approved SQL against its authorized read-only warehouse."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from threading import Timer
from time import monotonic
from typing import Any

import duckdb

from agent4.core.cache import LRUTTLCache, build_scoped_cache_key, file_revision
from agent4.core.errors import ContractError

from .compiler import BoundQuery
from .safety import SafeBoundQuery, SafetyResult

_STAGE = "sql_execution"
_MAX_CACHED_ROWS = 200
_RESULT_CACHE: LRUTTLCache[str, dict[str, Any]] = LRUTTLCache(
    max_entries=256,
    ttl_seconds=600,
    max_bytes_budget=16 * 1024 * 1024,
    max_rows_per_entry=_MAX_CACHED_ROWS,
)


def execute_safe_sql(
    safety_result: SafetyResult,
    *,
    timeout_ms: int = 5000,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Execute only the SQL and warehouse path sealed by the safety gate."""
    safe = safety_result.get("safe_bound_query") if isinstance(safety_result, dict) else None
    if (
        type(safe) is not SafeBoundQuery
        or safe.warehouse_path is None
        or safety_result.get("status") != "allowed"
        or safety_result.get("query_fingerprint") != safe.query.fingerprint
    ):
        raise ContractError("unsafe_sql_rejected", _STAGE, "Query lacks warehouse authorization.")
    if type(timeout_ms) is not int or timeout_ms <= 0:
        raise ContractError("invalid_request", _STAGE, "Invalid execution deadline.")

    started = monotonic()
    deadline = started + timeout_ms / 1000
    try:
        revision = _warehouse_revision(safe.warehouse_path)
        with _connect_read_only(safe.warehouse_path) as connection:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise _timeout()
            timer = Timer(remaining, connection.interrupt)
            timer.daemon = True
            timer.start()
            try:
                result = _execute(connection, safe.query, revision, use_cache, deadline)
            finally:
                timer.cancel()
                timer.join()
        if _warehouse_revision(safe.warehouse_path) != revision:
            raise _unavailable()
    except duckdb.InterruptException:
        raise _timeout() from None
    except (duckdb.Error, OSError):
        if monotonic() >= deadline:
            raise _timeout() from None
        raise _unavailable() from None
    if monotonic() >= deadline:
        raise _timeout()

    data, key, cache_hit = result
    if key is not None and not cache_hit and data["row_count"] <= _MAX_CACHED_ROWS:
        _RESULT_CACHE.set(key, data)
    return {**data, "cache_hit": cache_hit, "execution_ms": (monotonic() - started) * 1000}


def _connect_read_only(path: Path) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(
        str(path),
        read_only=True,
        config={"enable_external_access": "false", "threads": "1", "memory_limit": "512MB"},
    )


def _warehouse_revision(path: Path) -> tuple[tuple, tuple | None]:
    try:
        wal = file_revision(path.with_name(path.name + ".wal"))
    except FileNotFoundError:
        wal = None
    return file_revision(path), wal


def _execute(
    connection: duckdb.DuckDBPyConnection,
    bound: BoundQuery,
    revision: tuple,
    use_cache: bool,
    deadline: float,
) -> tuple[dict, str | None, bool]:
    connection.execute("BEGIN TRANSACTION")
    calendar = dict(
        connection.execute(
            "SELECT key, value FROM company_info WHERE key IN (?, ?, ?)",
            ["as_of_date", "data_start", "last_closed_month"],
        ).fetchall()
    )
    watermark = calendar.get("as_of_date")
    try:
        if type(watermark) is not str or date.fromisoformat(watermark).isoformat() != watermark:
            raise _unavailable()
    except ValueError:
        raise _unavailable() from None
    key = None
    if use_cache:
        key = build_scoped_cache_key(
            "sql-result",
            tenant_id=bound.tenant_id,
            policy_hash=bound.policy_hash,
            catalog_hash=bound.catalog_hash,
            data_watermark=watermark,
            query_fingerprint=bound.fingerprint,
            row_cap=bound.row_cap,
            warehouse_revision=revision,
        )
        cached = _RESULT_CACHE.get(key)
        if cached is not None:
            return cached, key, True
    if monotonic() >= deadline:
        raise _timeout()
    cursor = connection.execute(bound.sql, bound.params)
    names = [item[0] for item in cursor.description]
    if tuple(names) != (*bound.dimensions, *bound.metric_ids):
        raise ContractError("execution_failed", _STAGE, "Unexpected warehouse result columns.")
    rows = [
        {
            name: None
            if value is None
            else (
                format(Decimal(str(value)), ".6f" if bound.units[name] == "ratio" else ".2f")
                if name in bound.units
                else str(value)
            )
            for name, value in zip(names, raw_row, strict=True)
        }
        for raw_row in cursor.fetchall()
    ]
    return (
        {
            "columns": [
                {
                    "key": name,
                    "type": "decimal" if name in bound.units else "string",
                    "unit": bound.units.get(name),
                }
                for name in names
            ],
            "rows": rows,
            "row_count": len(rows),
            "truncated": len(rows) == bound.row_cap
            and (bound._plan.top_k is None or bound._plan.top_k > bound.row_cap),
            "data_watermark": watermark,
            "data_start": calendar.get("data_start"),
            "last_closed_month": calendar.get("last_closed_month"),
        },
        key,
        False,
    )


def _timeout() -> ContractError:
    return ContractError(
        "execution_timeout",
        _STAGE,
        "Database query timed out.",
        retryable=True,
        final_status="temporarily_unavailable",
    )


def _unavailable() -> ContractError:
    return ContractError(
        "database_unavailable",
        _STAGE,
        "Database is temporarily unavailable.",
        retryable=True,
        final_status="temporarily_unavailable",
    )
