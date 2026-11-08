# PLAN_03 — OCR/layout bridge

> **Mặc định hiện hành đã đổi sang PP-OCRv6 + VietOCR.** Xem [model switch](model_switch/README.md), [72-test gate](model_switch/validation_summary.json) và [runbook mới](model_switch/runbook.md). Phần dưới mô tả lần triển khai/baseline Tesseract ban đầu, giữ làm lịch sử.

Ngày triển khai: **12/10/2026**. Phạm vi `ocr-layout-v1`, kế thừa gate kỹ thuật của PLAN_00–02.

Ứng dụng nhận page artifacts từ PLAN_02, gọi Tesseract trong interpreter/cwd của benchmark qua JSONL, rồi lưu `NormalizedDocumentExtraction`. Không import package `src` của benchmark vào ứng dụng. Native pages bỏ qua inference; OCR/HYBRID dùng raster chuẩn của PLAN_02. HYBRID chạy toàn trang để tránh cắt mất ký tự, sau đó dedup theo geometry và text.

| Task | Bằng chứng |
|---|---|
| P03-T01 | `protocol.py`, 11 schemas tại `contracts/ocr-v1/`, request/response examples; correlation/version/output-limit tests |
| P03-T02 | [Runtime matrix](adapter_runtime_matrix.json), interpreter thật, checksum executable/DLL/language data/adapter/package implementations; CPU Job Object peak memory |
| P03-T03 | `normalizer.py`; normalized polygon, evidence và raw response; reject NaN, zero-area/out-of-page; full-page geometry UNAVAILABLE |
| P03-T04 | `layout_merge.py`; exact overlap dedup, split-span dedup, conflict candidates, column/table ordering tests |
| P03-T05 | `worker_client.py`, `repository.py`, migration 003; process tree limits, SQLite claims/leases, retry budget, tenant-scoped cache, audit rollback |
| P03-T06 | [So sánh baseline](ocr_baseline_comparison.md), [summary](baseline_summary.json), manifests cục bộ có checksum |
| P03-T07 | [Lựa chọn OCR](OCR_SELECTION.md), lỗi/giới hạn và fallback policy |
| P03-T08 | [Runbook](bridge_runbook.md), `tests/ocr/`, [validation](validation_summary.json) |

`ocr_jobs` là trạng thái chạy theo ingestion + config key. `extraction_outbox` của PLAN_02 tiếp tục là bằng chứng đã giao đầu vào, không dùng `IngestionView.extraction_status` để kết luận OCR đã xong; đọc endpoint extraction riêng. Không có OCR daemon hoặc scheduler tự chạy trên import/startup.

Cache thành công bất biến, khóa theo tenant/taxpayer, page artifact/hash, preprocess/config/runtime và checksum implementation bridge/normalizer/merge. Document result COMPLETE/PARTIAL/FAILED đã commit cũng bất biến. Timeout/transient IO retry tối đa 2 lần trong worker; crash, bad input, protocol error, model unavailable không tự retry. Worker ứng dụng chết trước commit có thể reclaim sau lease, tối đa 2 claims. Sau khi PARTIAL/FAILED đã lưu, giữ artifact để điều tra; chạy cấu hình có version mới khi cần xử lý lại, không ghi đè kết quả cũ.

Mỗi claim có audit và completion/result hash ghi chung transaction với audit. Thành công từng trang có thể cache trước document commit; crash/reclaim tận dụng lại trang thành công. Trang lỗi không được cache. Token cũ không thể hoàn tất claim mới. SQLite giữ tối đa một document OCR đang có lease trong một database; semaphore bổ sung giữ một subprocess mỗi app process. Nhiều database độc lập cần scheduler chung ở PLAN_14.

App env không thêm dependency; benchmark env có sẵn được dùng nguyên trạng. Có thêm `src/bridge_worker.py` vào benchmark, không sửa adapter cũ. DB mới dùng migration 003 từ version 1/2/empty; database prototype cũ và evidence PLAN_01/02 được giữ nguyên. Baseline PLAN_03 dùng SQLite backup riêng, không migrate DB baseline PLAN_02.

Bàn giao PLAN_04: normalized blocks giữ raw text, provenance từng nguồn, evidence bbox/polygon, page transform có inverse, conflict links, raw OCRResult 1.1 và input/runtime/config hashes. `table_candidates` là hint vùng/block, chưa phải rows/cells/line items. COMPLETE nghĩa đủ bước OCR cho mọi trang, kể cả trang trắng; không phải field đã đủ hoặc invoice hợp lệ. PLAN_05 nhận score distributions trong summary và line scores trong raw manifests; chưa có calibration.
