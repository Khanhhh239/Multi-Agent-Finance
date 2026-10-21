# P2_LIMIT_FOREIGN — Ngoại tệ chưa xác minh số tiền VND

Người rà: `ASSISTANT_SYNTHETIC_REVIEW`. Đánh giá định tính trên dữ liệu mô phỏng; không phải kết luận kế toán độc lập hoặc kết luận gian lận.

**Kết quả nghiệm thu:** Cần sửa/cải thiện. **Giải thích:** Cần rõ hơn. **Ưu tiên:** Hợp lý có điều kiện.

## Dữ kiện đã đọc

Giao dịch ghi currency=USD, amount_vnd=5.000.000; P2 yêu cầu verified_vnd_amount và giữ 0 điểm. Tuy nhiên dòng sổ debit_vnd/credit_vnd cũng bằng 5.000.000 và tab sổ gắn nhãn VND.

## Giải thích có dễ hiểu không?

Phần giao dịch cảnh báo chưa xác minh VND là đúng, nhưng tab sổ trình bày cùng số như VND, tạo mâu thuẫn về đơn vị. Cần gắn trạng thái chưa xác minh cho sổ này và tách số nguyên tệ/giá trị quy đổi ở phiên bản nguồn sau.

## Cần chứng từ gì?

- Số nguyên tệ, đồng tiền, tỷ giá và thời điểm quy đổi từ nguồn xác minh
- Giá trị VND đã đối chiếu cùng chứng từ gốc

## Mức ưu tiên có hợp lý không?

0 điểm và tuyến bổ sung hợp lý vì chưa thể so với hạn mức VND. Cần ưu tiên sửa cách thể hiện đơn vị dữ liệu, không tự suy rằng 5.000.000 USD bằng 5.000.000 VND.

## Câu diễn giải đề xuất

Chưa xác minh giá trị VND của khoản ngoại tệ; chưa so hạn mức, các giá trị sổ trong mẫu này cũng chưa phải số quy đổi đã xác nhận.

Vấn đề liên quan: RR03.

[Gói bằng chứng](../evidence/P2_LIMIT_FOREIGN.json) · [Bảng tổng hợp](../../representative_review_20261018.md).
