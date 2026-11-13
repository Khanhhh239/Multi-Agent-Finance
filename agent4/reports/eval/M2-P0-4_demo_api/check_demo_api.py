import json
import sys
from pathlib import Path
from statistics import median
from time import perf_counter

import httpx

from agent4.core.catalog import LEGACY_METRIC_IDS

url, output = sys.argv[1:]
expected = [
    ("ready", {"net_revenue"}, 200),
    ("ready", {"gross_margin_pct"}, 200),
    ("ready", {"cash_and_equivalents"}, 200),
    ("ready", {"net_revenue", "cogs", "gross_profit"}, 200),
    ("ready", {"operating_expenses"}, 200),
    ("ready", {"net_revenue"}, 200),
    ("ready", {"net_profit"}, 200),
    ("ready", {"operating_expenses"}, 200),
    ("ready", {"operating_expenses"}, 200),
    ("needs_clarification", None, 200),
    ("forbidden", None, 403),
    ("unsupported", None, 422),
]

results = []
with httpx.Client(base_url=url, timeout=100, trust_env=False) as client:
    health = client.get("/health").raise_for_status().json()
    questions = client.get("/v1/demo-questions").raise_for_status().json()
    for i, (item, (status, ids, code)) in enumerate(zip(questions, expected, strict=True), 1):
        start = perf_counter()
        resp = client.post(
            "/v1/query",
            headers={"X-Demo-Persona": item.get("persona", "cfo_full")},
            json={
                "api_version": "v1",
                "question": item["question"],
                "locale": item["locale"],
                "options": {"include_evidence_preview": True},
            },
        )
        elapsed_ms = (perf_counter() - start) * 1000
        body = resp.json()
        interp = body.get("interpretation") or {}
        plan = (body.get("demo_evidence") or {}).get("semantic_plan") or {}
        warnings = body["warnings"]
        selected = interp.get("metric_ids", [])
        aliases = [LEGACY_METRIC_IDS.get(mid, mid) for mid in selected]
        checks = {"status": body["status"] == status and resp.status_code == code}
        if ids is not None:
            checks["metrics"] = set(aliases) == ids and len(aliases) == len(ids)
        if i == 3:
            checks["snapshot"] = interp.get("time", {}).get("as_of") == "2025-12-31"
        if i == 5:
            checks["department_breakdown"] = "department_code" in interp.get("dimensions", [])
        if i == 6:
            checks["monthly_range"] = (
                "month" in interp.get("dimensions", [])
                and interp.get("time", {}).get("start") == "2026-01-01"
                and interp.get("time", {}).get("end") == "2026-08-31"
            )
        if i == 7:
            checks["tax_view"] = interp.get("view") == "tax"
        if i in (8, 9):
            checks["vendor_redacted"] = "NCC-MK-DG" not in resp.text and any(
                flt["field"] == "partner_code" and flt["value"] == "[REDACTED]"
                for flt in plan.get("filters", [])
            )
            checks["watermark"] = "partial_data_watermark" in warnings
        if i == 9:
            checks["ytd_range"] = (
                interp.get("time", {}).get("start") == "2026-01-01"
                and interp.get("time", {}).get("end") == "2026-09-30"
            )
        result = {
            "id": item["id"],
            "persona": item.get("persona", "cfo_full"),
            "http_status": resp.status_code,
            "status": body["status"],
            "metric_ids": selected,
            "time": interp.get("time"),
            "view": interp.get("view"),
            "warnings": warnings,
            "error": (body.get("error") or {}).get("code"),
            "duration_ms": round(elapsed_ms, 1),
            "checks": checks,
        }
        results.append(result)
        print(
            item["id"],
            result["status"],
            selected,
            [key for key, ok in checks.items() if not ok],
            flush=True,
        )
summary = {
    "health": health,
    "cases": results,
    "count": len(results),
    "statuses_matched": sum(r["checks"]["status"] for r in results),
    "all_checks_matched": sum(all(r["checks"].values()) for r in results),
    "latency_p50_ms": round(median(r["duration_ms"] for r in results), 1),
}
Path(output).parent.mkdir(parents=True, exist_ok=True)
Path(output).write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print({k: v for k, v in summary.items() if k != "cases"})
sys.exit(0 if summary["all_checks_matched"] == len(results) else 1)
