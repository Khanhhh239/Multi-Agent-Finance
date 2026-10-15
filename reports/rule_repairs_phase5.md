# Đợt 5 — ràng buộc nghĩa vụ chi A1/A2/A4

Đã triển khai nguồn yêu cầu chi, liên kết PO, hóa đơn typed, hợp đồng trả nhiều đợt và lịch chi định kỳ có trần. Thiếu nguồn giữ cảnh báo hiện tại; bằng chứng chỉ loại đúng giao dịch/nghĩa vụ được duyệt và tổng đã trả chưa vượt trần.

Xem [chính sách, schema, kiểm chứng và giới hạn](rule_payment_evidence.md). Snapshot validation cũ không có nguồn mới nên hàng đợi không đổi; đây là kiểm tra chống hồi quy, không phải kết luận đã giảm FP trên dữ liệu thật.
