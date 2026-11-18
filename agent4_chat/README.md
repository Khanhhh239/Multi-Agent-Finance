# Giao diện Hỏi đáp CFO Hai Sổ — Agent 4 (`agent4_chat/`)

Khung giao diện hội thoại tiếng Việt dành cho **CFO & Kế toán trưởng** bên trong **Sổ Son — Phòng Kế Toán Số** (`http://127.0.0.1:8800/#agent4`).

## Tính năng chính
- **Bảo mật khóa máy chủ & CSP nghiêm ngặt**: Chỉ giao tiếp qua `/api/agent4/query` và `/api/agent4/metrics` của Portal; không lưu khóa nội bộ trên trình duyệt và không dùng bất kỳ thuộc tính `style="..."` hay `on*="..."` nội tuyến nào.
- **Số học VND chính xác (BigInt/Decimal) & Bảo toàn dấu âm**: Định dạng chuẩn tiếng Việt và tóm tắt đọc nhanh (`approxVnd`) giữ nguyên dấu âm rõ ràng (ví dụ `-666.387.909 đồng (khoảng âm 666,4 triệu đồng)`), kèm thẻ KPI và huy hiệu cảnh báo lỗ / dòng tiền âm / chênh lệch hai sổ riêng biệt.
- **Hội thoại đa lượt (`session_id`) & Chip làm rõ 1 chạm**: Duy trì `session_id` xuyên suốt phiên để hỏi nối tiếp (*“Còn theo sổ thuế thì sao?”*, *“Chi tiết theo từng chi nhánh?”*), có nút **Làm mới hội thoại** và hiển thị nút chọn nhanh khi câu hỏi cần làm rõ (`needs_clarification` / `clarification_needed`).
- **Minh bạch quản trị AI**: Hiển thị rõ huy hiệu khung sổ trả lời (**Sổ quản trị `v_mgmt`**, **Sổ thuế `v_tax`**, hoặc **So sánh hai sổ**) cùng cơ chế thực thi (**SQL tất định đóng dấu** so với **Chế độ từ vựng dự phòng Lexical**).
