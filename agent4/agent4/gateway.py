"""Provider-neutral authentication gateway for the Agent 4 cloud slice.

The gateway deliberately accepts only a verified OIDC access token and a policy
document owned by the server. It does not accept identity, role, tenant or policy
headers from the browser. The policy document is intentionally small and static
for the single-tenant vertical slice; a Neon-backed policy resolver can replace
it later without changing the protected Agent 4 contract.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import Request
from fastapi.responses import JSONResponse

from .api import create_cloud_app
from .metric_selection.errors import ConfigurationError

_PUBLIC_PATHS = {"/healthz", "/readyz"}
_MAX_POLICY_BYTES = 128 * 1024
_MAX_SUBJECT_LENGTH = 256
_MAX_TENANT_LENGTH = 128
_JWKS_CACHE_SECONDS = 300.0
_JWKS_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class GatewaySettings:
    """Non-secret gateway configuration validated before the server starts."""

    issuer: str
    audience: str
    jwks_url: str
    algorithms: tuple[str, ...]
    tenant_claim: str
    rate_limit_per_minute: int
    policy: dict[str, dict[str, dict[str, Any]]]
    leeway_seconds: int = 30

    @classmethod
    def from_env(cls) -> GatewaySettings:
        issuer = _required_env("AGENT4_OIDC_ISSUER")
        audience = _required_env("AGENT4_OIDC_AUDIENCE")
        jwks_url = _required_env("AGENT4_OIDC_JWKS_URL")
        if not jwks_url.startswith("https://"):
            raise ConfigurationError("AGENT4_OIDC_JWKS_URL must use HTTPS")
        algorithms = tuple(
            item.strip()
            for item in os.getenv("AGENT4_OIDC_ALGORITHMS", "RS256").split(",")
            if item.strip()
        )
        if not algorithms or any(item not in {"RS256", "ES256"} for item in algorithms):
            raise ConfigurationError("AGENT4_OIDC_ALGORITHMS must contain RS256 or ES256")
        tenant_claim = os.getenv("AGENT4_OIDC_TENANT_CLAIM", "tenant_id").strip()
        if not tenant_claim or len(tenant_claim) > 64:
            raise ConfigurationError("AGENT4_OIDC_TENANT_CLAIM is invalid")
        rate_limit = _positive_int_env("AGENT4_RATE_LIMIT_PER_MINUTE", 30)
        leeway = _bounded_int_env("AGENT4_OIDC_LEEWAY_SECONDS", 30, maximum=120)
        policy = _load_policy()
        return cls(
            issuer=issuer,
            audience=audience,
            jwks_url=jwks_url,
            algorithms=algorithms,
            tenant_claim=tenant_claim,
            rate_limit_per_minute=rate_limit,
            policy=policy,
            leeway_seconds=leeway,
        )


class _AuthUnavailable(Exception):
    """The identity provider could not be reached or its metadata was invalid."""


class _Unauthenticated(Exception):
    """The request did not contain a valid verified identity."""


class _JwksCache:
    def __init__(self, url: str) -> None:
        self.url = url
        self._keys: dict[str, dict[str, Any]] = {}
        self._loaded_at = 0.0
        self._lock = asyncio.Lock()

    async def signing_key(self, token: str, *, algorithms: tuple[str, ...]):
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as exc:
            raise _Unauthenticated from exc
        algorithm = header.get("alg")
        kid = header.get("kid")
        if algorithm not in algorithms or not isinstance(kid, str) or not kid:
            raise _Unauthenticated

        keys = await self._load(force=False)
        jwk = keys.get(kid)
        if jwk is None:
            keys = await self._load(force=True)
            jwk = keys.get(kid)
        if jwk is None:
            raise _Unauthenticated
        try:
            signing_key = jwt.PyJWK.from_dict(jwk)
            if signing_key.algorithm_name != algorithm:
                raise _Unauthenticated
            return signing_key.key
        except (_Unauthenticated, ValueError, TypeError, jwt.InvalidKeyError) as exc:
            raise _Unauthenticated from exc

    async def _load(self, *, force: bool) -> dict[str, dict[str, Any]]:
        now = time.monotonic()
        if not force and self._keys and now - self._loaded_at < _JWKS_CACHE_SECONDS:
            return self._keys
        async with self._lock:
            now = time.monotonic()
            if not force and self._keys and now - self._loaded_at < _JWKS_CACHE_SECONDS:
                return self._keys
            try:
                async with httpx.AsyncClient(
                    timeout=_JWKS_TIMEOUT_SECONDS,
                    trust_env=False,
                    follow_redirects=False,
                ) as client:
                    response = await client.get(self.url)
                    response.raise_for_status()
                    body = response.json()
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                raise _AuthUnavailable from exc
            rows = body.get("keys") if isinstance(body, dict) else None
            if not isinstance(rows, list):
                raise _AuthUnavailable
            parsed = {
                row["kid"]: row
                for row in rows
                if isinstance(row, dict)
                and isinstance(row.get("kid"), str)
                and row.get("kty") in {"RSA", "EC"}
            }
            if not parsed:
                raise _AuthUnavailable
            self._keys = parsed
            self._loaded_at = time.monotonic()
            return parsed


class _SlidingWindowLimiter:
    def __init__(self, limit: int, *, window_seconds: float = 60.0, max_buckets: int = 4096):
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_buckets = max_buckets
        self._events: OrderedDict[str, deque[float]] = OrderedDict()

    def allow(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        events = self._events.get(key)
        if events is None:
            events = deque()
            self._events[key] = events
        else:
            self._events.move_to_end(key)
        cutoff = now - self.window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= self.limit:
            retry_after = max(1, int(self.window_seconds - (now - events[0]) + 0.999))
            return False, retry_after
        events.append(now)
        while len(self._events) > self.max_buckets:
            self._events.popitem(last=False)
        return True, 0


class _GatewayAuthenticator:
    def __init__(self, settings: GatewaySettings):
        self.settings = settings
        self.jwks = _JwksCache(settings.jwks_url)

    async def authenticate(self, request: Request) -> tuple[dict[str, Any], dict[str, Any]]:
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token or len(token) > 16 * 1024:
            raise _Unauthenticated
        key = await self.jwks.signing_key(token, algorithms=self.settings.algorithms)
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=list(self.settings.algorithms),
                audience=self.settings.audience,
                issuer=self.settings.issuer,
                leeway=self.settings.leeway_seconds,
                options={"require": ["exp", "iat", "iss", "sub"]},
            )
        except jwt.InvalidTokenError as exc:
            raise _Unauthenticated from exc
        if not isinstance(claims, dict):
            raise _Unauthenticated
        subject = claims.get("sub")
        tenant = claims.get(self.settings.tenant_claim)
        if not _bounded_text(subject, _MAX_SUBJECT_LENGTH) or not _bounded_text(
            tenant, _MAX_TENANT_LENGTH
        ):
            raise _Unauthenticated
        record = self.settings.policy.get(tenant, {}).get(subject)
        if record is None:
            raise _Unauthenticated
        idp_claims = {
            "user_id": subject,
            "tenant_id": tenant,
            # Roles are server policy, not a browser-controlled header or client payload.
            "roles": list(record["roles"]),
        }
        server_policy = {
            key: value
            for key, value in record.items()
            if key
            in {
                "allowed_views",
                "allowed_metrics",
                "allowed_branches",
                "allowed_departments",
                "policy_version",
            }
        }
        return idp_claims, server_policy


def create_gateway_app() -> Any:
    """Build the only production HTTP entrypoint for the Agent 4 cloud slice."""

    settings = GatewaySettings.from_env()
    app = create_cloud_app()
    authenticator = _GatewayAuthenticator(settings)
    ip_limiter = _SlidingWindowLimiter(settings.rate_limit_per_minute)
    identity_limiter = _SlidingWindowLimiter(settings.rate_limit_per_minute)
    app.state.gateway_settings = settings

    @app.middleware("http")
    async def gateway(request: Request, call_next):
        # Health probes and CORS preflight carry no business data and remain public.
        if request.url.path in _PUBLIC_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        client_host = request.client.host if request.client else "unknown"
        ip_allowed, ip_retry = ip_limiter.allow(client_host)
        if not ip_allowed:
            return _rate_limited(ip_retry)
        try:
            idp_claims, server_policy = await authenticator.authenticate(request)
        except _AuthUnavailable:
            return JSONResponse(
                {"error": {"code": "authentication_unavailable"}},
                status_code=503,
                headers={"Cache-Control": "no-store", "Retry-After": "5"},
            )
        except _Unauthenticated:
            return JSONResponse(
                {"error": {"code": "authentication_required"}},
                status_code=401,
                headers={
                    "Cache-Control": "no-store",
                    "WWW-Authenticate": "Bearer",
                },
            )
        identity_key = f"{idp_claims['tenant_id']}:{idp_claims['user_id']}"
        identity_allowed, identity_retry = identity_limiter.allow(identity_key)
        if not identity_allowed:
            return _rate_limited(identity_retry)
        request.state.idp_claims = idp_claims
        request.state.server_policy = server_policy
        return await call_next(request)

    return app


def _rate_limited(retry_after: int) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": "rate_limited", "retryable": True}},
        status_code=429,
        headers={"Cache-Control": "no-store", "Retry-After": str(retry_after)},
    )


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} is required for the cloud gateway")
    return value


def _positive_int_env(name: str, default: int) -> int:
    value = _bounded_int_env(name, default, maximum=600)
    if value <= 0:
        raise ConfigurationError(f"{name} must be positive")
    return value


def _bounded_int_env(name: str, default: int, *, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if value < 0 or value > maximum:
        raise ConfigurationError(f"{name} is outside the allowed range")
    return value


def _load_policy() -> dict[str, dict[str, dict[str, Any]]]:
    raw = os.getenv("AGENT4_AUTH_POLICY_JSON", "")
    if not raw or len(raw.encode("utf-8")) > _MAX_POLICY_BYTES:
        raise ConfigurationError("AGENT4_AUTH_POLICY_JSON is required and bounded")
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigurationError("AGENT4_AUTH_POLICY_JSON is invalid JSON") from exc
    tenants = document.get("tenants") if isinstance(document, dict) else None
    if not isinstance(tenants, dict) or not tenants:
        raise ConfigurationError("AGENT4_AUTH_POLICY_JSON must contain tenants")
    normalized: dict[str, dict[str, dict[str, Any]]] = {}
    for tenant, tenant_doc in tenants.items():
        if not _bounded_text(tenant, _MAX_TENANT_LENGTH) or not isinstance(tenant_doc, dict):
            raise ConfigurationError("AGENT4_AUTH_POLICY_JSON contains an invalid tenant")
        users = tenant_doc.get("users")
        if not isinstance(users, dict) or not users:
            raise ConfigurationError("AGENT4_AUTH_POLICY_JSON tenant must contain users")
        normalized_users: dict[str, dict[str, Any]] = {}
        for subject, record in users.items():
            if not _bounded_text(subject, _MAX_SUBJECT_LENGTH) or not isinstance(record, dict):
                raise ConfigurationError("AGENT4_AUTH_POLICY_JSON contains an invalid user")
            normalized_users[subject] = _validate_policy_record(record)
        normalized[tenant] = normalized_users
    return normalized


def _validate_policy_record(record: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "roles",
        "allowed_views",
        "allowed_metrics",
        "allowed_branches",
        "allowed_departments",
        "policy_version",
    }
    if set(record) - allowed or not {"roles", "allowed_views", "policy_version"}.issubset(record):
        raise ConfigurationError("AGENT4_AUTH_POLICY_JSON contains an incomplete policy")
    result = dict(record)
    for key in ("roles", "allowed_views", "policy_version"):
        value = result[key]
        if key == "policy_version":
            if not _bounded_text(value, 128):
                raise ConfigurationError("AGENT4_AUTH_POLICY_JSON contains an invalid policy version")
        elif not _bounded_string_list(value):
            raise ConfigurationError("AGENT4_AUTH_POLICY_JSON contains an invalid policy list")
    for key in ("allowed_metrics", "allowed_branches", "allowed_departments"):
        if key in result and not _bounded_string_list(result[key]):
            raise ConfigurationError("AGENT4_AUTH_POLICY_JSON contains an invalid scope")
    return result


def _bounded_text(value: Any, maximum: int) -> bool:
    return isinstance(value, str) and 0 < len(value) <= maximum and bool(value.strip())


def _bounded_string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and 0 < len(value) <= 128
        and all(_bounded_text(item, 128) for item in value)
    )
