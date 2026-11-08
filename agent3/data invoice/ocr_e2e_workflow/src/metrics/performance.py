from __future__ import annotations

from typing import Any


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def evaluate_performance(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    latency = [float(row["inference_time_ms"]) for row in predictions if row.get("error") is None]
    failures = sum(row.get("error") is not None for row in predictions)
    return {
        "samples": len(predictions),
        "successful": len(latency),
        "failure_rate": failures / max(1, len(predictions)),
        "latency_mean_ms": sum(latency) / max(1, len(latency)),
        "latency_p50_ms": percentile(latency, 0.50),
        "latency_p90_ms": percentile(latency, 0.90),
        "latency_p95_ms": percentile(latency, 0.95),
        "latency_p99_ms": percentile(latency, 0.99),
        "throughput_images_per_minute": 60000 / (sum(latency) / len(latency)) if latency and sum(latency) else None,
    }

