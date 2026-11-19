"""Run a bounded Agent 4 ASGI workload and report only safe measurements.

This harness is executed inside the production image with Docker cgroup limits. It
injects a test-only trusted gateway context in-process so the benchmark can exercise
the cloud query path without putting a bypass into the production entrypoint.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from agent4.api import create_cloud_app
from agent4.metric_selection.config import MetricSelectionConfig, load_config

_CLAIMS = {"tenant_id": "tenant-a", "user_id": "benchmark-user", "roles": ["finance_analyst"]}
_POLICY = {
    "allowed_views": ["mgmt", "tax", "gl"],
    "allowed_metrics": ["net_revenue", "gross_profit", "gross_margin_pct"],
    "allowed_branches": ["*"],
    "allowed_departments": ["*"],
    "policy_version": "cloud-benchmark-v1",
}
_PAYLOAD = {
    "api_version": "v1",
    "question": "Doanh thu thuần tháng 08/2026?",
    "locale": "vi-VN",
}


def _read_int(path: str) -> int | None:
    try:
        return int(Path(path).read_text(encoding="ascii").strip())
    except (FileNotFoundError, OSError, ValueError):
        return None


def _memory_snapshot() -> dict[str, Any]:
    current = _read_int("/sys/fs/cgroup/memory.current")
    peak = _read_int("/sys/fs/cgroup/memory.peak")
    events: dict[str, int] = {}
    try:
        for line in Path("/sys/fs/cgroup/memory.events").read_text(encoding="ascii").splitlines():
            key, value = line.split(maxsplit=1)
            events[key] = int(value)
    except (FileNotFoundError, OSError, ValueError):
        pass
    return {
        "current_bytes": current,
        "peak_bytes": peak,
        "peak_mib": round(peak / 1024 / 1024, 2) if peak is not None else None,
        "oom": bool(events.get("oom", 0)),
        "oom_kill": events.get("oom_kill", 0),
    }


def _safe_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = body.get("error") if isinstance(body, dict) else None
    data = body.get("data") if isinstance(body, dict) else None
    return {
        "status_code": response.status_code,
        "status": body.get("status") if isinstance(body, dict) else None,
        "error_code": error.get("code") if isinstance(error, dict) else None,
        "error_stage": error.get("stage") if isinstance(error, dict) else None,
        "retryable": error.get("retryable") if isinstance(error, dict) else None,
        "row_count": data.get("row_count") if isinstance(data, dict) else None,
    }


async def _query(client: httpx.AsyncClient) -> dict[str, Any]:
    started = time.perf_counter()
    response = await client.post("/v1/query", json=_PAYLOAD)
    result = _safe_response(response)
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return result


async def _run(mode: str, warehouse: Path) -> dict[str, Any]:
    started = time.perf_counter()
    if mode == "deterministic":
        config = MetricSelectionConfig(
            llm={"provider": "mock", "model": "cloud-benchmark-model"},
            embedding={"provider": "hashing"},
            retrieval={"mode": "full_catalog"},
        )
        allow_test_providers = True
    else:
        config = load_config(os.getenv("AGENT4_SELECTION_CONFIG"))
        allow_test_providers = False
    app = create_cloud_app(
        warehouses={"tenant-a": warehouse},
        selection_config=config,
        allow_test_providers=allow_test_providers,
    )

    @app.middleware("http")
    async def test_gateway_context(request, call_next):
        request.state.idp_claims = _CLAIMS
        request.state.server_policy = _POLICY
        return await call_next(request)

    startup_ms = round((time.perf_counter() - started) * 1000, 3)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        idle_memory = _memory_snapshot()
        cold = await _query(client)
        warm = [await _query(client) for _ in range(3)]
        concurrent = await asyncio.gather(_query(client), _query(client))
    return {
        "mode": mode,
        "startup_ms": startup_ms,
        "idle_memory": idle_memory,
        "cold": cold,
        "warm": warm,
        "concurrent": concurrent,
        "final_memory": _memory_snapshot(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("deterministic", "configured"), default="deterministic")
    parser.add_argument("--warehouse", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_run(args.mode, args.warehouse)), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
