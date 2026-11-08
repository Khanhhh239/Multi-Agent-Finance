# A5_003_cold_operational — Người lập có nhiều khoản cận hạn mức

Người rà: `ASSISTANT_SYNTHETIC_REVIEW`. Đánh giá định tính trên dữ liệu mô phỏng; không phải kết luận kế toán độc lập hoặc kết luận gian lận.

**Kết quả nghiệm thu:** Cần sửa/cải thiện. **Giải thích:** Lỗi dựng thẻ. **Ưu tiên:** Hợp lý theo bằng chứng.

## Dữ kiện đã đọc

Khoản 17.145.000 VND có A5 19/20 mẫu, ngưỡng null. Hồ sơ mở theo admission_basis=split_pattern bởi A4: 3 khoản cận hạn mức trong tháng, tổng điểm 3 nhưng ưu tiên trung bình; 2 giao dịch trước là ngữ cảnh.

## Giải thích có dễ hiểu không?

Đã tái hiện TypeError 'Cannot convert undefined or null to object' khi evidenceCard đọc window_days=null. Ngoài lỗi dựng thẻ, cần giải thích vì sao hồ sơ 3 điểm vẫn vào hàng đợi: chính sách rà mẫu A4, không phải A5 hay ngưỡng điểm thông thường.

## Cần chứng từ gì?

- Chứng từ của cả 3 khoản, thẩm quyền theo thời điểm và nghĩa vụ chi tương ứng
- Giải trình các khoản độc lập hoặc lịch thanh toán đã duyệt
- Lịch sử cùng tài khoản nếu có; không hạ số mẫu A5 để đánh giá được

## Mức ưu tiên có hợp lý không?

Trung bình có cơ sở theo tuyến rà mẫu A4 hiện tại; không phải lỗi tính ưu tiên do điểm 3 dưới ngưỡng số học. Chưa khẳng định các khoản cùng nghĩa vụ hay cố ý chia nhỏ.

## Câu diễn giải đề xuất

A5 chưa đủ 20 mẫu; hồ sơ vẫn cần rà vì có 3 khoản cận hạn mức trong tháng theo chính sách A4. Kiểm tra nghĩa vụ từng khoản và các ngoại lệ đã duyệt.

Vấn đề liên quan: RR01, RR05.

[Gói bằng chứng](../evidence/A5_003_cold_operational.json) · [Bảng tổng hợp](../../representative_review_20261018.md).
