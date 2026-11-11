"""Render deterministic, cited answer drafts."""

from agent4.core.catalog import MetricCatalog
from agent4.planning.validator import ValidatedPlan

from .result_validator import safe_display_text


def metric_label(metric: dict, locale: str) -> str:
    label = metric["label"] if locale == "vi-VN" else metric.get("label_en") or metric["label"]
    return safe_display_text(label)


def generate_grounded_answer(
    plan: ValidatedPlan,
    validated_result: dict,
    catalog: MetricCatalog,
    *,
    locale: str = "vi-VN",
) -> dict:
    result = validated_result["result"]
    rows = result["rows"]
    vi = locale == "vi-VN"
    warnings = list(validated_result["warnings"])
    claims = []
    if not rows:
        summary = (
            "Không có dữ liệu phù hợp cho kỳ truy vấn."
            if vi
            else "No matching data for the requested period."
        )
    else:
        row = rows[0]
        group = ", ".join(
            safe_display_text(row[dimension])
            for dimension in plan.dimensions
            if row[dimension] is not None
        )
        for mid in plan.metric_ids:
            metric = catalog.get(mid)
            label = metric_label(metric, locale)
            value = row[mid]
            if value is None:
                text = f"{label} không xác định." if vi else f"{label} is undefined."
            else:
                unit = safe_display_text(metric["unit"])
                text = f"{label} là {value} {unit}." if vi else f"{label} is {value} {unit}."
            if group:
                text = f"({group}) {text}"
            claims.append({"text": text, "source_columns": [mid], "source_rows": [0]})
        summary = " ".join(claim["text"] for claim in claims)
        if len(rows) > 1:
            summary += (
                " Bảng hiển thị các nhóm còn lại." if vi else " See the table for other groups."
            )
    if "partial_data_watermark" in warnings:
        watermark = result["data_watermark"]
        summary += (
            f" Kỳ chưa hoàn chỉnh. Dữ liệu cập nhật đến {watermark}."
            if vi
            else f" The period is incomplete. Data is current through {watermark}."
        )
    return {"summary": summary, "claims": claims, "warnings": warnings, "table_caption": None}
