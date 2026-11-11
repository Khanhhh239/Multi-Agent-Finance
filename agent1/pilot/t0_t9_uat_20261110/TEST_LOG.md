# Nhật ký test UI

Ngày: ______  Người test: ______  Commit: ______  Bộ / RunId / doanh nghiệp: ______

Trạng thái để trống nghĩa là **chưa chạy**. Ghi P (đạt), F (lỗi), B (không chạy được), kèm số dư và ảnh/lỗi. Các ca có lỗi đã biết vẫn ghi F nếu tái hiện; không chuyển thành P chỉ vì báo cáo đã nêu lỗi.

| Ca | Kiểm tra | P/F/B | Số dư, ảnh hoặc lỗi thực tế |
|---|---|---|---|
| S01 | Kho UAT riêng, ISO/plain, kết nối đúng doanh nghiệp | | |
| S02 | 4 file core; 13/14/1/1 bản ghi; dư cuối 195.990.000 | | |
| S03 | Nạp lại nguyên tệp không nhân đôi hóa đơn | | |
| S04 | Bản xem trước cũ sau thay đổi dữ liệu bị chặn | | |
| N01 | Trùng mã | | |
| N02 | Thiếu khách | | |
| N03 | Ngày sai | | |
| N04 | VND lẻ | | |
| N05 | USD | | |
| N06 | Tham chiếu không tồn tại | | |
| N07 | Chéo khách | | |
| N08 | Vượt phân bổ | | |
| N09 | Chiều sai | | |
| N10 | Lệch sao kê 1 VND | | |
| N11 | Thiếu tài khoản | | |
| N12 | Gán bán thu ngay vào AR | | |
| N13 | MST sai | | |
| N14 | Net + VAT khác tổng | | |
| T00 | Đề xuất đủ theo bảng đáp án; chưa giảm công nợ | | |
| T01 | Thiếu reviewer bị chặn | | |
| T02 | Duyệt exact, tải lại không trùng | | |
| T03 | Hai tab, đề xuất cũ bị chặn | | |
| T04 | Từ chối có lý do, không trừ nợ | | |
| T05 | Mơ hồ, manual chọn đúng hóa đơn và bằng chứng | | |
| T06 | Manual chéo khách/vượt tiền bị chặn | | |
| T07 | Đảo, nợ mở lại, bank và lịch sử giữ nguyên | | |
| T08 | Sửa bank + kỳ, đảo phân bổ, không đếm hai phiên bản | | |
| T09 | Bản sửa lệch kỳ hoặc preview cũ bị chặn | | |
| T10 | Thiếu lý do/bằng chứng bị chặn | | |
| L01 | Tiền lớn: còn đúng 1 VND | | |
| L02 | Thay thế, điều chỉnh, hủy; nợ và thời điểm đúng | | |
| L03 | XML, mapping khóa, không tạo nợ trùng với CSV | | |
| P01 | Sao kê chung Portal giữ memo/đối tác và tạo ba đề xuất đúng | | |
| P02 | PAGE_B105 chọn/duyệt được ngoài 100 dòng đầu | | |
| U01 | Khoản vay không gợi ý trừ nợ, không có trong hàng chờ AR; tổng tiền bank vẫn đủ | | |

Mô tả lỗi: thao tác → mong đợi → thực tế → mã chứng từ → ảnh/log. Nếu số tiền sai, ghi cả giá trị đầy đủ; không chỉ ghi “không đúng”.
