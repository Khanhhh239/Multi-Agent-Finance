"""Safe, structured errors and exact-key boundary validation."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from typing import Any

FINAL_STATUSES = {
    "ready",
    "needs_clarification",
    "unsupported",
    "forbidden",
    "no_data",
    "temporarily_unavailable",
    "error",
}

_SQL_PATTERN = re.compile(
    r"\b(?:SELECT|WITH|INSERT|UPDATE|DELETE|DROP)\b[\s\S]*",
    flags=re.IGNORECASE,
)
_TRACEBACK_PATTERN = re.compile(
    r"Traceback\s*\(most recent call last\)[\s\S]*",
    flags=re.IGNORECASE,
)
_CREDENTIAL_PATTERN = re.compile(
    r"\b(?:password|secret|token|api_key)\b\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;}\]]+)",
    flags=re.IGNORECASE,
)
_FORBIDDEN_DETAIL_KEYS = {
    "sql",
    "raw_sql",
    "stack_trace",
    "traceback",
    "credentials",
    "password",
    "rows",
    "raw_rows",
}


def _sanitize_message(msg: str) -> str:
    """Remove SQL, tracebacks, and credential values from a public message."""

    if not isinstance(msg, str):
        return "[REDACTED]"
    sanitized = _CREDENTIAL_PATTERN.sub("[REDACTED]", msg)
    sanitized = _TRACEBACK_PATTERN.sub("[REDACTED]", sanitized)
    return _SQL_PATTERN.sub("[REDACTED]", sanitized)


def _sanitize_details(details: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep, sanitized copy of safe public error details."""

    clean: dict[str, Any] = {}
    for key, value in details.items():
        public_key = str(key)
        if public_key.lower() in _FORBIDDEN_DETAIL_KEYS:
            continue
        clean[public_key] = _sanitize_detail_value(value)
    return clean


def _sanitize_detail_value(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_message(value)
    if isinstance(value, Mapping):
        return _sanitize_details(value)
    if isinstance(value, list):
        return [_sanitize_detail_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_detail_value(item) for item in value)
    return copy.deepcopy(value)


class ContractError(Exception):
    """Structured public failure conforming to the common error contract."""

    _sanitize_message = staticmethod(_sanitize_message)
    _sanitize_details = staticmethod(_sanitize_details)

    def __init__(
        self,
        code: str,
        stage: str,
        message: str,
        retryable: bool = False,
        details: Mapping[str, Any] | None = None,
        final_status: str = "error",
    ) -> None:
        sanitized_message = self._sanitize_message(message)
        super().__init__(sanitized_message)
        self.code = code
        self.stage = stage
        self.message = sanitized_message
        self.retryable = bool(retryable)
        self.details = self._sanitize_details(details or {})
        self.final_status = final_status if final_status in FINAL_STATUSES else "error"

    def to_dict(self) -> dict[str, Any]:
        """Return an isolated public representation of the error."""

        return {
            "code": self.code,
            "stage": self.stage,
            "message": self.message,
            "retryable": self.retryable,
            "details": copy.deepcopy(self.details),
        }


def enforce_exact_keys(
    obj: dict[str, Any],
    required_keys: AbstractSet[str],
    optional_keys: AbstractSet[str] | None = None,
    stage: str = "boundary",
) -> None:
    """Reject non-object, missing-field, and unknown-field boundary inputs."""

    if not isinstance(obj, dict):
        raise ContractError(
            "invalid_request",
            stage,
            "Input payload must be a JSON object.",
        )

    required = set(required_keys)
    allowed = required | set(optional_keys or ())
    actual = set(obj)
    unknown = sorted(actual - allowed)
    missing = sorted(required - actual)
    if unknown:
        raise ContractError(
            "invalid_request",
            stage,
            "Unknown fields rejected at boundary.",
            details={"unknown_fields": unknown},
        )
    if missing:
        raise ContractError(
            "invalid_request",
            stage,
            "Missing required fields at boundary.",
            details={"missing_fields": missing},
        )
