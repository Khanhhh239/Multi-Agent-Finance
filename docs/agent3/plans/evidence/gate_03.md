# Gate PLAN_03 — OCR/layout bridge

Ngày: **12/10/2026**. Phạm vi nghiệm thu: **ocr-layout-v1 / technical-functional**, theo scope kỹ thuật PLAN_00 và input ingestion-v1/route-v1.1 của PLAN_02.

> **Bổ sung hiện hành — đổi model theo yêu cầu người dùng:** mặc định đã chuyển sang **PP-OCRv6 + VietOCR**. [Gate model switch](plan03/model_switch/validation_summary.json): **72 tests PASS, 12 schemas, 5 tài liệu/6 trang**, có 4 trang chạy hybrid thật và 2 trang native bỏ qua model. [Thiết kế engine registry](../../../../agent3_tax_compliance/configs/ocr/README.md) · [runbook hiện hành](plan03/model_switch/runbook.md). Phần baseline Tesseract 38 tài liệu bên dưới giữ làm lịch sử, không phải kết quả benchmark hybrid.

**Quyết định: PASS_TECHNICAL_FUNCTIONAL — cho phép bắt đầu PLAN_04.** Đã qua **67 tests** (22 foundation + 23 ingestion + 22 OCR), **11 schemas**, 3 cấu hình × 10 mẫu so sánh và **38 normalized document artifacts / 41 trang**. Kết quả/checksum chính thức nằm trong [validation summary](plan03/validation_summary.json). Không chứng nhận quality production hoặc real-data acceptance.

## Đầu ra và kiểm chứng

- Bridge JSONL v1 bọc benchmark OCRResult 1.1; strict schema/correlation/version/output bounds, không import chung hai package `src`.
- Baseline Tesseract CPU chạy bằng benchmark interpreter thật; model/executable/DLL/package hashes và runtime versions được khóa trong [matrix](plan03/adapter_runtime_matrix.json).
- Normalized geometry/evidence, provenance native/OCR, conservative dedup kể cả native split spans, conflict links, column/table ordering và geometry UNAVAILABLE.
- SQLite migration 003, claims/leases/token fencing, tenant-scoped immutable cache/result, audit transaction, bounded retry và process-tree timeout/memory limits.
- API đọc artifact có Bearer + taxpayer scope; CLI hữu hạn xử lý document từ extraction outbox. Không tự chạy model khi import app.

Lệnh từ workspace root:

```powershell
& agent3_tax_compliance/.venv/Scripts/python.exe scripts/export_ocr_contracts.py
& agent3_tax_compliance/.venv/Scripts/python.exe scripts/build_plan03_baseline.py
python scripts/validate_plan03.py
```

Validator chạy foundation/ingestion/OCR regressions bằng app interpreter, OCR smoke bằng benchmark interpreter; kiểm tra schemas, raw run hashes, cùng split/images/reference, normalized document artifacts, runtime checksums và legacy database/evidence lịch sử không thay đổi.

## Baseline và quyết định

Ba cấu hình PSM 3/6/11 trên **10 logical synthetic PNG** chung split. Chọn **PSM 3**, ưu tiên exact ngày/tổng tiền trước CER/WER; quality tie dùng page segmentation tổng quát, không quyết định bằng nhiễu latency. Chạy tiếp pipeline **38 tài liệu / 41 trang** của PLAN_02 trong database backup riêng.

Chi tiết metric/mẫu số/latency/RAM: [comparison](plan03/ocr_baseline_comparison.md), [baseline JSON](plan03/baseline_summary.json), [selection và lỗi](plan03/OCR_SELECTION.md). Điểm OCR là ENGINE_HEURISTIC_NOT_CALIBRATED; không dùng làm xác suất field.

## Giới hạn còn mở và bàn giao

- CER 15,94%, WER 56,20%; exact ngày 10/10, tổng tiền 7/9 trong **oracle regions tổng hợp**, chưa phải accuracy extraction. Chưa đạt tự động chấp nhận.
- Chưa có bộ hóa đơn thuế Việt Nam được phép dùng và nhãn người đối chiếu; DQ-01–05 vẫn theo gate PLAN_00, nghiệm thu thực tế ở PLAN_05–06.
- Chưa benchmark cross-engine, blur/perspective/cell recognition; fallback tự động tắt. Không train trong chặng này.
- Reading order/table candidates là heuristics, chưa tạo line items. COMPLETE nghĩa đủ bước xử lý trang, không phải đủ dữ liệu/đúng nghiệp vụ.
- Windows Job Object đã kiểm tra; POSIX/security container/distributed scheduler/retention khi parent bị kill cứng thuộc hardening PLAN_14.
- Result terminal bất biến; rerun cấu hình khác tạo version/job mới. Chưa có daemon drain queue hoặc review UI.

PLAN_04 nhận `NormalizedDocumentExtraction` và evidence/raw responses để trích CFR/line items. PLAN_05 nhận raw line scores, distributions, manifests và nhóm lỗi để đánh giá/calibration. [Runbook](plan03/bridge_runbook.md) ghi cách tái hiện và phục hồi.
