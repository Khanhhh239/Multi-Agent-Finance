"""FastAPI integration. Run with: uvicorn agent4.metric_selection.api:create_app --factory."""
from __future__ import annotations

import os

from .config import MetricSelectionConfig, load_config
from .errors import EmptyCandidateError, LLMProviderError, MetricSelectionError
from .factory import build_pipeline
from .pipeline import MetricSelectionPipeline
from .schemas import MetricSelectionRequest, MetricSelectionResult


def create_app(
    pipeline: MetricSelectionPipeline | None = None,
    config: MetricSelectionConfig | None = None,
):
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:
        raise RuntimeError("FastAPI is required; install the project dependencies") from exc

    app = FastAPI(title="Agent 4 Metric Selection", version="1.0.0")
    selector = pipeline or build_pipeline(config or load_config())
    debug_enabled = os.getenv("AGENT4_METRIC_DEBUG", "0") == "1"

    @app.post(
        "/api/metrics/select",
        response_model=MetricSelectionResult,
        response_model_exclude_none=True,
    )
    async def select_metric(request: MetricSelectionRequest) -> MetricSelectionResult:
        if request.debug and not debug_enabled:
            raise HTTPException(status_code=403, detail="Debug traces are disabled")
        try:
            return await selector.select(request)
        except EmptyCandidateError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except LLMProviderError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except MetricSelectionError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    if debug_enabled:
        @app.get("/internal/metrics/catalog")
        async def inspect_catalog() -> dict:
            return {
                "catalog_version": selector.catalog.version,
                "metric_count": len(selector.catalog),
                "metric_ids": selector.catalog.metric_ids,
            }

    return app
