# Thử ML cùng snapshot 35 luật

**C001 dùng Isolation Forest, C002 dùng ECOD.** Model đúng contract bridge
đã được fit riêng và ghim trên cấu hình phân tích local. Mỗi DN có RobustZ
cho phần thống kê. Đây là demo hồi cứu bằng dữ liệu mô phỏng.

1. Mở [Nhập dữ liệu trên Portal](http://127.0.0.1:8800/agent2/data-import).
2. Chọn đúng doanh nghiệp và tệp:
   - C001: [C001_5_giao_dich.json](C001_5_giao_dich.json).
   - C002: [C002_5_giao_dich.json](C002_5_giao_dich.json).
3. Kiểm tra → xác nhận lưu → **Xem 35 luật tại node doanh nghiệp**.
4. Mở **Phân tích bất thường** dưới từng giao dịch để xem vị trí so với tập
   đối chiếu. **Đã chạy** nghĩa là model tính được điểm, không xác nhận sai phạm.

Mỗi tệp có 45 giao dịch nguồn: 32 dòng lịch sử train, 8 dòng reference và
**5 ứng viên cần xem kết quả** ngày 01–05/08/2025. Mốc nguồn khóa là 06/08/2025
00:00 UTC+07. Lịch sử giúp tạo feature, không trở thành 40 hồ sơ mới phải rà.
Tập dùng để fit được lưu riêng, không chứa 5 ứng viên đánh giá.

Input contract có 33 cột; 8 cột chưa có cấu trúc nguồn phù hợp vẫn null.
Preprocess median_flags học từ train, loại cố định các cột all-null trong train;
không tự học lại hoặc điền 0 khi chấm. Mẫu chỉ minh họa các khoản chi NCC,
chưa chứng minh chất lượng với dữ liệu doanh nghiệp thật hay toàn bộ nghiệp vụ.

Đây là đường phân tích **tại node DN**. Các model/bindings HE cũ được giữ riêng;
chưa có HE cho Isolation Forest/ECOD hoặc cả 33 feature. Điểm /100 trên giao
diện là vị trí tương đối, không phải phần trăm gian lận.

[Báo cáo chuẩn bị, ghim model và kiểm chứng](../../../reports/rule_bridge_models_20261114.md).
