#!/usr/bin/env python3
"""Gom CSV kết quả vào báo cáo Evaluation — số liệu không chép tay."""
import sys
from pathlib import Path
import json

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
SECTIONS = [
    ("T1-A rolling-origin, miền nguồn src", "t1/A_rolling_origin_src.csv",
     ["setting", "model", "MAE_p50", "pinball_avg", "cov80", "IS80", "IBS_13w", "ECE_4w", "C_index", "WAPE_collect_w1_4", "WAPE_collect_w5_13"]),
    ("T1-B domain adaptation, miền đích tgt (onboard 2024-07)", "t1/B_domain_adaptation_tgt.csv",
     ["months_history", "model", "MAE_p50", "pinball_avg", "cov80", "IBS_13w", "ECE_4w", "WAPE_collect_w1_4", "WAPE_collect_w5_13"]),
    ("T1-C LEGACY v1, chỉ kiểm toán", "t1/C_real_domains.csv",
     ["setting", "model", "MAE_p50", "pinball_avg", "cov80", "IBS_13w", "C_index"]),
    ("T1-C v2 fullweek, refit và BLEND chọn trên quá khứ", "t1/real_v2/C_real_v2.csv",
     ['setting','model','pinball_avg','MAE_p50','cov80','IS80','improvement_vs_B1d_pct','improvement_ci_low','improvement_ci_high']),
    ("G3 CQR hai phía theo kỳ đáo hạn, nguồn", "t1/G3/metrics.csv", None),
    ("P4 đặc trưng dừng, cùng cohort và ngân sách", "t1/P4/metrics.csv", None),
    ("T9 P5 lỗi phân bổ trên DN nguồn", "t9/sprint3/source_allocation_diagnostics.csv", None),
    ("T9 P5 đường precision–coverage và chọn tau trên nguồn", "t9/sprint3/source_precision_coverage.csv", None),
    ("T9 P5 chính sách nguồn trên tgt/retention/COD, không chọn lại trên test", "t9/sprint3/target_metrics.csv", None),
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
    ("Cổng hiện hành", "implementation/gates.csv", None),
    ("Kiểm thử môi trường hiện có và môi trường mới", "implementation/test_summary.csv", None),
    ("Berka thật: phân vị trực tiếp + ACI", "berka/cash_metrics.csv", None),
    ("SBA nhiều chính sách EXEMPT", "t2_t3/t2_sba_variants.csv", None),
    ("T9 precision–coverage (ngưỡng định trước .9)", "t9/precision_coverage.csv", None),
    ("T6 chính sách cảnh báo theo sự kiện", "t6/alert_policy.csv", None),
    ("E2E nguồn→fine-tune từ XML/CSV; trạng thái giao thức trong CSV", "e2e/e2e_metrics.csv", None),
    ("12 hard-case worlds", "data/hard_cases.csv", None),
    ("Hard-case: kiểm tra riêng mục tiêu tình huống", "data/hard_case_fidelity.csv", None),
    ("C2ST cấu trúc", "data/c2st.csv", None),
    ("Benchmark máy phát", "data/generator_benchmark.csv", None),
    ("Lời hứa nhiễu: tính bất biến bảng tài chính", "data/noisy_promise_coupling.csv", None),
    ("Cổng số của 200 mẫu cảnh báo", "service/alert_gate_summary.csv", None),
    ("DA1–DA7: kết luận và bằng chứng còn thiếu", "t1/DA_hypotheses.csv", None),
    ("Ổn định theo seed", "t1/A_seed_cv.csv", None),
    ("T8/T9 trên lời hứa nhiễu", "t1/EF_t8_t9_src_noisy_promises.csv", None),
    ("T9 chẩn đoán phân bổ trên nguồn", "t9/source_allocation_diagnostics.csv", None),
    ("Sinh thế giới lớn", "data/big_worlds.csv", None),
    ("T1 tuned và mặc định cùng ngân sách nguồn", "t1/A_tuned_equal_budget.csv", None),
    ("Kiểm tra mục tiêu tuning", "t1/tuning_comparison.csv", None),
    ("Onboarding: chỉ chọn bằng công ty nguồn giữ lại", "t1/onboarding_source_validation.csv", None),
    ("Scaling nguồn cùng phân phối, hàng khai triển lồng nhau", "t1/scaling_results.csv", None),
    ("Scaling: M* theo tiêu chí định trước", "t1/scaling_M_star.csv", None),
    ("Khác biệt miền: snapshot giữ lại nguyên công ty", "t1/domain_distance.csv", None),
    ("Khác biệt miền: top-10 đặc trưng theo gain", "t1/domain_top_features.csv", None),
    ("DA7: ablation sốc chung và đặc trưng nhanh trong khủng hoảng", "t1/crisis_ablation.csv", None),
    ("Dịch vụ local: kiểm tra một công ty demo, không thay UAT", "service/local_validation.csv", None),
    ("T1: monotone/PDP, daily 28 ngày, mixture và EB ML-II", "t1/T1_variants.csv", None),
    ("T1: CI cặp so mặc định, không tự chọn theo tgt", "t1/T1_variant_decisions.csv", None),
    ("T9→T1: ngân hàng/sổ/nhãn ước lượng, chấm tiền thật", "t1/T9_T1_error_propagation.csv", None),
    ("T9→T1: thu hẹp khoảng cách so nhãn sổ", "t1/T9_T1_gap_reduction.csv", None),
    ("BPI: ablation trường hợp không có hạn thanh toán", "t1/BPI_no_due_ablation.csv", None),
    ("T8: Brier giữ lời, lịch sử đóng băng hàng tuần", "t8/reliability_metrics.csv", None),
    ("T3→T1: lịch sử tranh chấp tại ngày lập", "t1/T3_T1_ablation.csv", None),
    ("DA1–DA4: xác nhận cặp, ngân sách cố định riêng", "t1/DA_paired_metrics.csv", None),
    ("DA1–DA4: CI cặp theo công ty", "t1/DA_paired_comparisons.csv", None),
    ("IW: trọng số và số mẫu hiệu dụng, không phải chỉ số test", "t1/IW_weight_diagnostics.csv", None),
    ("T9: recall riêng các hard cases, nguồn/ngưỡng cố định", "t9/hard_case_recall.csv", None),
    ("T6: ETS/ARIMA/B0, cùng cohort và chuẩn hoá E2E", "t6/traditional/metrics.csv", None),
    ("ETS/ARIMA: số fit hội tụ và lần dùng mốc dự phòng", "t6/traditional/fit_summary.csv", None),
    ("T6: Chronos-Bolt Tiny zero-shot trên số dư tuần", "t6/chronos/metrics.csv", None),
    ("T6: CI cặp mô hình chính so đối chứng thêm", "t6/additional_baseline_comparisons.csv", None),
    ("P0/P1/P2: mô phỏng chính sách thu nợ, không phải tác động nhân quả", "t6/collection_policy/metrics.csv", None),
    ("P2 so P1: cùng công ty và giả định phản hồi", "t6/collection_policy/P2_vs_P1.csv", None),
    ("T7→T6: bộ điều khiển chế độ, hai cửa sổ khủng hoảng", "t7/regime_cash/metrics.csv", None),
    ("DR: 400 công ty mỗi nhánh, kiểm tra sinh dữ liệu", "data/DR_comparison_build.csv", None),
    ("DR: một thế giới so hai mươi thế giới, cùng ngân sách", "t1/DR/metrics.csv", None),
    ("DR: CI cặp và quyết định", "t1/DR/decisions.csv", None),
    ("SBA: cohort trước tại ngày phê duyệt, trễ công bố giả định 90 ngày", "t2_t3/sba_macro_metrics.csv", None),
    ("SBA: CI Brier cặp cho đặc trưng chu kỳ", "t2_t3/sba_macro_comparisons.csv", None),
    ("SBA: hiệu chỉnh theo FY với/không cohort trước", "t2_t3/sba_macro_by_fy.csv", None),
    ("T5: tình huống hợp đồng/hồ sơ mở rộng, chưa xác minh luật", "rules/extended_obligation_cases.csv", None),
    ("T5: 54 tình huống nghiệp vụ theo cấu hình lịch sử", "rules/business_cases.csv", None),
    ("T5: độ phủ phiên bản quy tắc trong bộ hồi quy", "rules/business_case_coverage.csv", None),
    ("T9: trước/trong/sau sốc cung ứng 2022, nguồn chốt trước 2022", "t9/supply_shock_2022/metrics.csv",
        ['method','window','stratum','link_precision','link_precision_ci_low','link_precision_ci_high',
         'link_recall','link_f1','link_f1_ci_low','link_f1_ci_high','auto_txn_coverage','pay_date_MAE_est_days']),
    ("BCTC niêm yết: DSO/DPO mô tả, ba DN-kỳ, chưa đại diện ngành", "data/vn_listed_accounting.csv", None),
    ("DSO máy phát so từng DN công khai, không dùng để hiệu chỉnh", "data/vn_listed_DSO_comparison.csv", None),
    ("Copula phân tầng: lưới IS trên nguồn", "t6/copula_hierarchy/source_grid.csv", None),
    ("Copula phân tầng so một nhân tố: CI cặp trên đích", "t6/copula_hierarchy/metrics.csv", None),
    ("IW: dự đoán bộ phân loại miền ngoài nguyên công ty", "t1/IW_oof/weight_diagnostics.csv", None),
    ("IW ngoài công ty: cùng cohort/ngân sách M6", "t1/IW_oof/metrics.csv", None),
    ("IW ngoài công ty so pooled/in-sample: CI cặp", "t1/IW_oof/comparisons.csv", None),
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
    from analyze_results import main as analyze_results
    analyze_results()
    from record_verification import main as record_verification
    record_verification()
    from evaluate_gates import main as evaluate_gates
    evaluate_gates()
    from implementation_status import main as implementation_status
    implementation_status()
    fit_diagnostics=OUT/'t6/traditional/fit_diagnostics.csv'
    if fit_diagnostics.exists():
        fits=pd.read_csv(fit_diagnostics)
        summary=fits.groupby('model').agg(n_fits=('fallback','size'),fallback_count=('fallback','sum'),
            converged_count=('converged','sum'),warning_count=('warning_count','sum')).reset_index()
        summary['measurement_version']='cash-traditional-same-E2E-cohort-v1'
        summary.to_csv(OUT/'t6/traditional/fit_summary.csv',index=False)
    contract_path = OUT / 'wp0/world_contracts.csv'
    if contract_path.exists():
        c = pd.read_csv(contract_path)
        summary = c.groupby('world').agg(checks=('passed', 'size'), passed=('passed', 'sum')).reset_index()
        summary['failed'] = summary['checks'] - summary['passed']
        summary.to_csv(OUT / 'wp0/world_contract_summary.csv', index=False)
    parts = []
    for title, f, cols in SECTIONS:
        p = OUT / f
        completed_protocol=None
        for prefix,protocol_name in [
            ('t6/collection_policy/','t6/collection_policy/protocol.json'),
            ('t6/copula_hierarchy/','t6/copula_hierarchy/protocol.json'),
            ('t9/supply_shock_2022/','t9/supply_shock_2022/protocol.json'),
            ('t7/regime_cash/','t7/regime_cash/protocol.json'),
            ('t1/DR/','t1/DR/protocol.json'),
            ('t1/IW_oof/','t1/IW_oof/protocol.json'),
            ('t1/G3/','t1/G3/protocol.json'),
            ('t1/P4/','t1/P4/protocol.json'),
            ('t9/sprint3/','t9/sprint3/source_policy.json'),
            ('t2_t3/sba_macro_','t2_t3/sba_macro_protocol.json'),
            ('data/vn_listed_','data/vn_listed_protocol.json'),
            ('rules/extended_obligation_','rules/extended_obligation_protocol.json'),
            ('rules/business_case','rules/business_case_protocol.json')]:
            if f.startswith(prefix):
                protocol=OUT/protocol_name
                completed_protocol=protocol.exists() and json.loads(protocol.read_text(encoding='utf-8')).get('complete',False)
                if f=='t9/sprint3/target_metrics.csv':
                    completed_protocol=completed_protocol and json.loads(protocol.read_text(encoding='utf-8')).get('target_complete',False)
        if completed_protocol is False:
            parts.append(f'## {title}\n\n_Giao thức chưa hoàn tất hoặc đã vô hiệu hoá; CSV tạm không dùng nghiệm thu._\n')
            continue
        if not p.exists():
            parts.append(f"## {title}\n\n_chưa có `{f}`_\n")
            continue
        df = pd.read_csv(p)
        if 'measurement_version' in df:
            note = 'Giao thức: ' + ', '.join(sorted(df['measurement_version'].dropna().unique()))
            hazard=(f.startswith(('t1/','t6/','e2e/','t7/regime_cash/')) and
                f not in ['t1/D_t2_cure.csv','t1/domain_distance.csv'] and not f.startswith(('t6/traditional/','t6/chronos/')))
            if hazard and not df.measurement_version.fillna('').str.contains('fullweek').all():
                note+=' **LEGACY expand trước 20/10/2026: chờ chạy lại, không dùng nghiệm thu hazard mới.**'
        elif f.startswith('wp0/'):
            note = 'Kiểm tra dữ liệu, không phải đo chất lượng mô hình.'
        else:
            note = ('Giao thức bổ sung đã hoàn tất; xem protocol và phạm vi riêng của phép đo.' if completed_protocol else
                'CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.')
        if f=='t9/hard_case_recall.csv':
            protocol=OUT/'t9/hard_cases/protocol.json'
            complete=protocol.exists() and json.loads(protocol.read_text(encoding='utf-8')).get('complete')
            note+=f' Đã đo {df["case"].nunique()}/12 tình huống; giao thức đầy đủ hoàn tất = {complete}.'
            note+=' Kỳ test sau calibration: 2024-07→2025-06, không bao phủ đợt supply_shock 2022; DN mới có lịch sử ngắn hơn (ngày sao kê thực tế trong bảng).'
        if cols:
            ci_cols = ['pinball_ci_low', 'pinball_ci_high', 'improvement_pct', 'improvement_ci_low', 'improvement_ci_high', 'n_firms', 'bootstrap_n']
            df = df[[c for c in dict.fromkeys(cols + ci_cols) if c in df.columns]]
        parts.append(f"## {title}\n\nNguồn: `outputs/{f}`\n\n{note}\n\n{md(df)}\n")
    path = ROOT / 'docs/03_Evaluation/04_ket_qua_hien_co.md'
    start, end = '<!-- AUTO:IMPLEMENTATION_RESULTS -->', '<!-- /AUTO:IMPLEMENTATION_RESULTS -->'
    generated = start + '\n\n' + '\n'.join(parts) + '\n' + end
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
