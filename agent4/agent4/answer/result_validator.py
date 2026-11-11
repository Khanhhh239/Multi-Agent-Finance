"""Validate warehouse result schemas, values and coverage before rendering."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from math import isfinite

from agent4.core.catalog import MetricCatalog
from agent4.core.errors import ContractError
from agent4.metric_selection.llm_selector import INJECTION_PATTERNS
from agent4.planning.validator import ValidatedPlan

_DECIMAL = re.compile(r"-?\d+(?:\.\d+)?", re.ASCII)
_PHYSICAL = re.compile(
    r"\b(?:v_(?:mgmt|tax|gl)|gl_wide|company_info|information_schema|duckdb_\w+|"
    r"ar_invoice|ap_bill|journal_entries|read_(?:csv|parquet)\w*)\b|"
    r"\b(?:select|insert|update|delete|create|drop|alter|attach|copy|pragma)\b.*"
    r"\b(?:from|into|table|database|to)\b",
    re.IGNORECASE,
)


def safe_display_text(value: str) -> str:
    normalized = "".join(
        char for char in unicodedata.normalize("NFKC", value) if unicodedata.category(char) != "Cf"
    )
    normalized = " ".join(normalized.split())
    if INJECTION_PATTERNS.search(normalized) or _PHYSICAL.search(normalized):
        return "[REDACTED]"
    return value


def _invalid() -> ContractError:
    return ContractError(
        "invalid_result", "result_validation", "Warehouse result failed validation."
    )


def validate_result(
    execution_result: dict,
    plan: ValidatedPlan,
    catalog: MetricCatalog,
) -> dict:
    if type(plan) is not ValidatedPlan or plan.catalog_hash != catalog.get_catalog_hash():
        raise _invalid()
    if not isinstance(execution_result, dict):
        raise _invalid()
    result = execution_result
    cols, rows = result.get("columns"), result.get("rows")
    count, truncated, elapsed = (
        result.get("row_count"),
        result.get("truncated"),
        result.get("execution_ms"),
    )
    if (
        not isinstance(cols, list)
        or not isinstance(rows, list)
        or type(count) is not int
        or count != len(rows)
        or count > plan.row_cap
        or (plan.top_k is not None and count > plan.top_k)
        or type(truncated) is not bool
        or type(elapsed) not in (int, float)
        or elapsed < 0
        or not isfinite(elapsed)
    ):
        raise _invalid()
    caps = {mid: catalog.get_capability(mid) for mid in plan.metric_ids}
    expected = [{"key": dim, "type": "string", "unit": None} for dim in plan.dimensions] + [
        {"key": mid, "type": "decimal", "unit": cap["unit"]} for mid, cap in caps.items()
    ]
    if cols != expected:
        raise _invalid()
    keys = {*plan.dimensions, *plan.metric_ids}
    clean_rows = []
    warnings = []
    for row in rows:
        if not isinstance(row, dict) or row.keys() != keys:
            raise _invalid()
        clean_row = {}
        for key, value in row.items():
            if key in caps:
                if value is None and caps[key]["kind"] == "ratio":
                    if "ratio_undefined" not in warnings:
                        warnings.append("ratio_undefined")
                elif not isinstance(value, str) or not _DECIMAL.fullmatch(value):
                    raise _invalid()
                clean_row[key] = value
            else:
                if value is not None and not isinstance(value, str):
                    raise _invalid()
                clean_row[key] = safe_display_text(value) if value is not None else None
        clean_rows.append(clean_row)

    try:
        watermark = date.fromisoformat(result["data_watermark"])
        start = date.fromisoformat(result["data_start"]) if result.get("data_start") else None
        closed = result.get("last_closed_month")
        if closed is not None:
            date.fromisoformat(closed + "-01")
    except (KeyError, TypeError, ValueError):
        raise _invalid() from None
    time = plan.time
    if time.mode == "range":
        outside = time.start > watermark or (start is not None and time.end < start)
        partial = time.end > watermark or (closed is not None and time.end.isoformat()[:7] > closed)
    else:
        outside = start is not None and time.as_of < start
        partial = time.as_of > watermark
    status = "valid"
    if outside or not clean_rows:
        warnings.append("no_data_for_period" if outside else "no_data_found")
        clean_rows = []
        status = "no_data"
    elif partial:
        warnings.append("partial_data_watermark")
        status = "partial"
    return {
        "status": status,
        "warnings": warnings,
        "result": {
            "columns": expected,
            "rows": clean_rows,
            "row_count": len(clean_rows),
            "truncated": truncated and bool(clean_rows),
            "data_watermark": watermark.isoformat(),
            "execution_ms": elapsed,
        },
        "checks": dict.fromkeys(
            (
                "schema_valid",
                "types_valid",
                "columns_expected",
                "row_count_valid",
                "semantic_constraints_valid",
            ),
            True,
        ),
    }
