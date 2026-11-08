# Native/PDF reader functional baseline — 12/10/2026

Bộ project-generated của PLAN_00: 30 file/10 logical documents; thêm 11 fixtures PLAN_02. Không có OCR inference hoặc số accuracy thực tế.

| Expected route | Actual route | Pages |
|---|---|---:|
| NATIVE_TEXT | NATIVE_TEXT | 11 |
| OCR | OCR | 21 |

Original pages: 32. Route confusion chỉ là functional diagnostic theo loại fixture đã sinh, không chứng minh generalization.

Latency reader (parse/native/layout/render; không gồm OCR hay process startup): median 123.10 ms, max 180.08 ms trên 30 documents. Không là SLO production.

Extra cases: mixed, invisible overlay, hybrid, garbage text, encrypted, oversized, rotations 90/180/270 có crop, corrupt, JPEG EXIF 6. Ba negative cases trả đúng typed errors; không có extraction outbox cho chúng.

Reading order: reader giữ source_order và reading_order heuristic; chưa chứng minh thứ tự nhiều cột hoặc độ đúng line items. Invisible text bị bỏ khỏi native blocks; HYBRID có OCR regions và deduplication_required cho PLAN_03.

Manifest, text/bbox và renders nằm trong `data invoice/plan02_local/` (ignored). Raw hashes ở baseline_summary.json. Retry cùng ingestion giữ page_id; không ghi đè raw. NATIVE_TEXT không tạo probability confidence=1.0.

Lệnh root: `.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/build_plan02_baseline.py`. Chạy lại tái dùng ingestions đã commit; latency của reader lấy từ artifact lần đầu.
