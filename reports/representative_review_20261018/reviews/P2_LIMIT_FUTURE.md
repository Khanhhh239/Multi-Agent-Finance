# P2_LIMIT_FUTURE — Xác minh hạn mức chỉ có sau thời điểm chi

Người rà: `ASSISTANT_SYNTHETIC_REVIEW`. Đánh giá định tính trên dữ liệu mô phỏng; không phải kết luận kế toán độc lập hoặc kết luận gian lận.

**Kết quả nghiệm thu:** Cần sửa/cải thiện. **Giải thích:** Cần rõ hơn. **Ưu tiên:** Hợp lý theo bằng chứng.

## Dữ kiện đã đọc

Khoản 2.000.001 VND so với hạn mức 2.000.000 có trạng thái not_known_at_payment; tại lúc chi chưa có xác minh, P2 0 điểm/thấp.

## Giải thích có dễ hiểu không?

Trạng thái đúng nhưng bản chứng minh bị trả về null nên người dùng không nhìn được mốc xác minh đến sau. Cần hiển thị mốc bị loại khỏi đánh giá, có nhãn không dùng làm bằng chứng quá khứ.

## Cần chứng từ gì?

- Nguồn xác minh hạn mức đã có tại thời điểm chi nếu tồn tại
- Nhật ký thời điểm xác minh và hóa đơn/phiếu chi

## Mức ưu tiên có hợp lý không?

Giữ yêu cầu bổ sung thấp là hợp lý theo thời điểm, không dùng xác minh tương lai để chấm vi phạm quá khứ.

## Câu diễn giải đề xuất

Xác minh hạn mức chỉ được biết sau khoản chi; tại thời điểm chi chưa đủ căn cứ chấm vượt hạn mức.

Vấn đề liên quan: RR04.

[Gói bằng chứng](../evidence/P2_LIMIT_FUTURE.json) · [Bảng tổng hợp](../../representative_review_20261018.md).
