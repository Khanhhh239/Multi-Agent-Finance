"""Shared pytest fixtures for contract, security, and benchmark test suites."""

from __future__ import annotations

import json
from typing import Any, Generator

import duckdb
import pytest

from tests.contract_harness import (
    DB_PATH,
    GROUND_TRUTH_PATH,
    EmbeddingProvider,
    MetricCatalog,
    build_auth_context,
)


@pytest.fixture(scope="session")
def db_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Read-only connection to data/cfo_warehouse.duckdb."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        yield con
    finally:
        con.close()


@pytest.fixture(scope="session")
def ground_truth_events() -> list[dict[str, Any]]:
    """Loads the 20 ground truth scenarios from data/cfo_warehouse_ground_truth.json."""
    with open(GROUND_TRUTH_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture()
def catalog() -> MetricCatalog:
    """Approved MetricCatalog snapshot."""
    return MetricCatalog()


@pytest.fixture()
def embedding_provider() -> EmbeddingProvider:
    """Deterministic multilingual embedding provider."""
    return EmbeddingProvider()


@pytest.fixture()
def analyst_auth() -> dict[str, Any]:
    """AuthContext for finance_analyst with access only to 'mgmt' view."""
    return build_auth_context(
        idp_claims={"user_id": "user-analyst-1", "tenant_id": "minh-phat", "roles": ["finance_analyst"]},
        server_policy={"allowed_views": ["mgmt"], "policy_version": "2026.11"},
    )


@pytest.fixture()
def cfo_auth() -> dict[str, Any]:
    """AuthContext for CFO/controller with access to 'mgmt', 'tax', and 'gl' views."""
    return build_auth_context(
        idp_claims={"user_id": "user-cfo-1", "tenant_id": "minh-phat", "roles": ["cfo", "controller"]},
        server_policy={"allowed_views": ["mgmt", "tax", "gl"], "policy_version": "2026.11"},
    )


@pytest.fixture()
def runtime_context(analyst_auth: dict[str, Any], catalog: MetricCatalog) -> dict[str, Any]:
    """RuntimeContext adhering to Section 1.2 of contracts.md."""
    return {
        "request_id": "req-123",
        "trace_id": "trace-123",
        "tenant_id": analyst_auth["tenant_id"],
        "user_id": analyst_auth["user_id"],
        "roles": analyst_auth["roles"],
        "allowed_views": analyst_auth["allowed_views"],
        "locale": "vi-VN",
        "timezone": "Asia/Ho_Chi_Minh",
        "catalog_hash": catalog.get_catalog_hash(),
        "policy_hash": analyst_auth["policy_hash"],
    }
