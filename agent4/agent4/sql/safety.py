"""Check compiled statements and authorize execution for a tenant-owned warehouse."""

from __future__ import annotations

from dataclasses import InitVar, dataclass
from pathlib import Path
from typing import Any, Literal, TypedDict

from agent4.core.catalog import MetricCatalog
from agent4.core.errors import ContractError

from .compiler import BoundQuery, compile_sql

_SEAL = object()
_CHECKS = (
    "read_only",
    "single_statement",
    "approved_relations",
    "approved_columns",
    "parameterized",
    "row_cap_present",
    "tenant_scope_present",
)


@dataclass(frozen=True, slots=True)
class SafeBoundQuery:
    """Execution capability created by the safety gate."""

    query: BoundQuery
    _seal: InitVar[object]
    warehouse_path: Path | None = None

    def __post_init__(self, _seal: object) -> None:
        if _seal is not _SEAL:
            raise TypeError("Use validate_sql_safety to authorize execution.")


class SafetyResult(TypedDict):
    status: Literal["allowed"]
    query_fingerprint: str
    checks: dict[str, bool]
    safe_bound_query: SafeBoundQuery


def validate_sql_safety(
    bound_query: BoundQuery,
    catalog: MetricCatalog,
    runtime_context: dict[str, Any],
    *,
    warehouse_tenant_id: str | None = None,
    warehouse_path: Path | None = None,
) -> SafetyResult:
    """Verify the exact allowlisted statement for the sealed plan and current scope.

    The runtime and warehouse tenant come from server configuration. The
    execution layer must open the warehouse assigned to that tenant.
    """
    checks = dict.fromkeys(_CHECKS, False)
    if type(bound_query) is not BoundQuery:
        raise _rejected(checks)

    bound = bound_query
    plan = bound._plan
    valid_cap = type(bound.row_cap) is int and 1 <= bound.row_cap <= 1000
    try:
        expected = compile_sql(plan, catalog, row_cap=bound.row_cap if valid_cap else 1000)
    except ContractError:
        raise _rejected(checks) from None

    # Matching the complete template also proves the projection and source.
    # No SQL from a caller is parsed, transformed or passed to DuckDB here.
    template_matches = type(bound.sql) is str and bound.sql == expected.sql
    checks["read_only"] = template_matches
    checks["single_statement"] = type(bound.sql) is str and ";" not in bound.sql
    checks["approved_relations"] = template_matches and bound.source == expected.source
    checks["approved_columns"] = (
        template_matches
        and bound.metric_ids == expected.metric_ids
        and bound.dimensions == expected.dimensions
        and bound.units == expected.units
    )
    params_match = (
        type(bound.params) is tuple
        and all(type(value) in (str, int) for value in bound.params)
        and bound.params == expected.params
    )
    checks["parameterized"] = (
        template_matches
        and params_match
        and bound.sql.count("?") == len(bound.params)
        and bound.fingerprint == expected.fingerprint
    )
    checks["row_cap_present"] = (
        type(bound.sql) is str
        and bound.sql.endswith(" LIMIT ?")
        and valid_cap
        and bound.row_cap == expected.row_cap
        and type(bound.params) is tuple
        and bool(bound.params)
        and type(bound.params[-1]) is int
        and bound.params[-1] == bound.row_cap
    )
    checks["tenant_scope_present"] = _scope_matches(
        bound, expected, runtime_context, warehouse_tenant_id
    )
    if not all(checks.values()) or bound.contract_version != "bound-query.v1":
        raise _rejected(checks)
    return {
        "status": "allowed",
        "query_fingerprint": expected.fingerprint,
        "checks": checks,
        "safe_bound_query": SafeBoundQuery(
            expected,
            _seal=_SEAL,
            warehouse_path=warehouse_path.resolve() if warehouse_path is not None else None,
        ),
    }


def _scope_matches(
    bound: BoundQuery, expected: BoundQuery, runtime: dict[str, Any], warehouse_tenant: str | None
) -> bool:
    return (
        isinstance(runtime, dict)
        and isinstance(runtime.get("allowed_views"), list)
        and expected._plan.view in runtime["allowed_views"]
        and bound.tenant_id == expected.tenant_id == runtime.get("tenant_id") == warehouse_tenant
        and bound.policy_hash == expected.policy_hash == runtime.get("policy_hash")
        and bound.catalog_hash == expected.catalog_hash == runtime.get("catalog_hash")
    )


def _rejected(checks: dict[str, bool]) -> ContractError:
    return ContractError(
        "unsafe_sql_rejected",
        "sql_safety",
        "The query could not be authorized for execution.",
        details={"checks": checks},
    )
