# P2_INSTALL_MIXED — Một đợt ngân hàng và một đợt tiền mặt

Người rà: `ASSISTANT_SYNTHETIC_REVIEW`. Đánh giá định tính trên dữ liệu mô phỏng; không phải kết luận kế toán độc lập hoặc kết luận gian lận.

**Kết quả nghiệm thu:** Cần sửa/cải thiện. **Giải thích:** Cần rõ hơn. **Ưu tiên:** Hợp lý theo bằng chứng.

## Dữ kiện đã đọc

Hóa đơn 20.000.000 VND được trả 19.000.000 qua ngân hàng và 1.000.000 tiền mặt; P2 chỉ ở đợt tiền mặt, 8 điểm/trung bình. A1 được giải trình bằng AGR_CONTROL. Invoice.recorded_at là thời điểm đợt sau.

## Giải thích có dễ hiểu không?

Cần hiển thị tổng hợp hai kênh và lý do khoản tiền mặt 1.000.000 vẫn được đối chiếu theo hóa đơn. Câu ngoại lệ A1 hiện chưa cho người đọc xem đủ căn cứ thỏa thuận và tổng được phép.

## Cần chứng từ gì?

- Hóa đơn, sao kê đợt 19.000.000 và phiếu chi 1.000.000
- AGR_CONTROL/CONTRACT_CONTROL và phê duyệt gắn đúng nghĩa vụ
- Lịch sử biết hóa đơn trước đợt đầu

## Mức ưu tiên có hợp lý không?

Giữ trung bình cho P2 và không cộng nghi vấn chia nhỏ đã được giải trình là hợp lý trong mẫu; không chứng nhận nghĩa vụ chi là thật.

## Câu diễn giải đề xuất

Cùng hóa đơn 20.000.000 VND có hai kênh thanh toán; cần rà riêng đợt tiền mặt 1.000.000 VND. Mẫu chia nhỏ A1 đã có thỏa thuận giải trình.

Vấn đề liên quan: RR04, RR05, RR08.

[Gói bằng chứng](../evidence/P2_INSTALL_MIXED.json) · [Bảng tổng hợp](../../representative_review_20261018.md).
