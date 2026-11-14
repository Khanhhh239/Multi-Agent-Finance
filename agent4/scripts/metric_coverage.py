"""Report which registry metrics have governed SQL and evaluation evidence."""

import argparse
import json
from collections import Counter
from pathlib import Path

from agent4.core.catalog import CANONICAL_TO_LEGACY, MetricCatalog
from agent4.engine.metrics import REGISTRY
from agent4.sql.compiler import _VERIFIED_BINDINGS
from agent4.text2sql.catalog import CatalogSnapshot
from vals.run_eval import DEFAULT_DATASET, load_cases

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/metric_coverage_66.md"


def render_coverage() -> str:
    catalog = MetricCatalog(canonical=True)
    demo_visible = {
        metric["metric_id"]
        for metric in catalog.list_visible_metrics(
            {"allowed_views": ["mgmt", "tax"], "roles": ["finance_analyst", "payroll_viewer"]}
        )
    }
    reference = json.loads((ROOT / "data/eval/mpx10-v3-reference.json").read_text(encoding="utf-8"))
    reference_counts = Counter(key.rsplit(" [", 1)[0] for key in reference["catalog_baseline"])
    cases = load_cases(DEFAULT_DATASET)
    dev_counts = Counter(metric_id for case in cases for metric_id in case.expected_metric_ids)
    reviewed = Counter(
        metric_id
        for case in cases
        if case.expected_result is not None
        for metric_id in case.expected_metric_ids
    )
    synthetic = CatalogSnapshot()
    lines = [
        "# Coverage của 66 metric canonical",
        "",
        "Báo cáo sinh bởi `python -m scripts.metric_coverage`.",
        f"Catalog runtime `{catalog.get_catalog_hash()}`.",
        "",
        f"Web demo liệt kê {len(REGISTRY.keys() & demo_visible)}/{len(REGISTRY)} ID trong registry.",
        "Metric hiển thị bổ sung nằm ngoài registry gồm "
        + ", ".join(f"`{metric_id}`" for metric_id in sorted(demo_visible - REGISTRY.keys()))
        + ".",
        "",
        "- **Nguồn** ghi binding hiện có của pipeline governed. `metadata` là mô tả registry.",
        "- **Chiều** và **view** ghi khai báo của catalog. Từng tổ hợp chiều, filter và kỳ",
        "  vẫn cần fixture thực thi để xác nhận hỗ trợ.",
        "- **Synthetic** là trạng thái của adapter Text-to-SQL đời trước trên fixture riêng.",
        "- **MPX10** đếm cặp metric/view từ catalog baseline đóng băng. `legacy` dùng ID",
        "  tương thích và có thể khác đơn vị. Cột này ghi bằng chứng hồi quy catalog.",
        "- **Dev** đếm số câu có ID trong nhãn. **Số liệu đã duyệt** đếm `expected_result`",
        "  đã review độc lập trong bộ dev hiện tại.",
        "",
        "| Metric | Kiểu | Nhãn EN / alias | Nguồn | View | Chiều | Web | Synthetic | MPX10 | Dev | Số liệu đã duyệt |",
        "|---|---|---:|---|---|---|---|---|---:|---:|---:|",
    ]
    for metric_id, spec in REGISTRY.items():
        definition = catalog.get(metric_id)
        if definition is None:
            raise ValueError(f"Registry ID missing from governed catalog: {metric_id}")
        binding = _VERIFIED_BINDINGS.get(metric_id)
        if catalog.has_verified_sql_handler(metric_id) != (binding is not None) or (
            binding is not None
            and (definition.get("base_relation"), definition.get("sql_expr")) != binding
        ):
            raise ValueError(f"Catalog and compiler disagree on {metric_id}")
        source = binding[0] if binding else "metadata"
        en = "có" if definition.get("label_en") else "thiếu"
        legacy_count = reference_counts[CANONICAL_TO_LEGACY.get(metric_id, metric_id)]
        reference_count = str(reference_counts[metric_id])
        if not reference_counts[metric_id] and legacy_count:
            reference_count = f"{legacy_count} legacy"
        row = (
            f"`{metric_id}`",
            f"{spec.kind}/{spec.period_type}",
            f"{en} / {len(definition['aliases'])}",
            source,
            ", ".join(definition["supported_views"]),
            ", ".join(definition["supported_dimensions"]) or "—",
            "có" if metric_id in demo_visible else "—",
            synthetic.capability(metric_id).synthetic_status,
            reference_count,
            str(dev_counts[metric_id]),
            str(reviewed[metric_id]),
        )
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Check the committed Markdown snapshot"
    )
    args = parser.parse_args()
    report = render_coverage()
    if args.check:
        if REPORT.read_text(encoding="utf-8") != report:
            raise SystemExit(
                "Metric coverage snapshot differs from the current catalog or evidence"
            )
        print(f"Metric coverage snapshot matches all {len(REGISTRY)} registry IDs")
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
