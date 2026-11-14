# Chuẩn bị bảo vệ dữ liệu trước pilot

Đây là danh sách kiểm tra nội bộ cho triển khai Agent 1, thay bản cam kết mẫu cũ. Văn bản thỏa thuận với doanh nghiệp phải được người có thẩm quyền hoàn thiện theo phạm vi triển khai thực tế; trang này không là hợp đồng để ký.

## Chốt trách nhiệm và phạm vi

Ghi chủ dữ liệu, đơn vị xử lý, người có quyền truy cập, mục đích, dữ liệu cần nhận, nơi xử lý, hạn lưu và cách rút quyền/xóa. Chốt đầu mối sự cố và việc xử lý bản sao lưu. Không tự xem kết quả tổng hợp là đã ẩn danh hoàn toàn hoặc mặc nhiên được tái sử dụng.

## Đối chiếu với triển khai thực tế

| Kiểm tra | Bằng chứng cần có trước khi nhận dữ liệu |
|---|---|
| Tách doanh nghiệp | Kho dữ liệu, khóa, tiến trình và cấu hình đúng DN; không dùng kho demo cho dữ liệu thật |
| Quyền truy cập | Token/quyền đọc Agent4 và quyền ghi đúng vai trò; thử thu hồi/kết thúc phiên; không đưa khóa vào Git/URL/ảnh |
| Lưu trữ | Xác nhận bản ghi Workspace được mã hóa; khóa tách khỏi dữ liệu; kiểm thêm tệp gốc nhập, export, HTML báo cáo, backup và log ngoài DB |
| Dữ liệu nhận | Chỉ nhận phần được phép, giữ mã nhất quán, dùng kênh đã thống nhất; không yêu cầu mật khẩu/OTP ngân hàng |
| Phục hồi | Thử backup/restore trên kho riêng; khớp snapshot, model, forecast và quyền; giữ khóa cần thiết theo chính sách đã thống nhất |
| Hủy và kết thúc | Liệt kê DB, bản sao, tệp gốc, export, forecast/replay, báo cáo và khóa; xác nhận cách xử lý từng loại và người chịu trách nhiệm |
| Sự cố | Có người nhận thông báo, cách cô lập quyền truy cập và lưu bằng chứng; thử quy trình trước khi vận hành |

Không suy việc mã hóa DB thành mã hóa toàn bộ tệp trên máy. Không suy pipeline ẩn danh của ingest nghiên cứu thành mọi cột nhập trực tiếp qua Workspace đã được ẩn danh. Không hứa đã xóa sạch dữ liệu chỉ vì xóa một bản ghi: phiên bản, forecast và bản sao phục vụ truy vết có thể vẫn còn.

## Vận hành

Chạy local theo [README](../../README.md) và [hợp đồng dịch vụ](../../agent1_service/README.md). Nếu có Portal hoặc thành phần khác, kiểm quyền/lưu trữ của từng thành phần và đường truyền liên quan; một token Agent 1 không bao phủ toàn bộ hệ thống.

Ghi phạm vi và người xác nhận vào [biên bản pilot](../../pilot/quyet_dinh.md). Trạng thái kỹ thuật và chất lượng dự báo xem tại [nghiệm thu](../03_Evaluation/03_cong_nghiem_thu.md).
