# R2 — đối chiếu hành vi engine và giữ đủ đầu ra

R2 tổng thể **PARTIAL**. CR-017 đã đối chiếu adapter native với engine trên cùng nguồn/cấu hình và sửa mất cảnh báo sau đóng nhóm. Output chung hiện là **method-output/1.1.0**; input contract/33 feature và kernel/weight giữ nguyên.

- [209 lần đối chiếu](rule_parity_20261111/native_fixture_parity.json) đều khớp trên 696 lượt fixture → 696 kết quả; giữ 70 hit được miễn theo ngoại lệ, 4 batch events và 1 ngoại lệ nhóm. 123 test nghiệp vụ cũ pass trong audit. Đây là lượt fixture, không phải accuracy hoặc giao dịch thật duy nhất.
- **597 tests pass**, 0 skip/failure/error: [JSON](rule_parity_20261111/native_tests.json), [70 focused](rule_parity_20261111/focused_tests.json). [Báo cáo chi tiết](rule_parity_20261111/REPORT.md).
- Đã tái hiện và sửa P1 batch bị bỏ mất: native_rule_diagnostics giữ toàn bộ engine output ngoài scores/hits, có checksum/code binding, tách khỏi điểm dòng. Không cộng điểm nhóm vào dòng hoặc phát queue. Output copy chống alias, scope/participant guards, thiếu kết quả engine vẫn giữ dòng unavailable/null.
- [Parity](parity_report.json): 5 phương pháp số sai số 0; native scores/hits/diagnostics/graph không đổi. [Demo company models](rule_parity_20261111/company_demo/summary.json) dùng current-code artifacts và process riêng; 5/5 mới mỗi DN, không auto-active hoặc kết luận accuracy.

Nguồn canonical vẫn có RuleInputs 35 luật/RuleResult: E3 đánh giá khi đủ nguồn, missing không phải no-hit, tổng chưa đầy đủ rules_incomplete/null. Còn nguồn/evaluator canonical đầy đủ, benchmark E1–E2, D-03/04/09, active/recovery/UI. Stage commands full R2 chưa cấu hình; không duyệt toàn R2/DONE hoặc tự chuyển R3.

Lịch sử: [RuleResult CR-016](rule_results_20261111/REPORT.md), [nguồn CR-015](rule_sources_20261111/REPORT.md), [model jobs CR-013](company_fit_20261111/REPORT.md). Bản overview/fit/parity/map/schema trước được lưu trong rule_parity_20261111; evidence cũ giữ nguyên.
