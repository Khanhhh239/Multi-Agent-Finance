# R2 — đầu vào P1 và trạng thái hiện tại

R2 tổng thể **PARTIAL**. CR-018 đã bổ sung đầu vào P1, chưa bật evaluator/tính điểm P1. [Báo cáo chi tiết](p1_inputs_20261111/REPORT.md), [hướng dẫn và mẫu](../../../agent2/docs/P1_INPUTS.md).

- Input contract **1.1.0** thêm kênh thanh toán và khai báo phạm vi lịch sử theo hóa đơn, thời gian, manifest refs/count/checksum. Schema 1.0.0 vẫn đọc được; snapshot cũ không bị sửa.
- Thiếu/unknown kênh, lịch sử partial/unknown/bounded hoặc khai báo stale/mâu thuẫn: P1 input unavailable kèm lý do. Không suy từ tài khoản hoặc thay lịch sử thiếu bằng 0. Manifest sai bị reject trước lưu; giữ số âm điều chỉnh hợp lệ.
- **616 tests pass**, 0 skip/failure/error; có 19 ca P1 mới. [Hồi quy](p1_inputs_20261111/native_tests.json), [demo](p1_inputs_20261111/demo/summary.json): 6 đầu vào → 6 kết quả, retry cùng yêu cầu giữ cùng snapshot. Dữ liệu mô phỏng, không chứng minh accuracy hoặc đủ sổ bên ngoài.
- RuleInputs **1.1.0** bổ sung nguồn P1 theo cutoff từng giao dịch; đủ nguồn khai báo vẫn trả P1 rule_evaluator_unavailable/null. Feature contract 33 cột, kernel, model implementation và method-output/1.1.0 giữ nguyên. Không fit hoặc đổi active model trong bước này; [fit manifest trước](fit_manifest.json) vẫn là lịch sử fit CR-017.

CR-017 đã đối chiếu 209 lượt native trên 696 lượt fixture → 696 kết quả, giữ cả cảnh báo nhóm và ngoại lệ: [báo cáo](rule_parity_20261111/REPORT.md). Đây là evidence lịch sử của phần adapter/kernel giữ nguyên, không phải benchmark mới của P1 canonical.

Canonical hiện chỉ có evaluator E3; tổng rules vẫn rules_incomplete/null. Còn evaluator P1 và các luật khác, benchmark E1–E2, D-03/04/09, active/recovery/UI. Full R2 stage command chưa cấu hình; không tự duyệt toàn R2/DONE hoặc chuyển R3.

Evidence cũ được giữ nguyên; bản overview/index/map trước CR-018 được lưu trong p1_inputs_20261111.
