# Nguồn đối chiếu A1/A2/A4

Sao chép các CSV cần dùng vào thư mục dataset và cập nhật SHA-256 tương ứng trong `manifest.json`. Mốc thời gian dùng ISO 8601 có múi giờ `+07:00`.

`payment_requests` là quyền chi đã duyệt. `procurement_links` gắn đúng giao dịch với yêu cầu chi và đơn mua. `transaction_documents` cung cấp hóa đơn đã xác minh; để bật chính sách ràng buộc mới cần cả `invoice_number` và `invoice_gross_vnd`. `supplier_payment_agreements` cấp trần cho hợp đồng. `recurring_payments` cấp trần theo tuần/tháng/quý/năm. `vendor_payment_schedules` mô tả khoản chi theo năm hoặc mùa cho B6, với cửa sổ `MM-DD` và tổng tiền tối đa cho từng lần xuất hiện.

Mỗi revision giữ nguyên ID và các trường liên kết nghiệp vụ. Thu hồi bằng `status=revoked` với `observed_at` mới; không xóa vật lý lịch sử. Thiếu nguồn không tự cấp ngoại lệ. Xem [schema](../../sme_fraud/payment_evidence.schema.json) và [chính sách](../../reports/rule_payment_evidence.md).
