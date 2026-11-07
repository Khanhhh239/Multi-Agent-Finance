# Đại Phát · Bộ đầu vào thực hành

Dữ liệu 100% synthetic cho workspace DEMO_DAIPHAT. Nạp sáu CSV theo số 01–06 và chọn đúng loại bảng cùng tên trong hướng dẫn. Ngày trong CSV là `yyyy-mm-dd`, số tiền `plain`.

Đọc [hướng dẫn khởi động](../../README.md) và [PDF có ảnh](../../docs/06_Pilot/pdf/So-tay-Agent1.pdf). Workspace demo cho phép train và validation. Dữ liệu thật dùng kho SME riêng.

Ngày chốt thực hành **31-10-26**, số dư đầu kỳ **425000000 VND**, ngưỡng cảnh báo **200000000 VND**. Bộ dữ liệu có 6 khoản thu chưa ghép tổng 42 triệu để tập hàng chờ. Từng file trong `invalid_cases/` dùng thử thông báo lỗi, không nạp vào bộ sạch.

`manifest.json` ghi quy mô và giới hạn của bộ này. Báo cáo huấn luyện và trọng số được tạo trên máy nhận. Có thể tái tạo dữ liệu bằng `python scripts/business/make_large_demo.py` từ thư mục repo.
