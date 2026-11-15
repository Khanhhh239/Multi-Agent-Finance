"""Render deterministic, cited answer drafts."""

from agent4.core.catalog import MetricCatalog
from agent4.planning.validator import ValidatedPlan

from .result_validator import safe_display_text


def metric_label(metric: dict, locale: str) -> str:
    label = metric["label"] if locale == "vi-VN" else metric.get("label_en") or metric["label"]
    return safe_display_text(label)


def _format_vnd_vi(value: str) -> str:
    """Group an exact, validated decimal string into Vietnamese money units."""
    whole, _, fraction = value.removeprefix("-").partition(".")
    integer = int(whole)
    fraction = fraction.rstrip("0")
    parts = []
    for scale, name in ((10**9, "tỉ"), (10**6, "triệu"), (10**3, "nghìn")):
        group, integer = divmod(integer, scale)
        if group:
            parts.append(f"{group:,} {name}".replace(",", "."))
    if integer or fraction or not parts:
        remainder = f"{integer},{fraction}" if fraction else str(integer)
        if parts and integer < 100:
            parts.append("lẻ")
        parts.append(remainder)
    sign = "âm " if value.startswith("-") and (whole.strip("0") or fraction) else ""
    return f"{sign}{' '.join(parts)} đồng"


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
            for dimension in (
                column["key"] for column in result["columns"] if column["type"] == "string"
            )
            if row[dimension] is not None
        )
        for mid in plan.metric_ids:
            metric = catalog.get(mid)
            label = metric_label(metric, locale)
            value = row[mid]
            if value is None:
                text = f"{label} không xác định." if vi else f"{label} is undefined."
            else:
                unit = safe_display_text(
                    row["component_unit"] if metric["unit"] == "mixed" else metric["unit"]
                )
                amount = _format_vnd_vi(value) if vi and unit == "VND" else f"{value} {unit}"
                text = f"{label} là {amount}." if vi else f"{label} is {amount}."
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
