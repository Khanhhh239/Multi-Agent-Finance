"""Input-only adapter for the production governed pipeline."""

from __future__ import annotations

import os
from functools import cache

from agent4.core.config import AppConfig
from agent4.metric_selection.config import load_config
from agent4.pipeline import PipelineTrace, run_governed_pipeline
from agent4.planning.eval_adapter import _benchmark_plan

_WARNING_CODES = {
    "partial_data_watermark": "partial_data",
    "ratio_undefined": "undefined_ratio",
}


@cache
def _config():
    return load_config(os.getenv("AGENT4_METRIC_SELECTION_CONFIG")), AppConfig()


async def predict(request: dict) -> dict:
    fixture = request["auth_context"]
    claims = {key: fixture[key] for key in ("user_id", "tenant_id", "roles")}
    policy = {
        "allowed_views": fixture["allowed_views"],
        "allowed_metrics": fixture.get("allowed_metrics"),
        "policy_version": "contract-benchmark-v2",
    }
    config, app_config = _config()
    trace = PipelineTrace()
    response = await run_governed_pipeline(
        {
            "api_version": "v1",
            "question": request["user_query"],
            "locale": request["locale"],
            "options": request["options"],
        },
        claims,
        policy,
        app_config=app_config,
        selection_config=config,
        trace=trace,
        seed=request["seed"],
    )
    selected = trace.selected_metrics
    selection = None
    if selected is not None:
        selection = {
            "status": "resolved" if selected["status"] == "validated" else "ambiguous",
            "metric_ids": selected["metric_ids"],
            "clarification_question": selected["clarification_question"],
        }
    error = response["error"]
    if (
        selection is None
        and error
        and error["stage"] in {"metrics_validation", "request_scope"}
        and response["status"] == "unsupported"
    ):
        selection = {"status": "unsupported", "metric_ids": []}
    return {
        "id": request["id"],
        "retrieved_metric_ids": (
            trace.selection.retrieved_metric_ids
            if trace.selection.retrieval_result is not None
            else None
        ),
        "selection": selection,
        "plan": _benchmark_plan(trace.plan, request["user_query"].casefold())
        if trace.plan
        else None,
        "final_status": response["status"],
        "result": response["data"],
        "answer": response["answer"],
        "warning_codes": [_WARNING_CODES.get(code, code) for code in response["warnings"]],
        "execution": trace.execution or {"attempted": False, "succeeded": False},
        "clarification_question": (
            response["answer"] if response["status"] == "needs_clarification" else None
        ),
        "usage": trace.selection.usage,
        "stage_latency_ms": trace.selection.stage_latency_ms,
        "selected_example_ids": trace.selection.selected_example_ids,
        "error": {key: error[key] for key in ("stage", "code")} if error else None,
    }
