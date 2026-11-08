# PLAN_02 — Upload, phân loại và đọc PDF theo trang

> Trạng thái triển khai: **DONE — ingestion-v1**, 12/10/2026. Upload/auth, bounded reader, per-page routing/geometry, durable queue/recovery và baseline đã vượt gate kỹ thuật. Xem [gate_02](evidence/gate_02.md) và [runbook](evidence/plan02/runbook.md); chưa chạy OCR model.

[Lộ trình tổng](README.md) · Trước theo thứ tự đọc: [PLAN_01](PLAN_01_CONTRACT_FOUNDATION.md) · Sau: [PLAN_03](PLAN_03_OCR_LAYOUT_BRIDGE.md)

## 1. Kết quả cần đạt và điều kiện bắt đầu

Từ file tải lên tạo SourceEnvelope và từng trang có text/native image/geometry đáng tin; chỉ chuyển phần cần thiết sang OCR.

- Phụ thuộc bắt buộc: PLAN_01 đạt gate; dữ liệu PLAN_00 sẵn sàng.
- Ước lượng: **3–5 ngày công**, một người làm tập trung; chưa bao gồm thời gian chờ dữ liệu/hạ tầng/nghiệp vụ.
- Đối chiếu [NEW_PLAN](../NEW_PLAN.md): mục 3, 4.4, 12, 14.
- Đầu vào: Envelope/evidence contracts, upload policy, functional set.

Không bắt đầu phần phụ thuộc khi gate đầu vào chưa qua. Có thể chuẩn bị fixture/tài liệu độc lập, nhưng không ghi cả chặng DONE vì đã tạo scaffold.

## 2. Tài sản hiện có và cách tái sử dụng

Có PyMuPDF trong môi trường prototype theo kiểm kê trước; phải kiểm tra phiên bản/runtime đích trước khi tái dùng. Không giả định PDF có text là đọc được đúng thứ tự.

Kiểm tra lại tính tồn tại/phiên bản khi triển khai; kết quả kiểm kê là bằng chứng tham khảo, không thay nghiệm thu runtime đích.

## 3. Module và hợp đồng cần xây

Code ingestion và schemas đã hiện thực; storage dùng repository/SQLite foundation riêng, không cần thư mục src/storage trùng chức năng:

`agent3_tax_compliance/src/ingestion/{upload,detector,pdf_reader,preprocess,models,repository,service,sandbox,reader_worker,auth,api,cli}.py; migrations/002_ingestion.sql; contracts/ingestion-v1/; tests/ingestion/`

DocumentArtifact/PageArtifact chứa source_id/hash, page_id/index, original/render dimensions, rotation và geometry version. Page route NATIVE_TEXT/OCR/HYBRID/UNSUPPORTED độc lập SourceFormat. Theo registry PLAN_01, source_format dùng PDF/IMAGE; PDF_TEXT/PDF_IMAGE là dataset families, không tạo enum cạnh tranh. Ngoài lát cắt chỉ nhận diện signature/container để trả typed unsupported.

Mọi artifact phải có schema/config version, input hash hoặc record revision, creator/stage và timestamp. Artifact chứa dữ liệu thật lưu ngoài git theo policy; tài liệu chỉ ghi metadata đã che dữ liệu.

## 4. Công việc chi tiết theo thứ tự

### P02-T01 — Nhận upload có ràng buộc

- [x] Hoàn thành: upload/auth/API/config, stream byte/time limits và typed rejects; gate_02/tests ghi bằng chứng.
- Thực hiện: Stream file vào staging, giới hạn bytes/page/pixel, hash khi đọc; tên lưu do hệ thống cấp. Kiểm tra tenant/taxpayer trước khi tạo job.
- Đầu ra: upload.py, limits config.
- Kiểm chứng: Chặn path traversal, file quá lớn và spoof MIME; không đọc hết file vào RAM để mới kiểm size.

### P02-T02 — Detector theo chữ ký

- [x] Hoàn thành: detector signature/MIME/extension; ZIP/OLE2/XML unsupported, không extract hay invoice-route.
- Thực hiện: So MIME/header/parser result; nhận PDF, PNG/JPEG và báo rõ format chưa hỗ trợ. Registry đầy đủ có ZIP/XLSX và OLE2/XLS cho chặng sau; extension không là bằng chứng duy nhất.
- Đầu ra: detector.py + route table.
- Kiểm chứng: File .pdf chứa ZIP bị reject/mislabel issue; UNKNOWN_XML không bị route sang invoice adapter.

### P02-T03 — Đọc PDF có giới hạn

- [x] Hoàn thành: isolated reader, parser/render budgets, Windows Job Object memory cap + timeout và corrupt/encrypted tests.
- Thực hiện: Kiểm tra encrypted/corrupt/page count, trích text blocks + bbox; render trang theo cấu hình DPI. Không chạy script/embedded attachment; timeout và memory cap.
- Đầu ra: pdf_reader.py.
- Kiểm chứng: PDF mã hóa không mật khẩu trả typed issue; PDF hỏng không làm worker chết cả batch.

### P02-T04 — Chọn route theo từng trang

- [x] Hoàn thành: route-v1.1, mixed/hidden/garbage/HYBRID/NBSP tests; routes và reasons lưu trong PageArtifact.
- Thực hiện: Đánh giá text coverage, glyph hợp lệ và vùng ảnh/bảng; ngưỡng route có config/version. PDF mixed không bị phân loại toàn tài liệu theo trang đầu.
- Đầu ra hiện thực: DocumentArtifact/PageArtifact JSON chứa route/policy/reasons/regions; baseline_summary.json có route confusion.
- Kiểm chứng: Tài liệu text + scan tạo đúng hai route; text layer rác không đủ để bỏ OCR.

### P02-T05 — Chuẩn hóa geometry

- [x] Hoàn thành: original→render→processed affine/inverse, PDF rotations/crop origin/EXIF và stable page IDs. Processed raster hiện identity; chưa tự estimate deskew/crop.
- Thực hiện: Lưu transform gốc→render→deskew/crop, ảnh gốc và ảnh xử lý. Không ghi đè raw; hỗ trợ xoay 90/180/270 và transform nghịch đảo.
- Đầu ra: preprocess.py + transform fixtures.
- Kiểm chứng: Bbox quay ngược lên PDF gốc đúng trong tolerance đã chốt; page_id không đổi giữa retry.

### P02-T06 — Tạo artifacts và hàng đợi

- [x] Hoàn thành: source/STORED transaction, durable enqueue, document/renders/extraction outbox atomic, idempotency và cleanup.
- Thực hiện: Persist raw hash, document/page manifests rồi enqueue extraction; raw lưu thất bại thì không có job runnable. Idempotency cùng key/hash/versions trả cùng ingestion; key cùng mà khác payload báo conflict.
- Đầu ra: job repository, artifact writer.
- Kiểm chứng: Retry upload không tạo hai tài liệu logic; staging orphan có cleanup policy.

### P02-T07 — Đánh giá native text baseline

- [x] Hoàn thành: [native baseline](evidence/plan02/native_pdf_baseline.md), 30 originals/32 pages + 11 extra cases. Chỉ functional diagnostics, không real accuracy.
- Thực hiện: Chạy reader trên functional set, lưu text/bbox và lỗi reading order. Đo page route confusion và extraction latency riêng khỏi OCR.
- Đầu ra: native_pdf_baseline.md.
- Kiểm chứng: Mỗi quyết định route có lý do; không gọi native text confidence=1.0.

### P02-T08 — Kiểm tra recovery

- [x] Hoàn thành: real process death sau raw/trước enqueue, stale lease/token, rollback audit/outbox và bounded retry; [runbook](evidence/plan02/runbook.md).
- Thực hiện: Kill worker sau lưu raw/trước enqueue, thử upload lại và job retry. Ghi error category, retryable, next_action.
- Đầu ra: recovery fixtures + runbook.
- Kiểm chứng: Không mất raw/audit; lỗi không retryable không lặp vô hạn.

## 5. Tiến độ bên trong chặng

- Ngày 1: upload, storage và detector.
- Ngày 2–3: PDF reader, routing từng trang, geometry.
- Ngày 4–5: idempotency/recovery và baseline trên functional set.

Cuối mỗi ngày cập nhật task IDs đã làm, bằng chứng và blocker vào bảng tiến độ tổng. Khi phát hiện phụ thuộc mới hoặc scope tăng, ghi lại estimate còn lại; không cố giữ lịch bằng cách bỏ invariant.

## 6. Ca kiểm thử và tình huống bắt buộc

- [x] PDF 2 trang: một native text, một scan.
- [x] PDF có text vô hình bị trùng với OCR image.
- [x] Ảnh EXIF rotation và PDF rotation khác nhau.
- [x] Corrupt/encrypted/oversized upload; cùng idempotency key khác hash.

Dùng fixture tổng hợp nhỏ cho contract/recovery tests, dữ liệu có nhãn cho accuracy và sandbox thật cho connector. Không thay accuracy evaluation bằng unit test parser. Chỉ chạy phần test phù hợp chặng và integration qua ranh giới vừa thay đổi.

## 7. Gate hoàn thành và bàn giao

**Điều kiện gate:** Mọi trang trong phạm vi có route hoặc typed error, evidence tọa độ truy ngược được; upload tenant isolation/idempotency và tài nguyên giới hạn được kiểm chứng.

- [x] Mỗi task có artifact và command trong gate_02/runbook.
- [x] Không phát hiện lỗi hợp đồng tiền/tenant/version trong 45 checks đã chạy (22 foundation + 23 ingestion).
- [x] Giới hạn hỗ trợ/known gaps ghi rõ; chưa nghiệm thu accuracy thực tế.
- [x] Đã ghi [gate_02](evidence/gate_02.md), validation summary, test outputs và baseline.
- [x] Bàn giao: PLAN_03 nhận PageArtifact và route decisions/outbox; PLAN_04 nhận native blocks/evidence. Consumer OCR chưa triển khai.

## 8. Khi chưa đạt hoặc bị chặn

Ghi blocker cụ thể, task bị ảnh hưởng, điều kiện gỡ và người/nguồn cần cung cấp. Tiếp tục các task độc lập. Không biến thiếu dữ liệu, thiếu môi trường hoặc lỗi runtime thành kết quả thành công; không ghi DONE khi chỉ có mock mà gate yêu cầu dữ liệu thật.

Lệnh bootstrap, schema export, baseline, validate và API/worker/recovery nằm trong [hồ sơ](evidence/plan02/README.md) và [runbook](evidence/plan02/runbook.md). Chặng tiếp theo PLAN_03; không chạy model inference trong PLAN_02.
