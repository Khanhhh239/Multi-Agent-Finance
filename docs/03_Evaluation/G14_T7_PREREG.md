# G14 — T7 phát hiện đổi hành vi với khoảng nghỉ: đăng ký trước (22/10/2026, agent1-Khanh)

> Commit **trước khi** đo trên thế giới đích. Mục 1–4 không đổi sau khi xem kết quả.

## 1. Căn cứ (chỉ nguồn, `outputs/t7/sprint5/source_grid.csv`)
Cổng cần cả phát hiện ≥ 0,5 **và** báo giả ≤ 0,5/khách-năm trên thế giới giữ lại. Bộ phát hiện hiện tại (CUSUM k=0,25 h=5, chọn trên src với báo giả ≤ 0,5)
cho src: phát hiện 0,556, báo giả 0,466; trên thế giới giữ lại cũ: 0,524 / 0,633 ⇒ báo giả tăng khi chuyển miền.
Báo giả được đếm theo từng báo động, nên một khách lệch kéo dài bị đếm nhiều lần. **Khoảng nghỉ R ngày** sau mỗi báo động (một đợt = một sự kiện)
chỉ có thể giảm báo giả và không làm mất báo động đầu tiên ⇒ không giảm phát hiện.
Trên nguồn: R = 60 giảm báo giả của CUSUM(0,25; 5) từ 0,466 xuống **0,336** với phát hiện 0,556 và độ trễ 61 ngày không đổi.
(Chỉ 18 khách đủ điều kiện ⇒ tỉ lệ phát hiện có hạt 1/18, không đọc quá kỹ.)

## 2. Quy tắc chọn (đã chạy trên nguồn)
Lưới: CUSUM, Page-Hinkley × tham số T7 sẵn có × R ∈ {0, 30, 60, 90, 120, 180}. Chọn phát hiện cao nhất với báo giả nguồn ≤ **0,35**
(0,5 của cổng trừ biên chuyển miền 0,15 ≈ mức tăng đã thấy 0,466 → 0,633). Kết quả: **CUSUM k=0,25 h=5 R=60** (`choice.json`).
Đối chứng: cấu hình cũ (R=0, báo giả nguồn ≤ 0,5) = CUSUM k=0,25 h=5.

## 3. Đánh giá (một lần, `scripts/sprint5/t7_refractory.py --measure`)
- **Chính (cho dòng cổng `G14_new`):** `tgt2` + `tgt3` gộp — chưa từng dùng cho T7.
- Phụ: tgt + sens_uk + sens_coface (nhóm cũ, đã thấy cấu hình đối chứng; chỉ nối số liệu).
- Chỉ tính khách có ≥ 5 lần trả trong 180 ngày sau điểm gãy; báo động trong giai đoạn sốc vĩ mô báo riêng (như cũ).

## 4. Tiêu chí (không đổi so với G14)
Phát hiện ≥ 0,5 và báo giả ≤ 0,5 trên nhóm chính. Báo cả CI không có (không bootstrap) ⇒ **đạt điểm ước lượng, ghi rõ số khách đủ điều kiện**.

## 5. Kết quả
_Điền sau khi đo._
