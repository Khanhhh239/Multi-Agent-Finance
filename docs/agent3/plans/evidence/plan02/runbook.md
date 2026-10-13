# Runbook PLAN_02 — local API và worker

Ngày: 12/10/2026. Cwd các lệnh dưới: `D:\financial\agent3_tax_compliance`. Chỉ demo bằng synthetic taxpayer/documents; sample tax code không đại diện doanh nghiệp thật.

## Chuẩn bị

`.venv` đã có foundation + 5 dependencies ingestion. Khi tái tạo từ workspace nguồn, chạy bootstrap foundation ở root nếu chưa có `.venv`, sau đó bootstrap_ingestion bằng interpreter prototype. Không ghi đè env cũ:

```powershell
# cwd D:\financial
.\agent3_tax_compliance\venv\Scripts\python.exe scripts/bootstrap_ingestion.py
```

App không tự provision tenant/taxpayer hoặc credential. Trong một PowerShell session, tạo credential local và grant hash; không in token ra report:

```powershell
# cwd D:\financial\agent3_tax_compliance
$captureBytes = New-Object byte[] 32
$captureRng = [Security.Cryptography.RandomNumberGenerator]::Create()
$captureRng.GetBytes($captureBytes)
$captureRng.Dispose()
$env:CAPTURE_WORKER_TOKEN = [Convert]::ToBase64String($captureBytes)
$captureHasher = [Security.Cryptography.SHA256]::Create()
$captureDigest = ([BitConverter]::ToString($captureHasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($env:CAPTURE_WORKER_TOKEN)))).Replace('-', '').ToLowerInvariant()
$captureHasher.Dispose()
$captureGrants = @(@{
  token_sha256 = $captureDigest
  actor_id = 'local-admin'
  tenant_id = 'demo-tenant'
  taxpayer_ids = @('demo-payer')
  permissions = @('READ', 'WRITE', 'ADMIN')
})
$env:CAPTURE_AUTH_GRANTS_JSON = ConvertTo-Json -InputObject $captureGrants -Depth 5 -Compress
$env:CAPTURE_DATABASE_PATH = 'data/foundation/capture.sqlite3'
.\.venv\Scripts\python.exe -m src.ingestion.cli provision --master-file configs/examples/taxpayer_master.synthetic.json
```

Provision chỉ insert master revision mới, không upsert/ghi đè. Đã provision cùng revision thì không chạy lại lệnh đó. Muốn dùng dữ liệu thật phải tạo master đúng tenant/taxpayer/quyền dùng và revision, không dùng sample tax code.

## API và worker

Chạy API trên loopback. Ví dụ khởi động background ẩn để dùng tiếp cùng session/grants:

```powershell
$captureServer = Start-Process -FilePath "$PWD\.venv\Scripts\python.exe" -ArgumentList @('-m','uvicorn','src.app:create_app','--factory','--host','127.0.0.1','--port','8000','--limit-concurrency','16','--no-access-log') -WindowStyle Hidden -PassThru
```

Upload raw body, không multipart; tên header chỉ dùng kiểm định dạng, tên lưu luôn do hệ thống cấp:

```powershell
curl.exe -sS -X POST 'http://127.0.0.1:8000/v1/ingestions?taxpayer_id=demo-payer&master_revision=1' -H "Authorization: Bearer $env:CAPTURE_WORKER_TOKEN" -H 'Idempotency-Key: demo-upload-001' -H 'Content-Type: application/pdf' -H 'X-Filename: invoice.pdf' --data-binary '@tests/fixtures/ocr/functional_set_v1/syn-00-pdf_text.pdf'
.\.venv\Scripts\python.exe -m src.ingestion.cli work --taxpayer-id demo-payer --limit 10
```

POST trả 202 và IngestionView (thường QUEUED). Lấy ingestion_id/source_id từ JSON; các endpoint sau yêu cầu cùng Bearer grant + taxpayer_id:

| Endpoint | Ý nghĩa |
|---|---|
| GET /v1/health | Public health; không cần model/secret hoặc mở DB |
| GET /v1/ingestions/{id}?taxpayer_id=… | Status, attempts, typed issue, extraction_status |
| GET /v1/ingestions/{id}/document?taxpayer_id=… | Document/page manifests và native blocks sau SUCCEEDED |
| GET /v1/ingestions/{id}/pages/{page_index}/image?taxpayer_id=… | Canonical PNG, private/no-store |
| GET /v1/sources/{source_id}/raw?taxpayer_id=… | Raw attachment, octet-stream/nosniff |
| POST /v1/ingestions/{id}/retry?taxpayer_id=… | Explicit retry nếu failure retryable và còn attempts |

Worker là lệnh xử lý hữu hạn, không daemon tự khởi động từ API. `--limit` 1–100; chạy tiếp để drain pending queue. Extraction outbox chưa có consumer tới PLAN_03. Dừng đúng process server do session vừa tạo khi xong:

```powershell
Stop-Process -Id $captureServer.Id
```

## Recovery và typed errors

- STORED: raw/audit đã commit nhưng chưa enqueue. Retry upload cùng key/hash/config hoặc `cli recover --taxpayer-id demo-payer` tạo đúng một job.
- PROCESSING sau worker chết: đợi lease hết (timeout + 15 giây), chạy `cli work` lại. Token mới chặn worker cũ ghi outcome; page_id không đổi. Hết max attempts → FAILED không retry.
- FAILED retryable: sửa hạ tầng/config tài nguyên phù hợp rồi gọi endpoint retry, sau đó chạy worker. Encrypted/corrupt/limit input errors không tự lặp; export file phù hợp và dùng key mới.
- Cùng idempotency key với hash/master/processing profile khác → 409. Cùng input/config → cùng ingestion, kể cả đã FAILED; upload lại không tự bỏ qua retry policy.
- Upload timeout/too-large/mismatch/unsupported bị từ chối trước raw commit, không có runnable job. Body được kiểm size khi stream; Content-Length chỉ là early hint.
- `cli cleanup` cần ADMIN; chỉ xóa `.part` hoặc worker scratch namespace do hệ thống tạo và quá TTL, không đụng raw/documents đã commit. TTL dài hơn deadline tránh dọn worker đang chạy.

Migration và recovery không sửa prototype databases. Typed issue luôn có code/retryable/next_action, không trả raw exception chứa nội dung chứng từ. Credential grants là local shared-secret adapter, chưa có SSO/expiry/rate policy production. Đổi grant/env cần tạo lại app; secret lưu ngoài repository.
