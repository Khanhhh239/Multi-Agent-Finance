# Đại Phát · Nạp dữ liệu và diễn tập

Đọc [README khởi động](../../README.md) để tạo môi trường và chạy workspace DEMO_DAIPHAT ở cổng 8012. [Sổ tay PDF có ảnh](pdf/So-tay-Agent1.pdf) hướng dẫn đủ 12 bước. [Thông tin kỹ thuật và cấu hình](../HANDOFF.md) dành cho người nhận mã nguồn.

## Nạp file

Chọn **Dữ liệu** trên web, chọn đúng loại bảng, định dạng ngày trong file `yyyy-mm-dd`, số tiền `plain`. Với mỗi file, bấm **Kiểm tra file** rồi **Xác nhận lưu dữ liệu**.

| File từ pilot/demo_dai_phat | Loại bảng | Số dòng |
|---|---|---:|
| 01_invoices.csv | Hóa đơn bán hàng | 12.780 |
| 02_bank.csv | Dòng sao kê ngân hàng | 17.642 |
| 03_payments.csv | Khoản thanh toán đã nhận | 16.258 |
| 04_statements.csv | Kỳ sao kê và số dư | 142 |
| 05_outflows.csv | Lịch chi đã biết | 27 |
| 06_actions.csv | Nhật ký thu nợ và lời hứa | 5.001 |

Khóa kết nối nằm trong thư mục `.state-business-firm-DEMO_DAIPHAT-data-keys` do máy nhận tạo. Dữ liệu đã có cùng mã sẽ được cập nhật. Sáu khoản thu chưa ghép tổng 42 triệu có thể để chờ xác minh.

## Kiểm định và dự báo

Ngày chốt học và dự báo là **31-10-26**. Số dư đầu kỳ **425000000 VND**, ngưỡng **200000000 VND**. Chọn **Quản lý → Phiên bản & kiểm định**, xác nhận đủ thanh toán và bắt đầu. Sau khi kiểm tra kết quả, chọn **Sử dụng phiên bản này**.

Chạy gốc 13 tuần. Để so kịch bản, chạy gốc 26 tuần rồi chọn thu chậm thêm 28 ngày với cùng thông số. Xuất Excel có ba sheet. Ngày trên giao diện và Excel dùng `dd-mm-yy`.

Dữ liệu synthetic được train trong kho demo riêng. Job lớn cần ≥3 GiB RAM hệ thống trống, worker giữ giới hạn RSS 2 GiB và không giới hạn tổng thời gian. Giữ máy và dịch vụ chạy trong lúc học.

## Báo cáo riêng

Báo cáo HTML mã hóa tự lưu tại `outputs/private-training-reports/`. Mật khẩu nằm trong `report-password.txt` ở thư mục khóa doanh nghiệp. Script tự tạo mật khẩu ngẫu nhiên nếu chưa có. Có thể đặt `AGENT1_REPORT_DIR` để chọn nơi lưu khác. Các file này được tạo trên máy nhận và được loại khỏi Git.

Phiên bản minh họa trước đây dùng neural 25 vòng/batch 512, mất 138,84 giây. Mặc định hiện tại là 100/128. Muốn đo cấu hình hiện hành cần chạy lượt mới. Kết quả synthetic dùng kiểm nghiệm quy trình. Bộ hồ sơ xóa nợ, độ phủ khoảng số dư và hiệu quả thu hồi cần được đánh giá trên dữ liệu doanh nghiệp thật.
