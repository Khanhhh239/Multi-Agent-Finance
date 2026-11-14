# R2 — đánh giá P1 và trạng thái hiện tại

R2 tổng thể **PARTIAL**. CR-019 đã nối [evaluator P1](p1_evaluation_20261111/REPORT.md), sau [đầu vào CR-018](p1_inputs_20261111/REPORT.md).

- **640 tests pass**, 0 lỗi/thất bại/bỏ qua, gồm 24 ca P1 mới. [Hồi quy](p1_evaluation_20261111/native_tests.json), [68 focused](p1_evaluation_20261111/focused_tests.json).
- [Native parity](p1_evaluation_20261111/native_parity.json): 8 tình huống/16 dòng khớp miền dương/một hóa đơn, có lịch sử 45 ngày và đồng thời. Signed corrections kiểm riêng; không tuyên bố native hỗ trợ âm hoặc accuracy.
- P1 dùng phân bổ có liên kết/coverage, giữ điều chỉnh có dấu và revision. Row dùng prior + current; kiểm nhóm riêng không cộng vào điểm dòng. Thiếu nguồn/mâu thuẫn → unavailable/null. [Demo](p1_evaluation_20261111/demo/summary.json), [hướng dẫn](../../../agent2/docs/P1_EVALUATION.md).
- RuleInputs 1.1.1, evaluator P1 1.0.0; shape RuleResult 1.0.0/method-output 1.1.0 giữ nguyên. Cả input schema, 33 feature, kernel và model code/runtime không đổi. Không fit nghiệp vụ/đổi active; [fit manifest](fit_manifest.json) vẫn là lịch sử CR-017 tương thích về model/feature code.

Canonical có E3/P1, tổng rules vẫn rules_incomplete/null. Còn evaluator khác, benchmark E1–E2, D-03/04/09, active/recovery/UI. Full R2 stage command chưa cấu hình; không tự duyệt toàn R2/DONE hoặc chuyển R3. Kiểm nhóm là diagnostics, chưa phát event/queue.

Evidence cũ giữ nguyên: [CR-017](rule_parity_20261111/REPORT.md), [CR-018](p1_inputs_20261111/REPORT.md). Root overview/index/map trước CR-019 lưu trong p1_evaluation_20261111.
