# Nghiên cứu và kiểm định Agent 1

- [T1 compact](t1_compact/README.md) chứa mã chuẩn bị dữ liệu, huấn luyện ensemble, so sánh mô hình và kiểm tra artifact.
- `t6_backtest/` chứa mã dựng dữ liệu tại ngày chốt, tính sai số, tạo kịch bản căng thẳng và kiểm định T6 trên doanh nghiệp mới.

Dịch vụ dự báo chạy bằng `agent1/adaptive/` và catalog T1 đã đóng gói. Các script backtest trong `scripts/business/` và kiểm thử trong `tests/adaptive/` vẫn dùng hai thư mục nghiên cứu trên.

Để đọc lại các nhánh đã ngừng dùng gồm competing risks v5/v6, credit context, practical v6 và Unified Collection v2, xem `agent1/experiments/` tại commit `ced02a3a`. Việc chạy lại từng nghiên cứu cần artifact và dữ liệu đúng phiên bản.

Các bài kiểm thử cho công cụ `agent1/analysis/` cũ đi cùng mã phân tích trong lịch sử Git. Có thể tìm phiên bản cuối còn chứa các công cụ đó bằng `git log -- agent1/analysis`.
