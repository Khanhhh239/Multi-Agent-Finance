# Dấu vết bàn giao kịch bản R3 v5

Ghi theo mục 6 của đăng ký (`08_dang_ky_truoc_v5.md`): nguồn, quyền truy cập, dấu vết bàn giao, những lần làm rõ. Văn xuôi được **chốt** tại commit chứa tệp này, trước mọi bước mã hóa.

## 1. Tệp đã chốt

| Mục | Giá trị |
|---|---|
| Tệp | `scenarios_v5.md` (cùng thư mục) |
| SHA-256 | `3723fb9d4820f1db2411acdd6c1b8bc79d8f4219447e2db7858e2625159a02cc` |
| Ngày nộp | 2026-10-22, 15:00 |
| Số kịch bản | 10 (V5-KB01 đến V5-KB10), mỗi phiếu đủ 11 mục, hai tình huống hợp lệ trông giống, bảng 10 dòng mẫu |
| Kiểm hình thức | Dòng xác nhận độc lập ở đầu tệp; không có ký tự "~" hay "&"; không nhắc mã, kết quả hay số đo mô hình |

## 2. Người viết và mức độc lập

- Người viết là **một phiên agent tách biệt (mô hình ngôn ngữ)**, không phải kiểm toán viên hay kế toán trưởng con người. Đây là độc lập giữa phiên, đúng như mục 6 đã ghi, chưa thay thế tác giả nghiệp vụ độc lập.
- Phiên viết chỉ nhận `brief_v5.md` và `README.md`; không được giao tên điểm yếu của mô hình.
- Người viết đề nghị một kế toán trưởng đọc lại trước khi dùng. Việc này cần chủ dự án quyết định; chưa làm.

## 3. Kiểm tra giới hạn đọc (từ nhật ký công cụ của phiên viết, không dựa vào lời tự khai)

| Loại thao tác | Số lượt | Đích |
|---|---:|---|
| Đọc tệp trên máy | 3 | `brief_v5.md` (2 lượt, một lượt qua `smart_read` vì hook chặn `Read`), `README.md` |
| Ghi tệp trên máy | 2 | `scenarios_v5.md` (lượt `Write` bị hook chặn, ghi lại bằng `smart_write`) |
| Tìm kiếm web | 18 | ACFE 2024, Bộ luật Lao động 2019, Thông tư 48/2019/TT-BTC, các vụ án và bài báo Việt Nam |
| Đọc trang web công khai | 19 | Bản ACFE 2024 và các bản tóm tắt công khai, thuvienphapluat.vn, baophapluat.vn, amis.misa.vn và các bài phân tích ACFE |

Không có lượt liệt kê thư mục, tìm kiếm tệp, đọc `agent2/`, `docs/04_*`, `results/` hay chạy lệnh nào. Công cụ đọc web tự lưu bản sao hai tệp PDF công khai vào thư mục tạm của phiên, ngoài dự án; không có tệp nào được tải vào dự án.

## 4. Dòng thời gian và làm rõ

| Thời điểm | Sự kiện |
|---|---|
| 2026-10-22, khoảng 09:50 | Giao việc theo `brief_v5.md` |
| Trước 10:30 | Phiên viết dừng do giới hạn API, đã đọc xong nguồn, chưa ghi tệp |
| 14:52 | Cho chạy tiếp bằng một tin nhắn chỉ nhắc lại yêu cầu của brief và các ràng buộc (không đọc mã, kết quả, số đo; không trùng danh sách đã dùng; tiếng Việt trang trọng). Không thêm thông tin về mô hình hay điểm yếu |
| 15:00 | Nộp `scenarios_v5.md` |

Chưa có lần làm rõ nội dung nào với người viết. Mục 10 của từng phiếu liệt kê dữ liệu nằm ngoài các bảng của brief (ví dụ sổ tài sản cố định, người phụ trách khách hàng, lượt nhiên liệu theo xe); các câu hỏi đó chỉ được gửi lại người viết nếu R3 được thực hiện.

## 5. Khi nào văn xuôi này được dùng

Chỉ khi chốt chặn trước niêm phong ở R2 đạt. Khi đó mã hóa đúng ý văn xuôi, không chỉnh để dễ hay khó hơn cho bộ phát hiện; tần suất ca hợp lệ đã ghi trước ở mục "Làm rõ thực thi R3" của đăng ký. Nếu R2 không đạt, tệp này được giữ làm tư liệu cho vòng sau, không mã hóa.
