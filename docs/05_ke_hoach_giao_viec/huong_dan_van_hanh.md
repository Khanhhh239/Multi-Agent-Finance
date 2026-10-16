# Vận hành cục bộ Agent 2 v4

Tài liệu cho hiện vật nghiên cứu trên dữ liệu tổng hợp. Chỉ chuyển sang thí điểm khi các cổng đánh giá và hồ sơ pháp lý đã được đáp ứng. Chưa có tệp xuất thực tế để xác nhận tương thích phần mềm kế toán.

## Môi trường

Tại thư mục gốc dự án, dùng Python 3.12.14 và các phiên bản trong `requirements.txt`:

```powershell
$env:PYTHONPATH = (Get-Location).Path
.venv/Scripts/python.exe -m pytest tests_agent2 tests_sme_fraud -q
```

Các thư mục `work/`, `.venv/` và khóa truy cập không được đưa lên Git. Không đưa dữ liệu doanh nghiệp thật lên Git hoặc dịch vụ ngoài.

## Chuẩn bị đầu vào

CSV chung được ánh xạ theo [hướng dẫn adapter](adapters.md) và [hợp đồng dữ liệu](data_contract.md). Khóa phải giữ dạng chuỗi, tiền VND là số nguyên, ngày có múi giờ hoặc khai báo múi giờ trong YAML. Dữ liệu có nhãn gian lận trong bảng giao dịch bị từ chối.

```powershell
.venv/Scripts/python.exe -m agent2.adapters.csv_generic --input work/customer_source --mapping work/customer_mapping.yaml --out work/customer_normalized
```

Kiểm `input_report.json` trước khi chấm. XML hiện chỉ trích hóa đơn và dòng hàng; chưa đủ thay thế sổ kế toán.

## Chấm một công ty trong một tuần

Sau khi A6 tạo được mô hình v2 và cấu hình chính thức:

```powershell
.venv/Scripts/python.exe -m agent2.pipeline --data work/data/w4_s413 --out work/runs/413_C001_2025W40 --company C001 --week 2025-W40 --config configs/agent2_default.json
```

Chỉ chấm các dòng trong tuần ISO được yêu cầu, theo giờ Việt Nam. Lịch sử trước tuần được chia thành giai đoạn tham chiếu và 90 ngày hiệu chỉnh. Chế độ hiện tại cần cả hai giai đoạn có dữ liệu; khởi đầu lạnh không có nghĩa là không cần lịch sử. Bộ nạp vận hành chỉ mở danh sách bảng thô được cho phép, không mở nhãn, phân chia huấn luyện hoặc đặc trưng lưu sẵn.

Đầu ra: `alerts.csv`, `cases.csv`, `case_queue.csv`, `explanations.jsonl`, `report.json`, `run_manifest.json` và ảnh chụp bảng đầu vào. Thư mục ra đã có dữ liệu bị từ chối ghi đè. Báo cáo ghi số cảnh báo, phiên bản, thời gian từng giai đoạn và PSI; điểm ưu tiên không phải xác suất gian lận. Thời hạn là tham chiếu theo mức ưu tiên, cần thống nhất lại khi thí điểm.

## Dịch vụ và giao diện rà soát

Tạo `work/service/tenants.json` bằng mã truy cập ngẫu nhiên riêng cho từng công ty, ví dụ cấu trúc `{"C001": "MA_NGAU_NHIEN_RIENG"}`. Không sử dụng chuỗi minh họa này làm khóa thật. Người có khóa truy cập được dữ liệu của công ty tương ứng.

```powershell
.venv/Scripts/python.exe -m agent2.service --db work/service/review.sqlite --storage work/service/data --tenants work/service/tenants.json --config configs/agent2_default.json --port 8766
```

Mở `http://127.0.0.1:8766`, nhập mã truy cập và người rà soát. Nhập CSV hoặc ZIP bảng CSV kèm YAML ánh xạ, chọn tuần, chấm rồi mở hồ sơ để đối chiếu. Từng quyết định phải có người, kết luận, lý do và thời gian; đánh giá đáng kiểm tra là một trường riêng. Quyết định được ghi thêm, không sửa hoặc xóa bản ghi cũ. Chuyển mã công ty xóa dữ liệu đang hiển thị trước khi nạp hàng đợi mới.

Các điểm vào yêu cầu `Authorization: Bearer ...`: `POST /ingest`, `POST /score?week=2025-W40`, `GET /cases?status=new`, `POST /cases/{id}/decision`, `GET /report`, `GET /decisions`. Yêu cầu chấm trùng cùng lần nhập, tuần và phiên bản cấu hình trả lại kết quả cũ. Dịch vụ mặc định chỉ nghe `127.0.0.1`; đây là máy chủ phục vụ phát triển của Flask, chưa phải thiết kế triển khai qua Internet.

## Giới hạn và khôi phục

Phản hồi được thu thập nhưng không tự đổi cấu hình đã niêm phong. Khi đã có ít nhất 20 hồ sơ với cả kết luận xác nhận dấu hiệu sai phạm và hợp lệ, có thể tạo hiện vật học riêng:

```powershell
.venv/Scripts/python.exe -m agent2.feedback_v4 --db work/service/review.sqlite --company C001 --cutoff 2026-10-18T23:59:59+07:00 --out work/feedback/C001_20261018.json
```

Hồ sơ chưa xem, nghi vấn và đánh giá đáng kiểm tra không được chuyển thành nhãn gian lận. Hiện vật không đủ nhãn báo `insufficient_labels` và không được bật. Muốn thử trên tuần sau, tạo bản cấu hình riêng có `feedback_path` và `feedback_sha256`; không sửa tệp khóa gốc. Biến thể được ghi `unvalidated_feedback`, cách ly công ty, kiểm ngày học trước tuần chấm và giữ tầng ưu tiên cao nhất cho hard trigger. Kết quả G5 của cấu hình gốc không xác nhận hiệu năng của biến thể học phản hồi. Chưa có phản hồi thật hoặc thực nghiệm đủ để khuyến nghị bật.

- Không tự đổi mô hình, ngưỡng hoặc sáu tệp đóng băng khi băm không khớp. Dùng đúng phiên bản mã gắn với mô hình.
- Khi thiếu dữ liệu cho mô hình đầy đủ, báo cáo phải chỉ rõ năng lực bị tắt; không coi kết quả của chế độ giảm là độ chính xác đã đo của L4-FB.
- Sao lưu SQLite và thư mục dữ liệu khi dịch vụ đã dừng, giữ cùng cấu hình và mô hình có băm tương ứng. Không chỉnh trực tiếp bảng `decisions`.
- Nhãn người dùng phục vụ kiểm tra nghiệp vụ; một lần xác nhận trong giao diện không phải kết luận pháp lý. Chưa có bằng chứng thí điểm hoặc hiệu quả kinh tế thực tế.
