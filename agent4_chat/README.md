# Giao diện Hỏi đáp Agent 4 (`agent4_chat/`)

Khung giao diện trò chuyện tiếng Việt cho **Agent 4** bên trong Portal (`http://127.0.0.1:8800/#agent4`).

- Giao diện chỉ gọi qua `/api/agent4/query` và `/api/agent4/metrics` của Portal; khóa xác thực nội bộ của Agent 4 được giữ ở tầng máy chủ, không lộ ra trình duyệt.
- Tự động định dạng số tiền VND dễ đọc (kèm quy đổi triệu / tỷ / nghìn tỷ đồng), hiển thị bảng kết quả và hộp kiểm tra nguồn (chỉ tiêu, kỳ dữ liệu, khung sổ quản trị/thuế, mã băm danh mục).
