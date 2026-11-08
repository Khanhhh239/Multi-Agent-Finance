from __future__ import annotations

from pathlib import Path
from typing import Any

from src.prepare.common import output_path
from src.reporting.aggregate import COLUMNS, aggregate_runs
from src.reporting.implementation_status import render_implementation_status


def _markdown_table(rows: list[dict[str, Any]]) -> str:
    selected = [
        "model_id",
        "run_id",
        "split",
        "full_images",
        "recognition_cer",
        "detection_f1_50",
        "total_cost_exact_accuracy",
        "timestamp_exact_accuracy",
        "all_four_fields_accuracy",
        "latency_p95_ms",
    ]
    if not rows:
        return "_Chưa có run đã đánh giá._"
    lines = ["| " + " | ".join(selected) + " |", "|" + "|".join(["---"] * len(selected)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(key, "N/A")) for key in selected) + " |")
    return "\n".join(lines)


def render_report(config: dict[str, Any]) -> Path:
    pipeline, vlm = aggregate_runs(config)
    render_implementation_status(config)
    report = f"""# Báo cáo benchmark OCR end-to-end

## Pipeline có tọa độ

{_markdown_table(pipeline)}

## OCR VLM/document parser

{_markdown_table(vlm)}

## Quy tắc đọc kết quả

- `N/A` nghĩa là metric không áp dụng hoặc chưa có ground truth phù hợp; không phải điểm 0.
- Chọn model theo `TOTAL_COST`, `TIMESTAMP`, `SELLER`, recall, sau đó mới xét CER và latency.
- Không diễn giải insertion diagnostic thành hallucination toàn trang vì chưa có transcript đầy đủ.
- Chỉ so latency giữa các run dùng cùng phần cứng và backend.
- Các run có 1–2 ảnh chỉ xác minh kỹ thuật; không dùng để kết luận model tốt hơn trên toàn bộ dữ liệu.

## Trạng thái

- Số run pipeline: {len(pipeline)}
- Số run VLM: {len(vlm)}
- Chi tiết adapter/môi trường: `IMPLEMENTATION_STATUS.md`
"""
    target = output_path(config, "reports") / "FINAL_REPORT.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report, encoding="utf-8")
    return target
