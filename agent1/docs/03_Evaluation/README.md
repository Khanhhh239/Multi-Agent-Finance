# 03 · Đánh giá và nghiệm thu Agent 1

Đối chiếu luồng phục vụ ngày **14/11/2026**. Thư mục này giữ định nghĩa chỉ số, quy trình chấm và giới hạn nghiệm thu; bỏ log, bảng kết quả theo lần chạy và protocol đã bị pipeline hiện tại thay thế.

| Tài liệu | Đọc khi cần |
|---|---|
| [Metric kỹ thuật](01_metric_ky_thuat.md) | T1/cash13/IBS, partial, số dư, cảnh báo, đối soát và giải thích |
| [Giá trị, chi phí và ROI](02_metric_kinh_te.md) | Định nghĩa tác động sử dụng và công thức kinh tế; không coi giả định là kết quả |
| [Nghiệm thu và kiểm thử](03_cong_nghiem_thu.md) | Trạng thái bằng chứng, test/UAT, lock → predict → score và điều kiện đi tiếp |

Pipeline và hợp đồng từng khối ở [AI Methods](../04_AI_Methods/README.md). Kết quả validation/audit của tenant được lưu trong kho mã hóa/registry của đúng doanh nghiệp; báo cáo/CSV/source snapshot nghiên cứu còn nằm trong `outputs/` theo phiên bản. Không dùng điểm của model hoặc catalog cũ để chứng nhận T1 + partial/T6 đang phục vụ.

Các bảng G1–G18 và `GATES_CURRENT.md` trước đây thuộc pipeline nghiên cứu tháng 10, đã bỏ khỏi bộ tài liệu hiện tại. Chưa có bộ nghiệm thu độc lập đủ để tuyên bố runtime mới sẵn sàng cho pilot thật; việc dọn tài liệu không mở gate hoặc tạo số đo mới. Công cụ sinh báo cáo lịch sử vẫn là công cụ nghiên cứu, không là quy trình cập nhật trạng thái ở thư mục này.

Nguồn đầu vào nghiên cứu hiện thiếu raw/Parquet; kiểm [tồn kho dữ liệu](../02_Data/README.md) trước khi tái lập. Không sửa artifact hoặc hash frozen để làm mới kết luận.
