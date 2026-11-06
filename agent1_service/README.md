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
ngoại tệ được nhập T0 nhưng bị chặn khi dự báo/huấn luyện cho đến khi có
quy đổi tỷ giá có nguồn.

Mỗi hóa đơn và sự kiện hủy có `available_on` là ngày dữ liệu đã sẵn cho hệ
thống (mặc định ngày nhập theo giờ Việt Nam). `ingested_on` ghi ngày API thực
sự nhận bản ghi. Khi nhập lại dữ liệu lịch sử, cần khai báo `available_on`
theo chứng cứ nguồn; API chưa tự xác thực chứng cứ ngày lịch sử. Ngày này
không được trước ngày lập hóa đơn/sự kiện.
`record_version` là số nguyên dương cho phiên bản dữ liệu hóa đơn, mặc định 1;
bản sửa cùng nguồn phải tăng số phiên bản. Lịch sử phiên bản được giữ trong
kho mã hóa và dự báo/huấn luyện tại ngày cắt chỉ thấy phiên bản đã nhận đến
ngày đó. Trường `document_version` của XML là phiên bản định dạng XML, khác
với `record_version`.

Nhập lại cùng nguồn và `record_version` so sánh toàn bộ nội dung nghiệp vụ đã
chuẩn hóa, gồm khách hàng, hạn trả, credit note và tham chiếu chứng từ. Retry
giống nhau không tạo revision; sửa nội dung phải tăng `record_version`, nếu
không API trả 422. Kho giữ `source_payloads` riêng cho XML/ERP để việc gộp nguồn
không làm sai phép so sánh. Tên file, dòng nguồn, hash file và ngày nhập lại
không làm thay đổi nội dung nghiệp vụ hay viết lại availability của bản cũ.
Kho cũ đã gộp nhiều nguồn nhưng thiếu nội dung riêng để đối chiếu phải nhập
phiên bản mới; hệ thống không đoán rằng payload cũ và mới giống nhau.

Các trường ngày nhập qua JSON, XML/ERP và `/promises` được chuẩn hóa về ngày
Việt Nam `YYYY-MM-DD`, kể cả nguồn có timestamp/offset. Ngày bắt buộc thiếu hoặc
không hợp lệ bị từ chối trước khi lưu. Bản đọc lời hứa cũ có timestamp cũng
được chuẩn hóa mà không sửa bản nguồn hoặc lịch sử trong kho mã hóa.

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
kiểm chứng, dự báo và huấn luyện chỉ dùng giao dịch thuộc sao kê đó và chặn
nếu phạm vi đến ngày cắt chưa đủ. `available_on` của file (mặc định ngày
nhập) cũng áp cho kỳ và giao dịch; nhập lịch sử phải khai báo ngày sao kê đã
sẵn có, không trước ngày cuối kỳ. Hash và xác nhận của người kiểm duyệt giúp
đối chiếu với nguồn tách biệt, nhưng phần mềm không tự xác thực ngân hàng phát
hành file hay chứng minh hồ sơ nguồn đã liệt kê đủ tài khoản. Đường nhập giao dịch
JSON cũ vẫn phục vụ nghiên cứu nhưng không xác nhận phạm vi sao kê.

XML `TCHDon=1` được hiểu là thay thế; `TCHDon=2` là khoản điều chỉnh **có dấu**.
Tham chiếu phải xác định duy nhất hóa đơn đã nhập. Dự báo và huấn luyện dùng
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

Engine local dùng lịch sử đối soát đã xác nhận và mô hình riêng DN đã chọn;
chưa chọn model thì dùng B1d. Endpoint dự báo không tự huấn luyện.
Chưa thay thế mô hình tiền huấn luyện/fine-tune của thí nghiệm T6; lịch chi chưa có
`known_at` được dự báo từ lịch sử. E2E thực nghiệm ghi rõ giới hạn này và không mở cổng pilot.
Theo dõi cổng tại `docs/03_Evaluation/GATES_CURRENT.md`.

<a id="luong-t0-t9-thong-nhat"></a>

## Luồng T0–T9 thống nhất, cập nhật 06/11/2026

Luồng runtime duy nhất của API là **T0 Khánh → T9 từ lõi Thắng → snapshot
quan sát → train/dự báo/giám sát → T10 và Agent 4**. T0 vẫn đọc XML/ERP/sao kê,
kiểm chứng từ và giữ nguồn. Package `agent1/reconciliation/_thang/` giữ nguyên
tám module phụ thuộc từ commit `89c144ba3b3d2e7d79d8cb70dc7baf99dc319268`;
`provenance.json` ghi hash từng file. Runtime chỉ gọi `constrained.allocate`
và `ledger.replay`; các matcher cũ còn trong dependency không phải lựa chọn
runtime. Các thí nghiệm T9 cũ giữ làm hồ sơ/đối chứng, không tự chuyển thành
phân bổ đã xác nhận.

`constrained_flow` dùng tiền nguyên VND, phân biệt doanh nghiệp/khách hàng,
không ép FIFO khi nhiều nghiệm. Giới hạn mặc định: tuổi hóa đơn 3.650 ngày,
component mỗi phía tối đa 12, subset amount-only tối đa 3; vượt giới hạn hoặc
thiếu bằng chứng chuyển duyệt. Không suy accuracy từ nghiệm duy nhất. Chưa có
phí/tỷ giá được xác minh thì không tự bù chênh lệch để khớp. Các khả năng FX
của upstream không đồng nghĩa dịch vụ/mô hình hiện hỗ trợ ngoại tệ.

**Các thao tác trên dashboard:** nhập dữ liệu → chọn ngày hiện tại → tìm đề
xuất → đối chiếu chứng từ → xác nhận → xem công nợ/dự báo. Giao dịch mơ hồ
có thể nhập phân bổ thủ công với mã giao dịch, mã hóa đơn, tiền nguyên và
nguồn bằng chứng. Mỗi giao dịch chỉ được phân bổ cho một khách; tiền thừa
giữ chưa phân bổ. Có thể đảo quyết định, hoặc ghi/đảo quyết định write-off
toàn bộ dư nợ còn lại. Chưa hỗ trợ write-off từng phần hoặc thu hồi sau
write-off; cần đảo quyết định trước khi sửa các phân bổ liên quan.

| API có bearer token | Chức năng |
|---|---|
| `POST /reconciliation/run` | `{cutoff}` tạo đề xuất; chưa làm giảm công nợ |
| `POST /reconciliation/accept` | `{idempotency_key, reviewed_by, proposal_id}` xác nhận đề xuất hiện hành; hoặc `allocations=[{txn_id,invoice_id,amount_minor}]` cùng `note` cho phân bổ thủ công |
| `POST /reconciliation/reverse` | `{idempotency_key,decision_id,reviewed_by,note}` đảo phân bổ hoặc write-off |
| `POST /reconciliation/writeoffs` | `{idempotency_key,invoice_id,effective_on,reviewed_by,source_ref}` ghi write-off phần dư |
| `GET /snapshot?cutoff=YYYY-MM-DD` | Công nợ, thu tiền đã xác nhận, trạng thái đóng, `contract_version` và hash snapshot |
| `GET /reconciliation/history?cutoff=YYYY-MM-DD` | Quyết định và write-off; vẫn đọc được để đảo quyết định khi chứng từ T0 đã đổi làm snapshot không hợp lệ |
| `POST /models/deactivate` | Bỏ chọn model cũ, giữ artifact để kiểm toán; cho phép dùng baseline nghiên cứu |

Mỗi yêu cầu ghi có idempotency key: retry nguyên nội dung không ghi lần hai;
đổi nội dung phải dùng key mới. Lệnh và bằng chứng lưu mã hóa cùng Store,
không dùng SQLite plaintext của upstream. Xác nhận chỉ commit **sổ nội bộ**,
không ghi ERP, chuyển tiền hay xác minh hộ tính xác thực của file ngân hàng.
Write-off và credit note không tạo cash. Đảo phân bổ không đảo giao dịch bank.

**Hợp đồng thời gian và nguồn (`agent1-observed-cash-v2`).** Hóa đơn giữ
`available_on` và lịch sử revision của T0. Giao dịch JSON mới có availability,
tiền minor và không được ghi đè cùng `txn_id` với nội dung khác. Nguồn cũ
thiếu availability chỉ có fallback ngày nghiệp vụ cho nghiên cứu; không đủ
để tuyên bố backtest vận hành. Các lệnh duyệt/đảo/write-off luôn nhận ngày
hiện tại theo Việt Nam từ máy chủ; API không cho caller lùi ngày biết quyết
định. Đề xuất cũ hoặc đã thay dữ liệu phải chạy lại. Bank value date và ngày
biết phân bổ được giữ riêng: xác nhận tháng 9 không xuất hiện trong snapshot
tháng 7. Chứng từ chưa nhập đủ không được coi là chưa từng có sự kiện.

Khách hàng, lời hứa và lịch chi giữ cả bản hiện hành lẫn lịch sử mã hóa theo
ID và `available_on`/`known_at`. Snapshot chọn nguyên phiên bản đã biết tại
cutoff. Bản sửa phải có ngày biết mới hơn bản cũ; cùng ngày khác nội dung
bị từ chối vì hợp đồng hiện có độ phân giải theo ngày. Retry nguyên nội dung
không thêm phiên bản. Với kho cũ, bản còn lại được giữ trước lần sửa đầu;
không thể khôi phục các bản đã bị ghi đè trước khi có lịch sử.

Khi nguồn có cả `available_on` và `known_at`, chọn phiên bản hóa đơn, áp dụng
sự kiện hủy, snapshot giao dịch và nhãn giảm trừ đều dùng ngày muộn hơn.
Nhập lại sự kiện hủy giữ nguyên nội dung và ngày biết không thêm sự kiện;
ID nội bộ và ngày nạp lại không làm retry thành xung đột. Thay nội dung hoặc
ngày biết của sự kiện đã lưu vẫn bị từ chối.
Retry giao dịch không được đổi ngày biết,
remittance hoặc tài khoản/kỳ sao kê rồi báo thành công nhưng bỏ qua thay đổi.

Sau revision, phân bổ đã duyệt được đối chiếu lại với khách hàng, ngày lập
hóa đơn, loại khoản thu và số tiền nguồn. Khoản thu trước ngày lập hóa đơn
theo bản sửa hoặc thuộc khách khác làm snapshot/dự báo trả 422. Bản sửa T0
vẫn được giữ làm nguồn; cần kiểm tra nguồn và đảo quyết định xung đột trước
khi tiếp tục. Endpoint lịch sử và đảo quyết định vẫn hoạt động khi snapshot
bị chặn. Đây là kiểm tra sửa dữ liệu; chưa hỗ trợ nghiệp vụ chuyển công nợ.
Sửa tên cùng `customer_id` không tạo chuyển khách.

Write-off lưu `invoice_context` gồm ID hóa đơn/khách, MST người bán/mua, ký
hiệu/số, ngày lập và tiền tệ. Snapshot kiểm lại phạm vi và dư nợ; đổi khách
hoặc chứng từ không tự mang write-off cũ sang bản mới. Quyết định cũ thiếu
phạm vi chỉ được dựng lại từ lịch sử T0 tại ngày duyệt; thiếu lịch sử hoặc
đổi phạm vi cùng ngày không xác định được thứ tự thì báo cần đảo và duyệt
lại, không suy phạm vi từ khách hàng hiện tại. Không sửa
event cũ. Thay hạn trả đơn thuần không làm đổi phạm vi quyết định xóa nợ.

`last_cash_date` giữ ngày thu tiền cuối, `closed_date` giữ ngày hết công nợ.
Credit note đến sau hoặc cùng ngày khoản thu cuối làm hết dư nợ được ghi
`closure_type=credit_note`, không tạo `paid_date_est`. Nếu thu đủ phần còn
lại sau credit note, ngày thu đó có thể là ngày trả đủ phần tiền còn lại.
Một revision giảm giá trị hóa đơn sau khoản thu không được lùi ngày tất toán;
khi thiếu ngày nghiệp vụ riêng của revision, dùng ngày biết bản sửa và ghi
`closure_type=adjustment`. `outcome_known_at` tính cả ngày biết chứng từ giảm trừ.

`ObservedSnapshotBuilder` dựng lại view tại từng cutoff cho T1/T2/T3/T8;
chỉ ghép kết quả tương lai khi tạo **nhãn** tại `label_end`. Khoản tiền đã
về trước origin nhưng được nhận diện muộn không bị biến thành tiền tương
lai; các hàng đó bị loại khỏi risk set huấn luyện, kể cả khoản thu một phần
và cả nhãn đã trả/chưa trả. Nếu phân bổ đã được biết tại cutoff thì dư nợ
vẫn trừ đúng khoản thu đó. Không dùng kết quả duyệt sau cutoff để sửa ngược
feature. Cùng bộ dựng mẫu này phục vụ cả train và validation. Credit note
trong cửa sổ nhãn kết thúc thời gian theo dõi số tiền ban đầu, kể cả thu một
phần rồi giảm trừ phần còn lại. Chứng từ giảm trừ có ngày nghiệp vụ trước
origin nhưng được biết sau origin không trở thành nhãn thu tiền tương lai.
Hóa đơn đổi khách giữa origin và label_end không dùng để học lịch sử khách cũ.
Hóa đơn đổi giá trị gốc giữa hai mốc cũng bị loại khỏi các origin có số tiền
khác kết quả cuối; chưa suy nhãn cho số tiền cũ từ trạng thái số tiền mới.
Hóa đơn hủy/thay thế không còn endpoint
ở label_end bị loại thay vì coi là chưa trả. Chưa có nhãn đủ chín/hợp lệ
thì retrain trả lỗi rõ ràng; dữ liệu vừa tải không tự tạo được một lịch sử
phê duyệt hoặc một backtest độc lập.

Tập hóa đơn mở từ ledger được áp dụng trước khi tính các đặc trưng tổng hợp
khách hàng/công ty. Hóa đơn đóng bằng tiền thu cộng giảm trừ không làm tăng
số hóa đơn mở của hóa đơn khác; dư nợ VND còn đúng 1 đồng vẫn được giữ.

T4 dùng hóa đơn đã quan sát tại cùng cutoff cho doanh thu mới; T5 lọc theo
ngày biết lịch chi; T6 dùng dư nợ đã trừ thanh toán/credit và cùng lịch sử
thu tiền. Tiền đã về trước cutoff không cộng lại vào tiền tương lai; số dư
đầu kỳ vẫn là số dư ngân hàng người dùng cung cấp. Khi không còn hóa đơn
mở, T6 vẫn chạy phần số dư/thu mới/chi. T10 và Agent 4 đọc `/forecast`,
`/snapshot`, `/alerts`; forecast có `data_contract`, `data_snapshot` và
`model_version` để truy vết. Đây là giao diện tích hợp, chưa có thay đổi
mã của Agent 4 trong repo này.

Hai phase tách riêng: job retrain tạo ứng viên, người vận hành chọn phiên bản,
rồi `/forecast` chỉ suy luận từ phiên bản đó hoặc B1d. Đường runtime không
fit T1/T4 hay dựng tập train. Nếu chưa có artifact T4 thì chưa tính thu từ
hóa đơn mới (`new_revenue_included=false`); giao diện hiển thị giới hạn đó.
Registry/API hiện mới có T1, chưa có đường chọn artifact T4 cho dịch vụ;
T4 fit trong các thí nghiệm offline vẫn được giữ.

**Chuyển dữ liệu cũ:** giữ nguyên dữ liệu T0, không tự nhập các liên kết T9
thí nghiệm thành nhãn. Chạy đối soát và duyệt lại từ bằng chứng. Model registry
kiểm thêm hash của pipeline mới: model cũ có chữ ký khác bị từ chối; dùng
nút baseline hoặc `/models/deactivate`, sau đó chỉ retrain/kích hoạt khi đủ
lịch sử hợp lệ. Bộ ứng viên V6 93 feature vẫn là nghiên cứu riêng; thay
nguồn T9 không tự chứng minh nó tương thích hoặc kích hoạt nó.

Kiểm chứng kỹ thuật không thay G15/G13, UAT hoặc pilot thật. Không dùng dữ
liệu synthetic để tự chọn một model thắng rồi bật triển khai; fixture chỉ
kiểm bảo toàn tiền, trạng thái, idempotency và chống rò rỉ thời gian.

Bằng chứng kỹ thuật của đợt tích hợp: [JUnit hồi quy](../outputs/implementation/t9_canonical_runtime_tests.xml)
và [metadata kiểm chứng](../outputs/implementation/t9_canonical_runtime_verification.json).
Kiểm tra cú pháp/định danh DOM đã qua; kiểm tra trực quan trên Chrome chưa
hoàn thành vì computer-use không xác định được URL đủ chắc chắn và đã dừng.

## Phiên bản mô hình và giám sát local

Dựng lại bộ mẫu từ kho đã nạp bằng cùng builder mà job train sử dụng:

```powershell
.\.venv\Scripts\python.exe -m agent1.jobs.retrain --firm F000 --reason manual --cutoff 2026-11-06 --state .state --prepare-only --dataset-output outputs/data/observed_t1_20261106
```

Lệnh này tạo `train.parquet.enc`, `validation.parquet.enc` và `dataset.json`
ghi hash, số hàng, khoảng nhãn, missing windows và chữ ký mã. Parquet được
mã hóa bằng khóa của kho nguồn. Không fit hoặc kích hoạt model, không ghi
ngược dữ liệu T0/T9, không ghi đè thư mục dataset đã tồn tại. Nếu thiếu kho
nguồn thì dừng, không tự tạo dữ liệu hoặc lịch sử duyệt. `trainable=false`
nghĩa bộ mẫu chưa đủ nhãn để train; phải bổ sung dữ liệu có chứng cứ.

```powershell
.\.venv\Scripts\python.exe -m agent1.jobs.retrain --firm F000 --reason psi --cutoff 2024-07-01
.\.venv\Scripts\python.exe -m agent1_service.jobs.weekly --firm F000 --cutoff 2024-10-01
```

Retrain tạo ứng viên T1 từ nhãn ledger đã xác nhận, giữ nhãn train trước cutoff ít nhất
120 ngày. Validation chấm xác suất thu đủ tiền tại 7/28/56/91 ngày, gồm cả hóa
đơn đã trả và chưa trả có đủ thời gian theo dõi từng mốc. Model và B1d được
chấm trên cùng các hàng; báo Brier, Brier có trọng số dư nợ, số hàng trả/chưa
trả và số hàng thiếu theo dõi. Không đủ theo dõi thì điểm là `null`; không
gán nhóm này là chưa trả. Pinball/coverage trên nhóm đã trả chỉ còn là chẩn
đoán phụ. Kết quả có điều kiện trên nhóm đủ theo dõi; giảm trừ có thể gây
kiểm duyệt có thông tin, chưa chứng minh hiệu quả toàn bộ danh mục hay GO.
Thêm `--activate` để chọn ứng viên cho **nghiên cứu local**.
Dịch vụ chỉ dùng phiên bản có cutoff phù hợp và hash mã/mô hình còn khớp.
Mô hình dạng text LightGBM, metadata và mẫu tham chiếu được mã hoá trong SQLite;
API danh sách không trả mô hình hoặc mẫu đặc trưng. Xoá DN xoá cả registry.

Nhập số dư qua `/ingest` với `table="cash_balances"`, mỗi bản ghi có `date`, `balance`.
Tác vụ weekly tính PSI và độ phủ trên số dư thực tế đúng cuối tuần đã tới hạn;
thiếu số dư được báo thiếu bằng chứng. Ngưỡng PSI >0,1 hoặc bốn lượt độ phủ liên tiếp
ngoài [0,7;0,9] yêu cầu xem xét retrain. Tác vụ này chưa tự tạo lịch trên hệ điều hành.
Dashboard hiển thị báo cáo đã lưu, phiên bản và cảnh báo local.
