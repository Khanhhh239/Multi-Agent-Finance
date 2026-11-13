"""Compile sealed semantic plans using the verified warehouse catalog bindings."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

from agent4.core.catalog import (
    CANONICAL_METRIC_DEFINITIONS,
    DEFAULT_METRICS_DEFINITIONS,
    MetricCatalog,
)
from agent4.core.errors import ContractError
from agent4.planning.validator import ValidatedPlan

_STAGE = "sql_compiler"
_VIEW_RELATIONS = {"mgmt": "v_mgmt", "tax": "v_tax", "gl": "v_gl"}
_LEDGER_DIMENSIONS = {
    "month": "year_month",
    "quarter": "CAST(year_no AS VARCHAR) || '-Q' || CAST(quarter_no AS VARCHAR)",
    "year": "CAST(year_no AS VARCHAR)",
    "branch_code": "branch_code",
    "product_line": "product_line",
    "department_code": "department_code",
    "cost_category": "cost_category",
    "partner_code": "partner_code",
    "segment": "segment",
}
_BUDGET_DIMENSIONS = {
    "month": "PRINTF('%04d-%02d', year_no, month_no)",
    "year": _LEDGER_DIMENSIONS["year"],
    "branch_code": "branch_code",
    "cost_category": "cost_category",
}
_PERIOD_DIMENSIONS = {"month", "quarter", "year"}
_VERIFIED_BINDINGS = MappingProxyType(
    {
        metric["metric_id"]: (metric["base_relation"], metric["sql_expr"])
        for metric in (
            *DEFAULT_METRICS_DEFINITIONS,
            *CANONICAL_METRIC_DEFINITIONS,
        )
        if metric["status"] == "approved" and metric["verified_handler"] is True
    }
)
_DIRECTIONS = {"asc": "ASC", "desc": "DESC"}


@dataclass(frozen=True, slots=True)
class BoundQuery:
    """Internal SQL and the sealed plan needed to verify its provenance."""

    sql: str
    params: tuple[str | int, ...]
    metric_ids: tuple[str, ...]
    dimensions: tuple[str, ...]
    units: Mapping[str, str]
    row_cap: int
    fingerprint: str
    source: str
    tenant_id: str
    catalog_hash: str
    policy_hash: str
    _plan: ValidatedPlan = field(repr=False, compare=False)
    contract_version: Literal["bound-query.v1"] = field(default="bound-query.v1", init=False)


def compile_sql(
    validated_plan: ValidatedPlan, catalog: MetricCatalog, row_cap: int = 1000
) -> BoundQuery:
    """Bind values from a validated plan without interpolating them into SQL."""
    if type(validated_plan) is not ValidatedPlan:
        raise ContractError("invalid_request", _STAGE, "A validated plan is required.")
    if validated_plan.catalog_hash != catalog.get_catalog_hash():
        raise ContractError("invalid_request", _STAGE, "The plan catalog is out of date.")
    if type(row_cap) is not int or not 1 <= row_cap <= 1000:
        raise ContractError("invalid_request", _STAGE, "Invalid compiler row limit.")

    plan = validated_plan
    expressions = []
    units = {}
    sources = set()
    for metric_id in plan.metric_ids:
        definition = catalog.get(metric_id)
        binding = _VERIFIED_BINDINGS.get(metric_id)
        if (
            binding is None
            or definition is None
            or definition["status"] != "approved"
            or definition.get("verified_handler") is not True
            or (definition.get("base_relation"), definition.get("sql_expr")) != binding
        ):
            raise _unsupported("Metric has no verified warehouse binding.")
        relation, expression = binding
        sources.add(relation)
        expressions.append(f'{expression} AS "{metric_id}"')
        units[metric_id] = definition["unit"]

    if len(sources) != 1:
        raise _unsupported("Metrics require different warehouse sources.")
    is_budget = sources == {"budget"}
    relation = "budget" if is_budget else _VIEW_RELATIONS[plan.view]
    if plan.time.mode == "as_of" and _PERIOD_DIMENSIONS.intersection(plan.dimensions):
        raise _unsupported("Snapshot time series require cumulative balances at each period end.")
    columns = _BUDGET_DIMENSIONS if is_budget else _LEDGER_DIMENSIONS
    predicates, params = _time_predicates(plan, is_budget)
    for item in plan.filters:
        column = columns.get(item.field)
        if column is None or item.field in _PERIOD_DIMENSIONS:
            raise _unsupported("Filter has no binding on this warehouse source.")
        if isinstance(item.value, str):
            predicates.append(f"{column} = ?")
            params.append(item.value)
        else:
            placeholders = ", ".join("?" for _ in item.value)
            predicates.append(f"{column} IN ({placeholders})")
            params.extend(item.value)

    try:
        grouping = [columns[dimension] for dimension in plan.dimensions]
    except KeyError:
        raise _unsupported("Dimension has no binding on this warehouse source.") from None
    selections = [
        f'{expression} AS "{dimension}"'
        for expression, dimension in zip(grouping, plan.dimensions, strict=True)
    ]
    sql = (
        f"SELECT {', '.join([*selections, *expressions])} FROM {relation} "
        f"WHERE {' AND '.join(predicates)}"
    )
    if grouping:
        sql += f" GROUP BY {', '.join(grouping)}"
    else:
        sql += " HAVING COUNT(*) > 0"

    ordering = [f'"{dimension}" ASC NULLS LAST' for dimension in plan.dimensions]
    if plan.sort is not None:
        direction = _DIRECTIONS[plan.sort.direction]
        ordering.insert(0, f'"{plan.sort.metric_id}" {direction} NULLS LAST')
    if ordering:
        sql += f" ORDER BY {', '.join(ordering)}"
    sql += " LIMIT ?"
    effective_cap = min(plan.row_cap, row_cap, plan.top_k or row_cap)
    params.append(effective_cap)
    return BoundQuery(
        sql=sql,
        params=tuple(params),
        metric_ids=plan.metric_ids,
        dimensions=plan.dimensions,
        units=MappingProxyType(units),
        row_cap=effective_cap,
        fingerprint=_fingerprint(sql, params),
        source=relation,
        tenant_id=plan.tenant_id,
        catalog_hash=plan.catalog_hash,
        policy_hash=plan.policy_hash,
        _plan=plan,
    )


def _time_predicates(plan: ValidatedPlan, is_budget: bool) -> tuple[list[str], list[str | int]]:
    time = plan.time
    if time.mode == "as_of" and time.as_of is not None and not is_budget:
        return ["posting_date <= CAST(? AS DATE)"], [time.as_of.isoformat()]
    if time.mode != "range" or time.start is None or time.end is None:
        raise _unsupported("Time scope has no binding on this warehouse source.")
    if is_budget:
        return ["(CAST(year_no AS INTEGER) * 100 + month_no) BETWEEN ? AND ?"], [
            time.start.year * 100 + time.start.month,
            time.end.year * 100 + time.end.month,
        ]
    return [
        "posting_date >= CAST(? AS DATE)",
        "posting_date <= CAST(? AS DATE)",
        "NOT is_closing",
        "source_module IS DISTINCT FROM 'OPENING'",
    ], [time.start.isoformat(), time.end.isoformat()]


def _fingerprint(sql: str, params: list[str | int]) -> str:
    payload = json.dumps([sql, params], ensure_ascii=False, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(payload.encode()).hexdigest()}"


def _unsupported(message: str) -> ContractError:
    return ContractError("unsupported_data_source", _STAGE, message, final_status="unsupported")
