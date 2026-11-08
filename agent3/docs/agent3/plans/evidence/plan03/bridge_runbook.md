# Chạy OCR/layout bridge

> **Runbook Tesseract trước model switch, giữ làm lịch sử.** Mặc định hiện là PP-OCRv6 + VietOCR; dùng [runbook hiện hành](model_switch/runbook.md) và `validate_ocr_switch.py`. Các lệnh baseline/validator cũ bên dưới không phải gate cho model mới.

Runtime kiểm chứng: Windows x64, app `.venv` của PLAN_01/02 và benchmark `envs/tesseract`. Không cài hoặc download thêm model. Đường dẫn tính tương đối từ workspace; không hardcode tài khoản Windows. `WorkerClient(benchmark_root=...)` cho phép chỉ định root khác khi cấu trúc workspace thay đổi.

## 1. Đầu vào từ PLAN_02

Làm theo [runbook ingestion](../plan02/runbook.md) để provision taxpayer, cấu hình auth grants, upload và chạy reader. Cần `ingestion_id` có document artifact, page images và extraction outbox. Dùng đúng taxpayer đã cấp quyền. `CAPTURE_WORKER_TOKEN` phải khớp grant có READ/WRITE hoặc ADMIN; không ghi token vào file chạy.

## 2. Chạy một tài liệu

Từ `D:\financial\agent3_tax_compliance`, giữ các biến `CAPTURE_DATABASE_PATH`, `CAPTURE_AUTH_GRANTS_JSON`, `CAPTURE_WORKER_TOKEN` theo runbook PLAN_02:

```powershell
& .venv/Scripts/python.exe -m src.adapters.ocr.cli --taxpayer-id demo-payer --ingestion-id <ingestion-id>
```

Thay `<ingestion-id>` bằng ID thật. Mặc định đọc `configs/ocr/tesseract_psm3.json`; có thể truyền `--config configs/ocr/tesseract_psm6.json` cho lần thử riêng. CLI initialize/migrate database foundation đến version 3; từ chối legacy DB. Kết quả stdout chỉ có ID/status/attempts/config_key, không in nội dung chứng từ.

Lấy kết quả bằng Bearer auth như ingestion:

```text
GET /v1/ingestions/{ingestion_id}/extractions/{config_key}?taxpayer_id=demo-payer
```

`config_key` được CLI trả về; endpoint trả status và typed normalized document. COMPLETE chỉ là đủ bước xử lý trang; PARTIAL/FAILED luôn xem từng page issue trước dùng dữ liệu. PLAN_04 là bước tiếp theo để tạo CFR. `IngestionView.extraction_status=QUEUED` là dấu giao đầu vào của PLAN_02, không phải status OCR.

## 3. Phục hồi và giới hạn

- Chạy lại cùng ID/config/runtime sau thành công trả artifact đã commit, không OCR lại.
- Worker process timeout/transient IO retry tối đa 2 lần; bad input/crash/protocol/model missing không tự fallback.
- CLI/app chết giữa tài liệu: sau lease hết, chạy lại cùng lệnh; reclaim tối đa 2 lần, dùng cache trang thành công. Lease = số trang × timeout × worker attempts + 30 giây.
- Một database chỉ có một lease OCR hoạt động; gọi khi đang bận nhận QUEUED/PROCESSING, chạy lại sau. Chưa có daemon tự drain queue.
- Kết quả terminal bất biến; xử lý lại bằng config version mới và lưu provenance riêng. Không sửa database để xóa failure hoặc đặt lại counter.
- Windows Job Object giới hạn 3 tiến trình (venv redirector, Python interpreter, Tesseract), 512 MiB tổng mặc định, kill cây tiến trình khi đóng job; từng trang 30 giây mặc định. Đây là giới hạn tài nguyên, chưa phải security container. POSIX chưa được nghiệm thu.
- Response JSONL tối đa 4 MiB mặc định, text/detection/polygon có bound. Timeout/output/protocol lỗi không được coi là empty-success.
- Temp page/output dùng TemporaryDirectory; bình thường/failure có cleanup. Nếu parent bị kill cứng, thư mục `capture-ocr-*` trong OS temp có thể còn; cần retention/cleanup trong PLAN_14, không xóa nguồn/raw đã commit.

## 4. Tái hiện benchmark và gate

Từ workspace root, PLAN_02 baseline local phải có sẵn:

```powershell
& agent3_tax_compliance/.venv/Scripts/python.exe scripts/export_ocr_contracts.py
& agent3_tax_compliance/.venv/Scripts/python.exe scripts/build_plan03_baseline.py
python scripts/validate_plan03.py
```

Lệnh cuối dùng system Python có `jsonschema`; tests/inference vẫn chạy app/benchmark interpreter riêng. Baseline tạo DB bằng backup cục bộ từ `data invoice/plan02_local/native_unicode_v2/baseline.sqlite3`; giữ nguyên DB/evidence PLAN_02. Manifests có dữ liệu ở `data invoice/plan03_local/`, báo cáo ở thư mục này. Không chạy lại validator PLAN_01/02 để ghi đè báo cáo lịch sử.

Chỉ kiểm tra OCR tests từ backend root:

```powershell
& .venv/Scripts/python.exe -m unittest discover -s tests/ocr -v
```

Tests dùng fixture project và worker thật cho smoke/timeout; các fault injection chỉ kiểm tra recovery/protocol, không dùng làm accuracy. Nếu MODEL_UNAVAILABLE, kiểm tra matrix/checksum/env/language data; không tự download hoặc báo test inference đạt bằng mock.
