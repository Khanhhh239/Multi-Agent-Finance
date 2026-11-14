# R2 — bản sửa thời gian P1 đã qua kiểm thử

CR-022 sửa P1-NATIVE-LATE-INVOICE ở native current/history/batch. Nguồn hóa đơn khai báo chưa khả dụng tạo information_gap 0 điểm, không tạo risk hit hoặc coi là no-hit. [Báo cáo bản sửa](p1_native_fix_20261111/REPORT.md).

- **657 regression pass**, 0 lỗi/thất bại/bỏ qua; 10 ca mới. [JSON](p1_native_fix_20261111/native_tests.json). 97 focused và 15 compatibility cũng qua; fixture cũ giữ nguyên checksum toàn bộ rules/features/contract.
- [Audit 7 ca](p1_native_fix_20261111/audit_final/summary.json) exit 0, finding FIXED_IN_TESTED_SCOPE; hai giới hạn biểu diễn legacy vẫn ghi riêng. Không công nhận toàn engine đúng as_of cho header thiếu thời gian hoặc dữ liệu coverage/allocation mà native không biểu diễn.
- [Adapter](p1_native_fix_20261111/native_adapter_time_parity_final.json) giữ gap row/batch. [Service 8766](p1_native_fix_20261111/live_final.json) healthy, snapshot cũ vẫn một bản/3 dòng. [33 feature/model và các kernel khác](p1_native_fix_20261111/preservation_final.json) không đổi; không fit/active, không đổi weight.

R2 tổng thể **PARTIAL**: canonical mới E3/P1, tổng rules_incomplete/null; còn evaluator khác, benchmark E1–E2, D-03/04/09, active/recovery/UI. Backend đang chạy ở http://127.0.0.1:8766, chưa UI workflow/HTTP scoring mới. Bước kế tiếp đề xuất nối API phân tích snapshot có quyền rồi một màn hình demo tối thiểu; chưa triển khai ngầm trong CR-022.

Lịch sử: [CR-021 live run](live_run_20261111/REPORT.md), [CR-020 phát hiện lỗi](p1_recheck_20261111/REPORT.md), [CR-019 evaluator](p1_evaluation_20261111/REPORT.md). Finding OPEN trong evidence cũ là lịch sử trước sửa, không ghi đè. Root overview/index trước lưu trong p1_native_fix_20261111.
