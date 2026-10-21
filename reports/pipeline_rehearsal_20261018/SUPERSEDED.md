# Lượt kiểm tra đầu — giữ lại để truy vết

Lượt này dừng tại phép xác minh JSON đồ thị sau khi chấm xong 001. Runner đã giả định sai rằng từng nút có `company_id` và components là object; hợp đồng thật đặt công ty ở graph/scope và namespace ID, components là danh sách ID.

Phép kiểm đã được sửa, có đối chứng trên JSON NetworkX thật và được kiểm tra lại cùng ngưỡng động của 001. Lượt chạy đầy đủ dùng thư mục mới `reports/pipeline_rehearsal_20261018_v2`.

`failure.json` giữ nguyên để kiểm tra nguyên nhân. Nguồn và bộ holdout không thay đổi trong lượt này; chưa có kết quả nghiệm thu đầy đủ từ thư mục này.
