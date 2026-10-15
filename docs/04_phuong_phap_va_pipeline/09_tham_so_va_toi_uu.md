# Tham số và tối ưu

## 1. Bảng siêu tham số hiện tại

| Thành phần | Tham số | Giá trị | Ghi chú tối ưu |
|---|---|---|---|
| Ngân sách | B (cảnh báo mỗi công ty mỗi tuần) | 3 (thử 1) | H7: thích ứng |
| Khe | exploit : explore | `ceil(2B/3) : B − exploit` = 2 : 1 | Thử 1:2; đã thử ở v3 (`mixed_slots.csv`) |
| EntityDeviation | số điểm tham chiếu tối thiểu | 20 | Nên thử 30 và 50 |
| | ngưỡng đuôi cho lý do | 4,0 (xác suất 1,8%) | |
| | cắt điểm đuôi trong CES | [0, 12] | |
| Novelty | trọng số phá hòa | 0,001 × trung bình hạng | |
| ECOD, HBOS | số ô HBOS | 20 | |
| Isolation Forest | cây, mẫu | 300, `min(2048, n)` | |
| Autoencoder | kiến trúc, vòng, lô, tốc độ | (48, 12, 48), 60, 256, 1e-3 | Có thể thử (96, 24, 96), tách theo nhóm đặc trưng |
| LightGBM | cây, lá, tốc độ, dừng sớm | 600, {7, 15}, 0,05, 60 | Chưa lưới đầy đủ; thử `min_child_samples` 5, 10, 20 |
| | `colsample_bytree`, `subsample`, `reg_lambda` | 0,6; 0,8; 2,0 | |
| | `scale_pos_weight` | `sqrt(âm/dương)` | Thử 1, sqrt, tuyến tính |
| Cân bằng họ | trọng số | mỗi họ chia đều khối lượng dương | H2: thử `1/sqrt(n_f)` và trần |
| Hai tầng | số khối chéo gập, cửa sổ | 4 khối thời gian, 90 ngày | H3 |
| | ngưỡng hạng cao | 0,99 và 0,95 | |
| CES | `λ`, tiên nghiệm luật, tiên nghiệm thực thể | 0,02; 1,0; 0,25 | Chọn bằng bỏ-một-thế-giới |
| RuleLogit | `C` | 0,3 | |
| Conformal | mức FDR `q` | không đặt mặc định | Đặt 0,2 trong thí điểm |
| Ưu tiên | ngưỡng hạng vụ | 10%, 50% | |
| Thời hạn | giờ | 24, 48, 168 | Mô phỏng |
| Phản hồi | nhiễu thử | 0%, 15%, 30% | |

## 2. Đòn bẩy cải thiện theo thứ tự ưu tiên

1. **Nhiều thế giới huấn luyện hơn và đa dạng hơn** (H10): từ 3 lên 20 thế giới, kịch bản đa dạng, tham số công ty đa dạng. Thường là đòn lớn nhất cho chuyển giao.
2. **Đặc trưng bất biến quy mô** (H9): tỷ lệ, log-z, hạng trong thực thể thay cho số tiền thô.
3. **Cân bằng họ và ràng buộc đơn điệu** (H2, H8): giảm quá khớp họ phổ biến.
4. **Bộ phát hiện chuyên biệt cho kịch bản mà L3 yếu** (H5, H6, H12): `payroll_padding`, `vendor_burst`, `price_creep`, `ghost_employee`.
5. **Gộp mức vụ** (H13): chuyển 90% vụ tìm thấy thành giảm số mục cần xem.
6. **Hiệu chỉnh xác suất:** isotonic hoặc Platt trên kiểm định để điểm có nghĩa là xác suất; cần cho ngưỡng và cho giao diện.
7. **Tập hợp nhiều seed LightGBM** (5 seed trung bình): giảm phương sai; rẻ.
8. **Tối ưu theo mục tiêu thật:** nếu tối ưu trực tiếp "recall@B3" (ví dụ tinh chỉnh bằng lambdarank với nhóm = công ty-tuần), có thể hơn logloss. Thử `objective="lambdarank"` với `group` là công ty-tuần.

## 3. Kỹ thuật hiệu năng

| Vấn đề | Hiện tại | Đề xuất |
|---|---|---|
| Đặc trưng theo vòng lặp Python | `feats.py`, `feats_v4.py`: một lượt tuyến tính, khoảng vài chục giây cho 200.000 dòng | Chạy theo công ty, song song; hoặc DuckDB/Polars với hàm cửa sổ |
| Bộ nhớ | float64, khoảng 300 cột | float32, parquet, đọc cột cần dùng |
| Autoencoder sklearn | 34 đến 50 giây mỗi thế giới | PyTorch trên GPU nếu cần; hoặc bỏ nếu H1 không hỗ trợ |
| Luật + đồ thị của bạn bạn | khoảng vài chục giây | Giữ; lưu bộ nhớ đệm `_cache/rules2.pkl` |
| `groupby().rolling()` | Dùng trong bộ nhớ thực thể | Với 1 triệu dòng dùng bản dựa trên sắp xếp và `searchsorted` |
| Tiến trình dài bị ngắt | Phiên làm việc dừng giữa chừng làm mất tiến trình | Chạy bằng tiến trình tách rời, lưu JSON sau mỗi giao thức (đã làm) |

## 4. Quy tắc thí nghiệm
1. Đặt tiêu chí thành công **trước** khi chạy; ghi vào nhật ký.
2. Chọn tham số bằng kiểm định; **kiểm thử chỉ để báo cáo**.
3. Mọi kết quả kèm số dòng dương, số vụ, khoảng bootstrap.
4. Không dùng kết quả niêm phong để chỉnh.
5. Mỗi thay đổi mã đã chạm kết quả cũ phải chạy hồi quy E1.

