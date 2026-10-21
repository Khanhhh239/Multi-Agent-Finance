# Cấu hình phân loại bằng chứng P2

[config.json](config.json) là mẫu tổng hợp để truyền vào `score_rules(tables, config=...)`. Các tên nguồn và người xác minh đều là giả lập. Thay bằng hồ sơ của đúng công ty trước khi sử dụng nguồn thực tế.

| Nhóm | Điểm P2 | Cách tiếp nhận |
| --- | ---: | --- |
| Thiếu/không hợp lệ dữ kiện hóa đơn, số tiền VND hoặc xác minh hạn mức | 0 | Giữ hit; hồ sơ `information_request`, ưu tiên thấp, trạng thái chờ bổ sung |
| Có thông tin hóa đơn đủ để đối chiếu điều kiện thanh toán/VAT | 8 | Rà soát nghiệp vụ, ưu tiên trung bình nếu đứng riêng |
| Chi vượt hạn mức nội bộ có xác minh được khai báo và còn hiệu lực tại lúc chi | 14 | Rà soát nghiệp vụ, ưu tiên cao nếu đứng riêng; không hard trigger |

Nhóm có bằng chứng về hạn mức nội bộ được ưu tiên phân loại khi cùng lúc thiếu hóa đơn. Việc thiếu hóa đơn vẫn được ghi trong `missing_fields`; không làm mất bằng chứng độc lập về hạn mức.

`limit_vnd` phải khớp chính xác giá trị trong `cash_limit_vnd_by_company`. `source_ref` và `verified_by` bắt buộc. Các mốc là ISO 8601 có múi giờ; `verified_at` không được sau lúc chi; kỳ hiệu lực là `[effective_from, effective_to)`. Để trống `effective_to` nếu chưa có mốc kết thúc. Cấu hình chỉ có số tiền hạn mức sẽ được coi là **chưa xác minh** trong chính sách mới.

Đây là xác nhận nguồn do người cấu hình khai báo; module không đọc tài liệu gốc, kiểm chữ ký hay tự xác nhận người phê duyệt. Mẫu hiện biểu diễn một chính sách hạn mức/công ty trong một snapshot. Khi chính sách thay đổi theo kỳ, cần cung cấp cấu hình đúng kỳ và lưu snapshot riêng.

P2 giữ chính sách ngưỡng đối chiếu `vn_vat_v1` hiện có. Các trạng thái trên phục vụ tiếp nhận và ưu tiên rà soát; không phải kết luận gian lận hoặc quyết định về khấu trừ thuế.

Các yêu cầu bổ sung được gộp theo công ty–thực thể trong cửa sổ 30 ngày. Giao dịch đã nằm trong hồ sơ nghiệp vụ giữ hit P2 trong bằng chứng của hồ sơ đó, không mở thêm yêu cầu trùng. Hồ sơ bổ sung vẫn tính ngân sách xử lý khi được mở; có thể xuất hiện trong tóm tắt tuần, không tự tạo thông báo ưu tiên cao. Chọn **Yêu cầu bổ sung P2** trên web để xem nhóm này; bộ lọc tự bỏ chọn **Ưu tiên hôm nay** để hiển thị cả tồn đọng.

Để tái lập hành vi P2 cũ, ghim `cash_review_policy="legacy_v1"`; không ghi đè báo cáo hoặc phản hồi đã lưu. Chính sách mặc định mới là `evidence_v2`.

[Bộ đối chứng bổ sung](../p2_controls/README.md) đã phát hiện và sửa việc dòng thu/hoàn tiền còn mang loại chi bị P2 tiếp nhận sai phạm vi. Điều kiện loại dòng thu theo chiều Nợ/Có áp dụng cho cả hai chính sách; `legacy_v1` ghim phân loại/điểm cũ cho khoản chi, không tái tạo lỗi chiều dòng tiền đã sửa.
