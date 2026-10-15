# Quy mô và kế hoạch sinh dữ liệu

## 1. Quy mô hiện tại (đo thực tế)

| Chỉ tiêu | Giá trị |
|---|---|
| Dòng mỗi thế giới | 200.000; trung vị khoảng 3.630 dòng mỗi công ty trong 30 tháng |
| Thời gian sinh một thế giới | 103 đến 228 giây (một tiến trình Python, kèm kiểm định và kiểm tra lối tắt) |
| Dung lượng mỗi thế giới | khoảng 350 MB CSV (`features.csv` 106 MB, `transactions.csv` 76 MB, `journal_lines.csv` 55 MB, `account_flow_edges.csv` 34 MB, `journal_documents.csv` 34 MB) |
| Bộ nhớ khi nạp để huấn luyện | khoảng 1 đến 3 GB cho một thế giới (200.000 dòng, khoảng 300 cột); nạp đồng thời 3 thế giới từng gây lỗi hết bộ nhớ trên máy 16 GB, đã sửa trong `eval_v4.py` bằng cách ép float32 và nạp từng thế giới |
| Thế giới đã có | v3 phát triển 5 (seed 201 đến 205), v3 niêm phong 3 (901 đến 903), v4 phát triển 3 (411 đến 413), v4 niêm phong 3 (931 đến 933) |
| Seed đã bỏ | v4 401 đến 403 (sinh trước khi hiệu chỉnh cấp người thực hiện); không dùng |

## 2. Lệnh sinh lại (từ thư mục gốc kho)

```powershell
$env:PYTHONPATH = (Get-Location)
python -m agent2.world_v4 --output work/data/w4_s411 --rows 200000 --fraud-rate 0.004 --seed 411 --companies 48
python -m agent2.validate_v4 --data work/data/w4_s411
# niêm phong (dùng hàm, chưa có CLI):
python scripts/gen_s4.py        # sinh s4_s931..933 và kiểm định
```

Cùng seed và cùng mã cho cùng dữ liệu. **Không sinh lại thế giới niêm phong sau khi đã chạy đánh giá niêm phong.**

## 3. Mở rộng rất lớn

Mục tiêu: nhiều thế giới và nhiều dòng để (a) huấn luyện mô hình chuyển giao tốt hơn, (b) đo sai số nhỏ hơn, (c) có bộ thử độc lập.

| Núm điều chỉnh | Ảnh hưởng | Gợi ý |
|---|---|---|
| `--seed` | Thế giới mới độc lập | 20 thế giới phát triển (seed 1001 đến 1020), 5 thế giới niêm phong mới |
| `--rows` | Mật độ giao dịch | 200.000 hiện tại. Thử 1.000.000 cho 48 công ty để mô phỏng công ty có 20.000 dòng mỗi công ty |
| `--companies` | Số công ty | 200 công ty ở 200.000 dòng là công ty rất nhỏ; giữ khoảng 3.000 đến 20.000 dòng mỗi công ty |
| `--fraud-rate` | Mất cân bằng | Lưới 0,05%, 0,1%, 0,4%, 1% |
| `fraud_company_share` | Phần công ty có vụ | 25%, 55%, 85% |
| `difficulty_weights` | L0, L1, L2 | Hai bộ lệch như tệp 07 |

**Điểm nghẽn khi tăng quy mô** (cần coding agent xử lý, xem thư mục 05):
1. Bộ sinh và bộ đặc trưng dùng vòng lặp Python theo dòng: tuyến tính nhưng chậm; phân mảnh theo công ty (các công ty độc lập) để chạy song song.
2. Nạp bộ nhớ: ép float32, loại cột chữ, xử lý theo công ty.
3. `features.csv` có 190 cột; giữ định dạng parquet và nén.

## 4. Kết hợp dữ liệu thật và dữ liệu sinh

| Chế độ | Cách làm | Câu hỏi trả lời được | Điều kiện |
|---|---|---|---|
| **Chẩn đoán khoảng cách** | Huấn luyện bộ phân loại "thật hay sinh" trên trường không nhãn của dữ liệu thật và dữ liệu sinh (adversarial validation); so phân phối số tiền, giờ, thứ, tỷ lệ loại nghiệp vụ | Dữ liệu sinh khác thật ở đâu | Có dữ liệu thật dù không nhãn (BPI, chi trả thành phố, thí điểm) |
| **Khối lượng cảnh báo trên nền thật** | Chạy hệ thống trên nền thật không nhãn; đếm cảnh báo mỗi 1.000 giao dịch theo luật | Có báo nhầm quá nhiều không | Cần bộ chuyển đổi lược đồ |
| **Chèn vào nền thật** | Lấy nền thật làm lớp bình thường, chèn kịch bản v4 vào (cần quy đổi lược đồ) | Tỷ lệ phát hiện theo kịch bản trên nền thật | Có dữ liệu thật có người lập và người duyệt |
| **Huấn luyện sinh, hiệu chỉnh thật** | Huấn luyện trên thế giới sinh; chỉnh ngưỡng và trọng số bằng phản hồi thí điểm | Điều chỉnh hiệu năng thật | Phản hồi người dùng |
| **Đối chiếu ngoài** | Chạy trên ERP Fraud Data, DFKI | Bộ sinh của ta dễ hơn thật bao nhiêu | Đã làm một phần |

Quy tắc: số đo trên dữ liệu thật không nhãn **không được gọi là độ chính xác**.

## 5. Kế hoạch thế giới cho các mục đích (đề xuất)

| Bộ | Số thế giới | Dùng cho | Quy tắc |
|---|---:|---|---|
| Phát triển | 20 | Chọn phương pháp, đặt siêu tham số | Được xem kết quả |
| Hiệu chỉnh thật | 1 đến 5 doanh nghiệp thí điểm | Ngưỡng, trọng số, lý do | Chỉ xem; không nhãn trước |
| Niêm phong v4 | 3 (có) | Kiểm thử cuối | Chạy một lần |
| Niêm phong mới | 5, kịch bản **do người khác viết** | Kiểm thử độc lập | Chưa có; việc của vòng sau |
