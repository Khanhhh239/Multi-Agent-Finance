"""Fail-closed validation and sealing for query.plan-validation.v1."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import InitVar, dataclass, field
from datetime import date
from typing import Any, Literal

from agent4.core.catalog import MetricCatalog
from agent4.core.errors import ContractError, enforce_exact_keys

from .planner import ALLOWED_DIMENSIONS, ALLOWED_FILTER_VALUES, PARTNER_CODE_PATTERN

_STAGE = "semantic_plan_validation"
_FIELDS = {
    "plan_version",
    "status",
    "metric_ids",
    "time",
    "dimensions",
    "filters",
    "view",
    "operation",
    "sort",
    "top_k",
    "comparison",
    "question_for_user",
    "unresolved_slots",
    "reason_code",
}
_SLOTS = {"metric", "time", "dimensions", "filters", "view", "sort", "top_k"}
_OPERATIONS = ("aggregate", "timeseries", "breakdown", "ranking")
_GRAINS = ("month", "quarter", "year")
_VIEWS = ("mgmt", "tax")
_DIMENSION_ALIASES = {"branch_code": "branch", "department_code": "department"}
_PARTNER_SIDES = {"customer", "vendor"}
_ID = re.compile(r"[a-z][a-z0-9_]{0,63}")
_PARTNER_CODE = re.compile(PARTNER_CODE_PATTERN)
_UNSAFE_TEXT = re.compile(
    r"\b(?:select|insert|delete|update|drop|alter|attach|detach|pragma|create|replace|"
    r"truncate|grant|revoke|export|import|install|load|merge|copy|"
    r"read_[a-z_]+|duckdb_[a-z_]+|information_schema|"
    r"gl_wide|gl_journal|gl_entry|ar_invoice(?:_line)?|ar_receipt|ar_adjustment|"
    r"ap_bill|ap_payment|dim_[a-z_]+|v_(?:gl|mgmt|tax)|period_close|inventory_txn|"
    r"fixed_asset|loan_schedule|service_contract|company_info|ground_truth)\b|"
    r"\b(?:from|join|table|bảng)\s+(?:budget|loan|payroll)\b|"
    r"\b(?:with\s+\w+\s+as\s*\(|values\s*\(|call\s+\w+\s*\(|union\s+(?:all|distinct)\b)|"
    r"\bor\s+\d+\s*=\s*\d+|;|--|/\*",
    re.IGNORECASE,
)
_RESERVED_IDENTIFIERS = {"from", "join", "budget", "loan", "payroll", "ground_truth"}
_SEAL = object()


@dataclass(frozen=True, slots=True)
class ValidatedTime:
    mode: Literal["range", "as_of", "none"]
    start: date | None
    end: date | None
    as_of: date | None
    grain: str | None


@dataclass(frozen=True, slots=True)
class ValidatedFilter:
    field: str
    op: Literal["=", "IN"]
    value: str | tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ValidatedSort:
    metric_id: str
    direction: Literal["asc", "desc"]


@dataclass(frozen=True, slots=True)
class PlanClarification:
    question_for_user: str
    unresolved_slots: tuple[str, ...]
    status: Literal["needs_clarification"] = field(default="needs_clarification", init=False)


@dataclass(frozen=True, slots=True)
class ValidatedPlan:
    """Executable plan type for the rebuilt core. Only the gate can construct it."""

    _seal: InitVar[object]
    metric_ids: tuple[str, ...]
    time: ValidatedTime
    dimensions: tuple[str, ...]
    filters: tuple[ValidatedFilter, ...]
    view: Literal["mgmt", "tax"]
    operation: str
    sort: ValidatedSort | None
    top_k: int | None
    row_cap: int
    tenant_id: str
    catalog_hash: str
    policy_hash: str
    applied_defaults: tuple[str, ...]
    comparison: None = field(default=None, init=False)
    contract_version: Literal["validated-plan.v1"] = field(default="validated-plan.v1", init=False)
    status: Literal["validated"] = field(default="validated", init=False)

    def __post_init__(self, _seal: object) -> None:
        if _seal is not _SEAL:
            raise TypeError("Use validate_semantic_plan_draft to seal a plan.")


def _invalid(message: str, *, unsupported: bool = False) -> ContractError:
    return ContractError(
        "invalid_request",
        _STAGE,
        message,
        final_status="unsupported" if unsupported else "error",
    )


def _unsupported(code: str, message: str) -> ContractError:
    return ContractError(code, _STAGE, message, final_status="unsupported")


def _forbidden() -> ContractError:
    return ContractError(
        "forbidden_metric",
        _STAGE,
        "Plan is outside the authorized scope.",
        final_status="forbidden",
    )


def _exact_keys(value: Any, keys: set[str]) -> None:
    if isinstance(value, dict) and any(not isinstance(key, str) for key in value):
        raise _invalid("Plan object keys must be strings.")
    try:
        enforce_exact_keys(value, keys, stage=_STAGE)
    except ContractError:
        raise _invalid("Plan object fields do not match the contract.") from None


def _safe_text(value: str, *, identifier: bool = False) -> None:
    normalized = unicodedata.normalize("NFKC", value)
    if _UNSAFE_TEXT.search(normalized) or (
        identifier and normalized.casefold() in _RESERVED_IDENTIFIERS
    ):
        raise _invalid("Plan contains prohibited content.")


def _identifiers(value: Any, max_items: int) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or len(value) > max_items
        or any(not isinstance(item, str) or not _ID.fullmatch(item) for item in value)
        or len(value) != len(set(value))
    ):
        raise _invalid("Invalid plan identifier list.")
    for item in value:
        _safe_text(item, identifier=True)
    return tuple(value)


def _iso_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            pass
        else:
            if value == parsed.isoformat():
                return parsed
    raise _invalid("Plan dates must be valid YYYY-MM-DD values.")


def _time(value: Any, max_days: int) -> ValidatedTime:
    _exact_keys(value, {"mode", "start", "end", "as_of", "grain"})
    mode, grain = value["mode"], value["grain"]
    start, end, as_of = (_iso_date(value[key]) for key in ("start", "end", "as_of"))
    if mode == "range":
        if start is None or end is None or as_of is not None or grain not in _GRAINS:
            raise _invalid("A range requires start, end and a supported grain.", unsupported=True)
        if end < start:
            raise _invalid("Plan range end precedes its start.")
        if (end - start).days > max_days:
            raise _invalid("Plan date range exceeds the server limit.", unsupported=True)
    elif mode == "as_of":
        if as_of is None or any(part is not None for part in (start, end, grain)):
            raise _invalid("A snapshot requires only an as-of date.", unsupported=True)
    elif mode != "none" or any(part is not None for part in (start, end, as_of, grain)):
        raise _invalid("Invalid plan time mode.", unsupported=True)
    return ValidatedTime(mode, start, end, as_of, grain)


def _filters(raw: Any) -> tuple[ValidatedFilter, ...]:
    if not isinstance(raw, list) or len(raw) > 20:
        raise _invalid("Invalid plan filter list.")
    filters = []
    for item in raw:
        _exact_keys(item, {"field", "op", "value"})
        name, op, value = item["field"], item["op"], item["value"]
        if not isinstance(name, str):
            raise _invalid("Invalid plan filter field.")
        _safe_text(name, identifier=True)
        if name not in ALLOWED_FILTER_VALUES and name != "partner_code":
            raise _invalid("Filter field is outside the allowlist.", unsupported=True)
        if op == "=" and isinstance(value, str):
            values = (value,)
        elif op == "IN" and isinstance(value, list) and 1 <= len(value) <= 100:
            values = tuple(value)
        else:
            raise _invalid("Filter operator and value shape do not match.", unsupported=True)
        for code in values:
            if not isinstance(code, str) or len(code) > 64:
                raise _invalid("Invalid filter value.")
            _safe_text(code, identifier=True)
            if name == "partner_code":
                allowed = _PARTNER_CODE.fullmatch(code)
            else:
                allowed = code in ALLOWED_FILTER_VALUES[name]
            if not allowed:
                raise _invalid("Filter value is outside the allowlist.", unsupported=True)
        filters.append(ValidatedFilter(name, op, value if op == "=" else values))
    return tuple(filters)


def _sort(raw: Any, ids: tuple[str, ...]) -> ValidatedSort | None:
    if raw is None:
        return None
    _exact_keys(raw, {"metric_id", "direction"})
    if raw["metric_id"] not in ids or raw["direction"] not in ("asc", "desc"):
        raise _invalid("Sort must use a plan metric and an allowed direction.")
    return ValidatedSort(raw["metric_id"], raw["direction"])


def _auth_scope(auth: dict[str, Any], view: str | None, ids: tuple[str, ...]) -> None:
    if (
        not isinstance(auth, dict)
        or auth.get("contract_version") != "auth-context.v1"
        or any(
            not isinstance(auth.get(key), str) or not auth[key].strip()
            for key in ("user_id", "tenant_id", "policy_hash")
        )
        or any(
            not isinstance(auth.get(key), list)
            or not auth[key]
            or any(not isinstance(item, str) or not item.strip() for item in auth[key])
            for key in ("roles", "allowed_views")
        )
        or "allowed_metrics" not in auth
    ):
        raise _forbidden()
    allowed = auth["allowed_metrics"]
    if allowed is not None and (
        not isinstance(allowed, list)
        or any(not isinstance(item, str) or not item.strip() for item in allowed)
        or any(metric not in allowed for metric in ids)
    ):
        raise _forbidden()
    if view is not None and view not in auth["allowed_views"]:
        raise _forbidden()


def _capabilities(
    ids: tuple[str, ...], selected: dict[str, Any], catalog: MetricCatalog, catalog_hash: str
) -> list[dict[str, Any]]:
    if (
        not isinstance(selected, dict)
        or selected.get("status") not in ("validated", "needs_clarification")
        or selected.get("catalog_hash") != catalog_hash
    ):
        raise _invalid("Metric selection is invalid or belongs to a different catalog.")
    selected_ids = _identifiers(selected.get("metric_ids"), 100)
    if bool(selected_ids) != (selected["status"] == "validated"):
        raise _invalid("Metric selection status and metric IDs do not match.")
    if not set(ids).issubset(selected_ids):
        raise _unsupported("metric_outside_candidates", "Plan metric was not validated upstream.")
    capabilities = []
    for metric_id in ids:
        if not catalog.contains(metric_id):
            raise _unsupported("unknown_metric", "Plan metric is absent from the current catalog.")
        cap = catalog.get_capability(metric_id)
        if cap["status"] != "approved":
            raise _unsupported("unsupported_metric", "Plan metric is not approved.")
        if cap["verified_handler"] is not True:
            raise _unsupported("unsupported_data_source", "Plan metric has no verified handler.")
        capabilities.append(cap)
    return capabilities


def _validate_compatibility(
    capabilities: list[dict[str, Any]],
    view: str,
    operation: str,
    time: ValidatedTime,
    dimensions: tuple[str, ...],
    filters: tuple[ValidatedFilter, ...],
) -> None:
    periods = {cap["period_type"] for cap in capabilities}
    if len(periods) != 1:
        raise _unsupported("incompatible_metrics", "Flow and snapshot metrics cannot share a plan.")
    expected_mode = {"flow": "range", "snapshot": "as_of"}.get(periods.pop())
    if time.mode != expected_mode:
        raise _invalid("Time mode does not match the selected metric.", unsupported=True)

    common_dimensions = set(ALLOWED_DIMENSIONS) | _PARTNER_SIDES
    alternatives = ("ranking", "rank") if operation == "ranking" else (operation,)
    for cap in capabilities:
        if view not in cap["supported_views"]:
            raise _unsupported("unsupported_view", "Plan view is incompatible with a metric.")
        if not any(op in cap["supported_operations"] for op in alternatives):
            raise _unsupported(
                "unsupported_metric", "Plan operation is incompatible with a metric."
            )
        supported = set(cap["supported_dimensions"])
        for name, alias in _DIMENSION_ALIASES.items():
            if alias in supported:
                supported.add(name)
        common_dimensions.intersection_update(supported)

    for dimension in dimensions:
        if dimension in common_dimensions:
            continue
        if dimension == "partner_code" and len(_PARTNER_SIDES & common_dimensions) == 1:
            continue
        raise _unsupported("unsupported_metric", "Plan dimension is incompatible with a metric.")
    for item in filters:
        if item.field in common_dimensions:
            continue
        if item.field == "partner_code":
            codes = (item.value,) if isinstance(item.value, str) else item.value
            required = {"vendor" if code.startswith("NCC-") else "customer" for code in codes}
            if required <= common_dimensions:
                continue
        raise _unsupported("unsupported_metric", "Plan filter is incompatible with a metric.")


def validate_semantic_plan_draft(
    plan_draft: dict[str, Any],
    validated_metrics: dict[str, Any],
    catalog: MetricCatalog,
    auth_context: dict[str, Any],
    *,
    max_days: int = 750,
    max_top_k: int = 100,
    row_cap: int = 1000,
) -> ValidatedPlan | PlanClarification:
    """Validate an untrusted draft using only server-owned catalog, auth and limits."""
    if any(
        type(value) is not int or not 1 <= value <= ceiling
        for value, ceiling in ((max_days, 750), (max_top_k, 100), (row_cap, 1000))
    ):
        raise _invalid("Invalid server plan limits.")
    _exact_keys(plan_draft, _FIELDS)
    status = plan_draft["status"]
    if plan_draft["plan_version"] != "1.0" or status not in (
        "ready",
        "needs_clarification",
        "unsupported",
    ):
        raise _invalid("Invalid plan version or status.")
    if plan_draft["comparison"] is not None:
        raise _invalid("Plan comparisons are outside this contract.", unsupported=True)

    ids = _identifiers(plan_draft["metric_ids"], 100)
    dimensions = _identifiers(plan_draft["dimensions"], len(ALLOWED_DIMENSIONS))
    if not set(dimensions) <= ALLOWED_DIMENSIONS:
        raise _unsupported("unsupported_metric", "Plan dimension is outside the allowlist.")
    unresolved = _identifiers(plan_draft["unresolved_slots"], len(_SLOTS))
    if not set(unresolved) <= _SLOTS:
        raise _invalid("Invalid unresolved plan slot.")
    question, reason = plan_draft["question_for_user"], plan_draft["reason_code"]
    if question is not None:
        if not isinstance(question, str) or not question.strip() or len(question) > 500:
            raise _invalid("Invalid clarification question.")
        _safe_text(question)
    if reason is not None:
        if not isinstance(reason, str) or not _ID.fullmatch(reason):
            raise _invalid("Invalid plan reason code.")
        _safe_text(reason, identifier=True)

    view, operation = plan_draft["view"], plan_draft["operation"]
    if view is not None and view not in _VIEWS:
        raise _invalid("Plan view is outside the allowlist.")
    if operation is not None and operation not in _OPERATIONS:
        raise _invalid("Plan operation is outside the allowlist.")
    top_k = plan_draft["top_k"]
    if top_k is not None and (type(top_k) is not int or not 1 <= top_k <= max_top_k):
        raise _invalid("Plan top-k is outside the server limit.")
    time = _time(plan_draft["time"], max_days)
    filters = _filters(plan_draft["filters"])
    sort = _sort(plan_draft["sort"], ids)

    _auth_scope(auth_context, view, ids)
    catalog_hash = catalog.get_catalog_hash()
    capabilities = _capabilities(ids, validated_metrics, catalog, catalog_hash)

    if status == "needs_clarification":
        if question is None or not unresolved or reason is not None:
            raise _invalid("Clarification requires a question and unresolved slots.")
        return PlanClarification(question, unresolved)
    if status == "unsupported":
        if reason is None or question is not None or unresolved:
            raise _invalid("Unsupported plan requires only a reason code.")
        raise _unsupported("unsupported_metric", "Planner could not produce a supported plan.")

    if not ids or question is not None or unresolved or reason is not None or view is None:
        raise _invalid("Ready plan is missing required slots or contains unresolved fields.")
    if time.mode == "none":
        raise _invalid("A ready plan requires a time scope.", unsupported=True)
    defaults = ("operation=aggregate",) if operation is None else ()
    operation = operation or "aggregate"
    if operation == "ranking" and (not dimensions or sort is None):
        raise _invalid("Ranking requires a grouping dimension and a sort.")
    if top_k is not None and sort is None:
        raise _invalid("A top-k limit requires a sort.")
    if operation == "timeseries" and (time.mode != "range" or time.grain not in dimensions):
        raise _invalid("Time series requires a range and its grouping grain.", unsupported=True)
    _validate_compatibility(capabilities, view, operation, time, dimensions, filters)

    return ValidatedPlan(
        _seal=_SEAL,
        metric_ids=ids,
        time=time,
        dimensions=dimensions,
        filters=filters,
        view=view,
        operation=operation,
        sort=sort,
        top_k=top_k,
        row_cap=row_cap,
        tenant_id=auth_context["tenant_id"],
        catalog_hash=catalog_hash,
        policy_hash=auth_context["policy_hash"],
        applied_defaults=defaults,
    )
