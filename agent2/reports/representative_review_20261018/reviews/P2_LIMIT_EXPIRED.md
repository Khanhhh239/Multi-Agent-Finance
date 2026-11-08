# P2_LIMIT_EXPIRED — Hạn mức đã hết hiệu lực lúc chi

Người rà: `ASSISTANT_SYNTHETIC_REVIEW`. Đánh giá định tính trên dữ liệu mô phỏng; không phải kết luận kế toán độc lập hoặc kết luận gian lận.

**Kết quả nghiệm thu:** Cần sửa/cải thiện. **Giải thích:** Cần rõ hơn. **Ưu tiên:** Hợp lý theo bằng chứng.

## Dữ kiện đã đọc

Khoản chi lúc 11:00 ngày 12/08/2025; effective_to của hạn mức cũng là mốc này. Snapshot dùng khoảng hiệu lực loại trừ mốc cuối, nên trạng thái outside_effective_period và 0 điểm/thấp.

## Giải thích có dễ hiểu không?

UI nói ngoài hiệu lực nhưng chỉ hiện ngày xác minh, chưa hiện hiệu lực từ/đến và quy tắc mốc cuối; dễ nhầm với LIMIT_VERIFIED.

## Cần chứng từ gì?

- Quyết định hạn mức còn hiệu lực hoặc văn bản gia hạn
- Thời điểm hiệu lực chính xác và hóa đơn/phiếu chi

## Mức ưu tiên có hợp lý không?

Thấp của yêu cầu bổ sung là hợp lý vì chưa có hạn mức áp dụng ở thời điểm này. Không coi bằng chứng hết hiệu lực là hạn mức hiện hành.

## Câu diễn giải đề xuất

Hạn mức hết hiệu lực đúng mốc 11:00, không bao gồm khoản chi tại mốc cuối; cần quyết định còn hiệu lực để đánh giá.

Vấn đề liên quan: RR04.

[Gói bằng chứng](../evidence/P2_LIMIT_EXPIRED.json) · [Bảng tổng hợp](../../representative_review_20261018.md).
