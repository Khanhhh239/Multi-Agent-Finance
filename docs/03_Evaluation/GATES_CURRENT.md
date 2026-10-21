# Cổng hiện hành (sinh tự động)

Trạng thái pilot: **NO-GO**.

| Cổng | Trạng thái | Bằng chứng / lý do |
|---|---|---|
| G1 | passed | Giảm WAPE >=30% ở hai origin (`outputs/t1/A_rolling_origin_src.csv`) |
| G2 | passed | IBS so với B1 trên hai origin (`outputs/t1/A_rolling_origin_src.csv`) |
| G3 | failed | Mondrian CQR nguồn: cov80 75–85% ở hai gốc và IS80 không xấu hơn CQR hai phía toàn cục (`outputs/t1/G3/metrics.csv`) |
| G4 | failed | ECE4 <=0.05 trên cả hai origin (`outputs/t1/A_rolling_origin_src.csv`) |
| G5 | passed | BLEND w chọn trên calibration; G5 CI: pinball so B1 >=10% và CI thấp so B1d >0; G6 cả ci/bpi: CI cao >=0 và điểm >=-2% (`outputs/t1/real_v2/C_real_v2.csv`) |
| G6 | passed | BLEND w chọn trên calibration; G5 CI: pinball so B1 >=10% và CI thấp so B1d >0; G6 cả ci/bpi: CI cao >=0 và điểm >=-2% (`outputs/t1/real_v2/C_real_v2.csv`) |
| G7 | failed | Fine-tune M12 cải thiện pinball >=10% (`outputs/t1/B_domain_adaptation_tgt.csv`) |
| G8 | failed | SBA drop EXEMPT, kỳ hạn <=120 tháng, nhãn chín trước test (`outputs/t2_t3/t2_sba_variants.csv`) |
| G9 | passed | So mốc doanh thu trên nguồn và đích (`outputs/t4/t4_revenue_forecast.csv`) |
| G10 | passed | Đối chứng thật, có phân biệt cụm series (`outputs/t4/t4_revenue_forecast.csv`) |
| G11 | failed | Quy tắc cần cả hồi quy và xác minh chuyên môn; hiện chưa xác minh (`outputs/rules/rules_review.csv`) |
| G12 | passed | Nhãn T9 ước lượng: cov80 75–85%, IS80 thắng đủ bốn đối chứng, Brier thắng naive (`outputs/e2e/e2e_metrics.csv`) |
| G13 | failed | Isotonic + xác nhận 1 tuần, τ=0.3, chọn trên backtest src; phát hiện 0.94 [0.87; 1.00], báo giả 2.08/công ty-năm (`outputs/e2e/protocol/alert_policy_v2.csv`) |
| G14 | failed | Bộ phát hiện chọn ngưỡng trên nguồn; kết quả giữ lại (`outputs/t7/t7_changepoint.csv`) |
| G15 | failed | T9 P5: tau/ứng viên chọn trên DN nguồn; F1 >=.8, precision >=.95, coverage >=.6, MAE ngày <=3; chưa đổi pipeline E2E (`outputs/t9/sprint3/target_metrics.csv`) |
| G16 | passed | Chèn lỗi có nhãn, precision/recall >=.95 (`outputs/wp0/T0_quality_metrics.csv`) |
| G17 | failed | Giảm MAE >=10% trên lời hứa sạch và nhiễu (`outputs/t1/EF_t8_t9*.csv`) |
| G18 | passed | Điểm ước lượng: T9 thu hẹp >=50% khoảng cách WAPE với oracle ở cả hai chân trời; CI xa còn rộng, không bảo đảm cho mọi DN (`outputs/t1/T9_T1_gap_reduction.csv`) |
| G5_v1 | failed | LEGACY v1: Ensemble vs B1 trên AR thật, cohort đã chín (`outputs/t1/C_real_domains.legacy_expand.csv`) |
| G6_v1 | failed | LEGACY v1: Ensemble không thua B1d trên hai bộ thật (`outputs/t1/C_real_domains.legacy_expand.csv`) |
| G13_v1 | failed | v1 (kiểm toán): ngưỡng theo chi phí từng tuần trên 144 điểm nguồn (`outputs\e2e\protocol\alert_policy.csv`) |
| G13_tgt2 | passed | THAM KHẢO, nhãn oracle (cận trên): 71 sự kiện, phát hiện 0.75 [0.59; 0.84], báo giả 0.75 [0.43; 1.10] (`outputs/tgt2/alert_policy_tgt2.csv`) |
| G15_v1 | failed | LEGACY allocation: WP4: F1 >=.80 và thắng quy tắc, precision >=.95, tự động >=.6, MAE ngày <=3 (`outputs/t9/t9_reconciliation_tgt.csv`) |
