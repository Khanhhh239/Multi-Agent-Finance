# Dịch vụ local Agent 1

## Chạy Python

Tại thư mục dự án, cài `requirements.txt`, sau đó:

```powershell
$env:PYTHONUTF8='1'
$env:AGENT1_THREADS='4'
$env:OMP_NUM_THREADS='4'
$env:AGENT1_DEMO_DIR='data/synthetic/tgt'
.\.venv\Scripts\python.exe -m agent1_service.seed_demo
.\.venv\Scripts\python.exe -m uvicorn agent1_service.main:app --host 127.0.0.1 --port 8000
```

Mở `http://127.0.0.1:8000`. Khoá truy cập tự tạo ở `.state/api-token.txt`;
nhập khoá vào ô dashboard hoặc gửi header `Authorization: Bearer ...`.
Không đưa khoá vào URL, Git hoặc ảnh chụp màn hình.

Mặc định `/forecast` trả `409 NO_GO`. Dữ liệu, lời hứa, xác thực và giao diện vẫn hoạt động.
Khi kiểm tra nội bộ trên tổng hợp, có thể cấu hình `AGENT1_RESEARCH_MODE=1`
trước khi khởi động. Kết quả vẫn mang nhãn nghiên cứu và chưa đủ điều kiện pilot.

## Docker

Khi Docker engine hoạt động: `docker compose up --build -d`.
Compose nạp công ty F000 từ thế giới `tgt` vào SQLite mã hoá trên volume riêng,
chỉ mở cổng trên loopback. Đọc token bằng lệnh `docker compose exec agent1 cat /state/api-token.txt`.
Lần kiểm hiện tại trên Windows chưa xây/chạy container do Docker daemon không hoạt động;
đã kiểm dịch vụ bằng TestClient và Python local.

## API

`GET /health`, `POST /ingest`, `POST /forecast`, `POST /whatif`, `POST /promises`,
`GET /alerts`, `GET /data`, `DELETE /data`, `GET /models`, `GET /monitoring`. Ngoài health và trang đăng nhập,
các API đều yêu cầu token. Máy chủ gắn một DN; payload mang mã DN khác bị từ chối.

Importer CSV/Excel dùng ánh xạ cấu hình cho năm mẫu ngân hàng; mẫu kiểm thử không
thay cho chứng nhận hỗ trợ mọi phiên bản xuất của ngân hàng. XML hỗ trợ namespace,
kiểm phiên bản và nhận diện tham chiếu thay thế; nghiệp vụ điều chỉnh/huỷ thật cần được nghiệm thu thêm.

## Giới hạn hiện tại

Engine local dùng đối soát quy tắc và mô hình riêng DN hoặc B1d khi thiếu dữ liệu.
Chưa thay thế mô hình tiền huấn luyện/fine-tune của thí nghiệm T6; lịch chi chưa có
`known_at` được dự báo từ lịch sử. E2E thực nghiệm ghi rõ giới hạn này và không mở cổng pilot.
Theo dõi cổng tại `docs/03_Evaluation/GATES_CURRENT.md`.

## Phiên bản mô hình và giám sát local

```powershell
.\.venv\Scripts\python.exe -m agent1.jobs.retrain --firm F000 --reason psi --cutoff 2024-07-01
.\.venv\Scripts\python.exe -m agent1_service.jobs.weekly --firm F000 --cutoff 2024-10-01
```

Retrain tạo ứng viên T1 từ nhãn đối soát quy tắc, giữ nhãn train trước cutoff ít nhất
120 ngày. Chỉ số kiểm tra trên hoá đơn tất toán có thiên lệch sống sót, được ghi rõ;
không dùng làm bằng chứng GO. Thêm `--activate` để chọn ứng viên cho **nghiên cứu local**.
Dịch vụ chỉ dùng phiên bản có cutoff phù hợp và hash mã/mô hình còn khớp.
Mô hình dạng text LightGBM, metadata và mẫu tham chiếu được mã hoá trong SQLite;
API danh sách không trả mô hình hoặc mẫu đặc trưng. Xoá DN xoá cả registry.

Nhập số dư qua `/ingest` với `table="cash_balances"`, mỗi bản ghi có `date`, `balance`.
Tác vụ weekly tính PSI và độ phủ trên số dư thực tế đúng cuối tuần đã tới hạn;
thiếu số dư được báo thiếu bằng chứng. Ngưỡng PSI >0,1 hoặc bốn lượt độ phủ liên tiếp
ngoài [0,7;0,9] yêu cầu xem xét retrain. Tác vụ này chưa tự tạo lịch trên hệ điều hành.
Dashboard hiển thị báo cáo đã lưu, phiên bản và cảnh báo local.
