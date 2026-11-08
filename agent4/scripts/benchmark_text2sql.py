from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from agent4.text2sql.models import AuthContext, make_query_request
from agent4.text2sql.service import build_default_service

QUESTIONS = [
    "Doanh thu thuần quý 3 năm 2026",
    "Lợi nhuận gộp tháng 10/2026",
    "Biên lợi nhuận gộp quý 3/2026",
    "Số dư tiền cuối tháng 10/2026",
    "Dòng tiền thuần tháng 10/2026",
    "Tuổi nợ ngày 14/10/2026",
    "Top 5 hóa đơn lớn nhất tháng 10/2026",
]


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * p))]


def main() -> None:
    service = build_default_service()
    auth = AuthContext(
        user_id="benchmark", tenant_id="tenant_demo_A", roles=frozenset({"finance_analyst"}),
        allowed_views=frozenset({"mgmt", "tax"}),
    )
    durations: list[float] = []
    statuses: dict[str, int] = {}
    for _ in range(10):
        for question in QUESTIONS:
            started = time.perf_counter()
            response = service.query(make_query_request(question), auth)
            durations.append((time.perf_counter() - started) * 1000)
            statuses[response.status] = statuses.get(response.status, 0) + 1
    report = {
        "mode": "synthetic_duckdb_offline",
        "queries": len(durations),
        "hardware_note": "local development container; not a production SLO measurement",
        "p50_ms": round(statistics.median(durations), 3),
        "p95_ms": round(percentile(durations, 0.95), 3),
        "max_ms": round(max(durations), 3),
        "statuses": statuses,
    }
    destination = Path("reports/performance/latency_summary.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
