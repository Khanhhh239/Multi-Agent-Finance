# P2_REVERSAL_JOURNAL — Đảo bút toán, không có khoản chi mới

Người rà: `ASSISTANT_SYNTHETIC_REVIEW`. Đánh giá định tính trên dữ liệu mô phỏng; không phải kết luận kế toán độc lập hoặc kết luận gian lận.

**Kết quả nghiệm thu:** Cần sửa/cải thiện. **Giải thích:** Cần rõ hơn. **Ưu tiên:** Hợp lý có điều kiện.

## Dữ kiện đã đọc

Khoản chi 5.000.000 VND có P2; dòng đảo Nợ 111/Có 642 mang payment_channel=journal và không có P2. Liên kết nguồn vẫn mang loại cash_return_of.

## Giải thích có dễ hiểu không?

UI hiển thị kênh 'journal' và dịch liên kết thành 'Hoàn tiền', dễ đánh đồng đảo sổ với thực thu tiền. Cần loại liên kết đảo riêng trong phiên bản nguồn tiếp theo và nhãn tiếng Việt.

## Cần chứng từ gì?

- Chứng từ đảo, phê duyệt và lý do điều chỉnh
- Tham chiếu bút toán gốc; chỉ xác nhận thực thu nếu có bằng chứng dòng tiền riêng

## Mức ưu tiên có hợp lý không?

Giữ bằng chứng P2 quá khứ là đúng; ưu tiên xử lý hiện tại cần xem lý do đảo. Chưa đủ căn cứ coi khoản chi đã thực sự được hoàn tiền.

## Câu diễn giải đề xuất

Đã có bút toán đảo sổ, không phải khoản chi mới; cần xác minh điều chỉnh và không tự diễn giải thành tiền đã thu hồi.

Vấn đề liên quan: RR06.

[Gói bằng chứng](../evidence/P2_REVERSAL_JOURNAL.json) · [Bảng tổng hợp](../../representative_review_20261018.md).
