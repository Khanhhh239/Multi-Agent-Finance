from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from src.prepare.common import output_path
from src.utils import read_json


COLUMNS = [
    "model_id",
    "model_revision",
    "run_id",
    "split",
    "output_mode",
    "full_images",
    "recognition_crops",
    "location_support",
    "detection_precision_50",
    "detection_recall_50",
    "detection_f1_50",
    "recognition_cer",
    "recognition_wer",
    "recognition_em",
    "key_field_e2e_exact_f1",
    "key_field_e2e_soft_f1",
    "seller_em",
    "address_similarity",
    "timestamp_exact_accuracy",
    "total_cost_exact_accuracy",
    "all_four_fields_accuracy",
    "insertion_rate",
    "blank_image_text_rate",
    "unsupported_field_rate",
    "latency_p50_ms",
    "latency_p95_ms",
    "failure_rate",
]


def _get(value: dict[str, Any], *path: str, default: Any = "N/A") -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def flatten(summary: dict[str, Any]) -> dict[str, Any]:
    threshold = _get(summary, "detection", "thresholds", "0.5", "micro", default={})
    if threshold == "N/A":
        threshold = {}
    spotting = summary.get("text_spotting", {})
    fields = summary.get("fields", {})
    recognition = summary.get("recognition_normalized", {})
    diagnostic = summary.get("hallucination_diagnostics", {})
    performance = summary.get("performance", {})
    return {
        "model_id": summary.get("model_id"),
        "model_revision": summary.get("model_revision"),
        "run_id": summary.get("run_id"),
        "split": summary.get("split"),
        "output_mode": summary.get("output_mode"),
        "full_images": _get(summary, "sample_counts", "full_images"),
        "recognition_crops": _get(summary, "sample_counts", "recognition_crops"),
        "location_support": summary.get("location_support"),
        "detection_precision_50": threshold.get("precision", "N/A"),
        "detection_recall_50": threshold.get("recall", "N/A"),
        "detection_f1_50": threshold.get("f1", "N/A"),
        "recognition_cer": recognition.get("cer_micro", "N/A"),
        "recognition_wer": recognition.get("wer_micro", "N/A"),
        "recognition_em": recognition.get("exact_match", "N/A"),
        "key_field_e2e_exact_f1": _get(spotting, "exact", "f1"),
        "key_field_e2e_soft_f1": _get(spotting, "soft", "f1"),
        "seller_em": _get(fields, "seller", "exact_accuracy"),
        "address_similarity": _get(fields, "address", "similarity_macro"),
        "timestamp_exact_accuracy": _get(fields, "timestamp", "exact_accuracy"),
        "total_cost_exact_accuracy": _get(fields, "total_cost", "exact_accuracy"),
        "all_four_fields_accuracy": fields.get("all_four_fields_accuracy", "N/A"),
        "insertion_rate": diagnostic.get("recognition_insertion_rate", "N/A"),
        "blank_image_text_rate": diagnostic.get("blank_image_text_rate", "N/A"),
        "unsupported_field_rate": diagnostic.get("unsupported_field_rate", "N/A"),
        "latency_p50_ms": performance.get("latency_p50_ms", "N/A"),
        "latency_p95_ms": performance.get("latency_p95_ms", "N/A"),
        "failure_rate": performance.get("failure_rate", "N/A"),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def aggregate_runs(config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    run_root = output_path(config, "runs")
    rows = []
    if run_root.exists():
        for summary_path in sorted(run_root.glob("*/metrics/summary.json")):
            if (summary_path.parents[1] / "REPORT_EXCLUDE.txt").is_file():
                continue
            rows.append(flatten(read_json(summary_path)))
    pipeline = [row for row in rows if row["location_support"]]
    vlm = [row for row in rows if not row["location_support"]]
    report_root = output_path(config, "reports")
    write_csv(report_root / "leaderboard_pipeline.csv", pipeline)
    write_csv(report_root / "leaderboard_vlm.csv", vlm)
    return pipeline, vlm
