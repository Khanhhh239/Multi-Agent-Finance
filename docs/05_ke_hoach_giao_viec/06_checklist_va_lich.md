# Danh sách việc, công ước tính, định nghĩa hoàn thành

**Kết quả ngày 2026-10-17:** A1 đến A5 hoàn tất, nhưng G5 không đạt và **M2 kích hoạt điều kiện dừng toàn dự án**: recall S1 trung bình ba thế giới là 41,31%, thấp hơn 50%. A6, pha B và các công việc phát triển, triển khai tiếp không được thực hiện trong vòng này. Các phần C đã viết là hiện vật nghiên cứu, chưa hoàn tất chấp nhận hoặc thí điểm. Xem [báo cáo](../03_danh_gia_va_hieu_qua_kinh_te/07_ket_qua_niem_phong_v4.md) và [trạng thái](../STATUS.md). Bảng dưới giữ nguyên kế hoạch và ngưỡng gốc để truy vết.

Công tính theo ngày công của một kỹ sư (không gồm thời gian máy chạy). Ước tính thô **[G]**.

| Mã | Việc | Công | Phụ thuộc | Đầu ra chính |
|---|---|---:|---|---|
| A1 | Tái lập môi trường, dữ liệu, dấu vân tay | 0,5 | | Nhật ký |
| A2 | Hoàn tất so sánh phương pháp dev, `stats_v4.py` | 1,5 | A1 | `results/v4/method_study/` |
| A3 | Chọn cấu hình, đóng băng, `test_select_v4.py` | 0,5 | A2 | `v4_frozen.json` |
| A4 | Thử khô `sealed_v4.py`, `test_sealed_v4.py` | 0,5 | A3 | Thử khô qua |
| A5 | Chạy niêm phong v4 một lần, báo cáo | 0,5 | A4 | `sealed_v4.json`, báo cáo |
| A6 | Huấn luyện `pretrained_v2` | 1 | A5 | Mô hình, thẻ mô hình |
| B1 đến B12 | Thí nghiệm cải tiến | 17 | A5 | JSON và nhật ký |
| C1 đến C8 | Sản phẩm hóa | 17 | A6 | Đường ống, dịch vụ, UI |
| D1 đến D5 | Dữ liệu mở rộng và độc lập | 18 | A5 | Bộ sinh mở rộng, v5 |
| E1 đến E6 | Thí điểm, pháp lý | 10 công cộng thêm thời gian chờ 3 đến 6 tháng | C, D5 | Số đo thật |

Đường găng: A → C → E. Pha B và D chạy song song với C.

## Định nghĩa hoàn thành chung
1. Mã có kiểm thử tự động; `pytest tests_agent2 tests_sme_fraud -q` qua.
2. Có mục nhật ký (giả thuyết, tiêu chí đặt trước, kết quả, kết luận).
3. Kết quả JSON nằm trong `results/`.
4. Tài liệu liên quan cập nhật; `STATUS.md` cập nhật.
5. Không vi phạm quy tắc R1 đến R10 (tệp 00).

## Mốc

| Mốc | Điều kiện | Quyết định |
|---|---|---|
| M1. Cấu hình đóng băng | A3 | Cấu hình dùng cho niêm phong |
| M2. Niêm phong v4 | A5 | So với cổng G5 (thư mục 03 tệp 03) |
| M3. Mô hình v2 | A6 | Cho phép C1 |
| M4. Chạy được trên tệp thật | C1 đến C4 | Sẵn sàng nhận dữ liệu thí điểm |
| M5. Niêm phong v5 độc lập | D4 | Kết luận cuối về phương pháp |
| M6. Kết quả thí điểm | E5 | Đi hay không |

## Điều kiện dừng toàn dự án
Nếu M2 hoặc M5 cho recall chung dưới 50% hoặc báo nhầm ca khó trên 25%, hoặc M6 cho tỷ lệ cảnh báo "đáng kiểm tra" dưới 10% và không ai sẵn lòng trả: dừng, báo chủ dự án, xem lại bài toán (ví dụ chuyển sang bán như dịch vụ rà soát định kỳ cho đơn vị kế toán).
