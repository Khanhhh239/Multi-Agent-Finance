# R2 — đầu ra rõ ràng theo từng luật

R2 tổng thể **PARTIAL**. Đã có adapter chung, fit/score riêng theo DN, source bindings 35 luật và RuleResult theo CR-016. Hiện E3 có evaluator canonical khi đủ nguồn; các luật thiếu nguồn hoặc chưa có evaluator trả unavailable, điểm null. Chưa có tổng canonical đầy đủ hoặc benchmark hiệu quả, không mở active/queue/UI.

**Cập nhật CR-016:** [báo cáo kết quả từng luật](rule_results_20261111/REPORT.md), [hướng dẫn](../../../agent2/docs/RULE_RESULTS.md).

- **584 tests pass**, 0 skip/failure/error: [JSON](rule_results_20261111/native_tests.json), [57 focused](rule_results_20261111/focused_tests.json). Thêm 12 ca evaluator/schema/parity/cutoff/missing.
- [Ba ví dụ 5→5](rule_results_20261111/demo/summary.json): E3 có hit, no-hit và thiếu thông tin; mỗi giao dịch đủ 35 kết quả. unavailable có matched/score null với reason/gaps, khác no-hit điểm 0. E3 hit có điểm gốc 3 nhưng đóng góp 0 theo master_quality; không đổi trọng số để tăng cảnh báo.
- Source patch 1.0.1 chỉ lan truyền gap theo vai trò cần dùng, không để hóa đơn thiếu chặn tên NCC đã đủ nguồn. Context/history vẫn theo hai clock, loại nhóm đồng thời, không đưa chứng từ/ID/nhãn vào feature.
- [Parity](rule_results_20261111/parity_report.json): 5 phương pháp số sai số 0; native rule/hits/graph không đổi. [Demo company models](rule_results_20261111/company_demo/summary.json): C001/IF, C002/ECOD mỗi bên chấm 5/5 mới qua process riêng, không phải accuracy.
- [Fit manifest hiện hành](fit_manifest.json) dùng code/feature versions hiện hành, không auto-active. Input contract 1.0.0 và fingerprint feature 33 cột giữ nguyên; model hash adapter cũ vẫn bị từ chối.

Còn lại: bổ sung nguồn/hợp đồng và evaluator cho các luật chưa đủ, parity từng nhóm, benchmark E1–E2, D-03/04/09 và active/recovery/UI. Stage commands cho full R2 chưa cấu hình; không giả READY_FOR_REVIEW/DONE hoặc chuyển R3. Tổng rules vẫn rules_incomplete/null, không cộng tổng một phần.

Lịch sử: [nguồn CR-015](rule_sources_20261111/REPORT.md), [job model CR-013](company_fit_20261111/REPORT.md), [kiểm thử 5→5/no-fit CR-014](adapter_acceptance_20261111/REPORT.md). Bản overview/fit manifest trước CR-016 được giữ tại rule_results_20261111/prior_R2_*.
