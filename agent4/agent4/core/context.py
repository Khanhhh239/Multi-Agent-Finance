"""Query intake and server-sourced authorization/runtime contexts."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

from .errors import ContractError, enforce_exact_keys

SUPPORTED_LOCALES = {"vi-VN", "en-US"}
_INTAKE_KEYS = {"api_version", "question", "locale"}
_INTAKE_OPTIONAL_KEYS = {"session_id", "options"}
_OPTION_KEYS = {
    "include_table",
    "explain_metrics",
    "include_evidence_preview",
    "clarification_mode",
    "use_cache",
}
_AUTH_KEYS = {"user_id", "tenant_id", "roles"}
_POLICY_KEYS = {"allowed_views", "policy_version"}
ROW_SCOPE_FIELDS = {"allowed_branches": "branch_code", "allowed_departments": "department_code"}
_POLICY_OPTIONAL_KEYS = {"allowed_metrics", *ROW_SCOPE_FIELDS}
_SCOPE_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,31}")


def query_intake(
    payload: dict[str, Any],
    max_question_length: int = 500,
) -> dict[str, Any]:
    """Validate and normalize an untrusted ``query.intake.v1`` payload."""

    stage = "query_intake"
    enforce_exact_keys(
        payload,
        required_keys=_INTAKE_KEYS,
        optional_keys=_INTAKE_OPTIONAL_KEYS,
        stage=stage,
    )
    if payload["api_version"] != "v1":
        raise ContractError("invalid_request", stage, "Unsupported api_version.")

    question = payload["question"]
    if not isinstance(question, str) or not question.strip():
        raise ContractError(
            "invalid_request",
            stage,
            "Question must be a non-empty string.",
        )
    if len(question.strip()) > max_question_length:
        raise ContractError(
            "question_too_long",
            stage,
            f"Question exceeds maximum length of {max_question_length} characters.",
        )

    locale = payload["locale"]
    if not isinstance(locale, str) or locale not in SUPPORTED_LOCALES:
        raise ContractError(
            "unsupported_locale",
            stage,
            "Requested locale is not supported.",
            details={"locale": locale},
            final_status="unsupported",
        )

    options_in = payload.get("options")
    if options_in is None:
        options = {"include_table": True, "explain_metrics": True}
    else:
        enforce_exact_keys(
            options_in,
            required_keys=set(),
            optional_keys=_OPTION_KEYS,
            stage=stage,
        )
        for key, value in options_in.items():
            if key == "clarification_mode" and value in ("guided", "strict"):
                continue
            if key == "clarification_mode" or not isinstance(value, bool):
                raise ContractError(
                    "invalid_request",
                    stage,
                    "Query options must be boolean values.",
                    details={"invalid_option": key},
                )
        options = {
            "include_table": options_in.get("include_table", True),
            "explain_metrics": options_in.get("explain_metrics", True),
            **{
                key: options_in[key]
                for key in ("include_evidence_preview", "clarification_mode", "use_cache")
                if key in options_in
            },
        }

    session_id = payload.get("session_id")
    if session_id is not None and (
        not isinstance(session_id, str) or re.fullmatch(r"[0-9a-f]{32}", session_id) is None
    ):
        raise ContractError("invalid_request", stage, "Invalid clarification session identifier.")
    normalized_question = re.sub(r"\s+", " ", question.strip()).lower()
    normalized_question = re.sub(r"[?!.]+$", "", normalized_question).strip()
    return {
        "contract_version": "normalized-query.v1",
        "question": question,
        "normalized_question": normalized_question,
        "locale": locale,
        "options": copy.deepcopy(options),
        **({"session_id": session_id} if session_id else {}),
    }


def build_auth_context(
    idp_claims: dict[str, Any] | None,
    server_policy: dict[str, Any] | None,
    request_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build authorization only from IdP claims and server policy.

    ``request_body`` is intentionally never inspected; it exists only so a caller can
    pass the original request without accidentally treating client claims as authority.
    """

    del request_body
    stage = "auth_policy_context"
    if not isinstance(idp_claims, dict) or not idp_claims:
        raise _forbidden(stage, "Missing authentication claims.")
    if not isinstance(server_policy, dict) or not server_policy:
        raise _forbidden(stage, "Missing server policy.")

    _require_auth_keys(idp_claims, _AUTH_KEYS, stage)
    _require_auth_keys(server_policy, _POLICY_KEYS, stage)
    enforce_exact_keys(idp_claims, _AUTH_KEYS, set(), stage)
    enforce_exact_keys(
        server_policy,
        _POLICY_KEYS,
        _POLICY_OPTIONAL_KEYS,
        stage,
    )

    user_id = idp_claims["user_id"]
    tenant_id = idp_claims["tenant_id"]
    roles = idp_claims["roles"]
    allowed_views = server_policy["allowed_views"]
    allowed_metrics = server_policy.get("allowed_metrics")
    policy_version = server_policy["policy_version"]

    if not _nonempty_string(user_id) or not _nonempty_string(tenant_id):
        raise _forbidden(stage, "Incomplete identity claims.")
    if not _nonempty_string_list(roles) or not _nonempty_string_list(allowed_views):
        raise _forbidden(stage, "Incomplete authorization context.")
    if not _nonempty_string(policy_version):
        raise _forbidden(stage, "Missing policy version.")
    if allowed_metrics is not None and not _string_list(allowed_metrics):
        raise _forbidden(stage, "Invalid allowed metric policy.")

    row_scope = {}
    for key in ROW_SCOPE_FIELDS.keys() & server_policy.keys():
        codes = server_policy[key]
        if not _nonempty_string_list(codes) or (
            codes != ["*"] and not all(_SCOPE_CODE.fullmatch(code) for code in codes)
        ):
            raise _forbidden(stage, "Invalid row scope policy.")
        row_scope[key] = sorted(set(codes))

    roles_copy = copy.deepcopy(roles)
    views_copy = copy.deepcopy(allowed_views)
    metrics_copy = copy.deepcopy(allowed_metrics)
    policy_blob = json.dumps(
        {
            "tenant_id": tenant_id,
            "roles": sorted(roles_copy),
            "allowed_views": sorted(views_copy),
            "allowed_metrics": sorted(metrics_copy) if metrics_copy is not None else None,
            "policy_version": policy_version,
            **row_scope,
        },
        sort_keys=True,
    )
    policy_hash = "policy-" + hashlib.sha256(policy_blob.encode("utf-8")).hexdigest()[:12]
    return {
        "contract_version": "auth-context.v1",
        "user_id": user_id,
        "tenant_id": tenant_id,
        "roles": roles_copy,
        "allowed_views": views_copy,
        "allowed_metrics": metrics_copy,
        "policy_hash": policy_hash,
        **row_scope,
    }


def build_runtime_context(
    request_id: str,
    trace_id: str,
    auth_context: dict[str, Any],
    locale: str,
    timezone: str,
    catalog_hash: str,
    request_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine request metadata with a server-built authorization context."""

    del request_body
    stage = "runtime_context"
    if not isinstance(auth_context, dict):
        raise _forbidden(stage, "Missing authorization context.")
    required_auth_keys = {
        "contract_version",
        "user_id",
        "tenant_id",
        "roles",
        "allowed_views",
        "allowed_metrics",
        "policy_hash",
    }
    _require_auth_keys(auth_context, required_auth_keys, stage)
    enforce_exact_keys(auth_context, required_auth_keys, set(ROW_SCOPE_FIELDS), stage)
    if auth_context["contract_version"] != "auth-context.v1":
        raise _forbidden(stage, "Invalid authorization context version.")
    if not _nonempty_string(auth_context["user_id"]) or not _nonempty_string(
        auth_context["tenant_id"]
    ):
        raise _forbidden(stage, "Incomplete authorization identity.")
    if not _nonempty_string_list(auth_context["roles"]) or not _nonempty_string_list(
        auth_context["allowed_views"]
    ):
        raise _forbidden(stage, "Incomplete authorization permissions.")
    if not _nonempty_string(auth_context["policy_hash"]):
        raise _forbidden(stage, "Missing policy hash.")
    if not isinstance(locale, str) or locale not in SUPPORTED_LOCALES:
        raise ContractError(
            "unsupported_locale",
            stage,
            "Requested locale is not supported.",
            final_status="unsupported",
        )
    for field_name, value in {
        "request_id": request_id,
        "trace_id": trace_id,
        "timezone": timezone,
        "catalog_hash": catalog_hash,
    }.items():
        if not _nonempty_string(value):
            raise ContractError(
                "invalid_request",
                stage,
                "Runtime metadata must be non-empty strings.",
                details={"invalid_field": field_name},
            )

    return {
        "request_id": request_id,
        "trace_id": trace_id,
        "tenant_id": auth_context["tenant_id"],
        "user_id": auth_context["user_id"],
        "roles": copy.deepcopy(auth_context["roles"]),
        "allowed_views": copy.deepcopy(auth_context["allowed_views"]),
        "locale": locale,
        "timezone": timezone,
        "catalog_hash": catalog_hash,
        "policy_hash": auth_context["policy_hash"],
    }


def _require_auth_keys(obj: dict[str, Any], required_keys: set[str], stage: str) -> None:
    missing = required_keys - set(obj)
    if missing:
        raise _forbidden(stage, "Incomplete authentication or policy data.")


def _forbidden(stage: str, message: str) -> ContractError:
    return ContractError("forbidden", stage, message, final_status="forbidden")


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(_nonempty_string(item) for item in value)


def _nonempty_string_list(value: Any) -> bool:
    return _string_list(value) and bool(value)
