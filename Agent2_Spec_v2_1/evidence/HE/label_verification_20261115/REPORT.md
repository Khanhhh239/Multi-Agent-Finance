# CR-056 — danh sách xác minh nhãn tại doanh nghiệp

READY_FOR_REVIEW kỹ thuật; xem [báo cáo đầy đủ](../../../../reports/label_verification_20261115.md)
và [hướng dẫn sử dụng](../../../../agent2/docs/LABEL_VERIFICATION.md).

`checks.json`: kết quả và giới hạn. `tests.json`: hợp nhất test IDs, không cộng
lặp các lần chạy. `source_hashes.json`: checksum tệp nguồn tại thời điểm nghiệm thu.

Nghiệm thu dùng nguồn/khai báo mô phỏng và dịch vụ riêng. Không có nhãn gian lận
thực tế, không train mới hoặc deploy live, không có khóa/credential/bản mã trong
gói evidence này. Không tự phê duyệt gate R0–R6 hoặc model.
