# P2_INSTALL_CASH — Hai đợt tiền mặt nhỏ thuộc một hóa đơn lớn

Người rà: `ASSISTANT_SYNTHETIC_REVIEW`. Đánh giá định tính trên dữ liệu mô phỏng; không phải kết luận kế toán độc lập hoặc kết luận gian lận.

**Kết quả nghiệm thu:** Cần sửa/cải thiện. **Giải thích:** Cần rõ hơn. **Ưu tiên:** Hợp lý theo bằng chứng.

## Dữ kiện đã đọc

Hai khoản tiền mặt 3.000.000 VND thuộc cùng hóa đơn 12.000.000 VND. Mỗi khoản có P2 8 điểm; hồ sơ trung bình có max_score 9. Invoice.recorded_at lại là 14/08, sau khoản đầu 12/08.

## Giải thích có dễ hiểu không?

Cần giải thích P2 được phát theo tổng hóa đơn chứ không chỉ số tiền từng đợt, và giải thích phần điểm lặp lại. Mốc recorded_at có dấu hiệu bị cập nhật theo đợt cuối trong bộ dựng nguồn; cần tách thời điểm biết đầu tiên với cập nhật sau.

## Cần chứng từ gì?

- Hóa đơn 12.000.000 VND và lịch thanh toán
- Hai phiếu chi, số đã trả/còn phải trả
- Lịch sử phiên bản hóa đơn chứng minh đã biết ở khoản đầu

## Mức ưu tiên có hợp lý không?

Trung bình là hợp lý cho đối chiếu thanh toán của hóa đơn. Chưa có cơ sở gọi hai khoản là cố ý chia nhỏ hoặc tự tăng mức ưu tiên.

## Câu diễn giải đề xuất

Mỗi đợt chi 3.000.000 VND nhưng cùng hóa đơn 12.000.000 VND vượt ngưỡng của snapshot; cần đối chiếu cả lịch thanh toán.

Vấn đề liên quan: RR04, RR05.

[Gói bằng chứng](../evidence/P2_INSTALL_CASH.json) · [Bảng tổng hợp](../../representative_review_20261018.md).
