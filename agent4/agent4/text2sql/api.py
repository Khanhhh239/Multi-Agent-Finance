from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Header, HTTPException, Response

from .models import AuthContext, QueryRequest, QueryResponse
from .service import QueryService, build_default_service
from .validation import metric_allowed


def create_app(
    service: QueryService | None = None,
    *,
    demo_token: str | None = None,
    auth_context: AuthContext | None = None,
) -> FastAPI:
    query_service = service or build_default_service()
    configured_token = demo_token if demo_token is not None else os.getenv("AGENT4_DEMO_TOKEN")
    fixed_auth = auth_context or AuthContext(
        user_id="demo-analyst", tenant_id="tenant_demo_A",
        roles=frozenset({"finance_analyst"}), allowed_views=frozenset({"mgmt", "tax"}),
    )
    app = FastAPI(title="AI-fin Safe Financial Text-to-SQL", version="1.0.0")

    async def require_auth(authorization: str | None = Header(default=None)) -> AuthContext:
        if not configured_token:
            raise HTTPException(status_code=503, detail="Authentication is not configured")
        if authorization != f"Bearer {configured_token}":
            raise HTTPException(status_code=401, detail="Authentication required")
        return fixed_auth

    @app.get("/health/live")
    async def live() -> dict:
        return {"status": "live"}

    @app.get("/health/ready")
    async def ready() -> dict:
        healthy = bool(configured_token) and query_service.executor.ready()
        if not healthy:
            raise HTTPException(status_code=503, detail="Service is not ready")
        return {
            "status": "ready", "catalog_hash": query_service.catalog.hash,
            "metric_count": len(query_service.catalog.public_metrics()), "data_mode": "synthetic",
        }

    @app.get("/v1/metrics")
    async def metrics(auth: AuthContext = Depends(require_auth)) -> dict:  # noqa: B008
        visible = frozenset(
            item["id"]
            for item in query_service.catalog.public_metrics(
                auth.allowed_metrics, auth.allowed_views
            )
            if metric_allowed(item["id"], auth)
        )
        return {
            "catalog_hash": query_service.catalog.hash,
            "items": query_service.catalog.public_metrics(
                visible, auth.allowed_views
            ),
        }

    @app.post("/v1/query", response_model=QueryResponse)
    async def query(
        request: QueryRequest,
        response: Response,
        auth: AuthContext = Depends(require_auth),  # noqa: B008
    ) -> QueryResponse:
        result = query_service.query(request, auth)
        if result.status == "forbidden":
            response.status_code = 403
        if result.status == "temporarily_unavailable":
            response.status_code = 503
        return result

    return app
