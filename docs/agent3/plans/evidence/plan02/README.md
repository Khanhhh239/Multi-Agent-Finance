# Hồ sơ PLAN_02 — ingestion-v1

Ngày nghiệm thu: **12/10/2026**. Scope: technical-functional-v1, project-generated fixtures. [Gate](../gate_02.md) ghi quyết định; [runbook](runbook.md) hướng dẫn API/worker; [baseline](native_pdf_baseline.md) ghi routing/latency; [validation summary](validation_summary.json) chứa counts và hashes.

## Kiến trúc đã hiện thực

1. Credential SHA-256 grant → trusted AccessContext → tenant/taxpayer/master revision validation.
2. HTTP byte stream → staging do hệ thống đặt tên → byte/time limit + SHA-256 → signature/MIME/extension checks.
3. Transaction lưu immutable raw + source audit + ingestion STORED. Transaction enqueue riêng ghi job snapshot + ingestion QUEUED + event; crash giữa hai bước được recover.
4. Worker claim lease/token → subprocess suspended → Windows Job Object memory/process limits → resume → parser/native/render → result validation.
5. Transaction lưu document + page PNGs + hashes + audit + extraction outbox → SUCCEEDED. Consumer OCR/layout thuộc PLAN_03.

`SUCCEEDED` ở đây nghĩa đã đọc và tạo page artifacts, không nghĩa đã trích field/CFR hoặc kết luận thuế. `extraction_status=QUEUED` là outbox đã sẵn sàng, chưa có OCR consumer.

## Hợp đồng và định dạng

Namespace schemas: `agent3_tax_compliance/contracts/ingestion-v1/`; 7 schemas. Kế thừa envelope/FieldObject contracts PLAN_01, không sửa wire schema cũ. SourceFormat thống nhất PDF/IMAGE; PDF_TEXT/PDF_IMAGE là dataset families, không thêm enum source cạnh tranh. Page route NATIVE_TEXT/OCR/HYBRID/UNSUPPORTED là quyết định từng trang. XML nhận diện UNKNOWN_XML; ZIP/XLSX và OLE2/XLS chỉ nhận diện container để trả UNSUPPORTED_FORMAT, không unzip/route invoice tự động.

Raw là file gốc bất biến trong SQLite; canonical render PNG cũng là processed raster ở profile hiện tại (render_to_processed identity). PDF rotation/crop và EXIF được lưu affine/inverse. Chưa tự ước lượng deskew hoặc crop nội dung; helper transform có tests, không quảng bá như đã có model deskew. PDF evidence dùng tọa độ unrotated crop với crop_origin riêng, render bbox được normalized top-left. Không dùng pixel bbox lẫn PDF points.

Native blocks giữ text đúng glyph nguồn (kể cả NBSP), source_order và reading_order heuristic; semantic whitespace normalization/line items thuộc PLAN_04. Policy route-v1.1 công nhận Unicode Zs là whitespace hợp lệ. Page valid_glyph_ratio/text_coverage là diagnostics, không là calibrated confidence. Invisible render mode/opacity thấp bị loại; occlusion và multi-column reading order phức tạp chưa được chứng minh đầy đủ.

HYBRID giữ native blocks + OCR regions + deduplication_required. PLAN_03 phải dedup theo evidence; không ghép text native với OCR một cách cộng dồn. Không có model inference trong PLAN_02.

## Giới hạn mặc định

| Tài nguyên | Mặc định |
|---|---:|
| Upload | 20 MiB, 60 giây; stream trước khi bounded read vào storage |
| Pending ingestions | 50 toàn database local |
| PDF pages | 40 |
| Source image/embedded image pixels | 32 triệu / ảnh |
| Rendered pixels | 8 triệu / trang; 40 triệu / document |
| Render DPI | 150 |
| Render/manifest bytes | 64 MiB mỗi budget |
| Text spans/characters | 2.000 spans và 200.000 chars / trang |
| Image objects/drawings | 500 image objects, 10.000 drawings / trang |
| Reader subprocess | 45 giây; 512 MiB tổng Job Object trên Windows |
| Retry | Tối đa 3 attempts, chỉ retryable failures hoặc expired lease |
| Staging TTL | 3.600 giây; phải dài hơn upload/worker deadline + margin |

Process cap Windows là **2** để chứa venv redirector + interpreter; tổng memory cap vẫn 512 MiB. Process được tạo suspended và gắn Job Object trước resume, tránh child thoát giới hạn. Timeout/close job dừng cả cây process. OS từ chối limit thì fail closed. POSIX RLIMIT path có code nhưng chưa nghiệm thu trên máy này; Job Object là resource containment, chưa thay sandbox/container production.

PDF repaired/encrypted/corrupt hoặc vượt resource limit bị từ chối với typed issue. Không chạy JavaScript/attachment, không extract archive. PNG/JPEG single-frame được xử lý; multi-frame ngoài scope. Không tuyên bố hỗ trợ mọi PDF hợp lệ hoặc mọi layout từ fixture này.

## Kiểm chứng

Root workspace:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/export_ingestion_contracts.py
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/build_plan02_baseline.py
python scripts/validate_plan02.py
```

Validator dùng jsonschema của Python hệ thống; suite foundation/ingestion chạy bằng `.venv` riêng. Không ghi đè báo cáo lịch sử PLAN_01. Snapshot additive của 5 distributions/333 files giữ tại đây, foundation snapshot 15 distributions/438 files vẫn được kiểm nguyên vẹn. Migration 002 chỉ áp dụng application_id foundation, giữ data và triggers migration 001.
