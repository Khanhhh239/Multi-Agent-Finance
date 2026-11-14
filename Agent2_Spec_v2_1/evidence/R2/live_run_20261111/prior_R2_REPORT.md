# R2 — đối chiếu P1 và lỗi native còn mở

R2 tổng thể **PARTIAL**. CR-020: [báo cáo bảy ca](p1_recheck_20261111/REPORT.md), [111 focused pass](p1_recheck_20261111/focused_tests.json). Các ca canonical đạt assertions; **audit exit 2, còn finding native OPEN**, không phải nghiệm thu engine.

**P1-NATIVE-LATE-INVOICE:** raw/native P1 vẫn cho 20 điểm khi hóa đơn chỉ được biết sau khoản chi. Canonical snapshot trả unavailable/null đúng cutoff. Thiếu coverage hoặc mốc phân bổ không có trạng thái tương đương trong legacy hit list; không ép null thành 0. Điểm/tổng/căn cứ và nhóm đồng thời khớp trong bốn tình huống miền chung.

Không sửa runtime/model/weight/active trong lượt này. Cần sửa guard thời gian native và kiểm lại lịch sử/batch. Tổng rules canonical vẫn rules_incomplete/null; chưa full R2 gate hoặc R3.

Lịch sử: [CR-019 evaluator và 640 regression](p1_evaluation_20261111/REPORT.md), [CR-018 input](p1_inputs_20261111/REPORT.md), [CR-017 native parity](rule_parity_20261111/REPORT.md). 640 là lượt đầy đủ trước, không phải chạy lại trong CR-020; mã chấm giữ nguyên. Overview/index trước được lưu trong p1_recheck_20261111.
