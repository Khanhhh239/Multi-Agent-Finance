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

### Nhập hóa đơn T0

Mọi hóa đơn qua JSON, XML và Excel ERP đều cần đủ trường chuẩn để kiểm MST,
tiền trước thuế, VAT, tổng tiền, ký hiệu, số, ngày và tiền tệ. File ERP thiếu
các trường này bị từ chối; hệ thống không tự đoán VAT hoặc MST. Cùng một hóa
đơn từ XML và ERP được đối chiếu bằng `(seller_mst, symbol, invoice_no)` và
ngày/số tiền trước khi gộp thành một bản ghi. Khác biệt hoặc tham chiếu không
rõ được trả lỗi 422 và không ghi lô nhập.

Tiền nguồn nhận chuỗi thập phân hoặc số nguyên JSON; JSON float bị từ chối.
T0 lưu `amount_net_minor`, `vat_minor`, `amount_gross_minor` là số nguyên theo
VND/JPY (0 chữ số thập phân) hoặc USD/EUR/CNY (2 chữ số); các trường tiền gốc
được chuẩn hóa thành chuỗi. Sai độ chính xác tiền tệ, NaN/Infinity và lệch
giữa hai nguồn bị chặn bằng phép so số nguyên. Chỉ góc nhìn đưa vào mô hình
mới chuyển thành số thực. Mô hình hiện tính bằng VND; hóa đơn hoặc sao kê
ngoại tệ được nhập T0 nhưng bị chặn khi dự báo cho đến khi có
quy đổi tỷ giá có nguồn.

Mỗi hóa đơn và sự kiện hủy có `available_on` là ngày dữ liệu đã sẵn cho hệ
thống (mặc định ngày nhập theo giờ Việt Nam). `ingested_on` ghi ngày API thực
sự nhận bản ghi. Khi nhập lại dữ liệu lịch sử, cần khai báo `available_on`
theo chứng cứ nguồn; API chưa tự xác thực chứng cứ ngày lịch sử. Ngày này
không được trước ngày lập hóa đơn/sự kiện.
`record_version` là số nguyên dương cho phiên bản dữ liệu hóa đơn, mặc định 1;
bản sửa cùng nguồn phải tăng số phiên bản. Lịch sử phiên bản được giữ trong
kho mã hóa và dự báo tại ngày cắt chỉ thấy phiên bản đã nhận đến
ngày đó. Trường `document_version` của XML là phiên bản định dạng XML, khác
với `record_version`.

`/ingest/file` nhận `available_on` và `record_version` trong form. CSV và
Excel bị từ chối nếu header trống/trùng hoặc dòng CSV sai số cột; JSON API
chặn khóa trùng và số NaN/Infinity. Lỗi file 422 chứa tên file, số dòng
(nếu xác định được), SHA-256 và lý do. File lỗi không ghi vào bảng nghiệp vụ;
thông tin lỗi và dòng nguồn (khi đọc được) được giữ mã hóa trong
`ingest_quarantine` để kiểm tra lại. Mỗi bản ghi nhập thành công có
`source_file`, `source_row`, `source_sha256`.

### Sao kê ngân hàng

File CSV/Excel ngân hàng phải có cả cột ghi có và ghi nợ, cùng form field
`statement` dạng JSON. Ví dụ:

```json
{"account_id":"001","currency":"VND","period_start":"2024-03-01","period_end":"2024-03-31","opening_balance":"1000","closing_balance":"1080","total_credits":"100","total_debits":"20"}
```

Trước khi nhập sao kê, người vận hành tạo danh mục tài khoản **từ xác nhận hoặc
bản xuất cổng ngân hàng**, kiểm duyệt và lưu riêng tại
`<AGENT1_STATE_DIR>-keys/bank-accounts.json` (hoặc đường dẫn
`AGENT1_BANK_ACCOUNTS_FILE`). File bằng chứng gốc đặt cạnh danh mục. Ví dụ:

```json
{"firm_id":"F000","source_type":"bank_confirmation","evidence_file":"confirmation.pdf","evidence_sha256":"<SHA-256 của confirmation.pdf>","reviewed_by":"Người kiểm duyệt","reviewed_on":"2026-10-27","accounts":[{"bank":"vcb","account_id":"001","currency":"VND"},{"bank":"bidv","account_id":"002","currency":"VND"}]}
```

Phải thay chuỗi SHA-256 minh họa bằng hash thật của file bằng chứng. Danh mục
phải liệt kê toàn bộ tài khoản liên quan trong kỳ; mã tài khoản phải duy nhất
trong một DN. API nạp sao kê không có quyền tạo hoặc sửa danh mục này. Khi
thiếu danh mục/bằng chứng hoặc hash không khớp, file sao kê bị từ chối. Trường
`expected_accounts` trong metadata file là tùy chọn; nếu có thì phải khớp
**toàn bộ** danh mục đã duyệt, không thể dùng nó để rút bớt tài khoản.

T0 kiểm từng giao dịch nằm trong kỳ, tổng hai chiều khớp metadata, phương
trình số dư và sự nối tiếp ngày/số dư giữa các kỳ của cùng tài khoản. Mỗi
giao dịch (kể cả ghi nợ) được giữ trong `bank_entries`; chỉ giao dịch ghi có
được đưa vào `bank_txns` cho mô hình. `GET /bank/coverage` báo tài khoản hoặc
đoạn kỳ còn thiếu so với danh mục đã duyệt; các sao kê cũ chưa gắn bằng chứng
duyệt được báo là chưa tin cậy và cần nhập lại. Khi đã có sao kê
kiểm chứng, dự báo chỉ dùng giao dịch thuộc sao kê đó và chặn
nếu phạm vi đến ngày cắt chưa đủ. `available_on` của file (mặc định ngày
nhập) cũng áp cho kỳ và giao dịch; nhập lịch sử phải khai báo ngày sao kê đã
sẵn có, không trước ngày cuối kỳ. Hash và xác nhận của người kiểm duyệt giúp
đối chiếu với nguồn tách biệt, nhưng phần mềm không tự xác thực ngân hàng phát
hành file hay chứng minh hồ sơ nguồn đã liệt kê đủ tài khoản. Đường nhập giao dịch
JSON cũ vẫn phục vụ nghiên cứu nhưng không xác nhận phạm vi sao kê.

XML `TCHDon=1` được hiểu là thay thế; `TCHDon=2` là khoản điều chỉnh **có dấu**.
Tham chiếu phải xác định duy nhất hóa đơn đã nhập. Dự báo dùng
giá trị công nợ có hiệu lực tại ngày cắt, không cộng riêng hóa đơn bị thay thế
hoặc bản điều chỉnh. Sự kiện hủy đã xác nhận được nhập qua `/ingest` với
`table="invoice_events"` và bản ghi gồm `event_id`, `invoice_id`,
`event_type="cancel"`, `event_date`. Ví dụ:

```json
{"table":"invoice_events","records":[{"event_id":"cancel-001","invoice_id":"INV-001","event_type":"cancel","event_date":"2024-02-01"}]}
```

Các loại XML nhiều hóa đơn liên quan hoặc chiết khấu thương mại chưa được ánh
xạ an toàn sẽ bị từ chối. Thông báo hủy XML riêng của cơ quan thuế cần mẫu
thực tế để bổ sung parser; hiện cần nhập sự kiện hủy đã xác nhận như trên.

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
