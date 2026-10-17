# Hợp đồng đầu vào cho Agent 2

Mã kiểm tra: `agent2/schema.py::validate_input(tables)`. Đầu vào là ánh xạ tên bảng sang DataFrame hoặc danh sách bản ghi. Hàm không sửa đầu vào và không chấm điểm.

## Trường bắt buộc

`transactions`: `company_id`, `transaction_id`, `posted_at`, `created_at`, `approved_at`, `txn_type`, `amount_vnd`.

- Mã công ty và mã giao dịch không rỗng; cặp mã công ty và giao dịch duy nhất.
- Thời gian có thể phân tích được, tạo không sau duyệt và duyệt không sau đăng sổ. Khi chuyển đổi dữ liệu nguồn, phải chỉ rõ múi giờ; định dạng chuẩn dùng ISO 8601 với `+07:00`.
- Tiền là số nguyên đồng hữu hạn. Giá trị âm được giữ để có thể biểu diễn điều chỉnh kế toán.
- Bảng giao dịch không chứa nhãn đánh giá như `is_fraud`, `fraud_type`, `case_id`, `hard_negative_type` hoặc `loss_vnd`.

## Danh mục và khóa ngoại

Các danh mục `employees`, `vendors`, `customers` có `company_id` cùng khóa riêng tương ứng. Khóa duy nhất trong phạm vi công ty. Các trường `employee_id`, `creator_id`, `approver_id`, `collector_id`, `vendor_id`, `customer_id` của giao dịch nếu được điền phải trỏ tới danh mục trong cùng công ty. Không chấp nhận việc dùng thực thể của công ty khác dù mã thực thể trùng nhau.

Thiếu toàn bộ danh mục được báo là cảnh báo giảm chế độ. Danh mục có mặt nhưng khóa ngoại không hợp lệ là lỗi phải dừng.

## Bằng chứng tùy chọn và chế độ giảm

`CAPABILITIES` trong mã liệt kê các cột cần cho kiểm tra nghỉ việc, tài khoản người nhận, người trả tiền, lịch lương, hóa đơn, phê duyệt và chứng từ. Thiếu bằng chứng được ghi theo từng năng lực vào `disabled_capabilities`; không được thay dữ liệu thiếu bằng số không rồi coi đó là bằng chứng an toàn.

Trạng thái trả về:

| Trạng thái | Ý nghĩa |
|---|---|
| `error` | Có lỗi, dừng nhập và chấm điểm |
| `reduced` | Đầu vào cơ bản hợp lệ nhưng cần tắt các năng lực được liệt kê |
| `passed` | Qua các kiểm tra đã cài, đủ các cột bằng chứng được khai báo |

Pipeline v4 tiêu thụ báo cáo này. Để dùng mô hình đầy đủ, đầu vào phải có các bảng và cột trong `configs/v4_input_columns.json`, ngoài những năng lực kể trên. Đây là hợp đồng thận trọng theo lược đồ tổng hợp đã kiểm chứng; thiếu một cột không được tự điền thành bằng chứng âm tính.

Khi thiếu bằng chứng tùy chọn, pipeline tự chuyển sang `reduced`: chỉ chạy lại điều kiện C3 có sẵn về thời gian duyệt và mức tiền; C2 chỉ được bật khi có phiên bản danh mục nhân viên đã quan sát và hạn mức tự duyệt rõ ràng. Tắt các luật còn lại, đồ thị, tín hiệu thực thể và mọi mô hình học. Báo cáo liệt kê luật bật, luật tắt, mô hình tắt và cột thiếu. Không chọn cảnh báo chỉ để lấp ngân sách khi điểm bằng không. Đây là tập con luật vận hành, **không phải cấu hình L4-FB đã đánh giá niêm phong**, chưa có số đo trên doanh nghiệp thật.

Không đưa dữ liệu thiếu trường vào pipeline v3 cũ. Kiểm tra này không thay thế kiểm định kế toán hoặc đánh giá tính phù hợp của dữ liệu.

## Kiểm chứng

Trước phép so thời gian, các cột có hậu tố `_at` được chuẩn hóa về giờ Việt Nam. CSV adapter dùng múi giờ nguồn khai báo trong YAML cho giá trị chưa có múi giờ; đường vào chuẩn trực tiếp mặc định giờ Việt Nam. Giá trị đã có độ lệch múi giờ được chuyển đúng thời điểm. Khi đọc CSV chuẩn, biểu diễn số nguyên như `1000.0` được đổi thành token `1000`, không làm tròn giá trị có phần lẻ hoặc số tiền lớn. Cách xử lý này tránh đảo thứ tự thời gian khi đầu vào trộn UTC và giờ địa phương, đồng thời giữ giao diện số nguyên của bộ máy luật.

- Chín kiểm thử cho dữ liệu thiếu, tiền sai kiểu, thời gian sai, nhãn lẫn vào đầu vào, khóa trùng và khóa ngoại khác công ty.
- Thế giới tổng hợp `w4_s411` tái sinh ngày 2026-10-16: 200.000 giao dịch, `passed`, không có lỗi, cảnh báo hoặc năng lực thiếu cột. Kết quả tại `results/v4/schema_w4_s411.json`.
