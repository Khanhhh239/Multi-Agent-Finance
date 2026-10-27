# Bảo mật và quyền riêng tư của bản local

API yêu cầu bearer token, khóa theo một mã DN cấu hình tại máy chủ. Nội dung SQLite
được mã hoá Fernet; file DB mặc định ở `.state/`, còn khóa Fernet, HMAC và token
ở `AGENT1_KEY_DIR` (mặc định `.state-keys/`, thư mục anh em của `.state/`),
đều bị loại khỏi Git. File mô phỏng cảnh báo chứa bản mã. Nhật ký chỉ ghi mã DN,
loại thao tác và số lượng; không gửi email/Zalo hay gọi LLM bên ngoài.

HMAC tên/MST dùng khoá riêng ít nhất 32 byte; không dùng băm không khoá để ẩn danh.
`DELETE /data` xoá dữ liệu của DN và VACUUM SQLite; bản sao lưu cũng phải được xoá
theo chính sách lưu giữ. Mã nguồn không được tự chuyển dữ liệu thật vào môi trường phát triển.

Rủi ro còn lại: ai đọc được cả DB và file khoá có thể giải mã; quyền file trên Windows
phụ thuộc ACL của máy, chưa tích hợp kho bí mật/KMS. Chưa có quản lý người dùng,
phân quyền theo vai trò, TLS, giới hạn tốc độ ở reverse proxy hoặc kiểm toán độc lập.
Compose chỉ mở cổng trên 127.0.0.1; không dùng cấu hình này để công khai Internet.
**Chưa xác nhận Docker/weekly CLI với cách tách khóa mới:** `compose.yaml` chưa
gắn volume cho `/state-keys`, còn `agent1_service/jobs/weekly.py` vẫn tìm
`encryption.key` trong thư mục dữ liệu. Không xem hai đường chạy đó là đã đạt
cam kết bảo mật hoặc sẵn sàng vận hành trước khi sửa và kiểm thử lại.

Khi có sự cố: dừng API, cô lập máy, thu hồi token/khoá, bảo toàn nhật ký,
xác định phạm vi dữ liệu và làm việc với người phụ trách pháp lý/nghiệp vụ.
Tài liệu này không thay thế đánh giá tuân thủ pháp luật về dữ liệu cá nhân tại thời điểm pilot.
