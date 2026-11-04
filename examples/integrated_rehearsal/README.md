# Bản chạy tích hợp trên nguồn mô phỏng hiện có

Runner ghép luật mới nhất, graph/A5, hàng đợi, IF shadow có guard, app duyệt hai cấp và thông báo giả lập. Chỉ nhận cache mô phỏng reporting 001/003 có provenance tương thích; không đọc nhãn, split hoặc holdout 005.

Chạy từ `D:\agent22`, dùng Python trong [DEVELOPMENT](../../docs/DEVELOPMENT.md):

```powershell
$env:PYTHONPATH = "$PWD;.runtime/site-packages"
& $projectPython -X utf8 -B -m sme_fraud.integrated_rehearsal run `
  --output reports/integrated_rehearsal_next
```

Phải chọn output chưa tồn tại, tách khỏi nguồn/model. Nếu một lượt thất bại, giữ output để chẩn đoán và chạy lại vào thư mục mới. Không sửa manifest, nới guard hoặc đổi kỳ vọng chỉ để chạy qua.

## Các bước được kiểm tra

1. Sao chép nguyên byte các bảng/cache được manifest v4 chứng thực. Giữ nguyên mốc nguồn, cờ thiếu bằng chứng, feature contract và model đã khóa.
2. Kiểm tra lại các cửa sổ train/calibration/evaluation từ nguồn thực tế của bộ mô phỏng; chấm luật mới, xuất hàng đợi, đối soát kế toán, đồng bộ graph và ngưỡng A5. So sánh kết quả với snapshot ngày 24/10.
3. Chấm IF trên evaluation bằng model/ngưỡng cũ. Nhánh reranking dùng để chẩn đoán; nhánh discovery có guard 0 ngày trễ thêm là chính sách shadow được nghiệm thu. Cùng trần 5/120 hoặc 10/240 cho từng công ty/ngày.
4. Giải thích độ phủ IF, giữ riêng loại trừ lịch sử và lỗi dữ liệu; chạy 20 cấu hình discovery trên hai cohort. Không chấm train/calibration để lấp thiếu điểm.
5. App lấy bản sao **baseline mới**. IF không tự thêm hồ sơ vận hành hoặc kết luận. Kiểm tra HTTP thực tế, quyền công ty, gửi/trả/gửi lại/chốt, phiên bản cũ, duyệt khác người và thông báo giả lập chống trùng.

Các lý do, danh tính và phút trong test được ghi rõ là **mô phỏng**, không phải rà độc lập hoặc số phút kế toán thực tế. `independent_reviews=0`; nghiệm thu nguồn thật và lợi ích ML vẫn mở.

## Mở app của lượt đã chạy đạt

```powershell
& $projectPython -X utf8 -B -m sme_fraud.integrated_rehearsal serve `
  --output reports/integrated_rehearsal_20261028_v2 --base-port 8821
```

| Địa chỉ loopback | Danh tính test cố định tại máy chủ |
| --- | --- |
| `http://127.0.0.1:8821/` | MÔ PHỎNG · Kế toán viên C001 |
| `http://127.0.0.1:8822/` | MÔ PHỎNG · Kế toán trưởng C001 |
| `http://127.0.0.1:8823/` | MÔ PHỎNG · Giám đốc C001 |
| `http://127.0.0.1:8824/` | Chưa đăng nhập, chỉ xem |

Đây là launcher test, không phải luồng đăng nhập hoặc tài khoản thật. Không truyền danh tính từ request. `app/integration_qa.json` ghi clock test; các mốc hiển thị là mô phỏng. C001 chỉ ghi/duyệt hồ sơ C001; các công ty khác giữ phạm vi riêng.

Nếu các cổng này đã có đúng server của lượt chạy, dùng tiến trình đó. Không mở thêm writer vào cùng database. Database, kết quả duyệt và outbox chỉ nằm trong `reports/<lượt>/app/`; không dùng database demo cũ cổng 8774.

Thông báo bắt buộc `dry_run=true`, đích `.invalid`/`SIM_*`, không cấu hình SMTP/Zalo thật. Bằng chứng API và JavaScript được lưu riêng; không coi chúng là nghiệm thu thao tác trên browser khi công cụ browser chưa chạy được.

## Đầu ra

| Thư mục/file | Nội dung |
| --- | --- |
| `evaluation_plan.json` | Nguồn, phiên bản mã, cutoff, phạm vi model và chính sách trước chạy |
| `source/` | Bản sao cache và nguồn được chứng thực |
| `baseline/` | Điểm luật, hàng đợi, bằng chứng, graph và A5 mới; có hash khóa |
| `temporal/`, `comparison/`, `coverage/`, `discovery/` | Kiểm chứng thời gian, IF evaluation và so sánh shadow |
| `app/snapshots/`, `app/review.sqlite3` | Bản sao cho app và trạng thái test có thể tiếp tục thao tác |
| `app/api_checks.json`, `app/workflow_trace.json` | HTTP và lịch sử duyệt mô phỏng |
| `app/notification_verification.json` | Đối soát thông báo giả lập |
| `summary.json` | Trạng thái tổng hợp; không đóng cổng nghiệm thu dữ liệu thật/ML |

[Mã runner](../../sme_fraud/integrated_rehearsal.py) · [Test cách ly/provenance](../../tests/test_integrated_rehearsal.py).
