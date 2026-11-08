# PLAN_06 — chạy MVP review chứng từ

Ngày: 13/10/2026. Phạm vi: capture có người kiểm tra, không có tax verdict. UI `/review` hoạt động cùng API; OCR mặc định tiếp tục **PP-OCRv6 + VietOCR** qua adapter registry. Không cài dependency mới hoặc train model ở PLAN_06.

## Khởi động local

Cwd `D:\financial\agent3_tax_compliance`. Tạo credential/grants như [runbook PLAN_02](../plan02/runbook.md), nhưng chọn database demo riêng **trước khi provision master**:

```powershell
$env:CAPTURE_DATABASE_PATH = 'D:\financial\data invoice\plan06_local\demo.sqlite3'
$env:CAPTURE_STAGING_DIRECTORY = 'D:\financial\data invoice\plan06_local\demo_staging'
.\.venv\Scripts\python.exe -m src.ingestion.cli provision --master-file configs/examples/taxpayer_master.synthetic.json
$captureServer = Start-Process -FilePath "$PWD\.venv\Scripts\python.exe" -ArgumentList @('-m','uvicorn','src.app:create_app','--factory','--host','127.0.0.1','--port','8000','--limit-concurrency','16','--no-access-log') -WindowStyle Hidden -PassThru
```

Provision chỉ chạy một lần cho cùng master revision. Không trỏ demo vào DB legacy hoặc baseline PLAN_02–05. Migration `006_review.sql` nâng foundation 1–5 lên 6 khi gọi initialize/provision; API import và health không mở DB hoặc nạp model.

Mở `http://127.0.0.1:8000/review`, nhập token local đã tạo, taxpayer `demo-payer`, master revision 1. Token giữ trong bộ nhớ trang, không lưu localStorage hay URL. UI thông báo giới hạn dữ liệu/accuracy, hỗ trợ tải PDF/ảnh, danh sách chứng từ, task, bằng chứng, sửa và xuất JSON.

Sau upload, UI hiển thị mã job. Trong cùng session có `CAPTURE_WORKER_TOKEN` và grants, chạy:

```powershell
.\.venv\Scripts\python.exe -m src.jobs.worker --taxpayer-id demo-payer --job-id <capture-job-id>
```

Worker xử lý hữu hạn upload đã xếp hàng → reader → OCR/layout → CFR → quality → review tasks. UI poll trạng thái; HTTP upload không chờ model. Chưa có daemon tự drain queue; cần chạy worker cho mỗi job. Model/worker interpreter dùng cấu hình [model switch PLAN_03](../plan03/model_switch/runbook.md); PLAN_06 không đổi runtime/model đã pin. Khi xong:

```powershell
Stop-Process -Id $captureServer.Id
```

## Walkthrough review

1. Chọn chứng từ và task. Xem dữ liệu chuẩn hóa, raw/candidates, trang gốc và bbox. Có thể đổi trang để đối chiếu. Link ảnh được cấp hạn 120 giây, tối đa 300; vẫn yêu cầu bearer và đúng actor/tenant/taxpayer. UI tự xin grant khi tải trang; token truyền trong POST body, không trong query log.
2. Đánh dấu các trường muốn sửa/xác nhận. MST dùng đủ 10 hoặc 13 số; ngày ISO `YYYY-MM-DD`; tiền/số lượng dạng chuỗi thập phân như `200000.01`; không dùng float, dấu phân nhóm hoặc số mũ. Mỗi lệnh tối đa 32 trường; sửa nhiều hơn chia thành các revision.
3. VAT chọn TAXABLE_RATE/KCT/KKKNT. Chọn KCT/KKKNT tự đưa rate về NOT_APPLICABLE/null, không chuyển thành 0%. Không chọn treatment và numeric rate trái nhau trong cùng lệnh.
4. Chỉ xác nhận đủ dòng khi đã xem toàn bộ các trang và số dòng đúng. API yêu cầu số dòng hiện có và mọi page index; không tự suy COMPLETE từ việc đã sửa một dòng. MVP chưa thêm/tách/gộp dòng: thiếu dòng hoặc nhiều hóa đơn chuyển REQUEST_DATA/OPERATOR và upload nguồn đã xử lý lại.
5. Ghi lý do rồi lưu. Transaction tạo revision + correction event + audit + rederive + quality + task lineage. Khi hai người cùng sửa, người thứ hai nhận 409 và latest revision; UI tải lại, người dùng đối chiếu rồi gửi lại. Bản nguồn/candidate không bị ghi đè.
6. Xuất JSON gồm CFR head, tổng quan sát, tổng tính từ items, issues còn lại và giới hạn. Export không đồng nghĩa đã hoàn tất review. Với job đang mở trong phiên, nút Hoàn tất chỉ được máy chủ chấp nhận khi không còn issue/task cản trở; không có verdict thuế.

Task thiếu nguồn có nút yêu cầu dữ liệu/chuyển xử lý riêng và reason. Đây là lưu trạng thái/audit, chưa gửi email/thông báo. Sau sửa, task cũ resolve/supersede, task mới gắn revision mới; human proof đã xác minh được giữ lại. Issue UNPARSEABLE cũ vẫn ở immutable extraction artifact nhưng không được báo như lỗi hiện hành của field đã sửa có proof.

## API và hợp đồng

Mọi endpoint dưới `/v1` yêu cầu Bearer + `taxpayer_id`; trả envelope/schema version, private/no-store. Chỉ health public. OpenAPI lưu tại [openapi.json](openapi.json), JSON Schema tại `agent3_tax_compliance/contracts/review-v1`.

| Endpoint | Mục đích |
|---|---|
| POST /v1/ingestions | Upload raw, giữ hợp đồng PLAN_02 và Idempotency-Key |
| POST /v1/capture-jobs?ingestion_id=… | Xếp lượt capture, dedupe theo ingestion |
| GET /v1/jobs/{id} | Trạng thái, attempts, artifact/record refs, error code/recovery |
| POST /v1/jobs/{id}/recover | RETRY / REQUEST_DATA / OPERATOR + reason |
| POST /v1/jobs/{id}/complete | Hoàn tất manual capture sau kiểm tra head và quality |
| GET /v1/records | Danh sách theo taxpayer, keyset cursor |
| GET /v1/records/{id} | CFR head, candidates, assessment hiện hành, page count |
| GET /v1/records/{id}/revisions | Phân trang revision metadata/hash |
| GET /v1/records/{id}/revisions/{n} | CFR bất biến của revision đã chọn |
| GET /v1/review-tasks | Filter record_id/revision/status, cursor, limit 1–100 |
| POST /v1/records/{id}/review-tasks | Dedupe task từ assessment hiện hành |
| POST /v1/review-tasks/{id}/actions | REQUEST_DATA / OPERATOR / REOPEN + reason |
| POST /v1/corrections | CorrectionCommand + Idempotency-Key; quyền WRITE |
| POST /v1/cfr-extractions/{id}/evidence-grants | Grant ảnh theo page/actor, TTL giới hạn |
| POST /v1/evidence-image | Redeem token trong body + auth, PNG đã kiểm hash |
| GET /v1/cfr-extractions/{id}/evidence/{candidate} | Resolve block/span, render/original geometry |
| GET /v1/records/{id}/export | CFR + observed/derived totals + issues + limitations |
| GET /v1/records/{id}/audit | Phân trang actor/time/reason/hash/paths; không trả before/after field values |
| POST /v1/records/{id}/audit-replay | Kiểm raw hash → cached OCR/Document → canonicalize lại → áp correction events → rederive → so head |

CorrectionCommand: record_id, expected_revision, task_id, reason, changes[]. Mỗi change có field_path và SET(new_value hoặc selected_candidate_id), CONFIRM, CLEAR. Tenant/payer lấy từ context đã auth và query; không tin tenant gửi trong body. Item path dùng immutable ID, không line number. Không cho sửa derived, identity, source hoặc master. Idempotency gắn actor + command digest; key cũ với payload khác trả 409. Audit failure rollback toàn transaction.

Cursor được ký, khóa tenant/payer/filter/revision và snapshot rowid, hết hạn 1 giờ. Tenant filter áp trước pagination; insert mới không chen vào snapshot cũ. Trạng thái task có thể đổi do correction trong lúc duyệt; snapshot không đóng băng status của task.

## Tái hiện kiểm chứng

Cwd `D:\financial`:

```powershell
agent3_tax_compliance/.venv/Scripts/python.exe scripts/export_review_contracts.py
agent3_tax_compliance/.venv/Scripts/python.exe scripts/build_review_baseline.py
python scripts/validate_review.py
```

Builder sao lưu SQLite PLAN_05 sang `data invoice/plan06_local/{native,hybrid}.sqlite3` rồi migrate **bản sao**. 15 lượt sửa mô phỏng không dùng để tính accuracy sau human review. Latency chỉ đo transaction correction trên dữ liệu local; không phải p95 cả OCR pipeline hoặc thời gian người sửa.

Mã quality mới có implementation hash khác PLAN_05. Bằng chứng cũ không bị ghi đè; 10 file nguyên bản đã lưu với hash khớp tại `archive/plan06_pinned_plan05_quality`. Replay lịch sử bằng:

```powershell
agent3_tax_compliance/.venv/Scripts/python.exe scripts/replay_plan05_snapshot.py
```

Script này chỉ đọc 15 assessment cũ và policy snapshots, không migrate DB. Validator PLAN_05 nguyên bản phản ánh code tại gate cũ; với workspace mới dùng historical replay trên để kiểm chứng thay vì chạy builder cũ rồi ghi đè báo cáo.

Node kiểm tra syntax và DOM harness; chưa có browser/user visual acceptance. UI còn cần thử thao tác thực, bố cục/mobile, keyboard/screen-reader và thời gian sửa trước release. Auth vẫn là shared-secret local adapter; SSO, queue daemon, hardening và vận hành nhiều worker thuộc PLAN_14.
