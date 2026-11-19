"""FastAPI boundary for the governed query pipeline and its opt-in demo."""

import asyncio
import os
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from agent4.core.catalog import LEGACY_METRIC_IDS, MetricCatalog
from agent4.core.context import build_auth_context
from agent4.core.errors import ContractError
from agent4.metric_selection.config import MetricSelectionConfig, load_config
from agent4.planning.clarification import ClarificationSessionStore

from .demo_ui import DEMO_QUESTIONS, demo_page
from .metric_selection.config import require_api_key_config
from .metric_selection.errors import ConfigurationError
from .pipeline import PipelineTrace, build_final_response, run_governed_pipeline

_DEMO_TENANT = "demo-enterprise"
_DEMO_VIEWS = ["mgmt", "tax"]
_BRANCH_METRICS = ["net_revenue", "gross_profit", "gross_margin_pct", "gross_margin"]


def _csv_env(name: str) -> tuple[str, ...]:
    return tuple(sorted({item.strip() for item in os.getenv(name, "").split(",") if item.strip()}))


def _public_metric(metric: dict) -> dict:
    """Expose catalog metadata without SQL expressions or internal ownership fields."""
    return {
        "metric_id": metric["metric_id"],
        "name_vi": metric["label"],
        "name_en": metric.get("label_en", metric["label"]),
        "unit": metric["unit"],
        "period_type": metric["period_type"],
        "supported_dimensions": metric["supported_dimensions"],
        "allowed_views": list(metric["supported_views"]),
    }


def _forbidden_response(error: ContractError) -> JSONResponse:
    return JSONResponse(
        build_final_response(uuid4().hex, "forbidden", error=error),
        status_code=403,
        headers={"Cache-Control": "no-store"},
    )


def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be a positive integer")
    return value


def _demo_identity(persona: str, metric_ids: list[str]) -> tuple[dict, dict]:
    branch = persona == "branch_viewer"
    claims = {
        "tenant_id": _DEMO_TENANT,
        "user_id": "hcm-viewer" if branch else "cfo-demo",
        "roles": ["branch_viewer"] if branch else ["finance_analyst", "payroll_viewer"],
    }
    policy = {
        "policy_version": f"demo-v1-{persona}",
        "allowed_views": ["mgmt"] if branch else list(_DEMO_VIEWS),
        "allowed_metrics": list(_BRANCH_METRICS if branch else metric_ids),
        "allowed_branches": ["HCM"] if branch else ["*"],
        "allowed_departments": ["*"],
    }
    return claims, policy


def create_app(
    *,
    warehouses: Mapping[str, Path] | None = None,
    selection_config: MetricSelectionConfig | None = None,
    demo_mode: bool = False,
    require_api_keys: bool = False,
    cloud_mode: bool = False,
    allow_env_demo_mode: bool = True,
    cors_origins: tuple[str, ...] | None = None,
    max_concurrent_queries: int | None = None,
) -> FastAPI:
    """Use verified host claims, with server-owned synthetic personas in demo mode."""
    cloud_mode = cloud_mode or os.getenv("AGENT4_CLOUD_MODE") == "1"
    if allow_env_demo_mode:
        demo_mode = demo_mode or os.getenv("AGENT4_DEMO_MODE") == "1"
    if cloud_mode and (demo_mode or os.getenv("AGENT4_DEMO_MODE") == "1"):
        raise ConfigurationError("Cloud mode cannot run with AGENT4_DEMO_MODE")
    app = FastAPI(title="Agent 4 Governed Queries", version="1.0.0")
    sessions = ClarificationSessionStore()
    targets = dict(warehouses) if warehouses is not None else None
    catalog = MetricCatalog(canonical=True)
    query_limit = (
        max_concurrent_queries
        if max_concurrent_queries is not None
        else _positive_int_env("AGENT4_MAX_CONCURRENT_QUERIES", 1)
    )
    if query_limit <= 0:
        raise ConfigurationError("max_concurrent_queries must be a positive integer")
    query_slots = asyncio.Semaphore(query_limit)
    app.state.query_slots = query_slots
    app.state.cloud_mode = cloud_mode

    if demo_mode or cloud_mode:
        selection_config = selection_config or load_config(
            os.getenv("AGENT4_SELECTION_CONFIG")
            or os.getenv("AGENT4_METRIC_SELECTION_CONFIG")
            or ("config/selection_cloud.yaml" if cloud_mode else "config/selection.yaml")
        )
    if require_api_keys and selection_config is not None:
        require_api_key_config(selection_config)

    configured_origins = (
        tuple(cors_origins) if cors_origins is not None else _csv_env("AGENT4_CORS_ORIGINS")
    )
    if "*" in configured_origins:
        raise ConfigurationError("AGENT4_CORS_ORIGINS cannot contain wildcard origin")
    if configured_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(configured_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
            max_age=600,
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if cloud_mode:
            response.headers.setdefault(
                "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
            )
            if request.url.path.startswith("/v1/"):
                response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/healthz")
    async def liveness() -> dict:
        return {"status": "live"}

    @app.get("/readyz")
    async def readiness() -> JSONResponse:
        if not cloud_mode:
            return JSONResponse({"status": "ready"})
        checks = {"config": "ready" if selection_config is not None else "missing"}
        if not targets:
            checks["warehouse_artifact"] = "missing"
        else:
            checks["warehouse_artifact"] = (
                "ready"
                if all(path.is_file() and os.access(path, os.R_OK) for path in targets.values())
                else "missing"
            )
        ready = all(value == "ready" for value in checks.values())
        body = {"status": "ready" if ready else "not_ready", "checks": checks}
        return JSONResponse(body, status_code=200 if ready else 503)

    if demo_mode:
        demo_path = Path(os.getenv("AGENT4_DB_PATH", "data/cfo_warehouse.duckdb"))
        targets = targets if targets is not None else {}
        targets.setdefault(_DEMO_TENANT, demo_path)
        demo_metrics = [metric["metric_id"] for metric in catalog.list_metrics()] + list(
            LEGACY_METRIC_IDS
        )
        verified = [
            {
                **_public_metric(metric),
                "allowed_views": [
                    view for view in _DEMO_VIEWS if view in metric["supported_views"]
                ],
            }
            for metric in catalog.list_visible_metrics(
                {"allowed_views": _DEMO_VIEWS, "roles": ["finance_analyst", "payroll_viewer"]}
            )
        ]

        @app.get("/", include_in_schema=False)
        async def index():
            return demo_page()

        @app.get("/v1/metrics")
        async def metrics() -> list[dict]:
            return verified

        @app.get("/v1/demo-questions")
        async def demo_questions() -> list[dict]:
            return DEMO_QUESTIONS

    if cloud_mode:

        @app.get("/v1/metrics", response_model=None)
        async def cloud_metrics(request: Request) -> JSONResponse | list[dict]:
            try:
                auth = build_auth_context(
                    getattr(request.state, "idp_claims", None),
                    getattr(request.state, "server_policy", None),
                )
            except ContractError as exc:
                return _forbidden_response(exc)
            return [_public_metric(metric) for metric in catalog.list_visible_metrics(auth)]

    @app.get("/health")
    async def health() -> dict:
        status = {"status": "ok", "demo_mode": demo_mode}
        if demo_mode:
            status.update(
                db_path=str(targets[_DEMO_TENANT]),
                verified_metrics_count=len(verified),
                llm_model=selection_config.llm.model,
                llm_provider=selection_config.llm.provider,
                embedding_model=selection_config.embedding.model,
                embedding_provider=selection_config.embedding.provider,
                retrieval_mode=selection_config.retrieval.mode,
            )
        return status

    @app.post("/v1/query")
    async def query(request: Request) -> JSONResponse:
        claims = getattr(request.state, "idp_claims", None)
        policy = getattr(request.state, "server_policy", None)
        if demo_mode and claims is None and policy is None:
            persona = request.headers.get("X-Demo-Persona", "cfo_full")
            if persona not in ("cfo_full", "branch_viewer"):
                error = ContractError(
                    "forbidden", "demo_persona", "Unknown demo persona.", final_status="forbidden"
                )
                return JSONResponse(
                    build_final_response(uuid4().hex, "forbidden", error=error), status_code=403
                )
            claims, policy = _demo_identity(persona, demo_metrics)
        try:
            payload = await request.json()
        except ValueError:
            payload = None
        if cloud_mode:
            if query_slots.locked():
                busy = ContractError(
                    "query_busy",
                    "query_admission",
                    "Agent 4 is serving another expensive query.",
                    retryable=True,
                    final_status="temporarily_unavailable",
                )
                return JSONResponse(
                    build_final_response(uuid4().hex, "temporarily_unavailable", error=busy),
                    status_code=503,
                    headers={"Cache-Control": "no-store", "Retry-After": "1"},
                )
            await query_slots.acquire()
        trace = PipelineTrace(
            include_demo_evidence=demo_mode
            and isinstance(claims, dict)
            and claims.get("tenant_id") == _DEMO_TENANT
        )
        try:
            response = await run_governed_pipeline(
                payload,
                claims,
                policy,
                warehouses=targets,
                selection_config=selection_config,
                sessions=sessions,
                catalog=catalog,
                trace=trace,
            )
        finally:
            if cloud_mode:
                query_slots.release()
        if trace.demo_evidence is not None:
            response["demo_evidence"] = trace.demo_evidence
        error = response["error"] or {}
        status = {
            "forbidden": 403,
            "temporarily_unavailable": 503,
            "error": 500,
            "unsupported": 422 if demo_mode else 200,
        }.get(response["status"], 200)
        if error.get("stage") == "query_intake":
            status = 400
        if error.get("stage") == "clarification" and error.get("code") == "invalid_request":
            status = 400
        return JSONResponse(
            response,
            status_code=status,
            headers={"Cache-Control": "no-store"} if demo_mode else None,
        )

    return app


def create_cloud_app(
    *,
    warehouses: Mapping[str, Path] | None = None,
    selection_config: MetricSelectionConfig | None = None,
    allow_test_providers: bool = False,
) -> FastAPI:
    """Create the non-demo Render slice with an explicit artifact and deny-by-default auth.

    Claims and policy must be injected by the authenticated Gateway middleware. Browser
    headers, ``X-Demo-Persona`` and client-supplied policy fields are never trusted here.
    """
    if warehouses is None:
        tenant = os.getenv("AGENT4_WAREHOUSE_TENANT_ID") or os.getenv("AGENT4_TENANT_ID")
        artifact = (
            os.getenv("AGENT4_WAREHOUSE_PATH")
            or os.getenv("AGENT4_DB_PATH")
            or os.getenv("AGENT4_DB")
        )
        warehouses = {tenant: Path(artifact)} if tenant and artifact else {}
    return create_app(
        warehouses=warehouses,
        selection_config=selection_config,
        cloud_mode=True,
        allow_env_demo_mode=False,
        require_api_keys=not allow_test_providers,
    )


def create_demo_app(*, allow_test_providers: bool = False) -> FastAPI:
    """Start the synthetic warehouse demo with the two server-owned personas."""
    return create_app(demo_mode=True, require_api_keys=not allow_test_providers)
