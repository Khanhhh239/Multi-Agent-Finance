# Runbook OCR hiện hành — PP-OCRv6 + VietOCR

Chạy sau upload/reader của [PLAN_02](../../plan02/runbook.md). Giữ database và Bearer grants/token như hướng dẫn PLAN_02. App env không thêm framework OCR; sử dụng `ocr_e2e_workflow/envs/ppocrv6_vietocr` và trọng số local.

Từ `D:\financial\agent3_tax_compliance`:

```powershell
& .venv/Scripts/python.exe -m src.adapters.ocr.cli --taxpayer-id demo-payer --ingestion-id <ingestion-id>
```

Thay placeholder bằng ingestion ID thật. Không truyền `--config` thì đọc `configs/ocr/default.json` → `ppocrv6_vietocr.json`. CLI trả config_key; dùng Bearer auth đọc:

```text
GET /v1/ingestions/{ingestion_id}/extractions/{config_key}?taxpayer_id=demo-payer
```

Chọn Tesseract riêng cho một lần chạy:

```powershell
& .venv/Scripts/python.exe -m src.adapters.ocr.cli --taxpayer-id demo-payer --ingestion-id <ingestion-id> --config configs/ocr/tesseract_psm3.json
```

Đổi mặc định lâu dài chỉ sửa pointer trong `configs/ocr/default.json`; tạo config version mới khi đổi model/tham số. Không xóa/ghi đè result cũ. Framework/adapter/model/runtime fingerprints tách cache và job của từng engine; lỗi engine không làm ứng dụng âm thầm chạy Tesseract.

Từ workspace root, kiểm tra smoke mặc định và gate hiện hành:

```powershell
& agent3_tax_compliance/.venv/Scripts/python.exe scripts/smoke_ocr_engine.py
& agent3_tax_compliance/.venv/Scripts/python.exe scripts/export_ocr_contracts.py
& agent3_tax_compliance/.venv/Scripts/python.exe scripts/build_ocr_switch_baseline.py
python scripts/validate_ocr_switch.py
```

Baseline cần input local PLAN_02; tạo SQLite backup riêng tại `data invoice/plan03_local/model_switch/`. Raw response/normalized artifacts lưu tại đó, báo cáo tại thư mục này. Chạy lại dùng artifact đúng config/runtime đã commit. Smoke vẫn chạy inference thật, có thể mất khoảng một phút CPU cho một trang; không cần chạy lại nếu không đổi model/runtime và báo cáo/hash vẫn hợp lệ.

Validator dùng system Python có jsonschema; unittest dùng app interpreter, connector tests dùng interpreter benchmark. [Runbook Tesseract trước đây](../bridge_runbook.md) giữ làm lịch sử; không dùng validator/baseline cũ để ghi đè gate model switch.

Timeout/recovery/audit/tenant behavior kế thừa PLAN_03. Sau crash ứng dụng, chờ lease hết rồi gọi lại cùng lệnh; tối đa 2 claims. Result terminal bất biến; chỉ rerun bằng config version mới khi có lý do. Chưa có daemon drain queue; cleanup khi parent bị kill cứng và scheduler nhiều database vẫn thuộc PLAN_14.

Để thêm engine, đọc [hướng dẫn registry](../../../../../../agent3_tax_compliance/configs/ocr/README.md). PLAN_04 chỉ nhận NormalizedDocumentExtraction; không gọi trực tiếp Paddle/VietOCR.
