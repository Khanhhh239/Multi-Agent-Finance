"""Aggregate per-seed benchmark JSON files into mean +/- std markdown tables."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np


def ms(values, pct=False, digits=3):
    v = np.array([x for x in values if x is not None and not np.isnan(x)], dtype=float)
    if len(v) == 0:
        return "n/a"
    scale = 100 if pct else 1
    f = f"{{:.{1 if pct else digits}f}}"
    return f"{f.format(v.mean()*scale)} ± {f.format(v.std(ddof=1)*scale if len(v) > 1 else 0)}"


def temporal_table(results):
    methods = list(results[0]["temporal"])
    lines = ["| Phương pháp | Chế độ | AP | R-precision | P@B3 (%) | Recall@B3 (%) | Vụ tìm thấy@B3 (%) | Báo nhầm ca hợp lệ giống gian lận (%) | Cảnh báo/1000 dòng |",
             "|---|:-:|---:|---:|---:|---:|---:|---:|---:|"]
    for m in methods:
        g = lambda f: [f(r["temporal"][m]) for r in results]
        lines.append(f"| {m} | {results[0]['temporal'][m]['regime']} | {ms(g(lambda x: x['ap']))} | {ms(g(lambda x: x['r_precision']))} | "
                     f"{ms(g(lambda x: x['B3']['precision']), True)} | {ms(g(lambda x: x['B3']['recall']), True)} | "
                     f"{ms(g(lambda x: x['B3']['case_recall']), True)} | {ms(g(lambda x: x['B3']['hard_neg_alert_rate']), True)} | "
                     f"{ms(g(lambda x: x['B3']['alerts_per_1000']), digits=1)} |")
    return "\n".join(lines)


def family_table(results, key="by_family_B3", methods=None):
    methods = methods or list(results[0]["temporal"])
    fams = sorted({f for r in results for m in methods for f in r["temporal"][m][key]})
    lines = ["| Phương pháp | " + " | ".join(fams) + " |", "|---|" + "---:|" * len(fams)]
    for m in methods:
        cells = []
        for f in fams:
            v = [r["temporal"][m][key][f]["recall"] for r in results if f in r["temporal"][m][key]]
            cells.append(f"{100*np.mean(v):.0f}" if v else "-")
        lines.append(f"| {m} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def transfer_tables(results):
    out = []
    if "leave_family_out" in results[0]:
        fams = sorted(results[0]["leave_family_out"])
        methods = list(next(iter(results[0]["leave_family_out"].values())))
        lines = ["| Phương pháp (huấn luyện không có họ đó) | " + " | ".join(fams) + " | trung bình |", "|---|" + "---:|" * (len(fams) + 1)]
        for m in methods:
            cells, means = [], []
            for f in fams:
                v = np.mean([r["leave_family_out"][f][m]["B3_recall"] for r in results])
                cells.append(f"{100*v:.0f}")
                means.append(v)
            lines.append(f"| {m} | " + " | ".join(cells) + f" | {100*np.mean(means):.0f} |")
        out.append("**Recall@B3 (%) trên họ gian lận chưa từng thấy khi huấn luyện (trung bình 5 seed)**\n\n" + "\n".join(lines))
        lines = ["| Phương pháp | " + " | ".join(fams) + " | trung bình |", "|---|" + "---:|" * (len(fams) + 1)]
        for m in methods:
            cells, means = [], []
            for f in fams:
                v = np.mean([r["leave_family_out"][f][m]["ap"] for r in results])
                cells.append(f"{v:.2f}")
                means.append(v)
            lines.append(f"| {m} | " + " | ".join(cells) + f" | {np.mean(means):.2f} |")
        out.append("**AP trên họ chưa từng thấy (nền: 0,003 nếu ngẫu nhiên; AP tính trên họ đó cùng toàn bộ dòng hợp lệ)**\n\n" + "\n".join(lines))
    if "leave_company_out" in results[0]:
        lines = ["| Phương pháp | AP | R-precision | P@B3 (%) | Recall@B3 (%) |", "|---|---:|---:|---:|---:|"]
        for m in results[0]["leave_company_out"]:
            g = lambda k: [r["leave_company_out"][m][k] for r in results]
            lines.append(f"| {m} | {ms(g('ap'))} | {ms(g('r_precision'))} | {ms(g('B3_precision'), True)} | {ms(g('B3_recall'), True)} |")
        out.append("**Công ty chưa từng thấy (huấn luyện trên 7 công ty còn lại, cùng thế giới)**\n\n" + "\n".join(lines))
    return "\n\n".join(out)


def main():
    folder = Path(sys.argv[1])
    results = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]
    text = f"# Tổng hợp {len(results)} seed\n\n## Giao thức theo thời gian (huấn luyện 2024, kiểm thử nửa cuối 2025)\n\n{temporal_table(results)}\n\n" \
           f"## Recall@B3 (%) theo họ gian lận\n\n{family_table(results)}\n\n{transfer_tables(results)}\n"
    (folder / "summary.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
