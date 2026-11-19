"""Measure a real Agent 4 governed query without exposing credentials.

The deterministic mode uses the production pipeline, smoke financial
warehouse, lexical/catalog selection and the existing answer validators. It
does not replace a provider integration test; it isolates application and
DuckDB latency so provider latency can be measured separately.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import resource
import time
from pathlib import Path

from agent4.core.config import AppConfig
from agent4.metric_selection.config import MetricSelectionConfig, load_config
from agent4.pipeline import PipelineTrace, run_governed_pipeline

PROJECT_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_DIR = PROJECT_DIR.parent
SMOKE_WAREHOUSE = (
    REPOSITORY_DIR / "portal" / "workspace" / "datasets" / "enterprise-x10-v3-smoke" / "warehouse.duckdb"
)


def _peak_rss_kb() -> int:
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


def _default_warehouse() -> Path:
    configured = os.getenv("AGENT4_DB_PATH") or os.getenv("AGENT4_DB")
    if configured:
        return Path(configured).expanduser().resolve()
    generated = PROJECT_DIR / "data" / "cfo_warehouse.duckdb"
    return generated if generated.is_file() else SMOKE_WAREHOUSE


def _config(provider_mode: str, config_path: str | None) -> MetricSelectionConfig:
    if provider_mode == "deterministic":
        return MetricSelectionConfig(
            llm={"provider": "mock"},
            embedding={"provider": "hashing"},
            retrieval={"mode": "full_catalog"},
        )
    return load_config(config_path or os.getenv("AGENT4_SELECTION_CONFIG"))


def _public_error(response: dict) -> dict | None:
    error = response.get("error")
    if not isinstance(error, dict):
        return None
    return {
        key: error.get(key)
        for key in ("code", "stage", "retryable")
        if key in error
    }


async def _run_once(
    *,
    question: str,
    warehouse: Path,
    selection_config: MetricSelectionConfig,
    query_timeout_ms: int,
) -> dict:
    tenant_id = os.getenv("AGENT4_WAREHOUSE_TENANT_ID", "demo-enterprise")
    claims = {
        "tenant_id": tenant_id,
        "user_id": "phase1-benchmark",
        "roles": ["finance_analyst", "payroll_viewer"],
    }
    policy = {
        "policy_version": "phase1-benchmark",
        "allowed_views": ["mgmt", "tax"],
        "allowed_metrics": None,
        "allowed_branches": ["*"],
        "allowed_departments": ["*"],
    }
    trace = PipelineTrace()
    started = time.perf_counter()
    response = await run_governed_pipeline(
        {
            "api_version": "v1",
            "question": question,
            "locale": "vi-VN",
        },
        claims,
        policy,
        warehouses={tenant_id: warehouse},
        app_config=AppConfig(db_path=warehouse, query_timeout_ms=query_timeout_ms),
        selection_config=selection_config,
        trace=trace,
    )
    return {
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "status": response["status"],
        "error": _public_error(response),
        "pipeline_stage_latency_ms": {
            key: round(value, 3) for key, value in trace.stage_latency_ms.items()
        },
        "pipeline_stage_status": dict(trace.stage_status),
        "pipeline_stage_errors": dict(trace.stage_errors),
        "selection_stage_latency_ms": {
            key: round(value, 3) for key, value in trace.selection.stage_latency_ms.items()
        },
        "selection_stage_breakdown_ms": {
            key: round(value, 3) for key, value in trace.selection.stage_breakdown_ms.items()
        },
        "selection_stage_status": dict(trace.selection.stage_breakdown_status),
        "selection_stage_errors": dict(trace.selection.stage_breakdown_errors),
        "row_count": (response.get("data") or {}).get("row_count"),
        "peak_rss_kb": _peak_rss_kb(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--question",
        default="Doanh thu thuần tháng 08/2026?",
        help="Representative financial question.",
    )
    parser.add_argument("--warehouse", type=Path, default=None)
    parser.add_argument(
        "--provider-mode",
        choices=("deterministic", "configured"),
        default="deterministic",
    )
    parser.add_argument("--config", default=None, help="Metric-selection YAML path.")
    parser.add_argument("--query-timeout-ms", type=int, default=5000)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be positive")

    warehouse = (args.warehouse or _default_warehouse()).expanduser().resolve()
    if not warehouse.is_file():
        parser.error(f"Warehouse does not exist: {warehouse}")
    selection_config = _config(args.provider_mode, args.config)
    runs = [
        asyncio.run(
            _run_once(
                question=args.question,
                warehouse=warehouse,
                selection_config=selection_config,
                query_timeout_ms=args.query_timeout_ms,
            )
        )
        for _ in range(args.repeat)
    ]
    result = {
        "benchmark": "agent4-cloud-query-v1",
        "provider_mode": args.provider_mode,
        "question": args.question,
        "warehouse": str(warehouse),
        "warehouse_size_bytes": warehouse.stat().st_size,
        "repeat": args.repeat,
        "runs": runs,
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
