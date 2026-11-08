# Đầu vào theo thời điểm biết cho feature M01

Cutoff là `posted_at` của giao dịch, so sánh có bao gồm đúng thời điểm đó. Timestamp dùng dạng `YYYY-MM-DDTHH:MM:SS+07:00`.

Ưu tiên phiên bản `transaction_documents` đã biết, đúng `company_id + vendor_id + transaction_id`. Khóa phiên bản là `company_id + record_id`; các revision giữ binding giao dịch/NCC/loại chứng từ/định danh hóa đơn, chỉ thay nội dung hoặc trạng thái tại `observed_at` mới. Giữ nguyên các revision cũ. Nếu không có phiên bản phù hợp đã biết, có thể dùng snapshot scalar có ngày biết trên dòng giao dịch.

| Nhóm dữ kiện | Scalar trên giao dịch | Phiên bản `transaction_documents` |
|---|---|---|
| Số lượng chứng từ | `support_doc_count`, `support_docs_observed_at` | Đếm các bản ghi hiện hành đã biết, có `evidence_id`, không bị `revoked`/`rejected` |
| Giao nhận xác minh | `goods_receipt_verified` trong snapshot chứng từ; nếu có `goods_receipt_verified_at` thì thời điểm này cũng không được sau cutoff | `goods_receipt` hoặc `service_acceptance`, `status=verified`, `verified_at <= observed_at <= cutoff`, người xác minh thuộc công ty tại ngày xác minh và khác người lập |
| Tổng hóa đơn | `invoice_gross_vnd`, `invoice_issued_at`, `invoice_observed_at`, định danh hóa đơn | Loại `invoice`, định danh khớp giao dịch, `invoice_gross_vnd`, `invoice_issued_at`, `observed_at` |
| Thành phần hóa đơn | `invoice_net_vnd`, `invoice_vat_vnd` trong cùng snapshot có `invoice_observed_at` | Các trường cùng tên trong cùng revision hóa đơn |
| VAT liên kết | `linked_input_vat_vnd` trong cùng snapshot có `invoice_observed_at` | Trường cùng tên trong cùng revision hóa đơn |

Số lượng chứng từ đã quan sát không xác nhận bộ hồ sơ đầy đủ. Chứng từ pending/unverified có thể được đếm là đã có, nhưng không làm cờ giao nhận đã xác minh bằng 1. `support_docs_known=1` là khả dụng của quan sát, không phải kết luận đủ chứng từ hoặc không có gian lận.

`invoice_number` được chuẩn hóa khi đối chiếu; `invoice_id` phải khớp chính xác. Số tiền cũng có thể được cấp bởi revision chỉ có `invoice_id` khớp, nhưng chưa có số hóa đơn thì không tự tạo khóa lịch sử thanh toán theo số hóa đơn. Hai snapshot hóa đơn khả dụng đồng thời nhưng mâu thuẫn số tiền/thành phần bị từ chối thay vì tùy ý chọn một bản.

Không có `support_docs_observed_at` nghĩa là scalar chứng từ không có bằng chứng về thời điểm biết. Nếu đã có cột này nhưng giá trị rỗng/sai định dạng, quy tắc kiểm tra đầu vào hiện hành vẫn từ chối. `invoice_observed_at` và `goods_receipt_verified_at` mới cho phép rỗng để biểu diễn chưa biết; không dùng giá trị rỗng để miễn kiểm tra thời gian hoặc cấp xác nhận giao nhận.

Timestamp scalar phải mô tả đúng phiên bản các cờ/số tiền tương ứng mà hệ thống thực sự đã biết. Nếu bộ dữ liệu chỉ giữ giá trị cuối kỳ, cần xuất lại lịch sử từ nguồn; không gắn lùi `observed_at` để lấy lại điểm/độ phủ. Không dùng ngày phát hành hóa đơn thay cho ngày hệ thống nhận dữ kiện.

`invoice_versions.csv` dùng cho phần rà hồ sơ theo hợp đồng hiện có không tự trở thành nguồn detector. Bản sửa này đọc các revision `transaction_documents` nêu trên; không suy diễn nội dung các bảng rà hồ sơ chưa được đưa vào hợp đồng detector.
