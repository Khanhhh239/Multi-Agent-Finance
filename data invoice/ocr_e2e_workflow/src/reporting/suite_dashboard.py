from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from src.prepare.common import output_path
from src.reporting.aggregate import COLUMNS, write_csv


CHARTS = [
    ("detection_f1_50", "Detection F1 @ IoU 0.5", "detection_f1.svg", True),
    ("recognition_cer", "Recognition CER (thấp hơn tốt hơn)", "recognition_cer.svg", False),
    (
        "all_four_fields_accuracy",
        "Độ chính xác đồng thời 4 trường",
        "all_four_fields_accuracy.svg",
        True,
    ),
    ("latency_p95_ms", "P95 latency (ms, thấp hơn tốt hơn)", "latency_p95_ms.svg", False),
]


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result


def _format_number(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:,.1f}"
    return f"{value:.4f}"


def render_bar_chart(
    rows: list[dict[str, Any]], metric: str, title: str, target: Path, higher_is_better: bool
) -> bool:
    values = [(row, _number(row.get(metric))) for row in rows]
    values = [(row, value) for row, value in values if value is not None]
    if not values:
        return False
    width = 1100
    label_width = 330
    plot_width = 650
    row_height = 54
    height = 95 + row_height * len(values)
    max_value = max(value for _, value in values)
    if metric in {"detection_f1_50", "recognition_cer", "all_four_fields_accuracy"}:
        max_value = max(1.0, max_value)
    else:
        max_value = max(1.0, max_value * 1.08)
    color = "#16835b" if higher_is_better else "#2563a6"
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="24" y="36" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#172033">{html.escape(title)}</text>',
        '<text x="24" y="62" font-family="Arial, sans-serif" font-size="13" fill="#667085">Mỗi model dùng cùng giới hạn mẫu trong suite này.</text>',
    ]
    for index, (row, value) in enumerate(values):
        y = 86 + index * row_height
        label = f"{row.get('model_id')}  (n={row.get('full_images')})"
        bar_width = value / max_value * plot_width
        svg.extend(
            [
                f'<text x="24" y="{y + 22}" font-family="Arial, sans-serif" font-size="14" fill="#344054">{html.escape(label)}</text>',
                f'<rect x="{label_width}" y="{y + 5}" width="{plot_width}" height="25" rx="4" fill="#eef2f6"/>',
                f'<rect x="{label_width}" y="{y + 5}" width="{bar_width:.2f}" height="25" rx="4" fill="{color}"/>',
                f'<text x="{label_width + bar_width + 9:.2f}" y="{y + 23}" font-family="Arial, sans-serif" font-size="13" font-weight="700" fill="#172033">{_format_number(value)}</text>',
            ]
        )
    svg.append("</svg>")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(svg) + "\n", encoding="utf-8")
    return True


def _status_table(statuses: list[dict[str, Any]]) -> str:
    lines = [
        "| Model | Trạng thái | Run ID | Ghi chú |",
        "|---|---|---|---|",
    ]
    for item in statuses:
        note = str(item.get("error") or item.get("note") or "").replace("|", "\\|")
        lines.append(
            f"| {item['model_id']} | {item['status']} | {item.get('run_id', '')} | {note} |"
        )
    return "\n".join(lines)


def _metric_table(rows: list[dict[str, Any]]) -> str:
    selected = [
        "model_id",
        "full_images",
        "recognition_crops",
        "detection_f1_50",
        "recognition_cer",
        "all_four_fields_accuracy",
        "latency_p95_ms",
        "failure_rate",
    ]
    if not rows:
        return "_Chưa có model hoàn thành._"
    lines = ["| " + " | ".join(selected) + " |", "|" + "|".join(["---"] * len(selected)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(key, "N/A")) for key in selected) + " |")
    return "\n".join(lines)


def render_suite_dashboard(
    config: dict[str, Any], suite_id: str, statuses: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> Path:
    suite_dir = output_path(config, "reports") / "suites" / suite_id
    chart_dir = suite_dir / "charts"
    suite_dir.mkdir(parents=True, exist_ok=True)
    write_csv(suite_dir / "leaderboard.csv", rows)
    rendered_charts: list[tuple[str, str]] = []
    for metric, title, filename, higher_is_better in CHARTS:
        if render_bar_chart(rows, metric, title, chart_dir / filename, higher_is_better):
            rendered_charts.append((title, filename))
    chart_markdown = "\n\n".join(
        f"### {title}\n\n![{title}](charts/{filename})" for title, filename in rendered_charts
    ) or "_Chưa đủ dữ liệu để tạo biểu đồ._"
    report = f"""# Kết quả suite `{suite_id}`

## Trạng thái model

{_status_table(statuses)}

## Bảng so sánh

{_metric_table(rows)}

## Biểu đồ

{chart_markdown}

## Cách đọc

- Chỉ so sánh các dòng có cùng `full_images` và `recognition_crops`.
- Detection F1 và độ chính xác trường: cao hơn tốt hơn.
- CER, latency và failure rate: thấp hơn tốt hơn.
- Suite giới hạn 100 mẫu dùng để sàng lọc; không thay thế benchmark toàn bộ dev/test.
"""
    target = suite_dir / "RESULTS.md"
    target.write_text(report, encoding="utf-8")
    return target
