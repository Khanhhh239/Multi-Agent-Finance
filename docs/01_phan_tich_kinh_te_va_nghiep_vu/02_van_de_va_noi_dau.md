# Phát biểu vấn đề và nỗi đau

## 1. Phát biểu vấn đề

> Chủ doanh nghiệp nhỏ và vừa ở Việt Nam không có cách rẻ, đều đặn và có giải thích để biết người trong công ty có đang lấy tiền của công ty qua sổ sách hay không. Họ chỉ biết khi tiền đã mất nhiều tháng, thường qua tin báo hoặc tình cờ, và khi biết thì khó chứng minh vì không có dấu vết được giữ lại có hệ thống.

Phạm vi: **gian lận nội bộ trong sổ giao dịch** (nhà cung cấp ma, chỉnh người nhận tiền, lương khống, chi phí khống, tiền thu không ghi sổ, hủy hàng để che trộm, hoa hồng nhà cung cấp, bút toán cuối kỳ). Không thuộc phạm vi: gian lận của khách hàng bên ngoài (thẻ, mở tài khoản), rửa tiền, tuân thủ thuế (thuộc agent khác của hệ thống).

## 2. Nguyên nhân gốc

| # | Nguyên nhân | Biểu hiện | Bằng chứng |
|---|---|---|---|
| 1 | Một người làm nhiều việc, thiếu phân tách nhiệm vụ | Cùng người lập lệnh chi, duyệt và ghi sổ; thủ quỹ kiêm kế toán | ACFE: luân chuyển công việc chỉ 10% ở nhóm dưới 100 nhân sự [Đ] |
| 2 | Không có kiểm toán nội bộ, không có đường dây tố giác | Gian lận không có kênh lộ ra | 40% và 27% so với 90% và 82% [Đ] |
| 3 | Chủ tin kế toán trưởng vì không tự đọc được sổ | Người giữ sổ cũng là người có cơ hội | Vụ kế toán trưởng chuyển 51 lệnh sang công ty khác (xem tệp 03) [T] |
| 4 | Kiểm soát bằng ngưỡng tĩnh | Chia nhỏ khoản chi sát ngưỡng tự duyệt | Hành vi "structuring"; xem DATA_V4.md |
| 5 | Thông đồng không vi phạm quy trình | Nhân viên mua hàng và nhà cung cấp là người quen | ACFE: 54% vụ có từ hai người trở lên [Đ] |
| 6 | Quản lý rà soát bằng mắt trên khối lượng lớn | Bỏ sót khoản nhỏ lặp lại | Giám sát chủ động chỉ 19% [Đ] |

## 3. Nỗi đau theo từng vai trò

| Vai trò | Nỗi đau | Hệ quả kinh tế |
|---|---|---|
| Chủ doanh nghiệp | Không đọc được sổ; không biết hỏi ai; sợ nghi oan người có công | Mất tiền âm thầm; quyết định kinh doanh sai vì số liệu sai |
| Kế toán trưởng trung thực | Bị nghi ngờ mỗi khi có chênh lệch; không có công cụ chứng minh sạch | Mất thời gian giải trình; rủi ro uy tín |
| Kế toán viên, thủ quỹ | Bị dùng tên để làm khống (người lập chứng từ chịu trách nhiệm) | Rủi ro hình sự cá nhân |
| Ngân hàng, đối tác | Nghi ngờ sổ sách DNNVV | Vay khó, lãi cao |

## 4. Vì sao hôm nay mới giải được
- Hóa đơn điện tử và thanh toán không tiền mặt tạo dấu vết số hóa cho các giao dịch.
- Phần mềm kế toán đám mây cho phép đọc sổ định kỳ, không cần cài đặt riêng.
- Kỹ thuật phát hiện bất thường và mô hình cây tổng hợp chạy rẻ trên dữ liệu vài chục nghìn dòng.

## 5. Bốn ràng buộc quyết định thiết kế

1. **Không quá tải cảnh báo.** SME không có người rà soát hàng chục cảnh báo; ngân sách mặc định 3 cảnh báo mỗi tuần mỗi công ty.
2. **Phải giải thích được bằng tiếng Việt**, nêu bằng chứng cụ thể, không chỉ điểm số.
3. **Không có nhãn ngày đầu.** Phải chạy được ở chế độ không nhãn và học dần từ phản hồi.
4. **Gian lận mới sẽ xuất hiện.** Phải giữ phần cảnh báo không phụ thuộc vào mẫu đã biết.
