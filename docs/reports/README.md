# Báo cáo theo chủ đề

Tiến độ hiện tại nằm ở [STATUS](../STATUS.md); việc tiếp theo nằm ở [BACKLOG](../BACKLOG.md).

[Báo cáo tổng quan Agent 2 — 07/11/2026](app/agent2_overview_20261107.md): mục tiêu, kiến trúc, luật/ML, giao diện, dữ liệu demo, kiểm thử và hướng phát triển.

## Biên bản gần nhất

- [Túi phương pháp chọn theo tiêm gian lận cho ML từng công ty — 08/11](ml/bag_of_methods_injection_20261108.md).
- [Hợp nhất hàng đợi, nhập dữ liệu, ML và phiếu rà tại cổng 8765 — 07/11](app/unified_local_20261107.md).
- [Khóa chính xác tập bằng chứng và ngăn phiếu thừa 12 → 13 — 06/11](ml/ml_review_packet_lock_20261106.md).
- [Bổ sung nhãn giữ nhãn cũ và xử lý xung đột có xác nhận — 06/11](ml/company_ml_labels_20261106.md).
- [Phiếu rà ML trên web: căn cứ, hành động và đồng hồ — 05/11](ml/ml_review_web_20261105.md).
- [Đồng bộ điều kiện CatBoost và tương thích model giữa UI/backend — 05/11](ml/company_ml_readiness_20261105.md).
- [So sánh model riêng từng công ty, cùng kỳ/cùng ngân sách, phiếu hữu ích/phút rà — 04/11](ml/company_ml_comparison_20261104.md).
- [Nhập CSV/Excel, giải thích lỗi trước lưu và chuyển sang chọn ML — 04/11](ml/data_import_20261104.md).
- [Company ML: C001 Isolation Forest / C002 ECOD, cập nhật dữ liệu giữ model — 04/11](ml/company_ml_demo_20261104.md).
- [Nghiệm thu app tích hợp — 39 mẫu/17 luồng, màn hình nhỏ, offline/restart — 29/10](app/release_acceptance_20261029.md).
- [Tồn đầu kỳ, công suất, đồng hồ chờ và SLA của baseline — 28/10](operations/baseline_sla_20261028.md).
- [Tích hợp luật → IF shadow → app → thông báo trên workspace mới — 28/10](app/integrated_rehearsal_20261028.md).
- [Sinh nguồn và kiểm tra độ phủ C4/E2/F2/F3/F4 — 27/10](rules/rule_branch_controls_20261027.md).
- [Thông báo theo vai trò/công ty, nhắc quá hạn và lịch sử gửi — 27/10](app/notification_roles_20261027.md).
- [Giao diện nghiệp vụ hai cấp — Chrome desktop, 360px và 390px — 27/10](app/browser_workflow_20261027.md).
- [Giới hạn trì hoãn baseline trong IF shadow — 27/10](ml/if_delay_guard_20261027.md).
- [Ma trận kiểm thử 35 mã luật, ưu tiên/hàng đợi/SLA và các bản sửa A6/T1/T2 — 27/10](rules/rule_test_matrix_20261027.md).
- [RR09, model v4 và giới hạn ML còn mở](../../reports/rr09_ml_completion_20261024.md).
- [Phân quyền kế toán viên → kế toán trưởng/giám đốc](../../reports/review_roles_20261024.md).
- [B4: thời điểm biết bằng chứng](../../reports/b4_evidence_timing_fix_20261024.md).
- [B2: nhân viên chuyển công ty](../../reports/b2_company_transfer_fix_20261024.md).
- [M01: feature theo cutoff](../../reports/m01_feature_cutoff_fix_20261024.md).
- [M02: bỏ định danh rỗng](../../reports/m02_contact_identity_fix_20261024.md).
- [M03: quan hệ master hiện hành](../../reports/m03_current_relationship_fix_20261024.md).

## Tra cứu theo nhóm

| Nhóm | Nội dung |
| --- | --- |
| [Luật, đồ thị và nguồn](rules/README.md) | Đặc tả, sửa luật, ngưỡng, bằng chứng và nghiệm thu nguồn |
| [ML](ml/README.md) | Feature, model, cửa sổ thời gian, độ phủ, gộp điểm và shadow |
| [App](app/README.md) | Giao diện, P2, browser, rà hồ sơ và phân quyền |
| [Vận hành](operations/README.md) | Backup, khôi phục và phát hành |
| [Kế hoạch tham chiếu](history/README.md) | Kế hoạch theo mốc cũ; xem backlog hiện tại để chọn việc |

Các thư mục kết quả máy vẫn ở [reports](../../reports/README.md). Một số báo cáo cũ giữ đường dẫn gốc để bảo toàn manifest/hash và bộ đóng gói; mục lục nhóm liên kết trực tiếp tới chúng.
