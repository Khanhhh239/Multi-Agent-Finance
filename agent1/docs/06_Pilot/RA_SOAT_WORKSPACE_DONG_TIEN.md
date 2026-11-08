# Rà soát workspace dòng tiền · 07-11-26

Bố cục tham chiếu [Tabler](https://github.com/tabler/tabler). Workspace có hai mục chính là Dự báo và Dữ liệu. Mục Quản lý chứa Tổng quan, phiên bản kiểm định và hướng dẫn. Giải thích dài nằm trong phần mở rộng hoặc nút hỏi cạnh trường nhập.

Người dùng chọn kỳ từ 1 đến 52 tuần, mặc định 13. Phân phối thu và lịch chi được tính theo kỳ đã chọn. Ước lượng bán thu ngay, chi biến đổi và thu hóa đơn mới có phạm vi tối đa 13 tuần đầu, theo cửa sổ kiểm định hiện có. Tuần sau đó gồm công nợ đang mở và lịch chi đã biết. Định dạng ngày hiển thị và định dạng ô Excel là `dd-mm-yy`. API và dữ liệu lưu vẫn dùng ISO để đọc được kế hoạch cũ.

Kịch bản có lựa chọn sẵn và cho đặt riêng số ngày chậm, tỷ lệ thay đổi chi, khách chịu ảnh hưởng và phụ thuộc giữa các hóa đơn cùng khách. So sánh với kế hoạch gốc khi ngày chốt, số tuần, số dư, ngưỡng, dữ liệu, phiên bản và phạm vi tính giống nhau. Excel xuất từ kế hoạch đã lưu, gồm Kết quả dự báo, Kế hoạch từng tuần và Khoản cần chú ý.

| Yêu cầu | Workspace hiện tại | Phần còn thiếu |
|---|---|---|
| FR-01 Nhập liệu | CSV/XLSX, ghép cột, xem lỗi, duyệt trước khi lưu | Nhập XML hóa đơn trực tiếp trong workspace |
| FR-02 Đối soát | Bảng thanh toán liên kết sao kê, phân bổ nhiều dòng, hàng chờ xử lý | Đề xuất khớp tự động có lý do và xác nhận theo lô |
| FR-03 Thời điểm trả | Phiên bản học riêng, dự báo công nợ mở, kịch bản theo khách | Kiểm định thêm theo tuổi nợ và nhiều kỳ trên doanh nghiệp thật |
| FR-04 Rủi ro xóa nợ | Xác suất sự kiện xóa nợ ghi nhận trong 365 ngày khi đủ nhãn | Ước lượng mức tổn thất và luồng duyệt dự phòng |
| FR-05 Tranh chấp, trả một phần | Lịch thu từng phần từ lịch sử và trạng thái tranh chấp | Xác suất phát sinh tranh chấp có kiểm định |
| FR-06 Hoạt động mới | Có nhánh thu/chi hoạt động và hóa đơn bán chịu mới, tùy điều kiện kiểm định | Kiểm định riêng các chân trời dài hơn 13 tuần |
| FR-07 Lịch chi | Nhập lịch chi đã biết và đánh dấu tuần đã rà soát | Sinh lịch chi định kỳ và quy tắc ngày nghỉ trực tiếp trong workspace |
| FR-08 Số dư và cảnh báo | Dải P10/P90 mô phỏng, số dư kỳ vọng, ngưỡng cảnh báo và đối chiếu sao kê | P50 riêng, bằng chứng hiệu chỉnh độ phủ và đo thời gian cảnh báo trên dữ liệu thật |
| FR-09 Thay đổi hành vi | Tín hiệu thay đổi ngày trả trễ | Chế độ ứng phó được kiểm định và lịch sử xử lý cảnh báo |
| FR-10 Lời hứa trả | Nhập sự kiện, tính độ tin cậy và hiển thị trong danh sách | Kiểm định đóng góp vào dự báo và luồng ghi lời hứa nhanh |
| FR-11 Thu hồi và kịch bản | Xếp hạng có metric top 10, mẫu kịch bản và so sánh gốc | Đo kết quả sau liên hệ để đánh giá hiệu quả thu hồi |
| FR-12 Kiểm định | Chọn theo thời gian, audit riêng, báo cáo có mật khẩu | Kiểm định rolling-origin số dư toàn chuỗi trên doanh nghiệp thật |
| FR-13 Demo | Có bộ Đại Phát và kho train riêng | Dùng cho diễn tập luồng |

FR-14/T13 nằm ngoài phạm vi đã thống nhất. NFR-03 cần đo tải nhiều quy mô và kỳ dự báo trên máy mục tiêu. NFR-04 cần số đo khả dụng trong vận hành. Bản lưu có ngày chốt, mã phiên bản, dấu vân tay dữ liệu và giả định để truy vết. Phần ưu tiên còn thiếu theo luồng làm việc là gợi ý đối soát, độ đầy đủ của lịch chi và kiểm định số dư thực tế.

Kiểm tra trên Đại Phát ngày 07-11-26: 43 ca adaptive đạt. Kiểm tra bổ sung chân trời 52 tuần giữ đúng 13 tuần ước lượng hoạt động. Trên web, lập kế hoạch 26 tuần và chạy kịch bản thu chậm 28 ngày, có chênh lệch so với kế hoạch gốc. Excel mở được với 3 sheet, 26 dòng kế hoạch và 30 khoản cần chú ý. Lượt tính kịch bản này mất 8,698 giây trong lõi dự báo. Mục tiêu kịch bản 3 giây cần được đo riêng cho phạm vi chuẩn 13 tuần và máy mục tiêu.
