"""FastAPI boundary for the governed query pipeline and its opt-in demo."""

import os
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent4.core.catalog import LEGACY_METRIC_IDS, MetricCatalog
from agent4.core.errors import ContractError
from agent4.metric_selection.config import MetricSelectionConfig, load_config
from agent4.planning.clarification import ClarificationSessionStore

from .demo_ui import DEMO_QUESTIONS, demo_page
from .pipeline import PipelineTrace, build_final_response, run_governed_pipeline

_DEMO_TENANT = "demo-enterprise"
_DEMO_VIEWS = ["mgmt", "tax"]
_BRANCH_METRICS = ["net_revenue", "gross_profit", "gross_margin_pct", "gross_margin"]


def _demo_identity(persona: str, metric_ids: list[str]) -> tuple[dict, dict]:
    branch = persona == "branch_viewer"
    claims = {
        "tenant_id": _DEMO_TENANT,
        "user_id": "hcm-viewer" if branch else "cfo-demo",
        "roles": ["branch_viewer" if branch else "finance_analyst"],
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
) -> FastAPI:
    """Use verified host claims, with server-owned synthetic personas in demo mode."""
    demo_mode = demo_mode or os.getenv("AGENT4_DEMO_MODE") == "1"
    app = FastAPI(title="Agent 4 Governed Queries", version="1.0.0")
    sessions = ClarificationSessionStore()
    targets = dict(warehouses) if warehouses is not None else None
    catalog = MetricCatalog(canonical=True)

    @app.get("/healthz")
    async def liveness() -> dict:
        return {"status": "live"}

    if demo_mode:
        demo_path = Path(os.getenv("AGENT4_DB_PATH", "data/cfo_warehouse.duckdb"))
        targets = targets if targets is not None else {}
        targets.setdefault(_DEMO_TENANT, demo_path)
        selection_config = selection_config or load_config(
            os.getenv("AGENT4_SELECTION_CONFIG")
            or os.getenv("AGENT4_METRIC_SELECTION_CONFIG")
            or "config/selection.yaml"
        )
        demo_metrics = [metric["metric_id"] for metric in catalog.list_metrics()] + list(
            LEGACY_METRIC_IDS
        )
        verified = [
            {
                "metric_id": metric["metric_id"],
                "name_vi": metric["label"],
                "name_en": metric.get("label_en", metric["label"]),
                "unit": metric["unit"],
                "period_type": metric["period_type"],
                "supported_dimensions": metric["supported_dimensions"],
                "allowed_views": [
                    view for view in _DEMO_VIEWS if view in metric["supported_views"]
                ],
            }
            for metric in catalog.list_visible_metrics({"allowed_views": _DEMO_VIEWS})
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

    @app.get("/health")
    async def health() -> dict:
        status = {"status": "ok", "demo_mode": demo_mode}
        if demo_mode:
            status.update(
                db_path=str(targets[_DEMO_TENANT]),
                verified_metrics_count=len(verified),
                llm_model=selection_config.llm.model,
                embedding_model=selection_config.embedding.model,
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
        trace = PipelineTrace(
            include_demo_evidence=demo_mode
            and isinstance(claims, dict)
            and claims.get("tenant_id") == _DEMO_TENANT
        )
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


def create_demo_app() -> FastAPI:
    """Start the synthetic warehouse demo with the two server-owned personas."""
    return create_app(demo_mode=True)
