# R2 — PARTIAL

CR-027 đã mở API phân tích bốn nhánh luật/thống kê/đồ thị/ML không nhãn, dùng scorer hiện có và artifact cố định riêng theo doanh nghiệp. [Báo cáo tích hợp hiện hành](../R5/four_branch_20261112/REPORT.md), [hướng dẫn](../../../agent2/docs/FOUR_BRANCH_ANALYSIS.md).

- 742 backend pass, gồm 28 kiểm thử mới cho bốn nhánh và 29 API tests. ModelStore read-only, không fit khi chấm, không tự chọn latest; thiếu/sai model trả unavailable/null. Giao dịch không trúng luật vẫn được ML chấm.
- Contract snapshot-analysis/1.1.0 thêm bốn nhánh và nguồn thiếu; giữ DTO nghiệp vụ và view technical có quyền. Analysis ID gắn code/runtime/binding/artifact đọc thực tế.
- Canonical rules chỉ P1/E3 có evaluator, tổng vẫn incomplete/null. Đồ thị cung cấp bối cảnh/căn cứ; thống kê/ML chỉ vị trí tương đối so reference, chưa ngưỡng/ensemble/queue hoặc active release.

Còn evaluator khác/benchmark E1–E2, D-03/04/09, active/recovery/UI quản lý và full gate. Không tuyên bố accuracy/production hoặc DONE. Kernel, 33 feature và cơ chế fit/model cũ được bảo toàn.

Lịch sử: [API CR-023](analysis_api_20261111/REPORT.md), [P1 CR-022](p1_native_fix_20261111/REPORT.md), [live CR-021](live_run_20261111/REPORT.md).
