#!/usr/bin/env python3
"""Gom mọi CSV kết quả trong outputs/ thành bảng Markdown (docs/RESULTS_TABLES.md) — số liệu không chép tay."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
SECTIONS = [
    ("T1-A rolling-origin, miền nguồn src", "t1/A_rolling_origin_src.csv",
     ["setting", "model", "MAE_p50", "pinball_avg", "cov80", "IS80", "IBS_13w", "ECE_4w", "C_index", "WAPE_collect_w1_4", "WAPE_collect_w5_13"]),
    ("T1-B domain adaptation, miền đích tgt (onboard 2024-07)", "t1/B_domain_adaptation_tgt.csv",
     ["months_history", "model", "MAE_p50", "pinball_avg", "cov80", "IBS_13w", "ECE_4w", "WAPE_collect_w1_4", "WAPE_collect_w5_13"]),
    ("T1-C dữ liệu THẬT (Customer Invoices, BPI 2019)", "t1/C_real_domains.csv",
     ["setting", "model", "MAE_p50", "pinball_avg", "cov80", "IBS_13w", "C_index"]),
    ("T2 cure: P(không bao giờ trả | quá hạn)", "t1/D_t2_cure.csv",
     ["world", "model", "n", "base_rate", "PR_AUC", "ROC_AUC", "Brier", "ECE", "expected_loss_vs_actual"]),
    ("T8 lời hứa trả / T9 nguồn nhãn", "t1/EF_t8_t9.csv",
     ["setting", "model", "MAE_p50", "MAE_p50_promised_only", "IBS_13w", "cov80", "WAPE_collect_w1_4"]),
    ("T2 SBA 7(a) thật + T3", "t2_t3/t2_t3_results.csv",
     ["task", "model", "n_test", "ROC_AUC", "PR_AUC", "Brier", "ECE", "mean_p", "base_rate"]),
    ("T4 doanh thu mới", "t4/t4_revenue_forecast.csv", ["setting", "model", "SPL", "SPL_h1_4", "SPL_h5_13", "cov80", "WAPE_p50"]),
    ("T6 số dư 13 tuần — khoảng", "t6/t6_interval_metrics.csv", ["model", "horizon", "cov80", "IS80", "pinball", "MAE_p50"]),
    ("T6 xác suất thiếu hụt", "t6/t6_shortfall_metrics.csv", None),
    ("T7 điểm gãy", "t7/t7_changepoint.csv", None),
    ("T9 khớp sao kê", "t9/t9_reconciliation_tgt.csv", None),
    ("WP-0 hợp đồng dữ liệu", "wp0/world_contract_summary.csv", None),
]


def md(df):
    df = df.copy()
    for c in df.columns:
        if df[c].dtype.kind == "f":
            df[c] = df[c].map(lambda v: "" if pd.isna(v) else f"{v:.4f}" if abs(v) < 10 else f"{v:.1f}")
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(v) for v in r) + " |" for r in df.values]
    return "\n".join(lines)


def main():
    contract_path = OUT / 'wp0/world_contracts.csv'
    if contract_path.exists():
        c = pd.read_csv(contract_path)
        summary = c.groupby('world').agg(checks=('passed', 'size'), passed=('passed', 'sum')).reset_index()
        summary['failed'] = summary['checks'] - summary['passed']
        summary.to_csv(OUT / 'wp0/world_contract_summary.csv', index=False)
    parts = ["# Bảng kết quả (sinh tự động bởi scripts/make_report.py)\n"]
    for title, f, cols in SECTIONS:
        p = OUT / f
        if not p.exists():
            parts.append(f"## {title}\n\n_chưa có `{f}`_\n")
            continue
        df = pd.read_csv(p)
        if 'measurement_version' in df:
            note = 'Giao thức: ' + ', '.join(sorted(df['measurement_version'].dropna().unique()))
        elif f.startswith('wp0/'):
            note = 'Kiểm tra dữ liệu, không phải đo chất lượng mô hình.'
        else:
            note = 'CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.'
        if cols:
            ci_cols = ['pinball_ci_low', 'pinball_ci_high', 'improvement_pct', 'improvement_ci_low', 'improvement_ci_high', 'n_firms', 'bootstrap_n']
            df = df[[c for c in cols + ci_cols if c in df.columns]]
        parts.append(f"## {title}\n\nNguồn: `outputs/{f}`\n\n{note}\n\n{md(df)}\n")
    (ROOT / "docs" / "RESULTS_TABLES.md").write_text("\n".join(parts), encoding="utf-8")
    print("wrote docs/RESULTS_TABLES.md")
    path = ROOT / 'docs/03_Evaluation/04_ket_qua_hien_co.md'
    start, end = '<!-- AUTO:IMPLEMENTATION_RESULTS -->', '<!-- /AUTO:IMPLEMENTATION_RESULTS -->'
    generated = start + '\n\n' + '\n'.join(parts[1:]) + '\n' + end
    existing = path.read_text(encoding='utf-8')
    if start in existing and end in existing:
        left, tail = existing.split(start, 1)
        _, right = tail.split(end, 1)
        existing = left + generated + right
    else:
        existing += '\n\n## 4.11 Kết quả triển khai sinh từ CSV\n\n' + generated + '\n'
    path.write_text(existing, encoding='utf-8')


if __name__ == "__main__":
    sys.exit(main())
